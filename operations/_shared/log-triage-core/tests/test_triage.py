"""
Unit tests for the deterministic layer of log-triage (triage.py).

Run with: python3 -m unittest discover -s tests -v
(from the log-triage-core directory, stdlib unittest only — no deps)
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import triage  # noqa: E402

FIXTURES = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "fixtures")


def load_fixture(name):
    with open(os.path.join(FIXTURES, name)) as f:
        return f.read()


class TestAnchorDetection(unittest.TestCase):
    def test_iso_timestamp_is_anchor(self):
        self.assertTrue(triage.is_anchor("2026-06-01T12:00:00.123Z ERROR boom"))

    def test_json_line_is_anchor(self):
        self.assertTrue(triage.is_anchor('{"level": "INFO", "msg": "hi"}'))

    def test_syslog_line_is_anchor(self):
        self.assertTrue(triage.is_anchor("Jan  5 10:00:01 web01 sshd[1234]: Accepted publickey"))

    def test_stack_frame_is_not_anchor(self):
        self.assertFalse(triage.is_anchor('  File "/app/worker.py", line 88, in process'))

    def test_blank_line_is_not_anchor(self):
        self.assertFalse(triage.is_anchor(""))


class TestEntryGrouping(unittest.TestCase):
    def test_stacktrace_collapses_into_one_entry(self):
        text = load_fixture("stacktrace.log")
        entries = triage.group_into_entries(text.splitlines())
        # 4 anchor lines in the fixture -> 4 logical entries, not 15 raw lines
        self.assertEqual(len(entries), 4)
        # the traceback entry should contain all its frames
        traceback_entry = entries[1]
        joined = "\n".join(traceback_entry)
        self.assertIn("ConnectionError", joined)
        self.assertIn("client.py", joined)


class TestLevelAndTimestampExtraction(unittest.TestCase):
    def test_extract_level_from_iso_line(self):
        self.assertEqual(triage.extract_level("2026-06-01T12:00:00Z ERROR boom"), "ERROR")

    def test_extract_level_canonicalizes_warn(self):
        self.assertEqual(triage.extract_level("WARN: disk almost full"), "WARNING")

    def test_extract_level_unknown_when_absent(self):
        self.assertEqual(triage.extract_level("just a plain line"), "UNKNOWN")

    def test_extract_timestamp_iso(self):
        ts = triage.extract_timestamp("2026-06-01T12:00:00Z ERROR boom")
        self.assertTrue(ts.startswith("2026-06-01T12:00:00"))


class TestTemplating(unittest.TestCase):
    def test_similar_messages_produce_same_template(self):
        t1 = triage.make_template("connection timeout to redis:6379")
        t2 = triage.make_template("connection timeout to redis:6380")
        self.assertEqual(t1, t2)

    def test_uuid_is_masked(self):
        t = triage.make_template("failed for request 550e8400-e29b-41d4-a716-446655440000")
        self.assertIn("<UUID>", t)
        self.assertNotIn("550e8400", t)


class TestRedaction(unittest.TestCase):
    def setUp(self):
        self.text = load_fixture("secrets.log")

    def test_aws_key_redacted(self):
        out = triage.redact(self.text)
        self.assertNotIn("AKIAABCDEFGHIJKLMNOP", out)
        self.assertIn("[REDACTED_AWS_ACCESS_KEY]", out)

    def test_jwt_redacted(self):
        out = triage.redact(self.text)
        self.assertNotIn("eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9", out)
        self.assertIn("[REDACTED_JWT]", out)

    def test_api_key_kv_redacted(self):
        out = triage.redact(self.text)
        self.assertNotIn("sk_live_abcdef1234567890", out)

    def test_private_key_block_redacted(self):
        out = triage.redact(self.text)
        self.assertNotIn("MIIEpAIBAAKCAQEA1234567890abcdefghijklmnopqrstuvwxyz", out)
        self.assertIn("[REDACTED_PRIVATE_KEY_BLOCK]", out)

    def test_user_id_not_over_redacted(self):
        # regular ids/values not matching secret patterns should survive
        out = triage.redact(self.text)
        self.assertIn("user_id=445", out)


class TestTruncation(unittest.TestCase):
    def test_no_truncation_under_cap(self):
        lines = ["a"] * 10
        out, info = triage.truncate_lines(lines, max_lines=100)
        self.assertFalse(info["truncated"])
        self.assertEqual(len(out), 10)

    def test_truncation_keeps_tail(self):
        lines = [str(i) for i in range(100)]
        out, info = triage.truncate_lines(lines, max_lines=10)
        self.assertTrue(info["truncated"])
        self.assertEqual(out, lines[-10:])
        self.assertEqual(info["total_lines"], 100)
        self.assertEqual(info["analyzed_lines"], 10)


class TestFullPipeline(unittest.TestCase):
    def test_json_lines_clusters_redis_errors_together(self):
        text = load_fixture("json_lines.log")
        result = triage.run(text, max_lines=50000, surface_level="WARNING",
                             do_redact=True, max_clusters=40)
        redis_clusters = [c for c in result["clusters"] if "timeout" in c["template"]]
        self.assertEqual(len(redis_clusters), 1)
        self.assertEqual(redis_clusters[0]["count"], 4)  # 4x "connection timeout to redis:<PORT>"

    def test_info_omitted_by_default_surface_level(self):
        text = load_fixture("json_lines.log")
        result = triage.run(text, max_lines=50000, surface_level="WARNING",
                             do_redact=True, max_clusters=40)
        for c in result["clusters"]:
            self.assertNotEqual(c["dominant_level"], "INFO")
        self.assertGreater(result["entries_omitted_below_threshold"], 0)

    def test_secrets_redacted_in_cluster_samples(self):
        text = load_fixture("secrets.log")
        result = triage.run(text, max_lines=50000, surface_level="WARNING",
                             do_redact=True, max_clusters=40)
        combined_samples = " ".join(c["sample"] for c in result["clusters"])
        self.assertNotIn("AKIAABCDEFGHIJKLMNOP", combined_samples)

    def test_secrets_redacted_in_cluster_template_too(self):
        # regression: template field must not leak secrets even though it's
        # derived separately from `sample` (both must respect do_redact)
        text = load_fixture("secrets.log")
        result = triage.run(text, max_lines=50000, surface_level="WARNING",
                             do_redact=True, max_clusters=40)
        combined_templates = " ".join(c["template"] for c in result["clusters"])
        self.assertNotIn("AKIAABCDEFGHIJKLMNOP", combined_templates)
        self.assertNotIn("eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9", combined_templates)

    def test_no_redact_flag_preserves_raw(self):
        text = load_fixture("secrets.log")
        result = triage.run(text, max_lines=50000, surface_level="WARNING",
                             do_redact=False, max_clusters=40)
        combined_samples = " ".join(c["sample"] for c in result["clusters"])
        self.assertIn("AKIAABCDEFGHIJKLMNOP", combined_samples)

    def test_mixed_format_all_parsed(self):
        text = load_fixture("mixed.log")
        result = triage.run(text, max_lines=50000, surface_level="WARNING",
                             do_redact=True, max_clusters=40)
        self.assertGreaterEqual(result["total_entries_parsed"], 4)

    def test_clusters_sorted_by_severity_desc(self):
        text = load_fixture("json_lines.log")
        result = triage.run(text, max_lines=50000, surface_level="WARNING",
                             do_redact=True, max_clusters=40)
        scores = [c["severity_score"] for c in result["clusters"]]
        self.assertEqual(scores, sorted(scores, reverse=True))

    def test_truncation_reported_when_over_cap(self):
        text = load_fixture("json_lines.log")
        result = triage.run(text, max_lines=3, surface_level="WARNING",
                             do_redact=True, max_clusters=40)
        self.assertTrue(result["truncation"]["truncated"])


if __name__ == "__main__":
    unittest.main()

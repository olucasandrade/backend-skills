"""
Unit tests for the deterministic layer of rfc-review (doc_prepass.py).

Run with: python3 -m unittest discover -s tests -v
(from the scripts/ directory, stdlib unittest only — no deps)
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import doc_prepass  # noqa: E402

FIXTURES = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "fixtures")


def load_fixture(name):
    with open(os.path.join(FIXTURES, name)) as f:
        return f.read()


class TestSectionExtraction(unittest.TestCase):
    def test_extracts_headings_in_order(self):
        text = load_fixture("well_structured_rfc.md")
        sections = doc_prepass.extract_sections(text)
        titles = [s["title"] for s in sections]
        self.assertEqual(titles[0], "RFC: Add Rate Limiting to the Public API")
        self.assertIn("Summary", titles)
        self.assertIn("Design", titles)

    def test_content_between_headings_captured(self):
        text = load_fixture("well_structured_rfc.md")
        sections = doc_prepass.extract_sections(text)
        motivation = next(s for s in sections if s["title"] == "Motivation")
        self.assertIn("rate limiting", motivation["content"])


class TestTemplateDetection(unittest.TestCase):
    def test_well_structured_rfc_detected_as_rfc(self):
        text = load_fixture("well_structured_rfc.md")
        sections = doc_prepass.extract_sections(text)
        info = doc_prepass.detect_template(sections)
        self.assertEqual(info["template"], "rfc")
        self.assertIn("summary", info["matched_sections"])
        self.assertIn("goals", info["matched_sections"])

    def test_adr_detected_as_adr(self):
        text = load_fixture("adr_style.md")
        sections = doc_prepass.extract_sections(text)
        info = doc_prepass.detect_template(sections)
        self.assertEqual(info["template"], "adr")

    def test_readme_detected_as_no_template(self):
        text = load_fixture("not_an_rfc_readme.md")
        sections = doc_prepass.extract_sections(text)
        info = doc_prepass.detect_template(sections)
        self.assertIsNone(info["template"])

    def test_stub_rfc_detected_as_no_template_but_not_crash(self):
        text = load_fixture("stub_rfc.md")
        sections = doc_prepass.extract_sections(text)
        info = doc_prepass.detect_template(sections)
        # a single H1 heading isn't enough matches for any known template
        self.assertIsNone(info["template"])

    def test_missing_sections_reported_for_rfc(self):
        # a doc with only 3 of the RFC sections should report the rest missing
        text = "# Title\n\n## Summary\nx\n\n## Motivation\ny\n\n## Goals\nz\n"
        sections = doc_prepass.extract_sections(text)
        info = doc_prepass.detect_template(sections)
        self.assertEqual(info["template"], "rfc")
        self.assertIn("risks", info["missing_sections"])


class TestDocStats(unittest.TestCase):
    def test_word_count_positive(self):
        text = load_fixture("well_structured_rfc.md")
        stats = doc_prepass.doc_stats(text, base_dir=FIXTURES)
        self.assertGreater(stats["word_count"], 20)

    def test_image_refs_captured(self):
        text = load_fixture("well_structured_rfc.md")
        stats = doc_prepass.doc_stats(text, base_dir=FIXTURES)
        self.assertEqual(len(stats["image_refs"]), 2)
        self.assertIn("./diagrams/current.png", stats["image_refs"])

    def test_broken_local_link_detected(self):
        text = "See [the spec](./nonexistent-spec.md) for details."
        stats = doc_prepass.doc_stats(text, base_dir=FIXTURES)
        self.assertIn("./nonexistent-spec.md", stats["broken_local_links"])

    def test_external_links_not_flagged_as_broken(self):
        text = "See [docs](https://example.com/docs) for details."
        stats = doc_prepass.doc_stats(text, base_dir=FIXTURES)
        self.assertEqual(stats["broken_local_links"], [])

    def test_existing_local_link_not_flagged(self):
        text = "See [the RFC](./well_structured_rfc.md) for details."
        stats = doc_prepass.doc_stats(text, base_dir=FIXTURES)
        self.assertEqual(stats["broken_local_links"], [])


class TestVagueLanguageFlagging(unittest.TestCase):
    def test_flags_should_be_fast(self):
        candidates = doc_prepass.flag_vague_language("The system should be fast under load.")
        self.assertEqual(len(candidates), 1)
        self.assertIn("should be fast", candidates[0]["term"].lower())

    def test_flags_tbd(self):
        candidates = doc_prepass.flag_vague_language("The failover strategy is TBD.")
        self.assertTrue(any("TBD" in c["term"] for c in candidates))

    def test_does_not_flag_precise_language(self):
        candidates = doc_prepass.flag_vague_language(
            "The endpoint must respond within 200ms at p99 under 500 req/s."
        )
        self.assertEqual(candidates, [])

    def test_well_structured_fixture_flags_known_hedges(self):
        text = load_fixture("well_structured_rfc.md")
        candidates = doc_prepass.flag_vague_language(text)
        terms = [c["term"].lower() for c in candidates]
        self.assertTrue(any("tbd" in t for t in terms))


class TestFullPipeline(unittest.TestCase):
    def test_run_returns_all_top_level_keys(self):
        text = load_fixture("well_structured_rfc.md")
        result = doc_prepass.run(text, base_dir=FIXTURES)
        for key in ("template", "sections", "stats", "vague_language_candidates"):
            self.assertIn(key, result)

    def test_stub_rfc_low_word_count_and_no_template(self):
        text = load_fixture("stub_rfc.md")
        result = doc_prepass.run(text, base_dir=FIXTURES)
        self.assertIsNone(result["template"]["template"])
        self.assertLess(result["stats"]["word_count"], 30)


if __name__ == "__main__":
    unittest.main()

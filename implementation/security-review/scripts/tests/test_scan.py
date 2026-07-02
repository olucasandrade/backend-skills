import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import scan  # noqa: E402


class TempRepoTestCase(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def write(self, rel_path, content=""):
        abs_path = os.path.join(self.root, rel_path)
        os.makedirs(os.path.dirname(abs_path), exist_ok=True)
        with open(abs_path, "w", encoding="utf-8") as f:
            f.write(content)
        return abs_path


class TestFileEnumeration(TempRepoTestCase):
    def test_regular_source_file_included(self):
        self.write("src/app.py", "print('hi')\n")
        files, skipped = scan.enumerate_files(self.root, [])
        self.assertIn("src/app.py", files)

    def test_default_ignore_dirs_excluded(self):
        self.write("node_modules/pkg/index.js", "module.exports = {};\n")
        self.write("src/app.py", "print('hi')\n")
        files, skipped = scan.enumerate_files(self.root, [])
        self.assertNotIn("node_modules/pkg/index.js", files)
        self.assertIn("src/app.py", files)

    def test_lockfile_excluded(self):
        self.write("package-lock.json", "{}\n")
        files, skipped = scan.enumerate_files(self.root, [])
        self.assertNotIn("package-lock.json", files)
        self.assertIn("package-lock.json", skipped["lockfile"])

    def test_binary_extension_excluded(self):
        self.write("assets/logo.png", "not really png bytes")
        files, skipped = scan.enumerate_files(self.root, [])
        self.assertNotIn("assets/logo.png", files)
        self.assertIn("assets/logo.png", skipped["binary"])

    def test_binary_content_sniffed_even_with_text_extension(self):
        abs_path = os.path.join(self.root, "weird.txt")
        with open(abs_path, "wb") as f:
            f.write(b"hello\x00world")
        files, skipped = scan.enumerate_files(self.root, [])
        self.assertNotIn("weird.txt", files)
        self.assertIn("weird.txt", skipped["binary"])

    def test_gitignore_pattern_respected(self):
        self.write(".gitignore", "*.local.py\n")
        self.write("secrets.local.py", "TOKEN = 'x'\n")
        self.write("src/app.py", "print('hi')\n")
        files, skipped = scan.enumerate_files(self.root, [])
        self.assertNotIn("secrets.local.py", files)
        self.assertIn("secrets.local.py", skipped["gitignored"])
        self.assertIn("src/app.py", files)

    def test_extra_ignore_pattern_respected(self):
        self.write("generated/schema.py", "X = 1\n")
        files, skipped = scan.enumerate_files(self.root, ["generated"])
        self.assertNotIn("generated/schema.py", files)


class TestSecretsScanning(TempRepoTestCase):
    def test_aws_access_key_detected(self):
        self.write("config.py", "AWS_KEY = 'AKIAABCDEFGHIJKLMNOP'\n")
        findings = scan.scan_file_for_secrets(self.root, "config.py")
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["pattern"], "aws_access_key_id")
        self.assertEqual(findings[0]["confidence"], "high")

    def test_private_key_header_detected(self):
        self.write("key.pem", "-----BEGIN RSA PRIVATE KEY-----\nMIIB...\n")
        findings = scan.scan_file_for_secrets(self.root, "key.pem")
        self.assertTrue(any(f["pattern"] == "private_key_header" for f in findings))

    def test_github_token_detected(self):
        self.write(".env", "GH_TOKEN=ghp_" + "a" * 36 + "\n")
        findings = scan.scan_file_for_secrets(self.root, ".env")
        self.assertTrue(any(f["pattern"] == "github_token" for f in findings))

    def test_secret_is_redacted_in_snippet(self):
        self.write("config.py", "AWS_KEY = 'AKIAABCDEFGHIJKLMNOP'\n")
        findings = scan.scan_file_for_secrets(self.root, "config.py")
        self.assertNotIn("AKIAABCDEFGHIJKLMNOP", findings[0]["snippet"])
        self.assertIn("[REDACTED]", findings[0]["snippet"])

    def test_no_false_positive_on_uuid(self):
        self.write("model.py", "id = 'f47ac10b-58cc-4372-a567-0e02b2c3d479'\n")
        findings = scan.scan_file_for_secrets(self.root, "model.py")
        self.assertEqual(findings, [])

    def test_no_false_positive_on_plain_comment(self):
        self.write("model.py", "# remember to set your secret key in the .env file\n")
        findings = scan.scan_file_for_secrets(self.root, "model.py")
        self.assertEqual(findings, [])

    def test_line_number_reported_correctly(self):
        self.write("config.py", "x = 1\ny = 2\nAWS_KEY = 'AKIAABCDEFGHIJKLMNOP'\n")
        findings = scan.scan_file_for_secrets(self.root, "config.py")
        self.assertEqual(findings[0]["line"], 3)


class TestEndToEndOutputShape(TempRepoTestCase):
    def test_secrets_findings_use_relative_paths_from_full_scan(self):
        self.write("src/config.py", "AWS_KEY = 'AKIAABCDEFGHIJKLMNOP'\n")
        files, skipped = scan.enumerate_files(self.root, [])
        all_findings = []
        for f in files:
            all_findings.extend(scan.scan_file_for_secrets(self.root, f))
        self.assertEqual(len(all_findings), 1)
        self.assertEqual(all_findings[0]["file"], "src/config.py")


if __name__ == "__main__":
    unittest.main()

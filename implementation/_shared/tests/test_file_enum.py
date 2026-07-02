import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import file_enum  # noqa: E402


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


class TestEnumerateFiles(TempRepoTestCase):
    def test_regular_source_file_included(self):
        self.write("src/app.py", "print('hi')\n")
        files, skipped = file_enum.enumerate_files(self.root, [])
        self.assertIn("src/app.py", files)

    def test_default_ignore_dirs_excluded(self):
        self.write("node_modules/pkg/index.js", "module.exports = {};\n")
        self.write("src/app.py", "print('hi')\n")
        files, skipped = file_enum.enumerate_files(self.root, [])
        self.assertNotIn("node_modules/pkg/index.js", files)
        self.assertIn("src/app.py", files)

    def test_lockfile_excluded(self):
        self.write("package-lock.json", "{}\n")
        files, skipped = file_enum.enumerate_files(self.root, [])
        self.assertNotIn("package-lock.json", files)
        self.assertIn("package-lock.json", skipped["lockfile"])

    def test_binary_extension_excluded(self):
        self.write("assets/logo.png", "not really png bytes")
        files, skipped = file_enum.enumerate_files(self.root, [])
        self.assertNotIn("assets/logo.png", files)
        self.assertIn("assets/logo.png", skipped["binary"])

    def test_binary_content_sniffed_even_with_text_extension(self):
        abs_path = os.path.join(self.root, "weird.txt")
        with open(abs_path, "wb") as f:
            f.write(b"hello\x00world")
        files, skipped = file_enum.enumerate_files(self.root, [])
        self.assertNotIn("weird.txt", files)
        self.assertIn("weird.txt", skipped["binary"])

    def test_gitignore_pattern_respected(self):
        self.write(".gitignore", "*.local.py\n")
        self.write("secrets.local.py", "TOKEN = 'x'\n")
        self.write("src/app.py", "print('hi')\n")
        files, skipped = file_enum.enumerate_files(self.root, [])
        self.assertNotIn("secrets.local.py", files)
        self.assertIn("secrets.local.py", skipped["gitignored"])
        self.assertIn("src/app.py", files)

    def test_extra_ignore_pattern_respected(self):
        self.write("generated/schema.py", "X = 1\n")
        files, skipped = file_enum.enumerate_files(self.root, ["generated"])
        self.assertNotIn("generated/schema.py", files)

    def test_results_sorted(self):
        self.write("b.py", "")
        self.write("a.py", "")
        files, skipped = file_enum.enumerate_files(self.root, [])
        self.assertEqual(files, sorted(files))


if __name__ == "__main__":
    unittest.main()

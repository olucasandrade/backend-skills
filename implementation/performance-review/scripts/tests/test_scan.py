import json
import os
import subprocess
import sys
import tempfile
import unittest

SCAN_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scan.py")


class TestScanCli(unittest.TestCase):
    def test_output_shape(self):
        with tempfile.TemporaryDirectory() as root:
            with open(os.path.join(root, "app.py"), "w") as f:
                f.write("print('hi')\n")
            with open(os.path.join(root, "package-lock.json"), "w") as f:
                f.write("{}\n")

            result = subprocess.run(
                [sys.executable, SCAN_PATH, "--root", root],
                capture_output=True, text=True, check=True,
            )
            data = json.loads(result.stdout)

            self.assertIn("app.py", data["files"])
            self.assertIn("package-lock.json", data["skipped"]["lockfile"])
            self.assertNotIn("secrets_findings", data)


if __name__ == "__main__":
    unittest.main()

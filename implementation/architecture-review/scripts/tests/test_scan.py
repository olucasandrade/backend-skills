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


class TestPythonImportGraph(TempRepoTestCase):
    def test_simple_import_edge(self):
        self.write("a.py", "import b\n")
        self.write("b.py", "x = 1\n")
        files, _ = scan.enumerate_files(self.root, [])
        graph = scan.build_dependency_graph(self.root, files)
        self.assertIn("b.py", graph["a.py"])

    def test_relative_from_import(self):
        self.write("pkg/a.py", "from . import b\n")
        self.write("pkg/b.py", "x = 1\n")
        files, _ = scan.enumerate_files(self.root, [])
        graph = scan.build_dependency_graph(self.root, files)
        self.assertIn("pkg/b.py", graph["pkg/a.py"])

    def test_dotted_module_import(self):
        self.write("pkg/a.py", "from pkg.sub import c\n")
        self.write("pkg/sub.py", "c = 1\n")
        files, _ = scan.enumerate_files(self.root, [])
        graph = scan.build_dependency_graph(self.root, files)
        self.assertIn("pkg/sub.py", graph["pkg/a.py"])

    def test_external_package_import_not_in_graph(self):
        self.write("a.py", "import requests\n")
        files, _ = scan.enumerate_files(self.root, [])
        graph = scan.build_dependency_graph(self.root, files)
        self.assertEqual(graph["a.py"], [])

    def test_self_import_excluded(self):
        self.write("pkg/__init__.py", "")
        self.write("pkg/a.py", "from pkg import a\n")
        files, _ = scan.enumerate_files(self.root, [])
        graph = scan.build_dependency_graph(self.root, files)
        self.assertNotIn("pkg/a.py", graph["pkg/a.py"])


class TestJsImportGraph(TempRepoTestCase):
    def test_relative_require(self):
        self.write("a.js", "const b = require('./b');\n")
        self.write("b.js", "module.exports = {};\n")
        files, _ = scan.enumerate_files(self.root, [])
        graph = scan.build_dependency_graph(self.root, files)
        self.assertIn("b.js", graph["a.js"])

    def test_relative_es_import(self):
        self.write("a.ts", "import { x } from './lib/b';\n")
        self.write("lib/b.ts", "export const x = 1;\n")
        files, _ = scan.enumerate_files(self.root, [])
        graph = scan.build_dependency_graph(self.root, files)
        self.assertIn("lib/b.ts", graph["a.ts"])

    def test_bare_package_import_not_in_graph(self):
        self.write("a.js", "import React from 'react';\n")
        files, _ = scan.enumerate_files(self.root, [])
        graph = scan.build_dependency_graph(self.root, files)
        self.assertEqual(graph["a.js"], [])


class TestCycleDetection(TempRepoTestCase):
    def test_no_cycle_in_dag(self):
        graph = {"a.py": ["b.py"], "b.py": ["c.py"], "c.py": []}
        self.assertEqual(scan.find_cycles(graph), [])

    def test_two_node_cycle_detected(self):
        graph = {"a.py": ["b.py"], "b.py": ["a.py"]}
        cycles = scan.find_cycles(graph)
        self.assertEqual(len(cycles), 1)
        self.assertEqual(set(cycles[0]), {"a.py", "b.py"})

    def test_three_node_cycle_detected(self):
        graph = {"a.py": ["b.py"], "b.py": ["c.py"], "c.py": ["a.py"]}
        cycles = scan.find_cycles(graph)
        self.assertEqual(len(cycles), 1)
        self.assertEqual(set(cycles[0]), {"a.py", "b.py", "c.py"})

    def test_end_to_end_cyclic_fixture(self):
        self.write("a.py", "from b import x\n")
        self.write("b.py", "from a import y\n")
        files, _ = scan.enumerate_files(self.root, [])
        graph = scan.build_dependency_graph(self.root, files)
        cycles = scan.find_cycles(graph)
        self.assertEqual(len(cycles), 1)
        self.assertEqual(set(cycles[0]), {"a.py", "b.py"})


FIXTURES_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "fixtures")


class TestGoImportGraph(TempRepoTestCase):
    def test_go_module_path_parsed(self):
        self.write("go.mod", "module example.com/app\n\ngo 1.21\n")
        module_path, gomod_dir = scan.find_go_module(self.root)
        self.assertEqual(module_path, "example.com/app")
        self.assertEqual(gomod_dir, self.root)

    def test_go_import_block_and_single(self):
        block_content = (
            "package a\n\n"
            'import (\n\t"fmt"\n\talias "example.com/app/b"\n)\n'
        )
        self.assertIn("example.com/app/b", scan.extract_go_imports(block_content))
        self.assertIn("fmt", scan.extract_go_imports(block_content))

        single_content = 'package a\n\nimport "example.com/app/b"\n'
        self.assertIn("example.com/app/b", scan.extract_go_imports(single_content))

    def test_go_cycle_detected(self):
        root = os.path.join(FIXTURES_DIR, "go_cycle_sample")
        files, _ = scan.enumerate_files(root, [])
        graph = scan.build_dependency_graph(root, files)
        cycles = scan.find_cycles(graph)
        self.assertEqual(len(cycles), 1)
        self.assertEqual(set(cycles[0]), {"a", "b"})

    def test_go_external_imports_excluded(self):
        self.write("go.mod", "module example.com/app\n\ngo 1.21\n")
        self.write("a/a.go", 'package a\n\nimport (\n\t"fmt"\n\t"github.com/other/dep"\n)\n')
        files, _ = scan.enumerate_files(self.root, [])
        graph = scan.build_dependency_graph(self.root, files)
        self.assertEqual(graph["a"], [])

    def test_no_gomod_skips_go(self):
        self.write("a/a.go", 'package a\n\nimport "example.com/app/b"\n')
        files, _ = scan.enumerate_files(self.root, [])
        graph = scan.build_dependency_graph(self.root, files)
        self.assertNotIn("a", graph)


if __name__ == "__main__":
    unittest.main()

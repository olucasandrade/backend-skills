#!/usr/bin/env python3
"""
Deterministic pre-pass for the architecture-review skill (stdlib-only, no
dependencies).

This script does NOT judge layering violations, coupling/cohesion, or
architecture-pattern deviation — those need actual understanding of what a
module means, which is LLM judgment (see SKILL.md). It only does what's
genuinely a solved, deterministic graph problem:

1. File enumeration — reuses implementation/_shared/file_enum.py, the same
   module security-review and performance-review use.
2. Import-graph extraction — regex-based import/require parsing for
   Python and JS/TS (v1 scope; other languages are out of scope, see
   SKILL.md), resolving imports to in-repo files only (external package
   imports are not part of this graph).
3. Cycle detection — real DFS-based cycle detection on the resulting
   dependency graph. A detected cycle is always high-confidence: either
   the graph has a cycle or it doesn't, no judgment involved.

Output: a single JSON object on stdout.

{
  "root": "<resolved root path>",
  "files": [...],
  "skipped": {...},
  "dependency_graph": {"<file>": ["<file>", ...], ...},
  "cycles": [["a.py", "b.py", "a.py"], ...]   # each cycle as a path,
                                                # first and last entry equal
}

Usage:
    python3 scan.py --root PATH [--extra-ignore PATTERN ...]
"""
import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "_shared"))
from file_enum import enumerate_files  # noqa: E402

PY_FROM_IMPORT_RE = re.compile(r"^\s*from\s+([.\w]+)\s+import\s+([^\n]+)", re.MULTILINE)
PY_PLAIN_IMPORT_RE = re.compile(r"^\s*import\s+([.\w]+)", re.MULTILINE)
JS_IMPORT_RE = re.compile(r"""(?:require\(|from\s+)['"](\.{1,2}/[^'"]+)['"]""")


def resolve_python_import(current_file, module, files_set):
    """Resolve a dotted (possibly relative, leading-dot) Python module path
    to an in-repo file, or None if it doesn't resolve to a tracked file."""
    if module.startswith("."):
        leading_dots = len(module) - len(module.lstrip("."))
        remainder = module[leading_dots:]
        base_dir = os.path.dirname(current_file)
        for _ in range(leading_dots - 1):
            base_dir = os.path.dirname(base_dir)
        parts = remainder.split(".") if remainder else []
        rel = os.path.join(base_dir, *parts) if parts else base_dir
    else:
        rel = module.replace(".", "/")

    candidates = [rel + ".py", os.path.join(rel, "__init__.py")]
    for c in candidates:
        c = c.replace(os.sep, "/").lstrip("/")
        if c in files_set:
            return c
    return None


def resolve_js_import(current_file, rel_import, files_set):
    base_dir = os.path.dirname(current_file)
    target = os.path.normpath(os.path.join(base_dir, rel_import)).replace(os.sep, "/")
    candidates = [
        target, target + ".js", target + ".jsx", target + ".ts", target + ".tsx",
        target + "/index.js", target + "/index.ts",
    ]
    for c in candidates:
        if c in files_set:
            return c
    return None


def build_dependency_graph(root, files):
    files_set = set(files)
    graph = {f: [] for f in files}

    for rel_path in files:
        ext = os.path.splitext(rel_path)[1]
        abs_path = os.path.join(root, rel_path)
        try:
            with open(abs_path, "r", encoding="utf-8") as f:
                content = f.read()
        except (OSError, UnicodeDecodeError):
            continue

        targets = set()
        if ext == ".py":
            for m in PY_PLAIN_IMPORT_RE.finditer(content):
                resolved = resolve_python_import(rel_path, m.group(1), files_set)
                if resolved and resolved != rel_path:
                    targets.add(resolved)
            for m in PY_FROM_IMPORT_RE.finditer(content):
                module = m.group(1)
                resolved = resolve_python_import(rel_path, module, files_set)
                if resolved and resolved != rel_path:
                    targets.add(resolved)
                # "from X import name" may itself refer to a submodule
                # (from . import b -> pkg/b.py), not just an attribute of X.
                names = [n.split(" as ")[0].strip().strip("()")
                         for n in m.group(2).split(",")]
                for name in names:
                    if not name or not re.match(r"^\w+$", name):
                        continue
                    submodule = f"{module}.{name}" if not module.endswith(".") else f"{module}{name}"
                    resolved_sub = resolve_python_import(rel_path, submodule, files_set)
                    if resolved_sub and resolved_sub != rel_path:
                        targets.add(resolved_sub)
        elif ext in (".js", ".jsx", ".ts", ".tsx"):
            for m in JS_IMPORT_RE.finditer(content):
                resolved = resolve_js_import(rel_path, m.group(1), files_set)
                if resolved and resolved != rel_path:
                    targets.add(resolved)

        graph[rel_path] = sorted(targets)

    return graph


def find_cycles(graph):
    """DFS-based cycle detection. Returns a list of distinct cycles (as
    node-path lists, first == last), one representative cycle per back-edge
    encountered from an unvisited traversal root."""
    WHITE, GRAY, BLACK = 0, 1, 2
    color = {node: WHITE for node in graph}
    stack = []
    cycles = []
    seen_cycle_sets = set()

    def dfs(node):
        color[node] = GRAY
        stack.append(node)
        for neighbor in graph.get(node, []):
            if color.get(neighbor, WHITE) == WHITE:
                dfs(neighbor)
            elif color.get(neighbor) == GRAY:
                idx = stack.index(neighbor)
                cycle = stack[idx:] + [neighbor]
                key = frozenset(cycle)
                if key not in seen_cycle_sets:
                    seen_cycle_sets.add(key)
                    cycles.append(cycle)
        stack.pop()
        color[node] = BLACK

    for node in sorted(graph):
        if color[node] == WHITE:
            dfs(node)

    return cycles


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True)
    parser.add_argument("--extra-ignore", action="append", default=[])
    args = parser.parse_args()

    root = os.path.abspath(args.root)
    files, skipped = enumerate_files(root, args.extra_ignore)
    graph = build_dependency_graph(root, files)
    cycles = find_cycles(graph)

    print(json.dumps({
        "root": root,
        "files": files,
        "skipped": skipped,
        "dependency_graph": graph,
        "cycles": cycles,
    }, indent=2))


if __name__ == "__main__":
    sys.exit(main())

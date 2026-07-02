#!/usr/bin/env python3
"""
Deterministic pre-pass for the performance-review skill (stdlib-only, no
dependencies).

Unlike security-review's scan.py, this has no content-analysis pass of its
own — grep-heuristics for nested loops or ORM call sites were considered
and deliberately rejected (see SKILL.md): they're too noisy and too
framework-dependent to add real signal over an LLM just reading the code.
This script only does file enumeration, reusing the shared logic in
implementation/_shared/file_enum.py (the same enumeration security-review
uses — the first real second-consumer extraction in implementation/).

Output: a single JSON object on stdout.

{
  "root": "<resolved root path>",
  "files": ["<path relative to root>", ...],   # reviewable source files
  "skipped": {
    "vendor": [...],
    "binary": [...],
    "lockfile": [...],
    "gitignored": [...]
  }
}

Usage:
    python3 scan.py --root PATH [--extra-ignore PATTERN ...]
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "_shared"))
from file_enum import enumerate_files  # noqa: E402


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True)
    parser.add_argument("--extra-ignore", action="append", default=[])
    args = parser.parse_args()

    root = os.path.abspath(args.root)
    files, skipped = enumerate_files(root, args.extra_ignore)

    print(json.dumps({
        "root": root,
        "files": files,
        "skipped": skipped,
    }, indent=2))


if __name__ == "__main__":
    sys.exit(main())

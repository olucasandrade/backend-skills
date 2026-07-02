#!/usr/bin/env python3
"""
Deterministic pre-pass for the security-review skill (stdlib-only, no
dependencies).

This script does NOT judge whether code is vulnerable — that's the LLM's
job, reading actual source. It only does the two things that are genuinely
mechanical and language-agnostic:

1. File enumeration — walk a codebase root, respect .gitignore (a simple
   fnmatch-based subset, not a full gitignore-spec implementation), and
   filter out files that are never worth an LLM's attention (binaries,
   vendored/generated code, lockfiles, VCS metadata).
2. Secrets pattern-matching — regex scan for a small set of HIGH-CONFIDENCE
   secret shapes only (real key formats with recognizable prefixes/headers).
   Deliberately excludes generic "secret = <string>"-style heuristics, which
   are too noisy for a deterministic pass — flagging those from context is
   left to the LLM reading the file.

Output: a single JSON object on stdout.

{
  "root": "<resolved root path>",
  "files": ["<path relative to root>", ...],   # reviewable source files
  "skipped": {
    "vendor": [...],      # matched a vendor/build/dependency directory
    "binary": [...],      # binary extension or non-utf8 content
    "lockfile": [...],    # known lockfile name
    "gitignored": [...]   # matched a .gitignore pattern
  },
  "secrets_findings": [
    {
      "file": "<path relative to root>",
      "line": <int>,
      "pattern": "<pattern name>",
      "confidence": "high",
      "snippet": "<redacted line, secret value masked>"
    },
    ...
  ]
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

# Only real, recognizable key/token *shapes* — no generic "secret ="
# heuristics, per the "high-confidence patterns only" convention.
SECRET_PATTERNS = [
    ("aws_access_key_id", re.compile(r"AKIA[0-9A-Z]{16}")),
    ("aws_secret_access_key", re.compile(
        r"(?i)aws_secret_access_key\s*[:=]\s*['\"]?([A-Za-z0-9/+=]{40})['\"]?"
    )),
    ("private_key_header", re.compile(
        r"-----BEGIN (RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----"
    )),
    ("github_token", re.compile(r"gh[pousr]_[A-Za-z0-9]{36,}")),
    ("slack_token", re.compile(r"xox[baprs]-[A-Za-z0-9-]{10,}")),
    ("stripe_key", re.compile(r"sk_live_[A-Za-z0-9]{24,}")),
    ("generic_jwt", re.compile(r"eyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}")),
]

TEXT_READ_ERRORS = (UnicodeDecodeError,)


def redact_line(line, match_span):
    start, end = match_span
    return line[:start] + "[REDACTED]" + line[end:]


def scan_file_for_secrets(root, rel_path):
    findings = []
    abs_path = os.path.join(root, rel_path)
    try:
        with open(abs_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except TEXT_READ_ERRORS:
        return findings
    except OSError:
        return findings

    for lineno, line in enumerate(lines, start=1):
        for name, pattern in SECRET_PATTERNS:
            m = pattern.search(line)
            if m:
                findings.append({
                    "file": rel_path,
                    "line": lineno,
                    "pattern": name,
                    "confidence": "high",
                    "snippet": redact_line(line.rstrip("\n"), m.span()),
                })
    return findings


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True)
    parser.add_argument("--extra-ignore", action="append", default=[])
    args = parser.parse_args()

    root = os.path.abspath(args.root)
    files, skipped = enumerate_files(root, args.extra_ignore)

    secrets_findings = []
    for rel_path in files:
        secrets_findings.extend(scan_file_for_secrets(root, rel_path))

    print(json.dumps({
        "root": root,
        "files": sorted(files),
        "skipped": {k: sorted(v) for k, v in skipped.items()},
        "secrets_findings": secrets_findings,
    }, indent=2))


if __name__ == "__main__":
    sys.exit(main())

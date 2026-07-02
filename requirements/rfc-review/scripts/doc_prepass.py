#!/usr/bin/env python3
"""
Deterministic structural pre-pass for rfc-review (stdlib only).

Does NOT judge document quality — that's the calling skill's (LLM) job.
This script only extracts cheap, reproducible structural facts:
  - which known template (if any) the doc resembles, and which of that
    template's expected sections are present/missing
  - section map (heading -> content)
  - basic stats (word count, heading count, image refs, link targets,
    broken *local* relative links)
  - candidate vague-language spots (hedge words/phrases) — a CANDIDATE
    list only, not an authoritative ambiguity verdict; the LLM decides
    which candidates are actually problems in context.

Usage:
    doc_prepass.py --file PATH [--base-dir DIR]
    (reads stdin if --file is omitted; --base-dir used to resolve local
    relative links for broken-link checking, defaults to the file's dir)

Output: a single JSON object on stdout.
"""

import argparse
import json
import os
import re
import sys

# ---------------------------------------------------------------------------
# Template detection
# ---------------------------------------------------------------------------

TEMPLATES = {
    "rfc": {
        # each inner list is a synonym group; matching any one member
        # satisfies the whole group (reported under its first/canonical name)
        "expected_sections": [
            ["summary"], ["motivation"], ["goals"], ["non-goals", "non goals"],
            ["design", "detailed design"],
            ["alternatives considered", "alternatives"],
            ["risks"], ["rollout", "rollback"],
        ],
        "min_matches": 3,
    },
    "adr": {
        "expected_sections": [["context"], ["decision"], ["consequences"], ["status"]],
        "min_matches": 3,
    },
    "prfaq": {
        "expected_sections": [["press release"], ["faq", "frequently asked questions"]],
        "min_matches": 1,
    },
}

HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$", re.MULTILINE)


def extract_sections(text: str):
    """Return an ordered list of {level, title, content} from markdown headings."""
    matches = list(HEADING_RE.finditer(text))
    sections = []
    for i, m in enumerate(matches):
        level = len(m.group(1))
        title = m.group(2).strip()
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        content = text[start:end].strip()
        sections.append({"level": level, "title": title, "content": content})
    return sections


def detect_template(sections):
    titles_lower = {s["title"].strip().lower() for s in sections}
    best_name = None
    best_matched_groups = []
    best_score = 0
    for name, spec in TEMPLATES.items():
        matched_groups = [g for g in spec["expected_sections"]
                           if any(syn in titles_lower for syn in g)]
        if len(matched_groups) >= spec["min_matches"] and len(matched_groups) > best_score:
            best_name = name
            best_matched_groups = matched_groups
            best_score = len(matched_groups)
    if best_name is None:
        return {"template": None, "matched_sections": [], "missing_sections": []}
    missing_groups = [g for g in TEMPLATES[best_name]["expected_sections"]
                       if g not in best_matched_groups]
    return {
        "template": best_name,
        "matched_sections": sorted(g[0] for g in best_matched_groups),
        "missing_sections": sorted(g[0] for g in missing_groups),
    }


# ---------------------------------------------------------------------------
# Doc stats
# ---------------------------------------------------------------------------

IMAGE_RE = re.compile(r"!\[[^\]]*\]\(([^)]+)\)")
LINK_RE = re.compile(r"(?<!!)\[[^\]]*\]\(([^)]+)\)")


def doc_stats(text: str, base_dir: str):
    word_count = len(text.split())
    heading_count = len(HEADING_RE.findall(text))
    images = IMAGE_RE.findall(text)
    links = LINK_RE.findall(text)

    broken_local_links = []
    for target in links:
        if target.startswith(("http://", "https://", "#", "mailto:")):
            continue
        clean = target.split("#")[0].strip()
        if not clean:
            continue
        candidate = os.path.join(base_dir, clean)
        if not os.path.exists(candidate):
            broken_local_links.append(target)

    return {
        "word_count": word_count,
        "heading_count": heading_count,
        "image_refs": images,
        "link_targets": links,
        "broken_local_links": broken_local_links,
    }


# ---------------------------------------------------------------------------
# Candidate vague-language flagging (NOT authoritative — LLM decides)
# ---------------------------------------------------------------------------

HEDGE_PATTERNS = [
    r"\bshould be (fast|scalable|reliable|robust|secure|performant)\b",
    r"\bas needed\b",
    r"\bTBD\b",
    r"\bTODO\b",
    r"\bmight\b",
    r"\bpossibly\b",
    r"\bin most cases\b",
    r"\ba reasonable amount\b",
    r"\bwill scale\b",
    r"\bwill be fast\b",
    r"\bsome edge cases\b",
    r"\bmostly\b",
    r"\bgood enough\b",
]
HEDGE_RE = re.compile("|".join(HEDGE_PATTERNS), re.IGNORECASE)

SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")


def flag_vague_language(text: str, max_candidates: int = 60):
    candidates = []
    for sentence in SENTENCE_SPLIT_RE.split(text):
        s = sentence.strip()
        if not s:
            continue
        m = HEDGE_RE.search(s)
        if m:
            candidates.append({"term": m.group(0), "sentence": s[:240]})
            if len(candidates) >= max_candidates:
                break
    return candidates


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def run(text: str, base_dir: str):
    sections = extract_sections(text)
    template_info = detect_template(sections)
    stats = doc_stats(text, base_dir)
    vague_candidates = flag_vague_language(text)

    return {
        "template": template_info,
        "sections": [{"level": s["level"], "title": s["title"]} for s in sections],
        "stats": stats,
        "vague_language_candidates": vague_candidates,
    }


def main():
    ap = argparse.ArgumentParser(description="Deterministic structural pre-pass for rfc-review")
    ap.add_argument("--file", help="Path to the RFC/doc file; reads stdin if omitted")
    ap.add_argument("--base-dir", help="Base dir for resolving local relative links (default: file's dir or cwd)")
    args = ap.parse_args()

    if args.file:
        with open(args.file, "r", errors="replace") as f:
            text = f.read()
        base_dir = args.base_dir or os.path.dirname(os.path.abspath(args.file))
    else:
        text = sys.stdin.read()
        base_dir = args.base_dir or os.getcwd()

    result = run(text, base_dir)
    json.dump(result, sys.stdout, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Deterministic log-triage engine (stdlib only).

Reads raw log text (stdin or --file), and produces a JSON report containing:
  - truncation info (was the input capped, how much was dropped)
  - per-entry parse results are NOT emitted (too large); only clusters are
  - clusters: template, count, level distribution, first/last seen,
    a redacted representative sample, and a composite severity score
  - omitted-volume summary for levels below the surface threshold

This script does NOT explain, label, or correlate anything — that judgment
layer belongs to the calling skill (an LLM). This script only does the
cheap, deterministic, reproducible part: parsing, grouping, scoring,
redaction, and truncation.

Usage:
    triage.py [--file PATH] [--max-lines N] [--surface-level LEVEL]
               [--no-redact] [--max-clusters N]
    (reads stdin if --file is omitted)

Output: a single JSON object on stdout.
"""

import argparse
import json
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone

# ---------------------------------------------------------------------------
# Level handling
# ---------------------------------------------------------------------------

LEVEL_RANK = {
    "TRACE": 0,
    "DEBUG": 1,
    "INFO": 2,
    "NOTICE": 2,
    "WARN": 3,
    "WARNING": 3,
    "ERROR": 4,
    "ERR": 4,
    "CRITICAL": 5,
    "CRIT": 5,
    "FATAL": 5,
    "EMERGENCY": 5,
    "PANIC": 5,
}

LEVEL_CANON = {
    "WARN": "WARNING",
    "ERR": "ERROR",
    "CRIT": "CRITICAL",
    "EMERG": "EMERGENCY",
}

LEVEL_TOKEN_RE = re.compile(
    r"\b(TRACE|DEBUG|INFO|NOTICE|WARN(?:ING)?|ERR(?:OR)?|CRIT(?:ICAL)?|FATAL|EMERGENCY|PANIC)\b",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Anchor / continuation heuristic (Q4)
# ---------------------------------------------------------------------------

# A line is an "anchor" (starts a new logical entry) if it looks like a
# timestamped log line, a JSON object, or a syslog header. Anything else
# following an anchor is treated as a continuation (stack frames, "Caused
# by:" chains, pretty-printed JSON bodies, etc.)

ISO_TS_RE = re.compile(
    r"^\s*\[?(\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?)\]?"
)
SYSLOG_TS_RE = re.compile(
    r"^\s*([A-Z][a-z]{2}\s+\d{1,2}\s+\d{2}:\d{2}:\d{2})\s+\S+\s+"
)
EPOCH_TS_RE = re.compile(r"^\s*(\d{10,13})\s")
JSON_START_RE = re.compile(r"^\s*\{")
LEVEL_START_RE = re.compile(
    r"^\s*\[?(TRACE|DEBUG|INFO|NOTICE|WARN(?:ING)?|ERR(?:OR)?|CRIT(?:ICAL)?|FATAL|EMERGENCY|PANIC)\b\]?\s*[:\-]?",
    re.IGNORECASE,
)


def is_anchor(line: str) -> bool:
    if not line.strip():
        return False
    return bool(
        ISO_TS_RE.match(line)
        or SYSLOG_TS_RE.match(line)
        or EPOCH_TS_RE.match(line)
        or JSON_START_RE.match(line)
        or LEVEL_START_RE.match(line)
    )


def group_into_entries(lines):
    """Group raw lines into logical multi-line entries."""
    entries = []
    current = []
    for line in lines:
        if is_anchor(line) or not current:
            if current:
                entries.append(current)
            current = [line]
        else:
            current.append(line)
    if current:
        entries.append(current)
    return entries


# ---------------------------------------------------------------------------
# Per-entry field extraction
# ---------------------------------------------------------------------------


def extract_level(first_line: str) -> str:
    m = LEVEL_TOKEN_RE.search(first_line)
    if not m:
        return "UNKNOWN"
    token = m.group(1).upper()
    return LEVEL_CANON.get(token, token)


def extract_timestamp(first_line: str):
    m = ISO_TS_RE.match(first_line)
    if m:
        raw = m.group(1)
        try:
            norm = raw.replace("Z", "+00:00")
            if "T" not in norm and " " in norm:
                norm = norm.replace(" ", "T", 1)
            dt = datetime.fromisoformat(norm)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.isoformat()
        except ValueError:
            return raw
    m = SYSLOG_TS_RE.match(first_line)
    if m:
        return m.group(1)  # no year in syslog format; kept as raw string
    m = EPOCH_TS_RE.match(first_line)
    if m:
        try:
            val = int(m.group(1))
            if val > 10**12:
                val //= 1000
            return datetime.fromtimestamp(val, tz=timezone.utc).isoformat()
        except (ValueError, OSError):
            return None
    return None


# ---------------------------------------------------------------------------
# Templating / masking (Q5)
# ---------------------------------------------------------------------------

MASK_PATTERNS = [
    (re.compile(r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"), "<UUID>"),
    (re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}(?::\d{1,5})?\b"), "<IP>"),
    (re.compile(r"\b[0-9a-fA-F]{16,}\b"), "<HEX>"),
    (ISO_TS_RE, "<TS>"),
    (re.compile(r"\b\d{10,13}\b"), "<EPOCH>"),
    (re.compile(r"\b\d+\.\d+\b"), "<FLOAT>"),
    (re.compile(r"\b\d+\b"), "<NUM>"),
    (re.compile(r'"[^"]{0,80}"'), '"<STR>"'),
]


def extract_message(line: str) -> str:
    """Pull the meaningful message text out of a line, stripping structural
    noise (timestamps, level tokens, JSON envelope) so templating groups on
    content rather than incidental formatting."""
    stripped = line.strip()
    if stripped.startswith("{"):
        try:
            obj = json.loads(stripped)
        except json.JSONDecodeError:
            return stripped
        for key in ("msg", "message", "error", "err", "description", "text", "detail"):
            val = obj.get(key)
            if isinstance(val, str):
                return val
        return stripped
    rest = stripped
    rest = ISO_TS_RE.sub("", rest, count=1).strip()
    rest = SYSLOG_TS_RE.sub("", rest, count=1).strip()
    rest = EPOCH_TS_RE.sub("", rest, count=1).strip()
    rest = LEVEL_START_RE.sub("", rest, count=1).strip()
    return rest if rest else stripped


def make_template(message: str) -> str:
    """Collapse variable tokens so structurally-identical entries group together."""
    out = message.strip()
    for pattern, repl in MASK_PATTERNS:
        out = pattern.sub(repl, out)
    out = re.sub(r"\s+", " ", out)
    return out[:300]


# ---------------------------------------------------------------------------
# Redaction (Q10) — default-on, high-confidence secret patterns only
# ---------------------------------------------------------------------------

REDACT_PATTERNS = [
    (re.compile(r"AKIA[0-9A-Z]{16}"), "[REDACTED_AWS_ACCESS_KEY]"),
    (re.compile(r"\bASIA[0-9A-Z]{16}\b"), "[REDACTED_AWS_TEMP_KEY]"),
    (re.compile(r"\bey[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b"), "[REDACTED_JWT]"),
    (re.compile(r"(?i)\bBearer\s+[A-Za-z0-9\-_\.=]{10,}"), "Bearer [REDACTED_TOKEN]"),
    (re.compile(r'(?i)\b(api[_-]?key|secret|token|password|passwd)\b\s*[:=]\s*["\']?[A-Za-z0-9\-_\.]{6,}["\']?'),
     lambda m: f"{m.group(1)}=[REDACTED]"),
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----"),
     "[REDACTED_PRIVATE_KEY_BLOCK]"),
]


def redact(text: str) -> str:
    out = text
    for pattern, repl in REDACT_PATTERNS:
        if callable(repl):
            out = pattern.sub(repl, out)
        else:
            out = pattern.sub(repl, out)
    return out


# ---------------------------------------------------------------------------
# Truncation (Q6) — hard cap, tail-prioritized
# ---------------------------------------------------------------------------


def truncate_lines(lines, max_lines):
    total = len(lines)
    if total <= max_lines:
        return lines, {"truncated": False, "total_lines": total, "analyzed_lines": total}
    tail = lines[-max_lines:]
    return tail, {
        "truncated": True,
        "total_lines": total,
        "analyzed_lines": max_lines,
        "note": f"analyzed the last {max_lines} lines (input has {total}); "
                f"pre-filter (grep/time-range) for full-file analysis",
    }


# ---------------------------------------------------------------------------
# Severity scoring (Q11) — composite: level + frequency + recency + novelty
# ---------------------------------------------------------------------------


def composite_score(level_counts, count, total_entries, first_ts, last_ts, latest_ts_overall):
    dominant_level = max(level_counts.items(), key=lambda kv: kv[1])[0]
    level_weight = LEVEL_RANK.get(dominant_level, 2)  # unknown treated as INFO-ish

    freq_ratio = count / total_entries if total_entries else 0
    import math
    freq_score = math.log10(count + 1) * 2

    recency_score = 0.0
    if last_ts and latest_ts_overall:
        try:
            last_dt = datetime.fromisoformat(last_ts)
            latest_dt = datetime.fromisoformat(latest_ts_overall)
            delta = (latest_dt - last_dt).total_seconds()
            # still happening at end of window = higher recency score
            recency_score = 3.0 if delta <= 0 else max(0.0, 3.0 - (delta / 3600.0))
        except (ValueError, TypeError):
            recency_score = 1.0
    else:
        recency_score = 1.0

    novelty_score = 2.0 if count <= 3 else (1.0 if count <= 10 else 0.0)

    score = (level_weight * 3) + freq_score + recency_score + novelty_score
    return round(score, 2)


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------


def run(text: str, max_lines: int, surface_level: str, do_redact: bool, max_clusters: int):
    lines = text.splitlines()
    lines, trunc_info = truncate_lines(lines, max_lines)

    raw_entries = group_into_entries(lines)

    parsed = []
    for entry_lines in raw_entries:
        first = entry_lines[0]
        full_text = "\n".join(entry_lines)
        level = extract_level(first)
        ts = extract_timestamp(first)
        message = extract_message(first)
        if do_redact:
            message = redact(message)
        parsed.append({
            "level": level,
            "timestamp": ts,
            "raw": full_text,
            "template": make_template(message),
        })

    total_entries = len(parsed)
    timestamps = [p["timestamp"] for p in parsed if p["timestamp"]]
    latest_ts_overall = max(timestamps) if timestamps else None

    clusters = defaultdict(lambda: {
        "count": 0,
        "level_counts": defaultdict(int),
        "first_seen": None,
        "last_seen": None,
        "sample_raw": None,
    })

    for p in parsed:
        c = clusters[p["template"]]
        c["count"] += 1
        c["level_counts"][p["level"]] += 1
        if p["timestamp"]:
            if c["first_seen"] is None or p["timestamp"] < c["first_seen"]:
                c["first_seen"] = p["timestamp"]
            if c["last_seen"] is None or p["timestamp"] > c["last_seen"]:
                c["last_seen"] = p["timestamp"]
        if c["sample_raw"] is None:
            c["sample_raw"] = p["raw"]

    surface_rank = LEVEL_RANK.get(surface_level.upper(), 3)

    cluster_list = []
    omitted_count = 0
    omitted_entries = 0
    for template, c in clusters.items():
        dominant_level = max(c["level_counts"].items(), key=lambda kv: kv[1])[0]
        rank = LEVEL_RANK.get(dominant_level, 2)
        sample = redact(c["sample_raw"]) if do_redact else c["sample_raw"]
        entry = {
            "template": template,
            "count": c["count"],
            "level_counts": dict(c["level_counts"]),
            "dominant_level": dominant_level,
            "first_seen": c["first_seen"],
            "last_seen": c["last_seen"],
            "sample": sample,
            "severity_score": composite_score(
                c["level_counts"], c["count"], total_entries,
                c["first_seen"], c["last_seen"], latest_ts_overall,
            ),
        }
        if rank >= surface_rank:
            cluster_list.append(entry)
        else:
            omitted_count += 1
            omitted_entries += c["count"]

    cluster_list.sort(key=lambda e: e["severity_score"], reverse=True)
    if max_clusters and len(cluster_list) > max_clusters:
        cluster_list = cluster_list[:max_clusters]

    return {
        "truncation": trunc_info,
        "total_entries_parsed": total_entries,
        "surface_level": surface_level.upper(),
        "clusters_surfaced": len(cluster_list),
        "clusters_omitted_below_threshold": omitted_count,
        "entries_omitted_below_threshold": omitted_entries,
        "redaction_applied": do_redact,
        "clusters": cluster_list,
    }


def main():
    ap = argparse.ArgumentParser(description="Deterministic log-triage engine")
    ap.add_argument("--file", help="Path to log file; reads stdin if omitted")
    ap.add_argument("--max-lines", type=int, default=50000, help="Hard cap on lines analyzed (tail-prioritized)")
    ap.add_argument("--surface-level", default="WARNING", help="Minimum level surfaced in clusters (default WARNING)")
    ap.add_argument("--no-redact", action="store_true", help="Disable secret redaction in samples")
    ap.add_argument("--max-clusters", type=int, default=40, help="Max clusters returned, ranked by severity")
    args = ap.parse_args()

    if args.file:
        with open(args.file, "r", errors="replace") as f:
            text = f.read()
    else:
        text = sys.stdin.read()

    result = run(
        text=text,
        max_lines=args.max_lines,
        surface_level=args.surface_level,
        do_redact=not args.no_redact,
        max_clusters=args.max_clusters,
    )
    json.dump(result, sys.stdout, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()

---
name: log-triage
description: Organize messy, mixed-format logs into ranked error clusters with plain-English explanations. Use when the user pastes a log dump, points at a log file, or asks to debug/triage/analyze logs, errors, stack traces, or a crash from any source (file, command output, or pasted text).
---

# log-triage

One-shot log triage: turn a messy log dump into a ranked, explained report.
No questions asked — point it at logs, get a report back. For a version that
asks clarifying questions first when the input is ambiguous, use
`log-triage-interactive` instead.

**Requires:** `../_shared/log-triage-core/triage.py` (stdlib-only Python 3).
`install.sh` places this automatically.

## When to use this

The user pastes raw log text, names a log file, or asks you to run a command
that produces logs (`docker logs`, `kubectl logs`, `journalctl`, `tail`,
etc.) and wants to know what's going on — a single pass, straight to a
report.

## Step 1 — Resolve the input source

Figure out what the user gave you, in this order:

1. **Pasted text** — if raw log-looking text is already in the conversation, use it directly.
2. **A file or glob path** — read it (respect the truncation behavior in Step 2; don't `cat` huge files into context yourself, let the script handle size).
3. **A command to run** — if the user names a live source (`docker compose logs api --tail 2000`, `kubectl logs pod/x`, a log file path), run it via Bash and capture stdout.
4. **Nothing given** — ask the user what to analyze (a path, a command, or to paste logs) before proceeding.

## Step 2 — Run the deterministic engine

Pipe the resolved text into the shared script. Do not reimplement parsing,
clustering, scoring, or redaction yourself — that logic lives in the script
specifically so it's deterministic and testable.

```bash
python3 <skill_dir>/../_shared/log-triage-core/triage.py [--file PATH] [--no-redact] [--surface-level WARNING] [--max-lines 50000]
```

- If you have the text in hand (paste or command output), write it to a temp file and pass `--file`, or pipe it via stdin: `echo "$TEXT" | python3 triage.py`.
- Default surface level is `WARNING` (INFO/DEBUG are parsed but only counted, not shown individually — see the `entries_omitted_below_threshold` field).
- Redaction is **on by default**. Only pass `--no-redact` if the user explicitly asks for unredacted output, and say out loud that you're doing so.
- Default cap is 50,000 lines, tail-prioritized. If `truncation.truncated` is `true` in the output, mention it in the report.

The script returns JSON: truncation info, total entries parsed, and a list
of `clusters` (template, count, level distribution, dominant level, first/last
seen, a redacted sample, and a composite `severity_score`), already sorted
by severity descending.

## Step 3 — Build the report (this is where you add judgment)

The script does **not** explain anything — that's your job. For each
surfaced cluster (prioritize the top ones; don't force explanations onto
every single low-severity cluster if there are many), produce:

1. **One-line label** — plain-English name for the pattern, not the raw template.
2. **Explanation**, layered:
   - Generic: what this class of error typically means.
   - Codebase-grounded (if you're running inside a repo): grep the error
     string / exception type / message fragment in the codebase; if found,
     name the file:line and explain what that code path does. Label this
     clearly as grounded ("found at `worker.py:88`"), not a guess.
   - Temporal correlation: if another cluster's `first_seen` lands just
     before this one's spike, mention it as a **possible** trigger —
     never state it as the cause. Only mention correlations you're
     actually confident about; don't manufacture noise.
3. **Severity score** and why it ranked where it did (dominant level, frequency, whether it's still recurring at the end of the window, novelty).

## Step 4 — Assemble the output

Produce, in this order:

1. **Executive summary** — one paragraph: what's the input, how much was analyzed (mention truncation if it happened), what's the headline problem.
2. **Ranked cluster list** — severity-ranked, each with label, count, first/last seen, explanation, and the redacted sample.
3. **Frequency sketch** — if timestamps were parsed for a cluster, a simple bucketed count or ASCII sparkline across the time window. Skip this if timestamps weren't parseable — don't fabricate a timeline.
4. **Omitted volume note** — one line: "`entries_omitted_below_threshold` INFO/DEBUG entries omitted below WARNING; ask if you want those included."
5. **Suggested next steps** — short, per top 1-3 cluster.
6. **Optional issue export** — for the top 1-3 clusters, offer a ready-to-paste GitHub-issue-formatted block (title + body with explanation, sample, first/last seen) — only include this if useful, don't pad the report with it for every cluster.

Write the full report to a file named `TRIAGE_REPORT.md` next to the input
(same directory as the log file, or cwd if the input was piped/pasted/from a
command), **and** show it inline in your response — both, not one or the
other.

## Rules

- Don't claim a correlation is causal. "Possible trigger", never "caused by", unless you have direct evidence (e.g., the exact same request ID appears in both).
- Don't silently drop the truncation/omission disclosures — the user needs to know what wasn't analyzed.
- Don't re-implement clustering/masking in your own head from the raw log dump — always run the script first and reason from its output.

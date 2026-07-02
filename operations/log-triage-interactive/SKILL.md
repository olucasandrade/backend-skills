---
name: log-triage-interactive
description: Interactively triage messy, mixed-format logs — asks clarifying questions when the input is ambiguous (multiple services, wide time range, unclear intent) before producing a ranked, explained report, then supports drilling into specific clusters. Use when the user wants to investigate logs conversationally rather than get a single report dump.
---

# log-triage-interactive

Same triage engine as `log-triage`, but with a pre-report clarification pass
and post-report drill-down. Use this when the input looks ambiguous (large,
multi-service, wide time range) or the user wants to investigate rather than
just receive a report.

**Dependency:** this skill uses the shared engine at
`../_shared/log-triage-core/triage.py` (stdlib-only Python 3). If you copy
this skill folder standalone, also copy `_shared/log-triage-core/`.

**If you want a plain one-shot report with no questions asked, use
`log-triage` instead** — that's the right choice when the input is already
small/focused/obviously scoped (e.g., a single pasted stack trace).

## Step 1 — Resolve the input source

Same as `log-triage` Step 1: pasted text, file/glob path, a command to run,
or — if nothing is given — ask the user directly what to analyze.

## Step 2 — Pre-scan (before running the full deterministic engine, or immediately after — whichever is cheaper for the input size)

Look for genuine ambiguity signals only. Do **not** ask questions just
because it's the interactive skill — if the input is small, single-service,
and short-range, skip straight to Step 4 with zero questions, matching
`log-triage`'s behavior exactly.

Ambiguity signals to check:

1. **Multiple services/sources interleaved** — e.g., distinct `service`/`app`/`container` fields or clearly different log shapes mixed together.
2. **Wide time range** — logs span hours/days/months rather than a focused incident window.
3. **Unclear intent** — the user's request doesn't say what they're actually trying to find out ("check the logs" vs. "why did the deploy fail at 3pm").

If you detect one or more of these, ask **up to 3** clarifying questions via
AskUserQuestion, e.g.:

- "I see logs from `api`, `worker`, and `nginx` — which one matters, or all of them?"
- "This spans 6 months — what time range should I focus on?"
- "Are you debugging a specific incident, or doing a general health review?"

Do not exceed 3 questions and do not turn this into an open-ended interview.
If the pre-scan finds no real ambiguity, skip questions entirely.

## Step 3 — Run the deterministic engine

Identical to `log-triage` Step 2 — same script, same flags, apply any
scoping the user gave you in Step 2 (time range, service filter) by
pre-filtering the input text before passing it to the script, not by asking
the script to do it.

```bash
python3 <skill_dir>/../_shared/log-triage-core/triage.py [--file PATH] [--no-redact] [--surface-level WARNING] [--max-lines 50000]
```

## Step 4 — Build and present the report

Same report structure and judgment layer as `log-triage` Steps 3-4
(explanations layered generic → codebase-grounded → temporal-correlation;
executive summary; ranked clusters; frequency sketch; omitted-volume note;
next steps; optional issue export). Write `TRIAGE_REPORT.md` and show it
inline.

## Step 5 — Post-report drill-down

After presenting the report, offer concrete next steps via AskUserQuestion
(e.g., "See full stack trace for cluster 2", "Narrow to the last 30 minutes
and re-triage", "Explain likely root cause for cluster 1 in more depth"),
but also accept free-form follow-up questions — don't force the user through
a menu if they just ask something directly.

- **Drilling into a cluster**: show the full (redacted) raw entries for that template, not just the one sample used in the report.
- **Narrowing scope / re-triage**: if the user asks to filter by time window, service, or level, filter the already-loaded log text and re-run Step 3 on the subset — don't ask the script to do filtering itself.
- Keep answering in this mode until the user is done; there's no fixed end state.

## Things to not do

- Don't ask clarifying questions when the input is already unambiguous — that's just friction, not "interactive."
- Don't ask more than 3 clarifying questions before the first report.
- Don't claim correlation is causation (same rule as `log-triage`).
- Don't disable redaction unless explicitly asked.
- Don't re-run the full script on the entire original input for every drill-down question if the user has already scoped down — work from the narrowed subset.

---
name: performance-review
description: Review a codebase for performance issues — N+1 queries, algorithmic complexity, unbounded reads, blocking I/O in hot/async paths, missing caching, connection-pool misuse, and redundant work — like a senior engineer's performance audit. Use whenever the user asks why code is slow, whether it will scale, to find bottlenecks or hot paths, or to review/audit for performance or scalability — even without the word "review".
---

# performance-review

Reviews an entire codebase (v1 scope — not a diff or PR review) for
static, source-visible performance issues. Sibling skill to
`implementation/security-review`, sharing the same overall shape (whole
codebase, LLM-judgment-heavy, no neutral IR) but a different lens.

**Purely static** — there's no execution environment available to this
skill, so every finding is inferred from reading code, never from measured
latency/profiling data. Frame findings accordingly ("this pattern will
degrade at scale," not "this takes 400ms").

**Requires:** `scripts/scan.py` and `implementation/_shared/file_enum.py`
(stdlib-only Python 3). `install.sh` places these automatically.

## Step 1 — Resolve the input

Accept a directory path (the codebase root to review). If nothing is
given, ask for one.

If the user separately mentions a `schema.ir.json` (from `rfc-to-schema`)
or `api.ir.json` (from `rfc-to-api`) they want cross-checked, note its
path for Step 4. **Only use these if explicitly pointed at — never
search the repo for them**, same convention as `security-review` (these
artifacts typically live in a `jobs/`-style directory, not next to the
source).

## Step 2 — Run the structural pre-pass

```bash
python3 <skill_dir>/scripts/scan.py --root PATH
```

This returns JSON with `files` (the filtered reading list — vendor,
binary, lockfile, and `.gitignore`-matched paths already excluded) and
`skipped` (what was excluded and why). There is deliberately **no
content-analysis heuristic pass** — a regex can't tell a 3-item config
loop from an unbounded one. Read every file in `files` directly.

**Scoping (large codebases only):** if `files` contains more than 150
entries, ask one question via AskUserQuestion before reading — options:
review everything (slower, complete), focus on a subtree the user names,
or focus on request-handling/entry-point paths first. Skip this entirely
below the threshold, or when the user's request already scoped the review.

## Step 3 — Read the code

For every file in `files`, look for these five categories (skip one
entirely, and say so, only if genuinely inapplicable — e.g. no
network/file I/O anywhere in the codebase):

1. **N+1 queries** — a loop that issues a DB/ORM/network call per
   iteration instead of a single batched call.
2. **Algorithmic complexity red flags** — nested loops over the same
   collection, or any pattern that's quadratic-or-worse on data that's
   realistically unbounded. Don't flag nested loops over a fixed-size,
   small collection (e.g. a handful of config entries) — that's noise.
3. **Missing pagination / unbounded reads** — "fetch all" with no limit,
   especially in a request-handling path or on a table/collection that
   plausibly grows without bound.
4. **Blocking I/O in hot/async paths** — a synchronous network/file/DB
   call inside code that's otherwise async, or inside a loop in a
   request-handling path where it'll be repeated per-item instead of
   run concurrently.
5. **Redundant work** — re-parsing/re-serializing/re-computing the same
   data on every loop iteration when it could be hoisted out and computed
   once.
6. **Missing caching** — the same expensive read (config fetch, remote
   lookup, heavy computation) repeated per-request or per-iteration with
   no memoization or cache layer, where the value is obviously reusable.
7. **Connection/client churn** — creating a new DB connection, HTTP
   client, or session object per request/iteration instead of reusing a
   pooled/module-level one.

**Codebase-wide patterns matter more than isolated lines** — if the same
inefficiency recurs across many call sites (e.g. the same N+1 pattern in
every list endpoint), report it as one systemic finding listing every
affected location, not N near-duplicates.

## Step 4 — Optional: cross-check against the RFC pipeline

Only if the user explicitly pointed you at these artifacts in Step 1:

- **`schema.ir.json`** — for fields you observe the code actually
  querying/filtering/sorting by, check whether the IR declares that field
  `unique` or otherwise indexed. A field the code hits on every request
  with no indexing signal in the schema is a real, checkable finding —
  this is how this skill covers "missing index" without guessing at DB
  internals directly from application code.
- **`api.ir.json`** — for each operation declared `paginated: true` with
  a `pagination_style`, verify the handler actually applies a
  limit/cursor. A mismatch is real, checkable drift.

Report both under an **RFC/implementation drift** section — same
name/pattern as `security-review`'s, not new vocabulary — since this
check only exists because the pipeline artifacts happened to be
available, not because every finding of this kind implies one.

## Step 5 — Assemble findings

Each finding needs: `file`, `line`(s), `category` (one of Step 3's seven),
`severity`, `confidence`, a description, and a concrete suggested fix
(name the actual mechanism: batch via `WHERE id IN (...)`, add a `LIMIT`/
cursor, hoist the parse out of the loop, use an async HTTP client — not
just "make this faster").

**Severity** (impact at realistic production scale, not correctness):
- **Critical** — will cause timeouts/outages/unusable latency at
  expected scale (e.g. N+1 on a list endpoint already handling hundreds
  of items).
- **High** — meaningfully degrades latency/throughput under normal, not
  just worst-case, load.
- **Medium** — real inefficiency, but only matters well beyond currently
  plausible scale, or in a rarely-hit path.
- **Low** — minor/theoretical, correct-but-not-optimal, worth a mention
  not a fix-now.

**Confidence** (how sure this is a real problem, not a misread):
- **High** — traced the full path; no mitigating factor visible (e.g. no
  batching/caching layer above this code).
- **Medium** — the pattern looks wrong but a framework-level mitigation
  might exist that isn't visible in this file (e.g. ORM lazy-load
  batching, an upstream cache).
- **Low** — flagged out of caution; plausible this is a non-issue.

For every Medium/Low-confidence finding, add a one-line false-positive
note (e.g., "might already be batched if this ORM's `select_related` is
configured elsewhere — verify"). Never drop a finding purely for low
confidence.

## Step 6 — Write the report

Write `PERFORMANCE_REVIEW.md` next to the codebase root reviewed (or cwd
if the root has no clear parent worth writing into), and show it inline —
both. Structure:

1. **Summary line** — count per severity tier.
2. **Findings**, grouped by severity (Critical first), each with
   category, confidence, description, and suggested fix.
3. **RFC/implementation drift** (if Step 4 ran), its own section.
4. **Scan coverage** — files reviewed vs. skipped, and why.
5. **Out of scope** — note that this is a static review only: memory
   leaks and true root-cause latency require runtime/profiling data this
   skill doesn't have access to; recommend profiling in staging/prod if
   the codebase's scale makes that worthwhile.

No single approve/reject verdict for a whole codebase — the severity
summary is the top-line signal, same as `security-review`.

Every invocation is treated as a fresh review — this skill does not
track prior reviews or diff against an earlier scan in v1.

## Step 7 — Offer follow-ups

After presenting the report, offer concrete next steps via AskUserQuestion —
e.g. "Explain finding N in more depth", "Draft a fix for the top finding",
"Re-run scoped to <subtree>" — and also accept free-form follow-up
questions. Only draft or apply code fixes when the user explicitly picks
that option; never edit the reviewed codebase unprompted. When drafting a
fix, show a diff and let the user decide whether to apply it.

## Rules

- Don't claim measured latency/timing — every finding is inferred from
  reading code, not runtime data.
- Don't flag nested loops over small, fixed-size collections as
  algorithmic complexity issues.
- Don't search the repo for `schema.ir.json`/`api.ir.json` — only use
  them if the user explicitly points you at one.
- Don't drop findings for low confidence — flag with a false-positive
  note instead.
- Don't report N near-duplicate findings for one systemic pattern —
  merge into one finding listing every affected location.
- Don't edit the reviewed codebase unless the user explicitly asks for a
  fix to be applied.

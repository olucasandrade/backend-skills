---
name: architecture-review
description: Review an existing codebase's architecture for structural health — layering violations, circular dependencies, coupling/cohesion problems, and deviation from a stated architecture pattern. Use whenever the user asks to review architecture, check module boundaries or dependencies, find circular imports, assess tech debt or code structure, or asks "is this codebase well structured" — even without the word "architecture".
---

# architecture-review

Reviews an entire codebase (v1 scope — not a diff or PR review) for
structural health, not code correctness or security/performance.

**Requires:** `scripts/scan.py` and `implementation/_shared/file_enum.py`
(stdlib-only Python 3). `install.sh` places these automatically.

## Step 1 — Resolve the input

Accept a directory path (the codebase root to review). If nothing is
given, ask for one.

If the user separately mentions a `schema.ir.json`/`api.ir.json`, note its
path for Step 4. **Only use it if explicitly pointed at — never search
the repo for it**, same convention as `security-review`/`performance-review`.

## Step 2 — Run the structural pre-pass

```bash
python3 <skill_dir>/scripts/scan.py --root PATH
```

Unlike its two siblings, this pre-pass does real graph analysis, not just
enumeration:
- `files`/`skipped` — same filtered reading list as the other two skills.
- `dependency_graph` — an in-repo import graph, **Python, JS/TS, and Go**
  (regex-based import/require parsing; external package imports are
  deliberately excluded — this graph is in-repo structure only). Go edges
  are package-directory-level (from `go.mod`'s module path), not
  file-level. Other languages are out of scope for this pass; still read
  those files yourself in Step 3, just without a pre-built graph to lean on.
- `cycles` — circular dependencies, **always high confidence**: either
  the graph has a cycle or it doesn't, no judgment involved. Every
  reported cycle is a real finding, never a candidate to second-guess.

**Scoping (large codebases only):** if `files` contains more than 150
entries, ask one question via AskUserQuestion before reading — options:
review everything (slower, complete), focus on a subtree the user names,
or focus on request-handling/entry-point paths first. Skip this entirely
below the threshold, or when the user's request already scoped the review.

## Step 3 — Read the code

For every file, look across four categories (skip one only if genuinely
inapplicable, and say why):

1. **Circular dependencies** — start from `cycles` directly; explain the
   concrete risk of each (init-order bugs, forced tight coupling, harder
   incremental compilation/testing) rather than just restating the cycle.
2. **Layering violations** — a lower layer (data access, core domain
   logic) importing from a higher one (HTTP handlers, presentation, UI) —
   readable directly off `dependency_graph`'s edges once you know which
   directories represent which layer from the codebase's own structure
   (don't assume a layering scheme the codebase doesn't actually have).
3. **Coupling/cohesion red flags** — a module with unusually high fan-in/
   fan-out relative to the rest of the graph (a "god module" everything
   depends on), or a module whose contents are visibly unrelated
   (grab-bag `utils`/`helpers` files that have become load-bearing).
4. **Architecture-pattern deviation** — **only if the codebase itself
   declares a pattern** (a README/ADR stating "this follows hexagonal
   architecture," "clean architecture," a documented layering scheme,
   etc.). Flag concrete violations of that *stated* pattern only. **Never
   invent an expected pattern the codebase never claimed to follow** —
   that would be judging code against a standard nobody set.

## Step 4 — Optional: cross-check against the RFC pipeline

Only if explicitly pointed at `schema.ir.json`/`api.ir.json` in Step 1:
check whether an operation/entity's declared domain (e.g. inferred from
its name or grouping in the IR) matches where its implementation actually
lives in the module structure — a `billing`-named operation whose handler
imports mostly from a `notifications` module is real, checkable
ownership drift. Report under an **RFC/implementation drift** section,
same name/pattern as the other two `implementation/` skills.

## Step 5 — Assemble findings

Each finding: `files` (one or more), `category` (one of Step 3's four),
`severity`, `confidence`, description, and a concrete suggested fix (name
the actual mechanism: break the cycle by extracting a shared interface,
move the violating import behind the intended boundary, split the god
module along its actual responsibilities).

**Severity** (maintainability/change-risk impact):
- **Critical** — actively causing bugs or already blocking safe changes
  (e.g. a cycle that's caused a real init-order bug, or forces awkward
  workarounds already visible in the code).
- **High** — will meaningfully slow down or risk-inflate near-future
  changes if left alone.
- **Medium** — a real structural smell, not urgent.
- **Low** — minor/stylistic, worth a mention.

**Confidence:**
- Cycles from `scan.py`: always **High** — deterministic.
- Layering/coupling/pattern-deviation judgment: the usual High/Medium/Low,
  with a one-line false-positive note for anything below High (e.g., "this
  reads as a layering violation, but verify this directory is actually
  meant to be a separate layer and not just a naming convention").

Never drop a finding for low confidence.

## Step 6 — Write the report

Write `ARCHITECTURE_REVIEW.md` next to the codebase root reviewed (or cwd
if it has no clear parent), and show it inline — both. Structure:
severity-tier summary line, findings grouped by severity, RFC/
implementation drift section (if Step 4 ran), scan coverage (files
reviewed vs. skipped, and which languages had a dependency graph built
vs. which didn't). No single approve/reject verdict for a whole codebase
— same posture as `security-review`/`performance-review`.

Every invocation is a fresh review — no revision tracking in v1.

## Step 7 — Offer follow-ups

After presenting the report, offer concrete next steps via AskUserQuestion —
e.g. "Explain finding N in more depth", "Draft a fix for the top finding",
"Re-run scoped to <subtree>" — and also accept free-form follow-up
questions. Only draft or apply code fixes when the user explicitly picks
that option; never edit the reviewed codebase unprompted. When drafting a
fix, show a diff and let the user decide whether to apply it.

## Rules

- Don't invent an expected architecture pattern the codebase never
  declared.
- Don't build or claim a dependency graph for languages outside Python/
  JS/TS/Go — read those files directly instead, without a graph to lean on.
- Don't count external package imports as part of the dependency graph —
  in-repo structure only.
- Don't search the repo for `schema.ir.json`/`api.ir.json` — only use
  them if the user explicitly points you at one.
- Don't drop findings for low confidence — flag with a false-positive
  note instead.
- Don't edit the reviewed codebase unless the user explicitly asks for a
  fix to be applied.

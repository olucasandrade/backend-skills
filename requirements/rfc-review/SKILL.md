---
name: rfc-review
description: Review an RFC, design proposal, or ADR for completeness, ambiguity, risk, and feasibility before it's approved — like a senior engineer's review pass. Use when the user asks to review, critique, or sanity-check an RFC/proposal/design doc, or asks "is this ready to approve."
---

# rfc-review

Reviews a single proposal-style document (RFC, ADR, PRFAQ, or freeform
design doc) end-to-end: completeness, ambiguity, risk, feasibility, scope,
cost/value, stakeholder impact, testability, and — since this repo's
`design/` skills consume approved RFCs later — whether the doc has enough
concrete detail to be mechanically turned into a schema/API spec.

This skill does its own gap-analysis internally; it does not delegate to
`requirement-gap-analysis`, which is scoped to pre-solution input, not RFCs.

**Dependency:** uses the deterministic pre-pass script at
`scripts/doc_prepass.py` (stdlib-only Python 3). If you copy this skill
folder standalone, copy `scripts/` alongside it.

## Step 1 — Resolve the input

Accept a file path or pasted text only. **Do not attempt to fetch URLs**
(Google Docs / Notion / Confluence links almost always return a login wall
or unusable JS shell to a fetch tool) — if the user gives a link to an
external doc platform, ask them to paste the content or export it to a
markdown/text file instead.

If nothing is given, ask what to review.

## Step 2 — Run the structural pre-pass

```bash
python3 <skill_dir>/scripts/doc_prepass.py --file PATH
```

This returns JSON with:
- `template` — detected template (`rfc`, `adr`, `prfaq`, or `null`) plus matched/missing expected sections for that template. `null` means no recognized template — treat the doc as freeform, don't penalize it for "missing sections" that were never part of any template it's following.
- `sections` — the doc's actual heading structure.
- `stats` — word count, heading count, image references, link targets, and any broken **local** relative links.
- `vague_language_candidates` — a **candidate** list of hedge-word spots (e.g. "should be fast," "TBD," "might"). This is not an authoritative ambiguity verdict — a hedge word can be perfectly fine in context ("might" in a brainstormed alternatives list is fine; "might" in the actual design's core guarantee is not). Use your judgment on each candidate; don't just relay the list as findings.

## Step 3 — Sanity-check what you're looking at

Before reviewing in earnest:
- **Non-proposal doc**: if the doc doesn't read as forward-looking design/decision content (e.g. it's a README, a postmortem, install instructions), say so plainly and confirm the user actually wants an RFC-style review applied — don't force the lens onto an unrelated doc type.
- **Stub/very short input**: if the doc is a few sentences, still review what's there, but lead the report with a clear note that this is early-stage and the review is necessarily limited by missing content — don't refuse, and don't pretend it's a complete review either.
- **Embedded diagrams/images**: for each `image_refs` entry, explicitly note in the report "diagram referenced but not analyzed — verify manually," especially when the surrounding text leans on it for the actual design explanation. Never silently skip these — that's often exactly where the real risk lives.

## Step 4 — Review each dimension, with judgment

Apply these dimensions, but skip any that are genuinely not relevant to this
particular doc and say why (don't force every dimension onto every RFC):

1. **Completeness** — using the detected template's missing-sections list as a starting point, not a verdict. A missing "Rollback" section on a proposal to rename a config key doesn't matter; on a proposal to migrate a datastore, it does. If a sibling `GAP_ANALYSIS.md` exists (from `requirements/requirement-gap-analysis`, run earlier on the pre-design input this RFC grew out of), check which of its flagged questions got addressed in this RFC and which didn't — note any unaddressed **Blocking**/**Should-Fix** gaps as their own completeness findings. Optional, presence-checked — never require it.
2. **Ambiguity** — walk the `vague_language_candidates`, judge each in context, and add any others you notice that the pre-pass wordlist wouldn't catch (unfalsifiable claims, undefined terms, contradictory statements between sections).
3. **Risk** — security, data-loss, operational blast-radius, migration risk for existing users.
4. **Feasibility** — does the proposed design actually achieve the stated goals; any internal contradictions between the goals and the design.
5. **Scope** — is the boundary (goals vs. non-goals) clear; any scope creep.
6. **Cost/complexity vs. value** — is the proposed complexity proportionate to the problem.
7. **Stakeholder impact** — who's affected, is there a migration path for existing users/consumers.
8. **Testability** — how will anyone know this worked; are success criteria stated.
9. **Downstream readiness** — if this RFC will later be fed into `rfc-to-schema` or `rfc-to-api` (this repo's `design/` skills), are entities, fields, and operations concrete enough to be mechanically derived, or is that detail still missing. Flag this as its own finding when relevant, since it blocks a specific next step, not just general clarity.

**Codebase grounding** (only when run inside a repo): for concretely
checkable claims about the existing system ("no current rate limiting on
this endpoint," "no other service reads this table"), grep for them. Label
each such finding clearly as **verified** (you found supporting/contradicting
evidence) or **unverified** (not concretely checkable, taking the doc's word
for it). Don't attempt exhaustive verification of every claim — only the
ones that are cheap and unambiguous to check.

## Step 5 — Tone

Infer the review's tone from the document's own voice — a terse,
engineering-dense doc gets a terse review; a doc written for a broader
stakeholder audience gets a more measured one. Don't apply a fixed tone
regardless of the source doc.

## Step 6 — Assemble the report

1. **Overall verdict** — one of:
   - **Not Ready** — has one or more Blocking findings.
   - **Ready with Revisions** — no Blocking findings, but Should-Fix items exist.
   - **Ready to Approve** — only Nice-to-Have/Question findings remain, if any.
2. **Findings**, each tagged with a severity tier and containing: what's wrong, why it matters, and a **concrete suggested fix** (not just "this is vague" — propose the sharper version; not just "missing rollback plan" — sketch what one might look like for this design):
   - **Blocking** — real risk, missing critical decision, or too incomplete to evaluate.
   - **Should-Fix** — meaningfully improves the doc, not optional but not a blocker.
   - **Nice-to-Have** — polish, minor clarity improvements.
   - **Question** — something the reviewer would ask the author, not a defect per se.
3. **Detected template and section map** — what template (if any) was recognized, and the doc's actual structure.
4. **Diagrams not analyzed** — list, if any.

Write the full report to `RFC_REVIEW.md` next to the input file (or cwd if
piped/pasted), and show it inline — both, not one or the other.

Every invocation is treated as a fresh review — this skill does not track
prior reviews or diff against earlier versions of the same doc in v1.

## Things to not do

- Don't force the RFC-review lens onto a document that clearly isn't a proposal without checking with the user first.
- Don't relay `vague_language_candidates` as findings verbatim — judge each one in context; many will be non-issues.
- Don't claim a codebase-grounded finding is "verified" unless you actually found concrete supporting/contradicting evidence.
- Don't silently skip image/diagram references — always disclose that they weren't analyzed.
- Don't attempt to fetch external doc-platform URLs — ask for pasted content or a file instead.
- Don't apply a fixed tone regardless of the document's own voice.

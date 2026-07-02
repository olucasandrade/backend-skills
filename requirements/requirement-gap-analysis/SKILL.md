---
name: requirement-gap-analysis
description: Interrogate a pre-design requirements doc, stakeholder brief, epic, or freeform notes for missing information — before any solution has been proposed. Use when the user asks what's missing from a requirements doc, wants help scoping a feature before writing an RFC, or asks "what should I ask before we design this."
---

# requirement-gap-analysis

Interrogates a **pre-solution** input — a raw requirements doc, stakeholder
brief, Jira epic description, meeting notes, or freeform text describing a
problem/feature request — for what's *not yet known* that needs to be
known before anyone should start designing a solution. This runs one
stage earlier than `rfc-review`: `rfc-review` judges whether a *proposed
design* holds up (including a "completeness" check against what the RFC
itself claims to cover); this skill has no proposal to judge at all — it
asks category-based questions the input document doesn't even attempt to
answer, because it isn't structured as a design doc yet.

**No deterministic pre-pass script** — the first skill in this repo's
`requirements/`/`design/` family with no script layer at all. `rfc-review`'s
pre-pass earns its keep by parsing detectable RFC/ADR/PRFAQ template
structure; this skill's input is unstructured by design, so there's no
structure to extract. Judgment only, closer in spirit to
`security-review`/`performance-review`'s posture than to `rfc-review`'s.

## Step 1 — Resolve the input

Accept a file path or pasted text only — same as `rfc-review`, and for
the same reason: don't attempt to fetch external doc-platform URLs (Google
Docs/Notion/Confluence links return login walls or unusable JS shells to
a fetch tool); ask for pasted content or an export instead.

If nothing is given, ask what to analyze.

**No template expected.** Don't penalize the input for lacking RFC-style
structure — bullet points, a paragraph, a transcript excerpt, and a
formal brief are all equally valid input shapes here.

## Step 2 — Sanity-check the input's stage

Before analyzing: if the input already reads as a proposed *solution*
(has a Design/Approach/Solution section, describes a specific technical
implementation rather than a problem to solve), this input is past this
skill's intended stage. Say so plainly and suggest `rfc-review` instead —
don't silently run gap analysis on a doc that's actually ready for design
review; the two skills would produce overlapping, confusing output on the
same input.

## Step 3 — Interrogate across categories

Work through each category, skipping one only if genuinely inapplicable
to this input (say why):

1. **Functional** — unstated behavior, missing use cases, unclear scope
   boundaries (what's explicitly in/out of scope, if not stated).
2. **Non-functional** — performance, scale, availability, latency
   expectations never stated.
3. **Edge cases** — error states, concurrent access, empty/boundary
   conditions not addressed.
4. **Stakeholders** — who's affected or should be consulted that isn't
   mentioned (legal, security, other teams whose systems this touches,
   end users with accessibility needs).
5. **Data** — what data is involved, where it comes from, ownership/
   retention/privacy implications.
6. **Compliance/regulatory** — anything industry- or jurisdiction-specific
   left unaddressed, when inferable from context (don't invent regulatory
   concerns with no basis in the input's domain).

**Codebase grounding** (only when run inside a repo, same convention as
`rfc-review`): for concretely checkable claims about the existing system,
grep for them, and label findings **verified**/**unverified** accordingly.
Don't attempt exhaustive verification — only what's cheap and unambiguous.

## Step 4 — Assemble findings

Each finding: `category`, **the specific question that needs answering**
(not "X is missing" — the actual question someone should go ask), and why
it matters (what gets designed wrong, or costs more to fix later, if this
stays unanswered). Tag each with a severity tier, reusing `rfc-review`'s
scale directly:

- **Blocking** — can't responsibly start designing without this answered.
- **Should-Fix** — meaningfully de-risks the design if answered now, not
  fatal to skip.
- **Nice-to-Have** — worth asking, low stakes either way.
- **Question** — genuinely open, more a clarifying question than a gap.

**No confidence axis.** Unlike `security-review`/`performance-review`'s
judgment calls about whether code is *actually* buggy, a gap is a gap by
construction — the input simply doesn't address it. There's no "might be
a false positive" dimension to a missing answer.

## Step 5 — Write the report

Write `GAP_ANALYSIS.md` next to the input file (or cwd if piped/pasted),
and show it inline — both. Structure: findings grouped by category, each
tagged with severity, containing the question and why it matters. No
overall verdict — there's no proposal to approve/reject, only questions
to go answer.

Every invocation is a fresh analysis — this skill does not track prior
analyses or diff against an earlier version of the same input in v1.

## Step 6 — Composition with `rfc-review`

When `rfc-review` later runs on the RFC that eventually gets written from
this input, and finds a sibling `GAP_ANALYSIS.md`, it should note under
its own Completeness dimension which flagged gaps got addressed in the
RFC and which didn't — same explicit sibling-check convention as the rest
of the pipeline, not a hard dependency.

## Things to not do

- Don't apply this skill to a doc that already proposes a solution — flag
  it and point to `rfc-review` instead.
- Don't invent compliance/regulatory concerns with no basis in the
  input's actual domain.
- Don't penalize the input for lacking RFC-style structure — that's not
  what this skill is checking.
- Don't attach a confidence score to findings — a gap is a gap by
  construction.
- Don't invent an overall approve/reject verdict.
- Don't attempt to fetch external doc-platform URLs.

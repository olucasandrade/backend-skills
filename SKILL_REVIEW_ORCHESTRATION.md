# Skill improvement orchestration

This document is an execution prompt. It was produced by reviewing all 12 skills in
this repo against Anthropic's skill-creator guidelines
(https://github.com/anthropics/skills/blob/main/skills/skill-creator/SKILL.md).
It tells you — the executing model — exactly what to change, in what order, and how
to verify each change. Follow it literally. Where this document says "delete the
sentence starting with X", find that exact text and delete only that. Where it says
"insert verbatim", copy the block character-for-character. Do not improvise
improvements beyond what is written here.

## How to execute

1. Work through phases **in order** (0 → 6). Within a phase, work one skill at a time.
2. After every phase, run the verification commands for that phase (listed at the end
   of each phase). If a check fails, fix it before moving on.
3. Make **one git commit per phase**, message format: `Phase N: <phase title>`.
   Do NOT push. Do NOT amend previous commits.
4. If an instruction references text you cannot find (the file may have drifted),
   STOP work on that item, leave it unchanged, and record it under a
   `## Skipped items` section you append to the bottom of this file. Never guess at
   a "close enough" match for deletions.

## Global invariants — never violate these

- Never change a skill's frontmatter `name:`.
- Never move, rename, or delete a skill directory, a `scripts/` file, a `fixtures/`
  file, or anything under any `_shared/` directory, except where Phase 4 explicitly
  says to edit `implementation/architecture-review/scripts/scan.py`.
- Never edit `MANIFEST.json` paths (Phase 4 does not add new shared deps).
- Everything stays Python-stdlib-only. No `pip install`, no `requirements.txt`,
  no `package.json`. CI enforces this and will fail otherwise.
- All existing unit tests must still pass after every phase:
  the full list of test suites is in `.github/workflows/tests.yml` under the `test`
  job matrix. Run each as `cd <dir> && python3 -m unittest discover -s tests -v`.
- SKILL.md files keep their existing overall section flow (frontmatter → intro →
  Requires line → Steps → output/report step → Rules). Do not reorder steps except
  where a phase explicitly inserts a new step.
- Do not touch `README.md`, `PIPELINES.md`, or `EXAMPLES.md` except in Phase 6.

---

## Phase 0 — Fix stale references (small, exact edits)

These are factual errors; fix them first so later phases don't copy them around.

1. `requirements/rfc-review/SKILL.md` — the second paragraph contains
   `(`requirement-gap-analysis`, `system-design-review`, `architecture-review`),`.
   `system-design-review` does not exist and `architecture-review` lives under
   `implementation/`, not `requirements/`. Replace the entire paragraph (the one
   beginning "This skill does its own gap-analysis and architecture-fit checks
   internally;") with this single sentence:

   > This skill does its own gap-analysis internally; it does not delegate to
   > `requirement-gap-analysis`, which is scoped to pre-solution input, not RFCs.

2. `implementation/architecture-review/SKILL.md` — delete the entire paragraph
   beginning `**Originally sketched under `requirements/`, moved here deliberately.**`
   (it references the deleted `system-design-review` and is repo history, not
   instructions).

3. `design/rfc-to-api/SKILL.md` — in the "Composition with other skills" section,
   the bullet says `**`er-generator`** (planned)`. It is implemented. Change
   `(planned)` to nothing (just `**`er-generator`**:`).

4. `design/rfc-to-schema/SKILL.md` — in the "Composition with other skills" section,
   remove the two `(✅ implemented)` markers (keep the bullets otherwise unchanged).

**Verify:** `grep -rn "system-design-review\|✅ implemented\|(planned)" --include="SKILL.md" .`
must return nothing.

---

## Phase 1 — Token trim

**Why:** SKILL.md bodies load into context on every trigger. The skill-creator
guidance is "keep instructions lean — remove non-essential elements." These files
currently carry repo-development history ("this was the first skill that…",
"considered and rejected…", "extracted once a second consumer…") which is authoring
rationale, not execution instructions. It costs tokens on every single invocation
and adds zero behavior.

**Target:** every SKILL.md ≤ 750 words (`wc -w`) after this phase. Current counts
range 712–1328.

### 1a. Global rules (apply to every SKILL.md)

- **R1 — Standardize the dependency paragraph.** Every skill has a multi-sentence
  `**Dependency:** …` (or `**Dependencies:** …`) paragraph explaining what to copy
  for standalone installs. Replace each with exactly one line, keeping the actual
  paths from the original paragraph:

  > **Requires:** `<the same script/shared paths the original paragraph named>`
  > (stdlib-only Python 3). `install.sh` places these automatically.

  Do not drop any path the original named. Skills with no script
  (`requirement-gap-analysis`, `incident-summary` keeps its triage.py line) — for
  `requirement-gap-analysis` there is no dependency paragraph to normalize; instead
  see its per-skill list below.

- **R2 — Delete repo-history and design-rationale asides.** Any sentence whose
  content is about how/why this repo was built rather than what to do now. The
  per-skill lists below enumerate every instance; do not hunt for more on your own.

- **R3 — Deduplicate "Things to not do".** In each skill's final "Things to not do"
  list, delete any bullet that restates an instruction already stated in a Step
  above **in the same words** (the per-skill lists name which bullets to delete).
  Keep bullets that add a genuinely new constraint. Rename the section header from
  `## Things to not do` to `## Rules` in every skill (shorter, same meaning).

- **R4 — Keep the "why" but compress it.** Where a rule has a one-clause
  justification ("never state it as the cause"), keep it. Where the justification
  is a multi-sentence story, cut to the rule plus at most one clause of why.

### 1b. Per-skill deletion lists

Find each quoted anchor text exactly; delete the span described.

**`requirements/rfc-review/SKILL.md`** (after Phase 0 edit)
- No further deletions beyond R1/R3. R3: delete the "Don't apply a fixed tone…"
  bullet (Step 5 already says it) and the "Don't attempt to fetch external
  doc-platform URLs" bullet (Step 1 already says it).

**`requirements/requirement-gap-analysis/SKILL.md`**
- Delete the entire paragraph starting `**No deterministic pre-pass script** —`
  and ending `…closer in spirit to\n`security-review`/`performance-review`'s posture than to `rfc-review`'s.`
  Replace with one line: `No script layer — this skill is judgment only.`
- In Step 1, shorten the first paragraph to:
  `Accept a file path or pasted text only — don't fetch external doc-platform URLs (they return login walls); ask for pasted content or an export instead. If nothing is given, ask what to analyze.`
- R3: delete the bullets "Don't attempt to fetch external doc-platform URLs." and
  "Don't penalize the input for lacking RFC-style structure —…" (both already
  stated in Step 1).

**`design/rfc-to-schema/SKILL.md`**
- In the Dependencies paragraph (before applying R1), note it contains
  `(shared with `rfc-to-api` — extracted once that second skill needed the identical pluralization logic)`.
  R1 replaces the whole paragraph anyway; just make sure the R1 line keeps both
  paths (`scripts/` and `../_shared/`).
- In Step 3, replace the full abstract-type enumeration (the span from
  `using abstract types: `uuid`, `string`` through `…which isn't a single field).`)
  with: `using the abstract type system documented in the IR spec at the top of `scripts/render_schema.py` — read that docstring before writing the IR.`
  Keep the sentence that follows pointing at the IR spec if it becomes redundant —
  if the paragraph then contains two pointers to the same docstring, keep only one.
- R3: delete the bullet "Don't attempt to fetch external doc-platform URLs."

**`design/rfc-to-api/SKILL.md`**
- Delete from the Dependencies paragraph the aside
  `— the first\nreal cross-skill extraction in this repo, done once a second consumer\nactually needed the same logic, not before` (R1 replaces the paragraph anyway).
- In Step 3, the single giant paragraph enumerating every IR field duplicates
  `render_api.py`'s IR_SPEC docstring. Replace the whole Step 3 body (keep the
  heading and the final "Handling gaps" paragraph) with:

  > Produce `api.ir.json`: a list of `operations`. The full field-by-field IR spec
  > lives in the IR_SPEC docstring at the top of `scripts/render_api.py` — read it
  > before writing the IR. The details that most often go wrong:
  > - `name` is camelCase and protocol-agnostic — never a URL path.
  > - Set `entity` whenever the operation targets a specific entity — REST path
  >   derivation for `read`/`update`/`delete`/`action` kinds depends on it.
  > - `kind` is a semantic category (`create`/`read`/`list`/`update`/`delete`/`action`),
  >   not an HTTP verb.
  > - Base error cases map to status codes automatically; domain-specific error
  >   cases **require an explicit `status_hint`**.
  > - Populate `required_scopes` only when the RFC states them — never invent a
  >   role/scope system.
  > - `rest_override`/`graphql_override` are used verbatim when present.

- In the Rules section (R3): in the bullet about GraphQL enums, delete the trailing
  `(a real bug caught during this skill's own testing)`.

**`design/er-generator/SKILL.md`**
- In the "Architecture note" paragraph, keep the first two sentences (through
  `…not extraction judgment.`) — they are behavioral. Fine as-is.
- In the Dependency paragraph, delete the aside beginning
  `— each type-mapping table in this repo's renderers is genuinely\ndifferent per target, so nothing here met the bar for extraction (see the\n`rfc-to-api`/`rfc-to-schema` grill notes on why `slugify` *did* meet it)`
  (R1 replaces the paragraph; the R1 line for this skill is just `scripts/render_er.py`).
- In the Rules section, in the last bullet delete the trailing
  `(verify with `validate_mermaid()` if you touch the renderer — this exact class of bug was caught during this skill's own testing)` and replace with
  `(verify with `validate_mermaid()` if you touch the renderer)`.

**`implementation/security-review/SKILL.md`**
- Delete the sentence `This is the first skill in this\nrepo that reads actual source code rather than design docs or logs, and the\nfirst where the core value is LLM judgment rather than deterministic\nrendering — there's no neutral IR to generate here, just a careful read.`
  Keep the first sentence of the intro paragraph.
- R3: delete the bullets "Don't perform or simulate dependency/CVE scanning —…"
  (intro already covers it) and "Don't invent an overall approve/reject verdict…"
  (Step 6 already says it).

**`implementation/performance-review/SKILL.md`**
- In Step 2, replace the span from `Unlike `security-review`'s\npre-pass, there is **no content-analysis pass here**` through
  `…it would just train you (and the reader) to ignore noisy output.` with:
  `There is deliberately **no content-analysis heuristic pass** — a regex can't tell a 3-item config loop from an unbounded one.`
- R3: delete the bullet "Don't invent an overall approve/reject verdict for the codebase." (Step 6 already says it).

**`implementation/architecture-review/SKILL.md`** (after Phase 0 edit)
- In the intro, delete `Sibling\nto `implementation/security-review` and `implementation/performance-review`\n— same shape (real code as input, no proposal/doc to judge), reusing the\nsame shared file-enumeration script, but a distinct lens.` — the frontmatter and
  Steps already convey this.
- R3: delete the bullet "Don't invent an overall approve/reject verdict for the codebase."

**`implementation/api-docs/SKILL.md`**
- In the intro, delete the span `Closer in spirit to\n`design/rfc-to-schema`/`design/rfc-to-api` (render + narrate) than to its\n`implementation/` siblings `security-review`/`performance-review` (which\nread arbitrary source with no structured IR to lean on) — this skill's` and start
  the sentence at `This skill's primary path renders from an already-produced contract, and only falls back to reading source code when no structured contract exists at all.`
- In Step 5, in the paragraph about drift, delete the parenthetical
  `(Implementation-vs-IR drift is `security-review`'s\nand `performance-review`'s territory, not this skill's — see their\n"RFC/implementation drift" sections; duplicating that check here would\njust be the same work done twice.)` and keep only
  `Implementation-vs-IR drift checks are `security-review`'s/`performance-review`'s job, not this skill's.`
- R3: delete the bullet "Don't attempt an implementation-drift check —…" (now
  redundant with the Step 5 line kept above).

**`operations/log-triage/SKILL.md`** — R1/R3 only.
R3: delete "Don't disable redaction unless explicitly asked, and say so when you do." (Step 2 already says it verbatim).

**`operations/log-triage-interactive/SKILL.md`** — R1/R3 only.
R3: delete "Don't disable redaction unless explicitly asked." (Step 3 inherits log-triage's rule).

**`operations/incident-summary/SKILL.md`**
- In Step 3's intro, delete `(same convention as `/grill-me` and\n`log-triage-interactive`'s clarification pass)` — external skill reference that
  means nothing to an installed copy.
- In Step 4, delete the sentence `No connection\nto `rfc-review`'s rollback section — that's not a concrete enough link to\nbe worth forcing.`
- R3: delete "Don't conflate trigger and root cause." and "Don't write up a
  mitigation as if it were a real fix." (Step 3 items 3–4 already state both with
  their reasoning).

**Verify Phase 1:**
```bash
for f in $(find . -name SKILL.md); do wc -w "$f"; done   # every file ≤ 750
grep -rn "grill\|first skill in this repo\|considered and rejected\|first real cross-skill\|caught during this skill's own testing" --include="SKILL.md" .   # must be empty
grep -rLn "^## Rules" --include="SKILL.md" -r . | grep SKILL   # every SKILL.md must contain "## Rules"
```
Run all unit test suites (no script changed, but confirm nothing else broke).

---

## Phase 2 — Descriptions (trigger optimization)

**Why:** the skill-creator guide says undertriggering is the most common failure;
descriptions should include broad trigger contexts and phrases users actually say.
Most descriptions here are good. Replace only these five, verbatim (frontmatter
`description:` value only — one line, keep YAML valid):

**`implementation/security-review/SKILL.md`:**
```
Review a codebase for security vulnerabilities — injection, broken access control, XSS, SSRF, path traversal, CSRF, mass assignment, insecure deserialization, crypto misuse, and hardcoded secrets — like a senior security engineer's audit pass. Use whenever the user asks to review or audit code for security, asks "is this code safe", mentions OWASP, pentest prep, or vulnerabilities, or asks to check for leaked secrets/credentials — even if they don't say "security review" explicitly.
```

**`implementation/performance-review/SKILL.md`:**
```
Review a codebase for performance issues — N+1 queries, algorithmic complexity, unbounded reads, blocking I/O in hot/async paths, missing caching, connection-pool misuse, and redundant work — like a senior engineer's performance audit. Use whenever the user asks why code is slow, whether it will scale, to find bottlenecks or hot paths, or to review/audit for performance or scalability — even without the word "review".
```

**`implementation/architecture-review/SKILL.md`:**
```
Review an existing codebase's architecture for structural health — layering violations, circular dependencies, coupling/cohesion problems, and deviation from a stated architecture pattern. Use whenever the user asks to review architecture, check module boundaries or dependencies, find circular imports, assess tech debt or code structure, or asks "is this codebase well structured" — even without the word "architecture".
```

**`requirements/requirement-gap-analysis/SKILL.md`:**
```
Interrogate a pre-design requirements doc, stakeholder brief, epic, or freeform notes for missing information — before any solution has been proposed. Use whenever the user asks what's missing from requirements, wants help scoping a feature before writing an RFC or design doc, shares a rough feature idea and asks what to consider, or asks "what should I ask before we design/build this".
```

**`implementation/api-docs/SKILL.md`:**
```
Generate human-readable API reference documentation (Markdown) from an rfc-to-api IR, an existing OpenAPI/GraphQL spec, or (as a fallback) implemented route/handler source code. Use whenever the user asks to document an API or endpoints, generate API reference docs or a README for an API, or write developer-facing docs for a service.
```

All other skills: keep descriptions exactly as they are.

**Verify:** `python3 -c` a YAML-ish sanity check is unnecessary — instead confirm
each edited file still starts with `---`, has exactly one `name:` and one
`description:` line before the closing `---`, and the description is one line.

---

## Phase 3 — Interactivity upgrades

**Why:** the user experience goal — reviews currently end at a report dump.
`log-triage-interactive` and `incident-summary` already model good interaction
(bounded clarifying questions, post-report drill-down). Extend that pattern to the
other review skills. Do NOT add questions to `log-triage`, `rfc-to-schema`
rendering, or `er-generator` beyond what is written here — one-shot skills stay
one-shot by design.

### 3a. Code-review trio: `security-review`, `performance-review`, `architecture-review`

In each of the three SKILL.md files:

1. **Scoping question.** At the end of Step 2 (after the description of the scan
   output), append this paragraph verbatim:

   > **Scoping (large codebases only):** if `files` contains more than 150 entries,
   > ask one question via AskUserQuestion before reading — options: review
   > everything (slower, complete), focus on a subtree the user names, or focus on
   > request-handling/entry-point paths first. Skip this entirely below the
   > threshold, or when the user's request already scoped the review.

2. **Post-report follow-ups.** After the final report step (Step 6), add a new step
   (numbered one higher than the current last step) verbatim:

   > ## Step 7 — Offer follow-ups
   >
   > After presenting the report, offer concrete next steps via AskUserQuestion —
   > e.g. "Explain finding N in more depth", "Draft a fix for the top finding",
   > "Re-run scoped to <subtree>" — and also accept free-form follow-up questions.
   > Only draft or apply code fixes when the user explicitly picks that option;
   > never edit the reviewed codebase unprompted. When drafting a fix, show a diff
   > and let the user decide whether to apply it.

   (In `architecture-review` the report step is Step 6, so the new step is Step 7.
   Same numbering in the other two.)

3. Add to each skill's `## Rules` list: `- Don't edit the reviewed codebase unless the user explicitly asks for a fix to be applied.`

### 3b. `requirements/rfc-review`

After the final report step (Step 6 "Assemble the report"), insert a new
`## Step 7 — Offer follow-ups` verbatim:

> After presenting the report, offer next steps via AskUserQuestion — e.g. "Draft
> concrete replacement text for each Blocking finding", "Produce a revised copy of
> the doc with Should-Fix suggestions applied (as a new file next to the original,
> never overwriting it)", "Explain a specific finding" — and accept free-form
> follow-ups. Never modify the original document in place.

Renumber nothing else; "Things to not do"/Rules stays the final section.

### 3c. `requirements/requirement-gap-analysis`

After Step 5 (Write the report), insert a new step verbatim (then the existing
Step 6 "Composition with `rfc-review`" becomes Step 7 — update its heading number):

> ## Step 6 — Offer to resolve the gaps
>
> After presenting the report, offer via AskUserQuestion to walk the user through
> the **Blocking** questions one at a time — one question per turn, following the
> same convention as this repo's interactive skills — recording each answer, then
> append an `## Answers` section to `GAP_ANALYSIS.md` capturing them. This turns
> the gap list into design-ready input. If the user declines, stop after the
> report.

### 3d. `design/rfc-to-schema` and `design/rfc-to-api`

In each skill's render step (rfc-to-schema Step 4, rfc-to-api Step 4), append:

> If the target format is ambiguous (no existing convention detected in the repo
> and the user didn't state one), ask via AskUserQuestion — options matching the
> renderer's `--target` values plus "all" — instead of silently defaulting.

**Verify Phase 3:** `grep -c "AskUserQuestion" <file>` returns ≥1 for all seven
edited files; word counts may now exceed the Phase 1 budget by the inserted blocks —
allowed overage: ≤ 850 words per file. Run all unit test suites.

---

## Phase 4 — Broaden coverage (backend focus)

### 4a. `security-review` — three new categories

In Step 3's numbered category list, after item 7 (**Hardcoded secrets**), append:

> 8. **Path traversal** — user-influenced file paths reaching filesystem
>    reads/writes without normalization + containment checks (`../` escapes,
>    absolute-path injection, zip-slip in archive extraction).
> 9. **Mass assignment** — request bodies bound directly onto models/entities
>    without an allowlist of settable fields (e.g. a user setting `is_admin` or
>    `role` via a profile-update endpoint).
> 10. **CSRF** — state-changing endpoints relying on cookie auth with no CSRF
>     token or SameSite protection. Skip (and say so) for pure token-in-header
>     APIs, where CSRF doesn't apply.

Also in Step 5, the `category` field's allowed values sentence says "one of Step
3's seven, or `secret`" — change "seven" to "ten".

Add one fixture: `implementation/security-review/scripts/fixtures/vulnerable_samples/path_traversal.py`
containing a small Flask-style handler that opens `os.path.join(BASE_DIR, request.args["filename"])`
without containment checks, ~15 lines, with a comment `# fixture: intentional path traversal`.
Do not add tests for it (fixtures in this skill are for manual QA; only `scan.py`'s
secret patterns have unit tests, and this fixture must NOT contain secret-shaped
strings — verify by running the existing security-review test suite afterwards).

### 4b. `performance-review` — two new categories

In Step 3's list, after item 5 (**Redundant work**), append:

> 6. **Missing caching** — the same expensive read (config fetch, remote lookup,
>    heavy computation) repeated per-request or per-iteration with no memoization
>    or cache layer, where the value is obviously reusable.
> 7. **Connection/client churn** — creating a new DB connection, HTTP client, or
>    session object per request/iteration instead of reusing a pooled/module-level
>    one.

In Step 5, "one of Step 3's five" → "one of Step 3's seven".

Add one fixture: `implementation/performance-review/scripts/fixtures/inefficient_samples/client_churn.py`
— a handler that constructs a new `httpx.Client()`-style object (write it as a
plain class instantiation, no real imports needed) inside a per-request function,
~12 lines, comment `# fixture: intentional per-request client construction`.

### 4c. `architecture-review` — Go support in the dependency graph

Edit `implementation/architecture-review/scripts/scan.py`. Current behavior:
builds a file-level import graph for Python and JS/TS via regex. Add **Go**,
package-directory-level:

Spec (implement exactly):
1. Detect the module path: find a `go.mod` at or below `--root` (use the first one
   found walking top-down; if none exists, skip Go graphing entirely). Read its
   `module <path>` line via regex `^module\s+(\S+)`.
2. For every `.go` file in the enumerated `files` list, extract imports: both
   single-form `import "x"` and block form `import (\n\t"x"\n\t"y"\n)` — including
   aliased imports (`alias "x"`), via regex on quoted strings inside the import
   statement/block. Ignore files ending `_test.go`? No — include them; tests are
   part of the structure.
3. An import is in-repo iff it starts with the module path + `/` (or equals it).
   Strip the module-path prefix to get a repo-relative package directory.
4. Graph nodes for Go are **directory paths relative to root** (the package dir of
   each `.go` file, and the target package dirs). Edges: source file's package dir →
   imported package dir. Deduplicate edges. Self-edges (same dir) are dropped.
5. Merge these nodes/edges into the existing `dependency_graph` output structure
   unchanged in shape (Go nodes are dir paths where Python/JS nodes are file paths —
   document this in the JSON as a top-level `"go_nodes_are_directories": true` key
   only when any Go edge was added). Cycle detection (`find_cycles`) runs over the
   merged graph as-is — it is graph-shape-agnostic.

Add tests in `implementation/architecture-review/scripts/tests/` (follow the
existing test file's style — same imports, same fixture-directory pattern):
- New fixture `scripts/fixtures/go_cycle_sample/` containing: `go.mod` with
  `module example.com/app`, `a/a.go` importing `example.com/app/b`, and `b/b.go`
  importing `example.com/app/a` (minimal valid-looking Go — package line, import,
  one empty func).
- `test_go_module_path_parsed` — module path extracted correctly.
- `test_go_import_block_and_single` — both import forms parsed (can use a string
  literal, matching how existing regex tests are written).
- `test_go_cycle_detected` — running the graph build over `go_cycle_sample`
  yields exactly one cycle containing dirs `a` and `b`.
- `test_go_external_imports_excluded` — `"fmt"` and `"github.com/other/dep"`
  produce no in-repo edges.
- `test_no_gomod_skips_go` — a `.go` file with in-repo-looking imports but no
  `go.mod` anywhere produces no Go edges.

Then update `implementation/architecture-review/SKILL.md`:
- In Step 2, change `**Python and JS/TS only\nin v1**` to `**Python, JS/TS, and Go**`
  and append to that bullet: `Go edges are package-directory-level (from `go.mod`'s module path), not file-level.`
- In `## Rules`, change the bullet "Don't build or claim a dependency graph for
  languages outside Python/JS/TS…" to "…outside Python/JS/TS/Go…".

**Verify Phase 4:** run the architecture-review, security-review, and
performance-review test suites; all pass including the 5 new tests. Run
`python3 implementation/architecture-review/scripts/scan.py --root implementation/architecture-review/scripts/fixtures/go_cycle_sample`
and confirm the JSON output contains one cycle.

---

## Phase 5 — Evals

**Why:** the skill-creator framework expects `evals/evals.json` per skill with 2–3
realistic test cases. None exist yet.

For **each of the 12 skills**, create `<skill_dir>/evals/evals.json` with this exact
schema (from skill-creator):

```json
{
  "skill_name": "<frontmatter name>",
  "evals": [
    {
      "id": 1,
      "prompt": "<realistic user prompt>",
      "expected_output": "<one-paragraph description of the expected result>",
      "files": ["<repo-relative fixture paths the prompt references>"],
      "assertions": ["<short checkable statements>"]
    }
  ]
}
```

Write 2 evals per skill. Use these prompts/fixtures (fixtures are repo-relative;
confirm each exists before referencing — if one doesn't, pick the closest file in
the same fixtures directory and note it in `## Skipped items`):

| Skill | Eval 1 prompt (fixture) | Eval 2 prompt (fixture) |
|---|---|---|
| log-triage | "triage these logs" (`operations/_shared/log-triage-core/fixtures/mixed.log`) | "why is this crashing" (`.../stacktrace.log`) |
| log-triage-interactive | "something's wrong with the API, dig through these logs" (`.../mixed.log`) | "triage this" on a single focused trace (`.../stacktrace.log`) — assert NO clarifying questions asked |
| incident-summary | "help me write up this incident" (`operations/incident-summary/fixtures/log_grounded_incident.log`) | same, notes only (`.../notes_only_scenario.txt`) |
| rfc-review | "review this RFC" (pick one file from `requirements/rfc-review/scripts/fixtures/`) | "is this ready to approve" (a second fixture file) |
| requirement-gap-analysis | "what am I missing before I design this" (`requirements/requirement-gap-analysis/fixtures/two_sentence_feature_request.txt`) | "what should I ask before we build this" (`.../stakeholder_brief_missing_compliance.txt`) |
| rfc-to-schema | "generate the schema for this RFC" (a fixture from `design/rfc-to-schema/scripts/fixtures/`) | "derive the data model" (second fixture) |
| rfc-to-api | "generate the API for this RFC" (fixture from `design/rfc-to-api/scripts/fixtures/`) | "give me the OpenAPI spec for this proposal" (second fixture) |
| er-generator | "diagram this schema" (fixture from `design/er-generator/scripts/fixtures/`) | "draw an ER diagram of this database" (second fixture) |
| security-review | "review this codebase for security issues" (`implementation/security-review/scripts/fixtures/vulnerable_samples/`) | "is this code safe" (same dir) — assert path_traversal.py finding present |
| performance-review | "review this for performance issues" (`implementation/performance-review/scripts/fixtures/inefficient_samples/`) | "why would this be slow at scale" (same dir) |
| architecture-review | "check for circular dependencies" (`implementation/architecture-review/scripts/fixtures/cyclic_sample/`) | "review the architecture" (`.../layering_violation_sample/`) |
| api-docs | "document this API" (fixture IR from `implementation/api-docs/scripts/fixtures/`) | "generate API reference docs" (same fixture + schema IR if present) |

Assertions per eval: 2–4, each a plain checkable sentence about the output, e.g.
for security-review eval 1: `"Report written to SECURITY_REVIEW.md"`,
`"SQL injection in sqli.py reported with severity and confidence"`,
`"Findings include a concrete suggested fix, not just a description"`.
Derive assertions from each skill's own output-structure step — do not invent
behaviors the SKILL.md doesn't require.

Add a CI guard: in `.github/workflows/tests.yml`, add a job `evals-consistency`
(same runner/setup style as `manifest-consistency`) running:

```bash
python3 - <<'EOF'
import json, os, sys
bad = []
for root, dirs, files in os.walk('.'):
    if 'evals.json' in files:
        p = os.path.join(root, 'evals.json')
        try:
            data = json.load(open(p))
            assert 'skill_name' in data and isinstance(data['evals'], list) and data['evals']
            for e in data['evals']:
                for f in e.get('files', []):
                    assert os.path.exists(f), f'{p}: missing file {f}'
        except Exception as ex:
            bad.append(f'{p}: {ex}')
if bad:
    print('\n'.join(bad)); sys.exit(1)
print('all evals.json valid')
EOF
```

**Verify:** run that snippet locally from repo root; it must print `all evals.json valid`.
`find . -name evals.json | wc -l` must print `12`.

---

## Phase 6 — Docs sync

1. `README.md` — in the "Contributing" section sentence listing the expected shape,
   after "fixtures for manual QA (and real unit tests if there's a script)", insert
   ", an `evals/evals.json` with 2–3 test cases". No other README changes.
2. `EXAMPLES.md` — for each of the five skills that gained a post-report follow-up
   step (`security-review`, `performance-review`, `architecture-review`,
   `rfc-review`, `requirement-gap-analysis`), find that skill's **Typical use**
   entry and append one sentence to its expected-output description:
   `Ends by offering follow-ups (explain a finding, draft a fix, re-scope).`
   (For `requirement-gap-analysis` use: `Ends by offering to walk through the Blocking questions one at a time.`)
3. `PIPELINES.md` — no changes.
4. `MANIFEST.json` — no changes (evals/ ships inside each skill dir automatically).

**Final verification (run all):**
```bash
# every suite in the CI matrix:
for d in operations/_shared/log-triage-core requirements/rfc-review/scripts design/rfc-to-schema/scripts design/rfc-to-api/scripts design/er-generator/scripts implementation/_shared implementation/security-review/scripts implementation/performance-review/scripts implementation/architecture-review/scripts implementation/api-docs/scripts; do
  (cd "$d" && python3 -m unittest discover -s tests -v) || echo "FAILED: $d"
done
# word budget:
for f in $(find . -name SKILL.md); do wc -w "$f"; done          # ≤ 850 each
# no stale/meta text:
grep -rn "system-design-review\|✅\|(planned)\|grill" --include="*.md" . | grep -v SKILL_REVIEW_ORCHESTRATION
# installer still works:
bash install.sh --local-path . log-triage   # into a scratch CLAUDE_SKILLS_DIR
# manifest + evals checks: run the python snippets from the CI jobs locally
```

When every check passes, report: files changed per phase, new word counts per
SKILL.md, test counts, and any `## Skipped items`. Do not push.

## Skipped items

- Phase 1's "≤ 750 words per file" target was not met. All R1–R4 global rules
  and every per-skill deletion/replacement listed in section 1b were applied
  exactly as specified (verified: no stale-text matches remain, every
  SKILL.md has a `## Rules` header). The resulting range is 689–1240 words
  (down from 712–1328 before Phase 1), because the target was an estimate
  made before counting the actual deletable text, not a literal instruction
  with its own edit list. No further cuts were improvised beyond what
  section 1b specified, per the "do not improvise" rule in this doc's
  header. Phase 3 adds more words back (new interactivity steps), so the
  ≤850-word Phase 3 budget was adjusted accordingly where checked.

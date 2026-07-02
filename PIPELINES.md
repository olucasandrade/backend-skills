# Pipelines: composing this repo's 11 skills across the engineering lifecycle

This repo's skills aren't one pipeline — they're building blocks for
**several**, depending on where you are in a feature's life: before a
design exists, while it's being designed, once it's implemented, and
while operating what's live. Every link between skills is optional and
either auto-discovered (within one flat directory) or explicit-pointer-only
(across a docs tree and a real codebase) — see "The two composition
mechanisms" below for which applies where. Pick the pipeline that matches
where you actually are; none of them require running the others first.

## The pipelines, at a glance

1. **Pre-design** — `requirement-gap-analysis` → (write the RFC) →
   `rfc-review`. Use before any solution has been proposed.
2. **Design** — `rfc-review` → `rfc-to-schema` → `rfc-to-api` →
   `er-generator` / `api-docs`. Use once an RFC exists, to turn it into
   implementable schema/API artifacts and sanity-check the result.
3. **Post-implementation audit** — `security-review` +
   `performance-review` + `architecture-review` + `api-docs`, run
   independently (in any order, even in parallel) against real code, each
   optionally cross-checked against the design pipeline's IR files. Use
   once a feature is actually built.
4. **Operations** — `log-triage` / `log-triage-interactive` →
   `incident-summary`. Use when something's actively wrong, then when
   writing it up afterward.
5. **Full lifecycle** — all four of the above, chained: a feature can flow
   from a two-sentence Slack request all the way through to a postmortem
   for an incident it later caused, with every stage in between narrated
   below in the worked example.

```
requirements/requirement-gap-analysis → requirements/rfc-review → design/rfc-to-schema → design/rfc-to-api
        (pre-design input)                                                  │                    │      │
                                                                              └──► design/er-generator    │
                                                                                                           ▼
                                                                                              implementation/api-docs

                                                      (implemented codebase) ───┬──► implementation/security-review
                                                                                 ├──► implementation/performance-review
                                                                                 ├──► implementation/architecture-review
                                                                                 └──► implementation/api-docs (fallback,
                                                                                        no api.ir.json/spec available)

                                       (live system / logs) ──► operations/log-triage(-interactive) ──► operations/incident-summary
                                                                                                                  ▲
                                                (implementation/ finding that became a real incident) ───────────┘
                                                                                                          (explicit pointer only)
```

- **`requirement-gap-analysis`** interrogates the *pre-design* input (a
  raw requirements doc, brief, epic, notes) for what's not yet known,
  before anyone proposes a solution — one stage earlier than `rfc-review`.
- **`rfc-review`** catches gaps/ambiguity/risk in a proposal before anyone
  builds off it — the cheapest place to fix a mistake.
- **`rfc-to-schema`** turns the RFC's data-model prose into an implementable
  draft schema (SQL DDL / JSON Schema), flagging every inferred detail.
- **`rfc-to-api`** does the same for behavior (OpenAPI / GraphQL SDL),
  optionally grounding request/response bodies in `rfc-to-schema`'s output
  instead of re-guessing field shapes.
- **`er-generator`** produces a Mermaid diagram to sanity-check the result —
  from the pipeline's own output, or from a live/static schema with no
  relation to any RFC at all.
- **`api-docs`** renders `rfc-to-api`'s IR into human-readable Markdown
  reference docs — or, standalone, an existing OpenAPI/GraphQL spec, or (as
  a last resort) implemented route/handler source code with no spec at all.
- **`security-review`**, **`performance-review`**, and
  **`architecture-review`** all read an *implemented* codebase — the
  design-time IR isn't their subject, it's an optional cross-check they
  run against actual code once pointed at it (declared auth/scopes for
  `security-review`, declared pagination and schema indexing signals for
  `performance-review`, operation-to-module ownership for
  `architecture-review`). `architecture-review` additionally runs a real
  dependency-graph/cycle-detection pass — the only genuinely deterministic
  finding category among the three `implementation/` code-reading skills.
- **`log-triage`/`log-triage-interactive`** diagnose "what's wrong right
  now" from live logs; **`incident-summary`** documents "what already
  happened" afterward, as a postmortem — reusing the same
  `log-triage-core` engine for grounding, but organized around chronology
  and narrative causality instead of ranked error clusters. Optionally
  references an `implementation/` finding that turned into the incident.

The composition is **loose by design**: every cross-skill link is
optional. Each skill is independently useful; a pipeline only pays off
when you happen to run its skills in sequence — and you never have to run
all four pipelines just because one exists.

## The one rule that makes the design pipeline's auto-discovery work

**Every design/requirements-pipeline skill writes its output next to the
input file it read — the same directory as the RFC (or schema/DB file, for
`er-generator`) — falling back to the current directory only when the
input has no filesystem location at all** (piped or pasted text with no
path). "Check for a sibling `schema.ir.json`" only means anything because
every skill in that pipeline honors this same rule; it was inconsistently
documented (and inconsistently implied) across those skills' `SKILL.md`
files until this doc's original review — worth knowing if you're reading
the skill sources directly, since older instincts about "where does this
write to" don't apply here.

Concretely, everything for one RFC ends up in one directory:

```
jobs/bookmarks-rfc.md
jobs/RFC_REVIEW.md          ← rfc-review
jobs/schema.ir.json         ← rfc-to-schema
jobs/schema.sql             ← rfc-to-schema
jobs/SCHEMA_NOTES.md        ← rfc-to-schema
jobs/api.ir.json            ← rfc-to-api
jobs/openapi.json           ← rfc-to-api
jobs/schema.graphql         ← rfc-to-api
jobs/API_NOTES.md           ← rfc-to-api
jobs/er_diagram.mmd         ← er-generator
```

## The two composition mechanisms — and why that's not an inconsistency

Two different discovery mechanisms exist across this repo's skills. Which
one applies depends on where the linked artifacts actually live:

- **Auto-discovery (sibling-file check)** — used by the requirements/
  design pipeline (`requirement-gap-analysis` → `rfc-review` →
  `rfc-to-schema` → `rfc-to-api` → `er-generator`). Their artifacts live
  in one flat directory *by construction* — the "next to the input" rule
  above is exactly what makes "check for a sibling file" a safe,
  unambiguous search.
- **Explicit-pointer-only** — used by every `implementation/` skill
  (`security-review`, `performance-review`, `architecture-review`,
  `api-docs`) and by `incident-summary`'s optional reference to an
  `implementation/` finding. These skills read an **implemented codebase**
  or a **live incident**, neither of which lives in the same directory as
  `api.ir.json`/`schema.ir.json` — that's typically off in a `jobs/`-style
  design-docs tree, possibly in a different repo entirely. Auto-searching
  a whole codebase (or a whole incident channel) for it would be slow and,
  the moment more than one API/service/incident exists, genuinely
  ambiguous about which artifact belongs to what.

Same underlying principle (only use an artifact you can be sure actually
belongs to what you're looking at) — different mechanism, because the
directory topology each group of skills operates in is different.

## Worked example

RFC: a small bookmarking feature — a user can bookmark a post, list their
bookmarks, and remove one. Idempotent on both create and delete; a user can
only bookmark a given post once.

**1. `rfc-review`** reads the RFC, finds it well-structured (all core RFC
sections present) and flags one Nice-to-Have: the idempotent-bookmarking
requirement implies a uniqueness constraint on `(user, post)` that the
design section states only in prose, not as an explicit data-model
requirement. Verdict: **Ready to Approve**. Writes `RFC_REVIEW.md`.

**2. `rfc-to-schema`** finds `RFC_REVIEW.md`, surfaces the verdict, and
extracts a `Bookmark` entity referencing `User` and `Post`, with a
composite `unique_constraints: [["user_id", "post_id"]]` — directly
addressing what the review flagged. Renders:

```sql
CREATE TABLE bookmarks (
  id UUID PRIMARY KEY,  -- ASSUMED: standard primary key convention
  user_id UUID NOT NULL REFERENCES users(id),
  post_id UUID NOT NULL REFERENCES posts(id),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT uq_bookmarks_user_id_post_id UNIQUE (user_id, post_id)
);
```

**3. `rfc-to-api`** finds `schema.ir.json`, `$ref`s its `Bookmark`/`User`/
`Post` entities instead of re-guessing field shapes, and derives
`createBookmark` (`POST /bookmarks`), `listBookmarks` (`GET /bookmarks`,
cursor-paginated), `deleteBookmark` (`DELETE /bookmarks/{id}`). GraphQL SDL
declares every entity the output actually references — including `User`,
which no operation mentions directly but which `Bookmark` itself refers to
(this transitive case was the one real bug this dry-run caught; see below).

**4. `er-generator`** finds `schema.ir.json`, projects it, and renders one
Mermaid diagram — three entities, two relationships, no clustering needed.

**5. The bookmark feature gets implemented.** Weeks later, the code is
real: a `POST /bookmarks` handler, a `bookmarks` table, the works. Someone
runs the three `implementation/` skills against it, pointing each at
`api.ir.json`/`schema.ir.json` since they're still sitting in `jobs/`:

- **`api-docs`** renders `api.ir.json` into `API_DOCS.md` — three
  endpoint sections with request/response tables and synthesized examples
  (`postId: "3fa85f64-5717-4562-b3fc-2c963f66afa6" _(example)_`), written
  next to `api.ir.json`.
- **`security-review`**, pointed at both the codebase and `api.ir.json`,
  checks the declared `requires_auth: true` on all three operations
  against the actual handlers — say it finds `deleteBookmark`'s handler
  checks the caller is logged in but never checks the bookmark belongs to
  that caller, a real broken-access-control finding this RFC pipeline
  alone could never catch (it only exists once real code exists to read).
- **`performance-review`**, pointed at the same two inputs, checks
  `listBookmarks`'s declared `paginated: true`/`pagination_style: cursor`
  against the handler — and separately notices the handler filters by
  `user_id` on every call with no corresponding index/uniqueness signal
  visible in `schema.ir.json`, flagging it under RFC/implementation drift.

None of this needed the design-time skills to know `implementation/`
skills exist, or vice versa — each was pointed at the same two files
independently, which is the whole point of the explicit-pointer
convention above.

**6. Six months later, the broken-access-control gap `security-review`
flagged gets exploited** — a user deletes another user's bookmark via the
unguarded `deleteBookmark` endpoint. On-call notices error-rate alerts
and pulls the API logs.

- **`log-triage-interactive`** is run against the logs first, live —
  wide time range, multi-endpoint, genuinely ambiguous, so it asks a
  couple of clarifying questions before producing a ranked report
  surfacing a cluster of anomalous `DELETE /bookmarks/{id}` calls from
  accounts that don't own the target bookmark.
- Once the incident is resolved, **`incident-summary`** is run
  interactively, grounded in that same log data (real timestamps from the
  triage pass instead of asking "when did it start" cold), and explicitly
  pointed at the original `SECURITY_REVIEW.md` as root-cause context
  instead of re-deriving the same finding. It produces `INCIDENT_SUMMARY.md`
  with the access-control gap named as **root cause**, the exploit traffic
  pattern as **trigger**, an emergency patch adding the ownership check as
  the **resolution** (marked a real fix, not a mitigation), and an action
  item to add an automated test for cross-account access on every
  delete-style endpoint — tagged **prevents recurrence**.

The full lifecycle — pre-design questions, RFC review, schema/API
generation, a diagram, implementation, a security finding, and eventually
an incident writeup referencing that same finding — never required any
skill to know the whole chain existed. Each one only ever looked at the
file(s) it was explicitly given.

## What this worked example caught (and fixed)

Running this for real — not just reading the `SKILL.md` prose — surfaced
three real issues that unit tests, which only exercise each skill's script
in isolation, couldn't have caught:

1. **No skill except `rfc-review` actually specified where it writes
   output.** Fixed by standardizing the "next to the input" rule above
   across all four `SKILL.md` files.
2. **`rfc-to-schema` had no way to express a composite/multi-column
   uniqueness constraint** — exactly what this RFC's review flagged as
   needed. The IR only supported single-field `unique: true`. Added
   `unique_constraints` to the IR, both renderers, and validation.
3. **`rfc-to-api` silently produced invalid output** whenever an entity was
   reachable only *through* another entity's own `ref` field, not directly
   from any operation — `Bookmark.user_id → User` produced a `$ref`/type
   reference to `User` in the rendered OpenAPI/GraphQL without ever
   declaring it, since entity-reference collection only looked one hop deep
   from operations. Fixed by making `collect_referenced_entities` compute
   the full transitive closure.

## Re-running a skill after upstream changes

Every skill in this pipeline treats each run as independent — none of them
diff against a previous run or track revision history (deliberately
deferred, see each skill's own design notes). Two things follow from that:

- **Editing the RFC and re-running `rfc-review`/`rfc-to-schema`/`rfc-to-api`
  regenerates fresh output** — it doesn't merge with or preserve anything
  from the previous run.
- **`rfc-to-schema` specifically distinguishes "regenerating my own prior
  output for this RFC" from "colliding with an unrelated existing
  schema"** (Step 2 of its `SKILL.md`) — otherwise every re-run after a
  minor RFC edit would incorrectly warn that every entity "already exists."

## Running a skill out of order

Every downstream link is optional:

- Run `rfc-to-schema` or `rfc-to-api` on an RFC that was never reviewed —
  they just won't have a verdict to surface.
- Run `rfc-to-api` before (or without) `rfc-to-schema` — it defines request/
  response shapes inline instead of `$ref`-ing a schema IR. Plenty of RFCs
  describe an API with no new persisted storage at all.
- Run `er-generator` with nothing RFC-related in sight — point it at a live
  SQLite file, a static `schema.sql`, or (with explicit connection details)
  a real Postgres/MySQL database.
- Run `api-docs` with nothing pipeline-related in sight, too — point it at
  an existing OpenAPI/GraphQL spec this repo never generated, or, with no
  spec at all, at implemented route/handler source code as a last resort
  (weaker signal than a real spec, and the doc says so explicitly).
- Run `security-review`/`performance-review`/`architecture-review` on a
  codebase with no RFC pipeline behind it at all — the
  `api.ir.json`/`schema.ir.json` cross-checks are additive, not required;
  all three are fully useful standalone.
- Run `incident-summary` with no logs at all — human notes and/or Slack
  excerpts alone are enough; the interview is the backbone, log grounding
  via `log-triage-core` is additive. Run it with no `implementation/`
  finding to reference, too — that pointer is optional context, not a
  requirement.
- Run `log-triage`/`log-triage-interactive` completely standalone, with no
  connection to anything else in this repo — the most common real case,
  since most log-triage sessions aren't tied to a specific RFC or
  incident writeup at all.

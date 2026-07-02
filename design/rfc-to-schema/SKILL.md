---
name: rfc-to-schema
description: Turn an RFC/design doc into a concrete data schema (SQL DDL, JSON Schema, or a matched target detected from the repo) via a neutral intermediate representation. Use when the user asks to derive a database schema, data model, or entity definitions from an RFC or proposal.
---

# rfc-to-schema

Generates a concrete, implementable schema from an RFC's prose description
of its data model. This is a **generative** skill (unlike the `requirements/`
review skills): it produces new artifacts, not a critique of existing ones.

Two layers, deliberately separated:
1. **Extraction (you, the LLM)** — read the RFC, infer entities/fields/types/
   relationships into a neutral intermediate representation (IR). This is
   judgment work; it cannot be scripted.
2. **Rendering (the bundled script)** — mechanically, deterministically turn
   that IR into concrete target syntax (SQL DDL, JSON Schema). This is
   reproducible and is exactly what's unit-tested.

**Dependencies:** `scripts/render_schema.py` (stdlib-only Python 3), which
imports `design/_shared/naming.py` (shared with `rfc-to-api` — extracted
once that second skill needed the identical pluralization logic). If you
copy this skill folder standalone, copy both `scripts/` and `../_shared/`.

## Step 1 — Resolve the input

Accept a file path or pasted RFC text (same contract as `rfc-review`: no
URL fetching for external doc platforms — ask the user to paste/export
instead).

**Check for a sibling `RFC_REVIEW.md`** (from the `rfc-review` skill) next
to the input. If found: surface its overall verdict and, specifically, any
"downstream readiness" finding. If the verdict was "Not Ready" or downstream
readiness was flagged, say so clearly before proceeding — but proceed anyway
if the user wants to (a draft schema is often a legitimate way to help
finish an unclear RFC, not just a reward for a finished one). This is
informational, not a hard gate.

## Step 2 — Check for an existing schema in the repo

If run inside a real codebase, look for what already exists: migrations
directory, `prisma/schema.prisma`, ORM model files, an existing
`schema.ir.json` from a prior run, etc.

**Regenerating vs. a real collision**: if the existing `schema.ir.json`
found next to the input looks like *this same skill's own prior output for
this same RFC* (check: does its recorded source — e.g. a note in the
sibling `SCHEMA_NOTES.md`, or the RFC's file path/title — match the RFC
you're reading now?), treat this as regenerating an updated draft, not a
collision: overwrite/update, no collision warnings, just a one-line note
("updating previous draft for this RFC"). Only fall through to genuine
collision detection (below) when the existing artifact doesn't match this
RFC's identity, or there's no way to tell (e.g. piped/pasted RFC text with
no stable file identity) — in that ambiguous case, treat it as a possible
real collision rather than silently assuming it's your own prior output.

This informs two things:

- **Target format** (Step 4): match whatever the repo already uses.
- **Existing-entity collisions** (Step 3): if a proposed entity name matches
  something that already exists, treat this as a modification, not a fresh
  creation.

## Step 3 — Extract the IR

Read the RFC and produce `schema.ir.json`. The IR is a neutral,
renderer-agnostic representation — no target-specific syntax (no
`VARCHAR(255)`, no Prisma types) — using abstract types: `uuid`, `string`
(with optional `max_length`), `text`, `int`, `bigint`, `float`, `decimal`,
`bool`, `datetime`, `date`, `json`, `enum` (with `values`), `object` (with
nested `fields`), `array` (with `item_type`, and nested `fields` if the item
type is `object`), and `ref` (a relationship to another entity, with
`cardinality`). Many-to-many relationships are top-level `relationships`
entries (they need a join table, which isn't a single field). See the full
IR spec documented at the top of `scripts/render_schema.py`.

**Handling gaps in the RFC** — RFCs are usually light on DB-level detail.
For each field/decision:
- If the RFC states it, use it, `assumed: false`.
- If the RFC doesn't state it but a sensible default exists (e.g., an
  unmentioned primary key, a standard `created_at` audit field), fill it in
  and set `assumed: true` with a short `assumed_reason`. Never let an
  inferred detail look as certain as a stated one.
- If the *entities themselves* can't be identified at all (the RFC doesn't
  actually describe what's being stored), stop and say so rather than
  inventing a data model out of nothing.

**Existing-schema collisions** (only when Step 2 found something): if a
proposed entity matches an existing one, generate the IR as a description of
the *change* (note what's added/altered) rather than a fresh definition, and
flag it clearly. If there's a naming collision with no clear relationship to
what the RFC describes, flag it as a blocking-style warning instead of
silently producing a conflicting definition.

## Step 4 — Render

```bash
python3 <skill_dir>/scripts/render_schema.py --ir-file schema.ir.json --target sql|json-schema|all
```

The script validates the IR first (duplicate names, dangling refs, malformed
enums/arrays) — if invalid, it reports errors and renders nothing; fix the
IR, don't hand-patch broken output.

v1 ships two renderers:
- **SQL DDL** (Postgres-flavored) — relational; nested `object`/`array<object>`
  fields are flattened to `JSONB` since they can't be represented as native
  columns; `enum` fields become `TEXT` with a `CHECK` constraint (for
  portability, not a native Postgres `ENUM` type); many-to-many
  relationships become join tables.
- **JSON Schema** — preserves nesting natively; `ref` fields become
  `$ref: "#/$defs/<Entity>"`.

If Step 2 detected a specific existing convention (e.g., a `prisma/`
directory), say so and note that a matching renderer isn't shipped yet in
v1 — offer SQL DDL or JSON Schema as the closest available output rather
than silently defaulting to one without explaining why.

Assumed fields carry their flag into the rendered output too: a trailing
`-- ASSUMED: <reason>` comment in SQL, an `"x-assumed": true` /
`"x-assumed-reason"` pair in JSON Schema.

## Step 5 — Assemble the output

**Location convention (applies to every file below, and to every other
skill in this pipeline): write next to the input file — same directory as
the RFC that was read. Fall back to cwd only when the input has no
filesystem location at all (piped/pasted text with no file path).** This is
what makes `rfc-to-api`/`er-generator`'s "check for a sibling
`schema.ir.json`" actually work — it only means something if this skill
writes to a predictable, consistent place every time.

Write, and also show inline:
- `schema.ir.json` — the neutral IR. This is a real, documented artifact:
  `er-generator` and `rfc-to-api` (this repo's other `design/` skills) can
  optionally consume it later, but nothing here hard-depends on that.
- One rendered file per target produced (`schema.sql`, `schema.json`, or a
  path matching a detected existing convention).
- `SCHEMA_NOTES.md` — human-facing summary: which entities/fields came
  directly from the RFC vs. were assumed (and why), any existing-schema
  conflicts or modifications detected, what render targets were produced
  and why (auto-detected vs. asked), and the `rfc-review` verdict if one was
  found.

Every run is independent — this skill doesn't track prior runs or diff
against a previous `schema.ir.json` version in v1.

## Composition with other skills

- **`rfc-review`**: optional, informational input (Step 1). Never required.
- **`er-generator`**: a general-purpose diagram skill that can
  visualize either a live database *or* an IR produced here — `rfc-to-schema`
  owns "derive an implementable model," `er-generator` owns "diagram any
  model." No dependency in this direction; `er-generator` depends on this
  skill's IR format, not the other way around.
- **`rfc-to-api`**: can optionally consume `schema.ir.json` if
  present next to its input, to ground request/response bodies in real
  entities — but doesn't require it (plenty of APIs don't need new storage).

## Things to not do

- Don't bake target-specific syntax into the IR — it must stay renderer-agnostic.
- Don't let an assumed/inferred detail look as certain as something the RFC actually stated — always flag it, in both the IR and every rendered output.
- Don't silently generate a schema that conflicts with an existing entity of the same name — flag it.
- Don't hand-patch renderer output for a one-off case instead of fixing the IR or the renderer script; the renderer's whole value is being deterministic and tested.
- Don't attempt to fetch external doc-platform URLs.

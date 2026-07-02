---
name: er-generator
description: Generate an entity-relationship diagram (Mermaid erDiagram) from rfc-to-schema's IR, a live SQLite file, static SQL/migration files, or a Postgres/MySQL database (only with explicit connection details). Use when the user asks to diagram, visualize, or draw an ER diagram of a schema or database — not tied to any RFC.
---

# er-generator

Generates a Mermaid `erDiagram` from whatever schema source is available.
Unlike `rfc-to-schema`/`rfc-to-api`, this skill is **not tied to RFCs at
all** — it's a general-purpose diagramming tool that happens to be able to
consume `rfc-to-schema`'s output as one of several possible sources.

**Architecture note**, since this differs from the other two `design/`
skills: there's no prose to interpret here — every source (a schema IR, a
live SQLite file, static SQL, Postgres/MySQL introspection output) is
already structured. So this skill is **script-heavy, LLM-thin**: almost
everything (source parsing, clustering, rendering) is deterministic and
unit-tested in `scripts/render_er.py`. Your job is mostly orchestration —
picking a source, resolving ambiguity, running the right command safely —
not extraction judgment.

**Requires:** `scripts/render_er.py` (stdlib-only Python 3, including
`sqlite3` for live SQLite introspection). No shared `design/_shared/`
dependency. `install.sh` places this automatically.

## Step 1 — Resolve the source (auto-detect priority)

Never guess silently between sources — check in this order, use the first
that applies, and say which one you used. **Location convention**: "found
nearby" means the same directory as whatever input the user pointed at (an
RFC, a schema file, cwd if nothing else) — the same next-to-the-input rule
`rfc-to-schema`/`rfc-to-api` use for their own outputs, since this skill has
no RFC of its own to anchor to.

1. **`schema.ir.json`** (from `rfc-to-schema`) — if found next to the given input (or in cwd if no input path was given), use it. Most reliable, already-structured.
2. **A SQLite file** — if one is named, or trivially found (a single `.db`/`.sqlite` next to the given input or in cwd), introspect it live via stdlib `sqlite3`. This is genuinely "live" with zero extra tooling.
3. **Static schema/migration files** — a `migrations/` directory, an existing `schema.sql`, etc. Parsed as text, not connected to.
4. **A live Postgres/MySQL connection** — **only when the user explicitly provides connection details.** Never attempt this from an ambiguous "diagram my database" request — it could hit a real production database, prompt for credentials, or hang on an unreachable host. When explicit, shell out to `psql`/`mysql` (a CLI dependency, not a Python package — same category as this repo's other `Bash`-based tool use) running a query that outputs pipe-delimited rows in the exact shape `render_er.py`'s `parse_introspection_rows()` expects (see that function's docstring for the required column order); the query itself is environment-specific (schema name, connection string) and is your job to construct, not the script's.

If nothing is found, ask what to diagram.

## Step 2 — Get to the lightweight ER representation

Every source projects down into the same small internal shape (see
`render_er.py`'s `ER_SPEC` docstring — entities with name/type/pk/nullable
fields, plus a flat relationships list). This is **deliberately not the
same shape as `rfc-to-schema`'s IR** — that IR carries RFC-extraction
concepts (`assumed`, `max_length`, `default`) meaningless for something read
directly off a live database. Use the matching helper:

- `project_schema_ir(schema_ir)` — from a loaded `schema.ir.json`.
- `parse_sqlite_file(path)` — direct stdlib introspection.
- `parse_create_table_sql(sql_text)` — returns `(er, report)`; **check
  `report["skipped"]`** — the parser only handles a documented `CREATE
  TABLE` subset (matching what `rfc-to-schema`'s own SQL renderer produces,
  plus common hand-written variations) and reports, rather than silently
  guesses at, anything outside it. Surface skipped tables/columns to the
  user rather than presenting a diagram that quietly dropped information.
- `parse_introspection_rows(raw_text)` — parses the CLI output you fetched in Step 1.4.

## Step 3 — Render

```bash
python3 <skill_dir>/scripts/render_er.py --er-file er.json [--max-entities 40]
```

(Or call `render_mermaid_diagrams(er, max_entities)` directly if you already
have the ER dict in hand from Step 2 — no need to round-trip through a
file.)

**Type/cardinality mapping**: abstract scalar types map to simple Mermaid
type names; `enum` renders as `string` with a comment listing allowed
values (Mermaid has no enum concept); `object`/`array` render as a single
`json`/`array`-typed field — never fake-flattened into pretend columns, since
that would misrepresent the schema; `ref` (foreign key) fields render typed
as `uuid` with an `FK` marker (this repo's PK convention default — an
approximation when the real referenced-PK type differs, not a guarantee).
Relationships use crow's-foot notation: required FK (`nullable: false`) →
`||--o{` (one required to zero-or-many); nullable FK → `|o--o{`; many-to-many
(from a schema IR's join-table relationship) → `}o--o{`.

**Scale handling**: `build_diagrams()` computes connected components first
(entities with no relationship path between them obviously belong in
separate diagrams), then applies greedy BFS clustering — seed from the
highest-degree node, grow to `--max-entities`, repeat — to any single
component still over the cap. This is a **disclosed heuristic**, not real
community detection; say so when it triggers, don't present the split as an
authoritative domain boundary. Check the returned `disclosure` dict
(`clustered`, `diagram_count`, `total_entities`) and mention it in your
response whenever `clustered` is true.

**Cycles/self-references**: rendered as-is, no special handling — Mermaid
represents them fine syntactically.

## Step 4 — Assemble the output

Write next to the source input (cwd fallback if it has no filesystem
location — same convention as every other skill in this pipeline). One
`.mmd` file per diagram (`er_diagram.mmd`, or
`er_diagram_1.mmd`/`_2.mmd`/... if clustering split it), and show each
inline wrapped in a ` ```mermaid ` fence so it renders directly if the
surface supports it. Follow with a short disclosure note (not a full
separate `_NOTES.md` file — there's much less to track here than the
generative skills' assumption-flagging): which source was used, entity/
relationship counts, whether clustering happened, and any `report["skipped"]`
entries from static SQL parsing.

## Composition with other skills

- **`rfc-to-schema`**: one of several possible sources (Step 1.1), consumed via `project_schema_ir()`. No dependency in the other direction.
- **`rfc-to-api`**: no relationship — this skill diagrams data shape, not API operations.
- Not tied to `rfc-review` or any RFC at all — this is a general-purpose diagramming tool.

## Rules

- Don't attempt a live Postgres/MySQL connection without the user explicitly providing connection details.
- Don't silently mis-parse static SQL outside the documented `CREATE TABLE` subset — report what was skipped and why.
- Don't fake-flatten `object`/`array` fields into pretend relational columns.
- Don't present heuristic clustering as an authoritative domain split.
- Don't render a diagram whose relationship lines reference entities that aren't actually declared in it (verify with `validate_mermaid()` if you touch the renderer).

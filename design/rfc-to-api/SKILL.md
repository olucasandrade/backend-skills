---
name: rfc-to-api
description: Turn an RFC/design doc's described behavior into a concrete API design (OpenAPI REST spec and/or GraphQL SDL) via a protocol-neutral intermediate representation. Optionally grounds request/response bodies in entities from rfc-to-schema's IR. Use when the user asks to derive an API design, endpoints, or a GraphQL schema from an RFC or proposal.
---

# rfc-to-api

Generates a concrete, implementable API design from an RFC's description of
system behavior. Second generative skill in this repo, following the same
split as `rfc-to-schema`:

1. **Extraction (you, the LLM)** — read the RFC, infer operations (what can
   be called, with what inputs, what it returns, what can go wrong) into a
   protocol-neutral intermediate representation (IR). Judgment work.
2. **Rendering (the bundled script)** — mechanically, deterministically turn
   that IR into OpenAPI 3.1 (as JSON — no YAML; this repo stays stdlib-only)
   and/or GraphQL SDL. Reproducible, unit-tested.

**Requires:** `scripts/render_api.py` and `design/_shared/naming.py`
(stdlib-only Python 3). `install.sh` places these automatically.

## Step 1 — Resolve the input

Same contract as `rfc-review`/`rfc-to-schema`: file path or pasted text
only, no URL fetching for external doc platforms.

**Location convention** (same rule as every skill in this pipeline): a
"sibling" file means one in the same directory as the input RFC — this only
works because `rfc-review` and `rfc-to-schema` both write their outputs
there, next to the RFC they read, not to cwd or anywhere else.

**Check for a sibling `RFC_REVIEW.md`** (from `rfc-review`). If found,
surface its verdict and any downstream-readiness finding — informational,
not a hard gate, same as `rfc-to-schema`.

**Check for a sibling `schema.ir.json`** (from `rfc-to-schema`). If found,
request/response bodies should `$ref` its entities rather than redefining
them. If absent, define shapes locally inline using the same abstract type
system (`uuid`/`string`/`text`/`int`/`bigint`/`float`/`decimal`/`bool`/
`datetime`/`date`/`json`/`enum`/`object`/`array`/`ref`) — this is optional
composition, not a hard dependency; plenty of RFCs describe an API with no
new persisted storage at all.

## Step 2 — Check for an existing API in the repo

If run inside a real codebase, look for an existing OpenAPI spec, `.graphql`
SDL file, or route definitions. This informs:
- **Modification vs. new**: if a proposed operation's derived path+verb
  (REST) or field name (GraphQL) already exists, treat it as a change to
  document, not a fresh addition — note what's changing.
- **Collision flagging**: an unclear collision (same path/field, materially
  different shape, no clear relation to the RFC) gets a Blocking-style
  warning rather than a silently conflicting proposal.

Opportunistic/best-effort, same scope discipline as `rfc-to-schema`'s
existing-schema check — not an exhaustive spec diff.

## Step 3 — Extract the IR

Produce `api.ir.json`: a list of `operations`. The full field-by-field IR
spec lives in the IR_SPEC docstring at the top of `scripts/render_api.py` —
read it before writing the IR. The details that most often go wrong:
- `name` is camelCase and protocol-agnostic — never a URL path.
- Set `entity` whenever the operation targets a specific entity — REST path
  derivation for `read`/`update`/`delete`/`action` kinds depends on it.
- `kind` is a semantic category (`create`/`read`/`list`/`update`/`delete`/`action`),
  not an HTTP verb.
- Base error cases map to status codes automatically; domain-specific error
  cases **require an explicit `status_hint`**.
- Populate `required_scopes` only when the RFC states them — never invent a
  role/scope system.
- `rest_override`/`graphql_override` are used verbatim when present.

**Handling gaps** — same discipline as `rfc-to-schema`: state it → use it;
don't state it but a sensible default exists → fill it and flag `assumed:
true` with a reason; can't identify what operations even exist → stop and
say so rather than inventing an API surface from nothing.

## Step 4 — Render

```bash
python3 <skill_dir>/scripts/render_api.py --ir-file api.ir.json [--schema-ir-file schema.ir.json] --target openapi|graphql|all
```

The script validates first (duplicate operation names, invalid `kind`,
domain-specific errors missing a `status_hint`, unresolved entity refs) and
renders nothing if invalid.

**REST/OpenAPI derivation convention**: `kind` → HTTP verb
(`create`→POST, `read`/`list`→GET, `update`→PATCH, `delete`→DELETE,
`action`→POST to a sub-path); path from the operation's `entity` (pluralized
via the shared `slugify_table_name`) plus `{id}` for single-item operations;
non-CRUD `action` operations get a derived sub-path
(`POST /posts/{id}/publish`) flagged `x-path-derivation-confidence: low`
since it's a weaker derivation than the CRUD cases. An explicit
`rest_override` is always used verbatim instead.

**GraphQL derivation convention**: `read`/`list` → `Query` fields,
everything else → `Mutation` fields; cursor-paginated `list` operations
render as Relay-style connections (`edges`/`node`/`pageInfo`); operations
with declared `errors` get a `<Operation>Payload` type (data field +
`errors: [Error!]`) rather than trying to force REST status codes into
GraphQL; every `enum`-typed field gets an actual `enum` declaration in the
SDL (a field referencing an undeclared type is invalid GraphQL — verify this
didn't regress if you touch the renderer); entity/field names render in
camelCase regardless of the source IR's naming convention (schema IRs
commonly use snake_case DB-style names).

Assumed details carry into rendered output: `x-assumed`/`x-assumed-reason`
in OpenAPI schemas (same convention as `rfc-to-schema`'s JSON Schema
output).

## Step 5 — Assemble the output

Write next to the input file (cwd fallback only if the input has no
filesystem location — same convention as `rfc-to-schema`), and also show
inline:
- `api.ir.json` — the neutral IR.
- `openapi.json` — OpenAPI 3.1.
- `schema.graphql` — GraphQL SDL.
- `API_NOTES.md` — human-facing: assumed vs. stated details, existing-API
  conflicts/modifications detected, whether `schema.ir.json` was found and
  referenced vs. shapes were defined inline, and the `rfc-review` verdict if
  found.

Every run is independent — no revision-tracking in v1, consistent with
`rfc-to-schema`.

## Composition with other skills

- **`rfc-review`**: optional informational input (Step 1).
- **`rfc-to-schema`**: optional informational input for entity `$ref`s (Step 1) — never required.
- **`er-generator`**: unrelated to this skill's output; it consumes `rfc-to-schema`'s IR or a live DB, not this skill's API IR.

## Rules

- Don't force every operation's routing through the mechanical derivation when the RFC states something explicit — use the override fields.
- Don't invent auth scopes/roles the RFC never mentions.
- Don't let a domain-specific error case through without a `status_hint` — the renderer has nowhere sensible to fall back to.
- Don't let a GraphQL `enum` field type reference go undeclared in the SDL — this is invalid GraphQL, not just an idiom nicety.
- Don't collapse an inline (non-`$ref`) output shape into a bare `JSON` scalar when it has real fields — render a proper named type.

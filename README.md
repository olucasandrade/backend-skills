# api-skills

Claude Code skills covering the full backend engineering lifecycle — pre-design gap analysis, RFC review, schema/API generation, ER diagrams, security/performance/architecture review, API docs, log triage, incident postmortems. Twelve skills, stdlib-only Python, zero dependencies to install.

```bash
curl -fsSL https://raw.githubusercontent.com/olucasandrade/backend-skills/main/install.sh | bash -s -- log-triage
```

No clone required. See [Install](#install) for installing more than one skill at a time.

## What's here

Each skill acts like a specialized senior engineer with deep expertise in one domain — narrow scope, careful judgment, and a deterministic script layer wherever the work is genuinely mechanical, so the model isn't re-deriving parsing or rendering logic on every run.

```
requirements/     rfc-review                   review a proposal for gaps, ambiguity, risk
                   requirement-gap-analysis     interrogate pre-design input for unknowns

design/            rfc-to-schema                RFC → SQL DDL / JSON Schema
                   rfc-to-api                   RFC → OpenAPI 3.1 / GraphQL SDL
                   er-generator                 schema/live DB → Mermaid ER diagram

implementation/    security-review              codebase → vuln findings + secrets scan
                   performance-review           codebase → N+1s, complexity, unbounded reads
                   architecture-review          codebase → layering, cycles, coupling
                   api-docs                     IR/spec/code → Markdown API reference

operations/        log-triage                   messy logs → ranked, explained report
                   log-triage-interactive       same, with clarifying questions + drill-down
                   incident-summary             logs/notes → postmortem (interactive)
```

These aren't one pipeline — they compose into several, depending on where you are in a feature's life. See [`PIPELINES.md`](PIPELINES.md) for all of them, a full worked example, and the file-discovery conventions that make composition work. See [`EXAMPLES.md`](EXAMPLES.md) for real prompts and expected output on the non-obvious edge cases.

| Skill | What to say | What you get |
|---|---|---|
| [`requirement-gap-analysis`](requirements/requirement-gap-analysis/SKILL.md) | *"what am I missing before I design this"* | `GAP_ANALYSIS.md` |
| [`rfc-review`](requirements/rfc-review/SKILL.md) | *"review this RFC"* | `RFC_REVIEW.md` |
| [`rfc-to-schema`](design/rfc-to-schema/SKILL.md) | *"generate the schema for this RFC"* | `schema.ir.json`, `schema.sql`, `SCHEMA_NOTES.md` |
| [`rfc-to-api`](design/rfc-to-api/SKILL.md) | *"generate the API for this RFC"* | `api.ir.json`, `openapi.json`, `schema.graphql`, `API_NOTES.md` |
| [`er-generator`](design/er-generator/SKILL.md) | *"diagram this schema"* | `er_diagram.mmd` |
| [`security-review`](implementation/security-review/SKILL.md) | *"review this codebase for security issues"* | `SECURITY_REVIEW.md` |
| [`performance-review`](implementation/performance-review/SKILL.md) | *"review this for performance issues"* | `PERFORMANCE_REVIEW.md` |
| [`architecture-review`](implementation/architecture-review/SKILL.md) | *"check for circular dependencies"* | `ARCHITECTURE_REVIEW.md` |
| [`api-docs`](implementation/api-docs/SKILL.md) | *"document this API"* | `API_DOCS.md` |
| [`log-triage`](operations/log-triage/SKILL.md) | *"triage these logs"* | inline report |
| [`log-triage-interactive`](operations/log-triage-interactive/SKILL.md) | *"why is this crashing"* | clarifying Qs → inline report → drill-down |
| [`incident-summary`](operations/incident-summary/SKILL.md) | *"help me write up this incident"* | `INCIDENT_SUMMARY.md` |

Every skill writes its output next to the input it read.

## Install

```bash
curl -fsSL https://raw.githubusercontent.com/olucasandrade/backend-skills/main/install.sh | bash -s -- log-triage
curl -fsSL .../install.sh | bash -s -- log-triage rfc-review        # multiple skills
curl -fsSL .../install.sh | bash -s -- --category implementation     # a whole category
curl -fsSL .../install.sh | bash -s -- --all                         # everything
```

`install.sh` downloads just what you ask for and places any required shared dependency alongside it automatically (source of truth: [`MANIFEST.json`](MANIFEST.json)). Re-running it updates an already-installed skill in place. Requires only `curl`, `tar`, and `python3` — no `git`, no build step. Inspect [`install.sh`](install.sh) before piping it into `bash`.

Prefer a manual install from a clone? Copy the skill folder plus whatever `shared` path(s) `MANIFEST.json` lists for it into `~/.claude/skills/`:

```bash
cp -r operations/log-triage ~/.claude/skills/
cp -r operations/_shared ~/.claude/skills/_shared
```

Claude Code picks up the skill on next start. Invoke it by describing what you want ("triage these logs", "review this RFC") or directly with `/<skill-name>`.

## How it's built

- **Two-layer architecture.** A deterministic script does the structural work — parsing, validation, rendering, graph analysis; the model does extraction and judgment on top. The ratio shifts by skill: `er-generator` is script-heavy, `security-review` is almost entirely judgment.
- **Never silently guess.** Every inferred detail is flagged, not presented with the same confidence as something the input actually stated — `assumed: true` in schema/API IR, confidence tiers on review findings, explicit "verify" notes on low-confidence derivations.
- **Shared code only on a genuine second consumer.** `_shared/` folders exist for logic two or more skills need identically, not preemptively.
- **Composition is optional, never required.** Every skill works standalone. Cross-skill links are either auto-discovered or explicit-pointer-only, depending on whether the linked artifacts live in one predictable directory or not — see [`PIPELINES.md`](PIPELINES.md).

## Tests

```bash
cd operations/_shared/log-triage-core && python3 -m unittest discover -s tests -v
```

Every skill's deterministic layer ships with stdlib-only unit tests. CI (`.github/workflows/tests.yml`) runs the full suite, validates `MANIFEST.json` against the filesystem, and exercises `install.sh` end-to-end on every push and PR.

## Contributing

New skill ideas, bug reports, and PRs are welcome. Match the existing shape: a `SKILL.md` with clear steps, a thin stdlib-only `scripts/` layer where there's genuinely deterministic work to do, fixtures for manual QA (and real unit tests if there's a script), an `evals/evals.json` with 2–3 test cases, and an entry in `MANIFEST.json` if it should be installable.

## License

MIT — see [LICENSE](LICENSE).

# api-skills

Claude Code skills for my backend engineering lifecycle, I'm sharing it to the world. From a rough
feature idea to a shipped, reviewed, documented API. Pre-design gap
analysis, RFC review, schema/API generation, ER diagrams, security/
performance/architecture review, API docs, log triage, and incident
postmortems. Stdlib-only Python under the hood, no dependencies to
install, no build step.

Each skill acts like a specialized senior engineer with deep expertise in
its one domain — narrow scope, careful judgment, and a deterministic
script layer wherever the work is genuinely mechanical (parsing,
rendering, graph analysis) so the model isn't re-deriving the same
structural logic on every run.

## Skills

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

These 11 skills aren't one pipeline — they compose into several, depending
on where you are in a feature's life (pre-design, design, implementation,
operations). See [`PIPELINES.md`](PIPELINES.md) for all of them, a full
worked example, and the two file-discovery conventions (auto-discovery vs.
explicit-pointer-only) that make composition actually work. See
[`EXAMPLES.md`](EXAMPLES.md) for real prompts and expected output on the
non-obvious edge cases.

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

Every skill writes its output next to the input it read — see
[`PIPELINES.md`](PIPELINES.md) for the exact rule and how skills discover
each other's output.

## Install

No clone required — `install.sh` downloads just what you ask for and
places any required shared dependency alongside it automatically (source
of truth: [`MANIFEST.json`](MANIFEST.json)):

```bash
curl -fsSL https://raw.githubusercontent.com/olucasandrade/backend-skills/main/install.sh | bash -s -- log-triage
curl -fsSL .../install.sh | bash -s -- log-triage rfc-review        # multiple skills
curl -fsSL .../install.sh | bash -s -- --category implementation     # a whole category
curl -fsSL .../install.sh | bash -s -- --all                         # everything
```

Re-running the installer updates an already-installed skill in place.
Requires only `curl`, `tar`, and `python3` (Python 3 is already a hard
dependency of the skills themselves) — no `git`, no build step. Inspect
[`install.sh`](install.sh) before piping it into `bash`.

Prefer a manual install from a clone? Copy the skill folder plus whatever
`shared` path(s) `MANIFEST.json` lists for it into `~/.claude/skills/`:

```bash
cp -r operations/log-triage ~/.claude/skills/
cp -r operations/_shared ~/.claude/skills/_shared
```

Claude Code picks up the skill on next start (or immediately if it's
already scanning `~/.claude/skills/`). Invoke it by describing what you
want ("triage these logs", "review this RFC") or directly with
`/<skill-name>`.

## Design principles

- **Two-layer architecture.** A deterministic script does the structural
  work (parsing, validation, rendering, graph analysis); the model does
  extraction and judgment on top. The ratio shifts by skill — `er-generator`
  is script-heavy, `security-review` is almost entirely judgment — but the
  split itself is deliberate everywhere.
- **Never silently guess.** Every inferred (non-stated) detail is flagged,
  not presented with the same confidence as something the input actually
  said — `assumed: true` in schema/API IR, confidence tiers on review
  findings, explicit "best guess, verify" notes on low-confidence
  derivations.
- **Shared code only on a genuine second consumer.** `_shared/` folders
  exist for logic two or more skills need *identically* — not preemptively.
  See the shared-dependency notes in each category's skills for what's
  actually shared and why.
- **Composition is optional, never required.** Every skill works standalone.
  Cross-skill links are either auto-discovered (skills that write into one
  flat directory by convention) or explicit-pointer-only (skills reading a
  real codebase, where auto-search would be slow or ambiguous) — see
  [`PIPELINES.md`](PIPELINES.md).

## Running the tests

Each skill's deterministic layer ships with stdlib-only unit tests — no
dependencies to install, `python3 -m unittest` is enough. Skills with no
script layer (`requirement-gap-analysis`, `incident-summary`) rely on
fixture-based manual QA instead.

```bash
cd operations/_shared/log-triage-core && python3 -m unittest discover -s tests -v
```

CI (`.github/workflows/tests.yml`) runs every skill's test suite,
validates `MANIFEST.json` against the filesystem, and exercises
`install.sh` end-to-end on every push/PR.

## Contributing

New skill ideas, bug reports, and PRs are welcome. If you're adding a
skill, match the existing shape: a `SKILL.md` with clear steps, a thin
stdlib-only `scripts/` layer if there's genuinely deterministic work to
do, fixtures for manual QA (and real unit tests if there's a script), and
an entry in `MANIFEST.json` if it should be installable via `install.sh`.

## License

MIT — see [LICENSE](LICENSE).

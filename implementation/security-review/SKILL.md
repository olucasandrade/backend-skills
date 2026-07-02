---
name: security-review
description: Review a codebase for security vulnerabilities — injection, broken access control, XSS, SSRF, path traversal, CSRF, mass assignment, insecure deserialization, crypto misuse, and hardcoded secrets — like a senior security engineer's audit pass. Use whenever the user asks to review or audit code for security, asks "is this code safe", mentions OWASP, pentest prep, or vulnerabilities, or asks to check for leaked secrets/credentials — even if they don't say "security review" explicitly.
---

# security-review

Reviews an entire codebase (v1 scope — not a diff or PR review) for
code-level security vulnerabilities, hardcoded secrets/credentials, and
broken authentication/authorization logic.

**Out of scope for v1:** dependency/CVE scanning. That needs an
up-to-date vulnerability database, which an LLM can't reliably reason about
from training data alone — it's a fundamentally different problem, better
served by existing tools (`npm audit`, `pip-audit`, `osv-scanner`, etc.).
If the codebase has a lockfile, mention in the report that a dependency
scan is a separate recommended step, but don't attempt to perform one.

**Requires:** `scripts/scan.py` and `implementation/_shared/file_enum.py`
(stdlib-only Python 3). `install.sh` places these automatically.

## Step 1 — Resolve the input

Accept a directory path (the codebase root to review). If nothing is
given, ask for one — don't default to reviewing an unrelated cwd without
confirming that's actually what the user wants scanned.

If the user separately mentions an `api.ir.json` (from `rfc-to-api`) or
`RFC_REVIEW.md` (from `rfc-review`) they want cross-checked against the
implementation, note its path for Step 4. **Only use these if explicitly
pointed at — do not search the repo for them.** They typically don't live
next to the source (they're usually generated into a `jobs/`-style
directory elsewhere), so auto-discovery would be guesswork, not detection.

## Step 2 — Run the structural pre-pass

```bash
python3 <skill_dir>/scripts/scan.py --root PATH
```

This returns JSON with:
- `files` — the filtered list of reviewable source files (binaries,
  vendored/generated directories, lockfiles, and `.gitignore`-matched
  paths already excluded). This is your reading list — don't waste budget
  re-deriving which files are worth reading.
- `skipped` — what was excluded and why (`vendor`, `binary`, `lockfile`,
  `gitignored`), each as a plain path list.
- `secrets_findings` — deterministic, high-confidence secret-shape matches
  only (AWS keys, private key headers, GitHub/Slack/Stripe tokens, JWTs).
  Each entry's `snippet` is already redacted — never echo the actual
  secret value into the report or anywhere else, only the pre-redacted
  snippet plus file/line. This pass is intentionally narrow (real key
  *shapes* only, no generic "secret =" heuristics) — it will not catch
  every hardcoded credential. Still read the code yourself for secrets
  that don't match a known shape (obviously-named config constants,
  suspicious base64 blobs assigned to `*_key`/`*_token`/`*_password`
  variables, etc.) — the script narrows the search, it doesn't replace it.

**Scoping (large codebases only):** if `files` contains more than 150
entries, ask one question via AskUserQuestion before reading — options:
review everything (slower, complete), focus on a subtree the user names,
or focus on request-handling/entry-point paths first. Skip this entirely
below the threshold, or when the user's request already scoped the review.

## Step 3 — Read the code

For every file in `files`, read with a senior security engineer's eye
across these categories (skip a category entirely, and say so, only if
truly inapplicable to this codebase — e.g. no crypto usage anywhere):

1. **Injection** — SQL/NoSQL/command/LDAP injection from unsanitized
   input reaching a query, shell call, or interpreter.
2. **Broken access control** — endpoints/functions that check
   *authentication* (is someone logged in) but not *authorization* (is
   this specific user allowed to do this specific thing to this specific
   resource) — the most common real-world gap, and the easiest to miss
   because the code often "looks" protected at a glance.
3. **XSS** — unescaped user input rendered into HTML/DOM/templates.
4. **SSRF** — server-side requests to user-influenced URLs without
   allowlisting.
5. **Insecure deserialization** — unpickling/deserializing untrusted data
   (`pickle`, unsafe YAML loaders, PHP `unserialize`, Java
   `ObjectInputStream`, etc.).
6. **Crypto misuse** — weak/broken algorithms (MD5/SHA1 for passwords,
   ECB mode), hardcoded IVs/salts, insecure randomness (`random` instead
   of `secrets`/`crypto.randomBytes` for tokens/keys).
7. **Hardcoded secrets** — beyond what `secrets_findings` already caught;
   see Step 2's note.

**Codebase-wide patterns matter more than isolated lines** — if the same
sanitization gap or missing authz check recurs across many handlers, say
so as one systemic finding with every affected location listed, not N
near-duplicate findings.

## Step 4 — Optional: cross-check against the RFC pipeline

Only if the user explicitly pointed you at an `api.ir.json` in Step 1:
for each operation with `requires_auth: true` and/or a non-empty
`required_scopes`, verify the corresponding code path actually enforces
that — not just "some auth check exists somewhere," but that the specific
required scope/role is checked for that specific operation. Report any
mismatch as its own finding, tagged as **RFC/implementation drift** so
it's clearly distinguished from a standalone code-review finding — this
check exists only because the pipeline artifacts happened to be available,
not because every finding of this kind implies one.

## Step 5 — Assemble findings

Each finding needs: `file`, `line`(s), `category` (one of Step 3's seven,
or `secret`), `severity`, `confidence`, a description of the issue, and a
concrete suggested fix (not just "sanitize this input" — name the
actual mechanism: parameterized query, `textContent` instead of
`innerHTML`, an allowlist check, etc.).

**Severity** (how bad if exploited):
- **Critical** — remote, unauthenticated, high-impact (data breach, full
  account takeover, RCE).
- **High** — serious impact but requires some precondition (authenticated
  user, specific config, chained with another issue).
- **Medium** — real issue, limited blast radius or requires unusual
  circumstances to exploit.
- **Low** — defense-in-depth / best-practice gap, not directly exploitable
  on its own.

**Confidence** (how sure you are this is real, not a false positive):
- **High** — you traced the full data flow from input to sink; no
  mitigating control seen.
- **Medium** — the pattern looks wrong but you can't fully confirm from
  the code alone (e.g., sanitization might happen in a framework layer
  you can't see).
- **Low** — flagged out of caution; plausible this is a non-issue.

For every Medium/Low-confidence finding, add a one-line note on what
would make it a false positive (e.g., "safe if this ORM parameterizes
`.raw()` calls internally — verify against the driver docs"). Never omit
a finding purely for low confidence — that's the reader's call to make
when triaging, not something to pre-filter away.

## Step 6 — Write the report

Write `SECURITY_REVIEW.md` next to the codebase root reviewed (or cwd, if
the root itself has no clear parent worth writing into), and show it
inline — both, not one or the other. Structure:

1. **Summary line** — count per severity tier, e.g. "2 Critical, 4 High,
   9 Medium, 3 Low."
2. **Findings**, grouped by severity (Critical first), each with category,
   confidence, description, and suggested fix.
3. **RFC/implementation drift** (if Step 4 ran) as its own section.
4. **Scan coverage** — how many files were reviewed vs. skipped, and why
   (from `skipped`), so the reader knows the review's actual boundaries.
5. **Recommended follow-ups** — dependency/CVE scan reminder if a
   lockfile was seen; anything else structurally out of this skill's
   scope (e.g., infra/network-level review, pen testing).

There is no single approve/reject verdict for a whole codebase — don't
invent one. The severity summary is the top-line signal.

Every invocation is treated as a fresh review — this skill does not track
prior reviews or diff against an earlier scan of the same codebase in v1.

## Step 7 — Offer follow-ups

After presenting the report, offer concrete next steps via AskUserQuestion —
e.g. "Explain finding N in more depth", "Draft a fix for the top finding",
"Re-run scoped to <subtree>" — and also accept free-form follow-up
questions. Only draft or apply code fixes when the user explicitly picks
that option; never edit the reviewed codebase unprompted. When drafting a
fix, show a diff and let the user decide whether to apply it.

## Rules

- Don't search the repo for `api.ir.json`/`RFC_REVIEW.md` — only use them
  if the user explicitly points you at one.
- Don't echo an unredacted secret value anywhere, even in an explanation —
  use the pre-redacted snippet only.
- Don't drop findings for low confidence — flag with a false-positive note
  instead.
- Don't report N near-duplicate findings for one systemic pattern — merge
  into one finding listing every affected location.
- Don't edit the reviewed codebase unless the user explicitly asks for a
  fix to be applied.

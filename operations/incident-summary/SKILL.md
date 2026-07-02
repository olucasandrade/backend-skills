---
name: incident-summary
description: Interactively reconstruct a post-incident narrative (timeline, root cause, impact, resolution, action items) from logs, human notes, and/or Slack/incident-channel excerpts, following standard postmortem conventions. Use when the user wants to write up a postmortem, document an incident, or reconstruct what happened during an outage.
---

# incident-summary

Produces a postmortem-shaped narrative — timeline, impact, root cause,
resolution, action items — after an incident is over or being actively
resolved. **Interactive only, no one-shot variant.** Distinct from
`log-triage-interactive`: that skill diagnoses "what's wrong right now"
from logs, organized around error clusters ranked by severity. This skill
documents "what already happened," organized around chronology and
narrative causality, and fills in everything logs alone can never answer
(user impact, whether a fix was real or just a mitigation, action items)
through an interview.

**Dependency:** reuses the shared engine at
`../_shared/log-triage-core/triage.py` (stdlib-only Python 3) for raw-log
parsing/clustering/timestamp extraction when logs are given — no
reparsing logic of its own. If you copy this skill folder standalone,
also copy `operations/_shared/log-triage-core/`.

## Step 1 — Resolve the input(s)

**Logs are optional, not required.** Accept any combination of:
- Raw/messy logs (file, command output, or pasted text — same
  auto-detected formats as `log-triage`).
- A rough human-provided timeline or notes ("started around 2pm,
  customers reported X").
- Pasted Slack/incident-channel excerpts.

None of these alone is assumed sufficient. The interview (Step 3) is the
backbone; whatever inputs exist just ground and pre-fill parts of it.

## Step 2 — Ground what you can, before asking anything

If logs were given, run the shared engine first:

```bash
python3 <skill_dir>/../_shared/log-triage-core/triage.py --file PATH
```

Use its extracted timestamps, clusters, and severity scores as a starting
skeleton for the timeline — a real error spike at a real timestamp is
worth more than an approximate human recollection, so ground the timeline
in it wherever it exists. If notes/Slack excerpts were given instead (or
in addition), extract any concrete timestamps/facts they already state
before asking about them again.

## Step 3 — Interview, one question at a time

Ask **one question at a time** (same convention as `/grill-me` and
`log-triage-interactive`'s clarification pass), each grounded in what's
already known rather than generic — e.g. "logs show the error rate spiked
at 14:02 — is that when the incident actually started, or was there
user-facing impact before it became visible in logs?" rather than "tell
me about the incident." Work through what Step 2's grounding couldn't
answer:

1. **True start time and user-facing impact** — often earlier than the
   first log signal.
2. **Blast radius / severity** — ask directly, don't infer purely from
   log severity scores (see Step 5 — blast radius requires knowing user/
   revenue impact, which logs alone can't determine).
3. **Trigger vs. root cause** — what set it off (a deploy, traffic spike,
   upstream outage) vs. the underlying weakness that made it possible.
   Keep these genuinely distinct; conflating them produces shallow action
   items later.
4. **Resolution** — what was actually done, and explicitly whether it was
   a **real fix** or a **mitigation** (rollback, workaround, scaling up).
   Never let a mitigation get silently written up as if the underlying
   cause was fixed.
5. **Action items** — concrete follow-ups, owner if known, and whether
   each **prevents recurrence** or **improves detection/response time** —
   both matter, but they're different kinds of follow-up and shouldn't be
   blended together in one undifferentiated list.

## Step 4 — Optional: reference existing review findings

If the user explicitly points at a `SECURITY_REVIEW.md` or
`ARCHITECTURE_REVIEW.md` finding that turned into this incident,
reference it directly as root-cause grounding instead of re-deriving the
same analysis. **Explicit-pointer-only — never search the repo for
these**, same convention as the `implementation/` skills. No connection
to `rfc-review`'s rollback section — that's not a concrete enough link to
be worth forcing.

## Step 5 — Assemble the report

Write `INCIDENT_SUMMARY.md` next to the primary input (the log file, or
cwd if working from pasted notes/excerpts with no filesystem location),
and show it inline — both. Structure, in this order:

1. **Summary** — one paragraph: what happened, user-facing impact,
   duration.
2. **Severity** — one of **SEV1** (full outage/critical data issue),
   **SEV2** (significant degradation/partial outage), **SEV3** (minor
   user-facing impact), **SEV4** (no user impact, internal-only) — from
   Step 3's blast-radius question, not inferred from log severity alone.
3. **Timeline** — chronological, timestamped where grounded in real data;
   mark anything not grounded in a real timestamp as approximate
   (`~14:15`, "reported, exact time unclear").
4. **Impact** — who/what was affected, scope, business impact if stated.
5. **Trigger** — what set it off.
6. **Root cause** — the underlying weakness, kept distinct from trigger.
7. **Resolution** — what was done, explicitly marked **fix** or
   **mitigation**.
8. **Action items** — each tagged **prevents recurrence** or **improves
   detection/response**, with an owner if known.

Every invocation is a fresh reconstruction — this skill does not track
prior incident summaries or diff against an earlier draft in v1.

## Things to not do

- Don't require logs — work from human notes/Slack excerpts alone if
  that's all that's available.
- Don't infer severity/blast-radius purely from log severity scores — ask
  directly.
- Don't conflate trigger and root cause.
- Don't write up a mitigation as if it were a real fix.
- Don't search the repo for `SECURITY_REVIEW.md`/`ARCHITECTURE_REVIEW.md`
  — only use one if the user explicitly points at it.
- Don't ask generic open-ended questions when a grounded, specific one is
  possible from what's already known.

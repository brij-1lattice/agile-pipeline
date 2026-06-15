---
name: finalize-tech-spec
description: Interactively finalize a technical requirements document by asking the user questions, starting from foundations and narrowing toward implementation details. Reads existing planning docs first, only asks about gaps, and writes the technical spec when it's closed.
---

# finalize-tech-spec

Walk the user through closing out a technical requirements document. Extract what's already known
from existing planning docs, ask **only the unanswered questions**, layer by layer, until every
required section has an answer — then write the technical spec.

This is a **conversational, multi-turn skill.** Don't draft the document in one shot. Don't
invent answers the user hasn't given.

## Configuration

Paths and document names resolve from **`.claude/pipeline.config.md`** when present: read the
blueprint from `{blueprint}`, the design doc from `{design_doc}`, and write the output to
`{tech_spec}`. If no config exists yet (this skill often runs before the pipeline is
bootstrapped), fall back to discovering planning docs by the patterns in Phase 1 and write to
`TECHNICAL-REQUIREMENTS.md` at the working root — and tell the user to record that path as
`tech_spec` in their config / during `/manage-stories bootstrap`.

## Phase 1 — Ground yourself in existing context

Before asking anything, read the planning docs that exist:
- `{blueprint}` (or any `*blueprint*.md`, `*product*.md`, `*core-idea*.md` — the "what to build" doc)
- `{design_doc}` (or any `DESIGN*.md`, `UI-SPEC*.md`, `*HANDOFF*.md` — the "what the prototype decided" doc)
- `CLAUDE.md` (repo conventions), `README.md`
- Any existing `{tech_spec}` / `ARCHITECTURE.md` / `SPEC.md` — if found, you're in **update mode** (re-read it, diff the interview against current sections, propose amendments, maintain the `Last updated` header + the open-questions table).

Extract: tech stack, modules, data shapes, API contracts, phases, integrations, auth model — so
you don't re-ask.

## Phase 2 — Section-by-section interview

A complete tech spec needs answers across these sections, in order (each layer assumes the
previous is settled):

1. **Product foundation** — what the system does, users, success criteria, in/out of scope for the current phase
2. **Tech stack & runtime** — framework + version, language, package manager, runtime version, targets
3. **Data layer** — database, ORM/client, schema source-of-truth, seed strategy, file storage
4. **Auth & authorization** — provider, identity + role model, sessions, route gating, reset flow
5. **External integrations** — email/payments/analytics/search/CDN/captcha/error-tracking, with vendor + tier
6. **API contracts** — endpoints for this phase with method, path, payload, auth, rate limit
7. **Rendering strategy** — per route: SSG/SSR/ISR/CSR/streaming, revalidation, cache headers
8. **Performance targets** — Core Web Vitals, p95 latency, bundle budget, image pipeline
9. **Security & compliance** — validation surface, CSRF/XSS posture, secrets, retention, regulatory (GDPR/DPDP/…)
10. **Observability** — logging, error tracking, analytics, uptime, alert routing
11. **Deployment & environments** — host, environments, branch strategy, CI/CD, preview deploys, secret injection
12. **Testing strategy** — unit/integration/E2E/visual/a11y, tooling, coverage target, gate timing
13. **Migration & rollout** — greenfield build sequence; or data-migration + cutover + rollback
14. **Open questions & deferred decisions** — what's intentionally deferred, each with the trigger that forces it

### How to ask
1. **Check the docs first.** If existing material pins a section, summarize it in 1–3 lines and ask one confirmation ("Docs say X — keep or revise?"). Don't re-litigate decided items.
2. **For open sections, start broad** (the foundational question), then drill based on the answer.
3. **Use `AskUserQuestion`** with 2–4 concrete options; first option `(Recommended)` based on what the chosen stack implies. The user can always free-text.
4. **Batch only related sub-questions** (max 4). 5. **After each answer, state what you recorded + what's next.** 6. **Adapt depth to the user's pace.**

### Stop conditions
Move to Phase 3 when every section has a recorded answer (decided / deferred-with-trigger /
out-of-scope), or the user says "wrap it up" — then mark unanswered sections **Open** rather than
fabricating.

## Phase 3 — Write the technical spec

Write to `{tech_spec}` (or the fallback path). Structure:

```markdown
# Technical Requirements — <project name>

> Status: <Draft | Approved> · Last updated: <YYYY-MM-DD>
> Companion to: <the planning docs you read in Phase 1>

## 1. Product foundation
…
[one section per Phase 2 item, in order]
…
## 14. Open questions
| # | Question | Owner | Trigger to resolve |
|---|---|---|---|
```

Inside each section: lead with the decision (1–2 lines), then rationale from the user's words;
tables for enumerated items; cite the source doc for decisions drawn from planning material
(`[from: <blueprint> §3]`); flag any answer that **conflicts** with existing docs rather than
silently overwriting.

> **Section alignment.** Downstream skills reference these sections by *role* via the config
> `tech_spec_sections` map (stack/schema/auth/api/ui_rules/testing/env/open_questions/…). Keep the
> output's numbering stable, and make sure the config map matches it — note any renumbering so the
> user can update `tech_spec_sections`.

After writing, show a one-line summary per section and ask if any needs revision before marking
the doc Approved.

## Operating rules

- **Never invent answers** — ask, or write "Open" with a trigger.
- **Never widen scope** beyond the phase the user set in §1.
- **Stay terse between questions** (1–2 sentences).
- **Save progress** — after every ~3 sections, write a draft with locked sections + the rest marked "In progress", so an interruption doesn't lose state.
- **One file out** — the deliverable is `{tech_spec}`; no sidecar docs unless asked.

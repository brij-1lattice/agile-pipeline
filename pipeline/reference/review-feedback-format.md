# Reference — feedback-section format (Code Review · Testing · Verification)

> Single source of truth for the three in-story feedback sections — `## Code Review Feedback`
> (written by `code-review-sprint`), `## Testing Feedback` (written by `qa-sprint`, and by the
> builder on an un-greenable gate), and `## Verification Feedback` (written by `verify-sprint`).
> Each stage writes its findings into its own section so the **next build run** fixes them in
> place. There is **no separate ledger file** — the story owns its findings.

## The cardinal rule — verify, never summarize

For the judgment sections (Code Review, Verification), every finding **must cite exact `file:line`
on BOTH sides** — what's wrong in the build, and the contract it violates (a prototype line, or a
tech-spec section/line). A finding you can't ground in two references does not get written. Re-read
the cited lines directly before asserting a Severity-A/B gap. (This rule exists because an early
summary-only pass produced false positives, claiming faithful sections had shipped wrong.) Testing
Feedback items are objective — a red test — and cite the failing test's `file:line`.

## Severity legends

Two legends, one per judgment section. Same A→D shape (most to least severe), different axis:

**`## Code Review Feedback` — engineering** (`code-review-sprint`):
- **A — Security / data-integrity:** authz/RLS gap, injection, missing validation, secret leak, data loss.
- **B — Correctness:** logic bug, wrong result, an unhandled error path.
- **C — Robustness / edge-case:** empty/null/permission/boundary/race not handled.
- **D — Maintainability / test-quality:** weak/duplicated assertion, dead code, a test that asserts nothing.

**`## Verification Feedback` — design parity** (`verify-sprint`):
- **A — Missing / structural:** a designed screen or major section is absent or structurally different.
- **B — Component / behavior:** section present but wrong composition, count, states, or interaction.
- **C — Design-system / rule:** violates a locked UI rule (`ui_rules` section of the tech spec / design-doc rules).
- **D — Copy / cosmetic:** wording, color, spacing nits.

## Finding tags (judgment sections only)

Code-review and verification findings carry a **severity** (A–D, above) **and** a tag:
- **`[true]`** — a genuine gap. **Severity A/B/C → a blocking open `- [ ]` item** the next build run must close. **Severity D → a non-blocking `> nit [D]:` note** (logged, not a checkbox) — a real QA team records cosmetic / maintainability / weak-assertion trivia without blocking sign-off. A D nit gets swept up only opportunistically (it's in the re-run scope if the story rebuilds for some A/B/C reason); it never, by itself, fails a gate.
- **`[justified]`** — deviates but defensible: schema constraint, documented decision, production hardening, or a tech-spec override of the prototype. Recorded as a **non-blocking note** (a `> justified:` line), not a checkbox.
- **`[choice]`** — a real open product decision (neither option clearly right). **Surfaced to the user** by the stage, not auto-written as actionable; once decided it may become a `[true]` item or a note.

A story is **`<stage>-failed` iff its section has ≥1 open _blocking_ `- [ ]` item** — i.e. ≥1
`[true]` finding of severity **A, B, or C** (`code-review-failed` ← Code Review Feedback;
`verification-failed` ← Verification Feedback). `[choice]`-only, `[justified]`-only, or `[D]`-nit-only
audits **don't** fail the gate (decisions / defensible / cosmetic, not blocking gaps) — the story
advances to the passed status carrying the surfaced choice or the logged nit. **Testing Feedback is
not tagged**: a failing test is objectively blocking, so any open `## Testing Feedback` item makes the
story `testing-failed`.

## Item formats

Each open finding is one checkbox line. `[justified]`/`[choice]` items are `>`-quoted notes
beneath (not checkboxes). When a re-run fixes an item the builder flips `- [ ]` → `- [x]` (keeping
the line for history).

```markdown
## Code Review Feedback

<!-- written by code-review-sprint; cleared by the next execute-sprint run -->
- [ ] [A] jobs POST route — no auth/authz check; any caller can create a job · build {app_dir}app/api/jobs/route.ts:40 vs spec {tech_spec} security (auth required on writes)
- [ ] [C] listArticles — page<=0 not handled, returns the whole table · build {app_dir}lib/articles.ts:22 vs spec {tech_spec} api (pagination bounds)

> nit [D]: applyToJob test asserts only the 200 status, not the inserted row — vacuous · build {app_dir}lib/jobs.test.ts:30
> justified [D]: the inline Supabase type cast is the documented pattern for generated types — {tech_spec} schema

## Testing Feedback

<!-- written by qa-sprint (and the builder on an un-greenable gate); cleared by the next execute-sprint run -->
- [ ] jobs-filter empty-state: expected the "no roles" panel, got 0 rows and no panel ({app_dir}e2e/qa/jobs-filter.qa.spec.ts:31)
- [ ] applyToJob: expected 401 when unauthenticated, got 500 ({app_dir}lib/jobs.qa.test.ts:18)

## Verification Feedback

<!-- written by verify-sprint; cleared by the next execute-sprint run -->
- [ ] [A] Experts directory — featured-expert rail is absent · design {design_dir}screens-experts.jsx:88 vs build {app_dir}app/experts/page.tsx:1 (absent)
- [ ] [C] heading uses Inter, design pins Sora · design {design_doc} ui_rules vs build {app_dir}app/jobs/page.tsx:12

> choice [B]: prototype shows 2 featured slots, copy implies 3 — awaiting product decision
```

`execute-sprint`'s re-run scope is the **union** of open `- [ ]` items across all three sections
(blocking items only — `> nit`/`> justified`/`> choice` notes are not checkboxes and aren't scoped
in). A stage's `--recheck` / `--reverify` re-runs only after the story is `done` again; a clean
re-audit with every blocking item in that section resolved advances the story to the stage's passed
status.

## When a fixed gap invalidates a committed QA test

The adversarial tests `generate-test-sprint` commits join the **permanent gate**, so a later fix can
legitimately turn one red — a resolved `[choice]` or a changed AC moves the expected behavior, and
the committed *test*, not the code, is now wrong. Without an owner this deadlocks: the builder must
green the gate but is otherwise barred from touching tests. The rule:

- **The builder may edit or retire that one QA test** during a `*-failed` re-run **only with a
  two-sided citation** — the changed AC / resolved `[choice]` ↔ the `e2e/qa/`·`*.qa.test.ts` line it
  invalidates — recorded in the RESULT `notes`. **Absent that justification a red QA test is a real
  defect** to fix in production code, never edited away to pass.
- **Bulk QA-test revision** (a surface that changed shape, not a single stale assertion) belongs to
  **`/generate-test-sprint --recheck`**, which re-authors the story's adversarial suite in place.

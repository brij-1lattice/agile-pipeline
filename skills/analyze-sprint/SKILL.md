---
name: analyze-sprint
description: Analyze every story in a named sprint, one at a time — ask clarifying questions, reconcile the story against the technical and design docs (proposing doc updates on approval), mine the prototype into acceptance criteria, confirm design linkage, break the story into tasks, classify its build model, and mark it analyzed. Takes a sprint name or number.
---

# analyze-sprint

The **analysis pass** between story creation (`/manage-stories`) and execution. It takes one
sprint, walks its stories one at a time, and for each: sharpens the requirement through
questions, reconciles it against the technical and design docs, mines the prototype into ACs,
confirms design linkage, breaks it into tasks, classifies its build model, and stamps it
**analyzed**. It is the gate that turns a `draft` story into a `ready` one.

## Configuration

All paths/docs/constants/section-refs resolve from **`.claude/pipeline.config.md`** — read it
first. This skill reuses `manage-stories`' format contract; where the two overlap on a *rule*,
`manage-stories` and the shared reference docs are the source of truth and this skill owns the
*analysis workflow*. Shared contracts it applies verbatim:
- Frontmatter & lifecycle → `.claude/pipeline/reference/frontmatter-schema.md`
- Task states → `.claude/pipeline/reference/task-states.md`
- Design-linkage gate → `.claude/pipeline/reference/design-linkage-gate.md`
- Dependency ordering → `.claude/pipeline/reference/topo-order.md`
- INDEX template → `.claude/pipeline/reference/index-template.md`
- AC method tags → `.claude/pipeline/reference/ac-method-tags.md`

Key paths: stories `{stories_dir}<topic>/story-*.md`, index `{index_path}`, tech spec
`{tech_spec}` (open questions in its `open_questions` section), design doc `{design_doc}`,
design sources `{design_dir}*.{design_ext}` (`design:` paths resolve here).

## Input — the sprint

One argument, resolved to a sprint. **Single-operator** (no `.claude/operators/`): a bare number
(`1`), `Sprint N`, or a name fragment matched against the config `sprint_labels` / `{index_path}`
headings. **Multi-operator** (any `.claude/operators/*.md` exists): the canonical form is `owner/N`
(e.g. `brij/2`), resolved per `operator-profile.md` — a bare `N` is owner-ambiguous and prompts. If
absent/ambiguous, read the distinct `owner`+`sprint` values and ask via `AskUserQuestion` (show story
count + SP per sprint). Never invent a sprint — resolve only to one that exists in story frontmatter.

## Story selection & ordering

1. Collect every `{stories_dir}**/story-*.md` (exclude `{archive_dir}`) whose `sprint:` matches (and, in multi-operator mode, whose `owner:` matches the resolved `owner/N` — see `operator-profile.md`).
2. **Preflight lint (errors only)** via the `manage-stories` lint; surface error-severity findings. They don't hard-stop analysis, but report them so the user can fix structural problems first.
3. **Order dependency-first** per `topo-order.md` (a cycle → fall back to INDEX order at analysis time).
4. **Skip already-analyzed** (`analyzed: true`) unless `--all`/`--reanalyze`. Report the skip count up front.

## Per-story loop

One story at a time — never batch. For each, run steps 0–5, then checkpoint.

### Step 0 — Read & ground
Read the story in full, its linked `{design_dir}` sources, and the `{tech_spec}` / `{design_doc}`
sections it touches. Print a 3–4 line orientation (title, User-story line, AC count, `design:`, `dependencies:`).

### Step 1 — Clarifying questions
Judge whether Description + ACs are complete, unambiguous, and testable. Ask via
`AskUserQuestion` **only** on a real gap (vague/untestable criteria, undefined empty/error/
loading/pagination/validation/permission states, scope ambiguity, an ungrounded criterion).
Fold answers back into the story. If already clear, say so and skip — don't manufacture questions.

**Size guard:** if clarification pushes it > `{sp_cap}` SP, stop, recommend `/manage-stories split <id>`, and **defer to backlog** (below). Don't mark analyzed.

### Step 1b — Reconcile ACs against the prototype, then tag each AC
Stops design detail from leaking through the gate (build verifies *against the ACs*).
1. **Enumerate the linked prototype screen** — its visible elements, controls (sort/filter/pagination), states (empty/loading/error/hover/active), featured slots, copy patterns, and the design tokens the design-doc pins (typography family per element, accent usage, spacing density).
2. **Diff that against the ACs.** Every design item not covered by an AC → resolve explicitly: add an AC (in scope) or record a one-line scope-cut in `## Notes` (out of scope — this is what later feeds the parity audit honestly). A design element neither covered nor cut → unresolved; don't mark analyzed.
3. **Tag every AC with its verification method** per `ac-method-tags.md` (`(unit|e2e|axe|visual|manual)`). Prefer automation; reserve `(visual)`/`(manual)` for what truly can't be asserted in code.

### Step 2 — Detect & reconcile doc changes
Compare the clarified story against the docs; flag anything implied but absent:
- **Technical** → routes, endpoints, payload shapes, tables/columns, auth/role rules, integrations, env vars not in `{tech_spec}`.
- **Design** → components, layouts, states, copy, tokens not in `{design_doc}` and not in the linked source.

For each gap, **propose the exact text + target section**; new technical open questions go to
the tech spec's `open_questions` section. **Write only after the user approves the shown text.**
Decline → defer the story (record the unresolved item in `## Notes`). No gap → say so, move on.

**Open-question trigger watch.** Read the tech spec's `open_questions` section and check this
story against every *unresolved* OQ's trigger condition. If it trips one (e.g. an OQ due
"before self-serve upload surfaces ship" and this story *is* one) — **stop before marking
analyzed.** Ask the user to (a) resolve the OQ now (draft the resolution, with approval) or (b)
explicitly re-defer it with a new trigger recorded in the OQ row. Never analyze past an armed,
matching trigger silently.

### Step 3 — Confirm / resolve design linkage
Reconfirm `design:` against reality per `design-linkage-gate.md` (empty/missing → run the gate;
`none-needed` but ACs now imply UI → switch; listed path 404s → fix). Unresolved → defer.

### Step 4 — Break the story into tasks
Break into the natural number of tasks (each maps to ≥1 AC, fits one commit) using the five task
states (`task-states.md`), default `[new]`; replace the TODO placeholder; set
`tasks_populated: true`. Let the AC method tags drive the verification task(s): `(unit)`/`(e2e)`/
`(axe)` ACs each imply a test; `(visual)`/`(manual)` imply a screenshot or documented check. Name
which ACs (by method) each verification task discharges.

### Step 4b — Classify the build model (`exec_model`)
Record which model execute-sprint builds it on.
- **Default `{default_exec_model}`** — porting a prototype screen, composing built primitives, presentational content, obvious tests.
- **Set `{escalation_model}`** when the story shows **≥2** signals: adds/changes schema (migration)/RLS/a new API contract · coordinates with other stories' data · real algorithmic/stateful logic (ranking, search, pagination edges, idempotency, concurrency) · this analysis needed real reconciliation (a `## Notes` entry) · security/auth/validation surface · establishes a net-new pattern.
- Story points are **not** a signal. Record one `## Notes` line stating the call + why.

`exec_model` is advisory — execute-sprint auto-escalates a default-model story that can't pass.

### Step 5 — Mark analyzed
Only when steps 1–4b fully resolved: add `analyzed: true`, `analyzed_date: <today>`,
`exec_model:` (from 4b); bump `status: draft → ready` (never downgrade further-along states);
`tasks_populated: true`.

### Checkpoint
One line per story — e.g. `✓ story-<topic>-03 analyzed [{default_exec_model}] (3 questions · 1 doc update · 4 tasks · ACs 6/0/1 auto/visual/manual)` or `⏸ story-<topic>-05 → backlog (deferred) — design upload pending`. Include `exec_model` and the AC method split so non-automatable ACs are visible from analysis on. User may say "stop" at any checkpoint.

## Deferral handling — move to backlog

When a step can't be fully resolved, the story is **deferred** (not analyzed, not left cluttering
the sprint):
1. Move the file to `{backlog_dir}` (create if missing; excluded from sprint sections). Keep the filename.
2. Set `status: deferred`. 3. Add `original_sprint: <N>`; leave `sprint:` unchanged.
4. Don't change scope — only a short `## Notes` paragraph on *why* + the next step.
5. Leave `tasks_populated`/the Tasks placeholder untouched.

**Triggers:** > `{sp_cap}` SP after clarification · an unresolved doc gap the user declined · an
unresolved design linkage. A deferred story keeps its real `dependencies:`; flag dependents in
the summary. Restore later via `/manage-stories restore <id>`.

## After the sprint

1. **Regenerate `{index_path}`** per the `manage-stories` index flow (including the Backlog section).
2. **Print a summary:** analyzed vs. deferred, the `exec_model` split (with the escalation-model picks named), questions resolved, doc additions (doc + section), design linkages resolved, total tasks, total `(manual)`/`(visual)` ACs. List deferred stories with reasons + next steps.

## Operating rules

- **One story at a time.** **Never fabricate** ACs, tasks, or doc text — propose, then confirm.
- **Doc edits require explicit approval** and exact text shown first. Outside `{stories_dir}`, this skill writes only `{tech_spec}`, `{design_doc}`, and `{design_dir}.gitkeep` (if missing).
- **Analyzed only when fully resolved** — else defer.
- **Leave the `## Code Review Feedback` / `## Testing Feedback` / `## Verification Feedback` sections alone** — the build pass and the QA gauntlet own them; they're empty at analysis and are never a doc-gap signal.
- **Respect `manage-stories` invariants** (≤ `{sp_cap}` SP, five task states, design linkage never silently empty, idempotent INDEX). **Never set `status: done` or any QA-gauntlet status** (`code-reviewed`/`code-review-failed`/`tests-generated`/`tested`/`testing-failed`/`verified`/`verification-failed`). **Never invent a sprint.**

## When to bail and ask

- Sprint matches zero stories → list existing sprints, ask.
- A within-sprint cycle → report, suggest `/manage-stories lint`, fall back to INDEX order.
- An ambiguous doc gap → describe interpretations, let the user pick.
- Clarification implies a split → recommend `/manage-stories split <id>` and defer.

---
name: manage-stories
description: Create and maintain a modular agile-stories tree. First run bootstraps the pipeline config + story tree from the blueprint; subsequent runs support add / split / update / restore / lint / index. Enforces a story-point cap, owner assignment, dependency tracking, design linkage, and tech-feasibility against the technical spec.
---

# manage-stories

This skill creates and maintains a functional spec broken into independently developable units
called **stories** — small markdown files under `{stories_dir}<topic>/`. It enforces size
limits, ownership, dependency tracking, design linkage, and tech-feasibility against the
project's technical spec.

## Configuration

All paths, document names, constants, models, vocabulary, and tech-spec section references
resolve from **`.claude/pipeline.config.md`** — read it first. Placeholders below
(`{stories_dir}`, `{blueprint}`, `{sp_cap}`, the `topics` table, `tech_spec_sections`, …) are
that file's keys. **If the config is absent, run `bootstrap` (below) before anything else.**

This skill **owns the story format**. It defers the shared contract to single-source reference
docs — apply them verbatim, don't restate them:
- Frontmatter, body sections & lifecycle → `.claude/pipeline/reference/frontmatter-schema.md`
- Task states & done-gate → `.claude/pipeline/reference/task-states.md`
- Design-linkage gate → `.claude/pipeline/reference/design-linkage-gate.md`
- Feedback-section format (Code Review / Testing / Verification) → `.claude/pipeline/reference/review-feedback-format.md`
- INDEX template → `.claude/pipeline/reference/index-template.md`

## Vocabulary

Agile terms. Two look alike — read carefully:
- **story** (this skill's unit of work) → a file like `{stories_dir}<topic>/story-<topic>-03-<slug>.md`
- **User story** (a narrative section *inside* a story file) → the `As a … I want … So that …` block

A **sprint** here is a release grouping (from the blueprint's phases via the config
`sprint_labels`), **not** a 2-week iteration. A **topic** is a feature area (config `topics`).
Never invent sprint numbers — only those defined in config.

## Mode detection

| Condition | Mode |
|---|---|
| `.claude/pipeline.config.md` missing | **bootstrap** (then init) |
| `{stories_dir}` does not exist (or only `.gitkeep`) | **init** |
| Subcommand `add` | **add** |
| Subcommand `split <story-id>` | **split** |
| Subcommand `update <story-id>` | **update** |
| Subcommand `restore <story-id>` | **restore** |
| Subcommand `lint` | **lint** |
| Subcommand `index` | **index** |
| No subcommand, `{stories_dir}` exists | Ask which mode via `AskUserQuestion` |

## Per-story file format

Path: `{stories_dir}<topic>/story-<topic>-<NN>-<kebab-slug>.md` (two-digit `<NN>`, unique per
topic — pick the next free number). Frontmatter, body sections, and the lifecycle are defined
in `frontmatter-schema.md`; task states in `task-states.md`; the `design:` field in
`design-linkage-gate.md`. **This skill never populates `## Tasks`** — it writes the empty
placeholder from `task-states.md` and sets `tasks_populated: false`; analyze-sprint fills it. It
also scaffolds the three empty feedback sections — **`## Code Review Feedback`**,
**`## Testing Feedback`**, and **`## Verification Feedback`** (per the body-sections list in
`frontmatter-schema.md`) — the QA-gauntlet stages fill these.

Acceptance criteria are written **untagged** here (the verification method isn't known until
analysis); analyze-sprint adds the `(unit|e2e|axe|visual|manual)` tags
(`.claude/pipeline/reference/ac-method-tags.md`).

## Bootstrap flow

Run when `.claude/pipeline.config.md` is missing — it writes that file, then continues to init.
This is what makes the pipeline project-agnostic: nothing project-specific is hardcoded in the
skills, so a new project supplies its bindings here.

1. **Locate planning docs.** Search the repo for the blueprint (`*product*.md`, `*blueprint*.md`, `*core-idea*.md`), the tech spec (`*TECHNICAL*`, `*tech-spec*`, `ARCHITECTURE.md`, `SPEC.md`), and the design doc (`*HANDOFF*`, `DESIGN*`, `UI-SPEC*`). Show what you found; ask the user to confirm or correct each path. If no tech spec exists, route to `/finalize-tech-spec` first.
2. **Ask the path layout** via `AskUserQuestion`: `working_root` (where planning artifacts live — default `plan/` or repo root), `app_dir` (where built code goes — default `web/`), `design_dir` + `design_ext` (prototype location + format).
3. **Derive topics & sprints from the blueprint.** Read `{blueprint}`, extract its phases (→ `sprint_labels`) and modules/feature areas (→ `topics`), and **propose** the topic→sprint table + sprint labels for the user to confirm or edit. Never invent — only what the blueprint supports.
4. **Pick the stack profile.** List the profiles available under `.claude/pipeline/stack-profiles/`; the user picks one, or chooses "author a new profile" (point them at `stack-profiles/README.md` and pause until it exists).
5. **Confirm the tech-spec section map.** Read the tech spec's headings and propose the `tech_spec_sections` role→ref map (stack/schema/auth/api/ui_rules/testing/env/open_questions); the user corrects any that differ.
6. **Ask the rest** (offer the template defaults): `default_owner`, `external_services`, `sp_cap` (5), `max_fix_attempts` (3), `stale_days` (30), the model keys (build + the four QA-gauntlet stage models).
7. **Write `.claude/pipeline.config.md`** from `pipeline.config.template.md` with the confirmed values; show it back for approval.
8. **Continue to init** (below) using the freshly-written config.

## Init flow

The heaviest path. Run on first invocation when `{stories_dir}` is missing.

1. **Read the blueprint** (`{blueprint}`) — extract its phase mapping (→ sprint numbers, per config `sprint_labels`) and module/feature specs (→ topics, per config `topics`).
2. **Read the tech spec** (`{tech_spec}`) — especially its success-criteria and `api` sections (each endpoint usually implies ≥1 story). Build an in-memory **capability index** from the `stack`, `structure`, `schema`, `auth`, `api`, and `security` sections (resolve section refs via `tech_spec_sections`) so the tech-feasibility check runs per-story without re-reading.
3. **Derive topics** from the config `topics` table (topic → default sprint → blueprint source).
4. **Propose a draft story list per topic** (typically 3–8), each ≤ `{sp_cap}` SP. Unit-of-work signals: one story per route × purpose (list/detail/filter/submit); one per API endpoint with its own auth+validation; one per non-trivial reusable component family. Cross-check against the blueprint's surface inventory so no screen is missing.
5. **Ask for the primary owner once** (default `{default_owner}`). Present the full proposed list via `AskUserQuestion` (topic-by-topic if large); confirm sizes, splits, sprint assignments (pre-filled from config `topics`; always ask for `ask`-marked topics), and per-story owner.
6. **Per story, run the tech-feasibility gate** (below).
7. **Per story, run the design-linkage gate** (`design-linkage-gate.md`); create `{design_dir}` with `.gitkeep` if missing.
8. **Compute dependencies** — base UI shell first; list→detail→filter within a topic; auth before authed surfaces; admin-approval after the entity's create/edit.
9. **Write all files in one batch**, then generate `{index_path}` (`index-template.md`).
10. **Summarize:** stories per topic, per sprint, total SP, owner workload.

## Add flow

1. Ask: topic? title? user story? estimated SP? sprint (pre-fill from config `topics`; ask for `ask`-topics)? owner (default to most-recently-named this session, else ask)?
2. **SP > `{sp_cap}`** → divert to split before writing.
3. **Tech-feasibility gate** (below). 4. **Design-linkage gate** (`design-linkage-gate.md`). 5. **Suggest dependencies**; user confirms. 6. **Next sequence number** for the topic. 7. **Write the file**, regenerate `{index_path}`.

## Split flow

Triggered by `split <story-id>` or an add proposing > `{sp_cap}` SP.
1. Read the story; show its description + ACs. 2. **Propose 2–3 children**, each ≤ `{sp_cap}` SP, ACs redistributed; children inherit owner/topic/sprint unless overridden. 3. On confirm: move the original to `{archive_dir}` with `superseded_by: [new-ids]`; write the new files with fresh sequence numbers; **rewrite dependency arrays** in every story that pointed at the old ID. 4. Regenerate `{index_path}`.

## Update flow

Triggered by `update <story-id>`; user picks the field (`status`, `story_points`, `owner`, `dependencies`, `design`, `sprint`, `topic`).

- **Done-gate** (`task-states.md`): refuse `status: done` unless `tasks_populated: true` AND every task is `[completed]`/`[cancelled]`. On failure, print the offending tasks and exit without writing.
- **Un-block (`blocked → ready`):** allowed only once the recorded blocker is resolved. Flip the `[hold]` task back to `[new]`, append a one-line `## Notes` entry on how it cleared, keep `analyzed: true`. Never hand-edit a story to `done` to skip a blocker.

After any change, regenerate `{index_path}`.

## Restore flow

Triggered by `restore <story-id>` — bring a deferred backlog story back into an active sprint.
1. Read the story from `{backlog_dir}` (status `deferred`, carrying `original_sprint:`). 2. Confirm the deferral reason is resolved (split done / design uploaded / doc decided). 3. Move the file back to `{stories_dir}<topic>/`; set `status: draft` (or `ready` if still analyzed), clear `status: deferred`; restore `sprint:` from `original_sprint:` (or ask) and drop `original_sprint:`. 4. Regenerate `{index_path}` (the story leaves the Backlog section, rejoins its sprint). Re-run `/analyze-sprint` if it needs re-analysis.

## Tech-feasibility gate (init + add)

For each story, check every needed route / integration / table / auth assumption against the
capability index (tech spec `stack`/`schema`/`auth`/`api`/`security` sections). On a gap, ask:
- **(a)** Update `{tech_spec}` first (offer to draft the addition; pause).
- **(b)** Defer the story (drop from this run).
- **(c)** Record as an open question in the tech spec's `open_questions` section and write the story `status: blocked` with a `## Notes` pointer.
Default (a). Never silently write a story the architecture doesn't support.

## Lint flow

Read every `{stories_dir}**/story-*.md` (and `{backlog_dir}` for backlog-specific rules). Parse
frontmatter + Tasks. Report; **never modify**.

| Rule | Condition | Severity |
|---|---|---|
| oversize | `story_points > {sp_cap}` | error |
| broken-ref | a dependency ID has no matching file (search `{stories_dir}` + `{backlog_dir}`) | error |
| cycle | dependency graph has a cycle | error |
| status-inversion | `done` but a dependency isn't `done` | error |
| sprint-violation | Sprint N story depends on a Sprint > N story | error |
| untestable | `## Acceptance criteria` empty or only `TBD` | warning |
| unassigned | `owner:` missing/empty | error |
| untasked | `in-progress` but `tasks_populated: false` | warning |
| task-marker-mismatch | `tasks_populated: true` but Tasks empty/TODO-only | warning |
| premature-done | `done` but ≥1 task `new`/`started`/`hold` | error |
| invalid-task-state | task line missing `[state]` or unknown state | error |
| tech-arch-mismatch | story needs a capability absent from `{tech_spec}` | warning |
| missing-design | `design:` is `[]` | warning |
| design-not-found | `design:` path doesn't resolve under `{design_dir}` | error |
| template-chain-empty | `follows-template:` chain ends in empty `design:` | error |
| design-claim-mismatch | `design: none-needed` but ACs mention UI | warning |
| untagged-ac | `analyzed: true` but ≥1 AC lacks a `(unit\|e2e\|axe\|visual\|manual)` tag | warning |
| qa-pending | `done`/`code-reviewed`/`tests-generated`/`tested` — in the QA gauntlet but not yet `verified` | info |
| stage-failed-empty | a `*-failed` status but no open `- [ ]` item in that stage's section (`code-review-failed`→Code Review, `testing-failed`→Testing, `verification-failed`→Verification) | error |
| passed-with-open | a passed status (`code-reviewed`/`tested`/`verified`) but ≥1 open `- [ ]` item in that stage's section or an earlier one | error |
| deferred-parked | story in `{backlog_dir}` with `status: deferred` (informational; not an error) | info |
| stale | `draft` for > `{stale_days}` days, measured from `analyzed_date` or last git-commit date — **never** filesystem mtime | info |

Print a grouped report; suggest the fixing subcommand where applicable.

## Index flow

Regenerate `{index_path}` exactly per `.claude/pipeline/reference/index-template.md` (sprint
labels from config `sprint_labels`; includes the Backlog section and the CR/Gen/Test/Verify columns;
idempotent). **`manage-stories` is the sole `{index_path}` writer** — the four QA-chain skills don't
regenerate it; run `/manage-stories index` after a QA pass to refresh the board. **Multi-operator**
(any `.claude/operators/*.md`): group by **operator → sprint → topic**, each operator sprint headed by
its one-line goal from the profile `Sprints` table (per `operator-profile.md`); single-operator stays
sprint → topic.

## Operating rules

- **Every story has an owner** (single string; lint flags `unassigned`).
- **Never auto-generate ACs the blueprint/tech-spec doesn't support** — write `- [ ] TBD — needs founder input on <x>` instead.
- **Never populate `## Tasks`** — that's analyze-sprint's job.
- **Done only when** `tasks_populated: true` and every task `completed`/`cancelled`.
- **Design-linkage + tech-feasibility on every create** — never silently write an unsupported or UI-unlinked story.
- **Sprint from config `topics`** — pre-fill; ask for `ask`-topics; never invent. **Multi-operator** (any `.claude/operators/*.md`): a story's `owner` + `sprint` *is* its operator sprint `owner/N` (see `operator-profile.md`); set both so each story belongs to exactly one operator's sprint.
- **Never exceed `{sp_cap}` SP** — divert to split.
- **Dependencies are real IDs at write time.** **`{archive_dir}`/`{backlog_dir}`** hold superseded/deferred files — never delete history.
- **`{index_path}` is generated, not edited.** **First-run never overwrites** an existing story tree.

## Files this skill touches

May create/edit: `{index_path}`, `{stories_dir}<topic>/story-*.md`, `{archive_dir}` (split),
`{backlog_dir}` (restore), `{design_dir}.gitkeep` (if missing), and `.claude/pipeline.config.md`
(bootstrap only). With explicit confirmation it may append to the tech spec's `open_questions`
section (tech-feasibility option c). It never creates design source files.

## When to bail and ask

- Sequence-number collision → ask which to keep.
- A dependency refers to an archived story → ask whether to rewrite to its successor IDs.
- An ambiguous tech-feasibility gap → describe the interpretations, let the user pick.
- Blueprint/tech-spec changed since last init → run lint first, then add/update one-by-one; do not re-init.

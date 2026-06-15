---
name: execute-sprint
description: Builds a sprint's analyzed stories one at a time in dependency order — scaffolds the app on first run (per the project's stack profile), then writes the code and tests each story calls for, runs the gate, verifies every acceptance criterion, and marks the story done. A thin orchestrator that dispatches one sprint-story-builder subagent per story. The build pass downstream of /analyze-sprint.
---

# execute-sprint

The **build pass** downstream of `/analyze-sprint`. It takes one sprint, lines up its analyzed
stories, and builds them **one at a time in dependency order** — not inline, but as a **thin
orchestrator** that dispatches one `sprint-story-builder` subagent per story (on a per-story
model). The subagent implements code + tests, runs the gate, verifies every AC, and stamps the
story **done** in isolated context. The orchestrator resolves the sprint, orders the work,
dispatches, reads each result, handles escalation, and regenerates the index. It is the gate
that turns a `ready` story into a `done` one.

**This skill only executes `analyzed: true` stories.** It never analyzes, breaks down tasks, or
reconciles docs — if a story isn't ready or a doc gap surfaces, it stops and routes to
`/analyze-sprint`.

## Configuration

All paths/docs/constants/models/section-refs resolve from **`.claude/pipeline.config.md`** — read
it first. The **stack-specific half** (scaffold, gate commands, test toolchain, render command,
directory layout, toolchain preflight) lives in the stack profile named by config
(`.claude/pipeline/stack-profiles/{stack_profile}.md`) — this skill's orchestration logic is
stack-agnostic. Shared contracts it reuses:
- Dependency ordering → `.claude/pipeline/reference/topo-order.md`
- INDEX template → `.claude/pipeline/reference/index-template.md`
- Frontmatter/task states/done-gate → the reference docs (via `manage-stories`)

The per-story **build protocol** lives in `.claude/agents/sprint-story-builder.md`; this skill
owns the *orchestration* around it. Read `analyze-sprint` and `manage-stories` if anything is
ambiguous.

## What it builds

Stories describe the **production app** under `{app_dir}`, not the prototype. `{design_dir}` is the
visual reference to port from (per its `{design_ext}` format), never the thing shipped. The build
obeys `{tech_spec}` (the stack it declares) and follows `{design_doc}` + the linked prototype
screens.

## Working paths

Stories `{stories_dir}<topic>/story-*.md`, index `{index_path}`; tech spec `{tech_spec}`
(**source of truth** for stack/structure/schema/auth/api/routing/ui_rules/security/testing/env —
it **outranks** the prototype); design doc `{design_doc}`; prototype `{design_dir}*.{design_ext}`;
production app `{app_dir}` (layout per the stack profile).

## Model & orchestration

Per-story work runs in subagents so the orchestrator's context stays tiny (only story ids,
pass/fail, SHAs — never file dumps or test output). This isolates context and lets each story
run on the right-sized model.

- **Run the orchestrator on `{orchestrator_model}`** (its floor — the work is light, but it must reliably hold the serial-dispatch HARD RULE against the harness's "batch agents for speed" default; a weaker model slips there). Bump higher only for the first-run Scaffold if needed.
- **Each story's model = its `exec_model`** (`{default_exec_model}` default; `{escalation_model}` where analysis flagged it). Absent field → `{default_exec_model}`.
- **Auto-escalation:** a `{default_exec_model}` subagent returning `failed` escalates that one story to `{escalation_model}` (below). The escalation model failing too → the story is `blocked`.
- The subagent's `model` is set via the Agent tool per spawn.

## Input — the sprint

One argument, resolved exactly as `analyze-sprint` does — single-operator `N`/`Sprint N`/label, or
multi-operator `owner/N` per `operator-profile.md`. Absent/ambiguous → ask via `AskUserQuestion`.
Never invent a sprint.

## Pre-flight — align all stories

**Multi-operator guard (any `.claude/operators/*.md`).** The sprint is `owner/N`; **before any
mutation**, assert the current git branch is the operator's profile branch (`sprint/<owner>-N`) and
you're in their worktree — a mismatch is a **hard stop** (run `scaffold-plan.py operator <owner>
--sprint N`, then `cd` into the printed worktree). The dev server + Supabase bind the operator's
profile ports. Builds merge to `main` via PR. See `operator-profile.md`. (Single-operator: skip this
guard; build on the current branch as before.)

1. **Collect** every `{stories_dir}**/story-*.md` (exclude `{archive_dir}`, `{backlog_dir}`) whose `sprint:` matches (multi-operator: and whose `owner:` matches the resolved `owner/N`). Run the `manage-stories` lint (errors only); a structural error halts — fix via `/manage-stories` first. (Cycles are handled in step 3.)
2. **Require built-ready:** `analyzed: true` and `status: ready | in-progress | code-review-failed | testing-failed | verification-failed`. `draft`/un-analyzed → don't execute; list them, route to `/analyze-sprint <N>`. Already-`done`/`code-reviewed`/`tests-generated`/`tested`/`verified` → skip (report the count). A **`*-failed`** story (code-review / testing / verification) re-enters here: its build scope is the **union of open `- [ ]` items across `## Code Review Feedback`, `## Testing Feedback`, and `## Verification Feedback`** — the builder fixes those, checks them off, and returns it to `done`, from which it re-flows the QA gauntlet from stage 1 (`/code-review-sprint`).
   - **`blocked` stories aren't silently excluded.** Print each one's `## Notes` reason and ask if it's resolved. Yes → un-block it (`blocked → ready`, `[hold]` task → `[new]`) and queue it. No → leave it blocked, exclude it, treat as a blocked-subtree root for step 3.
3. **Order dependency-first** per `topo-order.md`. A within-sprint **cycle is a hard blocker → halt** (never fall back to INDEX order at build time). A cross-sprint dependency that isn't `done` → hard blocker.
4. **Toolchain preflight + scaffold:** per the stack profile's *Toolchain preflight*. If `{app_dir}` is absent → run the profile's **Scaffold**, commit it as the bootstrap; present → reuse.
5. **Print the execution plan** — the ordered story list with SP, deps, and per-story `exec_model`.

## Dispatch loop — one subagent per story

> ### ⚠️ HARD RULE — exactly ONE `Agent` tool-call per assistant message. No exceptions.
> Every "sequential" mention points here.
> - **Never** place two `sprint-story-builder` calls in one message, and **never** map the story list into a batch of Agent calls.
> - The harness runs same-message tool-uses **concurrently**. Two builders at once write atomic commits into the **same `{app_dir}` tree on the same branch** → corrupted tree, broken dependency order, broken escalation reset (which does `git checkout -- .` / `git clean -fd` and would wipe a sibling's work).
> - **This overrides any general guidance about batching agents for speed.** Builders share one branch — there is no speed win worth a corrupted tree.
> - **Multi-operator note:** isolation is *between* operators (each in their own worktree + branch, so two operators' sprints never collide); *within* a single operator's worktree this serial one-builder-at-a-time rule still holds in full.
> - **Strictly serial:** spawn one → await its `RESULT` → handle it → only then spawn the next.

Walk the ordered list as a serial loop. The orchestrator does **not** read design/docs or write
`{app_dir}` code — that's the subagent's job. For the **current** story:

1. **Read just the routing facts** — `exec_model` (default `{default_exec_model}`) and confirm its `dependencies:` are all `done`. A not-`done` dependency means it sits under a blocked/skipped root → **skip it** (part of that subtree; don't halt).
2. **Pre-dispatch self-check:** confirm the previous story's `RESULT` was received and handled. About to emit > 1 Agent call? Stop — emit only the first.
3. **Spawn exactly one `sprint-story-builder`** with `model` = the story's `exec_model`, passing `story_id`, the file path, `exec_model`, and `escalation: false`. It runs Steps 0–5 and returns a `RESULT` block.
4. **Parse `RESULT`** and act on `status`:
   - **`green`** → confirm cheaply (`git log -1`; the `tests:` line). Print the checkpoint. Don't re-run the suite. Carry forward the `manual_checks` line.
   - **`failed`** → if model was `{default_exec_model}`, **escalate** (below). If already `{escalation_model}`, the story is `blocked` → **skip its subtree and continue**.
   - **`blocked`** → recorded in `## Notes` (`status: blocked`). **Skip its subtree and continue** — don't halt the whole sprint.
5. **STOP — barrier.** Don't begin the next story until this one's `RESULT` is handled and its checkpoint printed. Then return to step 1 for the next *eligible* story (fresh message, single Agent call).

### Partial-sprint continuation — one blocked story doesn't kill the sprint
A `blocked` story (or an `{escalation_model}` `failed`) **no longer halts the run**:
1. Mark the story `blocked` (the subagent did, for `blocked`; for an escalation `failed`, the orchestrator sets it with the failing summary in `## Notes`).
2. Compute its **transitive dependents** in the sprint and mark them **skipped — blocked dependency**; don't dispatch them.
3. **Continue with the still-eligible stories** (no blocked/skipped dependency).
4. At end of sprint, report the **blocked subtree(s)** — root, reason, dependents skipped.

Only run-level blockers (a dependency **cycle**, an unavailable **toolchain**) halt the entire run.

### Escalation — default model failed → retry on the escalation model
When a `{default_exec_model}` subagent returns `failed`:
1. **Save the failed attempt's diff before discarding:** from `{app_dir}`, `git diff > /tmp/<story_id>-failed.patch` (+ list untracked), *then* `git checkout -- .` / `git clean -fd`. Per-task commits the attempt landed are kept.
2. **Stamp** `exec_model: {escalation_model}` and `escalated: true`; write the file.
3. **Spawn a fresh subagent with `model: {escalation_model}`**, passing `escalation: true`, a short prior-failure summary, **and the patch path** — so it mines the dead-end instead of replaying it.
4. Act on the result. The escalation model `failed`/`blocked` → the story is `blocked` → skip its subtree and continue.

### Checkpoint
One line per story — `✓ story-x done [{default_exec_model}] (6 tasks · 7 ACs · 14 tests green)`, `↑ story-y done [{escalation_model}, escalated] (…)`, `♻ story-v done [from verification-failed] (3 feedback items cleared across CR/Test/Verify · tests green)`, `⛔ story-z blocked — <reason>`, or `⤼ story-w skipped — depends on blocked story-z`. Continue automatically to the next eligible story; only a sprint-wide blocker (cycle/toolchain) halts. User may say "stop".

## Blockers — story-level (skip subtree) vs run-level (halt)

**Story-level** (mark one story `blocked`, skip its subtree, continue): its own dependency isn't
`done` · the gate can't be greened after both the default-model attempt and the escalation ·
an AC needs an external service (`{external_services}`/hosted infra) unavailable and un-stubbable ·
an AC is ambiguous/contradicts the docs (route that story to `/analyze-sprint`).

**Run-level** (halt the whole run): a within-sprint dependency **cycle** · the **toolchain** is
unavailable (per the stack profile preflight).

The subagent marks in-place state for blockers it detects and returns `status: blocked`. The
orchestrator skips-and-continues on story-level, halts on run-level, and either way **regenerates
`{index_path}` and reports** what built / blocked / skipped. Never check off an unsatisfied AC;
never edit an AC to make a test pass.

## After the sprint

1. **Regenerate `{index_path}`** per the `manage-stories` index flow.
2. **Print a summary** (from the `RESULT` blocks — never re-derived): stories done/blocked/skipped, model each ran on + which escalated, tasks completed, tests passing, commits. List blocked stories (reason + next step) and skipped stories (the blocked dependency that caused them).
3. **Retro line:** escalation rate; for each escalated story, which `exec_model` signal was present-but-unflagged at analysis (feeds analyze-sprint's signal list); total `(manual)`/`(visual)` checks outstanding across the `RESULT` `manual_checks` lines; a one-line blocked-reason tally.
4. **Point to the QA gauntlet:** build-green ≠ correct-safe-and-faithful — run `/code-review-sprint <N>` next (then `/generate-test-sprint`, `/qa-sprint`, `/verify-sprint`). Stories are `done`, at the head of the gauntlet. Any story that re-ran from a `*-failed` state this pass re-flows from stage 1 — re-check it through the chain (`--recheck`/`--reverify`).
5. *(Optional)* one end-of-sprint full gate run from `{app_dir}` as a belt-and-suspenders check.

## Operating rules

- **One subagent at a time, dependency-first, never parallel** (see HARD RULE). Never build a story before its dependencies are `done`.
- **The orchestrator stays thin** — dispatch, parse, escalate, regenerate INDEX; never read design/docs or write `{app_dir}` code (except the first-run Scaffold). Run on `{orchestrator_model}`.
- **Only `analyzed: true` stories execute.** **Code obeys `{tech_spec}`** (highest precedence); visuals follow `{design_doc}` + linked screens; the prototype never overrides the tech spec.
- **Tests mandatory** per the tech spec `testing` section + the stack profile. **Never edit an AC to make it pass** — halt and flag (reconciliation is `/analyze-sprint`'s job).
- **This skill never edits the planning docs.** **Atomic commits** referencing the story id. **Never touch `{backlog_dir}`/`{archive_dir}`.** **Never invent a sprint.**

## Files this skill touches

Subagents write: `{app_dir}**` (code/tests/config/migrations); `{stories_dir}<topic>/story-*.md`
(status, `tasks_populated`, `executed_date`, task markers, AC checkboxes, `## Notes`, and the
`## Code Review Feedback` / `## Testing Feedback` / `## Verification Feedback` checklists — appending
un-greenable test failures and checking off feedback items a re-run clears). The
orchestrator writes: `{stories_dir}<topic>/story-*.md` (`exec_model`/`escalated` on escalation)
and `{index_path}`. Neither writes the planning docs. The first-run Scaffold is performed by the
orchestrator per the stack profile.

## When to bail and ask

- Sprint matches zero stories → list existing sprints, ask.
- Stories aren't `analyzed`/`ready` → list them, route to `/analyze-sprint <N>`.
- A `blocked` story → surface its reason, ask if resolved; yes → un-block + queue; no → exclude it + its subtree.
- A within-sprint **cycle** → halt, route to `/manage-stories lint` (never fall back to INDEX at build time).
- A cross-sprint dependency isn't `done` → halt (build the earlier sprint first).

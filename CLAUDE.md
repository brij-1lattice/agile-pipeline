# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repository is

This repo **is** a Claude Code pipeline — a set of Markdown **skills** (slash commands), **agents**
(subagent definitions), and **reference contracts**. There is **no application code, no build, no
test suite, and no lint command here.** Everything is prose-as-program: the files are instructions
Claude reads at runtime. "Running" the pipeline happens in a *target* project after installing these
files into its `.claude/` (see `README.md`), not in this repo.

So a change here = editing Markdown. There's nothing to compile or execute to validate it. Verify by
reading: trace the affected skill/agent/contract end-to-end and confirm the invariants below still hold.

## The pipeline (what these files orchestrate)

A spec becomes **stories** → grouped into **sprints** → built by an isolated subagent (code + tests +
AC verification) → run through a four-stage QA gauntlet in fresh context. The stages, each its own
skill consuming the status the prior produced:

```
/finalize-tech-spec → /manage-stories → /analyze-sprint N → /execute-sprint N
  → /code-review-sprint N → /generate-test-sprint N → /qa-sprint N → /verify-sprint N
```

Status lifecycle (the spine everything keys off — defined once in `pipeline/reference/frontmatter-schema.md`):

```
draft → ready → in-progress → done
done → code-reviewed → tests-generated → tested → verified (terminal)
       code-review-failed / testing-failed / verification-failed  (EXECUTABLE — re-run /execute-sprint)
       blocked · deferred
```

## Architecture & the invariants you must preserve

These are the design decisions that span multiple files. Breaking one silently corrupts the pipeline.

1. **Nothing project-specific is hardcoded in skills or agents.** Every path, document name, constant,
   model, vocabulary term, and tech-spec section is resolved at runtime from `.claude/pipeline.config.md`
   (template: `pipeline.config.template.md`). Skills reference values as `{working_root}`, `{app_dir}`,
   `{tech_spec}`, etc., and cite tech-spec sections **by role** (`security`, `api`, `schema`) through the
   `tech_spec_sections` map — never a raw `§N`. When editing a skill, keep using the placeholders; do not
   bake in a path or a section number.

2. **Single source of truth per contract.** Shared rules live once under `pipeline/reference/` and every
   skill *points at* them rather than restating them:
   - `frontmatter-schema.md` — story fields, body-section order, status lifecycle
   - `review-feedback-format.md` — the three feedback sections (severity legends, `[true]`/`[justified]`/`[choice]` tags, what blocks)
   - `task-states.md` · `ac-method-tags.md` · `design-linkage-gate.md` · `topo-order.md` · `index-template.md`

   If you change a rule (e.g. add a status, rename a field, alter what blocks a gate), edit the reference
   file **and** audit every skill/agent that consumes it — a status name appears in `frontmatter-schema.md`,
   `execute-sprint`, the QA skills, `index-template.md`, and `manage-stories`. Drift between them is the
   primary failure mode for this codebase.

3. **The stack profile is the only framework-specific code.** Scaffold, gate commands, test toolchain,
   render command, and directory layout live in `pipeline/stack-profiles/<name>.md` (default
   `nextjs14-supabase`). Orchestration logic (dispatch, escalation, partial-continuation, audit) must stay
   stack-agnostic. A new profile must provide the headings listed in `pipeline/stack-profiles/README.md`,
   matched by role.

4. **Status-pipelining, not parallelism.** The four QA stages consume **disjoint** input statuses, so they
   never write the same story file. But three share the target's `{app_dir}` checkout and/or a fixed
   dev/DB port — true cross-session parallelism needs git-worktree + per-stack isolation. The QA skills
   deliberately **never write `INDEX.md`** (to avoid racing on it); `manage-stories index` is the sole
   writer of the board. Preserve both properties when editing a QA skill.
   **One carve-out — `generate-test-sprint` fans out its authors *within* a run without worktrees.**
   Test *authoring* needs no port and each `qa-test-author` writes a distinct QA-namespace file, so the
   authors run **in parallel** and the only shared resource — git — is deferred: authors are write-only,
   and the orchestrator does a single `typecheck`/`lint` pass + **one bulk commit** after they return.
   (Cross-*session* parallelism of the whole skill still needs a worktree.) This is the one place a QA
   skill commits to `{app_dir}`; the other three never write the repo from the orchestrator.
   The **read-only** stages dispatch in parallel by design — `code-review-sprint` (reviewers never
   write) and `verify-sprint`'s `design: none-needed` **code-only** audits (no render, no port) both
   fan out concurrently; only `verify-sprint`'s *render* audits and the `qa-sprint` runners stay serial
   (shared port/stack). Don't "fix" the read-only fan-out back to one-at-a-time.

5. **Self-healing via executable failure states.** A `*-failed` story carries open `- [ ]` blocking items
   in its own feedback section (no separate ledger). `/execute-sprint` picks these up, fixes them in place,
   clears the stale downstream date stamps, returns the story to `done`, and it re-flows the gauntlet from
   stage 1. `status` is the single honest source the INDEX projects from — keep it that way.

6. **`execute-sprint`'s serial HARD RULE.** The build orchestrator dispatches **exactly one**
   `sprint-story-builder` per assistant message and awaits its `RESULT` before the next — builders share
   one `{app_dir}` branch and concurrent ones corrupt the tree (and escalation's `git checkout -- .` /
   `git clean -fd` would wipe a sibling's work). This **overrides** the general "batch agents for speed"
   guidance. Never weaken it. (`qa-sprint` runners and `verify-sprint` auditors stay serial too — shared
   dev/DB port. Only `generate-test-sprint`'s write-only authors parallelize — see #4.)

   **Liveness — a hung worker must never stall the orchestrator.** While awaiting a subagent the
   orchestrator is blocked *inside* the Agent tool-call and can't poll or kill it, so hangs are
   prevented at the source: every gate/test/render command is non-watch and wrapped in
   `timeout {gate_timeout}` (stack profile + config), and every worker carries a **liveness contract**
   — always emit a `RESULT`, even on a `timeout`-kill (exit `124`) or unrecoverable state. The
   orchestrators define a **no-RESULT recovery** (mark the story `blocked`/`infra-blocked` and continue,
   never re-await a dead child). When editing a worker agent or a dispatch loop, keep both halves.

7. **Verify-never-summarize for judgment findings.** Code-review and verification findings must cite exact
   `file:line` on **both** sides (the build defect and the contract it violates). This rule exists because
   a summary-only pass produced false positives. Keep it in any edit to `review-feedback-format.md` or the
   QA skills.

8. **`done` and gate sign-offs are gated, never gamed.** `done` requires all tasks `[completed]`/`[cancelled]`
   and all ACs `[x]`. The builder never checks off an unsatisfied AC or edits an AC/test to make it pass —
   a red QA test is a production-code defect (the one documented exception, with a two-sided citation, is in
   `review-feedback-format.md`).

## Layout

```
skills/<name>/SKILL.md          # the eight slash commands (frontmatter: name + description)
agents/<name>.md                # sprint-story-builder, qa-test-author (per-story workers)
pipeline/reference/*.md         # single-source contracts
pipeline/stack-profiles/*.md    # the only stack-specific part
pipeline.config.template.md     # per-project binding (copied to .claude/pipeline.config.md)
README.md                       # the single guide — overview, install, run, reference
```

## Conventions when editing

- **Match the existing voice.** Skills/agents/contracts are densely written, imperative, and cross-link by
  relative path (`pipeline/reference/foo.md`, `.claude/agents/bar.md`). New files should read the same.
- **A skill file** is `skills/<name>/SKILL.md` with YAML frontmatter (`name`, `description`) and a body
  that always opens by resolving config first, then names the reference contracts it reuses.
- **When you touch the lifecycle, the feedback format, or a field name**, update `README.md` too — it
  restates the lifecycle and the QA-concurrency table for operators, and must not drift from the
  contracts.
- **Commits are the user's call.** Don't commit or push unless asked.

---
name: generate-test-sprint
description: Writes the adversarial test suite for each code-reviewed story — the empty/error/permission/boundary cases the builder's happy-path tests skipped — into the app's QA test namespace, then marks the story tests-generated so qa-sprint can run them. Stage 2 of the QA gauntlet, downstream of /code-review-sprint. A thin orchestrator that dispatches one qa-test-author subagent per story.
---

# generate-test-sprint

**Stage 2 of the QA gauntlet**, downstream of `/code-review-sprint`. The builder wrote the
happy-path tests its ACs named; a real QA team writes the *adversarial complement* — the
empty/error/permission/boundary cases that break weak code. This skill authors those tests (it does
**not** run them — `qa-sprint` does), then advances each story to **`tests-generated`** so the
running stage can pick it up.

It is a **thin orchestrator** that dispatches one `qa-test-author` subagent per story on
`{test_gen_model}`. The author writes durable tests into the app's QA namespace and commits them;
the orchestrator reads each result, sets the status, and reports.

## Configuration

All paths/docs/constants/models resolve from **`.claude/pipeline.config.md`** — read it first. The
**stack-specific half** (QA test namespace, test toolchain, gate commands) lives in the stack
profile (`.claude/pipeline/stack-profiles/{stack_profile}.md`). Shared contracts:
- AC method tags (what the adversarial tests must *not* duplicate) → `.claude/pipeline/reference/ac-method-tags.md`
- Frontmatter / statuses → `.claude/pipeline/reference/frontmatter-schema.md`
- Sprint resolution & dependency ordering → reuse `execute-sprint`

The per-story **authoring protocol** lives in `.claude/agents/qa-test-author.md`; this skill owns
the orchestration around it. **Model:** each author runs on `{test_gen_model}` (absent →
`{escalation_model}` → `{default_exec_model}`).

## Input — the sprint

One argument resolved as `execute-sprint` does (single-operator `N`/label, or multi-operator
`owner/N` per `operator-profile.md` — authored in that operator's worktree). Absent/ambiguous → ask
(show how many stories are already `tests-generated`+). `--recheck` re-authors for a re-built story;
a single story id does
just that one. **`--recheck` is also how a story's QA suite is re-authored when its surface changed
shape** (a resolved `[choice]` / changed AC the builder shouldn't patch test-by-test — see
`review-feedback-format.md`); the author updates the existing QA files **in place** (idempotent, no
duplicates). Never invent a sprint.

## Selection

1. Collect `{stories_dir}**/story-*.md` (exclude `{archive_dir}`, `{backlog_dir}`) whose `sprint:` matches (multi-operator: and whose `owner:` matches the resolved `owner/N`) and `status: code-reviewed`. (`code-reviewed` is the input — passed code review, ready for adversarial tests.)
2. Skip `tests-generated`/`tested`/`verified` unless `--recheck`. `done`/`code-review-failed` → not yet eligible; route to `/code-review-sprint <N>`. Report the skip count.

## Dispatch loop — one subagent per story

> ### ⚠️ HARD RULE — exactly ONE `Agent` tool-call per assistant message. No exceptions.
> The author writes atomic commits into the **same `{app_dir}` tree on the same branch**; two at
> once corrupt each other. Spawn one → await its `RESULT` → handle it → only then spawn the next.
> **This overrides any general guidance about batching agents for speed.**
> (To run this stage truly concurrently with `qa-sprint` or `execute-sprint`, isolate it in a
> separate git worktree — they share `{app_dir}` otherwise.)

Walk the selected stories in any order (no inter-story dependency at this stage). For the **current**
story:

1. **Spawn exactly one `qa-test-author`** on `{test_gen_model}`, passing `story_id` + the file path. It runs the authoring protocol and returns a `RESULT` block.
2. **Parse `RESULT`** and act on `status`:
   - **`generated`** → confirm cheaply (`git log -1`; the `tests_added:` line). Set `status: code-reviewed → tests-generated`, stamp `test_gen_date: <today>`. Print the checkpoint.
   - **`blocked`** → the author couldn't author meaningful tests (untestable as built / an unavailable un-stubbable external service). It set `status: blocked` + a `## Notes` reason; record and continue (don't halt the sprint).
3. **STOP — barrier.** Don't begin the next story until this one's `RESULT` is handled. Then the next story (fresh message, single Agent call).

### Checkpoint
One line per story — `✓ story-x tests-generated [{test_gen_model}] (6 qa tests added · 2 unit · 4 e2e)`, or `⛔ story-y blocked — <reason>`. Continue automatically; user may say "stop".

## After the sprint

1. **Print a summary** (from the `RESULT` blocks): stories `tests-generated` vs `blocked`, total adversarial tests added, files touched. Point `tests-generated` stories at `/qa-sprint <N>` to run them. List blocked stories (reason + next step).
2. End with: "run `/manage-stories index` to refresh the board." **Do not regenerate `{index_path}`** yourself (parallel-chain skill).

## Operating rules

- **One subagent at a time** (see HARD RULE) — authors share one `{app_dir}` branch.
- **The orchestrator stays thin** — dispatch, parse, set status; never write `{app_dir}` or author tests itself. Run on `{orchestrator_model}`.
- **Authors write tests only** — never production code, never an AC, never the running of the suite. A story stays `code-reviewed` if authoring failed; it never skips ahead.
- **The only status move is `code-reviewed → tests-generated | blocked`.** **Never regenerate `{index_path}`.** **Never invent a sprint.**

## Files this skill touches

Subagents write: `{app_dir}` QA test files (the namespace from the stack profile) + atomic commits.
The orchestrator writes: `{stories_dir}<topic>/story-*.md` — `status` (`code-reviewed →
tests-generated | blocked`) + `test_gen_date`. Neither writes `{index_path}`, production code, or
the planning docs.

## When to bail and ask

- Sprint matches zero `code-reviewed` stories → list sprints, route earlier-stage stories to `/code-review-sprint <N>`.
- A story's adversarial cases can't be written without an unavailable service → author returns `blocked`; record and continue.

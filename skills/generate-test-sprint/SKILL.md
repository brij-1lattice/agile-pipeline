---
name: generate-test-sprint
description: Writes the adversarial test suite for each code-reviewed story — the empty/error/permission/boundary cases the builder's happy-path tests skipped — into the app's QA test namespace, then marks the story tests-generated so qa-sprint can run them. Stage 2 of the QA gauntlet, downstream of /code-review-sprint. A thin orchestrator that fans out write-only qa-test-author subagents in parallel, then validates and bulk-commits their tests.
---

# generate-test-sprint

**Stage 2 of the QA gauntlet**, downstream of `/code-review-sprint`. The builder wrote the
happy-path tests its ACs named; a real QA team writes the *adversarial complement* — the
empty/error/permission/boundary cases that break weak code. This skill authors those tests (it does
**not** run them — `qa-sprint` does), then advances each story to **`tests-generated`** so the
running stage can pick it up.

It is a **thin orchestrator** that dispatches the `qa-test-author` subagents — **in parallel**, one
per story, on `{test_gen_model}`. The authors write durable tests into the app's QA namespace
(write-only, no git); the orchestrator then runs a single `typecheck`/`lint` validate pass, makes one
bulk commit, sets each story's status, and reports.

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
`owner/N` per `operator-profile.md` — authored in that operator's checkout, i.e. its worktree only in
`worktree` isolation). Absent/ambiguous → ask
(show how many stories are already `tests-generated`+). `--recheck` re-authors for a re-built story;
a single story id does
just that one. **`--recheck` is also how a story's QA suite is re-authored when its surface changed
shape** (a resolved `[choice]` / changed AC the builder shouldn't patch test-by-test — see
`review-feedback-format.md`); the author updates the existing QA files **in place** (idempotent, no
duplicates). Never invent a sprint.

## Selection

1. Collect `{stories_dir}**/story-*.md` (exclude `{archive_dir}`, `{backlog_dir}`) whose `sprint:` matches (multi-operator: and whose `owner:` matches the resolved `owner/N`) and `status: code-reviewed`. (`code-reviewed` is the input — passed code review, ready for adversarial tests.)
2. Skip `tests-generated`/`tested`/`verified` unless `--recheck`. `done`/`code-review-failed` → not yet eligible; route to `/code-review-sprint <N>`. Report the skip count.

## Dispatch — fan out authors in parallel, then one bulk commit

Authors are **write-only** (they leave test files on disk; they never touch git) and each writes a
**distinct** QA-namespace file, so — unlike the serial builder/QA-runner stages — they have no shared
git-commit race and **run in parallel**. The orchestrator does the single validate pass and the one
bulk commit after they return.

> ### ⚠️ Fan-out rule — parallel authors, but never two on the same file.
> Spawn the batch of `qa-test-author` agents **concurrently** (multiple `Agent` calls in one message;
> the harness runs same-message tool-uses in parallel). The one hazard is two authors writing the
> *same* file at once — so first **partition** the selected stories by QA-namespace target: stories
> mapping to distinct files fan out together; any group that would touch one shared file (same source
> surface → same `*.qa.test.ts`) runs **serially within that group**. Authors do **not** commit — so
> there is no tree-corruption risk from concurrency, only the same-file write to avoid.

1. **Partition & fan out.** Group the selected stories so no two concurrent authors target the same QA
   file; spawn each group's `qa-test-author` agents in parallel on `{test_gen_model}`, passing
   `story_id` + the file path. Each runs the authoring protocol and returns a `RESULT` block (with its
   `files:` line). Collect every RESULT before proceeding.
2. **Sort the results.** Split `generated` from `blocked`. A `blocked` author set its story `status:
   blocked` + a `## Notes` reason (untestable as built / unavailable un-stubbable service) — record and
   continue; it contributes no files.
3. **Validate once.** Run the stack profile's cheap checks **a single time** over the QA namespace —
   `pnpm typecheck` + `pnpm lint` (bounded by `timeout {gate_timeout}`). Green → proceed. Red → the
   error is in one author's file: fix it inline (test code only) or re-dispatch that one author, then
   re-check. Never run the suite for pass/fail (that's `qa-sprint`).
4. **One bulk commit.** Commit all `generated` stories' QA files together —
   `test(qa): sprint <N> adversarial tests` — ending with the repo's Co-Authored-By trailer
   convention (match `git log`; multi-operator: add the `Operator: <owner>` trailer). One commit for
   the batch, not per story.
5. **Set statuses.** For each `generated` story, `status: code-reviewed → tests-generated`, stamp
   `test_gen_date: <today>`. (`blocked` stories already carry their status from step 2.)

### Checkpoint
One line per story — `✓ story-x tests-generated [{test_gen_model}] (6 qa tests added · 2 unit · 4 e2e)`, or `⛔ story-y blocked — <reason>` — printed after the batch settles, plus the single bulk-commit SHA. User may say "stop".

## After the sprint

1. **Print a summary** (from the `RESULT` blocks): stories `tests-generated` vs `blocked`, total adversarial tests added, files touched. Point `tests-generated` stories at `/qa-sprint <N>` to run them. List blocked stories (reason + next step).
2. End with: "run `/manage-stories index` to refresh the board, then `/clear` before `/qa-sprint <N>` — each stage runs fresh from `status`, so clearing keeps the orchestrator lean." **Do not regenerate `{index_path}`** yourself (parallel-chain skill).

## Operating rules

- **Authors run in parallel; never two on the same QA file** (see Fan-out rule). They're write-only, so concurrency is safe — partition by target file to avoid the one same-file write hazard.
- **The orchestrator owns git + validation** — it dispatches, runs the single `typecheck`/`lint` pass, makes the **one bulk commit**, and sets status; it never *authors* tests or writes production code. Run on `{orchestrator_model}`.
- **Authors write tests only** — never production code, never an AC, never a commit, never the running of the suite. A story stays `code-reviewed` if authoring failed; it never skips ahead.
- **The only status move is `code-reviewed → tests-generated | blocked`.** **Never regenerate `{index_path}`.** **Never invent a sprint.**

## Files this skill touches

Subagents write: `{app_dir}` QA test files (the namespace from the stack profile) — **files only, no
commits**. The orchestrator writes: the **single bulk commit** of those QA files, and
`{stories_dir}<topic>/story-*.md` — `status` (`code-reviewed → tests-generated | blocked`) +
`test_gen_date`. Neither writes `{index_path}`, production code, or the planning docs.

## When to bail and ask

- Sprint matches zero `code-reviewed` stories → list sprints, route earlier-stage stories to `/code-review-sprint <N>`.
- A story's adversarial cases can't be written without an unavailable service → author returns `blocked`; record and continue.

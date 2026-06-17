---
name: qa-sprint
description: Runs the adversarial test suite generated for each tests-generated story, triages the failures, writes them into the story's own Testing Feedback section, and moves the story to tested (all green) or testing-failed (real failures to fix). Stage 3 of the QA gauntlet, downstream of /generate-test-sprint. Runs on the cheaper test-running model.
---

# qa-sprint

**Stage 3 of the QA gauntlet**, downstream of `/generate-test-sprint`. The expensive model *designed*
the adversarial tests; this stage is the cheap, mechanical other half — **run them, triage what
fails, record it.** It turns a `tests-generated` story into a **`tested`** one when the adversarial
suite is green, or into a **`testing-failed`** one when a real failure surfaces — writing each
failing test into that story's own **`## Testing Feedback`** section so the **next `/execute-sprint`
run fixes it in place**.

It does **not** write production code, **not** author new tests (that's stage 2), and **not** edit
ACs — it runs the suite and records results. The only status move is
`tests-generated → tested | testing-failed`.

## Configuration

All paths/docs/constants/models resolve from **`.claude/pipeline.config.md`** — read it first. The
**stack-specific half** (QA test namespace, gate/test commands, toolchain preflight) lives in the
stack profile (`.claude/pipeline/stack-profiles/{stack_profile}.md`). Shared contracts:
- Testing Feedback item format → `.claude/pipeline/reference/review-feedback-format.md`
- Frontmatter / statuses → `.claude/pipeline/reference/frontmatter-schema.md`
- Sprint resolution → reuse `execute-sprint`

**Model:** spawn runners on `{test_run_model}` (absent → `{default_exec_model}`).

## Input — the sprint

One argument resolved as `execute-sprint` does (single-operator `N`/label, or multi-operator
`owner/N` per `operator-profile.md`). Absent/ambiguous → ask (show how many stories are already
`tested`+). `--recheck` re-runs for a re-built story; a single story id does just that one. Never
invent a sprint.

## Selection

1. Collect `{stories_dir}**/story-*.md` (exclude `{archive_dir}`, `{backlog_dir}`) whose `sprint:` matches (multi-operator: and whose `owner:` matches the resolved `owner/N`) and `status: tests-generated`. (`tests-generated` is the input — adversarial tests authored, not yet run.)
2. Skip `tested`/`verified` unless `--recheck`. `code-reviewed`/`testing-failed` → not yet eligible; route to `/generate-test-sprint` or `/execute-sprint`. Report the skip count.

## Orchestration — one runner per story, serial

Tests run against the local stack (a dev server + the local Supabase stack), so **runners are
serial** — one story's suite at a time, to avoid port/DB contention. (To run this stage concurrently
with another writing stage, isolate it in a separate git worktree + stack.) **Reuse one stack per
session** per the stack profile's *Render command* note — boot the dev server + Supabase once at the
first runner and keep it up (`reuseExistingServer`) so later stories skip the tens-of-seconds boot.
**Multi-operator:** bind
the stack to the operator's profile ports (`web`/`supabase` from their `.claude/operators/<owner>.md`)
so two operators' stacks coexist; see `operator-profile.md`. Each
runner is read-mostly (runs tests, captures output/artifacts; **never** writes `{app_dir}` source or
story files); the **orchestrator does all story writes** after it returns. **It does not regenerate
`{index_path}`** (parallel-chain skill — print a `/manage-stories index` reminder instead).

> ### ⚠️ HARD RULE — exactly ONE `Agent` tool-call per assistant message.
> Spawn one runner → await its `RESULT` → handle it → only then the next. Test runs share the local
> stack; two at once collide on ports/DB.
> **Liveness:** you're blocked inside the Agent call while awaiting — you can't kill a hung runner,
> so hangs are prevented at the source (every command is `timeout {gate_timeout}`-bounded and the
> runner always emits a RESULT). A dispatch that still returns no RESULT is recovered in *After the
> runs* (treated as `infra-blocked`); never sit re-awaiting a dead runner.

Spawn each runner on `{test_run_model}` with the **Per-story run protocol** below, plus `story_id`
and the file path.

## Per-story run protocol (runs inside each runner)

1. **Locate the story's adversarial tests** — the QA namespace files for this story (per the stack profile's *QA test toolchain*: `{app_dir}e2e/qa/` + `*.qa.test.ts`).
2. **Run them** via the stack profile's test commands (the QA-namespace subset), **time-bounded** (`CI=true timeout {gate_timeout}`, non-watch, per the profile), against the local stack with `{external_services}` stubbed. Capture the verbatim failures. A command that hits `{gate_timeout}` (exit `124`) is **not** a hang to wait on — record it (a stuck suite is `infra-blocked` if nothing ran, or a failure for the specific test that wouldn't terminate).
3. **Triage each failure — fail-closed.** A failure is a **real defect by default; record it.** You may downgrade one to flaky/infra **only after a confirmed clean re-run** (re-run the failing test once: still red, or red-then-green-then-red → record it; cleanly green on the honest re-run → note as flaky, don't record). When the cause is genuinely ambiguous, **record it** — a false `testing-failed` costs a build cycle; a buried real defect ships. Don't fix anything.
4. **Return the RESULT block** — the failing tests, each with its assertion + `file:line`.

### RESULT block (the runner's entire substantive output)

```
RESULT
story: <story_id>
status: green | failures | infra-blocked
ran: <n qa tests run — unit/e2e split>
failures:
- test: <test name>   file: <file:line>
  expected: <one line>   got: <one line>
notes: <≤2 lines — flaky/infra flags, what was stubbed>
```

`status: green` only when every adversarial test passed. `infra-blocked` if the stack/toolchain
couldn't run the suite at all (per the profile preflight).

**Liveness contract — always emit a RESULT.** The orchestrator is blocked awaiting this block and
cannot interrupt you. Run every command time-bounded (`timeout {gate_timeout}`) so nothing can hang
you; on a timeout, toolchain failure, or any unrecoverable state, stop and return a RESULT —
`failures` (with the offending test) or `infra-blocked` (suite couldn't run) — naming the cause in
`notes:`. Never end your turn without the block.

## After the runs — the orchestrator writes

For each story (orchestrator-only — runners wrote nothing to the story):

1. **Write failures into the story's `## Testing Feedback`** per `review-feedback-format.md`: one open `- [ ]` per failing test (name — assertion — `file:line`). Append (don't wipe `- [x]` history).
2. **Set the status** (the only status move; never revert past `tests-generated`):
   - zero failures → `status: tests-generated → tested`.
   - ≥1 failure → `status: tests-generated → testing-failed`.
   - Either way stamp `test_date: <today>`.
   - `infra-blocked` → leave the story `tests-generated`, report it, don't fabricate a pass.
   - **No parseable `RESULT`** (empty / truncated / dead runner) → treat like `infra-blocked`: leave the story `tests-generated`, note "runner returned no RESULT — recovered, re-run `/qa-sprint`", and continue to the next story. Don't re-await a dead runner and don't fabricate `tested`. (Runners are read-only, so there's no tree to clean up.)
3. **Print a summary:** stories `tested` vs `testing-failed`, failing tests per story, any infra-blocked re-runs. Point `testing-failed` stories at `/execute-sprint <N>` to fix and re-`done` (→ re-flow), `tested` stories at `/verify-sprint <N>`. End with: "run `/manage-stories index` to refresh the board, then `/clear` before `/verify-sprint <N>` — each stage runs fresh from `status`, so clearing keeps the orchestrator lean."

## Operating rules

- **Run, don't fix.** Never edit `{app_dir}`, never author tests, never edit an AC. A failure becomes a `## Testing Feedback` item the next build run fixes.
- **The only status move is `tests-generated → tested | testing-failed`** — never revert further, never touch an out-of-stage story.
- **`testing-failed` ⇔ ≥1 open `## Testing Feedback` item.** A failing test is objectively actionable — no `[justified]`/`[choice]` here.
- **Fail-closed triage:** record by default; downgrade to flaky **only** after a confirmed clean re-run, and record anything genuinely ambiguous. Don't record an infra non-run as a story defect (that's `infra-blocked`).
- **Never regenerate `{index_path}`** (parallel-chain skill). **Never invent a sprint.**
- **Safe to interrupt.** State lives in story frontmatter — selection is by `status: tests-generated`, so stop anytime, `/clear`, and re-run `/qa-sprint <N>`: it resumes from where it stopped (already-`tested` stories are skipped). Clearing mid-run keeps the serial loop's context flat.

## Files this skill touches

Orchestrator writes: `{stories_dir}<topic>/story-*.md` — `status` (`tests-generated → tested |
testing-failed`) + `test_date` + the `## Testing Feedback` section. Runner subagents write
**nothing** to the repo (run tests, capture throwaway output/artifacts, return RESULT). Not
`{index_path}`, not `{app_dir}` source, not the planning docs.

## When to bail and ask

- Sprint matches zero `tests-generated` stories → list sprints, route earlier-stage stories onward.
- The toolchain/stack can't run the suite → report `infra-blocked`; never pass off a non-run as `tested`.

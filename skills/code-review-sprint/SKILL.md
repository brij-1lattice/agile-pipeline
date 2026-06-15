---
name: code-review-sprint
description: Independent engineering code review of a built sprint — reads each done story's build diff, tests, and the tech-spec security/api/schema/auth rules in fresh context, writes real findings into the story's own Code Review Feedback section, and moves the story to code-reviewed (clean) or code-review-failed (gaps to fix). Stage 1 of the QA gauntlet, downstream of /execute-sprint.
---

# code-review-sprint

**Stage 1 of the QA gauntlet**, downstream of `/execute-sprint`. The build gate proves *"the tests
I wrote pass"* — not *"this code is correct, safe, and robust."* A self-written suite encodes the
same blind spots as the code: a missing authz check, an unhandled empty/error path, a test that
asserts nothing. This skill is the independent engineering review — **per story, in fresh context**,
reading the diff that built the story against the tech-spec contract it must honor.

It turns a `done` story into a **`code-reviewed`** one when the code is sound, or into a
**`code-review-failed`** one when it isn't — writing the real gaps into that story's own
**`## Code Review Feedback`** section so the **next `/execute-sprint` run fixes them in place**.
There is **no separate ledger file and no separate fix story** — the story owns its findings.

It does **not** edit `{app_dir}`, **not** touch scope/ACs, and makes only the status move
`done → code-reviewed | code-review-failed`. A review produces *findings written into the story*,
never silent rework.

## Configuration

All paths/docs/section-refs resolve from **`.claude/pipeline.config.md`** — read it first. Shared
contracts:
- Code Review Feedback item format (engineering severity, tags, two-sided citation) → `.claude/pipeline/reference/review-feedback-format.md`
- Frontmatter / statuses / body sections → `.claude/pipeline/reference/frontmatter-schema.md`
- AC method tags → `.claude/pipeline/reference/ac-method-tags.md`
- Sprint resolution & dependency ordering → reuse `analyze-sprint`/`execute-sprint`

Key paths: stories `{stories_dir}<topic>/story-*.md`; built app `{app_dir}`; tech spec
`{tech_spec}` — review against its `security`/`api`/`schema`/`auth` sections (resolve by role via
`tech_spec_sections`, **never** a raw `§N`). **Model:** spawn auditors on `{code_review_model}`
(absent → `{escalation_model}` → `{default_exec_model}`).

## Input — the sprint

One argument resolved as `execute-sprint` does (single-operator `N`/label, or multi-operator
`owner/N` per `operator-profile.md` — reviews that operator's branch diffs). Absent/ambiguous → ask
(show how many stories are already `code-reviewed`+). `--recheck` re-reviews
`code-review-failed`/`code-reviewed` stories; a single story id reviews just that one. Never invent
a sprint.

## Selection

1. Collect `{stories_dir}**/story-*.md` (exclude `{archive_dir}`, `{backlog_dir}`) whose `sprint:` matches (multi-operator: and whose `owner:` matches the resolved `owner/N`) and `status: done`. (`done` is the input — built, not yet code-reviewed.)
2. Skip `code-reviewed`/`tests-generated`/`tested`/`verified` unless `--recheck`. A `code-review-failed` story must be re-built to `done` (via `/execute-sprint`) before re-review — route it there. Report the skip count.
3. Stories with no `{app_dir}` diff (pure content/doc) still get a light review (the tech-spec contract still applies); note reduced surface.

## Orchestration — fresh context per story, parallel-safe

Each story is reviewed by **one freshly-spawned subagent** so its judgment isn't anchored by the
builder's rationalizations. The reviewers are **read-only** — they never write `{app_dir}` or story
files — so there's **no shared-tree hazard and no serial constraint**: you **may** dispatch several
reviewers concurrently. The **orchestrator does all writes** (the story's status + `code_review_date`
+ `## Code Review Feedback` section) after reviews return. **It does not regenerate `{index_path}`**
(parallel-chain skill — print a one-line `/manage-stories index` reminder instead).

Spawn each reviewer (a general read-only subagent) on `{code_review_model}` with the **Per-story
review protocol** below, plus `story_id`, the file path, and the relevant `{tech_spec}`
`security`/`api`/`schema`/`auth` sections. Each returns one **REVIEW block**.

## Per-story review protocol (runs inside each reviewer)

> **The cardinal rule — verify, never summarize** (per `review-feedback-format.md`). Every finding
> cites exact `file:line` on BOTH sides — the offending build line and the tech-spec rule (section
> or line) it violates. Can't cite both → not a finding. Re-read cited lines before asserting a
> Severity-A/B gap.

1. **Read the story's ACs** (with method tags) and any `## Notes` scope-cuts. Read any existing `## Code Review Feedback` so you don't re-file a fixed item.
2. **Read the build diff.** `git -C {app_dir} log --grep=<story_id> --oneline` → `git show` each commit (fall back to the touched files in full when the diff is too sparse to judge). This is the surface you review.
3. **Read the builder's tests** for the story — judge test-quality (do the assertions actually exercise the behavior, or pass vacuously?).
4. **Review against the contract** — the `{tech_spec}` `security`/`api`/`schema`/`auth` sections — for:
   - **Security / data-integrity (A):** authz/RLS on every write + sensitive read, input validation (Zod at the boundary), injection, secret handling.
   - **Correctness (B):** logic matches the AC; error paths handled; right status codes/shapes.
   - **Robustness / edge-case (C):** empty/null/zero/over-limit/permission-denied/race.
   - **Maintainability / test-quality (D):** dead code, duplicated logic, vacuous assertions.
5. **Classify each gap** per `review-feedback-format.md` (engineering severity A/B/C/D; tag `[true]`/`[justified]`/`[choice]`). Only **`[true]` of severity A/B/C blocks** (a blocking `- [ ]` item); a `[true]` **D** is a logged `> nit [D]:` note, not a gate failure. Verify any in-code justification claim against the tech spec.
6. **Return the REVIEW block.**

### REVIEW block (the reviewer's entire substantive output)

```
REVIEW
story: <story_id>
verdict: clean | findings
findings: <n blocking findings — [true] A/B/C only; D-nits/justified/choice don't count toward code-review-failed>
diff: <commits reviewed, or "no app diff — <why>">
items:
- sev: <A|B|C|D>  tag: <true|justified|choice>  surface: <file/function>
  build: <file:line — what's wrong>
  spec: <{tech_spec} section or file:line — the rule it violates>
  note: <one line — why true/justified/choice; verify any justification claim>
  fix: <one line — the change that closes it>
notes: <≤2 lines — reduced-surface flags, ambiguities>
```

`verdict: clean` only with zero **blocking** items (`[true]` A/B/C). `findings:` counts those only —
a `[true]` D nit, a `[justified]`, or a `[choice]` leaves the verdict `clean`.

## After the reviews — the orchestrator writes

For each reviewed story (orchestrator-only — reviewers wrote nothing):

1. **Write findings into the story's `## Code Review Feedback`** per `review-feedback-format.md`: each blocking `[true]` A/B/C finding as an open `- [ ]` checkbox (engineering severity + surface + fix + both-sided citation); each `[true]` **D** as a `> nit [D]:` note; each `[justified]`/`[choice]` as a `>`-quoted note. Append (don't wipe `- [x]` history).
2. **Set the status** (the only status move; never revert past `done`):
   - zero blocking items (`[true]` A/B/C) → `status: done → code-reviewed` (D nits / justified / choice don't block).
   - ≥1 blocking item → `status: done → code-review-failed`.
   - Either way stamp `code_review_date: <today>`.
3. **Surface `[choice]` findings to the user** — print them; do **not** auto-write them as actionable `- [ ]` items.
4. **Print a summary:** stories reviewed, `code-reviewed` vs `code-review-failed`, `[true]` findings by severity, `[choice]` decisions awaiting the user. Point `code-review-failed` stories at `/execute-sprint <N>` to fix and re-`done`, then `/code-review-sprint --recheck`. Point `code-reviewed` stories at `/generate-test-sprint <N>`. End with: "run `/manage-stories index` to refresh the board."

## The killer self-test

Run `code-review-sprint` against a story you know shipped a real bug (a missing auth check, an
unhandled empty state). If it independently resurfaces it with a two-sided citation written into
Code Review Feedback, the gate works. If it comes back `code-reviewed` on code you know was flawed,
the prompt is too weak — tighten the security/edge-case enumeration before trusting it. A review
that rubber-stamps is worse than none.

## Operating rules

- **Read-only reviewers; orchestrator-only writes.** This is what makes parallel review safe.
- **Every finding cites two references** (build line + tech-spec rule). No summary-only claims; re-verify A/B findings.
- **Never edit `{app_dir}`; never edit an AC or scope.** Gaps become `## Code Review Feedback` items the next build run fixes.
- **The only status move is `done → code-reviewed | code-review-failed`** — never revert to an earlier state, never touch a non-`done` story.
- **`code-review-failed` ⇔ ≥1 open blocking item** (`[true]` A/B/C); a `[true]` D nit, `[justified]`, or `[choice]` never forces it.
- **Never regenerate `{index_path}`** (parallel-chain skill) — only stamp the story's frontmatter + section. **Never invent a sprint.**

## Files this skill touches

Orchestrator writes: `{stories_dir}<topic>/story-*.md` — `status` (`done → code-reviewed |
code-review-failed` only), `code_review_date`, and the `## Code Review Feedback` section. Nothing
else — not `{index_path}`, not `{app_dir}`, not ACs/scope. Reviewer subagents write **nothing**
(read `{stories_dir}` + `{app_dir}` diff, return REVIEW blocks).

## When to bail and ask

- Sprint matches zero `done` stories → list sprints with built stories, ask.
- A story is earlier than `done` → route to `/execute-sprint <N>`.
- A `[choice]` finding → surface it; don't auto-write it as actionable.

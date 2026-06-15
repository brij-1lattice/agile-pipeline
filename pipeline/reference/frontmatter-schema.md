# Reference — story frontmatter schema

> Single source of truth for story frontmatter. Every skill in the pipeline reads and writes
> these fields; none redefine them. All paths resolve through `.claude/pipeline.config.md`.

A story is a markdown file at `{stories_dir}<topic>/story-<topic>-<NN>-<kebab-slug>.md`. The
`<NN>` is a two-digit zero-padded sequence, unique within a topic.

## Required fields (set at create time by `manage-stories`)

```yaml
---
id: story-<topic>-<NN>            # must match the filename's prefix
topic: <topic>                    # one of the topics in the config Topics→sprint table
sprint: <N>                       # single-operator: release grouping (config Topics→sprint table). multi-operator: owner-scoped — `owner` + `sprint` jointly address the operator sprint `owner/N` (see operator-profile.md)
story_points: <1..sp_cap>         # never > sp_cap — split if larger
status: <draft|ready|in-progress|done|code-reviewed|code-review-failed|tests-generated|tested|testing-failed|verified|verification-failed|blocked>
owner: <name-or-handle>           # required; single person responsible for execute + test. In multi-operator mode this is the scoping dimension: `owner` + `sprint` = the operator sprint `owner/N`
tasks_populated: <true|false>     # false at create; true only when analyze-sprint breaks it down
dependencies:                     # list of story IDs; empty list = no deps
  - story-<topic>-<NN>
design:                           # see design-linkage-gate.md
  - design/<file>.<design_ext>
---
```

## Downstream-managed fields

Added by later stages; **preserve them, never strip them**. `lint`/`index` tolerate them
(and `index` may surface them) — never flag as unknown.

| Field | Written by | Meaning |
|---|---|---|
| `analyzed` / `analyzed_date` | analyze-sprint | story passed the analysis gate |
| `exec_model: <default_exec_model> \| <escalation_model>` | analyze-sprint | model execute-sprint builds it on (default from config) |
| `escalated: true` | execute-sprint | a default-model build failed the gate and was retried on the escalation model |
| `executed_date` | execute-sprint | story reached `done` |
| `code_review_date` | code-review-sprint | date of the last code review; verdict is the `status` (`code-reviewed` clean / `code-review-failed` carrying open `## Code Review Feedback` items) |
| `test_gen_date` | generate-test-sprint | date the adversarial tests were generated (status `tests-generated`) |
| `test_date` | qa-sprint | date of the last test run; verdict is the `status` (`tested` clean / `testing-failed` carrying open `## Testing Feedback` items) |
| `verified_date` | verify-sprint | date of the last parity audit; verdict is the `status` (`verified` clean / `verification-failed` carrying open `## Verification Feedback` items) |
| `status: deferred` + `original_sprint: <N>` | analyze-sprint | parked to `{backlog_dir}` during analysis (outside the lifecycle states); planned sprint preserved |
| `superseded_by: [<id>…]` | manage-stories | split: this archived story was replaced by the listed new IDs |

## Body sections, in order

1. **User story** — `As a <role>, I want <capability>, so that <outcome>.`
2. **Description** — prose describing the surface the story covers.
3. **Acceptance criteria** — `- [ ]` checklist of independently verifiable conditions. Never bare "works correctly". `analyze-sprint` prefixes each line with a verification-method tag (see `ac-method-tags.md`).
4. **Tasks** — see `task-states.md`; created empty by `manage-stories`, populated by `analyze-sprint`.
5. **Code Review Feedback** — created empty by `manage-stories`; `- [ ]` checklist of engineering findings written by `code-review-sprint` (see `review-feedback-format.md`). Cleared as a re-run fixes them.
6. **Testing Feedback** — created empty by `manage-stories`; `- [ ]` checklist of failing tests written by `qa-sprint` (and by the builder on an un-greenable gate). Cleared as a re-run fixes them.
7. **Verification Feedback** — created empty by `manage-stories`; `- [ ]` checklist of design-parity findings written by `verify-sprint` (see `review-feedback-format.md`). Cleared as a re-run fixes them.
8. **Notes** — blueprint links, design rationale, scope cuts, deferral/blocker reasons.

## Status lifecycle

The QA gauntlet runs **after** `done`, as four gated stages — each owned by a separate skill that
consumes the status the prior stage produced, so the four can run in parallel sessions without
collision:

```
draft → ready (analyze) → in-progress (builder) → done (builder)
  done            ── code-review-sprint   ─→ code-reviewed       │  fail → code-review-failed
  code-reviewed   ── generate-test-sprint ─→ tests-generated     │  blocker → blocked
  tests-generated ── qa-sprint            ─→ tested              │  fail → testing-failed
  tested          ── verify-sprint        ─→ verified (terminal) │  fail → verification-failed
  ├─ code-review-failed / testing-failed / verification-failed — EXECUTABLE: execute-sprint re-runs,
  │     clears the open feedback items across all three sections, returns the story to `done`,
  │     and it re-enters the gauntlet at code review (a fix can affect an earlier gate)
  ├─ deferred (analyze → backlog; restored via manage-stories restore/update)
  └─ blocked (execute/builder/generate-test; un-blocked via manage-stories update: blocked → ready)
```

`status: done` is gated: allowed only when `tasks_populated: true` AND every task is
`[completed]`/`[cancelled]` (see `task-states.md`). Each QA verdict **is the status**, set by the
stage that owns it and gated on that stage's feedback section:

- `code-review-sprint`: `done → code-reviewed` (zero open **blocking** `## Code Review Feedback` items — `[true]` A/B/C; D-nits/justified/choice don't block) or `→ code-review-failed`.
- `generate-test-sprint`: `code-reviewed → tests-generated` (adversarial tests written) or `→ blocked`.
- `qa-sprint`: `tests-generated → tested` (generated tests green) or `→ testing-failed`.
- `verify-sprint`: `tested → verified` (parity clean — terminal; zero open blocking `## Verification Feedback` items) or `→ verification-failed`.

The three `*-failed` states are **executable**: `execute-sprint` re-runs them to clear the open
feedback, returning the story to `done` to re-flow the gauntlet from the top. **On that return to
`done` the builder clears the now-stale downstream stage stamps** (`code_review_date`,
`test_gen_date`, `test_date`, `verified_date`) — the code changed, so the prior verdicts no longer
hold and the gauntlet re-stamps each as the story re-flows. This keeps `status` the single honest
source the INDEX projects from.

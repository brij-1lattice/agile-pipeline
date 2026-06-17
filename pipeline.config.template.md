# Pipeline configuration

> **This is the only project-specific file in the sprint pipeline.** Every skill
> (`manage-stories`, `analyze-sprint`, `execute-sprint`, `verify-sprint`,
> `finalize-tech-spec`) and the `sprint-story-builder` agent reads this file **first** and
> resolves *all* paths, document names, constants, models, vocabulary, and tech-spec
> section references from it. Nothing project-specific is hardcoded in the skills.
>
> Copy this template to `.claude/pipeline.config.md` and fill it in — or run
> `/manage-stories bootstrap`, which interviews you for these values and writes the file.
>
> **Resolution rule (every skill obeys):** a path written `{working_root}stories/…` means
> "join `working_root` from the Paths block below." A reference like `the schema section`
> resolves through the `tech_spec_sections` map — skills never cite a raw `§N`. If this file
> is absent, the skill stops and runs bootstrap.

## Paths

```yaml
# Root that all planning artifacts live under (trailing slash). "" = repo root.
working_root: plan/
# Built application directory (where execute-sprint/sprint-story-builder write code).
app_dir: web/
# Design/prototype source directory and the file extension its artifacts use.
design_dir: plan/design/
design_ext: jsx          # jsx | html | tsx | png | fig-export | …
# Derived story-tree locations (override only if your layout differs from the default).
stories_dir: plan/stories/
archive_dir: plan/stories/_archive/
backlog_dir: plan/stories/_backlog/
index_path: plan/stories/INDEX.md
```

## Documents

```yaml
# The "what to build" blueprint manage-stories init + finalize-tech-spec read to derive
# sprints (release groupings) and topics (feature areas).
blueprint: plan/PRODUCT.md
# The implementation contract (stack, schema, auth, API, UI rules, testing, env).
tech_spec: plan/TECHNICAL-REQUIREMENTS.md
# The UI/design contract (design system, component inventory, rationale).
design_doc: plan/UI-DESIGN-HANDOFF.md
```

> Note: there is no separate deviations/ledger file. `verify-sprint` writes parity findings into
> each story's own `## Code Review Feedback` section (see `pipeline/reference/review-feedback-format.md`)
> and moves the story to `reviewed` or `review-failed`.

## Tech-spec section map

> Skills reference tech-spec sections **by role**, never by raw number — so a project whose
> tech spec is organized differently just remaps here. Use whatever anchor your doc uses
> (`§4`, `## Database`, `4.`).

```yaml
tech_spec_sections:
  stack:          "§2"
  structure:      "§3"
  schema:         "§4"
  auth:           "§5"
  api:            "§6"
  routing:        "§7"
  ui_rules:       "§8"
  security:       "§9"
  testing:        "§10"
  env:            "§11"
  open_questions: "Appendix — Open Questions"
```

## Topics → sprint

> The feature areas (topics) and which sprint (release grouping) each defaults to. Drives
> manage-stories init and the `sprint:` pre-fill. `ask` = always ask the user. `source`
> points at the blueprint section/module a topic derives from (free-form).
>
> **Single-operator default.** In multi-operator mode (any `.claude/operators/*.md` exists) sprints
> become owner-scoped `owner/N`, and each operator's per-sprint goals live in their own profile's
> `Sprints` table — this table and `sprint_labels` below then act only as defaults for the `sprint:`
> pre-fill. How operators isolate is set by `operator_isolation` (Constants below): `worktree` (each
> on its own machine gets a sibling worktree/branch/ports) or `shared` (each teammate in their own
> clone builds in the current checkout — pair with `default_owner: "@git"` for git-identity operators).
> See `pipeline/reference/operator-profile.md` and `operator.template.md`.

| Topic | Default sprint | Source (blueprint) |
|---|---|---|
| homepage | 1 | Module 7 |
| blog | 1 | Module 2 |
| templates | 1 | Module 3 |
| services | 1 | Module 6 |
| newsletter | ask | cross-cutting |
| auth | 2 | Module 1 |
| jobs | 2 | Module 4 |
| experts | 2 | Module 5 |
| admin | ask | Module 8 |
| search | 3 | sprint-3 only |

## Sprint labels

```yaml
sprint_labels:
  1: "Content + Credibility"
  2: "Community + Self-Serve"
  3: "Operations + Growth"
```

## Constants & models

```yaml
default_owner: brij            # owner of a new story by default. Use a literal handle to pin it, or
                               # `@git` = slug(git config user.name) resolved at runtime (see
                               # pipeline/reference/operator-profile.md → @git token + slugify rule),
                               # so each teammate's git identity is their owner.
# How operators isolate from each other (absent → worktree):
#   shared   = build in the current checkout (no git worktree). Use when each teammate has their own
#              clone on their own device — the per-device clone is the isolation. Code lands directly
#              in {app_dir}; merge to main via PR.
#   worktree = the classic mode: each operator builds in a sibling git worktree on its own branch
#              (for several operators sharing ONE machine).
operator_isolation: worktree
sp_cap: 5                 # max story points per story; split if larger
sprint_story_cap: 12      # soft cap — lint warns above this. The serial build/QA loops and the
                          # parallel fan-out both scale with stories-per-sprint, so an oversized
                          # sprint bloats the orchestrator's context; split across sprints/operators.
max_fix_attempts: 3       # builder gate fix attempts before failed
gate_timeout: 900         # seconds — hard ceiling per gate/test/render command (wrap each in
                          # `timeout {gate_timeout}`). A command that exceeds it is KILLED and
                          # treated as a failed gate, so a hung dev-server/watcher can never block
                          # a subagent (and thus the orchestrator) forever. Raise for slow e2e suites.
stale_days: 30            # draft-staleness lint threshold (measured from analyzed_date/git)
orchestrator_model: sonnet     # execute-sprint orchestrator floor (never haiku)
default_exec_model: sonnet     # per-story build model when analysis didn't flag opus
escalation_model: opus         # model a failed default-model build escalates to
# QA-gauntlet stage models (absent → fall back to escalation_model / default_exec_model):
code_review_model: opus        # code-review-sprint — analytical, read-only engineering review
test_gen_model: opus           # generate-test-sprint — adversarial test-case authoring (the
                               # "thinking" half: designing the edge cases). Authors now fan out in
                               # parallel (write-only, one bulk commit), so latency no longer scales
                               # with story count — keep opus for depth. Downshift to sonnet only if
                               # cost/speed outweighs adversarial-test quality on routine sprints.
test_run_model: sonnet         # qa-sprint — running tests + triaging failures (mechanical)
verify_model: opus             # verify-sprint — design-parity / verification judgment
```

## Stack

```yaml
# Names the stack profile under pipeline/stack-profiles/<stack_profile>.md that carries the
# scaffold, gate commands, test toolchain, render command, and directory layout. This is
# the ONLY place framework/language specifics live.
stack_profile: nextjs14-supabase
# Third-party services whose absence is a legitimate build blocker and whose clients are
# stubbed in tests. Used by execute-sprint/sprint-story-builder blocker detection.
external_services: [ZeptoMail, Turnstile, Sentry, Upstash]
```

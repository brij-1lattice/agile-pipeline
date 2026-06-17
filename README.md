# agile-pipeline

A portable, project-agnostic **story → sprint** delivery pipeline for Claude Code.

You write a spec. The pipeline breaks it into small **stories**, groups them into **sprints**, and
then — one story at a time, each in its own isolated subagent — **builds the code, writes the tests,
and checks the result against your design.** You drive the whole thing with slash commands; the
subagents do the heavy lifting in fresh context so nothing pollutes your main session.

The pipeline's logic is generic. Everything project-specific lives in **one config file**
(`.claude/pipeline.config.md`) plus **one stack profile** — so you drop it into any repo, fill in the
config, and go. Nothing is hardcoded in the skills themselves.

> **New here?** Read sections 1–4 (install → run a sprint → understand the QA gauntlet → statuses).
> That's everything you need to take a sprint from spec to verified. The rest is reference.

---

## 1. Install it into a project

Copy the generic parts into your project's `.claude/`, then add one config file:

```bash
TARGET=/path/to/your/project
cp -R skills agents pipeline "$TARGET/.claude/"        # the generic pipeline (or: ln -s for a live link)
cp pipeline.config.template.md "$TARGET/.claude/pipeline.config.md"
cp scripts/scaffold-plan.py "$TARGET/"                 # planning-tree scaffolder + operator helper
```

Now you have two ways to fill in the config:

- **Recommended — let it bootstrap.** In the project, run **`/manage-stories bootstrap`**. It finds
  your planning docs, proposes the topics, sprints, and tech-spec section map from your blueprint,
  helps you pick a stack profile, writes `.claude/pipeline.config.md`, and continues straight into
  creating the story tree.
- **By hand.** Edit `.claude/pipeline.config.md` directly (see the cheat-sheet in §6).

If the config is ever missing, every skill stops and points you back to `bootstrap`.

**Scaffolding the planning tree (optional helper).** `scaffold-plan.py` reads the config and makes
your planning folders match it — creating missing directories, stubbing `stories/INDEX.md`, and
*warning* about any missing source document (it never fabricates one). It's stdlib-only and safe to
re-run:

```bash
python3 scaffold-plan.py --dry-run    # preview every change, touch nothing
python3 scaffold-plan.py              # apply (exits non-zero if a required doc is still missing)
```

To also pull stashed or misplaced source files into place, copy `pipeline.seeds.template.md` to
`.claude/pipeline.seeds.md`, fill in its `source | destination | overwrite` rows, and the scaffolder
applies them (it never clobbers an existing file unless you pass `--force`).

---

## 2. Run a sprint

Each command takes a sprint — a number (`2`), `Sprint 2`, or a label fragment — and moves that
sprint's stories one step forward. Run them in order:

```
/finalize-tech-spec        →  your technical spec        (a short interview)
/manage-stories            →  a story tree               (stories start as "draft")
/analyze-sprint N          →  ready    (questions resolved, acceptance criteria mined + tagged, tasks, build model)
/execute-sprint N          →  done     (builds the code + tests, runs the gate, verifies every AC)
─── the QA gauntlet ──────────────────────────────────────────────────────────────
/code-review-sprint N      →  code-reviewed     | code-review-failed
/generate-test-sprint N    →  tests-generated   | blocked
/qa-sprint N               →  tested            | testing-failed
/verify-sprint N           →  verified (done!)  | verification-failed
```

**The self-healing rule.** A `*-failed` state is not a dead end — it's a *to-do list*. Just run
**`/execute-sprint N`** again: it reads the open findings, fixes them in place, and returns the story
to `done`. From there the story **re-flows the gauntlet from the start** (a fix can break an earlier
gate, so every gate runs again). Repeat until every story reaches `verified`.

The simplest way to take a sprint all the way through, in a single session:

```
/execute-sprint N        → done
/code-review-sprint N
/generate-test-sprint N
/qa-sprint N
/verify-sprint N
# anything *-failed → /execute-sprint N  (clears the findings) → done → resume from /code-review-sprint N
/manage-stories index    # ONCE, after the pass settles — refreshes the board
```

> The board (`INDEX.md`) is intentionally stale *between* QA stages — the four QA skills never write
> it, so they can't race on it. Refresh it yourself with `/manage-stories index` once a pass settles.

> **`/clear` between stages.** Every stage rebuilds its working set from story `status` — all state
> lives in the story files and git, never in context. So `/clear` (or run each stage in its own
> session) between stages: it loses nothing and keeps each orchestrator's context lean. Running the
> whole chain in one session — the thing the design works hardest to avoid — stacks every stage's
> summary and quietly undoes the per-story subagent isolation. The serial stages (`execute-sprint`,
> `qa-sprint`, `verify-sprint`) are also **safe to interrupt**: stop, `/clear`, re-run the same
> command, and they resume from `status`, skipping finished stories.

**Browse it in a browser.** For a visual, read-only spec browser, run the viewer — a config-driven
static server (it auto-detects the project and reads its paths from `.claude/pipeline.config.md`):

```bash
python3 scripts/viewer/serve.py start    # opens a 3-pane spec browser (stop / status too)
python3 scripts/viewer/serve.py          # or foreground (Ctrl+C to stop)
```

Left pane: topics grouped by sprint. Middle: the filtered story list (search · sprint · status ·
owner, with options derived from the data). Right: full story detail — metadata chips, the
depends-on / blocks graph, and the rendered markdown. Refresh after `/manage-stories index`. See
`scripts/viewer/README.md`.

---

## 3. The QA gauntlet — why four passes?

Passing the build gate only proves *"the tests I wrote pass."* It does **not** prove the code is
correct, safe, robust, or faithful to the design — a test suite written by the same mind that wrote
the code inherits the same blind spots. So building and checking are kept as **separate passes**, and
each check runs independently in fresh context:

| Pass | What it checks | Writes to |
|---|---|---|
| **`code-review-sprint`** | Engineering review of the build diff against the tech spec: security, correctness, robustness, test-quality | `## Code Review Feedback` |
| **`generate-test-sprint`** | Authors the *adversarial complement* of the happy-path tests — empty / error / permission / boundary cases — into a separate QA test namespace (doesn't run them) | the QA test files |
| **`qa-sprint`** | Runs that adversarial suite and triages failures (fail-closed: a failure is a real defect unless a clean re-run proves it flaky) | `## Testing Feedback` |
| **`verify-sprint`** | Design-parity audit with eyes on the *rendered* output — the terminal sign-off | `## Verification Feedback` |

**Findings live inside the story**, in those three feedback sections — there's no separate ledger
file and no orphaned "fix" stories. Each finding is graded:

- **`[true]` A/B/C** — a real gap → a blocking `- [ ]` checkbox the next build run must clear.
- **`[true]` D** — cosmetic / weak-assertion trivia → a `> nit [D]:` note (logged, never blocks).
- **`[justified]`** — a defensible deviation → a `> justified:` note (non-blocking).
- **`[choice]`** — a genuine product decision → surfaced to *you*, never auto-actioned.

When a re-run clears blocking items, the builder collapses the resolved `- [x]` lines into a per-section
`> resolved: N (git history)` tally — git keeps the detail, so feedback sections (which the builder
re-reads in full on every rebuild) don't grow across re-flow cycles. Open items and `> nit`/
`> justified`/`> choice` notes are never collapsed.

A story is `<stage>-failed` **only if** its section has at least one open *blocking* (A/B/C) item.
Testing Feedback is untagged — any failing test blocks. (Full rules:
`pipeline/reference/review-feedback-format.md`.)

**Models are right-sized.** The expensive model does the *thinking* (code review, test design, parity
judgment); the cheap model does the *mechanical* work (running tests). Configured in §6.

---

## 4. Statuses

```
draft → ready → in-progress → done
done → code-reviewed → tests-generated → tested → verified         ← the happy path
       code-review-failed / testing-failed / verification-failed   ← executable: re-run /execute-sprint
       blocked    ← external service / ambiguity stopped work (un-block via /manage-stories update)
       deferred   ← parked in the backlog
```

- **`done` is gated** — a story reaches `done` only when every task is `[completed]`/`[cancelled]`
  **and** every acceptance criterion is checked off. The builder never ticks an unsatisfied AC or
  edits an AC to make a test pass.
- The three **`*-failed`** states carry open findings and are the only QA states `/execute-sprint`
  picks up.
- **`verified`** is terminal — all four gates are clear.

---

## 5. Running in parallel

The four QA commands consume **disjoint** input statuses, so they never fight over the same *story
file*. But three of them touch the shared app checkout and/or a fixed dev-server/DB port, so running
them at the same time *within one checkout* needs care:

| Command | Changes app files? | Needs a running port? | Safe to run concurrently? |
|---|---|---|---|
| `code-review-sprint`   | no (reads diffs)    | no  | **Yes** — read-only reviewers **fan out in parallel within one run**, and multiple sessions are fine too |
| `generate-test-sprint` | **yes** (writes tests) | no  | **Authors fan out in parallel within one run** — they're write-only (no git race) and the orchestrator does one bulk commit. A *2nd concurrent session* of the skill still needs its own git worktree |
| `qa-sprint`            | no (runs tests)     | **yes** | Serial; a 2nd session needs a worktree **+ its own stack/port** |
| `verify-sprint`        | no (renders)        | **yes** | Render audits serial by default; **code-only audits (`design: none-needed`) fan out in parallel** (no render, no port) |

> **Why `generate-test-sprint` parallelizes but the others don't.** Test *authoring* needs no
> running port and each author writes a distinct file, so concurrent authors have no shared resource
> once you defer the commit — the orchestrator validates once and bulk-commits. The build/run/render
> stages either share one git branch (builders) or a fixed dev/DB port (qa/verify), so they stay
> serial unless isolated in a worktree + stack.

### Multiple operators, fully in parallel

The table above is about one person's checkout. **Different operators (people) run completely in
parallel** — owner-scoped sprints never collide. This is opt-in: with no `.claude/operators/`
directory, the pipeline stays single-operator. How operators isolate is set by `operator_isolation`
in `.claude/pipeline.config.md` (absent → `worktree`):

**`shared` — each teammate in their own clone on their own device** (recommended for a distributed
team). Drop in **one** generic profile `.claude/operators/self.md` with `owner: "@git"` (copy Form A
of `operator.template.md`) and set `default_owner: "@git"`. Each teammate's git identity *is* their
operator — `owner` resolves to `slug(git config user.name)` at runtime, zero per-person setup. No
worktree: build in the current checkout, on your own branch, and PR to `main`.

```bash
git config user.name "Ashish Kumar"   # → operator ashish-kumar
/execute-sprint N                      # bare N scopes to YOUR stories (your git slug)
# …rest of the gauntlet, e.g. /verify-sprint N — builds straight into {app_dir}, PR to main …
```

**`worktree` — several operators sharing one machine.** Copy Form B of `operator.template.md` to
`.claude/operators/<name>.md` (one file per person), fill in branch / ports / sprint goals, then:

```bash
python3 scaffold-plan.py operator <name> --sprint N   # creates ../<repo>-<name> on sprint/<name>-N, prints ports
cd ../<repo>-<name>                                    # work inside your own worktree
/execute-sprint <name>/N                               # owner-scoped — builds only your sprint's stories
# …rest of the gauntlet, all addressed <name>/N, e.g. /verify-sprint brij/2 …
```

Either way sprints are addressed **`owner/N`** (e.g. `brij/2`), each carrying a one-line goal; the
INDEX groups operator → sprint → topic, and every build commit carries an `Operator: <owner>` trailer.
Merge to `main` via PR once your stories are `verified`. Full contract:
`pipeline/reference/operator-profile.md`.

---

## 6. Configuration cheat-sheet

These are the keys in `.claude/pipeline.config.md` you actually touch:

```yaml
# Paths — where things live
working_root / app_dir / design_dir / stories_dir / index_path …

# Documents — your three source docs
blueprint / tech_spec / design_doc

# Topics → sprint table     # feature areas and which release each defaults to
# Sprint labels             # 1: "…"  2: "…"  3: "…"

# Constants & models
default_owner, operator_isolation, sp_cap, sprint_story_cap, max_fix_attempts, stale_days   # default_owner: "@git" = git-identity; operator_isolation: shared | worktree; sprint_story_cap: lint warns above this (oversized sprints bloat context)
orchestrator_model, default_exec_model, escalation_model        # build models
code_review_model, test_gen_model, test_run_model, verify_model  # QA models (e.g. opus, opus, sonnet, opus)

# Stack
stack_profile: nextjs14-supabase
external_services: [...]    # stubbed in tests; if one is genuinely unavailable, that's a real blocker
```

Tech-spec sections are referenced **by role** (`security`, `api`, `schema`, …) through the
`tech_spec_sections` map — so a spec organized differently just remaps there, no skill changes
needed.

### Adding a new stack

The default stack profile is `nextjs14-supabase`. For another stack, copy
`pipeline/stack-profiles/nextjs14-supabase.md`, replace each section with your stack's equivalents
(scaffold, gate commands, test toolchain, render command, directory layout, toolchain preflight), and
set `stack_profile:` in the config. The orchestration logic — dispatch, escalation, partial
continuation, audit — never changes. See `pipeline/stack-profiles/README.md`.

---

## 7. What every file does

The whole pipeline is ~21 files.

**Skills — the slash commands** (`skills/<name>/SKILL.md`)

| Command | Role |
|---|---|
| `finalize-tech-spec` | Interactively finalize the technical-requirements doc; asks only about gaps, then writes the spec. |
| `manage-stories` | Create/maintain the story tree: `bootstrap` / `add` / `split` / `update` / `restore` / `lint` / `index`. Sole writer of `INDEX.md`. |
| `analyze-sprint` | Per story: resolve questions, reconcile against the docs, mine + tag ACs from the prototype, break out tasks, classify build model → `ready`. |
| `execute-sprint` | Build pass — dispatches one `sprint-story-builder` per story in dependency order; escalates a failed cheap build; → `done`. Also clears the `*-failed` states. |
| `code-review-sprint` | QA stage 1 — independent engineering review → `code-reviewed` / `code-review-failed`. |
| `generate-test-sprint` | QA stage 2 — dispatches `qa-test-author` to write adversarial tests → `tests-generated`. |
| `qa-sprint` | QA stage 3 — runs the adversarial suite, triages failures → `tested` / `testing-failed`. |
| `verify-sprint` | QA stage 4 (terminal) — design-parity audit → `verified` / `verification-failed`. |

**Agents — the per-story workers** (`agents/<name>.md`)

| Agent | Role |
|---|---|
| `sprint-story-builder` | Builds ONE story end-to-end (code + tests + gate + AC verification) in isolated context; spawned by `execute-sprint`. |
| `qa-test-author` | Writes ONE story's adversarial test suite into the QA namespace (idempotent — augments in place on a re-flow); spawned by `generate-test-sprint`. |

**Reference contracts — the single sources of truth** (`pipeline/reference/*.md`)

| File | Role |
|---|---|
| `frontmatter-schema.md` | Story frontmatter fields, body-section order, and the status lifecycle. |
| `task-states.md` | The `## Tasks` checklist states and the `done`-gate. |
| `ac-method-tags.md` | The `(unit\|e2e\|axe\|visual\|manual)` AC verification-method tag. |
| `design-linkage-gate.md` | How a story's `design:` field is resolved (for UI-touching stories). |
| `topo-order.md` | The dependency ordering both `analyze-sprint` and `execute-sprint` walk. |
| `index-template.md` | The `INDEX.md` layout and how its review columns are derived. |
| `review-feedback-format.md` | The three feedback sections: severity legends, tags, gating, QA-test ownership. |
| `operator-profile.md` | The multi-operator contract (the `@git` token, `shared`/`worktree` isolation, owner-scoped sprints). |

**Stack profiles — the only framework-specific part** (`pipeline/stack-profiles/*.md`)

| File | Role |
|---|---|
| `README.md` | What a stack profile is and how to add one. |
| `nextjs14-supabase.md` | The default profile: scaffold, gate, test + QA-test toolchain, render command, layout. |

**Root files**

| File | Role |
|---|---|
| `pipeline.config.template.md` | The per-project binding file — copy to `.claude/pipeline.config.md` and fill in (or bootstrap). |
| `pipeline.seeds.template.md` | Optional seed manifest for `scaffold-plan.py` to copy stashed sources into place. |
| `operator.template.md` | Operator profile — Form A (generic `@git`/`shared`) → `.claude/operators/self.md`; Form B (per-person/`worktree`) → `.claude/operators/<name>.md`. |
| `scripts/scaffold-plan.py` | Scaffolds the planning tree; its `operator` subcommand sets up worktrees. |
| `scripts/viewer/` | Read-only **spec browser** in your browser (`serve.py` + `index.html` + `viewer.jsx` + css) — topics-by-sprint, filtered story list, and full story detail with dependency graph, parsed straight from `stories/INDEX.md` + the story files. |

---

## 8. Gotchas

- **Commits stay under your control.** The build makes per-story commits inside the app, but the
  pipeline never pushes — you decide when to commit the planning trees.
- **Refresh the board yourself.** The four QA skills don't write `INDEX.md`; run
  `/manage-stories index` after a gauntlet pass.
- **A red QA test is a defect** — fix it in the *code*, not the test. The only exception: the
  requirement legitimately changed (a resolved `[choice]` or changed AC). Then the builder may edit
  that one test **with a two-sided citation**, or you re-author the suite via
  `/generate-test-sprint --recheck`.
- **`--recheck` / `--reverify`** re-run a QA stage on an already-advanced story (e.g. after a fix).
- **`blocked` ≠ `failed`.** `blocked` means an external service or an ambiguity stopped the work;
  un-block it via `/manage-stories update` once resolved.
- **Gates can't hang the run.** Every gate/test/render command is non-watch and wrapped in
  `timeout {gate_timeout}` (config, default 900s), and every worker subagent must always return a
  `RESULT` — even on a timeout or crash. A killed command becomes a normal gate *failure*, and a
  subagent that returns no RESULT is recovered (marked `blocked` / `infra-blocked`) so the
  orchestrator continues instead of waiting forever. Raise `gate_timeout` for genuinely slow suites.
- **Set Playwright `workers` explicitly.** The gates run e2e with `CI=true` (for non-interactivity),
  and under `CI=true` **Playwright defaults to a single worker** — serializing your whole e2e suite.
  Set `fullyParallel: true` + an explicit `workers` in `playwright.config.ts` (or pass `--workers=N`)
  so e2e actually runs in parallel. See the stack profile's *Parallelism & caching* section.

---

## 9. Why it's built this way

- **Forward *and* backward, self-healing.** Building and the four-stage QA gauntlet are deliberately
  separate passes, because build-green ≠ correct, safe, and design-faithful. Each gauntlet stage runs
  in independent fresh context, writes its findings into the story's own feedback section, and flips
  the story to an *executable* `*-failed` state — which the next build run picks up and fixes in
  place, after which the story re-flows the gauntlet from the top. No separate ledger, no orphaned fix
  stories.
- **One source of truth.** Every shared contract (frontmatter + body schema, task states,
  design-linkage gate, dependency ordering, INDEX template, feedback format, AC method tags) lives
  exactly once under `pipeline/reference/`, and every skill points at it — so the rules can't drift.
- **Right-sized models.** Analysis classifies each story's build model up front; execution
  auto-escalates a failed cheaper build, handing the stronger model the discarded attempt's patch to
  learn from rather than starting cold.
- **Isolated context per story.** Each story is built and each gauntlet check is run by a freshly
  spawned subagent, so the orchestrator's context stays tiny (just IDs and pass/fail) and each
  judgment is independent — uninfluenced by the builder's rationalizations.

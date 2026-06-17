# Reference — operator profiles & owner-scoped sprints

> Single source of truth for **multi-operator mode**: how several people each run their own sprint
> in parallel on one project without colliding. Every skill that takes a sprint argument resolves it
> through the rules here; none redefine them. **This mode is opt-in and fully backward compatible** —
> a project with **no `.claude/operators/` directory** behaves exactly as the single-operator pipeline
> always has (global `sprint:` grouping + `default_owner`). The moment one or more operator profiles
> exist, the owner-scoped behavior below takes precedence.

## The model in one line

A **sprint is owned by one operator** and addressed `owner/N` (e.g. `brij/2`) — one person's batch of
work with a one-line goal, merged to `main` via PR. **An operator is a person, not a subsystem.**

How operators isolate is set by `operator_isolation` in `.claude/pipeline.config.md` (absent →
`worktree`):

- **`shared`** — every operator builds **in the current checkout on the current branch**; no worktree
  is created. This is the right mode when each teammate has their **own clone on their own device**:
  the per-device clone *is* the isolation, so there is nothing to keep separate on one machine. The
  owner only **scopes which stories** a sprint command builds (Resolution rule below). Code lands
  directly in the repo's app dirs; the `branch`/`worktree`/`ports` profile fields are advisory.
- **`worktree`** — the classic mode for **several operators sharing one machine**: each builds in its
  **own git worktree on its own branch** with its **own ports**. Because each owns an isolated
  worktree, two operators building at once can't corrupt each other — the one-builder-per-tree HARD
  RULE stays true *within* a worktree.

No new story field is introduced: a story's existing `owner` + `sprint` frontmatter pair **is** its
operator sprint. `owner: brij` + `sprint: 2` ⇒ `brij/2`.

## Owner identity — the `@git` token (git-identity operators)

An owner value of **`@git`** (in the generic operator profile and/or `default_owner`) means **resolve
the owner at runtime to the slug of `git config user.name`**. This is how a team runs **one generic,
committed profile** instead of one file per person: each teammate's git identity *is* their operator,
with zero per-person setup. Wherever a skill needs "the current operator," it runs `git config
user.name` and slugifies it.

**Slugify rule** (apply to the git user.name everywhere `@git` resolves): lowercase; replace every run
of characters outside `[a-z0-9]` with a single `-`; trim leading/trailing `-`. Examples:
`brij-1lattice` → `brij-1lattice`, `Ashish Kumar` → `ashish-kumar`, `brijmohan.singh` →
`brijmohan-singh`. If `git config user.name` is empty, the skill stops and asks the user to set it (or
to pass an explicit `owner/N`).

A **story's `owner:` is always a concrete slug** (e.g. `owner: brij-1lattice`) written into the file —
`@git` only governs the *default* at creation time and *the current operator* at command time, never
what's stored. So filtering stays a plain string match (Resolution rule).

## Operator profile file

Two supported shapes:

- **Generic git-identity profile (recommended for a team on separate devices).** A **single**
  committed file `.claude/operators/self.md` with `owner: "@git"`. Everyone shares it; the owner
  resolves per-machine from `git config user.name` (see the `@git` token above). The filename is
  `self` (it does **not** match a person) — this is the one exception to the filename-matches-owner
  rule, allowed precisely because the owner is dynamic. With one profile present, bare `N` resolves to
  the current git operator's `N` (Resolution rule, "exactly one profile" case).
- **Per-person profile.** One markdown file per operator at `.claude/operators/<name>.md` where
  `<name>` matches the story `owner` field — for teams that want per-person goal tables or model
  overrides. (A `self.md` and named profiles can coexist; named ones win for their owner.)

Schema (per-person form shown; the generic form just sets `owner: "@git"` and omits the goals table):

```yaml
---
owner: brij                        # required; matches story `owner:` and the filename (a person). Or "@git" for the generic profile.
isolation: shared                  # shared = build in the current checkout (no worktree); else worktree. Falls back to config operator_isolation.
branch: current                    # worktree mode: `sprint/brij-<n>`. shared mode: `current` (build on whatever branch you're on).
worktree: .                        # worktree mode: sibling dir `../<repo>-brij`. shared mode: `.` (no worktree is created).
ports:                             # base ports this operator owns (see Port convention)
  web: 3001
  supabase: 54321
exec_model: <default_exec_model | escalation_model>   # optional; per-operator override of the config global

```yaml
---
owner: brij                        # required; matches story `owner:` and the filename (a person)
isolation: shared                  # shared = build in the current checkout (no worktree); else worktree. Falls back to config operator_isolation.
branch: current                    # worktree mode: `sprint/brij-<n>`. shared mode: `current` (build on whatever branch you're on).
worktree: .                        # worktree mode: sibling dir `../<repo>-brij`. shared mode: `.` (no worktree is created).
ports:                             # base ports this operator owns (see Port convention)
  web: 3001
  supabase: 54321
exec_model: <default_exec_model | escalation_model>   # optional; per-operator override of the config global
---

## Sprints

| N | Goal | Status |
|---|---|---|
| 2 | Expert directory + booking | active |
| 3 | Search + saved filters      | planning |
```

- **`Sprints` table** is the per-operator replacement for the global `sprint_labels` map: it supplies
  the one-line **goal** shown for `owner/N` everywhere (INDEX headings, skill summaries). `Status` is
  free text for the operator's own tracking (`planning | active | done`) — it does **not** drive the
  pipeline; story `status` remains the only lifecycle source.
- **Optional model overrides** (`exec_model`, and any of the QA-stage models) let one operator run a
  different tier; absent keys inherit the config globals. Never widen beyond the config's allowed set.

## Sprint-addressing grammar

A skill's sprint argument accepts, in priority order:

1. **`owner/N`** — e.g. `brij/2`. The canonical multi-operator form. Resolves to the operator sprint.
2. **`owner/N` goal-fragment** — a fragment matched against that operator's `Sprints` goals.
3. **Legacy forms** — bare `N`, `Sprint N`, or a `sprint_labels` fragment. Used as-is for
   single-operator projects; in multi-operator mode they are **owner-ambiguous** (see Resolution).

## Resolution rule (every skill obeys)

Given a sprint argument, collect every `{stories_dir}**/story-*.md` (exclude `{archive_dir}`,
`{backlog_dir}`) and select stories by:

- **`owner/N`** → stories where `owner == <owner>` **AND** `sprint == <N>`. (`<owner>` is a literal
  slug; the generic profile never makes you type `@git/N` — use bare `N` for your own, below.)
- **bare `N` / `Sprint N` / label**, and:
  - **no `.claude/operators/` dir** → stories where `sprint == <N>` (today's global behavior).
  - **the generic `self.md` (`owner: "@git"`) is the only profile** → resolve the current operator =
    slug(`git config user.name`) and treat it as `<that>/N`. This is the normal git-identity path:
    every teammate's bare `N` scopes to their own stories.
  - **`operators/` exists, exactly one *named* profile** → treat as that operator's `N` (`<thatOwner>/N`).
  - **`operators/` exists, multiple profiles** → **ambiguous**: ask via `AskUserQuestion`, listing
    each operator's matching story count + SP for that `N`. Never guess; never invent a sprint.
    (With the generic profile present, prefer the current git operator as the default offered.)

A skill resolves only to an (`owner`,`sprint`) pair that actually exists in story frontmatter.

## Worktree / branch / port convention

> **`shared` isolation skips this entire section's worktree/branch machinery.** When
> `operator_isolation: shared`, no worktree or per-sprint branch is created or asserted — the build
> runs in the current checkout on the current branch and only **ports** below still apply. The rest of
> this section is the `worktree`-mode contract.

For operator `<name>` running sprint `N` **in `worktree` mode**, read the profile and derive:

- **branch** = the profile `branch` with `<n>` → `N` (default pattern `sprint/<name>-<n>`).
- **worktree** = the profile `worktree` path (default sibling `../<repo>-<name>`).
- **ports** = the profile `ports` block. `web` is the dev-server port; `supabase` is the **base** of
  the local Supabase port block — each operator must pick a non-overlapping base (offset siblings by
  ≥100, e.g. 54321 / 54421) so two local stacks coexist. How the ports are consumed is owned by the
  active `stack-profiles/*.md`; the profile only declares the bases.

The `scripts/scaffold-plan.py operator <name> --sprint N` helper creates the worktree + branch from
these values (idempotently) and prints the resolved ports/env. Skills never create worktrees; they
**read** the profile to know which branch/ports they should already be running in.

## What skills read vs. write

- **Read-only of profiles:** every skill. They resolve the sprint arg and (for build/run stages) read
  ports. **In `worktree` mode**, build/run stages also **assert the current git branch matches the
  resolved profile branch before mutating** — a mismatch is a hard stop ("you're on `main`, not
  `sprint/brij-2`; run the operator helper or `cd` into the worktree"). **In `shared` mode this branch
  assertion is skipped** — the build runs on the current branch in the current checkout.
- **Commits/PRs carry the operator.** Every build commit gets an **`Operator: <owner>` trailer**
  (`<owner>` = the resolved slug, e.g. `Operator: brij-1lattice`) — machine-readable and squash-merge
  proof — on top of the normal git author. In `shared` git-identity mode this trailer + the git author
  (the teammate's own identity) + the story `owner:` are the three ways to attribute a change; there is
  no per-operator branch. `git log --grep "Operator: <owner>"` lists one owner's work.
- **No skill writes operator profiles** — operators maintain them by hand (the generic `self.md` rarely
  changes), the same way `.claude/pipeline.config.md` is maintained.

## Adding a teammate (git-identity mode)

Nothing to create. A new teammate just:
1. clones the repo and sets a clean `git config user.name` (it slugifies to their owner handle);
2. creates stories — `manage-stories` defaults `owner:` to their git slug (config `default_owner:
   "@git"`), so the stories are theirs (`<their-slug>/N`);
3. works on **their own branch** and opens a **PR to `main`**.

No `.claude/operators/<name>.md` is needed — the shared `self.md` covers everyone. (Add a named
profile only for per-person goal tables or model overrides.)

## Backward compatibility (the invariant)

If `.claude/operators/` is absent, **nothing above applies**: `sprint:` is the global release
grouping, `default_owner` fills `owner`, INDEX groups by sprint→topic, and the build runs on the
current branch — identical to the single-operator pipeline. Multi-operator mode is purely additive.

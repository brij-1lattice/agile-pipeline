# Reference — operator profiles & owner-scoped sprints

> Single source of truth for **multi-operator mode**: how several people each run their own sprint
> in parallel on one project without colliding. Every skill that takes a sprint argument resolves it
> through the rules here; none redefine them. **This mode is opt-in and fully backward compatible** —
> a project with **no `.claude/operators/` directory** behaves exactly as the single-operator pipeline
> always has (global `sprint:` grouping + `default_owner`). The moment one or more operator profiles
> exist, the owner-scoped behavior below takes precedence.

## The model in one line

A **sprint is owned by one operator** and addressed `owner/N` (e.g. `brij/2`). It is one person's
batch of work with a one-line goal, built in that operator's **own git worktree on their own branch**
with their **own dev + Supabase ports**, then merged to `main` via PR. Because each operator owns an
isolated worktree, two operators building at once can never corrupt each other — the existing
one-builder-per-tree HARD RULE stays true *within* a worktree.

No new story field is introduced: a story's existing `owner` + `sprint` frontmatter pair **is** its
operator sprint. `owner: brij` + `sprint: 2` ⇒ `brij/2`.

## Operator profile file

One markdown file per operator at **`.claude/operators/<name>.md`** (the `<name>` matches the story
`owner` field). Schema:

```yaml
---
owner: brij                        # required; matches story `owner:` and the filename
branch: sprint/brij-<n>            # required; `<n>` is filled with the sprint number at use time
worktree: ../<repo>-brij          # required; sibling dir the worktree is created at
ports:                             # required; base ports this operator owns (see Port convention)
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

- **`owner/N`** → stories where `owner == <owner>` **AND** `sprint == <N>`.
- **bare `N` / `Sprint N` / label**, and:
  - **no `.claude/operators/` dir** → stories where `sprint == <N>` (today's global behavior).
  - **`operators/` exists, exactly one profile** → treat as that operator's `N` (`<thatOwner>/N`).
  - **`operators/` exists, multiple profiles** → **ambiguous**: ask via `AskUserQuestion`, listing
    each operator's matching story count + SP for that `N`. Never guess; never invent a sprint.

A skill resolves only to an (`owner`,`sprint`) pair that actually exists in story frontmatter.

## Worktree / branch / port convention

For operator `<name>` running sprint `N`, read the profile and derive:

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
  branch + ports. **Build/run stages assert the current git branch matches the resolved profile
  branch before mutating** — a mismatch is a hard stop ("you're on `main`, not `sprint/brij-2`; run
  the operator helper or `cd` into the worktree").
- **Commits/PRs** carry the operator: builders stamp the operator in the commit trailer/PR so `main`
  history shows whose sprint a change came from.
- **No skill writes operator profiles** — operators (or the helper, on first `--sprint`) maintain
  them by hand, the same way `.claude/pipeline.config.md` is maintained.

## Backward compatibility (the invariant)

If `.claude/operators/` is absent, **nothing above applies**: `sprint:` is the global release
grouping, `default_owner` fills `owner`, INDEX groups by sprint→topic, and the build runs on the
current branch — identical to the single-operator pipeline. Multi-operator mode is purely additive.

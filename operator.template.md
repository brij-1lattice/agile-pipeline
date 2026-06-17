# Operator profile — TEMPLATE

> An operator is a **person**, not a subsystem. Creating the first profile under `.claude/operators/`
> **switches the project into multi-operator mode**: sprints become owner-scoped (`<owner>/N`) and
> skills resolve work by owner. With **no** `.claude/operators/` directory, the pipeline stays
> single-operator and behaves exactly as before — operator profiles are opt-in. See
> `pipeline/reference/operator-profile.md` for the full contract (the `@git` token, slugify rule,
> isolation modes, and resolution rules).
>
> **Pick the shape that matches how your team works** — the two forms below resolve to the same
> owner-scoped sprints; they differ only in *how operators isolate* (`operator_isolation` in
> `.claude/pipeline.config.md`, absent → `worktree`).

---

## Form A — Generic git-identity profile (recommended for a team on separate devices)

> **One committed file shared by everyone**, copied to `.claude/operators/self.md`. The owner is the
> **`@git` token**: it resolves at runtime to `slug(git config user.name)`, so each teammate's git
> identity *is* their operator — zero per-person setup. Pair with `operator_isolation: shared` and
> `default_owner: "@git"` in the config: each teammate works in **their own clone, on their own
> branch**, builds straight into `{app_dir}`, and opens a **PR to `main`** (the per-device clone is the
> isolation — no worktree). The filename is `self` (it does not match a person) — the one allowed
> exception to filename-matches-owner, because the owner is dynamic.

```yaml
---
owner: "@git"                      # resolve to slug(git config user.name) at runtime (the shared identity)
isolation: shared                  # build in the current checkout — no worktree (falls back to config operator_isolation)
branch: current                    # build on whatever branch you're on; PR to main
worktree: .                        # no sibling worktree is created in shared mode
ports:                             # local dev-server ports (each teammate is on their own device)
  web: 3001                        # your dev-server port
# exec_model: sonnet               # optional override; omit to inherit the config global
---
```

> With the generic `@git` operator there is **no per-person goals table** — per-sprint goal labels fall
> back to the global `sprint_labels` map in `.claude/pipeline.config.md`.

---

## Form B — Per-person profile (several operators sharing one machine, or per-person goals/models)

> One file per operator at `.claude/operators/<your-name>.md`; the `<name>` must match the `owner:`
> field on the stories you'll build. With `operator_isolation: worktree` each operator builds in its
> **own git worktree on its own branch** with its **own ports**. After filling it in, run
> `python3 scaffold-plan.py operator <name> --sprint N` to create your git worktree + branch and print
> your ports. (A `self.md` and named profiles can coexist; named ones win for their owner.)

```yaml
---
owner: brij                        # matches story `owner:` and this filename
isolation: worktree                # build in a sibling git worktree (falls back to config operator_isolation)
branch: sprint/brij-<n>            # `<n>` is filled with the sprint number; keep the <n> placeholder
worktree: ../<repo>-brij          # sibling dir your worktree is created at
ports:                             # base ports you own — pick a block no other operator uses
  web: 3001                        # your dev-server port
  supabase: 54321                  # base of your local Supabase port block (offset siblings by >=100)
# Optional per-operator model overrides (omit to inherit the config globals):
# exec_model: sonnet
---
```

## Sprints

> Your owned sprints (Form B). `Goal` is the one-line description shown for `<name>/N` in the INDEX and
> skill summaries. `Status` is your own free-text tracking (`planning | active | done`) — it does not
> drive the pipeline; story `status` remains the only lifecycle source.

| N | Goal | Status |
|---|---|---|
| 2 | Expert directory + booking | active |

# Operator profile — TEMPLATE

> Copy this to `.claude/operators/<your-name>.md` (one file per operator) to run your **own sprints
> in parallel** with other operators on the same project. The `<name>` must match the `owner:` field
> on the stories you'll build. See `pipeline/reference/operator-profile.md` for the full contract.
>
> Creating the first operator profile **switches the project into multi-operator mode**: sprints
> become owner-scoped (`<name>/N`) and skills resolve work by owner. With **no** `.claude/operators/`
> directory, the pipeline stays single-operator and behaves exactly as before — this file is opt-in.
>
> After filling it in, run `python3 scaffold-plan.py operator <name> --sprint N` to create your git
> worktree + branch and print your ports.

```yaml
---
owner: brij                        # matches story `owner:` and this filename
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

> Your owned sprints. `Goal` is the one-line description shown for `<name>/N` in the INDEX and skill
> summaries. `Status` is your own free-text tracking (`planning | active | done`) — it does not drive
> the pipeline; story `status` remains the only lifecycle source.

| N | Goal | Status |
|---|---|---|
| 2 | Expert directory + booking | active |

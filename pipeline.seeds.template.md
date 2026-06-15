# Pipeline seed manifest — TEMPLATE

> **Optional** input for `scripts/scaffold-plan.py`. Copy this file to
> `.claude/pipeline.seeds.md` and replace the example rows with your own — each row tells the
> scaffolder to copy one stashed or misplaced source file into its correct home while it
> verifies/creates the planning tree. If this file is absent, the scaffolder simply skips the
> copy step (it still creates directories and checks documents).
>
> **Paths** are relative to the project root (the dir holding `.claude/`).
>
> **`overwrite` column:** `no` (default) never clobbers an existing destination — the row only
> acts as a bootstrap fallback when the destination is genuinely absent (so a curated doc is
> safe). `yes` forces the copy; the `--force` CLI flag overrides every row. A missing source is
> reported as a warning, not an error.
>
> Delete the example rows below before use — they are illustrative only.

| source | destination | overwrite |
|---|---|---|
| `path/to/stashed-original.md` | `plan/SOME-DOC.md` | `no` |
| `misplaced-file.md` | `.claude/skills/<skill>/file.md` | `no` |

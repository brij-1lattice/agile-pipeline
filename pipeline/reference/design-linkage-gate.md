# Reference — design-linkage gate

> Single source of truth for resolving a story's `design:` field. Run by `manage-stories` on
> every UI-touching create, and re-run by `analyze-sprint` when a story's linkage is empty or
> stale. Paths resolve through `.claude/pipeline.config.md` (`design_dir`, `design_ext`).

The `{design_dir}` folder holds design artifacts — the prototype/spec files (extension
`{design_ext}`) produced by the design tool. The `design:` frontmatter links each story to its
design.

## Allowed `design:` values

| Value | Meaning |
|---|---|
| List of paths under `design/` | Normal case. Each path must resolve on disk at write time. |
| `none-needed` | Backend / API / data-only story with no UI surface. **Must be chosen explicitly** — never assumed. |
| `follows-template: <story-id>` | Reuses another already-linked story's design. The referenced story must have a non-empty `design:`. |
| `[]` (empty) | Valid only transiently while awaiting a design. Lint flags it `missing-design`. |

## The gate (four exits — one must be chosen)

A UI-bearing story with an unresolved `design:` is **never written**. On every UI-touching
create (or re-confirmation):

1. Scan `{design_dir}` for artifacts whose names (or quick keyword content match) plausibly map to the story.
2. **Candidate found** → propose it; the user accepts, picks another, or overrides to `none-needed` / `follows-template:`.
3. **No candidate** → ask via `AskUserQuestion` with four options:
   - **(a) Provide a path** — verify the file exists before recording.
   - **(b) `none-needed`** — explicit declaration of no UI surface.
   - **(c) `follows-template: <story-id>`** — reuse another story's design (list candidate IDs from the same topic).
   - **(d) Upload now & re-run** — the user will drop a file in `{design_dir}` first; write nothing for this story this run.

`analyze-sprint` adds two re-confirmation checks: a `none-needed` story whose clarified ACs now
imply UI → switch to a path; a listed path that no longer resolves → ask for a correction. An
unresolved linkage at analysis time → defer the story to `{backlog_dir}` (it is not analyzed).

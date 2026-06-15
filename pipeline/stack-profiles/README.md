# Stack profiles

A stack profile is the **only** framework/language-specific part of the pipeline. It isolates
everything `execute-sprint`, `sprint-story-builder`, and `verify-sprint` need that depends on
the target stack, so the orchestration logic (dispatch, escalation, partial-continuation,
audit) stays identical across projects.

A project selects its profile in `.claude/pipeline.config.md` (`stack_profile: <name>`), and
the skills read `pipeline/stack-profiles/<name>.md`.

## Authoring a new profile

Copy `nextjs14-supabase.md` and replace each section with your stack's equivalent. A profile
**must** provide these headings (the skills look for them by role):

| Heading | Used by | What it provides |
|---|---|---|
| **Toolchain preflight** | execute-sprint | what must be installed/running before any build; absence = run-level blocker |
| **Scaffold** | execute-sprint | first-run project creation, committed before story 1 |
| **Directory layout** | builder, verify | where built code/tests/migrations land under `{app_dir}` |
| **Gate commands** | builder | the ordered checks a story must pass to reach `done` |
| **Test toolchain** | builder | unit/e2e/a11y frameworks + mock/stub strategy |
| **Render command** | builder, verify | how to screenshot a built route for `(visual)` AC checks |

Keep all paths config-driven (`{app_dir}`, `{design_dir}`, tech-spec section roles) so the
profile carries stack specifics, not project specifics. Examples to write: `vite-react-spa`,
`python-fastapi`, `go-chi`, `rails`, `expo-react-native`.

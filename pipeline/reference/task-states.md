# Reference — task states & the done-gate

> Single source of truth for the `## Tasks` checklist. `manage-stories` creates the section
> empty; `analyze-sprint` populates it; `sprint-story-builder` advances the markers.

Tasks live as a checklist inside `## Tasks`. Each line begins with a **lifecycle state** in
square brackets. Exactly five states — no others:

| State | Marker | Meaning |
|---|---|---|
| new | `[new]` | Identified, not picked up. Default for newly written tasks. |
| started | `[started]` | Work in progress. |
| completed | `[completed]` | Done. |
| cancelled | `[cancelled]` | Decided not to do (scope cut, duplicate, already satisfied, obsolete). |
| hold | `[hold]` | Paused — blocked on external input or another story. Append the reason in parens, e.g. `[hold] (a required external-service key unavailable — dependent send blocked)`. |

## Empty (create-time) form

`manage-stories` writes the section as a single placeholder and sets `tasks_populated: false`:

```markdown
## Tasks
<!-- Populated by analyze-sprint, not by manage-stories. Each task maps to one or more
     acceptance criteria and is small enough to land in a single commit. -->
- [ ] TODO — break this story into implementation tasks
```

`analyze-sprint` replaces the TODO line with real `[new]` tasks and sets
`tasks_populated: true`.

## The done-gate

A story may be set `status: done` **only** when:

- `tasks_populated: true`, **and**
- every task line is `[completed]` or `[cancelled]`.

`manage-stories update` enforces this and refuses to write `done` otherwise.
`sprint-story-builder` may mark a task `[cancelled]` (with a one-line reason recorded in its
RESULT) when the codebase already satisfies it — but may never add scope beyond the ACs.

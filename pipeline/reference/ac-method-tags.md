# Reference — acceptance-criterion verification-method tags

> Single source of truth for the AC method tag. `analyze-sprint` writes it, `manage-stories`
> lint tolerates it, `sprint-story-builder` consumes it, `verify-sprint` re-checks it.

`analyze-sprint` prefixes **every** acceptance-criterion line with exactly one method tag, so
the verification method is decided once — upstream — and nothing silently degrades to an
unrecorded manual IOU at build time.

| Tag | Meaning | How the builder discharges it |
|---|---|---|
| `(unit)` | A unit / schema / utility assertion covers it. | Write the unit test. |
| `(e2e)` | An end-to-end flow covers it. | Write the e2e test. |
| `(axe)` | An automated a11y assertion covers it. | Add the a11y check. |
| `(visual)` | Only verifiable by *looking* — typography family, accent colour, layout fidelity to the prototype. | Screenshot the built route and confirm by eye against the design; `verify-sprint` re-checks in fresh context. |
| `(manual)` | Needs a human / non-automatable check. | Record a documented manual check in `## Notes`; it is counted and surfaced downstream, never silently skipped. |

Example:

```markdown
## Acceptance criteria
- [ ] (e2e) GET /items?category=X returns only items where category = X
- [ ] (visual) active category pill is marked active per design tokens
- [ ] (axe) page has zero critical/serious a11y violations
```

Rules:
- Prefer an automatable method wherever one exists; reserve `(visual)`/`(manual)` for what
  genuinely can't be asserted in code.
- The `(unit)`/`(e2e)`/`(axe)` tags scope the **builder's** happy-path tests. `generate-test-sprint`
  later writes the *adversarial complement* (empty/error/permission/boundary states the tags didn't
  claim) under `{app_dir}e2e/qa/` — it must **not** duplicate a tagged AC's assertion.
- The tags are valid AC syntax — preserve them, never strip. Lint flags an `analyzed: true`
  story with any untagged AC (`untagged-ac`, warning).
- `manage-stories` writes ACs **untagged** at create time (the method isn't known until
  analysis); `analyze-sprint` adds the tags during its prototype-reconciliation step.

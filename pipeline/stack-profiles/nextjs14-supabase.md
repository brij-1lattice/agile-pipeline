# Stack profile — nextjs14-supabase

> The stack-specific half of the pipeline. `execute-sprint` (scaffold + toolchain preflight),
> `sprint-story-builder` (gate + test toolchain), and `verify-sprint` (render) read this
> profile by name from `.claude/pipeline.config.md` (`stack_profile: nextjs14-supabase`).
> `{app_dir}` / `{design_dir}` / `{design_doc}` / section refs resolve through that config.
> A different stack supplies its own profile with the same headings; the orchestration logic
> never changes.

## Toolchain preflight

Confirm before any build: **Node 20** and **pnpm** available; **Docker** running (local
Supabase dev stack); Playwright browsers installable. A missing toolchain is a run-level
blocker (nothing can build).

## Scaffold (first run only — when `{app_dir}` is absent)

Create the production project per the tech spec `stack` + `structure` sections, then commit it
before building any story:

- Next.js 14 **App Router** + **TypeScript strict** (`strict: true`, `noUncheckedIndexedAccess: true`), Node 20, **pnpm**.
- **Tailwind CSS** with `{app_dir}tailwind.config.ts` extending the design tokens (from the design-token reference in `{design_dir}` / `{design_doc}`); thin `{app_dir}globals.css` for resets + `@font-face` only (no per-component CSS).
- **Supabase** via `@supabase/ssr` — server/client/middleware factories in `{app_dir}lib/supabase/`; `{app_dir}supabase/migrations/` + `seed.sql`; `{app_dir}types/database.ts` for generated types. Use the local Supabase dev stack for running tests.
- `{app_dir}middleware.ts` gating the authenticated route groups per the tech spec `auth` section.
- Directory roots per the `structure` section: `{app_dir}app/`, `{app_dir}lib/{schemas,supabase,email,search,utils}/`, `{app_dir}components/`, `{app_dir}supabase/`, `{app_dir}types/`.
- **Env:** a committed `{app_dir}.env.example` listing every var from the tech spec `env` section, and a git-ignored `{app_dir}.env.local` populated with whatever is available (local Supabase keys + safe test stubs). External-service keys absent → fine for the scaffold; they only matter when a specific story's tests need them.

The scaffold is **not** a story — it's the substrate the first sprint's stories build on.

## Directory layout (where built code lands)

Routes in `{app_dir}app/`, shared code in `{app_dir}lib/` + `{app_dir}components/`, DB migrations
in `{app_dir}supabase/migrations/`, generated types in `{app_dir}types/database.ts`, unit tests
`*.test.ts(x)` beside their source, E2E in `{app_dir}e2e/`.

## Gate commands (run in order from `{app_dir}`)

```
pnpm typecheck
pnpm lint
pnpm test          # Vitest unit suite
pnpm build
pnpm e2e           # Playwright, against the local Supabase stack + stubbed externals
```

All five must pass for a story to reach `done`. A red gate → fix and re-run (subject to
`max_fix_attempts` from config).

## Test toolchain

- **Unit:** Vitest + React Testing Library, Supabase client mocked, external-service clients stubbed. Every `app/api/*` route → ≥1 unit test; Zod schemas and non-trivial utilities unit-tested.
- **E2E:** Playwright per page/flow, against the local Supabase stack.
- **A11y:** axe-core check on each key page (per the tech spec `testing` section), zero critical/serious violations.

## QA test toolchain (generate-test-sprint + qa-sprint)

The QA gauntlet's adversarial tests live in a **separate namespace** from the builder's, so the
two never tangle:

- **Location:** Playwright specs in `{app_dir}e2e/qa/`; unit specs as `*.qa.test.ts` beside their source.
- **Authoring** (`generate-test-sprint` → `qa-test-author`): write the adversarial complement (empty / error / permission / boundary), `{external_services}` stubbed, Supabase mocked (unit) / local stack (e2e). Ensure they compile — `pnpm typecheck` + `pnpm lint` on the new files — but **do not** run them for pass/fail.
- **Running** (`qa-sprint`): run just the QA namespace — `pnpm test` over the `*.qa.test.ts` files (Vitest) and `pnpm e2e e2e/qa/` (Playwright) against the local Supabase stack. Capture each failure with its `file:line`.
- Once committed, the QA specs join the **permanent gate** — the builder's `pnpm test` / `pnpm e2e` pick them up on every future run, so a QA-authored regression test guards the codebase for good. **Because they're permanent, a later fix can turn one red when a requirement legitimately changed** — ownership for editing/retiring such a test is the changed-requirement rule in `pipeline/reference/review-feedback-format.md` (builder edits one with a two-sided citation; bulk re-author via `/generate-test-sprint --recheck`). A red QA test is never edited away just to green the gate.

## Render command (for `(visual)` ACs and verify-sprint)

Drive the built route with Playwright against the local Supabase stack and capture a
screenshot (`page.screenshot(...)` in a throwaway spec, or reuse an E2E's page), to compare the
rendered output against the linked prototype screen and the design-doc token rules.

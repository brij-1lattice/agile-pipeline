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

**Every command is non-interactive, non-watch, and time-bounded.** Run each under
`timeout {gate_timeout}` and with `CI=true` so nothing waits on a TTY, a file-watcher, or a
dev-server that never backgrounds — a hung command is *killed* and surfaces as a normal gate
failure (`timeout` exit code `124`) rather than blocking the subagent (and the orchestrator)
forever. Use Vitest **`run`** mode (never bare `vitest`, which watches) and let Playwright manage
its own server via `webServer.reuseExistingServer` + a bounded `webServer.timeout` in
`playwright.config.ts` (never a foreground `next dev` that blocks on stdin).

**Final gate (full — the gate for `done`):**

```
pnpm typecheck
pnpm lint
CI=true timeout {gate_timeout} pnpm test -- --run     # Vitest, run mode (whole unit suite)
timeout {gate_timeout} pnpm build
CI=true timeout {gate_timeout} pnpm e2e               # Playwright, local Supabase stack + stubbed externals
```

All five must pass for a story to reach `done`.

**Inner-loop (scoped) gate — fast feedback while fixing.** During the fix-and-retry cycles the
builder does *not* need the whole suite + a full production build each attempt. Run the scoped
subset for quick signal, and run the **Final gate above exactly once** to green it before flipping
`status: done`:

```
pnpm typecheck
CI=true timeout {gate_timeout} pnpm test -- --run --changed   # only tests related to the diff
CI=true timeout {gate_timeout} pnpm e2e {story e2e spec(s)}   # only this story's specs
```

A red gate → fix and re-run (subject to `max_fix_attempts` from config). The final full gate is
authoritative — a scoped-green story is **not** `done` until the full gate passes once.

## Test toolchain

- **Unit:** Vitest + React Testing Library, Supabase client mocked, external-service clients stubbed. Every `app/api/*` route → ≥1 unit test; Zod schemas and non-trivial utilities unit-tested.
- **E2E:** Playwright per page/flow, against the local Supabase stack.
- **A11y:** axe-core check on each key page (per the tech spec `testing` section), zero critical/serious violations.

## QA test toolchain (generate-test-sprint + qa-sprint)

The QA gauntlet's adversarial tests live in a **separate namespace** from the builder's, so the
two never tangle:

- **Location:** Playwright specs in `{app_dir}e2e/qa/`; unit specs as `*.qa.test.ts` beside their source.
- **Authoring** (`generate-test-sprint` → `qa-test-author`): write the adversarial complement (empty / error / permission / boundary), `{external_services}` stubbed, Supabase mocked (unit) / local stack (e2e). Ensure they compile — `pnpm typecheck` + `pnpm lint` on the new files — but **do not** run them for pass/fail.
- **Running** (`qa-sprint`): run just the QA namespace — `CI=true timeout {gate_timeout} pnpm test -- --run` over the `*.qa.test.ts` files (Vitest) and `CI=true timeout {gate_timeout} pnpm e2e e2e/qa/` (Playwright) against the local Supabase stack (reuse one stack per session per the *Render command* note). Capture each failure with its `file:line`.
- Once committed, the QA specs join the **permanent gate** — the builder's *Final* gate (`pnpm test` / `pnpm e2e`) picks them up on every future run, so a QA-authored regression test guards the codebase for good. To keep this permanent growth from taxing every fix attempt, the builder's **inner-loop (scoped) gate skips the full QA namespace** (it runs `--changed` + the story's own specs); the whole QA suite runs in the **Final gate** and in `qa-sprint`. **Because they're permanent, a later fix can turn one red when a requirement legitimately changed** — ownership for editing/retiring such a test is the changed-requirement rule in `pipeline/reference/review-feedback-format.md` (builder edits one with a two-sided citation; bulk re-author via `/generate-test-sprint --recheck`). A red QA test is never edited away just to green the gate.

## Parallelism & caching (in-run speed — set in the Scaffold's configs)

Each gate run is faster when the test runners use all cores and reuse caches. The Scaffold wires
these into the generated `vitest.config.ts` / `playwright.config.ts`; the gate commands above stay
unchanged.

- **Playwright — set `workers` explicitly (don't let `CI=true` throttle to 1).** The gate commands
  run `pnpm e2e` with `CI=true` (for non-interactivity / no watch), and **under `CI=true` Playwright
  defaults to `workers: 1`** — serializing the whole e2e suite. Counter it: in `playwright.config.ts`
  set `fullyParallel: true` and an explicit `workers` (e.g. `workers: process.env.CI ? '50%' : '100%'`,
  or a fixed N), **or** pass `--workers=<N>` on the `pnpm e2e` command. Config/flag wins over the CI
  default, restoring parallel e2e.
- **Vitest — keep it multi-threaded.** Vitest runs test files in parallel via worker threads by
  default; the Scaffold must **not** pin `pool: 'forks'` with `singleFork`, `singleThread: true`, or
  `maxWorkers: 1`. Leave the default worker pool (optionally `poolOptions` tuned to cores).
- **Caching — keep it warm across the session.** With one stack reused per session (see *Render
  command*) the working dir persists between stories, so let the caches persist too: `.next/cache`
  (makes each `pnpm build` **incremental** instead of cold), Vitest's cache, and the Playwright
  browser cache. **Git-ignore them** (`.next/`, etc.) so `execute-sprint`'s escalation reset
  (`git clean -fd`, which respects `.gitignore`) does **not** wipe them. Never `rm -rf .next` between
  stories.
- **(Optional)** `next build` with Turbopack once stable for your Next version — opt-in, validate the
  build output first; not the default.

## Render command (for `(visual)` ACs and verify-sprint)

Drive the built route with Playwright against the local Supabase stack and capture a
screenshot (`page.screenshot(...)` in a throwaway spec, or reuse an E2E's page), to compare the
rendered output against the linked prototype screen and the design-doc token rules.

**Bounded, never a foreground dev-server.** Render against a **built** server — `next build` then
`next start` on a fixed port — and run the screenshot spec under `timeout {gate_timeout}`, e.g.:

```
CI=true timeout {gate_timeout} pnpm exec playwright test <throwaway-screenshot-spec>
```

Let Playwright own the server through `webServer` (`reuseExistingServer: true`, bounded
`webServer.timeout`); never launch an unbounded foreground `next dev` that blocks on stdin. If the
render can't complete inside `{gate_timeout}` it is a render failure to report — not a hang.

**Reuse one stack per session.** Booting the dev/`next start` server + the local Supabase stack
costs tens of seconds; pay it **once per session**, not per story. Start the stack at the first
render/e2e of a run and keep it up (`reuseExistingServer: true` reattaches to it) so subsequent
stories in the same `qa-sprint` / `verify-sprint` / build session skip the boot. (Multi-operator:
the reused stack binds the operator's profile ports so operators still don't collide.)

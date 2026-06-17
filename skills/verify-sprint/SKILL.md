---
name: verify-sprint
description: Independent design-parity audit of a tested sprint — checks each story's shipped output against its prototype screen + design doc in fresh context, writes real findings into the story's own Verification Feedback section, and moves the story to verified (clean, terminal) or verification-failed (gaps to fix). Stage 4 — the terminal sign-off — of the QA gauntlet, downstream of /qa-sprint.
---

# verify-sprint

**Stage 4 — the terminal sign-off — of the QA gauntlet**, downstream of `/qa-sprint`. Code review
and the test stages proved the code is correct, safe, and robust; this last pass proves it *matches
the design*. A test written by the mind that misread a screen encodes the same misreading, and
purely-visual detail (typography, accent colour, a missing control no AC named) sails through every
textual gate. This skill is the independent second look — **per story, in fresh context, with eyes
on the rendered output** — comparing the shipped app against the prototype it ported.

It turns a `tested` story into a **`verified`** one (the terminal state — all four gates clear) when
the build is faithful, or into a **`verification-failed`** one when it isn't — writing the real gaps
into that story's own **`## Verification Feedback`** section so the **next `/execute-sprint` run
fixes them in place**. There is **no separate ledger file and no separate fix story** — the story
owns its findings.

It does **not** edit `{app_dir}`, **not** touch scope/ACs, and makes only the status move
`tested → verified | verification-failed`. An audit produces *findings written into the story*,
never silent rework.

## Configuration

All paths/docs/section-refs resolve from **`.claude/pipeline.config.md`** — read it first. How to
render a built route for the visual pass comes from the stack profile's *Render command*
(`.claude/pipeline/stack-profiles/{stack_profile}.md`). Shared contracts:
- Verification Feedback item format (design severity, tags, two-sided citation) → `.claude/pipeline/reference/review-feedback-format.md`
- Frontmatter / statuses / body sections → `.claude/pipeline/reference/frontmatter-schema.md`
- AC method tags → `.claude/pipeline/reference/ac-method-tags.md`
- Sprint resolution & dependency ordering → reuse `analyze-sprint`/`execute-sprint`

Key paths: stories `{stories_dir}<topic>/story-*.md`; design doc `{design_doc}` (locked UI
rules/tokens); tech spec `{tech_spec}` (its `ui_rules` section **outranks** the prototype — a detail
the tech-spec overrode is **not** a deviation); prototype `{design_dir}*.{design_ext}`; built app
`{app_dir}`. **Model:** spawn auditors on `{verify_model}` (absent → `{escalation_model}` →
`{default_exec_model}`).

## Input — the sprint

One argument resolved as `execute-sprint` does (single-operator `N`/label, or multi-operator
`owner/N` per `operator-profile.md`; the visual pass renders on the operator's profile ports).
Absent/ambiguous → ask (show how many stories are already `verified`). `--reverify` re-audits
`verified` stories; a single story id audits just that one. Never invent a sprint.

## Selection

1. Collect `{stories_dir}**/story-*.md` (exclude `{archive_dir}`, `{backlog_dir}`) whose `sprint:` matches (multi-operator: and whose `owner:` matches the resolved `owner/N`) and `status: tested`. (`tested` is the audit input — a story that cleared code review + the test stages.) Earlier-stage stories → report and route onward (`done`→`/code-review-sprint`, `code-reviewed`→`/generate-test-sprint`, `tests-generated`→`/qa-sprint`; a `*-failed` story must be re-built to `done` and re-flowed before it reaches here).
2. Skip `status: verified` unless `--reverify`. Report the skip count.
3. `design: none-needed` → lightweight audit (no visual pass): confirm the surface is genuinely backend/data-only and matches the tech spec; set `verified` unless it contradicts the schema/api/security sections.

## Orchestration — fresh context per story

Each story is audited by **one freshly-spawned subagent** so its judgment isn't anchored by the
builder's rationalizations. Auditors never write `{app_dir}` or story files (no shared-tree hazard),
so the **orchestrator does all writes** (the story's status + `verified_date` +
`## Verification Feedback` section) after audits return. **It does not regenerate `{index_path}`**
(parallel-chain skill — print a one-line `/manage-stories index` reminder instead).

> **Concurrency caveat — the visual pass is not free.** Read-only *of files* ≠ free-running: the
> visual pass **renders the built route** (boots a dev server + the local Supabase stack on fixed
> ports), so two auditors at once — or a concurrent `qa-sprint` in the same checkout — **collide on
> the render port / DB**. Dispatch auditors **serially** by default; only run them (or this whole
> skill alongside `qa-sprint`) in parallel when each has its **own git worktree + stack/port**.
> Stories whose `design: none-needed` (code-only audit, no render) have no such constraint and may
> be audited concurrently. **Reuse one stack per session** (stack profile's *Render command* note):
> boot the render server + Supabase once and let `reuseExistingServer` reattach, so serial auditors
> skip the per-story boot.

**Partition the selected stories by whether they render**, then dispatch each group accordingly:
- **`design: none-needed` (code-only, no render)** → **fan out in parallel** — these auditors boot no
  server and touch no port, so spawn them concurrently (a batch of `Agent` calls per message, up to
  the harness cap) exactly like `code-review-sprint`.
- **Render-needed** → **serial by default** — they share the render port / stack (see the caveat
  above); spawn one → await its AUDIT → next, unless each has its own worktree + stack/port.

Spawn each auditor (a general read-only subagent) on `{verify_model}` with the **Per-story audit
protocol** below, plus `story_id`, the file path, its `design:` paths, and **references** to the
relevant `{design_doc}` / `{tech_spec}` `ui_rules` sections (by role — the auditor opens those docs
and reads them itself; **don't inline the section bodies** into the spawn prompt, which would
duplicate them across concurrent `none-needed` audits). Each returns one **AUDIT block**.

## Per-story audit protocol (runs inside each auditor)

> **The cardinal rule — verify, never summarize** (per `review-feedback-format.md`). Every finding
> cites exact `file:line` on BOTH sides — the prototype line and the built line. Can't cite
> both → not a finding. Re-read cited lines before asserting a Severity-A/B gap.

1. **Read the story's ACs** (with their method tags) and any `## Notes` scope-cuts — a deliberately cut element is **not** a deviation. Read any existing `## Verification Feedback` so you don't re-file a fixed item.
2. **Read the linked prototype screen(s)** in `{design_dir}` and the governing `{design_doc}` rules. Enumerate the screen's concrete surface: sections, controls, states, featured slots, counts, copy, locked tokens.
3. **Read the built surface** in `{app_dir}` — cite files+lines that implement (or omit) each item.
4. **Render and look (visual pass).** Use the stack profile's *Render command* (bounded by `timeout {gate_timeout}`, reusing the session stack) to screenshot the built route, then **view it** against the prototype and the design-doc tokens. Confirm typography family, accent colour, layout fidelity, and the presence of every designed control by eye. If rendering can't run **or hits `{gate_timeout}`**, say so in the AUDIT `screenshots:` line and fall back to a code-only audit (note reduced confidence — don't silently skip, and don't hang waiting on a render).
5. **Classify each gap** per `review-feedback-format.md` (design severity A/B/C/D; tag `[true]`/`[justified]`/`[choice]`), against the precedence rule (tech spec `ui_rules` outranks the prototype). Only **`[true]` of severity A/B/C blocks**; a `[true]` **D** (copy/cosmetic nit) is a logged `> nit [D]:` note, not a gate failure. Verify any built-in justification claim against the tech spec.
6. **Return the AUDIT block.**

### AUDIT block (the auditor's entire substantive output)

```
AUDIT
story: <story_id>
verdict: clean | deviations
findings: <n blocking findings — [true] A/B/C only; D-nits/justified/choice don't count toward verification-failed>
screenshots: <captured paths, or "code-only — <why>">
items:
- sev: <A|B|C|D>  tag: <true|justified|choice>  surface: <screen/component>
  design: <file:line — what the prototype shows>
  build: <file:line — what shipped (or "absent")>
  note: <one line — why true/justified/choice; verify any justification claim>
  fix: <one line — the change that closes it>
notes: <≤2 lines — reduced-confidence flags, ambiguities>
```

`verdict: clean` only with zero **blocking** items (`[true]` A/B/C). `findings:` counts those only —
a `[true]` D nit, a `[justified]`, or a `[choice]` leaves the verdict `clean`.

## After the audits — the orchestrator writes

For each audited story (orchestrator-only — auditors wrote nothing):

1. **Write findings into the story's `## Verification Feedback`** in the `review-feedback-format.md` layout: each blocking `[true]` A/B/C finding as an open `- [ ]` checkbox line (design severity + surface + fix + both-sided citation); each `[true]` **D** as a `> nit [D]:` note; each `[justified]`/`[choice]` as a `>`-quoted note. Append to the section (don't wipe `- [x]` history from prior cycles).
2. **Set the review status** (the only status move; never revert past `tested`):
   - zero blocking items (`[true]` A/B/C) → `status: tested → verified` (terminal — all four gates clear; D nits / justified / choice don't block).
   - ≥1 blocking item → `status: tested → verification-failed`.
   - Either way stamp `verified_date: <today>`.
3. **Surface `[choice]` findings to the user** — print them as open decisions; do **not** auto-write them as actionable `- [ ]` items. Once the user decides, a follow-up `/verify-sprint <id>` or `/manage-stories` turns the decision into a `[true]` item or a note.
4. **Print a summary:** stories audited, `verified` vs `verification-failed`, `[true]` findings by severity (now sitting in each story's Verification Feedback), `[choice]` decisions awaiting the user, code-only audits to re-run. Point `verification-failed` stories at `/execute-sprint <N>` to fix and re-`done` (→ re-flow the gauntlet), then `/verify-sprint --reverify`. End with: "run `/manage-stories index` to refresh the board, then `/clear` before the next sprint or re-flow pass — each stage runs fresh from `status`, so clearing keeps the orchestrator lean."

## The killer self-test

Run `verify-sprint` against an already-built sprint you suspect shipped parity gaps. If it
independently resurfaces real deviations (with both-sided citations, written into the stories'
Verification Feedback), the loop is closed. If it comes back `verified` on a sprint you know had
gaps, the audit prompt is too weak — tighten the enumeration/visual steps before trusting it. An
audit that rubber-stamps is worse than none.

## Operating rules

- **Read-only auditors (of files); orchestrator-only writes.** Auditors never write the repo — but the visual pass renders on a shared port/stack, so dispatch them **serially by default** (concurrency needs a worktree + own stack per auditor; `none-needed` code-only audits are exempt).
- **Every finding cites two line references.** No summary-only claims; re-verify A/B findings.
- **Precedence:** `{tech_spec}` `ui_rules` outranks the prototype; a `## Notes` scope-cut is a decision, not a deviation.
- **Never edit `{app_dir}`; never edit an AC or scope.** Gaps become `## Verification Feedback` items the next build run fixes.
- **The only status move is `tested → verified | verification-failed`** — never revert to an earlier state, never touch a non-`tested` story.
- **`verification-failed` ⇔ ≥1 open blocking item** (`[true]` A/B/C); a `[true]` D nit, `[justified]`, or `[choice]` never forces it.
- **Never regenerate `{index_path}`** (parallel-chain skill) — only stamp the story's frontmatter + section. **Idempotent re-runs** (skip `verified` unless `--reverify`). **Never invent a sprint.**
- **Safe to interrupt.** State lives in story frontmatter — selection is by `status: tested`, so stop anytime (the render pass is serial and slow), `/clear`, and re-run `/verify-sprint <N>`: it resumes from where it stopped (already-`verified` stories are skipped).

## Files this skill touches

Orchestrator writes: `{stories_dir}<topic>/story-*.md` — `status` (`tested → verified |
verification-failed` only), `verified_date`, and the `## Verification Feedback` section. It **never**
edits status/scope/ACs beyond that one transition, and **never** writes `{index_path}` or
`{app_dir}`. Auditor subagents write **nothing** (read `{stories_dir}` + `{app_dir}`, capture
throwaway screenshots, return AUDIT blocks).

## When to bail and ask

- Sprint matches zero `tested` stories → list sprints with stories that cleared the test stages, ask.
- A story is earlier than `tested` → route to the right stage (`/code-review-sprint`, `/generate-test-sprint`, `/qa-sprint`, or `/execute-sprint` for a `*-failed` story).
- Rendering can't run → offer a code-only audit (flagged) or stop; never pass off code-only as a full visual audit.
- A `[choice]` finding → surface it to the user; don't auto-write it as actionable.

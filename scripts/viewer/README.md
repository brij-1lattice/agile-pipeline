# Spec Browser

A read-only, browser-based viewer for a pipeline project's story tree. It renders whatever it finds
in the project's `stories/INDEX.md` plus the individual story files — no build step, no install, no
framework. Neutral visual design (warm paper background, restrained accent, serif H1) with auto +
manual dark mode.

It is **config-driven**: it resolves the project root by walking up for
`.claude/pipeline.config.md` and reads `stories_dir` / `design_dir` from it, so the viewer files
stay here in `scripts/viewer/` and serve *any* pipeline project without being copied in.

## Run

From inside a pipeline project (or pass `--project`):

```bash
python3 scripts/viewer/serve.py start      # background — terminal stays yours
python3 scripts/viewer/serve.py stop       # kill it
python3 scripts/viewer/serve.py status     # is it running, on what port
python3 scripts/viewer/serve.py            # foreground — Ctrl+C to stop (logs visible)

# target a project explicitly (e.g. when running from elsewhere):
python3 /path/to/agile-pipeline/scripts/viewer/serve.py start --project /path/to/project
```

`start` picks the first free port in 8000–8050, opens your browser to
`http://localhost:<port>/viewer/`, and routes requests by prefix: `/viewer/*` → these files,
`/stories/*` → the project's `stories_dir`, `/design/*` → its `design_dir`. State is per-project
(`/tmp/agile-viewer-<project>.{pid,port,log}`), so several projects can run at once.

If the shebang errors because your shell's `python3` points at a missing binary, invoke an explicit
interpreter (any Python 3 stdlib works), e.g. `/usr/bin/python3 scripts/viewer/serve.py start`.

(Browsers block `fetch()` under `file://`, so a static server is required — you can't just
double-click `index.html`.)

## Layout

- **Left pane** — topics grouped by sprint. Click to filter the list.
- **Middle pane** — filtered story list. Filters: search (`/`), sprint, status, owner (sprint and
  status options are derived from the data, so they always match what's actually there).
- **Right pane** — full story detail: metadata chips, dependency / blocks graph, rendered markdown.

## Keyboard

- `/` — focus search · `Esc` — clear search
- `J` / `↓` — next story · `K` / `↑` — previous story
- `Enter` — focus the detail pane

## Theme

A button in the top-right cycles `auto → light → dark → auto`. The choice is remembered in
localStorage; default `auto` follows your OS's `prefers-color-scheme`.

## Sharing

URLs are hash-routed: `#/<topic>/<id>` — e.g. `http://localhost:8000/viewer/#/blog/story-blog-02`.
(The port may differ if 8000 was busy — see the launcher banner.)

## Notes

- Refresh after running `/manage-stories index` — the viewer reads `stories/INDEX.md` on load.
- The viewer is read-only. Edit stories through `/manage-stories` or your editor.
- Optional: to deep-link a design chip into a rendered prototype (instead of opening the raw source
  file), populate the `FILE_TO_ROUTE` map at the top of `viewer.jsx` with your prototype's routes.

#!/usr/bin/env python3
"""View the sprint board — a live, browser-based view of the story pipeline.

Config-driven, project-agnostic, stdlib-only (no pip install, no build step). Reads
the canonical paths/labels from `.claude/pipeline.config.md`, parses every story's
frontmatter + sections, and renders a board grouped by sprint → topic showing each
story's status and its progress through the QA gauntlet (Build → CR → Gen → Test →
Verify). It is a read-only view — it never writes a story, the INDEX, or the config.

Two modes:

  view-sprint.py [serve]              # default: live server on a free port
    Boots a tiny HTTP server and (unless --no-browser) opens the board. Each page
    refresh re-reads the stories from disk, so the board tracks status as you run
    the pipeline. Ctrl-C to stop.

  view-sprint.py build [--out FILE]   # one-shot static HTML
    Renders the board to a single self-contained .html file (default:
    `{working_root}/sprint-board.html`) and exits. Open it in any browser.

Usage:
    ./view-sprint.py                       # serve against the auto-detected project
    ./view-sprint.py --sprint 2            # show only sprint 2
    ./view-sprint.py --port 8900           # pin the port
    ./view-sprint.py --no-browser          # don't auto-open a browser
    ./view-sprint.py --project DIR         # target a specific project root
    ./view-sprint.py build                 # write a static sprint-board.html
    ./view-sprint.py build --out board.html

The viewer reflects the same single source of truth the INDEX projects from: each
story's `status` (see pipeline/reference/frontmatter-schema.md) and the open `- [ ]`
items in its three feedback sections (see review-feedback-format.md).
"""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import argparse
import html
import re
import socket
import sys
import webbrowser

CONFIG_REL = Path(".claude/pipeline.config.md")
OPERATORS_REL = Path(".claude/operators")

# Status → display. Order is the lifecycle order; colour groups good/working/bad.
STATUS_ORDER = [
    "verified", "tested", "tests-generated", "code-reviewed", "done",
    "in-progress", "ready", "draft",
    "code-review-failed", "testing-failed", "verification-failed",
    "blocked", "deferred",
]
STATUS_COLOR = {
    "verified": "#1a7f37", "tested": "#2da44e", "tests-generated": "#3fb950",
    "code-reviewed": "#57ab5a", "done": "#0969da", "in-progress": "#9a6700",
    "ready": "#6e7781", "draft": "#8c959f",
    "code-review-failed": "#cf222e", "testing-failed": "#cf222e",
    "verification-failed": "#cf222e", "blocked": "#bc4c00", "deferred": "#8250df",
}

# Pure function of status → the four gauntlet columns, per index-template.md.
# Value is "y" (passed), "f" (failed — caller fills the open-item count), or "-" .
GAUNTLET = {
    "draft":               ("-", "-", "-", "-"),
    "ready":               ("-", "-", "-", "-"),
    "in-progress":         ("-", "-", "-", "-"),
    "blocked":             ("-", "-", "-", "-"),
    "deferred":            ("-", "-", "-", "-"),
    "done":                ("-", "-", "-", "-"),
    "code-reviewed":       ("y", "-", "-", "-"),
    "code-review-failed":  ("f", "-", "-", "-"),
    "tests-generated":     ("y", "y", "-", "-"),
    "tested":              ("y", "y", "y", "-"),
    "testing-failed":      ("y", "y", "f", "-"),
    "verified":            ("y", "y", "y", "y"),
    "verification-failed": ("y", "y", "y", "f"),
}
GAUNTLET_COLS = ["CR", "Gen", "Test", "Verify"]


# ─────────────────────── config + frontmatter parsing ───────────────────────

def find_project_root(start):
    """Walk up from `start` to the first dir containing the pipeline config."""
    for d in [start, *start.parents]:
        if (d / CONFIG_REL).is_file():
            return d
    return None


def _strip_scalar(v):
    return v.split("#", 1)[0].strip().strip('"').strip("'") if v else v


def parse_yaml_ish(lines):
    """Parse a flat-or-one-level YAML block into a dict (stdlib, no PyYAML).

    Handles `key: value`, a `key:` that opens a nested **map** (indented `k: v`)
    or a **list** (indented `- item`). One level of nesting — all the stories and
    the config need. Inline `#` comments and surrounding quotes are stripped.
    """
    data, cur_key, kind = {}, None, None
    for raw in lines:
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        indented = raw[:1] in (" ", "\t")
        body = raw.strip()
        if indented and cur_key is not None:
            if body.startswith("- "):
                if kind != "list":
                    data[cur_key], kind = [], "list"
                data[cur_key].append(_strip_scalar(body[2:]))
            elif ":" in body:
                if kind != "map":
                    data[cur_key], kind = {}, "map"
                k, v = body.split(":", 1)
                data[cur_key][k.strip()] = _strip_scalar(v)
            continue
        if ":" not in body:
            continue
        k, v = body.split(":", 1)
        k, v = k.strip(), _strip_scalar(v)
        if v == "":
            cur_key, kind, data[k] = k, None, None
        else:
            data[k], cur_key, kind = v, None, None
    return data


def parse_config(config_path):
    """Merge every ```yaml fence in the config into one dict."""
    text = config_path.read_text(encoding="utf-8")
    cfg = {}
    for block in re.findall(r"```yaml\n(.*?)\n```", text, re.DOTALL):
        for k, v in parse_yaml_ish(block.splitlines()).items():
            if isinstance(v, dict):
                cfg.setdefault(k, {}).update(v)
            else:
                cfg[k] = v
    return cfg


def split_frontmatter(text):
    """Return (frontmatter_dict, body_str) for a story file."""
    m = re.match(r"^---\n(.*?)\n---\n?(.*)$", text, re.DOTALL)
    if not m:
        return {}, text
    return parse_yaml_ish(m.group(1).splitlines()), m.group(2)


def split_sections(body):
    """Map `## Heading` → list of its lines (until the next `## `)."""
    sections, cur = {}, None
    for line in body.splitlines():
        h = re.match(r"^##\s+(.+?)\s*$", line)
        if h:
            cur = h.group(1).strip()
            sections[cur] = []
        elif cur is not None:
            sections[cur].append(line)
    return sections


def _count(lines, pattern):
    rx = re.compile(pattern)
    return sum(1 for ln in lines if rx.match(ln.strip()))


def extract_title(body, fallback):
    """First `# ` heading, with any `id — ` prefix stripped; else fallback."""
    m = re.search(r"^#\s+(.+?)\s*$", body, re.MULTILINE)
    if not m:
        return fallback
    title = m.group(1).strip()
    # Headings read "story-x-03 — Real title"; keep the part after the dash.
    parts = re.split(r"\s+[—–-]\s+", title, maxsplit=1)
    return parts[1].strip() if len(parts) == 2 else title


def load_story(path):
    """Parse one story file into the dict the renderer consumes."""
    fm, body = split_frontmatter(path.read_text(encoding="utf-8"))
    sec = split_sections(body)
    ac = sec.get("Acceptance criteria", [])
    tasks = sec.get("Tasks", [])
    done_tasks = _count(tasks, r"^- \[(completed|cancelled)\]")
    total_tasks = _count(tasks, r"^- \[(new|started|completed|cancelled|hold)\]")
    feedback = {
        "CR": _count(sec.get("Code Review Feedback", []), r"^- \[ \]"),
        "Test": _count(sec.get("Testing Feedback", []), r"^- \[ \]"),
        "Verify": _count(sec.get("Verification Feedback", []), r"^- \[ \]"),
    }
    deps = fm.get("dependencies") or []
    design = fm.get("design") or []
    if isinstance(deps, str):
        deps = [deps] if deps not in ("", "[]") else []
    if isinstance(design, str):
        design = [design] if design not in ("", "[]", "none-needed") else (
            ["none-needed"] if design == "none-needed" else [])
    return {
        "id": fm.get("id", path.stem),
        "title": extract_title(body, fm.get("id", path.stem)),
        "topic": fm.get("topic", "—"),
        "sprint": str(fm.get("sprint", "?")),
        "original_sprint": str(fm.get("original_sprint", "")),
        "sp": fm.get("story_points", "?"),
        "status": fm.get("status", "draft"),
        "owner": fm.get("owner", "—"),
        "analyzed": str(fm.get("analyzed", "")).lower() == "true",
        "exec_model": fm.get("exec_model", ""),
        "escalated": str(fm.get("escalated", "")).lower() == "true",
        "blocked_note": _first_note(sec.get("Notes", [])),
        "deps": deps,
        "design": design,
        "ac_open": _count(ac, r"^- \[ \]"),
        "ac_done": _count(ac, r"^- \[[xX]\]"),
        "tasks_done": done_tasks,
        "tasks_total": total_tasks,
        "feedback": feedback,
        "path": path,
    }


def _first_note(lines):
    for ln in lines:
        s = ln.strip()
        if s and not s.startswith("<!--"):
            return s.lstrip("> ").strip()
    return ""


def collect_stories(root, cfg):
    """Load all sprint stories + backlog stories; skip the archive."""
    stories_dir = root / cfg.get("stories_dir", "plan/stories/")
    archive = (root / cfg["archive_dir"]).resolve() if cfg.get("archive_dir") else None
    backlog = (root / cfg["backlog_dir"]).resolve() if cfg.get("backlog_dir") else None
    active, parked = [], []
    if not stories_dir.is_dir():
        return active, parked
    for path in sorted(stories_dir.rglob("story-*.md")):
        rp = path.resolve()
        if archive and archive in rp.parents:
            continue
        story = load_story(path)
        if (backlog and backlog in rp.parents) or story["status"] == "deferred":
            parked.append(story)
        else:
            active.append(story)
    return active, parked


# ───────────────────────────── HTML rendering ─────────────────────────────

CSS = """
:root{--bg:#f6f8fa;--card:#fff;--ink:#1f2328;--muted:#656d76;--line:#d0d7de;}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);
  font:14px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Helvetica,Arial,sans-serif;}
header{background:#24292f;color:#fff;padding:18px 28px;}
header h1{margin:0;font-size:18px;font-weight:600;}
header .meta{color:#b7bdc6;font-size:12.5px;margin-top:4px;}
.summary{display:flex;flex-wrap:wrap;gap:8px;margin-top:12px;}
.chip{display:inline-flex;align-items:center;gap:6px;background:#32383f;color:#fff;
  border-radius:999px;padding:3px 11px;font-size:12px;}
.chip b{font-weight:700}
.chip .dot{width:9px;height:9px;border-radius:50%}
main{padding:22px 28px 60px;max-width:1180px;margin:0 auto;}
.sprint{margin:30px 0 8px;font-size:16px;font-weight:700;
  border-bottom:2px solid var(--line);padding-bottom:6px;}
.sprint small{font-weight:500;color:var(--muted)}
.topic{margin:20px 0 10px;font-size:13px;font-weight:700;color:var(--muted);
  text-transform:uppercase;letter-spacing:.04em;}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(330px,1fr));gap:12px;}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;
  padding:13px 15px;box-shadow:0 1px 2px rgba(31,35,40,.05);}
.card.bad{border-left:4px solid #cf222e;}
.card.block{border-left:4px solid #bc4c00;}
.card.good{border-left:4px solid #1a7f37;}
.card .top{display:flex;justify-content:space-between;align-items:flex-start;gap:8px;}
.pill{color:#fff;border-radius:999px;padding:2px 9px;font-size:11px;font-weight:700;
  white-space:nowrap;text-transform:capitalize;}
.card h3{margin:8px 0 2px;font-size:14px;font-weight:600;line-height:1.35;}
.card .id{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:11.5px;
  color:var(--muted);}
.row{display:flex;flex-wrap:wrap;gap:6px 14px;margin-top:9px;font-size:12px;
  color:var(--muted);}
.row b{color:var(--ink);font-weight:600}
.bar{height:5px;border-radius:3px;background:#eaeef2;overflow:hidden;margin-top:3px;width:110px}
.bar i{display:block;height:100%;background:#2da44e}
.gaunt{display:flex;gap:5px;margin-top:11px;}
.stage{flex:1;text-align:center;border:1px solid var(--line);border-radius:6px;
  padding:4px 2px;font-size:10.5px;background:#fafbfc;}
.stage .lbl{display:block;color:var(--muted);font-size:9.5px;text-transform:uppercase;
  letter-spacing:.03em;}
.stage .mk{font-weight:700;font-size:13px;}
.stage.pass{background:#e9f7ec;border-color:#aedcb8;} .stage.pass .mk{color:#1a7f37;}
.stage.fail{background:#fdeceb;border-color:#f3b6b1;} .stage.fail .mk{color:#cf222e;}
.stage.todo .mk{color:#bbc1c8;}
.tags{margin-top:9px;display:flex;flex-wrap:wrap;gap:5px;}
.tag{font-size:10.5px;border:1px solid var(--line);border-radius:5px;padding:1px 7px;
  color:var(--muted);background:#fafbfc;}
.tag.warn{color:#bc4c00;border-color:#f0c9a8;background:#fff4ec;}
.note{margin-top:8px;font-size:11.5px;color:#bc4c00;background:#fff4ec;
  border-radius:6px;padding:6px 9px;}
.empty{color:var(--muted);padding:40px;text-align:center;}
.legend{margin-top:34px;font-size:11.5px;color:var(--muted);border-top:1px solid var(--line);
  padding-top:14px;}
table.bk{border-collapse:collapse;width:100%;font-size:12.5px;margin-top:6px;}
table.bk th,table.bk td{border:1px solid var(--line);padding:6px 9px;text-align:left;}
table.bk th{background:#f0f3f6;font-weight:600;}
"""


def _pill(status):
    c = STATUS_COLOR.get(status, "#6e7781")
    return f'<span class="pill" style="background:{c}">{html.escape(status)}</span>'


def _gauntlet_html(story):
    marks = GAUNTLET.get(story["status"], ("-", "-", "-", "-"))
    fb = story["feedback"]
    counts = {"CR": fb["CR"], "Gen": 0, "Test": fb["Test"], "Verify": fb["Verify"]}
    cells = []
    for col, mk in zip(GAUNTLET_COLS, marks):
        if mk == "y":
            cls, txt = "pass", "✓"
        elif mk == "f":
            n = counts.get(col, 0)
            cls, txt = "fail", (f"✗{n}" if n else "✗")
        else:
            cls, txt = "todo", "·"
        cells.append(f'<div class="stage {cls}"><span class="lbl">{col}</span>'
                     f'<span class="mk">{txt}</span></div>')
    return '<div class="gaunt">' + "".join(cells) + "</div>"


def _card(story):
    s = story["status"]
    klass = "card"
    if s in ("code-review-failed", "testing-failed", "verification-failed"):
        klass += " bad"
    elif s == "blocked":
        klass += " block"
    elif s == "verified":
        klass += " good"

    ac_total = story["ac_open"] + story["ac_done"]
    ac = f'{story["ac_done"]}/{ac_total}' if ac_total else "—"
    tt = story["tasks_total"]
    tasks_txt = f'{story["tasks_done"]}/{tt}' if tt else "—"
    task_pct = int(100 * story["tasks_done"] / tt) if tt else 0

    design = story["design"]
    if not design:
        design_txt = "—"
    elif design == ["none-needed"]:
        design_txt = "none-needed"
    else:
        design_txt = ", ".join(Path(d).name for d in design)
    deps_txt = ", ".join(story["deps"]) if story["deps"] else "—"

    tags = []
    if story["exec_model"]:
        tags.append(f'<span class="tag">model: {html.escape(story["exec_model"])}</span>')
    if story["escalated"]:
        tags.append('<span class="tag warn">escalated ↑</span>')
    if not story["analyzed"] and s in ("draft", "ready"):
        tags.append('<span class="tag warn">not analyzed</span>')
    tags_html = f'<div class="tags">{"".join(tags)}</div>' if tags else ""

    note = ""
    if s == "blocked" and story["blocked_note"]:
        note = f'<div class="note">⛔ {html.escape(story["blocked_note"])}</div>'

    return f"""
    <div class="{klass}">
      <div class="top"><span class="id">{html.escape(story["id"])}</span>{_pill(s)}</div>
      <h3>{html.escape(story["title"])}</h3>
      <div class="row">
        <span><b>{html.escape(str(story["sp"]))}</b> SP</span>
        <span>owner <b>{html.escape(story["owner"])}</b></span>
        <span>ACs <b>{ac}</b></span>
        <span>tasks <b>{tasks_txt}</b>
          <span class="bar"><i style="width:{task_pct}%"></i></span></span>
      </div>
      <div class="row">
        <span>design <b>{html.escape(design_txt)}</b></span>
        <span>deps <b>{html.escape(deps_txt)}</b></span>
      </div>
      {_gauntlet_html(story)}
      {tags_html}
      {note}
    </div>"""


def _bucket(stories):
    """sprint → topic → [stories], each level sorted naturally."""
    out = {}
    for st in stories:
        out.setdefault(st["sprint"], {}).setdefault(st["topic"], []).append(st)

    def seq(s):
        m = re.search(r"-(\d+)", s["id"])
        return int(m.group(1)) if m else 0

    for topics in out.values():
        for lst in topics.values():
            lst.sort(key=seq)
    return out


def _sprint_sort(key):
    return (0, int(key)) if key.isdigit() else (1, key)


def render(root, cfg, active, parked, only_sprint=None):
    labels = cfg.get("sprint_labels", {}) or {}
    project = root.name
    multi_op = (root / OPERATORS_REL).is_dir() and any(
        (root / OPERATORS_REL).glob("*.md"))

    if only_sprint:
        active = [s for s in active if s["sprint"] == str(only_sprint)]

    # Summary chips by status (lifecycle order).
    counts = {}
    for s in active + parked:
        counts[s["status"]] = counts.get(s["status"], 0) + 1
    total_sp = sum(int(s["sp"]) for s in active if str(s["sp"]).isdigit())
    chips = []
    for st in STATUS_ORDER:
        if counts.get(st):
            c = STATUS_COLOR.get(st, "#6e7781")
            chips.append(f'<span class="chip"><span class="dot" style="background:{c}">'
                         f'</span>{html.escape(st)} <b>{counts[st]}</b></span>')
    summary = (f'<span class="chip">{len(active)} stories <b>·</b> {total_sp} SP</span>'
               + "".join(chips))

    body = []
    buckets = _bucket(active)
    if not buckets:
        body.append('<div class="empty">No stories yet. Run <code>/manage-stories</code> '
                    'to create the story tree, then <code>/analyze-sprint N</code>.</div>')
    for sprint in sorted(buckets, key=_sprint_sort):
        label = labels.get(sprint, "")
        topics = buckets[sprint]
        scount = sum(len(v) for v in topics.values())
        ssp = sum(int(s["sp"]) for v in topics.values() for s in v if str(s["sp"]).isdigit())
        head = f"Sprint {sprint}" + (f" — {html.escape(label)}" if label else "")
        body.append(f'<div class="sprint">{head} '
                    f'<small>({scount} stories · {ssp} SP)</small></div>')
        for topic in sorted(topics):
            body.append(f'<div class="topic">{html.escape(topic)}</div><div class="grid">')
            body.extend(_card(s) for s in topics[topic])
            body.append("</div>")

    if parked and not only_sprint:
        body.append('<div class="sprint">Backlog '
                    '<small>(deferred during analysis)</small></div>')
        rows = "".join(
            f"<tr><td>{html.escape(s['id'])}</td><td>{html.escape(s['title'])}</td>"
            f"<td>{html.escape(str(s['sp']))}</td>"
            f"<td>{html.escape(s['original_sprint'] or '—')}</td>"
            f"<td>{html.escape(s['owner'])}</td>"
            f"<td>{html.escape(s['blocked_note'] or '—')}</td></tr>"
            for s in parked)
        body.append('<table class="bk"><tr><th>ID</th><th>Title</th><th>SP</th>'
                    '<th>Orig. sprint</th><th>Owner</th><th>Reason</th></tr>'
                    + rows + "</table>")

    op_note = (' · <b>multi-operator</b> mode' if multi_op else "")
    legend = (
        '<div class="legend"><b>Gauntlet:</b> CR (code review) · Gen (adversarial tests '
        'authored) · Test (tests run) · Verify (design parity). ✓ passed · ✗N = N open '
        'blocking items · · not reached. Each is a pure function of the story\'s single '
        '<code>status</code>. Read-only view — refresh to re-read from disk.</div>')

    return f"""<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(project)} — sprint board</title><style>{CSS}</style></head><body>
<header>
  <h1>{html.escape(project)} — sprint board</h1>
  <div class="meta">{html.escape(str(root))}{op_note}</div>
  <div class="summary">{summary}</div>
</header>
<main>{"".join(body)}{legend}</main>
</body></html>"""


# ───────────────────────────── serve / build ─────────────────────────────

def build_html(root, cfg, only_sprint=None):
    active, parked = collect_stories(root, cfg)
    return render(root, cfg, active, parked, only_sprint)


def free_port(preferred):
    """Return `preferred` if bindable, else the first free port above it."""
    for port in range(preferred, preferred + 60):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sk:
            sk.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sk.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    raise SystemExit(f"error: no free port in {preferred}–{preferred + 59}")


def serve(root, cfg, port, only_sprint, open_browser):
    port = free_port(port)
    url = f"http://127.0.0.1:{port}/"

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            try:
                page = build_html(root, cfg, only_sprint).encode("utf-8")
            except Exception as exc:  # never crash the server on a bad story
                page = (f"<pre>view-sprint error: {html.escape(str(exc))}</pre>"
                        ).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(page)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(page)

        def log_message(self, *_):  # quiet
            pass

    httpd = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"sprint board for {root.name}: {url}  (Ctrl-C to stop)", flush=True)
    if open_browser:
        webbrowser.open(url)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped.")
    finally:
        httpd.server_close()


# ───────────────────────────── dispatch ─────────────────────────────

def main():
    ap = argparse.ArgumentParser(
        prog="view-sprint.py",
        description="Live, read-only sprint board from the story tree.")
    ap.add_argument("command", nargs="?", default="serve", choices=["serve", "build"],
                    help="serve (default) a live board, or build a static HTML file")
    ap.add_argument("--project", type=Path, default=None,
                    help="project root (default: auto-detect from CWD)")
    ap.add_argument("--sprint", default=None, help="show only this sprint (number/label)")
    ap.add_argument("--port", type=int, default=8800, help="preferred port for serve")
    ap.add_argument("--no-browser", action="store_true", help="don't auto-open a browser")
    ap.add_argument("--out", type=Path, default=None,
                    help="output file for build (default: {working_root}/sprint-board.html)")
    args = ap.parse_args()

    start = (args.project or Path.cwd()).resolve()
    root = find_project_root(start)
    if root is None:
        print(f"error: no {CONFIG_REL} found at or above {start}", file=sys.stderr)
        return 2
    cfg = parse_config(root / CONFIG_REL)

    if args.command == "build":
        out = args.out or (root / cfg.get("working_root", "plan/") / "sprint-board.html")
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(build_html(root, cfg, args.sprint), encoding="utf-8")
        print(f"wrote {out}")
        return 0

    serve(root, cfg, args.port, args.sprint, open_browser=not args.no_browser)
    return 0


if __name__ == "__main__":
    sys.exit(main())

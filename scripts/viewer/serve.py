#!/usr/bin/env python3
"""Local static server for the agile-pipeline spec viewer.

Config-driven and project-agnostic. Resolves the project root by walking up for
`.claude/pipeline.config.md`, reads `stories_dir` / `design_dir` from it, and serves
a tiny prefix-routing static server so the viewer can fetch the story tree wherever
it lives — the viewer files themselves stay in this folder, no copy into the project
required.

URL routing:
    /viewer/...   → this directory (index.html, viewer.jsx, viewer.css, tokens.css)
    /stories/...  → the project's `stories_dir`   (incl. directory listings)
    /design/...   → the project's `design_dir`
    /             → redirect to /viewer/

Usage:
    ./serve.py                      # foreground (Ctrl+C to stop)
    ./serve.py start                # background, returns immediately
    ./serve.py stop                 # kills the backgrounded server
    ./serve.py status               # shows whether it's running
    ./serve.py --project DIR ...    # target a specific project (default: auto-detect from CWD)
"""

from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import os
import re
import socket
import subprocess
import sys
import time
import urllib.parse
import webbrowser

PORT_START = 8000
PORT_END = 8050
HOST = "127.0.0.1"
CONFIG_REL = Path(".claude/pipeline.config.md")
VIEWER_DIR = Path(__file__).resolve().parent  # holds index.html, viewer.jsx, *.css


# ───────────────────── config resolution ─────────────────────

def find_project_root(start):
    """Walk up from `start` to the first dir containing the pipeline config."""
    for d in [start, *start.parents]:
        if (d / CONFIG_REL).is_file():
            return d
    return None


def parse_paths(config_path):
    """Extract `key: value` pairs from the config's ## Paths yaml block (stdlib-only)."""
    text = config_path.read_text(encoding="utf-8")
    block = re.search(r"^##\s+Paths\s*$.*?```yaml\n(.*?)\n```",
                      text, re.MULTILINE | re.DOTALL)
    out = {}
    if block:
        for line in block.group(1).splitlines():
            line = line.split("#", 1)[0].strip()
            if not line or ":" not in line:
                continue
            k, v = line.split(":", 1)
            out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def resolve_paths(root):
    """Return (stories_dir, design_dir) as absolute paths for the project at `root`."""
    cfg = parse_paths(root / CONFIG_REL)
    stories = root / cfg.get("stories_dir", "plan/stories/")
    design = root / cfg.get("design_dir", cfg.get("working_root", "plan/"))
    return stories.resolve(), design.resolve()


# Resolved per-run and read by the handler (set in main / cmd_child).
STORIES_DIR = None
DESIGN_DIR = None


# ───────────────────── routing handler ─────────────────────

class ViewerHandler(SimpleHTTPRequestHandler):
    """Serve viewer assets, and route /stories and /design to the project tree.

    Directory listings (Python's autoindex) are preserved for /stories/<topic>/ —
    viewer.jsx scrapes them to map story ids to filenames.
    """

    def translate_path(self, path):
        path = urllib.parse.unquote(path.split("?", 1)[0].split("#", 1)[0])
        parts = [p for p in path.split("/") if p not in ("", ".", "..")]
        if parts and parts[0] == "stories":
            base, rel = STORIES_DIR, parts[1:]
        elif parts and parts[0] == "design":
            base, rel = DESIGN_DIR, parts[1:]
        elif parts and parts[0] == "viewer":
            base, rel = VIEWER_DIR, parts[1:]
        else:
            base, rel = VIEWER_DIR, parts
        return str(Path(base).joinpath(*rel))

    def do_GET(self):
        # Send the app's entry without requiring the user to type /viewer/.
        if self.path in ("/", ""):
            self.send_response(302)
            self.send_header("Location", "/viewer/")
            self.end_headers()
            return
        return super().do_GET()

    def end_headers(self):
        # Localhost spec browser: always serve fresh (no stale INDEX.md / viewer.jsx).
        self.send_header("Cache-Control", "no-store, must-revalidate")
        self.send_header("Expires", "0")
        super().end_headers()

    def log_message(self, *args):
        pass  # quiet


# ───────────────────── port + serve primitives ─────────────────────

def first_free_port(start, end):
    for port in range(start, end + 1):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            s.bind((HOST, port))
        except OSError:
            s.close()
            continue
        s.close()
        return port
    return None


def serve_blocking(root, port, open_browser=True):
    url = f"http://localhost:{port}/viewer/"
    print(f"→ Project root: {root}", flush=True)
    print(f"→ Stories:      {STORIES_DIR}", flush=True)
    print(f"→ Serving at    {url}", flush=True)
    if port != PORT_START:
        print(f"  (port {PORT_START} was busy, fell through to {port})", flush=True)
    print("→ Ctrl+C to stop", flush=True)
    if open_browser:
        try:
            webbrowser.open(url)
        except Exception:
            pass
    server = ThreadingHTTPServer((HOST, port), ViewerHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n→ Stopped.", flush=True)
    finally:
        server.server_close()


# ───────────────────── per-project state files ─────────────────────

def state_files(root):
    slug = re.sub(r"[^A-Za-z0-9_.-]", "-", root.name) or "project"
    base = Path("/tmp") / f"agile-viewer-{slug}"
    return (Path(f"{base}.pid"), Path(f"{base}.port"), Path(f"{base}.log"))


def read_pid(pid_file):
    if not pid_file.exists():
        return None
    try:
        return int(pid_file.read_text().strip())
    except (ValueError, OSError):
        return None


def pid_alive(pid):
    if pid is None:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def clear_state(pid_file, port_file):
    for p in (pid_file, port_file):
        try:
            p.unlink()
        except FileNotFoundError:
            pass


# ───────────────────── subcommands ─────────────────────

def cmd_foreground(root):
    port = first_free_port(PORT_START, PORT_END)
    if port is None:
        print(f"No free port in {PORT_START}-{PORT_END}.", file=sys.stderr)
        return 1
    serve_blocking(root, port, open_browser=True)
    return 0


def cmd_start(root):
    pid_file, port_file, log_file = state_files(root)
    existing = read_pid(pid_file)
    if pid_alive(existing):
        port = port_file.read_text().strip() if port_file.exists() else "?"
        print(f"Already running. pid={existing} port={port}", file=sys.stderr)
        print(f"  URL: http://localhost:{port}/viewer/", file=sys.stderr)
        print("  Use `./serve.py stop` to stop it.", file=sys.stderr)
        return 1
    if existing is not None:
        clear_state(pid_file, port_file)

    port = first_free_port(PORT_START, PORT_END)
    if port is None:
        print(f"No free port in {PORT_START}-{PORT_END}.", file=sys.stderr)
        return 1

    log_fd = open(log_file, "a", buffering=1)
    log_fd.write(f"\n--- started at {time.strftime('%Y-%m-%d %H:%M:%S')} "
                 f"on port {port} for {root} ---\n")
    proc = subprocess.Popen(
        [sys.executable, str(Path(__file__).resolve()),
         "--project", str(root), "--child", str(port)],
        stdout=log_fd, stderr=log_fd, stdin=subprocess.DEVNULL,
        start_new_session=True, close_fds=True,
    )
    pid_file.write_text(str(proc.pid))
    port_file.write_text(str(port))

    time.sleep(0.3)
    if proc.poll() is not None:
        clear_state(pid_file, port_file)
        print(f"Child exited with code {proc.returncode}. Recent log:", file=sys.stderr)
        try:
            print(log_file.read_text()[-500:], file=sys.stderr)
        except OSError:
            pass
        return 1

    url = f"http://localhost:{port}/viewer/"
    print(f"→ Started in background.  pid={proc.pid}  port={port}")
    print(f"→ {url}")
    if port != PORT_START:
        print(f"  (port {PORT_START} was busy, fell through to {port})")
    print(f"→ Logs: {log_file}")
    print("→ Stop: ./serve.py stop")
    try:
        webbrowser.open(url)
    except Exception:
        pass
    return 0


def cmd_stop(root):
    pid_file, port_file, _ = state_files(root)
    pid = read_pid(pid_file)
    if pid is None:
        print("Not running (no pid file).")
        return 0
    if not pid_alive(pid):
        print(f"Stale pid file (pid={pid} not alive). Cleaning up.")
        clear_state(pid_file, port_file)
        return 0
    try:
        os.kill(pid, 15)
    except ProcessLookupError:
        clear_state(pid_file, port_file)
        print("Process gone before signal arrived. Cleaned up.")
        return 0
    for _ in range(20):
        if not pid_alive(pid):
            break
        time.sleep(0.1)
    if pid_alive(pid):
        print(f"pid={pid} didn't exit on SIGTERM, sending SIGKILL.")
        try:
            os.kill(pid, 9)
        except ProcessLookupError:
            pass
        time.sleep(0.2)
    clear_state(pid_file, port_file)
    print(f"→ Stopped. pid={pid}")
    return 0


def cmd_status(root):
    pid_file, port_file, log_file = state_files(root)
    pid = read_pid(pid_file)
    if not pid_alive(pid):
        if pid is not None:
            print(f"Not running. (Stale pid={pid} found — run `stop` to clean up.)")
        else:
            print("Not running.")
        return 0
    port = port_file.read_text().strip() if port_file.exists() else "?"
    print(f"Running. pid={pid}  port={port}")
    print(f"  URL:  http://localhost:{port}/viewer/")
    print(f"  Logs: {log_file}")
    return 0


def cmd_child(root, port_arg):
    """Hidden: serve on the given port without opening a browser (used by `start`)."""
    try:
        port = int(port_arg)
    except (TypeError, ValueError):
        print(f"--child: invalid port {port_arg!r}", file=sys.stderr)
        return 2
    serve_blocking(root, port, open_browser=False)
    return 0


# ───────────────────── dispatch ─────────────────────

def main(argv):
    args = argv[1:]

    # Pull out `--project DIR` (anywhere) before reading the subcommand.
    project = None
    rest = []
    i = 0
    while i < len(args):
        if args[i] == "--project":
            project = args[i + 1] if i + 1 < len(args) else None
            i += 2
            continue
        rest.append(args[i])
        i += 1

    if rest and rest[0] in ("-h", "--help", "help"):
        print(__doc__)
        return 0

    start = Path(project).resolve() if project else Path.cwd().resolve()
    root = find_project_root(start)
    if root is None:
        print(f"error: no {CONFIG_REL} found at or above {start}\n"
              f"       run this from inside a pipeline project, or pass --project DIR.",
              file=sys.stderr)
        return 2

    global STORIES_DIR, DESIGN_DIR
    STORIES_DIR, DESIGN_DIR = resolve_paths(root)

    sub = rest[0] if rest else None
    if sub is None:
        return cmd_foreground(root)
    if sub == "start":
        return cmd_start(root)
    if sub == "stop":
        return cmd_stop(root)
    if sub in ("status", "ps"):
        return cmd_status(root)
    if sub == "--child":
        return cmd_child(root, rest[1] if len(rest) > 1 else None)
    print(f"Unknown subcommand: {sub}", file=sys.stderr)
    print("Run with --help to see usage.", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))

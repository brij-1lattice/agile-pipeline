#!/usr/bin/env python3
"""Scaffold a project's planning tree, and set up per-operator sprint worktrees.

Two subcommands (config-driven, project-agnostic, stdlib-only, idempotent):

  scaffold-plan.py [flags]            # default: scaffold + verify the planning tree
    Reads the canonical paths/documents from `.claude/pipeline.config.md`, then:
      1. creates any missing required directories under the planning root,
      2. drops a placeholder for a missing stories INDEX.md,
      3. warns (loudly) about missing required documents,
      4. copies stashed/misplaced source files into place from an optional
         `.claude/pipeline.seeds.md` manifest (never overwriting unless --force).

  scaffold-plan.py operator <name> [--sprint N] [--list]
    Multi-operator mode (opt-in; needs `.claude/operators/<name>.md`). Reads the
    operator profile, and for `--sprint N` creates the git worktree + branch
    (`sprint/<name>-N`) idempotently and prints the operator's ports/env. With no
    --sprint it just prints the profile; `--list` lists all operators.
    See pipeline/reference/operator-profile.md for the contract.

Usage:
    ./scaffold-plan.py                  # apply against the auto-detected project
    ./scaffold-plan.py --dry-run        # preview every action, change nothing
    ./scaffold-plan.py --verbose        # also log items already OK
    ./scaffold-plan.py --force          # let seed copies overwrite existing dests
    ./scaffold-plan.py --project DIR    # target a specific project root
    ./scaffold-plan.py operator brij --sprint 2     # create brij's sprint-2 worktree
    ./scaffold-plan.py operator --list              # list operators + their sprints

Scaffold exit code is 0 when the required structure is satisfied, non-zero when a
required document is still missing (so CI can gate on it). --dry-run always 0.
"""

from pathlib import Path
import argparse
import re
import shutil
import subprocess
import sys

CONFIG_REL = Path(".claude/pipeline.config.md")
SEEDS_REL = Path(".claude/pipeline.seeds.md")
OPERATORS_REL = Path(".claude/operators")

# Path keys whose values are directories to scaffold. archive/backlog are
# normally empty, so they get a .gitkeep to survive git.
DIR_KEYS = ["working_root", "design_dir", "stories_dir", "archive_dir", "backlog_dir"]
GITKEEP_KEYS = {"archive_dir", "backlog_dir"}

# Document keys that must exist but must never be fabricated (curated by hand).
DOC_KEYS = ["blueprint", "tech_spec", "design_doc"]


# ───────────────────────── tiny reporter ─────────────────────────

class Report:
    """Collects actions for the run summary and tracks failure state."""

    def __init__(self, dry_run, verbose):
        self.dry_run = dry_run
        self.verbose = verbose
        self.created = 0
        self.copied = 0
        self.skipped = 0
        self.warnings = 0
        self.incomplete = False  # set when a required doc is missing

    def _tag(self, verb):
        return f"[dry-run] {verb}" if self.dry_run else verb

    def act(self, verb, detail, kind):
        print(f"  {self._tag(verb):<22} {detail}")
        setattr(self, kind, getattr(self, kind) + 1)

    def ok(self, detail):
        if self.verbose:
            print(f"  {'ok':<22} {detail}")

    def warn(self, detail):
        print(f"  {'WARNING':<22} {detail}", file=sys.stderr)
        self.warnings += 1

    def summary(self):
        print(
            f"\n{self._tag('summary')}: "
            f"{self.created} created, {self.copied} copied, "
            f"{self.skipped} skipped, {self.warnings} warning(s)"
        )


# ─────────────────────── config + manifest parsing ───────────────────────

def find_project_root(start):
    """Walk up from `start` to the first dir containing the pipeline config."""
    for d in [start, *start.parents]:
        if (d / CONFIG_REL).is_file():
            return d
    return None


def parse_config(config_path):
    """Extract flat key: value pairs from the ## Paths and ## Documents blocks.

    Hand-rolled so the script stays stdlib-only (no PyYAML). Each block is a
    ```yaml fence holding simple `key: value` lines; inline `#` comments and
    surrounding quotes are stripped.
    """
    text = config_path.read_text(encoding="utf-8")
    out = {}
    for heading in ("Paths", "Documents"):
        block = re.search(
            rf"^##\s+{heading}\s*$.*?```yaml\n(.*?)\n```",
            text,
            re.MULTILINE | re.DOTALL,
        )
        if not block:
            raise ValueError(f"config is missing a '## {heading}' yaml block")
        for line in block.group(1).splitlines():
            line = line.split("#", 1)[0].strip()
            if not line or ":" not in line:
                continue
            key, value = line.split(":", 1)
            out[key.strip()] = value.strip().strip('"').strip("'")
    return out


def parse_seeds(seeds_path):
    """Parse the seed manifest's markdown table into (source, dest, overwrite) rows."""
    rows = []
    for line in seeds_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line.startswith("|"):
            continue
        cells = [c.strip().strip("`") for c in line.strip("|").split("|")]
        if len(cells) < 3:
            continue
        src, dest, overwrite = cells[0], cells[1], cells[2].lower()
        # Skip the header row and its `---` separator.
        if src in ("source", "") or set(src) <= {"-", ":"}:
            continue
        rows.append((src, dest, overwrite in ("yes", "true", "force")))
    return rows


# ───────────────────────── scaffold steps ─────────────────────────

def ensure_dir(path, gitkeep, rep):
    """Create `path` (and optionally a .gitkeep inside it) if missing."""
    if path.is_dir():
        rep.ok(f"dir {path}")
    else:
        rep.act("create dir", str(path), "created")
        if not rep.dry_run:
            path.mkdir(parents=True, exist_ok=True)
    # A .gitkeep only matters in an otherwise-empty dir; skip it once the dir
    # has real content (e.g. an archive that already holds a superseded story).
    # `not path.exists()` covers dry-run, where the dir hasn't been made yet.
    if gitkeep and (not path.exists() or not any(path.iterdir())):
        keep = path / ".gitkeep"
        if not keep.exists():
            rep.act("create", str(keep), "created")
            if not rep.dry_run:
                keep.touch()


def ensure_index(path, rep):
    """Write a placeholder INDEX.md if missing (manage-stories owns the real one)."""
    if path.exists():
        rep.ok(f"index {path}")
        return
    rep.act("create index", str(path), "created")
    if not rep.dry_run:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "# Stories — INDEX\n\n"
            "_Placeholder created by scaffold-plan.py._\n"
            "Run `/manage-stories index` to regenerate this board.\n",
            encoding="utf-8",
        )


def check_doc(path, rep):
    """Report whether a required document exists. Never fabricates it."""
    if path.is_file():
        rep.ok(f"doc {path}")
        return True
    rep.warn(f"required document missing: {path}")
    rep.incomplete = True
    return False


def apply_seed(src, dest, overwrite, force, root, rep):
    """Copy src -> dest per manifest rules; never clobber unless allowed."""
    src_abs, dest_abs = root / src, root / dest
    if not src_abs.exists():
        rep.warn(f"seed source missing: {src}")
        return
    if dest_abs.exists() and not (overwrite or force):
        rep.act("skip (dest exists)", str(dest), "skipped")
        return
    rep.act("copy", f"{src} -> {dest}", "copied")
    if not rep.dry_run:
        dest_abs.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src_abs, dest_abs)


# ───────────────────── operator profiles (multi-operator) ─────────────────────

def parse_operator_profile(path):
    """Parse an operator profile into {owner, branch, worktree, ports{}, sprints{N:(goal,status)}}.

    Frontmatter is a single `---` block with one level of nesting (the `ports:`
    map); the `## Sprints` markdown table supplies per-sprint goals. Stdlib-only.
    """
    text = path.read_text(encoding="utf-8")
    prof = {"ports": {}, "sprints": {}}

    fm = re.search(r"^---\n(.*?)\n---", text, re.DOTALL | re.MULTILINE)
    if not fm:
        raise ValueError(f"{path} has no '---' frontmatter block")
    block = None
    for raw in fm.group(1).splitlines():
        if not raw.split("#", 1)[0].strip():
            continue
        indented = raw[:1].isspace()
        key, _, val = raw.split("#", 1)[0].strip().partition(":")
        key, val = key.strip(), val.strip().strip('"').strip("'")
        if indented and block:
            prof[block][key] = val
        elif val == "":          # opens a nested block (e.g. `ports:`)
            prof.setdefault(key, {})
            block = key
        else:
            prof[key] = val
            block = None

    for line in text.splitlines():
        s = line.strip()
        if not s.startswith("|"):
            continue
        cells = [c.strip() for c in s.strip("|").split("|")]
        if len(cells) >= 3 and cells[0].isdigit():
            prof["sprints"][cells[0]] = (cells[1], cells[2])
    return prof


def git(root, *args):
    """Run `git -C root <args>`; return (returncode, stdout, stderr)."""
    proc = subprocess.run(["git", "-C", str(root), *args],
                          capture_output=True, text=True)
    return proc.returncode, proc.stdout, proc.stderr


def git_worktrees(root):
    """Map of resolved worktree path -> branch name for the repo at `root`."""
    rc, out, _ = git(root, "worktree", "list", "--porcelain")
    res, cur = {}, None
    if rc == 0:
        for line in out.splitlines():
            if line.startswith("worktree "):
                cur = str(Path(line[9:].strip()).resolve())
                res[cur] = None
            elif line.startswith("branch ") and cur:
                res[cur] = line[7:].strip().replace("refs/heads/", "")
    return res


def git_branch_exists(root, branch):
    rc, _, _ = git(root, "show-ref", "--verify", "--quiet", f"refs/heads/{branch}")
    return rc == 0


def _print_sprints(prof, owner):
    for n in sorted(prof["sprints"], key=int):
        goal, status = prof["sprints"][n]
        suffix = f"  [{status}]" if status else ""
        print(f"    {owner}/{n}  {goal}{suffix}")


def cmd_operator(argv):
    ap = argparse.ArgumentParser(
        prog="scaffold-plan.py operator",
        description="Set up a per-operator sprint worktree (multi-operator mode).",
    )
    ap.add_argument("name", nargs="?", help="operator name (matches .claude/operators/<name>.md)")
    ap.add_argument("--sprint", type=int, default=None, help="sprint number to create a worktree for")
    ap.add_argument("--list", action="store_true", help="list all operators and their sprints")
    ap.add_argument("--project", type=Path, default=None, help="project root (default: auto-detect)")
    ap.add_argument("--dry-run", action="store_true", help="print actions without changing anything")
    args = ap.parse_args(argv)

    start = (args.project or Path.cwd()).resolve()
    root = find_project_root(start)
    if root is None:
        print(f"error: no {CONFIG_REL} found at or above {start}", file=sys.stderr)
        return 2

    ops_dir = root / OPERATORS_REL
    if not ops_dir.is_dir():
        print(f"error: no {OPERATORS_REL}/ in {root} — this project is single-operator.\n"
              f"       copy operator.template.md to {OPERATORS_REL}/<name>.md to enable "
              f"multi-operator mode.", file=sys.stderr)
        return 2

    # List mode (explicit --list, or no name given).
    if args.list or not args.name:
        profiles = sorted(ops_dir.glob("*.md"))
        if not profiles:
            print(f"no operator profiles in {OPERATORS_REL}/")
            return 0
        for p in profiles:
            prof = parse_operator_profile(p)
            owner = prof.get("owner", p.stem)
            ports = prof.get("ports", {})
            print(f"{owner}  branch={prof.get('branch', '?')}  "
                  f"ports(web={ports.get('web', '?')}, supabase={ports.get('supabase', '?')})")
            _print_sprints(prof, owner)
        return 0

    prof_path = ops_dir / f"{args.name}.md"
    if not prof_path.is_file():
        print(f"error: no profile {prof_path}\n"
              f"       copy operator.template.md to {OPERATORS_REL}/{args.name}.md and fill it in.",
              file=sys.stderr)
        return 2

    prof = parse_operator_profile(prof_path)
    owner = prof.get("owner", args.name)
    ports = prof.get("ports", {})
    web, supa = ports.get("web", "?"), ports.get("supabase", "?")

    # No --sprint: just print the profile summary.
    if args.sprint is None:
        print(f"operator: {owner}")
        print(f"  branch pattern: {prof.get('branch', '?')}")
        print(f"  worktree:       {prof.get('worktree', '?')}")
        print(f"  ports:          web {web}  supabase {supa}")
        print("  sprints:")
        _print_sprints(prof, owner)
        print("\n(pass --sprint N to create that sprint's worktree + branch)")
        return 0

    n = str(args.sprint)
    branch = (prof.get("branch") or f"sprint/{owner}-<n>").replace("<n>", n)
    worktree_rel = (prof.get("worktree") or f"../{root.name}-{owner}").replace("<repo>", root.name)
    worktree_abs = (root / worktree_rel).resolve()
    goal = prof["sprints"].get(n, ("(no goal in profile)", ""))[0]
    tag = "[dry-run] " if args.dry_run else ""

    print(f"operator {owner} — sprint {owner}/{n}: {goal}")
    existing = git_worktrees(root)
    if str(worktree_abs) in existing:
        print(f"  worktree exists: {worktree_abs}  (branch {existing[str(worktree_abs)]})")
    else:
        new_branch = not git_branch_exists(root, branch)
        add = ["worktree", "add", str(worktree_abs)] + (["-b", branch] if new_branch else [branch])
        print(f"  {tag}create worktree: {worktree_abs}  (branch {branch}{' [new]' if new_branch else ''})")
        if not args.dry_run:
            rc, _, err = git(root, *add)
            if rc != 0:
                print(f"  git error: {err.strip() or 'see above'}", file=sys.stderr)
                return 1

    print(f"\n  branch:   {branch}")
    print(f"  worktree: {worktree_abs}")
    print(f"  ports:    web {web}  supabase {supa}")
    print(f"\n  next: cd {worktree_abs}  &&  run your sprint skills addressed `{owner}/{n}`")
    return 0


# ───────────────────────────── scaffold command ─────────────────────────────

def cmd_scaffold(argv):
    ap = argparse.ArgumentParser(
        prog="scaffold-plan.py",
        description="Scaffold + verify a planning tree from pipeline.config.md.",
    )
    ap.add_argument("--project", type=Path, default=None,
                    help="project root (default: auto-detect from CWD)")
    ap.add_argument("--dry-run", action="store_true",
                    help="print actions without changing anything")
    ap.add_argument("--force", action="store_true",
                    help="allow seed copies to overwrite existing destinations")
    ap.add_argument("--verbose", action="store_true",
                    help="also log items that are already OK")
    args = ap.parse_args(argv)

    start = (args.project or Path.cwd()).resolve()
    root = find_project_root(start)
    if root is None:
        print(f"error: no {CONFIG_REL} found at or above {start}", file=sys.stderr)
        return 2

    try:
        cfg = parse_config(root / CONFIG_REL)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    rep = Report(args.dry_run, args.verbose)
    print(f"project: {root}")

    print("\ndirectories:")
    for key in DIR_KEYS:
        if key in cfg:
            ensure_dir(root / cfg[key], key in GITKEEP_KEYS, rep)

    print("\nindex:")
    if "index_path" in cfg:
        ensure_index(root / cfg["index_path"], rep)

    print("\ndocuments:")
    for key in DOC_KEYS:
        if key in cfg:
            check_doc(root / cfg[key], rep)

    print("\nseed copies:")
    seeds_path = root / SEEDS_REL
    if seeds_path.is_file():
        for src, dest, overwrite in parse_seeds(seeds_path):
            apply_seed(src, dest, overwrite, args.force, root, rep)
    else:
        rep.ok(f"no seed manifest ({SEEDS_REL}) — skipping copies")

    rep.summary()

    if rep.incomplete and not args.dry_run:
        print("incomplete: one or more required documents are missing.", file=sys.stderr)
        return 1
    return 0


# ───────────────────────────── dispatch ─────────────────────────────

def main():
    argv = sys.argv[1:]
    if argv and argv[0] == "operator":
        return cmd_operator(argv[1:])
    return cmd_scaffold(argv)


if __name__ == "__main__":
    sys.exit(main())

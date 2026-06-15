// viewer.jsx — 3-pane spec browser for stories/
// Read-only. Fetches stories/INDEX.md + lazy-fetches story .md files.

const { useReducer, useEffect, useMemo, useRef, useCallback, useState } = React;

const STORIES_BASE = "../stories";
const DESIGN_BASE = "../design";

// Optional, per-project: map a design source file (basename) to a deep-link route
// in the rendered prototype, e.g. { "screens-blog.jsx": "/blog" }. Left empty by
// default — unmapped files just open the raw source. Populate it for your project
// if your prototype is a single hash-routed app you want to deep-link into.
const FILE_TO_ROUTE = {};

function designFileHref(base) {
  // Use the prototype's hash-routed entry so the link renders the screen.
  const route = FILE_TO_ROUTE[base];
  if (route) return `${DESIGN_BASE}/index.html#${route}`;
  // Unmapped file (the default) — fall back to opening the raw file.
  return `${DESIGN_BASE}/${base}`;
}

// ───────────────────────── parseIndex ─────────────────────────
// Walks stories/INDEX.md and yields a structured manifest.

function parseIndex(md) {
  const lines = md.split(/\r?\n/);
  const sprints = new Map(); // sprintNum -> { name, topics: Map<topic, story[]> }
  const stories = []; // flat list, insertion order
  let currentSprint = null;
  let currentTopic = null;
  let inTable = false;
  let headerSeen = false;
  let inBacklog = false;

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];

    // Sprint header: ## Sprint 1 — Content + Credibility  (...)
    const sprintMatch = line.match(/^##\s+Sprint\s+(\d+)\s+—\s+(.+?)(?:\s+\(.*\))?$/);
    if (sprintMatch) {
      const num = parseInt(sprintMatch[1], 10);
      const name = sprintMatch[2].trim();
      currentSprint = num;
      currentTopic = null;
      inTable = false;
      inBacklog = false;
      if (!sprints.has(num)) {
        sprints.set(num, { num, name, topics: new Map() });
      }
      continue;
    }

    // Backlog section: ## Backlog — deferred during analysis  (...)
    // Rendered as a pseudo-sprint that sorts last; its single "topic" is _backlog
    // (the folder the files actually live in), so the topic-based slug/path code reuses cleanly.
    const backlogMatch = line.match(/^##\s+Backlog\b(?:\s+—\s+.+?)?(?:\s+\(.*\))?$/);
    if (backlogMatch) {
      const num = 99; // sentinel: sorts after real sprints
      currentSprint = num;
      currentTopic = "_backlog";
      inTable = false;
      headerSeen = false;
      inBacklog = true;
      if (!sprints.has(num)) {
        sprints.set(num, { num, name: "deferred", backlog: true, topics: new Map() });
      }
      if (!sprints.get(num).topics.has("_backlog")) {
        sprints.get(num).topics.set("_backlog", []);
      }
      continue;
    }

    // Topic header: ### blog
    const topicMatch = line.match(/^###\s+(\S+)/);
    if (topicMatch && currentSprint !== null) {
      currentTopic = topicMatch[1].trim();
      inTable = false;
      headerSeen = false;
      const s = sprints.get(currentSprint);
      if (!s.topics.has(currentTopic)) {
        s.topics.set(currentTopic, []);
      }
      continue;
    }

    if (!currentTopic) continue;

    // Detect table header row: | ID | Title | ...
    if (!inTable && /^\|\s*ID\s*\|/.test(line)) {
      headerSeen = true;
      continue;
    }
    // Detect separator row: |---|---|...
    if (headerSeen && /^\|[\s\-:|]+\|$/.test(line)) {
      inTable = true;
      headerSeen = false;
      continue;
    }

    // Inside table: parse a row, or stop
    if (inTable) {
      if (!line.trim().startsWith("|")) {
        inTable = false;
        continue;
      }
      const cells = splitRow(line);
      // Two table shapes (see pipeline/reference/index-template.md):
      //   sprint:  ID | Title | SP | Status | Owner | Tasks | Design | Depends on | [CR | Gen | Test | Verify]
      //   backlog: ID | Title | SP | Orig. sprint | Owner | Reason
      let id, title, sp, status, owner, tasks, designRaw, depsRaw, originalSprint = null;
      if (inBacklog) {
        if (cells.length < 5) continue;
        [id, title, sp] = [cells[0], cells[1], cells[2]];
        originalSprint = parseInt(cells[3], 10) || null;
        owner = cells[4] || "";
        status = "deferred";        // backlog stories have no status column — they're deferred
        tasks = "";
        designRaw = "";
        depsRaw = "";
      } else {
        if (cells.length < 8) continue;
        // Trailing CR/Gen/Test/Verify columns (if present) are ignored.
        [id, title, sp, status, owner, tasks, designRaw, depsRaw] = cells;
      }
      const story = {
        id: id.trim(),
        title: title.trim(),
        sp: parseInt(sp, 10) || 0,
        status: status.trim() || "draft",
        owner: owner.trim() || "",
        tasksRaw: tasks.trim(),
        design: parseIndexDesignCell(designRaw),
        dependencies: parseIndexDepsCell(depsRaw),
        topic: currentTopic,
        sprint: currentSprint,
        originalSprint,
      };
      sprints.get(currentSprint).topics.get(currentTopic).push(story);
      stories.push(story);
    }
  }

  // Compute reverse-deps (Blocks N)
  const dependents = new Map();
  for (const s of stories) {
    for (const dep of s.dependencies) {
      if (!dependents.has(dep)) dependents.set(dep, []);
      dependents.get(dep).push(s.id);
    }
  }

  const byId = new Map(stories.map((s) => [s.id, s]));

  return { sprints, stories, byId, dependents };
}

function splitRow(line) {
  // Strip leading/trailing |, split on remaining |.
  const trimmed = line.replace(/^\s*\|/, "").replace(/\|\s*$/, "");
  return trimmed.split("|").map((c) => c.trim());
}

function parseIndexDesignCell(raw) {
  const v = raw.trim();
  if (!v || v === "—" || v === "-") return { kind: "none" };
  if (v === "none-needed") return { kind: "none" };
  if (v.startsWith("→")) {
    const target = v.replace(/^→\s*/, "").trim();
    return { kind: "follows-template", target };
  }
  const parts = v.split(",").map((p) => p.trim()).filter(Boolean);
  return { kind: "files", paths: parts };
}

function parseIndexDepsCell(raw) {
  const v = raw.trim();
  if (!v || v === "—" || v === "-") return [];
  return v.split(",").map((p) => p.trim()).filter(Boolean);
}

// ───────────────────── parseFrontmatter ─────────────────────

function splitFrontmatter(text) {
  const m = text.match(/^---\r?\n([\s\S]+?)\r?\n---\r?\n?([\s\S]*)$/);
  if (!m) return { fm: null, body: text, raw: "" };
  return { fmRaw: m[1], body: m[2] };
}

function parseStory(text) {
  const { fmRaw, body } = splitFrontmatter(text);
  let fm = null;
  let fmError = null;
  try {
    fm = jsyaml.load(fmRaw || "");
  } catch (e) {
    fmError = e.message;
  }
  let design = { kind: "raw", value: "" };
  if (fm) {
    design = normalizeDesign(fm.design);
    if (!Array.isArray(fm.dependencies)) {
      fm.dependencies = fm.dependencies ? [fm.dependencies] : [];
    }
  }
  return { fm, fmRaw, fmError, body: body || "", design };
}

function normalizeDesign(value) {
  if (value == null) return { kind: "raw", value: "" };
  if (Array.isArray(value)) {
    return { kind: "files", paths: value.map(String) };
  }
  const s = String(value).trim();
  if (s === "none-needed") return { kind: "none" };
  const m = s.match(/^follows-template:\s*(\S+)$/);
  if (m) return { kind: "follows-template", target: m[1] };
  return { kind: "raw", value: s };
}

// ───────────────────── markdown rendering ─────────────────────

let markedConfigured = false;
function configureMarked() {
  if (markedConfigured) return;
  marked.use({
    gfm: true,
    breaks: false,
    headerIds: false,
    mangle: false,
  });
  markedConfigured = true;
}

function renderMarkdown(body) {
  configureMarked();
  let html = marked.parse(body);
  // Swap GFM task checkboxes (input elements) for read-only glyphs with classes.
  html = html.replace(
    /<li><input checked(?:="")? disabled(?:="")? type="checkbox"[^>]*>\s*/g,
    '<li class="ac-done">',
  );
  html = html.replace(
    /<li><input disabled(?:="")? type="checkbox"[^>]*>\s*/g,
    '<li class="ac-todo">',
  );
  // Defense in depth: strip any script tags or on-event attributes (stories are first-party).
  html = html
    .replace(/<script[\s\S]*?<\/script>/gi, "")
    .replace(/\son\w+="[^"]*"/gi, "");
  return html;
}

// ───────────────────── directory listing scrape ─────────────────────
// Python's http.server emits <a href="filename">filename</a>. Fetch once per topic.

async function fetchSlugMap(topic) {
  const url = `${STORIES_BASE}/${topic}/`;
  const res = await fetch(url);
  if (!res.ok) throw new Error(`Directory listing for ${topic}/ returned ${res.status}`);
  const text = await res.text();
  const doc = new DOMParser().parseFromString(text, "text/html");
  const map = new Map();
  const anchors = doc.querySelectorAll("a");
  // The _backlog/ folder holds stories from any topic, so match any topic there.
  const idPat = topic === "_backlog" ? "[a-z]+" : topic;
  const pattern = new RegExp(`^(story-${idPat}-\\d{2})-[\\w-]+\\.md$`);
  for (const a of anchors) {
    const href = a.getAttribute("href") || "";
    const filename = decodeURIComponent(href.replace(/^\.?\//, "").replace(/\/$/, ""));
    const m = filename.match(pattern);
    if (m) {
      map.set(m[1], filename);
    }
  }
  return map;
}

// ───────────────────── router ─────────────────────

function readHash() {
  const h = window.location.hash || "";
  const m = h.match(/^#\/([^/]+)(?:\/(.+))?$/);
  if (!m) return { topic: null, id: null };
  return { topic: m[1] || null, id: m[2] || null };
}

function setHash(topic, id) {
  const next = id ? `#/${topic}/${id}` : topic ? `#/${topic}` : "";
  if (window.location.hash !== next) {
    window.location.hash = next;
  }
}

// ───────────────────── reducer ─────────────────────

const initialState = {
  manifest: null,
  manifestError: null,
  filters: { sprint: "all", status: "all", owner: "all", q: "" },
  selection: { topic: null, id: null },
  stories: new Map(), // id -> parsedStory | { error: msg, attemptedUrl }
  slugMaps: new Map(), // topic -> Map<id, filename>
  pendingFetches: new Set(),
  mobileTab: "list",
};

function reducer(state, action) {
  switch (action.type) {
    case "SET_MANIFEST":
      return { ...state, manifest: action.manifest, manifestError: null };
    case "MANIFEST_ERROR":
      return { ...state, manifest: null, manifestError: action.error };
    case "SET_FILTER":
      return { ...state, filters: { ...state.filters, [action.key]: action.value } };
    case "CLEAR_FILTERS":
      return { ...state, filters: initialState.filters };
    case "SELECT":
      return { ...state, selection: { topic: action.topic, id: action.id } };
    case "SET_STORY":
      return {
        ...state,
        stories: new Map(state.stories).set(action.id, action.payload),
      };
    case "SET_SLUGMAP":
      return {
        ...state,
        slugMaps: new Map(state.slugMaps).set(action.topic, action.map),
      };
    case "PENDING_ADD": {
      const p = new Set(state.pendingFetches);
      p.add(action.key);
      return { ...state, pendingFetches: p };
    }
    case "PENDING_DEL": {
      const p = new Set(state.pendingFetches);
      p.delete(action.key);
      return { ...state, pendingFetches: p };
    }
    case "SET_MOBILE_TAB":
      return { ...state, mobileTab: action.tab };
    default:
      return state;
  }
}

// ───────────────────── App ─────────────────────

function App() {
  const [state, dispatch] = useReducer(reducer, initialState);
  const searchRef = useRef(null);
  const detailRef = useRef(null);

  // Load INDEX.md once.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await fetch(`${STORIES_BASE}/INDEX.md`);
        if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
        const text = await res.text();
        if (cancelled) return;
        const manifest = parseIndex(text);
        dispatch({ type: "SET_MANIFEST", manifest });
      } catch (e) {
        if (cancelled) return;
        dispatch({ type: "MANIFEST_ERROR", error: e.message });
      }
    })();
    return () => { cancelled = true; };
  }, []);

  // Sync URL hash → selection.
  useEffect(() => {
    function onHash() {
      const { topic, id } = readHash();
      dispatch({ type: "SELECT", topic, id });
    }
    onHash();
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);

  // Once manifest loads, if no selection, default to first story.
  useEffect(() => {
    if (!state.manifest) return;
    if (state.selection.id) return;
    const first = state.manifest.stories[0];
    if (first) {
      setHash(first.topic, first.id);
    }
  }, [state.manifest]);

  // When selection.topic changes, ensure slugMap exists.
  useEffect(() => {
    const topic = state.selection.topic;
    if (!topic) return;
    if (state.slugMaps.has(topic)) return;
    const key = `slugmap:${topic}`;
    if (state.pendingFetches.has(key)) return;
    dispatch({ type: "PENDING_ADD", key });
    fetchSlugMap(topic)
      .then((map) => {
        dispatch({ type: "SET_SLUGMAP", topic, map });
      })
      .catch((e) => {
        dispatch({ type: "SET_SLUGMAP", topic, map: new Map() });
        console.warn(`Failed slug map for ${topic}:`, e.message);
      })
      .finally(() => {
        dispatch({ type: "PENDING_DEL", key });
      });
  }, [state.selection.topic, state.slugMaps, state.pendingFetches]);

  // When selection.id changes, fetch the story body.
  useEffect(() => {
    const { topic, id } = state.selection;
    if (!topic || !id) return;
    if (state.stories.has(id)) return;
    const slugMap = state.slugMaps.get(topic);
    if (!slugMap) return; // wait for slugmap
    const filename = slugMap.get(id);
    if (!filename) {
      dispatch({
        type: "SET_STORY",
        id,
        payload: {
          error: "Story file missing — no entry in directory listing.",
          attemptedUrl: `${STORIES_BASE}/${topic}/`,
        },
      });
      return;
    }
    const url = `${STORIES_BASE}/${topic}/${filename}`;
    const key = `story:${id}`;
    if (state.pendingFetches.has(key)) return;
    dispatch({ type: "PENDING_ADD", key });
    fetch(url)
      .then((r) => {
        if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
        return r.text();
      })
      .then((text) => {
        const parsed = parseStory(text);
        dispatch({ type: "SET_STORY", id, payload: { ...parsed, url } });
      })
      .catch((e) => {
        dispatch({
          type: "SET_STORY",
          id,
          payload: { error: e.message, attemptedUrl: url },
        });
      })
      .finally(() => {
        dispatch({ type: "PENDING_DEL", key });
      });
  }, [state.selection.id, state.selection.topic, state.slugMaps, state.stories, state.pendingFetches]);

  // Derived: visibleList per current filters.
  const visibleList = useMemo(() => {
    if (!state.manifest) return [];
    const { sprint, status, owner, q } = state.filters;
    const qLower = q.trim().toLowerCase();
    let list = state.manifest.stories;
    if (state.selection.topic) {
      list = list.filter((s) => s.topic === state.selection.topic);
    }
    if (sprint !== "all") list = list.filter((s) => s.sprint === parseInt(sprint, 10));
    if (status !== "all") list = list.filter((s) => s.status === status);
    if (owner !== "all") list = list.filter((s) => s.owner === owner);
    if (qLower) {
      list = list.filter((s) =>
        (s.id + " " + s.title + " " + s.topic).toLowerCase().includes(qLower),
      );
    }
    return list;
  }, [state.manifest, state.filters, state.selection.topic]);

  const ownerList = useMemo(() => {
    if (!state.manifest) return [];
    return Array.from(new Set(state.manifest.stories.map((s) => s.owner))).sort();
  }, [state.manifest]);

  // Sprint numbers actually present (exclude the backlog sentinel 99), ascending.
  const sprintList = useMemo(() => {
    if (!state.manifest) return [];
    return Array.from(state.manifest.sprints.keys())
      .filter((n) => n !== 99)
      .sort((a, b) => a - b);
  }, [state.manifest]);

  // Statuses actually present, ordered by the pipeline lifecycle.
  const statusList = useMemo(() => {
    if (!state.manifest) return [];
    const order = [
      "draft", "ready", "in-progress", "done",
      "code-reviewed", "code-review-failed",
      "tests-generated", "tested", "testing-failed",
      "verified", "verification-failed",
      "blocked", "deferred",
    ];
    const present = new Set(state.manifest.stories.map((s) => s.status));
    const known = order.filter((s) => present.has(s));
    const extra = Array.from(present).filter((s) => !order.includes(s)).sort();
    return [...known, ...extra];
  }, [state.manifest]);

  // Keyboard nav: J/K, arrows, /, Enter, Esc
  useEffect(() => {
    function onKey(e) {
      const t = e.target;
      const inField = t && t.matches && t.matches("input, textarea, select, [contenteditable]");
      if (e.key === "/" && !inField) {
        e.preventDefault();
        searchRef.current && searchRef.current.focus();
        return;
      }
      if (e.key === "Escape") {
        if (searchRef.current && document.activeElement === searchRef.current) {
          dispatch({ type: "SET_FILTER", key: "q", value: "" });
          searchRef.current.blur();
        }
        return;
      }
      if (inField) return;
      if (e.key === "j" || e.key === "ArrowDown") {
        moveSelection(1);
        e.preventDefault();
      } else if (e.key === "k" || e.key === "ArrowUp") {
        moveSelection(-1);
        e.preventDefault();
      } else if (e.key === "Enter") {
        if (detailRef.current) {
          detailRef.current.scrollIntoView({ behavior: "smooth", block: "start" });
          detailRef.current.focus();
        }
      }
    }
    function moveSelection(delta) {
      const list = visibleList;
      if (!list.length) return;
      const idx = list.findIndex((s) => s.id === state.selection.id);
      let next = idx + delta;
      if (next < 0) next = 0;
      if (next > list.length - 1) next = list.length - 1;
      const target = list[next];
      if (target) setHash(target.topic, target.id);
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [visibleList, state.selection.id]);

  if (state.manifestError) {
    return (
      <div className="shell">
        <TopBar manifest={null} />
        <div className="pane">
          <div className="center-card">
            <h2>Stories index not found</h2>
            <p>
              Expected at <code>{STORIES_BASE}/INDEX.md</code>. Run{" "}
              <code>/manage-stories index</code> from the project root, then refresh.
            </p>
            <p style={{ marginTop: 12, color: "var(--ink-muted)", fontSize: 12 }}>
              Fetch error: <code>{state.manifestError}</code>
            </p>
          </div>
        </div>
      </div>
    );
  }

  if (!state.manifest) {
    return (
      <div className="shell">
        <TopBar manifest={null} />
        <div className="pane">
          <div className="center-card">
            <p style={{ color: "var(--ink-muted)" }}>Loading stories index…</p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="shell">
      <TopBar manifest={state.manifest} selection={state.selection} />
      <div className="tabs">
        <button
          aria-current={state.mobileTab === "tree"}
          onClick={() => dispatch({ type: "SET_MOBILE_TAB", tab: "tree" })}
        >
          Topics
        </button>
        <button
          aria-current={state.mobileTab === "list"}
          onClick={() => dispatch({ type: "SET_MOBILE_TAB", tab: "list" })}
        >
          List
        </button>
        <button
          aria-current={state.mobileTab === "detail"}
          onClick={() => dispatch({ type: "SET_MOBILE_TAB", tab: "detail" })}
        >
          Detail
        </button>
      </div>
      <div className="panes">
        <TreePane
          className={state.mobileTab === "tree" ? "active" : ""}
          manifest={state.manifest}
          selection={state.selection}
          onSelect={(topic, id) => {
            setHash(topic, id);
            dispatch({ type: "SET_MOBILE_TAB", tab: "list" });
          }}
        />
        <ListPane
          className={state.mobileTab === "list" ? "active" : ""}
          list={visibleList}
          selection={state.selection}
          filters={state.filters}
          ownerList={ownerList}
          sprintList={sprintList}
          statusList={statusList}
          onFilter={(key, value) => dispatch({ type: "SET_FILTER", key, value })}
          onClearFilters={() => dispatch({ type: "CLEAR_FILTERS" })}
          onSelect={(topic, id) => {
            setHash(topic, id);
            dispatch({ type: "SET_MOBILE_TAB", tab: "detail" });
          }}
          searchRef={searchRef}
        />
        <DetailPane
          className={state.mobileTab === "detail" ? "active" : ""}
          manifest={state.manifest}
          selection={state.selection}
          stories={state.stories}
          detailRef={detailRef}
        />
      </div>
    </div>
  );
}

// ───────────────────── TopBar ─────────────────────

function TopBar({ manifest, selection }) {
  const total = manifest ? manifest.stories.length : 0;
  const totalSp = manifest ? manifest.stories.reduce((a, s) => a + s.sp, 0) : 0;
  const counts = manifest
    ? manifest.stories.reduce(
        (acc, s) => {
          acc[s.status] = (acc[s.status] || 0) + 1;
          return acc;
        },
        { draft: 0, ready: 0, "in-progress": 0, blocked: 0, done: 0 },
      )
    : null;
  return (
    <header className="topbar">
      <div className="brand">Stories</div>
      {selection && selection.id && (
        <div className="crumb">
          {selection.topic} / <code>{selection.id}</code>
        </div>
      )}
      {manifest && (
        <div className="summary">
          <span>
            <strong>{total}</strong> stories
          </span>
          <span>
            <strong>{totalSp}</strong> SP
          </span>
          {counts.done > 0 && (
            <span>
              <strong>{counts.done}</strong> done
            </span>
          )}
          {counts["in-progress"] > 0 && (
            <span>
              <strong>{counts["in-progress"]}</strong> in-progress
            </span>
          )}
          <span>
            <strong>{counts.draft}</strong> draft
          </span>
        </div>
      )}
      <ThemeToggle />
    </header>
  );
}

// ───────────────────── ThemeToggle ─────────────────────

const THEME_STORAGE_KEY = "stories-viewer-theme";
const THEME_CYCLE = ["auto", "light", "dark"];
const THEME_ICON = { auto: "◐", light: "☼", dark: "☾" };

function ThemeToggle() {
  const [theme, setTheme] = useState(() => {
    return document.documentElement.getAttribute("data-theme") || "auto";
  });
  const cycle = useCallback(() => {
    const idx = THEME_CYCLE.indexOf(theme);
    const next = THEME_CYCLE[(idx + 1) % THEME_CYCLE.length];
    document.documentElement.setAttribute("data-theme", next);
    try {
      localStorage.setItem(THEME_STORAGE_KEY, next);
    } catch (e) {
      /* private mode etc. — fine */
    }
    setTheme(next);
  }, [theme]);
  const label = `Theme: ${theme} (click to cycle)`;
  return (
    <button
      className="theme-toggle"
      onClick={cycle}
      aria-label={label}
      title={label}
    >
      {THEME_ICON[theme] || "◐"}
    </button>
  );
}

// ───────────────────── TreePane ─────────────────────

function TreePane({ className, manifest, selection, onSelect }) {
  const sprints = Array.from(manifest.sprints.values()).sort((a, b) => a.num - b.num);
  return (
    <nav className={`pane tree-pane ${className || ""}`} aria-label="Topics">
      <div className="pane-header">Topics</div>
      <div className="tree">
        {sprints.map((sprint) => (
          <div key={sprint.num}>
            <div className="sprint">
              {sprint.backlog ? "Backlog" : `Sprint ${sprint.num}`}{" "}
              <span className="meta">— {sprint.name}</span>
            </div>
            {sprint.topics.size === 0 ? (
              <button
                className="tree-row"
                disabled
                title="Deferred — no stories yet. See INDEX.md note."
              >
                <span className="twirl">▸</span>
                <span className="topic-name">(deferred)</span>
                <span className="topic-count">0</span>
              </button>
            ) : (
              Array.from(sprint.topics.entries()).map(([topic, list]) => {
                const active = selection.topic === topic;
                const totalSp = list.reduce((a, s) => a + s.sp, 0);
                return (
                  <button
                    key={topic}
                    className="tree-row"
                    aria-current={active}
                    onClick={() => onSelect(topic, list[0]?.id)}
                    title={`${list.length} stories · ${totalSp} SP`}
                  >
                    <span className="twirl">{active ? "▾" : "▸"}</span>
                    <span className="topic-name">{topic === "_backlog" ? "deferred" : topic}</span>
                    <span className="topic-count">{list.length}</span>
                  </button>
                );
              })
            )}
          </div>
        ))}
      </div>
    </nav>
  );
}

// ───────────────────── ListPane ─────────────────────

function ListPane({ className, list, selection, filters, ownerList, sprintList, statusList, onFilter, onClearFilters, onSelect, searchRef }) {
  return (
    <section className={`pane list-pane ${className || ""}`} aria-label="Story list">
      <div className="pane-header">
        {selection.topic ? (selection.topic === "_backlog" ? "deferred (backlog)" : selection.topic) : "All stories"}
        {selection.topic && (
          <span style={{ float: "right", fontWeight: 500, letterSpacing: 0, textTransform: "none", color: "var(--ink)" }}>
            {list.length} stories
          </span>
        )}
      </div>
      <div className="filterbar">
        <div className="search">
          <input
            ref={searchRef}
            placeholder="Filter by id / title / topic"
            value={filters.q}
            onChange={(e) => onFilter("q", e.target.value)}
            aria-label="Search stories"
          />
          <span className="slash">/</span>
        </div>
        <select
          value={filters.sprint}
          onChange={(e) => onFilter("sprint", e.target.value)}
          aria-label="Filter by sprint"
        >
          <option value="all">all sprints</option>
          {sprintList.map((n) => (
            <option key={n} value={String(n)}>
              sprint {n}
            </option>
          ))}
        </select>
        <select
          value={filters.status}
          onChange={(e) => onFilter("status", e.target.value)}
          aria-label="Filter by status"
        >
          <option value="all">all status</option>
          {statusList.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>
        <select
          value={filters.owner}
          onChange={(e) => onFilter("owner", e.target.value)}
          aria-label="Filter by owner"
        >
          <option value="all">all owners</option>
          {ownerList.map((o) => (
            <option key={o} value={o}>
              {o}
            </option>
          ))}
        </select>
      </div>
      <div className="list" role="list">
        {list.length === 0 ? (
          <div className="list-empty">
            <strong>No stories match</strong>
            <p>Try clearing the filters above.</p>
            <button className="copy-btn" onClick={onClearFilters}>
              Clear filters
            </button>
          </div>
        ) : (
          list.map((s) => (
            <button
              key={s.id}
              className="list-item"
              aria-current={selection.id === s.id}
              onClick={() => onSelect(s.topic, s.id)}
              role="listitem"
            >
              <div className="id-row">
                <span className="id">{s.id}</span>
                <span className="sp">{s.sp} SP</span>
              </div>
              <span className="title">{s.title}</span>
              <div className="meta">
                <span className={`chip chip-status-${s.status}`}>{s.status}</span>
                <span className="chip">{s.owner}</span>
                {s.design.kind === "files" && (
                  <span className="chip chip-design-file">{s.design.paths[0]}</span>
                )}
                {s.design.kind === "follows-template" && (
                  <span className="chip chip-design-template">→ {s.design.target}</span>
                )}
                {s.design.kind === "none" && (
                  <span className="chip chip-design-none">none-needed</span>
                )}
              </div>
            </button>
          ))
        )}
      </div>
    </section>
  );
}

// ───────────────────── DetailPane ─────────────────────

function DetailPane({ className, manifest, selection, stories, detailRef }) {
  const id = selection.id;
  const indexEntry = id ? manifest.byId.get(id) : null;
  const story = id ? stories.get(id) : null;

  if (!id) {
    return (
      <article className={`pane detail ${className || ""}`} aria-label="Story detail">
        <div className="center-card">
          <p style={{ color: "var(--ink-muted)" }}>Pick a story from the list.</p>
        </div>
      </article>
    );
  }

  if (!story) {
    return (
      <article className={`pane detail ${className || ""}`} aria-label="Story detail" ref={detailRef} tabIndex={-1}>
        <div className="detail-inner">
          <div className="detail-id">{id}</div>
          <div className="detail-title">{indexEntry ? indexEntry.title : "Loading…"}</div>
          <p style={{ color: "var(--ink-muted)" }}>Fetching story body…</p>
        </div>
      </article>
    );
  }

  if (story.error) {
    return (
      <article className={`pane detail ${className || ""}`} aria-label="Story detail" ref={detailRef} tabIndex={-1}>
        <div className="detail-inner">
          <div className="detail-id">{id}</div>
          <div className="detail-title">{indexEntry ? indexEntry.title : "Story file missing"}</div>
          <div className="warning-banner">
            <strong>Could not load this story.</strong>
            <div style={{ marginTop: 4 }}>{story.error}</div>
            <div style={{ marginTop: 8, fontSize: 12 }}>
              Attempted URL: <code>{story.attemptedUrl}</code>
              <button
                className="copy-btn"
                onClick={() => navigator.clipboard?.writeText(story.attemptedUrl)}
              >
                Copy path
              </button>
            </div>
          </div>
        </div>
      </article>
    );
  }

  const fm = story.fm || {};
  const title = (fm && fm.id && indexEntry ? indexEntry.title : indexEntry?.title) || id;

  const dependents = manifest.dependents.get(id) || [];
  const dependencies = (fm.dependencies || []).slice();

  return (
    <article className={`pane detail ${className || ""}`} aria-label="Story detail" ref={detailRef} tabIndex={-1}>
      <div className="detail-inner">
        <div className="detail-id">{id}</div>
        <h1 className="detail-title">{title}</h1>
        <MetadataChips fm={fm} story={story} manifest={manifest} />
        <DesignBlock design={story.design} manifest={manifest} />
        <Relationships
          dependencies={dependencies}
          dependents={dependents}
          manifest={manifest}
        />
        {story.fmError && (
          <div className="warning-banner">
            <strong>YAML frontmatter could not be parsed.</strong>
            <div style={{ marginTop: 4, fontSize: 12 }}>{story.fmError}</div>
            <pre className="fm-pre" style={{ marginTop: 8 }}>{story.fmRaw}</pre>
          </div>
        )}
        <div
          className="story-body"
          dangerouslySetInnerHTML={{ __html: renderMarkdown(story.body) }}
        />
      </div>
    </article>
  );
}

function MetadataChips({ fm, story, manifest }) {
  if (!fm) return null;
  const status = fm.status || "draft";
  return (
    <div className="chip-row">
      <span className="chip">
        <span className="k">sprint</span> {fm.sprint}
      </span>
      <span className="chip">
        <span className="k">SP</span> {fm.story_points}
      </span>
      <span className={`chip chip-status-${status}`}>
        <span className="k">status</span> {status}
      </span>
      <span className="chip">
        <span className="k">owner</span> {fm.owner || "—"}
      </span>
      <span className="chip">
        <span className="k">topic</span> {fm.topic}
      </span>
    </div>
  );
}

function DesignBlock({ design, manifest }) {
  if (!design) {
    return null;
  }

  let count = 0;
  let body = null;

  if (design.kind === "none") {
    count = 0;
    body = (
      <div className="none">no design — backend-only story</div>
    );
  } else if (design.kind === "follows-template") {
    count = 1;
    const ok = manifest.byId.has(design.target);
    const target = manifest.byId.get(design.target);
    body = (
      <div className="chip-row" style={{ marginBottom: 0 }}>
        <a
          className={`chip chip-design-template chip-link ${ok ? "" : "broken"}`}
          href={ok ? `#/${target.topic}/${design.target}` : "#"}
          title={ok ? "Open template story" : "not in INDEX.md"}
        >
          → {design.target}
        </a>
      </div>
    );
  } else if (design.kind === "files") {
    count = design.paths.length;
    body = (
      <div className="chip-row" style={{ marginBottom: 0 }}>
        {design.paths.map((p) => {
          const base = p.replace(/^design\//, "");
          return (
            <a
              key={p}
              className="chip chip-design-file"
              href={designFileHref(base)}
              target="_blank"
              rel="noreferrer"
              title={`Open the rendered screen for ${base} in a new tab`}
            >
              {base}
            </a>
          );
        })}
      </div>
    );
  } else {
    return null;
  }

  return (
    <div className="rel-block">
      <h3>Design ({count})</h3>
      {body}
    </div>
  );
}

function Relationships({ dependencies, dependents, manifest }) {
  return (
    <div className="rel-block">
      <h3>Depends on ({dependencies.length})</h3>
      {dependencies.length === 0 ? (
        <div className="none">— root story, nothing blocks it.</div>
      ) : (
        <div className="chip-row" style={{ marginBottom: 0 }}>
          {dependencies.map((dep) => {
            const target = manifest.byId.get(dep);
            return target ? (
              <a key={dep} className="chip chip-link" href={`#/${target.topic}/${dep}`}>
                {dep}
              </a>
            ) : (
              <span key={dep} className="chip chip-link broken" title="not in INDEX.md">
                {dep}
              </span>
            );
          })}
        </div>
      )}
      <h3 style={{ marginTop: 14 }}>Blocks ({dependents.length})</h3>
      {dependents.length === 0 ? (
        <div className="none">— leaf story, no downstream work depends on it.</div>
      ) : (
        <div className="chip-row" style={{ marginBottom: 0 }}>
          {dependents.map((id) => {
            const target = manifest.byId.get(id);
            return target ? (
              <a key={id} className="chip chip-link" href={`#/${target.topic}/${id}`}>
                {id}
              </a>
            ) : (
              <span key={id} className="chip chip-link broken">
                {id}
              </span>
            );
          })}
        </div>
      )}
    </div>
  );
}

// ───────────────────── mount ─────────────────────

const root = ReactDOM.createRoot(document.getElementById("root"));
root.render(<App />);

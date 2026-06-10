# Team Dashboard

Local web dashboard for observing **a single in-flight `agf-team-start` session** — team composition, task progress, message timeline, artifact updates — without juggling `agf-tasks`, transcript JSONL, and `docs/`.

**Zero-invasion**: this tool never modifies `agf-team-start.sh`, `.claude/`, or `.git/hooks/`. If the dashboard isn't running, team work is completely unaffected.

> **Release context**: [CHANGELOG v1.6.0](../../CHANGELOG.md#v160--2026-05-13--team-dashboard--versioning-discipline)（v1.6.0 引入；原 PRD / spec / plan 在 v3.0.0 docs cleanup 中移除自 working tree，可通过 `git show 865173d:docs/prd/archive/team-dashboard-2026-05-13.md` 查阅历史）

---

## Quick Start

```bash
# In a terminal SEPARATE from your agf-team-start session
cd tools/team-dashboard

# First time only: install backend deps
pip install -e ./server

# Dev mode (default): hot-reload Vite SPA + uvicorn backend
./start.sh
# Open http://localhost:5173/

# OR prod mode: build static SPA, FastAPI serves it directly
./start.sh --prod
# Open http://localhost:8765/
```

`Ctrl-C` cleanly stops both processes.

---

## Startup Modes

The dashboard ships with **two startup modes**, both first-class. Pick based on workflow.

| Mode | Command | Backend | Frontend | Open URL | Use case |
|---|---|---|---|---|---|
| **Dev** (default) | `./start.sh` | uvicorn `:8765` | Vite dev `:5173` (hot reload) | `http://localhost:5173/` | Local SPA development, fast iteration |
| **Prod** | `./start.sh --prod` | uvicorn `:8765` (static-serves `web/dist/`) | — (built into `dist/`) | `http://localhost:8765/` | Single-port deployment, no Node.js runtime needed at runtime |

In dev mode `start.sh` removes any stale `web/dist/` so the backend doesn't accidentally auto-serve a prior prod build.

---

## Port Conventions

| Port | Service | Notes |
|---|---|---|
| `8765` | FastAPI backend (uvicorn) — SSE on `/events/<sid>`, redirect on `/`, optional static at `/static/` and `/task/<sid>` | Fixed, fail-fast on conflict (AC-8) |
| `5173` | Vite dev server (dev mode only) — proxies `/events/*` to `:8765` | Fixed, fail-fast on conflict |

**Port conflict** → `start.sh` exits with code ≠ 0 and prints `port <N> in use` to stderr. v1 does **not** auto-find a free port — stop the conflicting process or wait. (Resolved by user as `OQ-2: fail-fast`; see PRD §9.)

---

## How It Works

The dashboard is a pure **observer** — it watches files and reads the Claude Code session JSONL, never writes back.

```
~/.claude/tasks/*.json           ──┐
~/.claude/projects/<slug>/*.jsonl ─┼─→ watchfiles → SSE → React SPA
docs/{plans,prd,qa,reviews}/*     ──┤
git worktree list (poll 5s)       ──┘
```

- **`server/`** — FastAPI + `watchfiles`; parses session JSONL with `transcript_parser.py`, picks the newest session via `session_resolver.py`, pushes SSE events.
- **`web/`** — React 19 + Vite + native `EventSource`; 3-column layout (Tasks / Timeline / Artifacts) with a header showing parsed `feature_desc` + `teammates`.

Five SSE event types (spec §7): `initial`, `task.update`, `timeline.append`, `artifact.update`, `worktree.status`.

---

## Known Limitations (v1)

- **macOS-only verified.** v1 uses BSD `lsof` and macOS-native watchfiles; Linux may work but is unsupported in v1.
- **`/clear` fragmentation.** Running `/clear` in the Claude session starts a new JSONL file (and a new session ID). The dashboard will switch to the new sid (mtime-newest), so events before `/clear` appear "lost" in the view. This is a known trade-off from spec §3 decision A1 — solving it requires self-generated `TASK_ID` + hooks, which would break zero-invasion. Deferred to v2.
- **Manual startup, no auto-launch.** You must run `./start.sh` in a separate terminal — there's no daemon, no autostart from the launcher. This is deliberate (zero-invasion). If you forget, team work proceeds normally; only the dashboard is missing.
- **Read-only.** No actions in the UI — can't cancel tasks, send hints, or close worktrees. Deferred to v2.
- **Single session.** v1 shows only the **currently-newest** session JSONL. No historical browse, no multi-session port. Deferred to v2.
- **Cost summarization not included.** Use Claude Code's built-in `/usage` for per-session token / cost / cache hit (v3.0.0 removed the wrapper + monthly cost log).

---

## Layout

```
tools/team-dashboard/
├── start.sh            # this entry point (port probe → uvicorn + vite or build+uvicorn)
├── README.md           # this file
├── server/             # FastAPI backend (Python ≥3.10)
│   ├── main.py         #   FastAPI app + SSE routes
│   ├── watcher.py      #   3x watchfiles + 5s worktree poll
│   ├── transcript_parser.py
│   ├── session_resolver.py
│   ├── models.py       #   Pydantic SessionMeta + 5 SSE event types
│   ├── pyproject.toml
│   └── tests/          #   63 pytest tests
└── web/                # React + Vite SPA
    ├── src/App.tsx     #   header + 3-column layout
    ├── src/sse.ts      #   EventSource wrapper + reducer
    ├── src/components/ #   TasksPanel / TimelinePanel / ArtifactsPanel
    └── README.md       #   frontend-specific details (build, lint, test commands)
```

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| `port 8765 in use` on startup | `lsof -nP -iTCP:8765 -sTCP:LISTEN` to find the holder; stop it or close it. |
| Header shows `(unparsed launch)` and empty teammates | The JSONL didn't start with `/agf-team-start <desc> [teammates: ...]`. Timeline / Tasks / Artifacts still work (AC-9 degraded mode). |
| `pnpm: command not found` | `npm install -g pnpm` (frontend uses pnpm; backend uses pip). |
| Backend imports fail | Run `pip install -e tools/team-dashboard/server` once. |

---

## Versioning

v1 of the dashboard ships behind this single tool directory. v2 roadmap was specified in the original PRD §8 (Out-of-Scope / Future Work)，归档可通过 `git show 865173d:docs/prd/archive/team-dashboard-2026-05-13.md` 查阅（v3.0.0 docs cleanup 时移除自 working tree）。

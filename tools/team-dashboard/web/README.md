# Team Dashboard — Frontend (React + Vite + TypeScript)

Real-time single-page app for observing an `agf-team-start` session.  
Connects to the FastAPI backend at `:8765` via SSE (Server-Sent Events).

---

## Startup Modes

### Dev mode (default) — Vite dev server on `:5173` + hot reload

```bash
# From this directory (tools/team-dashboard/web/)
pnpm install        # first time only
pnpm dev            # starts on http://localhost:5173
```

Requests to `/events/*` are proxied to the backend at `http://localhost:8765`.  
Navigate to `http://localhost:5173/task/<sid>` (or let the root `start.sh` open it).

**Ports:**
- Frontend SPA: `http://localhost:5173`
- Backend SSE:  `http://localhost:8765` (run separately)

### Prod mode — static build served by FastAPI on `:8765`

```bash
pnpm build          # outputs dist/ in this directory
```

The `dist/` folder is served by the FastAPI backend when launched with `--prod`.  
All routes are served from `http://localhost:8765/`.

**Ports:**
- Dashboard (prod): `http://localhost:8765`

---

## Development

```bash
pnpm test           # run unit tests (vitest)
pnpm test:watch     # watch mode
pnpm lint           # ESLint check
pnpm build          # type-check + production build
```

---

## Architecture

```
src/
├── types.ts          # TypeScript interfaces (SSE events, Task, Timeline…)
├── sse.ts            # EventSource wrapper + useDashboardStream hook + pure reducer
├── App.tsx           # Header + 3-column layout (TasksPanel|TimelinePanel|ArtifactsPanel)
├── App.css           # All styles (dark theme, no external UI lib)
├── main.tsx          # React root mount
├── components/
│   ├── TasksPanel.tsx      # Task list with status + owner
│   ├── TimelinePanel.tsx   # Event stream (SendMessage/TaskCreate/Agent)
│   └── ArtifactsPanel.tsx  # docs/ file watcher with mtime
└── __tests__/
    ├── sse.test.ts         # Pure reducer tests (no DOM)
    └── components.test.tsx # Render tests per panel
```

### SSE event types (5 total — spec §7)

| Event | Effect |
|---|---|
| `initial` | Replace all state (full snapshot — used on connect/reconnect) |
| `task.update` | Replace entire task list |
| `timeline.append` | Append 1 event to timeline |
| `artifact.update` | Upsert artifact by path |
| `worktree.status` | Replace worktree list |

---

## Routing

URL pattern: `/task/<session-id>`  

The backend `GET /` does a 302 redirect to `/task/<current-sid>`.  
The SPA reads the sid from `window.location.pathname` and opens an `EventSource`
to `/events/<sid>` (proxied to `:8765` in dev mode).

---

## Known Limitations (v1)

- **macOS-only** — tested on macOS only; Linux users may need to verify
- **`/clear` fragmentation** — if the user runs `/clear` mid-session, the sid changes
  and the dashboard shows a new empty view (known design trade-off, see spec §3)
- **Manual startup** — the dashboard must be started manually with `start.sh`
  before or after `agf-team-start`; if not started, team work is completely unaffected
- **Read-only** — no UI actions; purely observational

---

## Tech Stack

- **React 19** + **TypeScript** (strict)
- **Vite 8** (dev server + build)
- **Vitest 4** + **Testing Library** (unit tests)
- Native browser `EventSource` (no WebSocket or polling libs)
- Plain CSS (no Tailwind or UI component library)

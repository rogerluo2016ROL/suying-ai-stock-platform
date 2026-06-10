// ============================================================
// Team Dashboard — main App
// Routes: / (redirect to /task/<sid>) | /task/:sid
// Header: feature_desc + teammates + worktree + connection
// Body: 3 columns — Tasks | Timeline | Artifacts
// ============================================================

import { useMemo } from "react";
import { useDashboardStream } from "./sse";
import type { ConnectionState, WorktreeEntry } from "./types";
import TasksPanel from "./components/TasksPanel";
import TimelinePanel from "./components/TimelinePanel";
import ArtifactsPanel from "./components/ArtifactsPanel";
import "./App.css";

// ------------------------------------------------------------------
// Helpers
// ------------------------------------------------------------------

function parseSidFromPath(): string | null {
  // Expects path /task/<sid>  OR  /?sid=<sid>
  const path = window.location.pathname;
  const match = path.match(/\/task\/([^/?#]+)/);
  if (match) return decodeURIComponent(match[1]);
  const params = new URLSearchParams(window.location.search);
  return params.get("sid");
}

function ConnectionBadge({ state }: { state: ConnectionState }) {
  const label: Record<ConnectionState, string> = {
    connecting: "Connecting…",
    open: "Live",
    reconnecting: "Reconnecting…",
    closed: "Offline",
  };
  return (
    <span
      className={`conn-badge conn-${state}`}
      role="status"
      aria-live="polite"
    >
      <span className="conn-dot" aria-hidden="true" />
      {label[state]}
    </span>
  );
}

function WorktreeInfo({ entries }: { entries: WorktreeEntry[] }) {
  if (entries.length === 0) return null;
  return (
    <ul className="worktree-list" aria-label="Active worktrees">
      {entries.map((w) => (
        <li key={w.path} className="worktree-entry">
          <span className="worktree-branch">{w.branch}</span>
          <span className="worktree-path" title={w.path}>
            {w.path.split("/").slice(-2).join("/")}
          </span>
        </li>
      ))}
    </ul>
  );
}

// ------------------------------------------------------------------
// Main App
// ------------------------------------------------------------------

export default function App() {
  const sid = useMemo(() => parseSidFromPath(), []);
  const { meta, tasks, timeline, artifacts, worktree, connectionState } =
    useDashboardStream(sid);

  // If no sid in URL, show a waiting screen
  if (!sid) {
    return (
      <div className="waiting-screen" role="main">
        <h1>Team Dashboard</h1>
        <p className="waiting-msg">
          Waiting for a session…
          <br />
          Start a session:{" "}
          <code>./tools/team-dashboard/start.sh</code>
          <br />
          Then navigate to{" "}
          <code>http://localhost:8765/</code> which will redirect here
          automatically.
        </p>
      </div>
    );
  }

  return (
    <div className="app" data-testid="app-root">
      {/* ---- Header ---- */}
      <header className="app-header" role="banner">
        <div className="header-main">
          <h1 className="feature-desc">
            {meta?.feature_desc ?? "Team Dashboard"}
          </h1>
          <ConnectionBadge state={connectionState} />
        </div>

        <div className="header-meta">
          {meta && (
            <>
              <span className="meta-lead" aria-label="Lead">
                👑 {meta.lead}
              </span>
              {meta.teammates.length > 0 && (
                <ul className="teammates-list" aria-label="Teammates">
                  {meta.teammates.map((t) => (
                    <li key={t} className="teammate-chip">
                      {t}
                    </li>
                  ))}
                </ul>
              )}
              <span className="meta-sid" title="Session ID">
                sid: {meta.session_id.slice(0, 8)}…
              </span>
            </>
          )}
          {!meta && connectionState === "connecting" && (
            <span className="meta-loading">Loading session…</span>
          )}
          {!meta && connectionState === "open" && (
            <span className="meta-warn">
              (unparsed launch — no /agf-team-start format detected)
            </span>
          )}
        </div>

        {worktree.length > 0 && (
          <div className="header-worktree">
            <WorktreeInfo entries={worktree} />
          </div>
        )}
      </header>

      {/* ---- 3-column body ---- */}
      <main className="dashboard-body" role="main">
        <TasksPanel tasks={tasks} />
        <TimelinePanel timeline={timeline} />
        <ArtifactsPanel artifacts={artifacts} />
      </main>
    </div>
  );
}

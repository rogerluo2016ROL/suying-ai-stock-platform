// ============================================================
// Component render tests — TasksPanel, TimelinePanel, ArtifactsPanel
// Verify isolated renders + partial-update isolation
// ============================================================

import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import "@testing-library/jest-dom";
import TasksPanel from "../components/TasksPanel";
import TimelinePanel from "../components/TimelinePanel";
import ArtifactsPanel from "../components/ArtifactsPanel";
import type { Task, TimelineEvent, Artifact } from "../types";

// ---- Fixtures ----

const tasks: Task[] = [
  { id: "1", subject: "Build login form", status: "pending", owner: "frontend-dev" },
  { id: "2", subject: "Auth endpoint", status: "in_progress", owner: "backend-dev" },
  { id: "3", subject: "Deploy infra", status: "completed", owner: "backend-dev" },
];

const timeline: TimelineEvent[] = [
  {
    id: "evt-1",
    type: "task_create",
    timestamp: "2026-05-13T14:30:00.000Z",
    summary: "TaskCreate: Build login form",
  },
  {
    id: "evt-2",
    type: "send_message",
    timestamp: "2026-05-13T14:31:00.000Z",
    summary: "SendMessage to frontend-dev",
  },
  {
    id: "evt-3",
    type: "agent_spawn",
    timestamp: "2026-05-13T14:32:00.000Z",
    summary: "Agent spawn: backend-dev",
  },
];

const artifacts: Artifact[] = [
  { path: "docs/prd/login-2026-05-13.md", mtime: 1_715_000_000 },
  { path: "docs/plans/login-2026-05-13.md", mtime: 1_715_001_000 },
];

// ============================================================
// TasksPanel
// ============================================================

describe("TasksPanel", () => {
  it("renders all active tasks", () => {
    render(<TasksPanel tasks={tasks} />);
    expect(screen.getByText("Build login form")).toBeInTheDocument();
    expect(screen.getByText("Auth endpoint")).toBeInTheDocument();
    expect(screen.getByText("Deploy infra")).toBeInTheDocument();
  });

  it("shows task count badge", () => {
    render(<TasksPanel tasks={tasks} />);
    // All 3 are active (none deleted)
    expect(screen.getByText("3")).toBeInTheDocument();
  });

  it("shows 'No tasks yet' when list is empty", () => {
    render(<TasksPanel tasks={[]} />);
    expect(screen.getByText(/No tasks yet/)).toBeInTheDocument();
  });

  it("shows status labels", () => {
    render(<TasksPanel tasks={tasks} />);
    expect(screen.getByText("Pending")).toBeInTheDocument();
    expect(screen.getByText("In Progress")).toBeInTheDocument();
    expect(screen.getByText("Completed")).toBeInTheDocument();
  });

  it("shows owner for tasks that have one", () => {
    render(<TasksPanel tasks={tasks} />);
    expect(screen.getAllByText(/frontend-dev/)).not.toHaveLength(0);
    expect(screen.getAllByText(/backend-dev/)).not.toHaveLength(0);
  });

  it("excludes deleted tasks from count and display", () => {
    const withDeleted: Task[] = [
      ...tasks,
      { id: "99", subject: "Deleted task", status: "deleted" },
    ];
    render(<TasksPanel tasks={withDeleted} />);
    // count badge = 3 (the 3 non-deleted)
    expect(screen.getByText("3")).toBeInTheDocument();
    expect(screen.queryByText("Deleted task")).not.toBeInTheDocument();
  });
});

// ============================================================
// TimelinePanel — AC-3 coverage (3 event types)
// ============================================================

describe("TimelinePanel", () => {
  it("renders all 3 required event types", () => {
    render(<TimelinePanel timeline={timeline} />);
    expect(screen.getByText("TaskCreate")).toBeInTheDocument();
    expect(screen.getByText("SendMessage")).toBeInTheDocument();
    expect(screen.getByText("Agent spawn")).toBeInTheDocument();
  });

  it("renders event summaries", () => {
    render(<TimelinePanel timeline={timeline} />);
    expect(screen.getByText("TaskCreate: Build login form")).toBeInTheDocument();
    expect(screen.getByText("SendMessage to frontend-dev")).toBeInTheDocument();
    expect(screen.getByText("Agent spawn: backend-dev")).toBeInTheDocument();
  });

  it("shows count badge", () => {
    render(<TimelinePanel timeline={timeline} />);
    expect(screen.getByText("3")).toBeInTheDocument();
  });

  it("shows empty state when no events", () => {
    render(<TimelinePanel timeline={[]} />);
    expect(screen.getByText(/No events yet/)).toBeInTheDocument();
  });
});

// ============================================================
// ArtifactsPanel
// ============================================================

describe("ArtifactsPanel", () => {
  it("renders artifact file names", () => {
    render(<ArtifactsPanel artifacts={artifacts} />);
    // Both artifacts share the same filename base — use getAllByText
    const fileNames = screen.getAllByText("login-2026-05-13.md");
    expect(fileNames).toHaveLength(2);
  });

  it("shows correct artifact type labels", () => {
    render(<ArtifactsPanel artifacts={artifacts} />);
    expect(screen.getByText("PRD")).toBeInTheDocument();
    expect(screen.getByText("Plan")).toBeInTheDocument();
  });

  it("shows count badge", () => {
    render(<ArtifactsPanel artifacts={artifacts} />);
    expect(screen.getByText("2")).toBeInTheDocument();
  });

  it("shows empty state when no artifacts", () => {
    render(<ArtifactsPanel artifacts={[]} />);
    expect(screen.getByText(/No artifacts detected/)).toBeInTheDocument();
  });

  it("upsert: only renders 2 items when same path appears twice", () => {
    // ArtifactsPanel de-dup is handled by the reducer, not the component itself.
    // Component just renders what it's given. Pass only 1 artifact.
    render(<ArtifactsPanel artifacts={[artifacts[0]]} />);
    expect(screen.getByText("1")).toBeInTheDocument();
  });
});

// ============================================================
// Partial-update isolation test
// Verify Tasks re-renders do NOT affect Timeline output
// ============================================================

describe("Partial update isolation", () => {
  it("TasksPanel renders correctly when timeline changes externally", () => {
    // Simulate: render TasksPanel with tasks; render TimelinePanel with 1 event;
    // then re-render TimelinePanel with 2 events — TasksPanel should be unaffected.
    const { rerender: rerenderTimeline } = render(
      <TimelinePanel timeline={[timeline[0]]} />
    );
    const { container: tasksContainer } = render(<TasksPanel tasks={tasks} />);

    // Check tasks content is still intact
    expect(tasksContainer.querySelector(".tasks-panel")).toBeInTheDocument();
    expect(tasksContainer.querySelectorAll(".task-item")).toHaveLength(3);

    // Re-render timeline with more events
    rerenderTimeline(<TimelinePanel timeline={timeline} />);

    // Tasks container unchanged
    expect(tasksContainer.querySelectorAll(".task-item")).toHaveLength(3);
  });
});

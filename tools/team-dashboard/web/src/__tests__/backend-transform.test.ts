// ============================================================
// Integration tests — backend wire format → internal type transforms
// Tests the full pipeline: raw backend payload → applyBackendPayload → DashboardState
// Verifies contract against backend-dev's frozen spec
// ============================================================

import { describe, it, expect, beforeEach } from "vitest";
import {
  transformBackendTimelineEvent,
  applyBackendPayload,
  initialState,
} from "../sse";
import type {
  DashboardState,
  BackendTimelineEvent,
  BackendInitialPayload,
  SessionMeta,
  Task,
  Artifact,
} from "../types";

// ---- Fixtures: raw backend wire payloads ----

const mockMeta: SessionMeta = {
  session_id: "397df355-test",
  feature_desc: "Add login flow",
  lead: "product-lead",
  teammates: ["backend-dev", "frontend-dev"],
  started_at: "2026-05-13T14:30:00+08:00",
  worktree_path: "/path/to/repo",
};

const mockTask: Task = {
  id: "1",
  subject: "Build login form",
  status: "pending",
  owner: "frontend-dev",
};

const mockArtifact: Artifact = {
  path: "docs/prd/login-2026-05-13.md",
  mtime: 1_715_000_000,
};

const mockBackendTimeline: BackendTimelineEvent[] = [
  {
    event_type: "SendMessage",
    timestamp: "2026-05-13T14:31:00.000Z",
    summary: "SendMessage to frontend-dev: Begin login UI",
    details: { to: "frontend-dev" },
  },
  {
    event_type: "TaskCreate",
    timestamp: "2026-05-13T14:32:00.000Z",
    summary: "TaskCreate: Build login form",
    details: { task_id: "1", assignee: "frontend-dev" },
  },
  {
    event_type: "Agent",
    timestamp: "2026-05-13T14:33:00.000Z",
    summary: "Agent spawn: backend-dev",
    details: { agent_type: "backend-dev" },
  },
];

const mockBackendInitial: BackendInitialPayload = {
  meta: mockMeta,
  tasks: [mockTask],
  timeline: mockBackendTimeline,
  artifacts: [mockArtifact],
  worktree: [
    { path: "/worktrees/login-backend", head: "abc123", branch: "feature/login-backend" },
  ],
};

// ============================================================
// transformBackendTimelineEvent
// ============================================================

describe("transformBackendTimelineEvent — event_type mapping", () => {
  it('maps "SendMessage" → "send_message"', () => {
    const raw: BackendTimelineEvent = {
      event_type: "SendMessage",
      timestamp: "2026-05-13T14:31:00.000Z",
      summary: "Test",
    };
    const result = transformBackendTimelineEvent(raw);
    expect(result.type).toBe("send_message");
    expect(result.timestamp).toBe(raw.timestamp);
    expect(result.summary).toBe("Test");
    expect(result.id).toBeTruthy();
  });

  it('maps "TaskCreate" → "task_create"', () => {
    const raw: BackendTimelineEvent = {
      event_type: "TaskCreate",
      timestamp: "2026-05-13T14:32:00.000Z",
      summary: "TaskCreate: Build login form",
    };
    expect(transformBackendTimelineEvent(raw).type).toBe("task_create");
  });

  it('maps "TaskUpdate" → "task_update" (AC-3 extended)', () => {
    const raw: BackendTimelineEvent = {
      event_type: "TaskUpdate",
      timestamp: "2026-05-13T14:33:00.000Z",
      summary: "TaskUpdate: status → in_progress",
    };
    expect(transformBackendTimelineEvent(raw).type).toBe("task_update");
  });

  it('maps "Agent" → "agent_spawn"', () => {
    const raw: BackendTimelineEvent = {
      event_type: "Agent",
      timestamp: "2026-05-13T14:34:00.000Z",
      summary: "Agent spawn: backend-dev",
    };
    expect(transformBackendTimelineEvent(raw).type).toBe("agent_spawn");
  });

  it('maps "assistant" → "assistant_message"', () => {
    const raw: BackendTimelineEvent = {
      event_type: "assistant",
      timestamp: "2026-05-13T14:35:00.000Z",
      summary: "Assistant says: Done",
    };
    expect(transformBackendTimelineEvent(raw).type).toBe("assistant_message");
  });

  it("maps unknown event_type → 'unknown'", () => {
    const raw: BackendTimelineEvent = {
      event_type: "SomeFutureEventType",
      timestamp: "2026-05-13T14:36:00.000Z",
      summary: "Unknown event",
    };
    expect(transformBackendTimelineEvent(raw).type).toBe("unknown");
  });

  it("maps backend `details` → internal `detail`", () => {
    const raw: BackendTimelineEvent = {
      event_type: "SendMessage",
      timestamp: "2026-05-13T14:37:00.000Z",
      summary: "Test",
      details: { to: "frontend-dev", message_preview: "hello" },
    };
    const result = transformBackendTimelineEvent(raw);
    expect(result.detail).toEqual({ to: "frontend-dev", message_preview: "hello" });
  });

  it("generates unique IDs for two events with same timestamp", () => {
    const raw: BackendTimelineEvent = {
      event_type: "SendMessage",
      timestamp: "2026-05-13T14:38:00.000Z",
      summary: "A",
    };
    const id1 = transformBackendTimelineEvent(raw).id;
    const id2 = transformBackendTimelineEvent(raw).id;
    expect(id1).not.toBe(id2);
  });
});

// ============================================================
// task.update — backend sends { tasks: [...] }
// ============================================================

describe("applyBackendPayload — task.update", () => {
  let state: DashboardState;

  beforeEach(() => {
    state = applyBackendPayload(initialState, "initial", mockBackendInitial);
  });

  it("unwraps { tasks: [...] } and replaces task list", () => {
    const updatedTask: Task = { ...mockTask, status: "in_progress" };
    const next = applyBackendPayload(state, "task.update", { tasks: [updatedTask] });
    expect(next.tasks).toHaveLength(1);
    expect(next.tasks[0].status).toBe("in_progress");
  });

  it("also handles bare Task[] (backward compat fallback)", () => {
    const updatedTask: Task = { ...mockTask, status: "completed" };
    const next = applyBackendPayload(state, "task.update", [updatedTask]);
    expect(next.tasks[0].status).toBe("completed");
  });

  it("task.update does not affect timeline or artifacts", () => {
    const timelineBefore = state.timeline;
    const artifactsBefore = state.artifacts;
    const next = applyBackendPayload(state, "task.update", { tasks: [mockTask] });
    expect(next.timeline).toBe(timelineBefore);
    expect(next.artifacts).toBe(artifactsBefore);
  });
});

// ============================================================
// timeline.append — backend sends BackendTimelineEvent
// ============================================================

describe("applyBackendPayload — timeline.append", () => {
  let state: DashboardState;

  beforeEach(() => {
    state = applyBackendPayload(initialState, "initial", {
      ...mockBackendInitial,
      timeline: [],
    });
  });

  it("transforms BackendTimelineEvent and appends to timeline", () => {
    const raw: BackendTimelineEvent = {
      event_type: "SendMessage",
      timestamp: "2026-05-13T15:00:00.000Z",
      summary: "SendMessage to backend-dev",
      details: { to: "backend-dev" },
    };
    const next = applyBackendPayload(state, "timeline.append", raw);
    expect(next.timeline).toHaveLength(1);
    expect(next.timeline[0].type).toBe("send_message");
    expect(next.timeline[0].summary).toBe("SendMessage to backend-dev");
  });

  it("does not affect tasks or artifacts when timeline.append fires", () => {
    const tasksBefore = state.tasks;
    const artifactsBefore = state.artifacts;
    const raw: BackendTimelineEvent = {
      event_type: "TaskCreate",
      timestamp: "2026-05-13T15:01:00.000Z",
      summary: "TaskCreate: test",
    };
    const next = applyBackendPayload(state, "timeline.append", raw);
    expect(next.tasks).toBe(tasksBefore);
    expect(next.artifacts).toBe(artifactsBefore);
  });
});

// ============================================================
// worktree.status — backend sends { worktrees: [...] }
// ============================================================

describe("applyBackendPayload — worktree.status", () => {
  it("unwraps { worktrees: [...] } and replaces worktree list", () => {
    const next = applyBackendPayload(initialState, "worktree.status", {
      worktrees: [
        { path: "/repo/.worktrees/feat", head: "abc123", branch: "feature/feat" },
      ],
    });
    expect(next.worktree).toHaveLength(1);
    expect(next.worktree[0].branch).toBe("feature/feat");
    expect(next.worktree[0].head).toBe("abc123");
  });

  it("also handles bare WorktreeEntry[] (fallback)", () => {
    const next = applyBackendPayload(initialState, "worktree.status", [
      { path: "/repo", branch: "main", head: "def456" },
    ]);
    expect(next.worktree[0].branch).toBe("main");
  });
});

// ============================================================
// artifact.update — pass-through (shapes match)
// ============================================================

describe("applyBackendPayload — artifact.update", () => {
  it("passes through {path, mtime} correctly", () => {
    const next = applyBackendPayload(initialState, "artifact.update", {
      path: "docs/prd/login-2026-05-13.md",
      mtime: 1_715_000_000.0,
    });
    expect(next.artifacts).toHaveLength(1);
    expect(next.artifacts[0].path).toBe("docs/prd/login-2026-05-13.md");
    expect(next.artifacts[0].mtime).toBe(1_715_000_000.0);
  });

  it("upserts on second artifact.update for same path", () => {
    let state = applyBackendPayload(initialState, "artifact.update", {
      path: "docs/prd/foo.md",
      mtime: 1_000,
    });
    state = applyBackendPayload(state, "artifact.update", {
      path: "docs/prd/foo.md",
      mtime: 2_000,
    });
    expect(state.artifacts).toHaveLength(1);
    expect(state.artifacts[0].mtime).toBe(2_000);
  });
});

// ============================================================
// initial — full snapshot with timeline transform
// ============================================================

describe("applyBackendPayload — initial (full snapshot)", () => {
  it("processes initial payload and transforms timeline items", () => {
    const state = applyBackendPayload(initialState, "initial", mockBackendInitial);

    expect(state.meta?.feature_desc).toBe("Add login flow");
    expect(state.meta?.teammates).toEqual(["backend-dev", "frontend-dev"]);
    expect(state.tasks).toHaveLength(1);
    expect(state.artifacts).toHaveLength(1);
    expect(state.worktree).toHaveLength(1);

    // Timeline items are transformed
    expect(state.timeline).toHaveLength(3);
    expect(state.timeline[0].type).toBe("send_message");
    expect(state.timeline[1].type).toBe("task_create");
    expect(state.timeline[2].type).toBe("agent_spawn");

    // Each has an id
    state.timeline.forEach((ev) => {
      expect(ev.id).toBeTruthy();
    });

    expect(state.connectionState).toBe("open");
  });

  it("worktree entries have branch, path, head from backend", () => {
    const state = applyBackendPayload(initialState, "initial", mockBackendInitial);
    expect(state.worktree[0].branch).toBe("feature/login-backend");
    expect(state.worktree[0].path).toBe("/worktrees/login-backend");
    expect(state.worktree[0].head).toBe("abc123");
  });
});

// ============================================================
// AC-3 — 3 event types recognizable from backend wire format
// ============================================================

describe("AC-3: backend event_type → timeline rendering (3 required types)", () => {
  it("SendMessage, TaskCreate, Agent all appear via applyBackendPayload pipeline", () => {
    const events: BackendTimelineEvent[] = [
      { event_type: "SendMessage", timestamp: "2026-05-13T15:00:00.000Z", summary: "Msg A" },
      { event_type: "TaskCreate", timestamp: "2026-05-13T15:01:00.000Z", summary: "Task B" },
      { event_type: "Agent", timestamp: "2026-05-13T15:02:00.000Z", summary: "Spawn C" },
    ];

    let state: DashboardState = initialState;
    for (const ev of events) {
      state = applyBackendPayload(state, "timeline.append", ev);
    }

    expect(state.timeline.map((e) => e.type)).toEqual([
      "send_message",
      "task_create",
      "agent_spawn",
    ]);
  });
});

// ============================================================
// AC-9 — unparsed launch degradation via backend contract
// ============================================================

describe("AC-9: unparsed launch — backend sends (unparsed launch) meta", () => {
  it("gracefully handles feature_desc=(unparsed launch) and empty teammates", () => {
    const unparsedInitial: BackendInitialPayload = {
      ...mockBackendInitial,
      meta: {
        ...mockMeta,
        feature_desc: "(unparsed launch)",
        teammates: [],
      },
    };
    const state = applyBackendPayload(initialState, "initial", unparsedInitial);
    expect(state.meta?.feature_desc).toBe("(unparsed launch)");
    expect(state.meta?.teammates).toHaveLength(0);

    // task.update still works
    const next = applyBackendPayload(state, "task.update", { tasks: [mockTask] });
    expect(next.tasks).toHaveLength(1);
  });
});

// ============================================================
// SessionMeta contract compliance (spec §7)
// ============================================================

describe("SessionMeta from initial payload", () => {
  it("matches backend-dev frozen SessionMeta shape exactly", () => {
    const state = applyBackendPayload(initialState, "initial", mockBackendInitial);
    const meta = state.meta!;

    expect(typeof meta.session_id).toBe("string");
    expect(typeof meta.feature_desc).toBe("string");
    expect(typeof meta.lead).toBe("string");
    expect(Array.isArray(meta.teammates)).toBe(true);
    expect(typeof meta.started_at).toBe("string");
    expect(typeof meta.worktree_path).toBe("string");

    expect(meta.session_id).toBe("397df355-test");
    expect(meta.lead).toBe("product-lead");
  });
});

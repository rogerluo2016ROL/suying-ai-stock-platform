// ============================================================
// Unit tests for the SSE reducer / applySSEEvent helper
// Tests pure state transformations — no EventSource required.
// ============================================================

import { describe, it, expect } from "vitest";
import { applySSEEvent, initialState, buildSSEUrl } from "../sse";
import type {
  DashboardState,
  SSEEvent,
  Task,
  TimelineEvent,
  Artifact,
  WorktreeEntry,
  SessionMeta,
  InitialPayload,
} from "../types";

// ---- Fixtures ----

const mockMeta: SessionMeta = {
  session_id: "01HXX-test-session",
  feature_desc: "Add login flow",
  lead: "product-lead",
  teammates: ["backend-dev", "frontend-dev"],
  started_at: "2026-05-13T14:30:00+08:00",
  worktree_path: "/path/to/worktree",
};

const mockTask1: Task = {
  id: "1",
  subject: "Build login form",
  status: "pending",
  owner: "frontend-dev",
};

const mockTask2: Task = {
  id: "2",
  subject: "Implement auth endpoint",
  status: "in_progress",
  owner: "backend-dev",
};

const mockTimelineEvent1: TimelineEvent = {
  id: "evt-001",
  type: "task_create",
  timestamp: "2026-05-13T14:31:00.000Z",
  summary: "TaskCreate: Build login form → frontend-dev",
};

const mockTimelineEvent2: TimelineEvent = {
  id: "evt-002",
  type: "send_message",
  timestamp: "2026-05-13T14:32:00.000Z",
  summary: "SendMessage to frontend-dev: Begin login UI",
};

const mockTimelineEvent3: TimelineEvent = {
  id: "evt-003",
  type: "agent_spawn",
  timestamp: "2026-05-13T14:33:00.000Z",
  summary: "Agent spawn: frontend-dev",
};

const mockArtifact1: Artifact = {
  path: "docs/prd/login-2026-05-13.md",
  mtime: 1_715_000_000,
};

const mockArtifact2: Artifact = {
  path: "docs/plans/login-2026-05-13.md",
  mtime: 1_715_001_000,
};

const mockWorktree: WorktreeEntry[] = [
  { path: "/worktrees/login-backend", branch: "feature/login-backend" },
  { path: "/worktrees/login-frontend", branch: "feature/login-frontend" },
];

const mockInitialPayload: InitialPayload = {
  meta: mockMeta,
  tasks: [mockTask1, mockTask2],
  timeline: [mockTimelineEvent1, mockTimelineEvent2, mockTimelineEvent3],
  artifacts: [mockArtifact1],
  worktree: mockWorktree,
};

// ============================================================
// initial event
// ============================================================

describe("applySSEEvent — initial", () => {
  it("replaces entire state with snapshot", () => {
    const event: SSEEvent = {
      type: "initial",
      payload: mockInitialPayload,
    };
    const next = applySSEEvent(initialState, event);

    expect(next.meta).toEqual(mockMeta);
    expect(next.tasks).toHaveLength(2);
    expect(next.tasks[0]).toEqual(mockTask1);
    expect(next.timeline).toHaveLength(3);
    expect(next.artifacts).toHaveLength(1);
    expect(next.worktree).toHaveLength(2);
    expect(next.connectionState).toBe("open");
  });

  it("overwrites previous state on re-connect", () => {
    // Simulate state that already had some data
    const priorState: DashboardState = {
      ...initialState,
      tasks: [{ id: "stale", subject: "Stale task", status: "pending" }],
      timeline: [mockTimelineEvent1],
    };
    const event: SSEEvent = {
      type: "initial",
      payload: { ...mockInitialPayload, tasks: [mockTask2] },
    };
    const next = applySSEEvent(priorState, event);
    expect(next.tasks).toHaveLength(1);
    expect(next.tasks[0].id).toBe("2");
  });
});

// ============================================================
// task.update
// ============================================================

describe("applySSEEvent — task.update", () => {
  it("replaces the full task list", () => {
    const afterInitial = applySSEEvent(initialState, {
      type: "initial",
      payload: mockInitialPayload,
    });

    const updatedTask2: Task = { ...mockTask2, status: "completed" };
    const event: SSEEvent = {
      type: "task.update",
      payload: [mockTask1, updatedTask2],
    };
    const next = applySSEEvent(afterInitial, event);

    expect(next.tasks).toHaveLength(2);
    expect(next.tasks[1].status).toBe("completed");
    // Timeline should be unchanged
    expect(next.timeline).toHaveLength(3);
    // Artifacts should be unchanged
    expect(next.artifacts).toHaveLength(1);
  });

  it("does not mutate prior state", () => {
    const prior = applySSEEvent(initialState, {
      type: "initial",
      payload: mockInitialPayload,
    });
    applySSEEvent(prior, {
      type: "task.update",
      payload: [mockTask2],
    });
    // prior.tasks is still 2 tasks
    expect(prior.tasks).toHaveLength(2);
  });
});

// ============================================================
// timeline.append
// ============================================================

describe("applySSEEvent — timeline.append", () => {
  it("appends a single event to the timeline", () => {
    const afterInitial = applySSEEvent(initialState, {
      type: "initial",
      payload: { ...mockInitialPayload, timeline: [mockTimelineEvent1] },
    });
    expect(afterInitial.timeline).toHaveLength(1);

    const newEvent: TimelineEvent = {
      id: "evt-new",
      type: "send_message",
      timestamp: "2026-05-13T14:40:00.000Z",
      summary: "SendMessage to backend-dev",
    };
    const next = applySSEEvent(afterInitial, {
      type: "timeline.append",
      payload: newEvent,
    });

    expect(next.timeline).toHaveLength(2);
    expect(next.timeline[1]).toEqual(newEvent);
  });

  it("does not modify Tasks or Artifacts when timeline.append fires", () => {
    const afterInitial = applySSEEvent(initialState, {
      type: "initial",
      payload: mockInitialPayload,
    });
    const tasksBefore = afterInitial.tasks;
    const artifactsBefore = afterInitial.artifacts;

    const next = applySSEEvent(afterInitial, {
      type: "timeline.append",
      payload: mockTimelineEvent2,
    });

    // Reference equality — tasks + artifacts arrays were NOT replaced
    expect(next.tasks).toBe(tasksBefore);
    expect(next.artifacts).toBe(artifactsBefore);
  });
});

// ============================================================
// artifact.update
// ============================================================

describe("applySSEEvent — artifact.update", () => {
  it("adds a new artifact if path not yet known", () => {
    const afterInitial = applySSEEvent(initialState, {
      type: "initial",
      payload: { ...mockInitialPayload, artifacts: [mockArtifact1] },
    });

    const next = applySSEEvent(afterInitial, {
      type: "artifact.update",
      payload: mockArtifact2,
    });

    expect(next.artifacts).toHaveLength(2);
    expect(next.artifacts.find((a) => a.path === mockArtifact2.path)).toBeDefined();
  });

  it("updates mtime for an existing artifact (upsert)", () => {
    const afterInitial = applySSEEvent(initialState, {
      type: "initial",
      payload: { ...mockInitialPayload, artifacts: [mockArtifact1] },
    });

    const updatedArtifact: Artifact = {
      ...mockArtifact1,
      mtime: 1_715_999_999,
    };
    const next = applySSEEvent(afterInitial, {
      type: "artifact.update",
      payload: updatedArtifact,
    });

    expect(next.artifacts).toHaveLength(1);
    expect(next.artifacts[0].mtime).toBe(1_715_999_999);
  });

  it("does not modify Tasks or Timeline when artifact.update fires", () => {
    const afterInitial = applySSEEvent(initialState, {
      type: "initial",
      payload: mockInitialPayload,
    });
    const tasksBefore = afterInitial.tasks;
    const timelineBefore = afterInitial.timeline;

    const next = applySSEEvent(afterInitial, {
      type: "artifact.update",
      payload: mockArtifact2,
    });

    expect(next.tasks).toBe(tasksBefore);
    expect(next.timeline).toBe(timelineBefore);
  });
});

// ============================================================
// worktree.status
// ============================================================

describe("applySSEEvent — worktree.status", () => {
  it("replaces the worktree list", () => {
    const afterInitial = applySSEEvent(initialState, {
      type: "initial",
      payload: mockInitialPayload,
    });

    const newWorktrees: WorktreeEntry[] = [
      { path: "/worktrees/new", branch: "feature/new" },
    ];
    const next = applySSEEvent(afterInitial, {
      type: "worktree.status",
      payload: newWorktrees,
    });

    expect(next.worktree).toHaveLength(1);
    expect(next.worktree[0].branch).toBe("feature/new");
  });
});

// ============================================================
// Timeline event types (AC-3: 3 event types recognizable)
// ============================================================

describe("Timeline event types — AC-3 verification", () => {
  const types = ["send_message", "task_create", "agent_spawn"] as const;

  it("each of the 3 required event types can appear in timeline", () => {
    let state: DashboardState = applySSEEvent(initialState, {
      type: "initial",
      payload: { ...mockInitialPayload, timeline: [] },
    });

    for (const evType of types) {
      const ev: TimelineEvent = {
        id: `test-${evType}`,
        type: evType,
        timestamp: new Date().toISOString(),
        summary: `Test ${evType}`,
      };
      state = applySSEEvent(state, { type: "timeline.append", payload: ev });
    }

    expect(state.timeline).toHaveLength(3);
    expect(state.timeline.map((e) => e.type)).toEqual([
      "send_message",
      "task_create",
      "agent_spawn",
    ]);
  });
});

// ============================================================
// buildSSEUrl helper
// ============================================================

describe("buildSSEUrl", () => {
  it("builds the correct URL with a session ID", () => {
    const url = buildSSEUrl("abc123", "http://localhost:8765");
    expect(url).toBe("http://localhost:8765/events/abc123");
  });

  it("URL-encodes the session ID", () => {
    const url = buildSSEUrl("sid with space", "http://localhost:8765");
    expect(url).toBe("http://localhost:8765/events/sid%20with%20space");
  });
});

// ============================================================
// AC-9: unparsed launch fallback
// ============================================================

describe("AC-9: unparsed launch graceful degradation", () => {
  it("tasks update works even when meta.feature_desc is unparsed", () => {
    const unParsedMeta: SessionMeta = {
      ...mockMeta,
      feature_desc: "(unparsed launch)",
      teammates: [],
    };
    const state = applySSEEvent(initialState, {
      type: "initial",
      payload: {
        ...mockInitialPayload,
        meta: unParsedMeta,
        tasks: [],
        timeline: [],
      },
    });

    // Tasks update should still work
    const next = applySSEEvent(state, {
      type: "task.update",
      payload: [mockTask1],
    });

    expect(next.meta?.feature_desc).toBe("(unparsed launch)");
    expect(next.tasks).toHaveLength(1);
  });
});

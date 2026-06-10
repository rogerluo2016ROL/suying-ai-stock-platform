// ============================================================
// Team Dashboard — TypeScript types
// Section A: Internal app types (used by reducer + components)
// Section B: Backend wire types (raw shapes from server)
// ============================================================

// ============================================================
// A. Internal types
// ============================================================

export interface SessionMeta {
  session_id: string;
  feature_desc: string;
  lead: string;
  teammates: string[];
  started_at: string;
  worktree_path: string;
}

// ---- Task types (mirrors ~/.claude/tasks/*.json) ----

export type TaskStatus = "pending" | "in_progress" | "completed" | "deleted";

export interface Task {
  id: string;
  subject: string;
  status: TaskStatus;
  owner?: string;
  description?: string;
  activeForm?: string;
  blockedBy?: string[];
  blocks?: string[];
  metadata?: Record<string, unknown>;
}

// ---- Timeline event (internal, after transform from backend wire format) ----

export type TimelineEventType =
  | "send_message"   // backend: "SendMessage"
  | "task_create"    // backend: "TaskCreate"
  | "task_update"    // backend: "TaskUpdate"
  | "agent_spawn"    // backend: "Agent"
  | "assistant_message" // backend: "assistant"
  | "unknown";

export interface TimelineEvent {
  /** Client-generated stable key for React rendering */
  id: string;
  type: TimelineEventType;
  timestamp: string;
  summary: string;
  detail?: Record<string, unknown>;
}

// ---- Artifact ----

export interface Artifact {
  path: string;
  mtime: number;
}

// ---- Worktree (internal) ----

export interface WorktreeEntry {
  path: string;
  branch: string;
  head?: string;
  bare?: boolean;
}

// ---- Dashboard state (returned by useDashboardStream) ----

export type ConnectionState =
  | "connecting"
  | "open"
  | "reconnecting"
  | "closed";

export interface DashboardState {
  meta: SessionMeta | null;
  tasks: Task[];
  timeline: TimelineEvent[];
  artifacts: Artifact[];
  worktree: WorktreeEntry[];
  connectionState: ConnectionState;
}

// ---- Internal SSE event map (used by pure reducer / applySSEEvent) ----

export interface InitialPayload {
  meta: SessionMeta;
  tasks: Task[];
  timeline: TimelineEvent[];
  artifacts: Artifact[];
  worktree: WorktreeEntry[];
}

export interface SSEEventMap {
  initial: InitialPayload;
  "task.update": Task[];
  "timeline.append": TimelineEvent;
  "artifact.update": Artifact;
  "worktree.status": WorktreeEntry[];
}

export type SSEEventType = keyof SSEEventMap;

export interface SSEEvent<T extends SSEEventType = SSEEventType> {
  type: T;
  payload: SSEEventMap[T];
}

// ============================================================
// B. Backend wire types — raw shapes from FastAPI server
//    These are what actually arrive over the SSE stream.
//    Transform to internal types before dispatching to reducer.
// ============================================================

/**
 * Raw timeline event as sent by backend transcript_parser.
 * Backend `event_type` strings map to internal `TimelineEventType`.
 */
export interface BackendTimelineEvent {
  event_type: "SendMessage" | "TaskCreate" | "TaskUpdate" | "Agent" | "assistant" | string;
  timestamp: string;
  summary: string;
  details?: Record<string, unknown>;
}

/**
 * Raw task.update payload from backend: { "tasks": [...] }
 */
export interface BackendTaskUpdatePayload {
  tasks: Task[];
}

/**
 * Backend worktree entry shape: { path, head, branch }
 */
export interface BackendWorktreeEntry {
  path: string;
  head: string;
  branch: string;
}

/**
 * Raw worktree.status payload: { "worktrees": [...] }
 */
export interface BackendWorktreeStatusPayload {
  worktrees: BackendWorktreeEntry[];
}

/**
 * Raw initial payload from backend (timeline items use BackendTimelineEvent format).
 */
export interface BackendInitialPayload {
  meta: SessionMeta;
  tasks: Task[];
  /** Timeline items in raw backend format — need transform */
  timeline: BackendTimelineEvent[];
  artifacts: Artifact[];
  /** Worktree entries in backend format */
  worktree: BackendWorktreeEntry[];
}

/**
 * Full SSE envelope as sent by the backend.
 * The server may send either:
 *   1. Full envelope:  data: {"type":"task.update","payload":{...}}
 *   2. Named event:    event: task.update\ndata: {"tasks":[...]}
 * The SSE adapter handles both.
 */
export interface BackendSSEEnvelope {
  type: SSEEventType;
  payload: unknown;
}

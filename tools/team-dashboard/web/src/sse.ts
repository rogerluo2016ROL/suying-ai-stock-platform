// ============================================================
// Team Dashboard — SSE wrapper + useDashboardStream hook
// Encapsulates browser EventSource with:
//   • initial vs delta distinction
//   • auto-reconnect on disconnect (exponential backoff)
//   • local state patching per event type
//   • backend wire-format → internal type transformation
// ============================================================

import { useEffect, useReducer, useRef, useCallback } from "react";
import type {
  DashboardState,
  SSEEvent,
  SSEEventType,
  ConnectionState,
  Task,
  TimelineEvent,
  TimelineEventType,
  Artifact,
  WorktreeEntry,
  InitialPayload,
  BackendTimelineEvent,
  BackendTaskUpdatePayload,
  BackendWorktreeStatusPayload,
  BackendInitialPayload,
  BackendSSEEnvelope,
} from "./types";

// ------------------------------------------------------------------
// State & reducer
// ------------------------------------------------------------------

const initialState: DashboardState = {
  meta: null,
  tasks: [],
  timeline: [],
  artifacts: [],
  worktree: [],
  connectionState: "connecting",
};

type Action =
  | { type: "SET_CONNECTION"; state: ConnectionState }
  | { type: "INITIAL"; payload: InitialPayload }
  | { type: "TASK_UPDATE"; payload: Task[] }
  | { type: "TIMELINE_APPEND"; payload: TimelineEvent }
  | { type: "ARTIFACT_UPDATE"; payload: Artifact }
  | { type: "WORKTREE_STATUS"; payload: WorktreeEntry[] };

function reducer(state: DashboardState, action: Action): DashboardState {
  switch (action.type) {
    case "SET_CONNECTION":
      return { ...state, connectionState: action.state };

    case "INITIAL":
      // Full snapshot — replace everything (handles browser refresh)
      return {
        meta: action.payload.meta,
        tasks: action.payload.tasks,
        timeline: action.payload.timeline,
        artifacts: action.payload.artifacts,
        worktree: action.payload.worktree,
        connectionState: "open",
      };

    case "TASK_UPDATE":
      // Replace entire task list (server sends the full updated list)
      return { ...state, tasks: action.payload };

    case "TIMELINE_APPEND":
      // Append single event — keep insertion order (server sends sorted)
      return {
        ...state,
        timeline: [...state.timeline, action.payload],
      };

    case "ARTIFACT_UPDATE": {
      // Upsert by path
      const idx = state.artifacts.findIndex(
        (a) => a.path === action.payload.path
      );
      const newArtifacts =
        idx >= 0
          ? state.artifacts.map((a, i) => (i === idx ? action.payload : a))
          : [...state.artifacts, action.payload];
      return { ...state, artifacts: newArtifacts };
    }

    case "WORKTREE_STATUS":
      return { ...state, worktree: action.payload };

    default:
      return state;
  }
}

// ------------------------------------------------------------------
// Backend wire-format → internal type transforms
// ------------------------------------------------------------------

/** Maps backend event_type strings to internal TimelineEventType */
const BACKEND_EVENT_TYPE_MAP: Record<string, TimelineEventType> = {
  SendMessage: "send_message",
  TaskCreate: "task_create",
  TaskUpdate: "task_update",
  Agent: "agent_spawn",
  assistant: "assistant_message",
};

/** Monotonic counter to ensure unique timeline event IDs */
let _timelineIdCounter = 0;

/**
 * Transform a raw backend timeline event → internal TimelineEvent.
 * Exported for unit testing.
 */
export function transformBackendTimelineEvent(
  raw: BackendTimelineEvent
): TimelineEvent {
  const type: TimelineEventType =
    BACKEND_EVENT_TYPE_MAP[raw.event_type] ?? "unknown";
  return {
    id: `${raw.timestamp}-${raw.event_type}-${++_timelineIdCounter}`,
    type,
    timestamp: raw.timestamp,
    summary: raw.summary,
    detail: raw.details,
  };
}

/**
 * Transform a raw BackendInitialPayload → internal InitialPayload.
 */
function transformInitialPayload(raw: BackendInitialPayload): InitialPayload {
  return {
    meta: raw.meta,
    tasks: raw.tasks,
    timeline: raw.timeline.map(transformBackendTimelineEvent),
    artifacts: raw.artifacts,
    worktree: raw.worktree.map((w) => ({
      path: w.path,
      branch: w.branch,
      head: w.head,
    })),
  };
}

/**
 * Normalise a raw backend payload into the internal shape for each event type.
 * Handles:
 *   - task.update:     {tasks: [...]}  →  Task[]
 *   - timeline.append: BackendTimelineEvent  →  TimelineEvent
 *   - worktree.status: {worktrees: [...]}  →  WorktreeEntry[]
 *   - initial:         BackendInitialPayload  →  InitialPayload (with timeline transform)
 *   - artifact.update: pass-through (shapes match)
 */
function transformPayload(
  eventType: SSEEventType,
  rawPayload: unknown
): unknown {
  switch (eventType) {
    case "initial": {
      const raw = rawPayload as BackendInitialPayload;
      return transformInitialPayload(raw);
    }
    case "task.update": {
      // Backend sends { tasks: [...] }
      const raw = rawPayload as BackendTaskUpdatePayload | Task[];
      return Array.isArray(raw) ? raw : raw.tasks ?? [];
    }
    case "timeline.append": {
      const raw = rawPayload as BackendTimelineEvent;
      return transformBackendTimelineEvent(raw);
    }
    case "artifact.update":
      // Backend shape {path, mtime} matches internal Artifact — pass through
      return rawPayload as Artifact;
    case "worktree.status": {
      // Backend sends { worktrees: [...] }
      const raw = rawPayload as BackendWorktreeStatusPayload | WorktreeEntry[];
      const list = Array.isArray(raw) ? raw : (raw.worktrees ?? []);
      return list.map((w: WorktreeEntry & { head?: string }) => ({
        path: w.path,
        branch: w.branch,
        head: w.head,
      }));
    }
    default:
      return rawPayload;
  }
}

// ------------------------------------------------------------------
// SSE URL builder
// ------------------------------------------------------------------

export function buildSSEUrl(sid: string, baseUrl?: string): string {
  const base =
    baseUrl ?? (typeof window !== "undefined" ? "" : "http://localhost:8765");
  return `${base}/events/${encodeURIComponent(sid)}`;
}

// ------------------------------------------------------------------
// useDashboardStream
// ------------------------------------------------------------------

export const RECONNECT_DELAY_MS = 3_000;
export const MAX_RECONNECT_DELAY_MS = 30_000;

export interface UseDashboardStreamOptions {
  /** Override the backend base URL (defaults to same-origin / Vite proxy). */
  baseUrl?: string;
  /** Override initial reconnect delay for testing. */
  reconnectDelayMs?: number;
}

export function useDashboardStream(
  sid: string | null,
  options: UseDashboardStreamOptions = {}
): DashboardState {
  const [state, dispatch] = useReducer(reducer, initialState);
  const esRef = useRef<EventSource | null>(null);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const reconnectDelayRef = useRef(
    options.reconnectDelayMs ?? RECONNECT_DELAY_MS
  );
  const mountedRef = useRef(true);

  const applyEvent = useCallback(
    (eventType: SSEEventType, rawPayload: unknown) => {
      if (!mountedRef.current) return;
      const payload = transformPayload(eventType, rawPayload);
      switch (eventType) {
        case "initial":
          dispatch({ type: "INITIAL", payload: payload as InitialPayload });
          break;
        case "task.update":
          dispatch({ type: "TASK_UPDATE", payload: payload as Task[] });
          break;
        case "timeline.append":
          dispatch({
            type: "TIMELINE_APPEND",
            payload: payload as TimelineEvent,
          });
          break;
        case "artifact.update":
          dispatch({ type: "ARTIFACT_UPDATE", payload: payload as Artifact });
          break;
        case "worktree.status":
          dispatch({
            type: "WORKTREE_STATUS",
            payload: payload as WorktreeEntry[],
          });
          break;
        default:
          // Unknown type — silently ignore (spec §8)
          break;
      }
    },
    []
  );

  /**
   * Parse raw SSE data and dispatch the right action.
   *
   * Handles two server formats:
   *   1. Full envelope:  data: {"type":"task.update","payload":{"tasks":[...]}}
   *   2. Named event:    event: task.update  →  data: {"tasks":[...]}
   *      (knownType comes from the addEventListener("task.update") callback)
   */
  const handleRawMessage = useCallback(
    (data: string, knownType?: SSEEventType) => {
      if (!mountedRef.current) return;
      try {
        const parsed = JSON.parse(data) as Record<string, unknown>;

        // Full envelope: has both "type" and "payload" keys
        if ("payload" in parsed && "type" in parsed) {
          const envelope = parsed as unknown as BackendSSEEnvelope;
          const evType = (knownType ?? envelope.type) as SSEEventType;
          applyEvent(evType, envelope.payload);
          return;
        }

        // Named event — `parsed` IS the raw payload
        if (knownType) {
          applyEvent(knownType, parsed);
          return;
        }

        // Fallback: might be a bare envelope without `payload` key (shouldn't happen)
        if ("type" in parsed) {
          applyEvent(parsed.type as SSEEventType, parsed);
        }
      } catch {
        // Malformed JSON — ignore
      }
    },
    [applyEvent]
  );

  const connect = useCallback(
    (sessionId: string) => {
      if (!mountedRef.current) return;

      // Clean up any existing connection
      if (esRef.current) {
        esRef.current.close();
        esRef.current = null;
      }

      dispatch({ type: "SET_CONNECTION", state: "connecting" });

      const url = buildSSEUrl(sessionId, options.baseUrl);
      const es = new EventSource(url);
      esRef.current = es;

      // Handle unnamed messages (full envelope format)
      es.onmessage = (ev: MessageEvent<string>) => {
        handleRawMessage(ev.data);
      };

      // Handle named event types (named event format)
      const namedTypes: SSEEventType[] = [
        "initial",
        "task.update",
        "timeline.append",
        "artifact.update",
        "worktree.status",
      ];
      namedTypes.forEach((eventType) => {
        es.addEventListener(eventType, (ev: Event) => {
          const msgEv = ev as MessageEvent<string>;
          handleRawMessage(msgEv.data, eventType);
        });
      });

      es.onopen = () => {
        if (!mountedRef.current) return;
        reconnectDelayRef.current =
          options.reconnectDelayMs ?? RECONNECT_DELAY_MS;
        dispatch({ type: "SET_CONNECTION", state: "open" });
      };

      es.onerror = () => {
        if (!mountedRef.current) return;
        es.close();
        esRef.current = null;
        dispatch({ type: "SET_CONNECTION", state: "reconnecting" });

        const delay = reconnectDelayRef.current;
        reconnectDelayRef.current = Math.min(delay * 2, MAX_RECONNECT_DELAY_MS);

        reconnectTimerRef.current = setTimeout(() => {
          if (mountedRef.current) connect(sessionId);
        }, delay);
      };
    },
    [options.baseUrl, options.reconnectDelayMs, handleRawMessage]
  );

  useEffect(() => {
    mountedRef.current = true;

    if (!sid) {
      dispatch({ type: "SET_CONNECTION", state: "closed" });
      return;
    }

    connect(sid);

    return () => {
      mountedRef.current = false;
      if (reconnectTimerRef.current) {
        clearTimeout(reconnectTimerRef.current);
        reconnectTimerRef.current = null;
      }
      if (esRef.current) {
        esRef.current.close();
        esRef.current = null;
      }
    };
  }, [sid, connect]);

  return state;
}

// ------------------------------------------------------------------
// Pure helpers exported for testing
// ------------------------------------------------------------------

/**
 * Apply a single internal-format SSE event to state (pure, reducer-level).
 * Used by unit tests that work with internal types directly.
 */
export function applySSEEvent(
  state: DashboardState,
  event: SSEEvent
): DashboardState {
  return reducer(state, eventToAction(event));
}

/**
 * Apply a raw backend-format payload to state (transform + reduce).
 * Used by integration tests that verify the full pipeline.
 */
export function applyBackendPayload(
  state: DashboardState,
  eventType: SSEEventType,
  rawPayload: unknown
): DashboardState {
  const payload = transformPayload(eventType, rawPayload);
  const mockEvent: SSEEvent = {
    type: eventType,
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    payload: payload as any,
  };
  return reducer(state, eventToAction(mockEvent));
}

function eventToAction(event: SSEEvent): Action {
  switch (event.type) {
    case "initial":
      return { type: "INITIAL", payload: event.payload as InitialPayload };
    case "task.update":
      return { type: "TASK_UPDATE", payload: event.payload as Task[] };
    case "timeline.append":
      return {
        type: "TIMELINE_APPEND",
        payload: event.payload as TimelineEvent,
      };
    case "artifact.update":
      return { type: "ARTIFACT_UPDATE", payload: event.payload as Artifact };
    case "worktree.status":
      return {
        type: "WORKTREE_STATUS",
        payload: event.payload as WorktreeEntry[],
      };
    default:
      return { type: "SET_CONNECTION", state: "open" }; // no-op
  }
}

export { initialState };

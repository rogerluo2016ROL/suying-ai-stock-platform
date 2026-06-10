// ============================================================
// TimelinePanel — chronological event stream
// Uses a bottom-scroll-preserve technique: new items append
// at the bottom but the panel scroll position is preserved.
// Only re-renders when `timeline` prop reference changes.
// ============================================================

import { memo, useEffect, useRef } from "react";
import type { TimelineEvent, TimelineEventType } from "../types";

interface TimelinePanelProps {
  timeline: TimelineEvent[];
}

const EVENT_ICON: Record<TimelineEventType, string> = {
  send_message: "💬",
  task_create: "📋",
  task_update: "✏️",
  agent_spawn: "🤖",
  assistant_message: "🗣",
  unknown: "❓",
};

const EVENT_LABEL: Record<TimelineEventType, string> = {
  send_message: "SendMessage",
  task_create: "TaskCreate",
  task_update: "TaskUpdate",
  agent_spawn: "Agent spawn",
  assistant_message: "Assistant",
  unknown: "Unknown",
};

function formatTime(iso: string): string {
  try {
    return new Date(iso).toLocaleTimeString([], {
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    });
  } catch {
    return iso;
  }
}

function TimelineItem({ event }: { event: TimelineEvent }) {
  return (
    <article
      className={`timeline-item timeline-${event.type}`}
      aria-label={`${EVENT_LABEL[event.type]} event`}
    >
      <span className="timeline-icon" aria-hidden="true">
        {EVENT_ICON[event.type]}
      </span>
      <div className="timeline-body">
        <span className="timeline-type">{EVENT_LABEL[event.type]}</span>
        <span className="timeline-summary">{event.summary}</span>
      </div>
      <time className="timeline-time" dateTime={event.timestamp}>
        {formatTime(event.timestamp)}
      </time>
    </article>
  );
}

function TimelinePanel({ timeline }: TimelinePanelProps) {
  const listRef = useRef<HTMLUListElement>(null);
  const prevLenRef = useRef(timeline.length);
  const isAtBottomRef = useRef(true);

  // Track scroll position to decide whether to auto-scroll
  const handleScroll = () => {
    const el = listRef.current;
    if (!el) return;
    const { scrollTop, scrollHeight, clientHeight } = el;
    isAtBottomRef.current = scrollHeight - scrollTop - clientHeight < 40;
  };

  // Auto-scroll to bottom when new events arrive (if already at bottom)
  useEffect(() => {
    const el = listRef.current;
    if (!el) return;
    if (timeline.length > prevLenRef.current && isAtBottomRef.current) {
      el.scrollTop = el.scrollHeight;
    }
    prevLenRef.current = timeline.length;
  }, [timeline]);

  return (
    <section className="panel timeline-panel" aria-label="Timeline">
      <h2 className="panel-title">
        Timeline
        <span className="panel-badge">{timeline.length}</span>
      </h2>
      {timeline.length === 0 ? (
        <p className="panel-empty">No events yet…</p>
      ) : (
        <ul
          ref={listRef}
          className="timeline-list"
          role="list"
          onScroll={handleScroll}
        >
          {timeline.map((event) => (
            <li key={event.id}>
              <TimelineItem event={event} />
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

export default memo(TimelinePanel);

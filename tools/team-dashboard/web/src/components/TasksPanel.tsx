// ============================================================
// TasksPanel — displays the current task list
// Only re-renders when `tasks` prop reference changes.
// ============================================================

import { memo } from "react";
import type { Task, TaskStatus } from "../types";

interface TasksPanelProps {
  tasks: Task[];
}

const STATUS_LABEL: Record<TaskStatus, string> = {
  pending: "Pending",
  in_progress: "In Progress",
  completed: "Completed",
  deleted: "Deleted",
};

const STATUS_CLASS: Record<TaskStatus, string> = {
  pending: "status-pending",
  in_progress: "status-in-progress",
  completed: "status-completed",
  deleted: "status-deleted",
};

function TaskItem({ task }: { task: Task }) {
  return (
    <article className="task-item" aria-label={`Task: ${task.subject}`}>
      <header className="task-header">
        <span className={`task-status ${STATUS_CLASS[task.status]}`}>
          {STATUS_LABEL[task.status]}
        </span>
        <span className="task-id">#{task.id}</span>
      </header>
      <p className="task-subject">{task.subject}</p>
      {task.owner && (
        <p className="task-owner">
          <span aria-label="Assigned to">@</span>
          {task.owner}
        </p>
      )}
      {task.activeForm && (
        <p className="task-active-form">{task.activeForm}</p>
      )}
      {task.blockedBy && task.blockedBy.length > 0 && (
        <p className="task-blocked">
          Blocked by: {task.blockedBy.join(", ")}
        </p>
      )}
    </article>
  );
}

function TasksPanel({ tasks }: TasksPanelProps) {
  const activeTasks = tasks.filter((t) => t.status !== "deleted");
  const sorted = [...activeTasks].sort((a, b) => {
    // In-progress first, then pending, then completed
    const order: Record<TaskStatus, number> = {
      in_progress: 0,
      pending: 1,
      completed: 2,
      deleted: 3,
    };
    return order[a.status] - order[b.status];
  });

  return (
    <section className="panel tasks-panel" aria-label="Tasks">
      <h2 className="panel-title">
        Tasks
        <span className="panel-badge">{activeTasks.length}</span>
      </h2>
      {sorted.length === 0 ? (
        <p className="panel-empty">No tasks yet…</p>
      ) : (
        <ul className="task-list" role="list">
          {sorted.map((task) => (
            <li key={task.id}>
              <TaskItem task={task} />
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

export default memo(TasksPanel);

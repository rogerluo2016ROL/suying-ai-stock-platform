// ============================================================
// ArtifactsPanel — lists docs/ artifacts with path + mtime
// Only re-renders when `artifacts` prop reference changes.
// ============================================================

import { memo } from "react";
import type { Artifact } from "../types";

interface ArtifactsPanelProps {
  artifacts: Artifact[];
}

function formatMtime(mtime: number): string {
  if (!mtime) return "—";
  try {
    return new Date(mtime * 1000).toLocaleString([], {
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return String(mtime);
  }
}

function fileType(path: string): string {
  if (path.includes("/prd/")) return "PRD";
  if (path.includes("/plans/")) return "Plan";
  if (path.includes("/qa/")) return "QA";
  if (path.includes("/reviews/")) return "Review";
  return "Doc";
}

function ArtifactItem({ artifact }: { artifact: Artifact }) {
  const name = artifact.path.split("/").pop() ?? artifact.path;
  return (
    <article className="artifact-item" aria-label={`Artifact: ${name}`}>
      <span className="artifact-type">{fileType(artifact.path)}</span>
      <div className="artifact-path" title={artifact.path}>
        {name}
      </div>
      <time className="artifact-mtime">
        {formatMtime(artifact.mtime)}
      </time>
    </article>
  );
}

function ArtifactsPanel({ artifacts }: ArtifactsPanelProps) {
  // Sort newest first
  const sorted = [...artifacts].sort((a, b) => b.mtime - a.mtime);

  return (
    <section className="panel artifacts-panel" aria-label="Artifacts">
      <h2 className="panel-title">
        Artifacts
        <span className="panel-badge">{artifacts.length}</span>
      </h2>
      {sorted.length === 0 ? (
        <p className="panel-empty">No artifacts detected…</p>
      ) : (
        <ul className="artifact-list" role="list">
          {sorted.map((artifact) => (
            <li key={artifact.path}>
              <ArtifactItem artifact={artifact} />
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

export default memo(ArtifactsPanel);

import { STAGE_LABELS, type Job, type StageId } from "../lib/api";

const ORDER: StageId[] = ["plan", "images", "models", "animate", "shaders", "scene", "codegen", "review"];

const ICON: Record<StageResultStatus, string> = {
  pending: "○",
  running: "◐",
  done: "●",
  skipped: "—",
  failed: "✕",
};
type StageResultStatus = "pending" | "running" | "done" | "skipped" | "failed";

export function Pipeline({ job }: { job: Job }) {
  const byStage = new Map(job.stages.map((s) => [s.stage, s]));
  return (
    <div className="pipeline">
      {ORDER.map((id) => {
        const s = byStage.get(id);
        const status = (s?.status ?? "pending") as StageResultStatus;
        return (
          <div key={id} className={`stage stage--${status}`}>
            <div className="stage-dot">{ICON[status]}</div>
            <div className="stage-body">
              <div className="stage-name">{STAGE_LABELS[id]}</div>
              {s?.detail && <div className="stage-detail">{s.detail}</div>}
              {s?.provider && s.provider !== "" && (
                <span className="stage-provider">{s.provider}</span>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}

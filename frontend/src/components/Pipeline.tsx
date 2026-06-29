import { STAGE_LABELS, type Job, type StageId } from "../lib/api";
import { Check, Cross } from "./icons";

const ORDER: StageId[] = ["plan", "images", "models", "animate", "shaders", "scene", "codegen", "review"];

type StageResultStatus = "pending" | "running" | "done" | "skipped" | "failed";

function StageIcon({ status }: { status: StageResultStatus }) {
  if (status === "done") return <Check size={12} />;
  if (status === "failed") return <Cross size={12} />;
  if (status === "running") return <span className="dot" />;
  if (status === "skipped") return <span style={{ fontSize: 13, lineHeight: 1 }}>–</span>;
  return null;
}

export function Pipeline({ job }: { job: Job }) {
  const byStage = new Map(job.stages.map((s) => [s.stage, s]));
  const done = job.stages.filter((s) => s.status === "done").length;

  return (
    <div className="panel pipeline">
      <div className="panel-head">
        <span className="panel-eyebrow">Pipeline</span>
        <span className="panel-count">{done}/{ORDER.length}</span>
      </div>
      <div className="panel-body">
        {ORDER.map((id) => {
          const s = byStage.get(id);
          const status = (s?.status ?? "pending") as StageResultStatus;
          return (
            <div key={id} className={`stage stage--${status}`}>
              <div className="stage-icon">
                <StageIcon status={status} />
              </div>
              <div className="stage-body">
                <div className="stage-name">{STAGE_LABELS[id]}</div>
                {s?.detail && <div className="stage-detail">{s.detail}</div>}
                {s?.provider && s.provider !== "" && s.provider !== "none" && (
                  <span className="stage-provider">{s.provider}</span>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

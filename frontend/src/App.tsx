import { useEffect, useState } from "react";
import { api, subscribeJob, type Health, type Job } from "./lib/api";
import { PromptForm } from "./components/PromptForm";
import { Pipeline } from "./components/Pipeline";
import { PlanViewer } from "./components/PlanViewer";
import { SitePreview } from "./components/SitePreview";
import { JobLog } from "./components/JobLog";

export function App() {
  const [health, setHealth] = useState<Health | null>(null);
  const [job, setJob] = useState<Job | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.health().then(setHealth).catch(() => setHealth(null));
  }, []);

  const jobId = job?.id;
  const jobStatus = job?.status;

  useEffect(() => {
    if (!jobId) return;
    return subscribeJob(jobId, setJob);
  }, [jobId]);

  useEffect(() => {
    if (jobStatus === "succeeded" || jobStatus === "failed") setBusy(false);
  }, [jobStatus]);

  async function handleSubmit(prompt: string, brandMood?: string) {
    setError(null);
    setBusy(true);
    try {
      const created = await api.createJob({ prompt, brand_mood: brandMood });
      setJob(created);
    } catch (e) {
      setError(String(e));
      setBusy(false);
    }
  }

  const integ = health?.integrations;

  return (
    <div className="app">
      <header className="topbar">
        <div className="logo">
          <span className="logo-mark">▰</span> WEGEK <span className="logo-sub">AI 3D Website Factory</span>
        </div>
        <div className="integrations">
          <Badge label="Planner" value={integ?.planner_llm} />
          <Badge label="Images" value={integ?.image_gen} />
          <Badge label="3D" value={integ?.model_gen} />
          <Badge label="Renderer" value={integ ? (integ.renderer ? "on" : "off") : undefined} />
        </div>
      </header>

      <main className="layout">
        <section className="left">
          <PromptForm onSubmit={handleSubmit} busy={busy} />
          {error && <div className="error-box">⚠ {error}</div>}
          {job && (
            <>
              <div className="status-row">
                <span className={`pill pill--${job.status}`}>{job.status}</span>
                <span className="job-id">job {job.id}</span>
              </div>
              <Pipeline job={job} />
              <JobLog logs={job.logs} />
            </>
          )}
        </section>

        <section className="right">
          {!job && (
            <div className="empty-state">
              <div className="empty-emoji">🏭</div>
              <h2>자연어 → 3D 웹사이트</h2>
              <p>
                프롬프트만 넣으면 7-스테이지 AI 파이프라인이 기획 · 3D · 셰이더 · 스크롤 연출까지
                전부 만들어서 바로 열리는 사이트를 찍어냅니다. API 키 없어도 프로시저럴로 완성돼요.
              </p>
            </div>
          )}
          {job?.plan && <PlanViewer plan={job.plan} />}
          {job?.status === "succeeded" && job.site_url && (
            <SitePreview siteUrl={job.site_url} score={job.review_score} />
          )}
          {job?.status === "failed" && <div className="error-box">파이프라인 실패: {job.error}</div>}
        </section>
      </main>
    </div>
  );
}

function Badge({ label, value }: { label: string; value?: string }) {
  const live = value && value !== "none" && value !== "off";
  return (
    <span className={`integ-badge ${live ? "live" : "fallback"}`}>
      <span className="integ-label">{label}</span>
      <span className="integ-value">{value ?? "…"}</span>
    </span>
  );
}

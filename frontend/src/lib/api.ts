export type JobStatus = "queued" | "running" | "succeeded" | "failed";
export type StageId =
  | "plan" | "images" | "models" | "animate" | "shaders" | "scene" | "codegen" | "review";

export interface StageResult {
  stage: StageId;
  status: "pending" | "running" | "done" | "skipped" | "failed";
  detail: string;
  provider: string;
  started_at: number | null;
  finished_at: number | null;
  meta: Record<string, unknown>;
}

export interface LogEntry {
  ts: number;
  stage: StageId | null;
  level: string;
  message: string;
}

export interface Object3D {
  id: string;
  description: string;
  category: string;
  animation: string;
  model_format: string;
  primitive: string | null;
  color: string | null;
}

export interface Section {
  id: string;
  type: string;
  headline: string;
  subcopy: string;
  camera_preset: string;
  lighting_preset: string;
  scroll_behavior: string;
}

export interface SitePlan {
  project_name: string;
  tagline: string;
  brand_mood: string;
  sections: Section[];
  objects: Object3D[];
  global_style: {
    color_palette: string[];
    typography: string;
    background_shader: string;
    accent: string;
  };
}

export interface Job {
  id: string;
  prompt: string;
  status: JobStatus;
  created_at: number;
  updated_at: number;
  current_stage: StageId | null;
  stages: StageResult[];
  plan: SitePlan | null;
  site_url: string | null;
  review_score: number | null;
  error: string | null;
  logs: LogEntry[];
}

export interface JobSummary {
  id: string;
  prompt: string;
  status: JobStatus;
  created_at: number;
  updated_at: number;
  site_url: string | null;
  review_score: number | null;
}

export interface Health {
  status: string;
  integrations: {
    planner_llm: string;
    image_gen: string;
    model_gen: string;
    renderer: boolean;
  };
}

const json = async <T>(r: Response): Promise<T> => {
  if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
  return r.json() as Promise<T>;
};

export const api = {
  health: () => fetch("/api/health").then(json<Health>),
  presets: () => fetch("/api/presets").then(json<Record<string, string[]>>),
  listJobs: () => fetch("/api/jobs").then(json<JobSummary[]>),
  getJob: (id: string) => fetch(`/api/jobs/${id}`).then(json<Job>),
  createJob: (body: { prompt: string; brand_mood?: string; max_objects?: number }) =>
    fetch("/api/jobs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }).then(json<Job>),
};

export function subscribeJob(id: string, onUpdate: (job: Job) => void): () => void {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  const ws = new WebSocket(`${proto}://${location.host}/ws/jobs/${id}`);
  ws.onmessage = (ev) => {
    try {
      const data = JSON.parse(ev.data);
      if (data && data.id) onUpdate(data as Job);
    } catch {
      /* ignore pings */
    }
  };
  return () => ws.close();
}

export const STAGE_LABELS: Record<StageId, string> = {
  plan: "Stage 0 · Planner AI",
  images: "Stage 1 · Reference Images",
  models: "Stage 2 · Image → 3D",
  animate: "Stage 3 · Rig & Animate",
  shaders: "Stage 4 · GLSL Background",
  scene: "Stage 5 · Scene Assembly",
  codegen: "Stage 6 · DOM & Frontend",
  review: "Stage 7 · Render Review",
};

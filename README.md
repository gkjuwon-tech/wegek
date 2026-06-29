# 🏭 WEGEK — AI 3D Website Factory

> 자연어 한 줄 → 바로 열리는 프로덕션급 3D 스크롤리텔링 웹사이트.
> Natural language → a production-grade, standalone Three.js + GSAP + Lenis + GLSL website.

WEGEK takes a prompt like _"고급 시계 브랜드 랜딩, 시계가 돌아가며 부품이 분해됐다 재조립되는 느낌"_
and runs it through a **7-stage AI pipeline** that plans the site, generates 3D assets,
authors animations and GLSL backgrounds, assembles the scene, and **codegens a single
self-contained `index.html`** you can open in a browser.

**Zero API keys required.** Every external integration is optional — with no keys WEGEK
falls back to a heuristic planner, parametric Three.js geometry, and a curated GLSL shader
library, and still ships a complete, runnable site. Add keys to upgrade each stage to real
AI assets (Claude/GPT planning, FLUX images, Tripo 3D models). They enhance; they're never required.

---

## The pipeline

| Stage | What it does | With keys | Without keys (fallback) |
|------:|--------------|-----------|--------------------------|
| 0 · Plan    | Brief → structured `SitePlan` | Anthropic / OpenAI / Gemini | Heuristic category-aware planner |
| 1 · Images  | Reference images   | FLUX (BFL) / Gemini         | Skipped → procedural geometry |
| 2 · Models  | Image → 3D GLB                | Tripo              | Parametric primitives |
| 3 · Animate | Keyframe tracks               | — (deterministic)  | Deterministic keyframes |
| 4 · Shaders | GLSL background               | LLM-authored       | Curated shader library |
| 5 · Scene   | Lighting + camera + scroll    | — (presets)        | Presets |
| 6 · Codegen | Standalone HTML site bundle   | — (deterministic)  | Deterministic |
| 7 · Review  | Quality score + screenshot    | puppeteer-capture  | Structural review |

Progress streams live to the studio over WebSocket; jobs persist in SQLite.

---

## Quick start

### Option A — local dev (no Docker)

```bash
# 1. config (optional — works with all keys blank)
cp .env.example .env

# 2. backend
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
uvicorn app.main:app --reload          # → http://localhost:8000  (API + /docs)

# 3. studio (new terminal)
cd frontend
npm install
npm run dev                            # → http://localhost:5173
```

Open the studio, type a prompt, watch the 7 stages light up, and preview the generated
site inline. Download the standalone HTML or open it in a new tab.

### Option B — Docker Compose (backend + studio + renderer)

```bash
cp .env.example .env
docker compose up --build
# studio:  http://localhost:8080
# api:     http://localhost:8000/docs
```

---

## API

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/jobs` | Create a job `{ "prompt": "...", "brand_mood"?, "max_objects"? }` |
| `GET`  | `/api/jobs` | List recent jobs |
| `GET`  | `/api/jobs/{id}` | Full job (status, plan, stages, logs) |
| `GET`  | `/api/health` | Status + which integrations are live |
| `GET`  | `/api/presets` | Available shader / lighting / camera presets |
| `WS`   | `/ws/jobs/{id}` | Live job updates |
| `GET`  | `/sites/{id}/index.html` | The generated standalone site |

```bash
curl -X POST localhost:8000/api/jobs -H 'content-type: application/json' \
  -d '{"prompt":"Nike Air Max landing, shoe rotates and explodes into parts"}'
```

---

## Repo layout

```
backend/    FastAPI orchestrator — config, schemas, SQLite store, API clients,
            pipeline/ (stage0..7), presets/ (shaders, lighting, cameras, mapping),
            pipeline/templates/ (site.html + engine.js codegen templates)
frontend/   Vite + React + TS studio (prompt → live pipeline → preview/download)
renderer/   Optional puppeteer-capture render-review service (Stage 7)
.env.example  All configuration, every key optional
docker-compose.yml
```

---

## What "production quality" means here

- **No mockups.** API clients make real HTTP calls (BFL async poll, Tripo task poll,
  Anthropic/OpenAI messages). The fallbacks are real generators, not stubs.
- **Graceful degradation** at every stage — a missing key downgrades one stage, never breaks the run.
- **The generated site is genuinely standalone**: one `index.html`, ES-module Three.js via
  import map, a real GLSL `ShaderMaterial` background, GSAP ScrollTrigger choreography,
  Lenis smooth scroll, scroll-driven camera paths, and per-object keyframe animation.
- **Typed + tested**: backend passes `ruff` + `mypy` + `pytest`; frontend passes
  `eslint` + `tsc` + `vite build`. CI runs all of it.

---

## Configuration

See [`.env.example`](.env.example). Highlights:

- `PLANNER_PROVIDER` — `auto` | `anthropic` | `openai` | `gemini`
- `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` / `GEMINI_API_KEY` — Stage 0 + Stage 4
- `IMAGE_PROVIDER` — `auto` | `bfl` | `gemini`
- `BFL_API_KEY` — Stage 1 images (FLUX); `GEMINI_API_KEY` — Stage 1 images (Gemini)
- `TRIPO_API_KEY` — Stage 2/3 models + rig (accepts FLUX URLs or local Gemini images)
- `RENDERER_URL` — point Stage 7 at the renderer service for screenshots
- `SHADER_USE_LLM` — let the LLM author bespoke GLSL when a key is present

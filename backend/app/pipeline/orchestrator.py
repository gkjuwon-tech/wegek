"""Pipeline orchestrator — runs Stage 0..7 for a job, streaming live updates.

Each stage mutates the shared `SitePlan`, records a `StageResult`, and appends
log entries that fan out to subscribed WebSocket clients via the store.
"""
from __future__ import annotations

import time

from ..config import get_settings
from ..schemas import Job, JobStatus, Stage, StageResult
from ..store import get_store
from . import (
    stage0_planner,
    stage1_images,
    stage2_models,
    stage3_animate,
    stage4_shaders,
    stage5_scene,
    stage6_codegen,
    stage7_review,
)


async def run_pipeline(
    job_id: str,
    *,
    brand_mood: str | None = None,
    max_objects: int | None = None,
) -> None:
    settings = get_settings()
    store = get_store()
    job = await store.get(job_id)
    if job is None:
        return

    job.status = JobStatus.RUNNING
    job.stages = [StageResult(stage=s) for s in Stage]
    await _touch(store, job)

    async def make_logger(stage: Stage):
        async def log(message: str, level: str = "info") -> None:
            from ..schemas import LogEntry

            job.logs.append(LogEntry(stage=stage, level=level, message=message))
            await _touch(store, job)

        return log

    max_obj = max_objects or settings.max_objects_per_site

    try:
        # Stage 0 — Plan
        sr = await _begin(store, job, Stage.PLAN)
        plan, provider = await stage0_planner.run(
            job.prompt, settings, brand_mood=brand_mood, max_objects=max_obj
        )
        job.plan = plan
        await _end(store, job, sr, provider, f"Planned '{plan.project_name}' · {len(plan.sections)} sections · {len(plan.objects)} objects")

        # Stage 1 — Images
        sr = await _begin(store, job, Stage.IMAGES)
        provider, meta = await stage1_images.run(plan, settings, await make_logger(Stage.IMAGES))
        await _end(store, job, sr, provider, f"{meta.get('generated', 0)} reference image(s)", meta)

        # Stage 2 — 3D models
        sr = await _begin(store, job, Stage.MODELS)
        provider, meta = await stage2_models.run(plan, settings, await make_logger(Stage.MODELS))
        await _end(store, job, sr, provider, f"{meta.get('models', 0)} GLB model(s); rest procedural", meta)

        # Stage 3 — Animate
        sr = await _begin(store, job, Stage.ANIMATE)
        provider, meta = await stage3_animate.run(plan, settings, await make_logger(Stage.ANIMATE))
        await _end(store, job, sr, provider, f"{meta.get('tracks', 0)} keyframe track(s)", meta)

        # Stage 4 — Shaders
        sr = await _begin(store, job, Stage.SHADERS)
        provider, meta = await stage4_shaders.run(plan, settings, await make_logger(Stage.SHADERS))
        await _end(store, job, sr, provider, f"background shader ready ({meta.get('source')})", meta)

        # Stage 5 — Scene
        sr = await _begin(store, job, Stage.SCENE)
        provider, meta = await stage5_scene.run(plan, settings, await make_logger(Stage.SCENE))
        await _end(store, job, sr, provider, f"assembled {meta.get('sections', 0)} section(s)", meta)

        # Stage 6 — Codegen
        sr = await _begin(store, job, Stage.CODEGEN)
        provider, meta = await stage6_codegen.run(plan, settings, job_id, await make_logger(Stage.CODEGEN))
        job.bundle_path = meta.get("path")
        job.site_url = f"/sites/{job_id}/index.html"
        await _end(store, job, sr, provider, "standalone site generated", meta)

        # Stage 7 — Review (with bounded improvement loop)
        sr = await _begin(store, job, Stage.REVIEW)
        score = 0.0
        meta = {}
        for _attempt in range(1, settings.review_max_iterations + 1):
            provider, meta = await stage7_review.run(
                plan, settings, job.site_url, await make_logger(Stage.REVIEW)
            )
            score = float(meta.get("score", 0.0))
            if meta.get("preview_image"):
                job.preview_image = meta["preview_image"]
            if score >= settings.review_pass_score:
                break
        job.review_score = score
        await _end(store, job, sr, provider, f"verdict {meta.get('verdict')} · score {score:.2f}", meta)

        job.status = JobStatus.SUCCEEDED
        job.current_stage = None
        await _touch(store, job)
    except Exception as exc:  # noqa: BLE001
        job.status = JobStatus.FAILED
        job.error = f"{type(exc).__name__}: {exc}"
        if job.current_stage:
            cur = job.stage_result(job.current_stage)
            cur.status = "failed"
            cur.detail = job.error
            cur.finished_at = time.time()
        await _touch(store, job)


async def _begin(store, job: Job, stage: Stage) -> StageResult:
    job.current_stage = stage
    sr = job.stage_result(stage)
    sr.status = "running"
    sr.started_at = time.time()
    await _touch(store, job)
    return sr


async def _end(store, job: Job, sr: StageResult, provider: str, detail: str, meta: dict | None = None) -> None:
    sr.status = "done"
    sr.provider = provider
    sr.detail = detail
    sr.finished_at = time.time()
    if meta:
        sr.meta = {k: v for k, v in meta.items() if k != "preview_image"}
    await _touch(store, job)


async def _touch(store, job: Job) -> None:
    job.updated_at = time.time()
    await store.save(job)

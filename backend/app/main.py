"""WEGEK v2 backend API."""
from __future__ import annotations

import uuid

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings
from .pipeline import orchestrator
from .schemas import CreateJobRequest, Job, JobStatus
from .store import get_store

app = FastAPI(title="WEGEK v2 — AI 3D Render Studio")
settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins.split(",")],
    allow_methods=["*"], allow_headers=["*"],
)


@app.get("/healthz")
async def healthz() -> dict:
    return {"ok": True, "version": app.version, "service": "wegek-v2"}


async def _run(job_id: str) -> None:
    store = get_store()
    job = await store.get(job_id)
    if job:
        await orchestrator.run_job(job, settings, store.save)


@app.post("/jobs")
async def create_job(req: CreateJobRequest, bg: BackgroundTasks) -> dict:
    store = get_store()
    job = Job(id=uuid.uuid4().hex[:12], prompt=req.prompt)
    await store.save(job)
    bg.add_task(_run, job.id)
    return {"id": job.id, "status": job.status}


@app.get("/jobs/{job_id}")
async def get_job(job_id: str) -> Job:
    job = await get_store().get(job_id)
    if not job:
        raise HTTPException(404, "job not found")
    return job


@app.get("/jobs")
async def list_jobs() -> list[dict]:
    return [{"id": j.id, "status": j.status, "prompt": j.prompt[:80], "created_at": j.created_at}
            for j in get_store().list()]


@app.get("/jobs/{job_id}/spec")
async def get_spec(job_id: str) -> dict:
    job = await get_store().get(job_id)
    if not job:
        raise HTTPException(404, "job not found")
    if job.status != JobStatus.SUCCEEDED or not job.baked_spec:
        raise HTTPException(409, f"spec not ready (status={job.status})")
    return job.baked_spec

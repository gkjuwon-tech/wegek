"""REST API for the WEGEK factory."""
from __future__ import annotations

import asyncio
import uuid

from fastapi import APIRouter, HTTPException

from ..clients.bfl import BFLClient
from ..clients.llm import LLMClient
from ..clients.tripo import TripoClient
from ..config import get_settings
from ..pipeline.orchestrator import run_pipeline
from ..presets.cameras import CAMERA_PRESETS
from ..presets.lighting import LIGHTING_PRESETS
from ..presets.shaders import SHADERS
from ..schemas import CreateJobRequest, Job, JobSummary
from ..store import get_store

router = APIRouter(prefix="/api", tags=["jobs"])


@router.get("/health")
async def health() -> dict:
    s = get_settings()
    return {
        "status": "ok",
        "integrations": {
            "planner_llm": LLMClient(s).label,
            "image_gen": BFLClient(s).label,
            "model_gen": TripoClient(s).label,
            "renderer": bool(s.renderer_url),
        },
    }


@router.get("/presets")
async def presets() -> dict:
    return {
        "shaders": sorted(SHADERS.keys()),
        "lighting": sorted(LIGHTING_PRESETS.keys()),
        "cameras": sorted(CAMERA_PRESETS.keys()),
    }


@router.post("/jobs", response_model=Job, status_code=201)
async def create_job(req: CreateJobRequest) -> Job:
    store = get_store()
    job = Job(id=uuid.uuid4().hex[:12], prompt=req.prompt.strip())
    await store.save(job)
    asyncio.create_task(
        run_pipeline(job.id, brand_mood=req.brand_mood, max_objects=req.max_objects)
    )
    return job


@router.get("/jobs", response_model=list[JobSummary])
async def list_jobs(limit: int = 50) -> list[JobSummary]:
    return await get_store().list_summaries(limit=limit)


@router.get("/jobs/{job_id}", response_model=Job)
async def get_job(job_id: str) -> Job:
    job = await get_store().get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    return job

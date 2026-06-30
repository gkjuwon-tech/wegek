"""Tiny job store: in-memory with JSON persistence under _data/jobs."""
from __future__ import annotations

import time
from functools import lru_cache

from .config import get_settings
from .schemas import Job


class JobStore:
    def __init__(self) -> None:
        self.s = get_settings()
        self._jobs: dict[str, Job] = {}

    async def save(self, job: Job) -> None:
        job.updated_at = time.time()
        self._jobs[job.id] = job
        (self.s.jobs_dir / f"{job.id}.json").write_text(job.model_dump_json(indent=2), encoding="utf-8")

    async def get(self, job_id: str) -> Job | None:
        if job_id in self._jobs:
            return self._jobs[job_id]
        p = self.s.jobs_dir / f"{job_id}.json"
        if p.exists():
            job = Job.model_validate_json(p.read_text())
            self._jobs[job_id] = job
            return job
        return None

    def list(self) -> list[Job]:
        return sorted(self._jobs.values(), key=lambda j: j.created_at, reverse=True)


@lru_cache
def get_store() -> JobStore:
    return JobStore()

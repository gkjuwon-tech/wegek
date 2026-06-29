"""Durable job store (SQLite) + in-process pub/sub for live job updates.

Jobs are persisted as JSON blobs keyed by id. A lightweight asyncio broker
fan-outs every update to subscribed WebSocket connections so the studio shows
the pipeline progressing in real time.
"""
from __future__ import annotations

import asyncio
import contextlib
import json
import sqlite3
from collections import defaultdict
from contextlib import closing

from .config import get_settings
from .schemas import Job, JobSummary


class JobStore:
    def __init__(self) -> None:
        self._settings = get_settings()
        self._lock = asyncio.Lock()
        self._subscribers: dict[str, set[asyncio.Queue]] = defaultdict(set)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._settings.db_path, timeout=30)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with closing(self._connect()) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    status TEXT NOT NULL,
                    data TEXT NOT NULL
                )
                """
            )
            conn.commit()

    # --- persistence ------------------------------------------------------- #
    async def save(self, job: Job) -> None:
        async with self._lock:
            payload = job.model_dump_json()
            with closing(self._connect()) as conn:
                conn.execute(
                    """
                    INSERT INTO jobs (id, created_at, updated_at, status, data)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        updated_at=excluded.updated_at,
                        status=excluded.status,
                        data=excluded.data
                    """,
                    (job.id, job.created_at, job.updated_at, job.status.value, payload),
                )
                conn.commit()
        await self._publish(job)

    async def get(self, job_id: str) -> Job | None:
        async with self._lock:
            with closing(self._connect()) as conn:
                row = conn.execute(
                    "SELECT data FROM jobs WHERE id = ?", (job_id,)
                ).fetchone()
        if row is None:
            return None
        return Job.model_validate(json.loads(row["data"]))

    async def list_summaries(self, limit: int = 50) -> list[JobSummary]:
        async with self._lock:
            with closing(self._connect()) as conn:
                rows = conn.execute(
                    "SELECT data FROM jobs ORDER BY created_at DESC LIMIT ?",
                    (limit,),
                ).fetchall()
        jobs = [Job.model_validate(json.loads(r["data"])) for r in rows]
        return [
            JobSummary(
                id=j.id,
                prompt=j.prompt,
                status=j.status,
                created_at=j.created_at,
                updated_at=j.updated_at,
                current_stage=j.current_stage,
                site_url=j.site_url,
                review_score=j.review_score,
            )
            for j in jobs
        ]

    # --- pub/sub ----------------------------------------------------------- #
    def subscribe(self, job_id: str) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=256)
        self._subscribers[job_id].add(q)
        return q

    def unsubscribe(self, job_id: str, q: asyncio.Queue) -> None:
        self._subscribers[job_id].discard(q)
        if not self._subscribers[job_id]:
            self._subscribers.pop(job_id, None)

    async def _publish(self, job: Job) -> None:
        for q in list(self._subscribers.get(job.id, set())):
            with contextlib.suppress(asyncio.QueueFull):
                q.put_nowait(job.model_dump(mode="json"))


_store: JobStore | None = None


def get_store() -> JobStore:
    global _store
    if _store is None:
        _store = JobStore()
    return _store

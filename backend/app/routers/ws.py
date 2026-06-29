"""WebSocket endpoint streaming live job updates to the studio."""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ..store import get_store

router = APIRouter()


@router.websocket("/ws/jobs/{job_id}")
async def job_updates(websocket: WebSocket, job_id: str) -> None:
    store = get_store()
    await websocket.accept()

    # send current snapshot immediately
    job = await store.get(job_id)
    if job is not None:
        await websocket.send_json(job.model_dump(mode="json"))

    queue = store.subscribe(job_id)
    try:
        while True:
            try:
                update = await asyncio.wait_for(queue.get(), timeout=30.0)
                await websocket.send_json(update)
            except TimeoutError:
                await websocket.send_json({"type": "ping"})
    except WebSocketDisconnect:
        pass
    finally:
        store.unsubscribe(job_id, queue)

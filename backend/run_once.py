"""One-off real run: Gemini planner, box meshes, Blender render, real website."""
from __future__ import annotations

import asyncio
import os
import uuid
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env")
os.environ.setdefault("MESH_MODE", "box")
os.environ.setdefault("FRAMES_PER_SCENE", "24")
os.environ.setdefault("RENDER_SAMPLES", "16")
from app.config import get_settings  # noqa: E402
from app.pipeline import orchestrator  # noqa: E402
from app.schemas import Job  # noqa: E402
from app.store import get_store  # noqa: E402

PROMPT = ("CYPHER SHADOW X — a limited-edition chrome hypebeast sneaker drop. An immersive "
          "neon-noir 3D experience in three scrolling acts: arrival shrine, macro detail chamber, "
          "lifestyle finale. Dramatic camera moves, rim lighting, architectural staging.")

async def main():
    s = get_settings()
    print("mesh_mode=", s.mesh_mode, "frames/scene=", s.frames_per_scene, "samples=", s.render_samples)
    job = Job(id="run" + uuid.uuid4().hex[:6], prompt=PROMPT)
    store = get_store()
    await orchestrator.run_job(job, s, store.save, max_iters=2)
    print("STATUS:", job.status)
    if job.baked_spec:
        print("SITE:", job.baked_spec.get("site_path"))
        print("VIDEO:", job.baked_spec.get("video_path"))
        print("ACTS:", [(a["id"], a.get("frame_range")) for a in job.baked_spec.get("acts", [])])
    if job.error:
        print("ERROR:", job.error)

if __name__ == "__main__":
    asyncio.run(main())

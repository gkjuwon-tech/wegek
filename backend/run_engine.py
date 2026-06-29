"""Engine-interpreter pipeline (no AI three.js codegen).

AI authors shaders + placement + effect params; the fixed engine renders it;
meshes are external GLBs only (Objaverse). Then headless screenshot for review.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env")

from app.config import get_settings  # noqa: E402
from app.factory import render as frender  # noqa: E402
from app.pipeline import stage0_planner, stage2_assets, stage4_shaders, stage5_scene, stage6_codegen  # noqa: E402

PROMPT = ("CYPHER SHADOW X — a limited-edition hypebeast sneaker drop. Futuristic chrome high-top. "
          "Build an immersive Active-Theory-style 3D WORLD the camera flies through: the sneaker "
          "enshrined in a neon-noir ruined cathedral / data-temple — pillars, rocks, statues, "
          "floating debris, monitors, lamps arranged in deep space. Many animated meshes, particle "
          "storms, cinematic camera travel, kinetic mono typography. A place, not a product shot.")


async def log(msg, level="info"):
    print(f"   · {msg}", flush=True)


async def build(job: str):
    s = get_settings()
    site_dir = s.sites_dir / job
    plan, prov = await stage0_planner.run(PROMPT, s, brand_mood=None, max_objects=14)
    print(f"PLAN provider={prov} project={plan.project_name} objs={[o.id for o in plan.objects]}", flush=True)
    print(f"  effects={plan.effects}", flush=True)
    _, meta = await stage2_assets.run(plan, site_dir, log)
    print(f"  meshes sourced: {meta['meshes']}", flush=True)
    await stage4_shaders.run(plan, s, log)
    await stage5_scene.run(plan, s, log)
    _, m6 = await stage6_codegen.run(plan, s, job, log)
    print(f"  site: {m6['path']}", flush=True)
    return site_dir


if __name__ == "__main__":
    job = sys.argv[1] if len(sys.argv) > 1 else "engine-cypher"
    site_dir = asyncio.run(build(job))
    # headless verify OUTSIDE the asyncio loop (Playwright sync API)
    r = frender.render(site_dir, str(site_dir / "_shots" / "v"), shots=4)
    print(f"RENDER ready={r['ready']} errors={len(r['errors'])} shots={len(r['images'])}", flush=True)
    for e in r["errors"][:6]:
        print("   !", e, flush=True)
    print(f"SITE_DIR={site_dir}", flush=True)

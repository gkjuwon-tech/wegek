"""Stage 2 — Meshes: outsource every mesh to Tripo (reference image -> 3D GLB).

Deduped by mesh_query and cached on disk so repeated runs (and shared heroes across
scenes) never re-spend Tripo credits. Gemini paints a clean reference image; Tripo
turns it into a GLB; we download it locally for Blender to import.
"""
from __future__ import annotations

import re
from collections.abc import Awaitable, Callable

import httpx

from ..clients.llm import LLMClient
from ..clients.tripo import TripoClient
from ..config import Settings
from ..schemas import Experience

Logger = Callable[[str], Awaitable[None]]


def _key(query: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", query.lower()).strip("_")[:48] or "mesh"


async def run(exp: Experience, settings: Settings, log: Logger) -> tuple[str, dict]:
    if settings.mesh_mode == "box":
        await log("Mesh mode = box: all meshes are placeholder cubes (Blender builds them).")
        return "box", {"made": 0, "cached": 0, "failed": 0, "unique": 0, "box": True}
    tripo = TripoClient(settings)
    llm = LLMClient(settings)
    settings.assets_dir.mkdir(parents=True, exist_ok=True)

    # unique queries -> objects sharing them
    groups: dict[str, list] = {}
    for obj in exp.all_objects():
        groups.setdefault(_key(obj.mesh_query or obj.id), []).append(obj)

    made = cached = failed = 0
    async with httpx.AsyncClient(timeout=settings.request_timeout, follow_redirects=True) as http:
        for key, objs in groups.items():
            local = settings.assets_dir / f"{key}.glb"
            if local.exists():  # cache hit (incl. seeded assets)
                cached += 1
                await log(f"mesh '{key}': cached GLB reused.")
            elif not tripo.available:
                failed += 1
                await log(f"mesh '{key}': no Tripo key — left unmade.")
                continue
            else:
                try:
                    ref = objs[0].mesh_query or objs[0].description or key
                    img = await llm.generate_image(ref, settings.assets_dir / "_refimg") if llm.available else ref
                    url = await tripo.image_to_model(img)
                    resp = await http.get(url)
                    resp.raise_for_status()
                    local.write_bytes(resp.content)
                    made += 1
                    await log(f"mesh '{key}': Tripo GLB created.")
                except Exception as exc:  # noqa: BLE001
                    failed += 1
                    await log(f"mesh '{key}': Tripo failed ({exc}).")
                    continue
            for o in objs:
                o.model_local = str(local)
    return "tripo", {"made": made, "cached": cached, "failed": failed, "unique": len(groups)}

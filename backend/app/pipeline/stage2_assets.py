"""Stage 2 (external-mesh mode) — source every mesh as a real downloaded GLB.

Meshes are external only: each plan object is resolved to a free GLB (Objaverse)
and downloaded into the site's models/ folder. Objects that cannot be matched are
dropped (no procedural primitives) so the scene only ever shows real geometry.

Temporary stand-in while Tripo (image->3D) is offline.
"""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from pathlib import Path

from ..factory import assets
from ..schemas import SitePlan

Logger = Callable[[str], Awaitable[None]]


async def run(plan: SitePlan, site_dir: Path, log: Logger) -> tuple[str, dict]:
    site_dir.mkdir(parents=True, exist_ok=True)
    kept: list = []
    for obj in plan.objects:
        query = obj.mesh_query or obj.category or obj.description
        got = assets.resolve(query, site_dir, obj.id)
        if got:
            obj.model_url = got["path"]
            obj.model_format = "glb"
            kept.append(obj)
            await log(f"mesh '{obj.id}' <- objaverse[{got['category']}] ({query[:40]!r})")
        else:
            await log(f"mesh '{obj.id}' unresolved ({query[:40]!r}); dropped (external-only).")
    plan.objects = kept
    # prune object ids that were dropped from section references
    valid = {o.id for o in kept}
    for sec in plan.sections:
        sec.objects = [oid for oid in sec.objects if oid in valid]
        sec.object_layout = {k: v for k, v in (sec.object_layout or {}).items() if k in valid}
    return "objaverse", {"meshes": len(kept)}

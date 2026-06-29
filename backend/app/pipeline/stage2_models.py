"""Stage 2 — Image → 3D model generation (Tripo).

Converts reference images into GLB models. Objects without a successful 3D
generation keep `model_format="procedural"` and are rendered with parametric
Three.js geometry, guaranteeing a complete scene.
"""
from __future__ import annotations

from collections.abc import Awaitable, Callable

from ..clients.tripo import TripoClient
from ..config import Settings
from ..schemas import SitePlan

Logger = Callable[[str], Awaitable[None]]


async def run(plan: SitePlan, settings: Settings, log: Logger) -> tuple[str, dict]:
    client = TripoClient(settings)
    if not client.available:
        await log("No Tripo key — using procedural primitives for all objects.")
        return "procedural", {"models": 0}

    models = 0
    for obj in plan.objects:
        if not obj.reference_images:
            await log(f"'{obj.id}' has no images — procedural geometry.")
            continue
        try:
            url = await client.image_to_model(
                obj.reference_images, generate_parts=obj.needs_parts_separation
            )
            obj.model_url = url
            obj.model_format = "glb"
            models += 1
            await log(f"Tripo: GLB ready for '{obj.id}'.")
        except Exception as exc:  # noqa: BLE001
            await log(f"Tripo failed for '{obj.id}' ({exc}); procedural fallback.")
    return (client.label if models else "procedural"), {"models": models}

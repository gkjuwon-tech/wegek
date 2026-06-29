"""Stage 1 — Reference image generation (FLUX.2 via BFL).

For each object, generate multi-view reference images. Falls back to no images
(procedural geometry downstream) when the API is unavailable or errors.
"""
from __future__ import annotations

from collections.abc import Awaitable, Callable

from ..clients.bfl import BFLClient
from ..config import Settings
from ..schemas import SitePlan

Logger = Callable[[str], Awaitable[None]]


async def run(plan: SitePlan, settings: Settings, log: Logger) -> tuple[str, dict]:
    client = BFLClient(settings)
    if not client.available:
        await log("No FLUX key — skipping image gen, using procedural geometry.")
        return "procedural", {"generated": 0}

    generated = 0
    for obj in plan.objects:
        try:
            urls = await client.generate_views(obj.description)
            obj.reference_images = urls
            generated += len(urls)
            await log(f"FLUX: {len(urls)} views for '{obj.id}'.")
        except Exception as exc:  # noqa: BLE001
            await log(f"FLUX failed for '{obj.id}' ({exc}); procedural fallback.")
    return (client.label if generated else "procedural"), {"generated": generated}

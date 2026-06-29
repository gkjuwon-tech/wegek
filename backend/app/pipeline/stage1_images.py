"""Stage 1 — Reference image generation.

For each object, generate reference image(s) used by Stage 2 (image -> 3D).
The provider is chosen by `IMAGE_PROVIDER` (auto | bfl | gemini); `auto` prefers
FLUX, then Gemini, then falls back to no images (procedural geometry downstream).
Any per-object error degrades that object to procedural without failing the run.
"""
from __future__ import annotations

from collections.abc import Awaitable, Callable

from ..clients.bfl import BFLClient
from ..clients.gemini_image import GeminiImageClient
from ..config import Settings
from ..schemas import SitePlan

Logger = Callable[[str], Awaitable[None]]

ImageClient = BFLClient | GeminiImageClient


def select_image_client(settings: Settings) -> ImageClient | None:
    """Resolve the configured image-generation client, or None for procedural."""
    bfl = BFLClient(settings)
    gemini = GeminiImageClient(settings)
    choice = settings.image_provider.lower()
    if choice == "bfl":
        return bfl if bfl.available else None
    if choice == "gemini":
        return gemini if gemini.available else None
    # auto
    if bfl.available:
        return bfl
    if gemini.available:
        return gemini
    return None


async def run(plan: SitePlan, settings: Settings, log: Logger) -> tuple[str, dict]:
    client = select_image_client(settings)
    if client is None:
        await log("No image-gen key — skipping image gen, using procedural geometry.")
        return "procedural", {"generated": 0}

    await log(f"Image provider: {client.label}")
    generated = 0
    for obj in plan.objects:
        try:
            refs = await client.generate_views(obj.description)
            obj.reference_images = refs
            generated += len(refs)
            await log(f"{client.label}: {len(refs)} reference(s) for '{obj.id}'.")
        except Exception as exc:  # noqa: BLE001
            await log(f"Image gen failed for '{obj.id}' ({exc}); procedural fallback.")
    return (client.label if generated else "procedural"), {"generated": generated}

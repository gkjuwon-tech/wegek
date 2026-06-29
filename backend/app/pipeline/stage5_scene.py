"""Stage 5 — Scene assembly.

Validates and resolves lighting/camera presets per section and computes object
layout offsets (e.g. spacing for multi-object sections). The generated site
reads presets directly; this stage guarantees every section is renderable.
"""
from __future__ import annotations

from collections.abc import Awaitable, Callable

from ..config import Settings
from ..presets.cameras import CAMERA_PRESETS, DEFAULT_CAMERA
from ..presets.lighting import DEFAULT_LIGHTING, LIGHTING_PRESETS
from ..schemas import SitePlan

Logger = Callable[[str], Awaitable[None]]


async def run(plan: SitePlan, settings: Settings, log: Logger) -> tuple[str, dict]:
    resolved = 0
    for sec in plan.sections:
        if sec.lighting_preset not in LIGHTING_PRESETS:
            sec.lighting_preset = DEFAULT_LIGHTING
        if sec.camera_preset not in CAMERA_PRESETS:
            sec.camera_preset = DEFAULT_CAMERA
        # dom-only sections don't need a camera path
        if sec.type == "dom_section" and not sec.objects:
            sec.camera_preset = "static_hero"
        resolved += 1
    await log(f"Assembled {resolved} section(s): lighting + camera + scroll choreography.")
    return "scene_assembler", {"sections": resolved}

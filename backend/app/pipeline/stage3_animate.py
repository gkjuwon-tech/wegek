"""Stage 3 — Rig & animate.

For product/mechanical objects the highest-leverage approach (per the plan) is
AI-authored Three.js keyframes. We generate deterministic keyframe tracks from
the object's declared animation intent. These drive a GSAP timeline in the
generated site.
"""
from __future__ import annotations

import math
from collections.abc import Awaitable, Callable

from ..config import Settings
from ..schemas import SitePlan

Logger = Callable[[str], Awaitable[None]]

TAU = math.pi * 2


def _keyframes(animation: str) -> list[dict]:
    if animation == "slow_rotation_y":
        return [
            {"t": 0.0, "rotation": [0, 0, 0], "position": [0, 0.2, 0], "scale": 1.0},
            {"t": 0.5, "rotation": [0, math.pi, 0], "position": [0, 0, 0], "scale": 1.0},
            {"t": 1.0, "rotation": [0, TAU, 0], "position": [0, 0.2, 0], "scale": 1.0},
        ]
    if animation == "spin_fast":
        return [
            {"t": 0.0, "rotation": [0, 0, 0], "position": [0, 0, 0], "scale": 1.0},
            {"t": 1.0, "rotation": [0, TAU * 3, 0], "position": [0, 0, 0], "scale": 1.0},
        ]
    if animation == "float_bob":
        return [
            {"t": 0.0, "rotation": [0, 0, 0], "position": [0, -0.3, 0], "scale": 1.0},
            {"t": 0.5, "rotation": [0, math.pi * 0.5, 0], "position": [0, 0.3, 0], "scale": 1.02},
            {"t": 1.0, "rotation": [0, math.pi, 0], "position": [0, -0.3, 0], "scale": 1.0},
        ]
    if animation == "mechanical_tick":
        # Stepped rotation about the vertical axis (a bezel ticking round) with a
        # gentle face-up tilt — never the old Z-flip that laid the product on its side.
        return [
            {"t": 0.0, "rotation": [0.18, 0, 0], "position": [0, 0.1, 0], "scale": 1.0},
            {"t": 0.33, "rotation": [0.18, math.pi / 3, 0], "position": [0, 0.1, 0], "scale": 1.0},
            {"t": 0.66, "rotation": [0.18, TAU / 3, 0], "position": [0, 0.1, 0], "scale": 1.0},
            {"t": 1.0, "rotation": [0.18, TAU, 0], "position": [0, 0.1, 0], "scale": 1.0},
        ]
    if animation == "explode_reassemble":
        return [
            {"t": 0.0, "rotation": [0, 0, 0], "position": [0, 0, 0], "scale": 1.0, "explode": 0.0},
            {"t": 0.5, "rotation": [0, math.pi, 0], "position": [0, 0, 0], "scale": 1.0, "explode": 1.0},
            {"t": 1.0, "rotation": [0, TAU, 0], "position": [0, 0, 0], "scale": 1.0, "explode": 0.0},
        ]
    # default: gentle rotation
    return [
        {"t": 0.0, "rotation": [0, 0, 0], "position": [0, 0, 0], "scale": 1.0},
        {"t": 1.0, "rotation": [0, math.pi, 0], "position": [0, 0, 0], "scale": 1.0},
    ]


async def run(plan: SitePlan, settings: Settings, log: Logger) -> tuple[str, dict]:
    for obj in plan.objects:
        obj.keyframes = _keyframes(obj.animation)
    await log(f"Authored keyframe tracks for {len(plan.objects)} object(s).")
    return "threejs_keyframes", {"tracks": len(plan.objects)}

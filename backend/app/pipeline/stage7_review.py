"""Stage 7 — Render review.

Drives the optional puppeteer-capture renderer service to screenshot the
generated site, and scores the result against the "씹고퀄" checklist. When no
renderer is configured a static structural review is performed so the stage
always yields a verdict.
"""
from __future__ import annotations

from collections.abc import Awaitable, Callable

import httpx

from ..config import Settings
from ..schemas import SitePlan

Logger = Callable[[str], Awaitable[None]]


def structural_score(plan: SitePlan) -> tuple[float, list[str]]:
    """Heuristic quality score against the planning-doc checklist."""
    notes: list[str] = []
    score = 0.0
    # custom GLSL background present (no flat CSS gradient)
    if plan.background_shader_glsl and "gl_FragColor" in plan.background_shader_glsl:
        score += 0.2
    else:
        notes.append("missing GLSL background")
    # has 3D objects
    if plan.objects:
        score += 0.2
    else:
        notes.append("no 3D objects")
    # scroll-driven camera (path/cinematic present)
    if any(s.camera_preset in ("scroll_dolly", "cinematic_reveal", "top_down_to_perspective") for s in plan.sections):
        score += 0.15
    else:
        notes.append("no scroll-driven camera")
    # professional lighting variety
    if len({s.lighting_preset for s in plan.sections}) >= 1:
        score += 0.15
    # section count (narrative depth)
    if len(plan.sections) >= 3:
        score += 0.15
    else:
        notes.append("fewer than 3 sections")
    # custom typography + palette
    if plan.global_style.typography and len(plan.global_style.color_palette) >= 3:
        score += 0.15
    return round(min(score, 1.0), 3), notes


async def run(plan: SitePlan, settings: Settings, site_url: str, log: Logger) -> tuple[str, dict]:
    score, notes = structural_score(plan)
    preview_image: str | None = None
    provider = "structural_review"

    if settings.renderer_url:
        try:
            async with httpx.AsyncClient(timeout=settings.request_timeout) as client:
                resp = await client.post(
                    f"{settings.renderer_url.rstrip('/')}/capture",
                    json={"url": site_url, "width": 1440, "height": 900},
                )
                resp.raise_for_status()
                data = resp.json()
                preview_image = data.get("image_url") or data.get("image")
                provider = "puppeteer_capture"
                await log("Renderer captured preview screenshot.")
        except Exception as exc:  # noqa: BLE001
            await log(f"Renderer capture skipped ({exc}); using structural review.")

    verdict = "PASS" if score >= settings.review_pass_score else "REVIEW"
    note_str = (" Notes: " + ", ".join(notes)) if notes else ""
    await log(f"Quality score {score:.2f} → {verdict}.{note_str}")
    return provider, {"score": score, "verdict": verdict, "notes": notes, "preview_image": preview_image}

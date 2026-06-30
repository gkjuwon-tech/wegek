"""Stage 4 — Bake: turn Blender's export (exact world coords) into the site spec.

This is the whole point of the pivot: the frontend later reproduces what Blender
actually rendered — real per-act object placements, the real camera path and lights —
not previz approximations. We merge the authored Experience (narrative, palette,
transitions, scroll mapping) with Blender's exported world-space truth.
"""
from __future__ import annotations

from ..schemas import Experience


def bake(exp: Experience, export: dict, frames: list[str], video: str | None) -> dict:
    acts_export = {a["id"]: a for a in export.get("acts", [])}
    acts = []
    for scene in exp.scenes:
        ex = acts_export.get(scene.id, {})
        acts.append({
            "id": scene.id,
            "title": scene.title,
            "narrative": scene.narrative,
            "transition_out": scene.transition_out,
            "palette": scene.palette,
            "hdri": scene.hdri,
            "frame_range": ex.get("frame_range"),
            # exact Blender world-space data (the baked truth)
            "objects": ex.get("objects", []),
            "camera": ex.get("camera", []),
            "lights": ex.get("lights", []),
        })
    return {
        "project_name": exp.project_name,
        "tagline": exp.tagline,
        "mood": exp.mood,
        "scroll_model": "frame_sequence",     # frontend scrubs the rendered frames on scroll
        "frame_count": len(frames),
        "video": video,
        "acts": acts,
        "source": "blender_export",           # not previz
    }

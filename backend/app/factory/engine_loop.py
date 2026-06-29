"""Critique loop for the ENGINE pipeline (spec-driven, not codegen).

build (plan -> shader(RAG) -> scene -> codegen) -> render + screenshot -> critique
the screenshots against an Active-Theory rubric -> REVISE THE PLAN (composition,
shader, effects, scroll) -> rebuild. The LLM tunes the spec, not raw three.js.

Meshes are procedural stand-ins while Tripo is unfunded; the loop is tuning
composition / shader / lighting / effects / scroll, which procedural geometry shows.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from ..config import get_settings
from ..pipeline import stage0_planner, stage4_shaders, stage5_scene, stage6_codegen
from . import llm, render

CRITIC_SYSTEM = """You are a ruthless Awwwards jury art director reviewing scroll-position screenshots of a
generated WebGL site (Active Theory / Lusion / Resn standard). NOTE: the meshes are PLACEHOLDER
procedural primitives (Tripo is offline) — do NOT penalise the mesh shapes themselves. Judge:
composition & spatial design, background shader quality, lighting/exposure (no blown-out white),
depth/atmosphere, colour palette, typography integration, and whether the scene CHANGES across the
scroll screenshots. Return ONLY strict JSON:
{
 "score": 0.0-1.0, "verdict":"PASS|REVISE", "is_blank_or_broken": true/false,
 "strengths":["..."],
 "issues":[{"severity":"critical|major|minor","observation":"...","fix":"specific spec-level change"}],
 "spec_fixes":{"effects":"e.g. bloom too hot, lower strength to ~0.25","shader":"e.g. too busy/grid-like, want soft nebula","composition":"e.g. hero too small / off-centre / no depth","scroll":"e.g. scene doesn't change between beats"},
 "next_actions":["prioritised concrete changes"]
}
Be harsh; PASS only >= 0.85. Blown-out white, flat grid backgrounds, scattered/undesigned layout,
or no scene change across scroll all score below 0.5."""

REVISE_SYSTEM = stage0_planner.PLANNER_SYSTEM + """

You are REVISING an existing plan to fix an art director's critique. Keep what works; change the
JSON to address every spec_fix — tune effects (bloom/exposure/fog/grade), recompose object
placements (symmetry, depth, hero scale/position), pick a calmer background_shader if the bg is
weak, and make objects' scroll_in/scroll_out create real scene changes. Return the full improved plan JSON."""


async def _build(plan, settings, job: str, log) -> Path:
    await stage4_shaders.run(plan, settings, log)        # background shader (GLSL RAG)
    await stage5_scene.run(plan, settings, log)
    _, meta = await stage6_codegen.run(plan, settings, job, log)
    return Path(meta["path"]).parent


async def _alog(msg, level="info"):
    print(f"   · {msg}", flush=True)


def run(brief: str, job: str, *, max_iters: int = 3, pass_score: float = 0.85, log=print) -> dict:
    settings = get_settings()
    log("· planning (RAG-grounded)…")
    plan, prov = asyncio.run(stage0_planner.run(brief, settings, brand_mood=None, max_objects=12))
    log(f"· plan: {prov}, {len(plan.objects)} meshes, {len(plan.sections)} beats")

    best: dict[str, Any] = {"score": -1.0}
    history = []
    critique = None
    for it in range(1, max_iters + 1):
        site_dir = asyncio.run(_build(plan, settings, job, _alog))
        shots = settings.sites_dir / job / "_shots"
        shots.mkdir(exist_ok=True)
        r = render.render(site_dir, str(shots / f"i{it}"), shots=4)
        log(f"[iter {it}] ready={r['ready']} errors={len(r['errors'])} shots={len(r['images'])}")

        crit_user = (
            f"BRIEF:\n{brief}\n\nConsole errors: {json.dumps(r['errors'])[:300]} ready={r['ready']}. "
            "Screenshots are in scroll order (top → bottom)."
        )
        try:
            critique = llm.parse_json(llm.complete_with_images(CRITIC_SYSTEM, crit_user, r["images"], max_tokens=2500))
        except Exception as exc:  # noqa: BLE001
            critique = {"score": 0.0, "verdict": "REVISE", "is_blank_or_broken": True,
                        "issues": [{"severity": "critical", "observation": f"critic failed: {exc}"}],
                        "spec_fixes": {}, "next_actions": ["make it render"]}
        score = float(critique.get("score", 0.0))
        if r["errors"] or not r["ready"] or critique.get("is_blank_or_broken"):
            score = min(score, 0.4)
        critique["score"] = score
        log(f"[iter {it}] score={score:.2f} verdict={critique.get('verdict')}")
        for key, val in (critique.get("spec_fixes") or {}).items():
            log(f"     fix.{key}: {val}")

        history.append({"iter": it, "score": score, "ready": r["ready"]})
        if score > best["score"]:
            best = {"score": score, "iter": it, "plan": plan.model_dump(), "images": list(r["images"])}
            (site_dir / "index.best.html").write_text((site_dir / "index.html").read_text(), encoding="utf-8")

        if score >= pass_score and r["ready"] and not r["errors"]:
            log(f"PASS at iter {it} ({score:.2f})")
            break
        if it < max_iters:
            log(f"[iter {it}] revising plan from critique…")
            try:
                data = llm.parse_json(llm.complete(
                    REVISE_SYSTEM,
                    f"BRIEF: {brief}\n\nCRITIQUE:\n{json.dumps(critique, indent=1)}\n\n"
                    f"CURRENT PLAN:\n{json.dumps(plan.model_dump(), default=str)[:14000]}\n\n"
                    "Return the full improved plan JSON.",
                    max_tokens=24000,
                ))
                plan = stage0_planner._coerce_plan(data, brief, None, 12)
            except Exception as exc:  # noqa: BLE001
                log(f"     revise failed ({exc}); keeping current plan.")

    (settings.sites_dir / job / "loop_report.json").write_text(
        json.dumps({"brief": brief, "best_score": best["score"], "best_iter": best.get("iter"),
                    "history": history}, indent=2), encoding="utf-8")
    log(f"DONE best={best['score']:.2f} @ iter {best.get('iter')}")
    return {"best": best, "history": history, "site_dir": str(settings.sites_dir / job)}

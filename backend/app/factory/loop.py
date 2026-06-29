"""The generate -> render -> critique -> repair loop, with free-asset sourcing."""
from __future__ import annotations

import json
import os
import shutil
import time
from pathlib import Path
from typing import Any

from . import assets, llm, prompts, render

TEMPLATES = Path(__file__).resolve().parent.parent / "pipeline" / "templates"
VENDOR = TEMPLATES / "vendor"
# TEMP test scaffold: "objaverse" sources free GLBs for AI-requested meshes while
# Tripo is down; "none" falls back to a single provided GLB. Flip to revert.
ASSET_SOURCE = os.environ.get("FACTORY_ASSET_SOURCE", "objaverse")


def _prepare_site(site_dir: Path) -> None:
    site_dir.mkdir(parents=True, exist_ok=True)
    if VENDOR.is_dir():
        shutil.copytree(VENDOR, site_dir / "vendor", dirs_exist_ok=True)


def _plan_assets(concept: str, site_dir: Path, fallback_glb: Path | None, log) -> list[dict[str, Any]]:
    """Turn the concept into a list of resolved, downloaded GLB assets."""
    if ASSET_SOURCE != "objaverse":
        if fallback_glb and fallback_glb.exists():
            (site_dir / "models").mkdir(parents=True, exist_ok=True)
            shutil.copy(fallback_glb, site_dir / "models" / "hero.glb")
            return [{"id": "hero", "path": "models/hero.glb", "role": "hero product"}]
        return []
    try:
        manifest = llm.parse_json(llm.complete(prompts.ASSET_PLAN_SYSTEM, f"CONCEPT:\n{concept}", max_tokens=2000))
        wanted = manifest.get("assets", [])[:12]
    except Exception as exc:  # noqa: BLE001
        log(f"· asset-plan failed ({exc}); using fallback hero only.")
        wanted = []
    resolved: list[dict[str, Any]] = []
    for a in wanted:
        aid = str(a.get("id") or f"asset{len(resolved)}")
        q = str(a.get("query") or a.get("role") or aid)
        got = assets.resolve(q, site_dir, aid)
        if got:
            got["role"] = a.get("role", "")
            resolved.append(got)
            log(f"· asset '{aid}' <- objaverse[{got['category']}] for query {q!r}")
        else:
            log(f"· asset '{aid}' NOT FOUND for query {q!r}")
    if not resolved and fallback_glb and fallback_glb.exists():
        (site_dir / "models").mkdir(parents=True, exist_ok=True)
        shutil.copy(fallback_glb, site_dir / "models" / "hero.glb")
        resolved = [{"id": "hero", "path": "models/hero.glb", "role": "hero product"}]
    return resolved


def _asset_block(assets_list: list[dict[str, Any]]) -> str:
    lines = [f'- id="{a["id"]}"  path="{a["path"]}"  is: {a.get("role", "")}' for a in assets_list]
    return "AVAILABLE GLB ASSETS (load these by path):\n" + "\n".join(lines)


def _reresolve(assets_list: list[dict[str, Any]], feedback: list[dict], site_dir: Path, log) -> bool:
    """Swap out any asset the critic flagged as the wrong object. Returns True if changed."""
    if ASSET_SOURCE != "objaverse":
        return False
    changed = False
    by_id = {a["id"]: a for a in assets_list}
    for fb in feedback or []:
        if fb.get("ok") is False and fb.get("id") in by_id:
            a = by_id[fb["id"]]
            got = assets.resolve(a.get("query", a["id"]), site_dir, a["id"], exclude={a.get("uid", "")})
            if got:
                got["role"] = a.get("role", "")
                a.update(got)
                changed = True
                log(f"· re-sourced '{a['id']}' (was wrong: {fb.get('reason', '')[:60]})")
    return changed


def run(brief: str, site_dir: str | Path, *, glb: str | Path | None = None,
        max_iters: int = 6, pass_score: float = 0.85, log=print) -> dict:
    site_dir = Path(site_dir)
    _prepare_site(site_dir)
    shots_dir = site_dir / "_shots"
    shots_dir.mkdir(exist_ok=True)

    log("· concept: directing…")
    concept = llm.complete(prompts.CONCEPT_SYSTEM, f"Brief:\n{brief}", max_tokens=6000)
    log(f"· concept ready ({len(concept)} chars)")

    asset_list = _plan_assets(concept, site_dir, Path(glb) if glb else None, log)
    log(f"· {len(asset_list)} asset(s) sourced")

    history: list[dict[str, Any]] = []
    best: dict[str, Any] = {"score": -1.0}
    code = None
    critique = None
    errors: list[str] = []

    for it in range(1, max_iters + 1):
        t0 = time.time()
        asset_block = _asset_block(asset_list)
        if code is None:
            log(f"[iter {it}] generating site code…")
            code = llm.strip_html(llm.complete(
                prompts.CODEGEN_SYSTEM,
                f"CONCEPT BIBLE:\n{concept}\n\n{asset_block}\n\nBuild the complete index.html now.",
                max_tokens=48000,
            ))
        else:
            log(f"[iter {it}] repairing (errors={len(errors)}, prev_score={critique.get('score') if critique else 'NA'})…")
            code = llm.strip_html(llm.complete(prompts.REPAIR_SYSTEM, (
                f"CONCEPT BIBLE:\n{concept}\n\n{asset_block}\n\n"
                f"CONSOLE ERRORS:\n{json.dumps(errors, indent=2)}\n\n"
                f"ART DIRECTOR CRITIQUE:\n{json.dumps(critique, indent=2) if critique else 'n/a'}\n\n"
                f"CURRENT index.html:\n{code}\n\nReturn the full corrected index.html."
            ), max_tokens=48000))

        (site_dir / "index.html").write_text(code, encoding="utf-8")

        log(f"[iter {it}] rendering + screenshotting…")
        r = render.render(site_dir, str(shots_dir / f"i{it}"), shots=4)
        errors = r["errors"]
        log(f"[iter {it}] ready={r['ready']} errors={len(errors)} shots={len(r['images'])}")

        log(f"[iter {it}] critiquing…")
        crit_user = (
            f"BRIEF:\n{brief}\n\n{_asset_block(asset_list)}\n\n"
            f"Console errors: {json.dumps(errors)} ready_flag={r['ready']}. Judge the screenshots in scroll order."
        )
        try:
            critique = llm.parse_json(llm.complete_with_images(
                prompts.CRITIC_SYSTEM, crit_user, r["images"], max_tokens=3000))
        except Exception as exc:  # noqa: BLE001
            critique = {"score": 0.0, "verdict": "REVISE", "is_blank_or_broken": True,
                        "issues": [{"severity": "critical", "observation": f"critic failed: {exc}"}],
                        "asset_feedback": [], "next_actions": ["make it render so a critique is possible"]}
        score = float(critique.get("score", 0.0))
        if errors or not r["ready"] or critique.get("is_blank_or_broken"):
            score = min(score, 0.4)
        critique["score"] = score
        log(f"[iter {it}] score={score:.2f} verdict={critique.get('verdict')} ({int(time.time() - t0)}s)")
        for iss in (critique.get("issues") or [])[:4]:
            log(f"     - [{iss.get('severity')}] {iss.get('observation')}")

        _reresolve(asset_list, critique.get("asset_feedback") or [], site_dir, log)

        history.append({"iter": it, "score": score, "errors": len(errors), "ready": r["ready"]})
        if score > best["score"]:
            best = {"score": score, "iter": it, "html": code, "critique": critique, "images": list(r["images"])}
            (site_dir / "index.best.html").write_text(code, encoding="utf-8")

        if score >= pass_score and not errors and r["ready"]:
            log(f"PASS at iter {it} (score {score:.2f}).")
            break

    if best.get("html"):
        (site_dir / "index.html").write_text(best["html"], encoding="utf-8")
    (site_dir / "factory_report.json").write_text(json.dumps(
        {"brief": brief, "assets": asset_list, "best_score": best["score"],
         "best_iter": best.get("iter"), "history": history, "concept": concept}, indent=2), encoding="utf-8")
    log(f"DONE. best score={best['score']:.2f} @ iter {best.get('iter')}")
    return {"best": best, "history": history, "site_dir": str(site_dir), "assets": asset_list}

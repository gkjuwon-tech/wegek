"""The generate -> render -> critique -> repair loop."""
from __future__ import annotations

import json
import shutil
import time
from pathlib import Path
from typing import Any

from . import llm, prompts, render

TEMPLATES = Path(__file__).resolve().parent.parent / "pipeline" / "templates"
VENDOR = TEMPLATES / "vendor"


def _prepare_site(site_dir: Path, glb_src: Path | None) -> None:
    site_dir.mkdir(parents=True, exist_ok=True)
    if VENDOR.is_dir():
        shutil.copytree(VENDOR, site_dir / "vendor", dirs_exist_ok=True)
    if glb_src and glb_src.exists():
        (site_dir / "models").mkdir(exist_ok=True)
        shutil.copy(glb_src, site_dir / "models" / "sneaker.glb")


def run(brief: str, site_dir: str | Path, *, glb: str | Path | None = None,
        max_iters: int = 6, pass_score: float = 0.85, log=print) -> dict:
    site_dir = Path(site_dir)
    glb_src = Path(glb) if glb else None
    _prepare_site(site_dir, glb_src)
    shots_dir = site_dir / "_shots"
    shots_dir.mkdir(exist_ok=True)

    log("· concept: directing…")
    concept = llm.complete(prompts.CONCEPT_SYSTEM, f"Brief:\n{brief}", max_tokens=6000)
    log(f"· concept ready ({len(concept)} chars)")

    history: list[dict[str, Any]] = []
    best: dict[str, Any] = {"score": -1.0}
    code = None
    critique = None
    errors: list[str] = []

    for it in range(1, max_iters + 1):
        t0 = time.time()
        if code is None:
            log(f"[iter {it}] generating site code…")
            code = llm.strip_html(llm.complete(
                prompts.CODEGEN_SYSTEM,
                f"CONCEPT BIBLE:\n{concept}\n\nBuild the complete index.html now.",
                max_tokens=48000,
            ))
        else:
            log(f"[iter {it}] repairing (errors={len(errors)}, prev_score={critique.get('score') if critique else 'NA'})…")
            repair_user = (
                f"CONCEPT BIBLE:\n{concept}\n\n"
                f"CONSOLE ERRORS:\n{json.dumps(errors, indent=2)}\n\n"
                f"ART DIRECTOR CRITIQUE:\n{json.dumps(critique, indent=2) if critique else 'n/a'}\n\n"
                f"CURRENT index.html:\n{code}\n\nReturn the full corrected index.html."
            )
            code = llm.strip_html(llm.complete(prompts.REPAIR_SYSTEM, repair_user, max_tokens=48000))

        (site_dir / "index.html").write_text(code, encoding="utf-8")

        log(f"[iter {it}] rendering + screenshotting…")
        r = render.render(site_dir, str(shots_dir / f"i{it}"), shots=4)
        errors = r["errors"]
        log(f"[iter {it}] ready={r['ready']} errors={len(errors)} shots={len(r['images'])}")

        log(f"[iter {it}] critiquing screenshots…")
        crit_user = (
            f"BRIEF:\n{brief}\n\nConsole errors during render: {json.dumps(errors)}\n"
            f"ready_flag={r['ready']}. Judge the screenshots (in scroll order)."
        )
        try:
            critique = llm.parse_json(llm.complete_with_images(
                prompts.CRITIC_SYSTEM, crit_user, r["images"], max_tokens=3000))
        except Exception as exc:  # noqa: BLE001
            critique = {"score": 0.0, "verdict": "REVISE", "is_blank_or_broken": True,
                        "issues": [{"severity": "critical", "observation": f"critic failed: {exc}", "fix": "retry"}],
                        "next_actions": ["fix render so a critique can be produced"]}
        score = float(critique.get("score", 0.0))
        # broken/blank or console errors hard-cap the score
        if errors or not r["ready"] or critique.get("is_blank_or_broken"):
            score = min(score, 0.4)
        critique["score"] = score
        dt = int(time.time() - t0)
        log(f"[iter {it}] score={score:.2f} verdict={critique.get('verdict')} ({dt}s)")
        for iss in (critique.get("issues") or [])[:4]:
            log(f"     - [{iss.get('severity')}] {iss.get('observation')}")

        history.append({"iter": it, "score": score, "errors": len(errors),
                        "ready": r["ready"], "verdict": critique.get("verdict")})
        if score > best["score"]:
            best = {"score": score, "iter": it, "html": code, "critique": critique,
                    "images": list(r["images"])}
            (site_dir / "index.best.html").write_text(code, encoding="utf-8")

        if score >= pass_score and not errors and r["ready"]:
            log(f"PASS at iter {it} (score {score:.2f}).")
            break

    # leave the best version as the served index.html
    if best.get("html"):
        (site_dir / "index.html").write_text(best["html"], encoding="utf-8")
    (site_dir / "factory_report.json").write_text(
        json.dumps({"brief": brief, "best_score": best["score"], "best_iter": best.get("iter"),
                    "history": history, "concept": concept}, indent=2), encoding="utf-8")
    log(f"DONE. best score={best['score']:.2f} @ iter {best.get('iter')}")
    return {"best": best, "history": history, "site_dir": str(site_dir)}

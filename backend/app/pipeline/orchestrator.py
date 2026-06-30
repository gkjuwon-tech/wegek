"""Orchestrator — runs a job end to end with the SOLID-preview feedback loop.

plan -> meshes (Tripo) -> [ build SOLID preview -> critique -> revise ]xN -> final
Cycles render -> bake exact coords. The loop re-renders a fast solid preview after
every revision so the state is visible at each step (no blind code-guessing).
"""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from ..clients.llm import LLMClient
from ..config import Settings
from ..schemas import Experience, Job, JobStatus, Stage, StageResult
from . import bake, blender_build, meshes, plan

CRITIC_SYSTEM = """You are an Awwwards art director reviewing FAST SOLID preview frames (one per scene/act,
in scroll order) of a 3-scene Blender experience. Materials/lighting are NOT final — judge only
composition, object placement & scale, depth/staging, camera framing per act, and whether the
three acts read as distinct, deliberately-composed sets that would hand off well on scroll.
Return ONLY JSON: {"score":0.0-1.0,"verdict":"PASS|REVISE","issues":[{"severity":"...","observation":"...","fix":"..."}],"next_actions":["..."]}
Be harsh; PASS only >= 0.82. Empty/sparse/scattered or flat staging scores below 0.5."""

Saver = Callable[[Job], Awaitable[None]]


async def run_job(job: Job, settings: Settings, save: Saver, *, max_iters: int = 3, pass_score: float = 0.82) -> None:
    job.status = JobStatus.RUNNING
    job.stages = [StageResult(stage=s) for s in Stage]

    async def log(msg: str) -> None:
        job.logs.append(msg)
        await save(job)

    def sr(stage: Stage) -> StageResult:
        return next(s for s in job.stages if s.stage == stage)

    try:
        # 1) plan
        sr(Stage.PLAN).status = "running"
        await save(job)
        exp, prov = await plan.run(job.prompt, settings, mood=None)
        job.experience = exp
        sr(Stage.PLAN).status = "done"
        sr(Stage.PLAN).detail = f"{prov} · 3 scenes"
        await log(f"Planned '{exp.project_name}' ({prov}).")

        # 2) meshes (Tripo)
        sr(Stage.MESHES).status = "running"
        await save(job)
        _, meta = await meshes.run(exp, settings, log)
        sr(Stage.MESHES).status = "done"
        sr(Stage.MESHES).meta = meta
        await log(f"Meshes: {meta}")

        # 3) Blender feedback loop (SOLID previews)
        sr(Stage.BLENDER).status = "running"
        await save(job)
        llm = LLMClient(settings)
        for it in range(1, max_iters + 1):
            pre = await blender_build.run(exp, settings, job.id, "preview", log)
            critique: dict[str, Any] = {"score": 0.0, "verdict": "REVISE"}
            if llm.available and pre["frames"]:
                try:
                    critique = await llm.critique_images(
                        CRITIC_SYSTEM,
                        f"Project: {exp.project_name}. Mood: {exp.mood}. Frames are act1→act3.",
                        pre["frames"])
                except Exception as exc:  # noqa: BLE001
                    await log(f"critique failed ({exc})")
            score = float(critique.get("score", 0.0))
            if not pre["ok"]:
                score = min(score, 0.3)
            sr(Stage.BLENDER).meta = {"iter": it, "score": score, "verdict": critique.get("verdict")}
            await log(f"[preview {it}] score={score:.2f} verdict={critique.get('verdict')}")
            for iss in (critique.get("issues") or [])[:3]:
                await log(f"   - {iss.get('observation')}")
            if score >= pass_score or it == max_iters:
                break
            exp = await plan.revise(exp, critique, settings)
            job.experience = exp
            await log(f"[preview {it}] revised plan from critique.")

        # 4) final Cycles render + video
        fin = await blender_build.run(exp, settings, job.id, "final", log)
        video = blender_build.encode_video(fin["out_dir"], f"{fin['out_dir']}/scroll.mp4")
        sr(Stage.BLENDER).status = "done"
        await log(f"Final render: {len(fin['frames'])} frames; video={'yes' if video else 'no'}.")

        # 5) bake exact coords -> site spec
        sr(Stage.BAKE).status = "running"
        await save(job)
        job.baked_spec = bake.bake(exp, fin["export"], fin["frames"], video)
        sr(Stage.BAKE).status = "done"
        await log("Baked Blender export into site spec.")

        job.status = JobStatus.SUCCEEDED
    except Exception as exc:  # noqa: BLE001
        job.status = JobStatus.FAILED
        job.error = f"{type(exc).__name__}: {exc}"
        await log(f"FAILED: {job.error}")
    await save(job)


# convenience for a synchronous driver / tests
async def plan_only(prompt: str, settings: Settings) -> Experience:
    exp, _ = await plan.run(prompt, settings, mood=None)
    return exp

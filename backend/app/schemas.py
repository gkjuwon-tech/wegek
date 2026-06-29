"""Pydantic schemas: the contract that flows through the WEGEK pipeline.

The `SitePlan` is the structured artifact emitted by Stage 0 and progressively
enriched by every downstream stage until Stage 6 turns it into a website.
"""
from __future__ import annotations

import time
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


# --------------------------------------------------------------------------- #
# Pipeline stages & job lifecycle
# --------------------------------------------------------------------------- #
class Stage(StrEnum):
    PLAN = "plan"            # Stage 0
    IMAGES = "images"        # Stage 1
    MODELS = "models"        # Stage 2
    ANIMATE = "animate"      # Stage 3
    SHADERS = "shaders"      # Stage 4
    SCENE = "scene"          # Stage 5
    CODEGEN = "codegen"      # Stage 6
    REVIEW = "review"        # Stage 7


STAGE_ORDER: list[Stage] = [
    Stage.PLAN,
    Stage.IMAGES,
    Stage.MODELS,
    Stage.ANIMATE,
    Stage.SHADERS,
    Stage.SCENE,
    Stage.CODEGEN,
    Stage.REVIEW,
]

STAGE_LABELS: dict[Stage, str] = {
    Stage.PLAN: "Stage 0 · Planner AI",
    Stage.IMAGES: "Stage 1 · Reference Images",
    Stage.MODELS: "Stage 2 · Image → 3D",
    Stage.ANIMATE: "Stage 3 · Rig & Animate",
    Stage.SHADERS: "Stage 4 · GLSL Background",
    Stage.SCENE: "Stage 5 · Scene Assembly",
    Stage.CODEGEN: "Stage 6 · DOM & Frontend",
    Stage.REVIEW: "Stage 7 · Render Review",
}


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


# --------------------------------------------------------------------------- #
# Site plan (Stage 0 output)
# --------------------------------------------------------------------------- #
class Object3D(BaseModel):
    id: str
    description: str
    category: str = "tech"
    animation: str = "slow_rotation_y"
    needs_parts_separation: bool = False
    # enriched downstream
    reference_images: list[str] = Field(default_factory=list)
    model_url: str | None = None
    model_format: str = "procedural"  # "procedural" | "glb"
    primitive: str | None = None       # procedural geometry hint
    color: str | None = None
    keyframes: list[dict[str, Any]] = Field(default_factory=list)


class Section(BaseModel):
    id: str
    type: str = "3d_product_showcase"
    headline: str = ""
    subcopy: str = ""
    body: str = ""
    objects: list[str] = Field(default_factory=list)
    camera_preset: str = "orbit_showcase"
    lighting_preset: str = "studio_dramatic"
    scroll_behavior: str = "zoom_in_with_rotation"
    dom_overlay: bool = True


class GlobalStyle(BaseModel):
    color_palette: list[str] = Field(
        default_factory=lambda: ["#0a0a0f", "#e94560", "#0f3460", "#f5f5f7"]
    )
    typography: str = "modern_sans"
    background_shader: str = "gradient_noise_dark"
    accent: str = "#e94560"
    scroll_engine: str = "lenis_gsap"
    engine: str = "three_r3f"


class SitePlan(BaseModel):
    project_name: str
    tagline: str = ""
    brand_mood: str = "premium"
    sections: list[Section] = Field(default_factory=list)
    objects: list[Object3D] = Field(default_factory=list)
    global_style: GlobalStyle = Field(default_factory=GlobalStyle)
    # enriched at Stage 4
    background_shader_glsl: str | None = None

    def object_by_id(self, oid: str) -> Object3D | None:
        return next((o for o in self.objects if o.id == oid), None)


# --------------------------------------------------------------------------- #
# Jobs
# --------------------------------------------------------------------------- #
class StageResult(BaseModel):
    stage: Stage
    status: str = "pending"  # pending | running | done | skipped | failed
    detail: str = ""
    provider: str = ""       # which backend (llm/flux/tripo/procedural) was used
    started_at: float | None = None
    finished_at: float | None = None
    meta: dict[str, Any] = Field(default_factory=dict)


class CreateJobRequest(BaseModel):
    prompt: str = Field(..., min_length=3, max_length=4000)
    brand_mood: str | None = None
    max_objects: int | None = Field(default=None, ge=1, le=12)


class LogEntry(BaseModel):
    ts: float = Field(default_factory=time.time)
    stage: Stage | None = None
    level: str = "info"
    message: str


class Job(BaseModel):
    id: str
    prompt: str
    status: JobStatus = JobStatus.QUEUED
    created_at: float = Field(default_factory=time.time)
    updated_at: float = Field(default_factory=time.time)
    current_stage: Stage | None = None
    stages: list[StageResult] = Field(default_factory=list)
    plan: SitePlan | None = None
    site_url: str | None = None
    bundle_path: str | None = None
    preview_image: str | None = None
    review_score: float | None = None
    error: str | None = None
    logs: list[LogEntry] = Field(default_factory=list)

    def stage_result(self, stage: Stage) -> StageResult:
        for s in self.stages:
            if s.stage == stage:
                return s
        sr = StageResult(stage=stage)
        self.stages.append(sr)
        return sr


class JobSummary(BaseModel):
    id: str
    prompt: str
    status: JobStatus
    created_at: float
    updated_at: float
    current_stage: Stage | None = None
    site_url: str | None = None
    review_score: float | None = None

"""WEGEK v2 schemas — the contract the AI art-directs and Blender realizes.

An Experience is exactly three Scenes that hand off on scroll (Active-Theory grammar).
Every Scene declares its meshes (sourced from Tripo), their keyframed animation, a
camera move, lighting (incl. rim lights) and an HDRI. The same structure is later
re-populated with the *exact* coordinates Blender exports (see pipeline/bake.py).
"""
from __future__ import annotations

import time
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

Vec3 = list[float]


# --------------------------------------------------------------------------- #
# Scene description (Stage: plan)
# --------------------------------------------------------------------------- #
class Keyframe(BaseModel):
    """A pose at scene-local scroll t in [0,1]."""
    t: float = 0.0
    position: Vec3 = Field(default_factory=lambda: [0.0, 0.0, 0.0])
    rotation: Vec3 = Field(default_factory=lambda: [0.0, 0.0, 0.0])  # euler radians
    scale: float = 1.0


class SceneObject(BaseModel):
    id: str
    description: str = ""
    # what Tripo should make (clean noun phrase) and how the reference image looks
    mesh_query: str = ""
    is_hero: bool = False
    # static placement in the scene + keyframed motion across the scene's scroll
    position: Vec3 = Field(default_factory=lambda: [0.0, 0.0, 0.0])
    rotation: Vec3 = Field(default_factory=lambda: [0.0, 0.0, 0.0])
    scale: float = 1.0
    keyframes: list[Keyframe] = Field(default_factory=list)
    material: str = "chrome"  # chrome|glass|matte|emissive (Blender material preset)
    # enriched by the meshes stage
    model_url: str | None = None
    model_local: str | None = None


class CameraKey(BaseModel):
    t: float = 0.0
    position: Vec3 = Field(default_factory=lambda: [0.0, -7.0, 2.0])
    look_at: Vec3 = Field(default_factory=lambda: [0.0, 0.0, 0.0])
    fov: float = 45.0


class Light(BaseModel):
    type: str = "area"  # area|sun|point|spot
    position: Vec3 = Field(default_factory=lambda: [4.0, -4.0, 5.0])
    energy: float = 1000.0
    color: str = "#ffffff"
    size: float = 5.0
    is_rim: bool = False


class Scene(BaseModel):
    id: str
    title: str = ""
    narrative: str = ""
    objects: list[SceneObject] = Field(default_factory=list)
    camera: list[CameraKey] = Field(default_factory=list)
    lights: list[Light] = Field(default_factory=list)
    hdri: str = "studio"          # named HDRI/world preset
    palette: list[str] = Field(default_factory=lambda: ["#06080d", "#00e5ff", "#a06bff", "#eef6ff"])
    # how this scene leaves toward the next (Active-Theory hand-off)
    transition_out: str = "camera_fly"  # camera_fly|dissolve|push_through|morph


class Experience(BaseModel):
    project_name: str
    tagline: str = ""
    mood: str = "premium neon-noir"
    scenes: list[Scene] = Field(default_factory=list)  # exactly 3

    def all_objects(self) -> list[SceneObject]:
        return [o for s in self.scenes for o in s.objects]


# --------------------------------------------------------------------------- #
# Job lifecycle
# --------------------------------------------------------------------------- #
class Stage(StrEnum):
    PLAN = "plan"            # design the 3-scene experience
    MESHES = "meshes"        # outsource meshes to Tripo
    BLENDER = "blender"      # build + render + export the scenes in Blender
    BAKE = "bake"            # bake exact Blender coords into the site spec


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class StageResult(BaseModel):
    stage: Stage
    status: str = "pending"
    detail: str = ""
    meta: dict[str, Any] = Field(default_factory=dict)


class CreateJobRequest(BaseModel):
    prompt: str = Field(..., min_length=3, max_length=4000)
    mood: str | None = None


class Job(BaseModel):
    id: str
    prompt: str
    status: JobStatus = JobStatus.QUEUED
    created_at: float = Field(default_factory=time.time)
    updated_at: float = Field(default_factory=time.time)
    stages: list[StageResult] = Field(default_factory=list)
    experience: Experience | None = None
    baked_spec: dict[str, Any] | None = None
    error: str | None = None
    logs: list[str] = Field(default_factory=list)

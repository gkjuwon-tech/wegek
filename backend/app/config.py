"""Configuration for the WEGEK v2 backend."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = BACKEND_ROOT.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(REPO_ROOT / ".env", BACKEND_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    host: str = "0.0.0.0"
    port: int = 8000
    cors_origins: str = "*"

    data_dir: Path = Field(default=BACKEND_ROOT / "_data")

    # Planner LLM (Gemini OpenAI-compatible surface; absent key -> heuristic plan)
    gemini_api_key: str | None = None
    gemini_base_url: str = "https://generativelanguage.googleapis.com/v1beta"
    gemini_model: str = "gemini-3.5-flash"
    gemini_image_model: str = "gemini-3.1-flash-image"

    # mesh source: "tripo" (real meshes) or "box" (placeholder cubes for fast
    # iteration on composition / scroll / animation regardless of mesh quality)
    mesh_mode: str = "tripo"

    # Tripo (mesh outsourcing: image -> 3D)
    tripo_api_key: str | None = None
    tripo_base_url: str = "https://api.tripo3d.ai/v2/openapi"
    tripo_model_version: str = "v2.5-20250123"
    tripo_texture_quality: str = "detailed"

    # Blender render host
    blender_python: str = "python"   # interpreter that has the `bpy` module
    render_samples: int = 24
    render_width: int = 1280
    render_height: int = 720
    frames_per_scene: int = 48
    hdri_dir: Path = Field(default=BACKEND_ROOT / "_data" / "hdri")

    request_timeout: float = 120.0
    poll_interval: float = 3.0
    poll_timeout: float = 600.0

    @property
    def jobs_dir(self) -> Path:
        return self.data_dir / "jobs"

    @property
    def assets_dir(self) -> Path:
        return self.data_dir / "assets"

    @property
    def renders_dir(self) -> Path:
        return self.data_dir / "renders"

    def ensure_dirs(self) -> None:
        for d in (self.data_dir, self.jobs_dir, self.assets_dir, self.renders_dir, self.hdri_dir):
            d.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    s.ensure_dirs()
    return s

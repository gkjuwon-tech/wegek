"""Application configuration loaded from environment / .env.

All external integrations are optional: when an API key is absent the pipeline
transparently falls back to deterministic procedural generation so the factory
always produces a runnable 3D website.
"""
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

    # --- Server ---
    host: str = "0.0.0.0"
    port: int = 8000
    cors_origins: str = "*"
    log_level: str = "INFO"

    # --- Storage ---
    data_dir: Path = Field(default=BACKEND_ROOT / "_data")

    # --- Stage 0: Planner LLM ---
    # Provider auto-detected from available keys. "auto" picks anthropic > openai > heuristic.
    planner_provider: str = "auto"
    anthropic_api_key: str | None = None
    anthropic_model: str = "claude-sonnet-4-20250514"
    openai_api_key: str | None = None
    openai_model: str = "gpt-4o"
    openai_base_url: str = "https://api.openai.com/v1"

    # --- Stage 1: Image generation (Black Forest Labs FLUX.2) ---
    bfl_api_key: str | None = None
    bfl_base_url: str = "https://api.bfl.ai/v1"
    bfl_model: str = "flux-pro-1.1"

    # --- Stage 2/3: 3D model generation + rigging (Tripo) ---
    tripo_api_key: str | None = None
    tripo_base_url: str = "https://api.tripo3d.ai/v2/openapi"
    tripo_model_version: str = "v2.5-20250123"

    # --- Stage 4: Shader generation (reuses planner LLM) ---
    shader_use_llm: bool = True

    # --- Stage 7: Render review loop ---
    renderer_url: str | None = None  # e.g. http://localhost:8200
    review_max_iterations: int = 3
    review_pass_score: float = 0.78

    # --- Pipeline behaviour ---
    max_objects_per_site: int = 8
    request_timeout: float = 120.0
    poll_interval: float = 2.0
    poll_timeout: float = 300.0

    @property
    def jobs_dir(self) -> Path:
        return self.data_dir / "jobs"

    @property
    def sites_dir(self) -> Path:
        return self.data_dir / "sites"

    @property
    def db_path(self) -> Path:
        return self.data_dir / "wegek.db"

    def ensure_dirs(self) -> None:
        for d in (self.data_dir, self.jobs_dir, self.sites_dir):
            d.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.ensure_dirs()
    return settings

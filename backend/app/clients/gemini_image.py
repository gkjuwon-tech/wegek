"""Gemini image-generation client (Stage 1, optional).

Generates a reference product image per object via the Gemini `generateContent`
endpoint and writes the returned bytes to disk, returning local file paths. These
paths are consumed by Stage 2 (Tripo), which uploads them to obtain a 3D model —
so unlike FLUX (which returns hosted URLs), the bytes never need a public host.

Entirely opt-in: `available` is False without a Gemini key, leaving the FLUX
path and procedural fallback untouched.
"""
from __future__ import annotations

import base64
import uuid

import httpx

from ..config import Settings

PROMPT_SUFFIX = (
    ", single hero product, three-quarter 45 degree angle, centered, isolated on a "
    "pure white seamless background, studio product photography, soft shadows, "
    "high detail, photorealistic, no text, no watermark"
)


class GeminiImageClient:
    def __init__(self, settings: Settings) -> None:
        self.s = settings

    @property
    def available(self) -> bool:
        return bool(self.s.gemini_api_key)

    @property
    def label(self) -> str:
        return f"gemini:{self.s.gemini_image_model}" if self.available else "none"

    async def generate_views(self, description: str) -> list[str]:
        """Return local file path(s) to generated reference image(s)."""
        if not self.available:
            raise RuntimeError("no Gemini API key configured")
        async with httpx.AsyncClient(timeout=self.s.request_timeout) as client:
            path = await self._one(client, description + PROMPT_SUFFIX)
            return [path]

    async def _one(self, client: httpx.AsyncClient, prompt: str) -> str:
        resp = await client.post(
            f"{self.s.gemini_base_url}/models/{self.s.gemini_image_model}:generateContent",
            headers={"x-goog-api-key": self.s.gemini_api_key or "", "Content-Type": "application/json"},
            json={"contents": [{"parts": [{"text": prompt}]}]},
        )
        resp.raise_for_status()
        data = resp.json()
        for cand in data.get("candidates", []):
            for part in cand.get("content", {}).get("parts", []):
                inline = part.get("inlineData") or part.get("inline_data")
                if inline and inline.get("data"):
                    return self._save(inline["data"], inline.get("mimeType", "image/png"))
        raise RuntimeError("Gemini response had no image data")

    def _save(self, b64: str, mime: str) -> str:
        ext = "png" if "png" in mime else "jpg"
        self.s.refimg_dir.mkdir(parents=True, exist_ok=True)
        path = self.s.refimg_dir / f"{uuid.uuid4().hex}.{ext}"
        path.write_bytes(base64.b64decode(b64))
        return str(path)

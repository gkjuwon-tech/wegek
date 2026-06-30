"""Gemini client — planner (chat) + reference-image generation for Tripo.

Uses Gemini's OpenAI-compatible chat surface for planning and the native
generateContent endpoint for images. Absent key -> not available (heuristic plan).
"""
from __future__ import annotations

import base64
import json
import re
import uuid
from pathlib import Path

import httpx

from ..config import Settings


class LLMClient:
    def __init__(self, settings: Settings) -> None:
        self.s = settings

    @property
    def available(self) -> bool:
        return bool(self.s.gemini_api_key)

    @property
    def label(self) -> str:
        return f"gemini:{self.s.gemini_model}" if self.available else "none"

    async def complete_text(self, system: str, user: str, max_tokens: int = 8000) -> str:
        async with httpx.AsyncClient(timeout=self.s.request_timeout) as c:
            r = await c.post(
                f"{self.s.gemini_base_url}/openai/chat/completions",
                headers={"Authorization": f"Bearer {self.s.gemini_api_key}"},
                json={
                    "model": self.s.gemini_model,
                    "max_tokens": max_tokens,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                },
            )
            r.raise_for_status()
            return r.json()["choices"][0]["message"]["content"] or ""

    async def complete_json(self, system: str, user: str, max_tokens: int = 16000) -> dict:
        text = await self.complete_text(
            system + "\n\nReturn ONLY one valid JSON object, no prose, no markdown fences.",
            user, max_tokens,
        )
        return _extract_json(text)

    async def critique_images(self, system: str, user: str, image_paths: list[str], max_tokens: int = 2500) -> dict:
        """Multimodal critique: judge preview frames, return JSON."""
        content: list[dict] = [{"type": "text", "text": user}]
        for p in image_paths:
            b64 = base64.b64encode(Path(p).read_bytes()).decode()
            content.append({"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}})
        async with httpx.AsyncClient(timeout=self.s.request_timeout) as c:
            r = await c.post(
                f"{self.s.gemini_base_url}/openai/chat/completions",
                headers={"Authorization": f"Bearer {self.s.gemini_api_key}"},
                json={"model": self.s.gemini_model, "max_tokens": max_tokens,
                      "messages": [{"role": "system", "content": system}, {"role": "user", "content": content}]},
            )
            r.raise_for_status()
            return _extract_json(r.json()["choices"][0]["message"]["content"] or "{}")

    async def generate_image(self, prompt: str, dest_dir: Path) -> str:
        """Generate a reference image and return its local path (for Tripo)."""
        suffix = (", single hero product, three-quarter 45° angle, centered, isolated on a "
                  "pure white seamless background, studio product photography, soft shadows, "
                  "high detail, photorealistic, no text")
        async with httpx.AsyncClient(timeout=self.s.request_timeout) as c:
            r = await c.post(
                f"{self.s.gemini_base_url}/models/{self.s.gemini_image_model}:generateContent",
                headers={"x-goog-api-key": self.s.gemini_api_key or "", "Content-Type": "application/json"},
                json={"contents": [{"parts": [{"text": prompt + suffix}]}]},
            )
            r.raise_for_status()
            for cand in r.json().get("candidates", []):
                for part in cand.get("content", {}).get("parts", []):
                    inline = part.get("inlineData") or part.get("inline_data")
                    if inline and inline.get("data"):
                        dest_dir.mkdir(parents=True, exist_ok=True)
                        ext = "png" if "png" in inline.get("mimeType", "png") else "jpg"
                        p = dest_dir / f"{uuid.uuid4().hex}.{ext}"
                        p.write_bytes(base64.b64decode(inline["data"]))
                        return str(p)
        raise RuntimeError("Gemini returned no image data")


def _extract_json(text: str) -> dict:
    text = text.strip()
    m = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if m:
        text = m.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        a, b = text.find("{"), text.rfind("}")
        if a != -1 and b != -1:
            return json.loads(text[a:b + 1])
        raise

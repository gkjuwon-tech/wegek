"""LLM client for the planner (Stage 0) and shader generation (Stage 4).

Supports Anthropic and OpenAI-compatible APIs. Selection is automatic based on
which key is configured. When no key is present `available` is False and callers
fall back to deterministic generation.
"""
from __future__ import annotations

import json
import re

import httpx

from ..config import Settings


class LLMUnavailable(RuntimeError):
    pass


class LLMClient:
    def __init__(self, settings: Settings) -> None:
        self.s = settings
        self.provider = self._resolve_provider()

    def _resolve_provider(self) -> str:
        choice = self.s.planner_provider.lower()
        if choice == "anthropic" and self.s.anthropic_api_key:
            return "anthropic"
        if choice == "openai" and self.s.openai_api_key:
            return "openai"
        if choice == "auto":
            if self.s.anthropic_api_key:
                return "anthropic"
            if self.s.openai_api_key:
                return "openai"
        return "none"

    @property
    def available(self) -> bool:
        return self.provider != "none"

    @property
    def label(self) -> str:
        if self.provider == "anthropic":
            return f"anthropic:{self.s.anthropic_model}"
        if self.provider == "openai":
            return f"openai:{self.s.openai_model}"
        return "none"

    async def complete_text(self, system: str, user: str, max_tokens: int = 4000) -> str:
        if not self.available:
            raise LLMUnavailable("no LLM API key configured")
        async with httpx.AsyncClient(timeout=self.s.request_timeout) as client:
            if self.provider == "anthropic":
                return await self._anthropic(client, system, user, max_tokens)
            return await self._openai(client, system, user, max_tokens)

    async def complete_json(self, system: str, user: str, max_tokens: int = 4000) -> dict:
        text = await self.complete_text(
            system + "\n\nRespond ONLY with a single valid JSON object, no prose, no markdown fences.",
            user,
            max_tokens,
        )
        return _extract_json(text)

    async def _anthropic(self, client: httpx.AsyncClient, system: str, user: str, max_tokens: int) -> str:
        resp = await client.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": self.s.anthropic_api_key or "",
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": self.s.anthropic_model,
                "max_tokens": max_tokens,
                "system": system,
                "messages": [{"role": "user", "content": user}],
            },
        )
        resp.raise_for_status()
        data = resp.json()
        return "".join(block.get("text", "") for block in data.get("content", []))

    async def _openai(self, client: httpx.AsyncClient, system: str, user: str, max_tokens: int) -> str:
        resp = await client.post(
            f"{self.s.openai_base_url}/chat/completions",
            headers={"Authorization": f"Bearer {self.s.openai_api_key}"},
            json={
                "model": self.s.openai_model,
                "max_tokens": max_tokens,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            },
        )
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]


def _extract_json(text: str) -> dict:
    text = text.strip()
    # strip markdown fences if present
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if fence:
        text = fence.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            return json.loads(text[start : end + 1])
        raise

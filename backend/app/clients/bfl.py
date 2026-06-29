"""Black Forest Labs FLUX image-generation client (Stage 1).

Implements the BFL async request/poll protocol. Generates multi-view reference
images for an object. When no key is configured `available` is False.
"""
from __future__ import annotations

import asyncio

import httpx

from ..config import Settings

MULTIVIEW_ANGLES = [
    "front view, centered",
    "three-quarter 45 degree angle view",
    "side profile view",
]


class BFLClient:
    def __init__(self, settings: Settings) -> None:
        self.s = settings

    @property
    def available(self) -> bool:
        return bool(self.s.bfl_api_key)

    @property
    def label(self) -> str:
        return f"bfl:{self.s.bfl_model}" if self.available else "none"

    async def generate_views(self, description: str) -> list[str]:
        """Return a list of generated image URLs (one per view angle)."""
        if not self.available:
            raise RuntimeError("no BFL API key configured")
        async with httpx.AsyncClient(timeout=self.s.request_timeout) as client:
            tasks = [self._one(client, description, angle) for angle in MULTIVIEW_ANGLES]
            return await asyncio.gather(*tasks)

    async def _one(self, client: httpx.AsyncClient, description: str, angle: str) -> str:
        prompt = (
            f"{description}, {angle}, isolated on pure white background, "
            "studio product photography, soft shadows, ultra detailed, 8k"
        )
        resp = await client.post(
            f"{self.s.bfl_base_url}/{self.s.bfl_model}",
            headers={"x-key": self.s.bfl_api_key or "", "Content-Type": "application/json"},
            json={"prompt": prompt, "aspect_ratio": "1:1", "output_format": "png"},
        )
        resp.raise_for_status()
        request_id = resp.json()["id"]
        return await self._poll(client, request_id)

    async def _poll(self, client: httpx.AsyncClient, request_id: str) -> str:
        deadline = asyncio.get_event_loop().time() + self.s.poll_timeout
        while asyncio.get_event_loop().time() < deadline:
            resp = await client.get(
                f"{self.s.bfl_base_url}/get_result",
                headers={"x-key": self.s.bfl_api_key or ""},
                params={"id": request_id},
            )
            resp.raise_for_status()
            data = resp.json()
            status = data.get("status")
            if status == "Ready":
                return data["result"]["sample"]
            if status in ("Error", "Failed", "Content Moderated"):
                raise RuntimeError(f"BFL generation failed: {status}")
            await asyncio.sleep(self.s.poll_interval)
        raise TimeoutError("BFL generation timed out")

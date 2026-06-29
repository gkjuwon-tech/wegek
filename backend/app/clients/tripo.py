"""Tripo image-to-3D + auto-rig client (Stages 2 & 3).

Implements the Tripo task/poll protocol: create task -> poll -> read GLB url.
Supports single-image and multi-view inputs. When no key is configured
`available` is False and the pipeline emits procedural geometry instead.
"""
from __future__ import annotations

import asyncio

import httpx

from ..config import Settings


class TripoClient:
    def __init__(self, settings: Settings) -> None:
        self.s = settings

    @property
    def available(self) -> bool:
        return bool(self.s.tripo_api_key)

    @property
    def label(self) -> str:
        return f"tripo:{self.s.tripo_model_version}" if self.available else "none"

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.s.tripo_api_key}",
            "Content-Type": "application/json",
        }

    async def image_to_model(self, image_urls: list[str], generate_parts: bool = False) -> str:
        """Run image(s) -> 3D and return a downloadable GLB url."""
        if not self.available:
            raise RuntimeError("no Tripo API key configured")
        async with httpx.AsyncClient(timeout=self.s.request_timeout) as client:
            if len(image_urls) >= 2:
                payload = {
                    "type": "multiview_to_model",
                    "model_version": self.s.tripo_model_version,
                    "files": [{"type": "png", "url": u} for u in image_urls[:4]],
                    "texture_quality": "detailed",
                    "generate_parts": generate_parts,
                }
            else:
                payload = {
                    "type": "image_to_model",
                    "model_version": self.s.tripo_model_version,
                    "file": {"type": "png", "url": image_urls[0]},
                    "texture_quality": "detailed",
                }
            task_id = await self._create_task(client, payload)
            result = await self._poll(client, task_id)
            return self._extract_model_url(result)

    async def auto_rig(self, model_task_id: str) -> str:
        if not self.available:
            raise RuntimeError("no Tripo API key configured")
        async with httpx.AsyncClient(timeout=self.s.request_timeout) as client:
            task_id = await self._create_task(
                client, {"type": "animate_rig", "original_model_task_id": model_task_id, "out_format": "glb"}
            )
            result = await self._poll(client, task_id)
            return self._extract_model_url(result)

    async def _create_task(self, client: httpx.AsyncClient, payload: dict) -> str:
        resp = await client.post(f"{self.s.tripo_base_url}/task", headers=self._headers(), json=payload)
        resp.raise_for_status()
        return resp.json()["data"]["task_id"]

    async def _poll(self, client: httpx.AsyncClient, task_id: str) -> dict:
        deadline = asyncio.get_event_loop().time() + self.s.poll_timeout
        while asyncio.get_event_loop().time() < deadline:
            resp = await client.get(f"{self.s.tripo_base_url}/task/{task_id}", headers=self._headers())
            resp.raise_for_status()
            data = resp.json()["data"]
            status = data.get("status")
            if status == "success":
                return data
            if status in ("failed", "cancelled", "banned", "expired"):
                raise RuntimeError(f"Tripo task {status}")
            await asyncio.sleep(self.s.poll_interval)
        raise TimeoutError("Tripo task timed out")

    @staticmethod
    def _extract_model_url(data: dict) -> str:
        output = data.get("output", {})
        for key in ("pbr_model", "model", "rigged_model", "base_model"):
            if output.get(key):
                return output[key]
        result = data.get("result", {})
        for key in ("pbr_model", "model"):
            if isinstance(result.get(key), dict) and result[key].get("url"):
                return result[key]["url"]
        raise RuntimeError("Tripo response had no model url")

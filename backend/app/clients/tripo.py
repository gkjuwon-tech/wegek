"""Tripo client — mesh outsourcing (reference image -> 3D GLB)."""
from __future__ import annotations

import asyncio
import mimetypes
from pathlib import Path

import httpx

from ..config import Settings


def _is_url(ref: str) -> bool:
    return ref.startswith(("http://", "https://"))


class TripoClient:
    def __init__(self, settings: Settings) -> None:
        self.s = settings

    @property
    def available(self) -> bool:
        return bool(self.s.tripo_api_key)

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.s.tripo_api_key}", "Content-Type": "application/json"}

    def _auth(self) -> dict:
        return {"Authorization": f"Bearer {self.s.tripo_api_key}"}

    async def image_to_model(self, image_ref: str) -> str:
        """Reference image (local path or URL) -> downloadable GLB url."""
        if not self.available:
            raise RuntimeError("no Tripo API key configured")
        async with httpx.AsyncClient(timeout=self.s.request_timeout) as client:
            file_desc = await self._file_descriptor(client, image_ref)
            payload = {
                "type": "image_to_model",
                "file": file_desc,
                "model_version": self.s.tripo_model_version,
                "texture": True,
                "pbr": True,
                "texture_quality": self.s.tripo_texture_quality,
                "auto_size": True,
            }
            task_id = await self._create_task(client, payload)
            result = await self._poll(client, task_id)
            return self._extract_model_url(result)

    async def _file_descriptor(self, client: httpx.AsyncClient, ref: str) -> dict:
        if _is_url(ref):
            return {"type": "png", "url": ref}
        p = Path(ref)
        mime = mimetypes.guess_type(p.name)[0] or "image/png"
        img_type = "jpg" if "jpeg" in mime or "jpg" in mime else "png"
        resp = await client.post(
            f"{self.s.tripo_base_url}/upload/sts",
            headers=self._auth(),
            files={"file": (p.name, p.read_bytes(), mime)},
        )
        resp.raise_for_status()
        return {"type": img_type, "file_token": resp.json()["data"]["image_token"]}

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
        for key in ("pbr_model", "model", "base_model", "rigged_model"):
            if output.get(key):
                return output[key]
        raise RuntimeError("Tripo response had no model url")

    async def balance(self) -> int:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.get(f"{self.s.tripo_base_url}/user/balance", headers=self._headers())
            r.raise_for_status()
            return int(r.json()["data"]["balance"])

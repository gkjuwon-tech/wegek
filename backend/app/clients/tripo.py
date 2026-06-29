"""Tripo image-to-3D + auto-rig client (Stages 2 & 3).

Implements the Tripo task/poll protocol: create task -> poll -> read GLB url.
Supports single-image and multi-view inputs. When no key is configured
`available` is False and the pipeline emits procedural geometry instead.
"""
from __future__ import annotations

import asyncio
import mimetypes
from pathlib import Path

import httpx

from ..config import Settings


def _is_url(ref: str) -> bool:
    return ref.startswith("http://") or ref.startswith("https://")


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

    def _auth(self) -> dict:
        return {"Authorization": f"Bearer {self.s.tripo_api_key}"}

    async def image_to_model(self, image_refs: list[str], generate_parts: bool = False) -> str:
        """Run image(s) -> 3D and return a downloadable GLB url.

        Each reference is either a public image URL (e.g. FLUX output) or a local
        file path (e.g. a Gemini-generated image), which is uploaded first to
        obtain a Tripo file token.
        """
        if not self.available:
            raise RuntimeError("no Tripo API key configured")
        async with httpx.AsyncClient(timeout=self.s.request_timeout) as client:
            files = [await self._file_descriptor(client, ref) for ref in image_refs[:4]]
            if len(files) >= 2:
                payload = {
                    "type": "multiview_to_model",
                    "model_version": self.s.tripo_model_version,
                    "files": files,
                    "texture_quality": "detailed",
                    "generate_parts": generate_parts,
                }
            else:
                payload = {
                    "type": "image_to_model",
                    "model_version": self.s.tripo_model_version,
                    "file": files[0],
                    "texture_quality": "detailed",
                }
            task_id = await self._create_task(client, payload)
            result = await self._poll(client, task_id)
            return self._extract_model_url(result)

    async def _file_descriptor(self, client: httpx.AsyncClient, ref: str) -> dict:
        if _is_url(ref):
            return {"type": "png", "url": ref}
        token, img_type = await self.upload_image(client, ref)
        return {"type": img_type, "file_token": token}

    async def upload_image(self, client: httpx.AsyncClient, path: str) -> tuple[str, str]:
        """Upload a local image and return (file_token, image_type)."""
        p = Path(path)
        mime = mimetypes.guess_type(p.name)[0] or "image/png"
        img_type = "jpg" if "jpeg" in mime or "jpg" in mime else "png"
        resp = await client.post(
            f"{self.s.tripo_base_url}/upload/sts",
            headers=self._auth(),
            files={"file": (p.name, p.read_bytes(), mime)},
        )
        resp.raise_for_status()
        return resp.json()["data"]["image_token"], img_type

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

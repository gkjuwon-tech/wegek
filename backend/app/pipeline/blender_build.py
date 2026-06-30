"""Stage 3 — Build & render the Experience in Blender (headless).

Writes the Experience to JSON, optionally fetches a Poly Haven HDRI for the mood,
then runs app/blender/build_scene.py inside the bpy interpreter. Two qualities:
  - "preview": SOLID/Workbench, sub-second per frame — used by the feedback loop.
  - "final":   Cycles path tracing.
Returns the export.json (exact world coords) and the rendered frames dir.
"""
from __future__ import annotations

import json
import subprocess
from collections.abc import Awaitable, Callable
from pathlib import Path

import httpx

from ..config import Settings
from ..schemas import Experience

Logger = Callable[[str], Awaitable[None]]
BUILD_SCRIPT = Path(__file__).resolve().parent.parent / "blender" / "build_scene.py"

# free Poly Haven 1k HDRIs (no key) per mood keyword
HDRI_MAP = {
    "studio": "studio_small_03", "warehouse": "empty_warehouse_01",
    "sunset": "venice_sunset", "night_city": "dikhololo_night", "void": "moonless_golf",
}


async def _fetch_hdri(name: str, settings: Settings, log: Logger) -> str | None:
    slug = HDRI_MAP.get(name)
    if not slug:
        return None
    dest = settings.hdri_dir / f"{slug}_1k.hdr"
    if dest.exists():
        return str(dest)
    url = f"https://dl.polyhaven.org/file/ph-assets/HDRIs/hdr/1k/{slug}_1k.hdr"
    try:
        async with httpx.AsyncClient(timeout=settings.request_timeout, follow_redirects=True) as c:
            r = await c.get(url)
            r.raise_for_status()
            dest.write_bytes(r.content)
        await log(f"HDRI '{slug}' fetched from Poly Haven.")
        return str(dest)
    except Exception as exc:  # noqa: BLE001
        await log(f"HDRI fetch failed ({exc}); using gradient world.")
        return None


async def run(exp: Experience, settings: Settings, job_id: str, quality: str, log: Logger) -> dict:
    out_dir = settings.renders_dir / job_id / quality
    out_dir.mkdir(parents=True, exist_ok=True)
    hdri = await _fetch_hdri(exp.scenes[0].hdri if exp.scenes else "studio", settings, log)

    data = exp.model_dump()
    data["_quality"] = quality
    data["_hdri_file"] = hdri
    if quality == "preview":
        data["_w"], data["_h"], fpa = 640, 360, 1          # 1 frame/act = fast state check
    else:
        data["_w"], data["_h"], data["_samples"], fpa = (
            settings.render_width, settings.render_height, settings.render_samples, settings.frames_per_scene)
    exp_path = out_dir / "experience.json"
    exp_path.write_text(json.dumps(data), encoding="utf-8")

    cmd = [settings.blender_python, str(BUILD_SCRIPT), str(exp_path), str(out_dir), str(fpa)]
    await log(f"Blender {quality} render: {' '.join(cmd[:2])} … (fpa={fpa})")
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=settings.poll_timeout)
    ok = "WEGEK_BLENDER_DONE" in proc.stdout
    export = {}
    exp_json = out_dir / "export.json"
    if exp_json.exists():
        export = json.loads(exp_json.read_text())
    frames = sorted(str(p) for p in out_dir.glob("f_*.png"))
    if not ok:
        await log(f"Blender render issue: {proc.stderr[-300:]}")
    return {"ok": ok, "frames": frames, "export": export, "out_dir": str(out_dir)}


def encode_video(frames_dir: str, out_mp4: str, fps: int = 24) -> str | None:
    """Encode a frame sequence to mp4 via imageio-ffmpeg (best-effort)."""
    try:
        import imageio_ffmpeg
        ff = imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None
    subprocess.run(
        [ff, "-y", "-framerate", str(fps), "-pattern_type", "glob", "-i", f"{frames_dir}/f_*.png",
         "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "24", "-movflags", "+faststart", out_mp4],
        capture_output=True,
    )
    return out_mp4 if Path(out_mp4).exists() else None

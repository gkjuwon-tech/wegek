"""Stage 4 — GLSL background shader.

Uses the curated shader library by default. When an LLM key is configured and
`shader_use_llm` is on, asks the LLM for a bespoke fragment shader, validating it
against the required uniform convention before accepting it.
"""
from __future__ import annotations

from collections.abc import Awaitable, Callable

from ..clients.llm import LLMClient
from ..config import Settings
from ..presets.shaders import NOISE_CHUNK, get_shader
from ..schemas import SitePlan

Logger = Callable[[str], Awaitable[None]]

SHADER_SYSTEM = """You are a GLSL fragment-shader master writing WebGL1-compatible shaders for
a Three.js ShaderMaterial used as a full-screen website background.

Hard requirements:
- Declare and use only these uniforms: float u_time; vec2 u_mouse; vec2 u_resolution; vec3 u_color0; vec3 u_color1; vec3 u_color2;
- Use varying vec2 vUv; (already provided by the vertex shader)
- Write the final colour to gl_FragColor
- No #version, no texture samplers, no external includes
- Under 90 lines, mobile-friendly, smooth ambient motion driven by u_time, subtle u_mouse reactivity
- You MAY call fbm(vec2) and snoise(vec2) — they are already defined, do not redefine them
Do NOT declare the uniforms/varying again — they are already provided; write only helper
functions and `void main()`.

OUTPUT FORMAT: respond with NOTHING but raw GLSL. No prose, no reasoning, no explanation, no
markdown fences. The very first characters of your reply must be GLSL code, and it MUST contain
a complete `void main(){ ... gl_FragColor = ...; }`."""

_HEADER = """
precision highp float;
varying vec2 vUv;
uniform float u_time;
uniform vec2  u_mouse;
uniform vec2  u_resolution;
uniform vec3  u_color0;
uniform vec3  u_color1;
uniform vec3  u_color2;
"""


def _valid_shader(code: str) -> bool:
    # texture samplers are banned, but texture2D-free generated code may still
    # mention "texture" in a comment; only reject real sampler usage.
    has_sampler = "sampler2D" in code or "texture2D(" in code or "texture(" in code
    return "gl_FragColor" in code and "void main" in code and not has_sampler


def _extract_glsl(raw: str) -> str:
    """Pull the GLSL out of an LLM reply that may include reasoning prose / fences."""
    import re

    m = re.search(r"```(?:glsl|c|cpp)?\s*\n(.*?)```", raw, re.DOTALL)
    if m:
        return m.group(1).strip()
    # no fence: drop any leading reasoning by starting at the first GLSL-looking line
    lines = raw.splitlines()
    for i, ln in enumerate(lines):
        if re.match(r"\s*(precision |uniform |varying |void\s+main|float |vec[234] |#|//)", ln):
            return "\n".join(lines[i:]).strip().strip("`").strip()
    return raw.strip().strip("`").strip()


async def run(plan: SitePlan, settings: Settings, log: Logger) -> tuple[str, dict]:
    preset = plan.global_style.background_shader
    if settings.shader_use_llm:
        llm = LLMClient(settings)
        if llm.available:
            try:
                desc = (
                    f"Mood: {plan.brand_mood}. Palette: {plan.global_style.color_palette}. "
                    f"Style hint: {preset.replace('_', ' ')}. "
                    "Make it deep, atmospheric and cinematic: volumetric haze / nebula / flow, "
                    "soft depth and vignette, mostly dark so a 3D product reads in front. "
                    "STRICTLY NO hard grids, no straight ruled lines, no wireframe lattice, no scanlines."
                )
                raw = await llm.complete_text(SHADER_SYSTEM, desc, max_tokens=4000)
                code = _extract_glsl(raw)
                if _valid_shader(code):
                    plan.background_shader_glsl = _HEADER + NOISE_CHUNK + "\n" + code
                    await log(f"LLM-authored bespoke GLSL shader ({llm.label}).")
                    return llm.label, {"source": "llm"}
                await log("LLM shader failed validation; using preset library.")
            except Exception as exc:  # noqa: BLE001
                await log(f"LLM shader gen failed ({exc}); using preset library.")

    plan.background_shader_glsl = get_shader(preset)
    await log(f"Using curated shader preset '{preset}'.")
    return "shader_library", {"source": "preset", "preset": preset}

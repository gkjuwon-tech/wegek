"""Stage 6 — DOM & frontend code generation.

Assembles the validated plan, presets and shader into a single self-contained,
production-quality 3D scrollytelling website (Three.js + GSAP ScrollTrigger +
Lenis + GLSL). The output is a standalone `index.html` that runs by opening it.
"""
from __future__ import annotations

import html
import json
from collections.abc import Awaitable, Callable
from pathlib import Path

from ..config import Settings
from ..presets.cameras import CAMERA_PRESETS
from ..presets.lighting import LIGHTING_PRESETS
from ..presets.shaders import get_shader
from ..schemas import SitePlan

Logger = Callable[[str], Awaitable[None]]

TEMPLATES = Path(__file__).resolve().parent / "templates"

FONTS = {
    "serif_luxury": (
        '<link href="https://fonts.googleapis.com/css2?family=Cormorant+Garamond:wght@400;600;700&display=swap" rel="stylesheet" />',
        "'Cormorant Garamond', Georgia, serif",
    ),
    "mono_tech": (
        '<link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;700&family=JetBrains+Mono:wght@400;700&display=swap" rel="stylesheet" />',
        "'Space Grotesk', 'JetBrains Mono', monospace",
    ),
    "editorial": (
        '<link href="https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,400;9..144,600;9..144,900&display=swap" rel="stylesheet" />',
        "'Fraunces', Georgia, serif",
    ),
    "modern_sans": (
        '<link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;700&display=swap" rel="stylesheet" />',
        "'Space Grotesk', system-ui, sans-serif",
    ),
}


def _section_html(plan: SitePlan) -> str:
    blocks: list[str] = []
    for i, sec in enumerate(plan.sections):
        eyebrow = html.escape(sec.id.replace("_", " ").upper())
        headline = html.escape(sec.headline or plan.project_name.replace("_", " ").title())
        tag = "h1" if i == 0 else "h2"
        parts = [f'<span class="eyebrow reveal">{eyebrow}</span>']
        parts.append(f'<{tag} class="reveal">{headline}</{tag}>')
        if sec.subcopy:
            parts.append(f'<p class="sub reveal">{html.escape(sec.subcopy)}</p>')
        if sec.body:
            parts.append(f'<p class="body reveal">{html.escape(sec.body)}</p>')
        if sec.type == "dom_section":
            parts.append('<a class="cta reveal" href="#">Get started →</a>')
        inner = "\n        ".join(parts)
        blocks.append(
            f'<section data-wegek-section="{html.escape(sec.id)}">\n'
            f'      <div class="section-inner">\n        {inner}\n      </div>\n'
            f'    </section>'
        )
    return "\n    ".join(blocks)


def _build_bundle(plan: SitePlan) -> dict:
    used_lighting = {s.lighting_preset for s in plan.sections}
    used_cameras = {s.camera_preset for s in plan.sections}
    return {
        "plan": plan.model_dump(),
        "lighting": {k: LIGHTING_PRESETS[k] for k in used_lighting if k in LIGHTING_PRESETS},
        "cameras": {k: CAMERA_PRESETS[k] for k in used_cameras if k in CAMERA_PRESETS},
        "shader": plan.background_shader_glsl or get_shader(plan.global_style.background_shader),
    }


def render_site(plan: SitePlan) -> str:
    """Render the full standalone HTML string for a plan."""
    template = (TEMPLATES / "site.html").read_text(encoding="utf-8")
    engine = (TEMPLATES / "engine.js").read_text(encoding="utf-8")
    bundle = _build_bundle(plan)
    palette = (plan.global_style.color_palette + ["#0a0a0f", "#e94560", "#0f3460", "#f5f5f7"])[:4]
    font_link, font_family = FONTS.get(plan.global_style.typography, FONTS["modern_sans"])
    project = html.escape(plan.project_name.replace("_", " "))

    replacements = {
        "__TITLE__": html.escape(f"{plan.project_name.replace('_', ' ').title()} — {plan.tagline}"),
        "__META_DESC__": html.escape(plan.tagline or "A WEGEK-generated 3D website."),
        "__PROJECT__": project,
        "__FONT_LINK__": font_link,
        "__FONT_FAMILY__": font_family,
        "__C0__": palette[0],
        "__C1__": palette[1],
        "__C2__": palette[2],
        "__C3__": palette[3],
        "__SECTIONS__": _section_html(plan),
        # json.dumps is safe to embed in a <script type="application/json"> block,
        # but guard against a literal </script> sneaking in via shader/text.
        "__BUNDLE_JSON__": json.dumps(bundle).replace("</", "<\\/"),
    }
    for key, val in replacements.items():
        template = template.replace(key, val)
    # engine injected last so its JS content isn't touched by placeholder replace
    return template.replace("__ENGINE_JS__", engine)


async def run(plan: SitePlan, settings: Settings, job_id: str, log: Logger) -> tuple[str, dict]:
    site_dir = settings.sites_dir / job_id
    site_dir.mkdir(parents=True, exist_ok=True)
    html_str = render_site(plan)
    (site_dir / "index.html").write_text(html_str, encoding="utf-8")
    (site_dir / "plan.json").write_text(plan.model_dump_json(indent=2), encoding="utf-8")
    await log(f"Generated standalone site ({len(html_str) // 1024} KB) at sites/{job_id}/index.html.")
    return "codegen", {"bytes": len(html_str), "path": str(site_dir / "index.html")}

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

import httpx

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


# Rotated through when the planner leaves a section's anchor unspecified, so even
# a weak plan never stacks every headline in the same corner.
_ANCHOR_CYCLE = ["bottom-left", "mid-right", "top-left", "center", "bottom-right", "mid-left"]
_VALID_ANCHORS = {
    "top-left", "mid-left", "bottom-left", "top-center", "center", "bottom-center",
    "top-right", "mid-right", "bottom-right",
}
_VALID_ALIGN = {"left", "center", "right"}
_VALID_WIDTH = {"narrow", "wide", "full"}


def _inner_classes(sec, i: int) -> tuple[str, str, str]:
    """Return (section_anchor_class, inner_classes, inline_style) from layout."""
    layout = sec.layout or {}
    anchor = str(layout.get("text_anchor") or "").strip().lower()
    if anchor not in _VALID_ANCHORS:
        anchor = _ANCHOR_CYCLE[i % len(_ANCHOR_CYCLE)]
    section_cls = "a-" + anchor

    inner = ["section-inner"]
    align = str(layout.get("text_align") or "").strip().lower()
    if align in _VALID_ALIGN:
        inner.append("ta-" + align)
    width = str(layout.get("width") or "").strip().lower()
    if width in _VALID_WIDTH:
        inner.append("w-" + width)
    if layout.get("panel") or layout.get("invert"):
        inner.append("panel")

    style = ""
    try:
        hl = float(layout.get("headline_scale"))
        if 0.4 <= hl <= 2.2:
            style = f' style="--hl:{hl:.2f}"'
    except (TypeError, ValueError):
        pass
    return section_cls, " ".join(inner), style


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
        section_cls, inner_cls, style = _inner_classes(sec, i)
        blocks.append(
            f'<section class="{section_cls}" data-wegek-section="{html.escape(sec.id)}">\n'
            f'      <div class="{inner_cls}"{style}>\n        {inner}\n      </div>\n'
            f'    </section>'
        )
    return "\n    ".join(blocks)


def _build_bundle(plan: SitePlan) -> dict:
    used_lighting = {s.lighting_preset for s in plan.sections}
    used_cameras = {s.camera_preset for s in plan.sections}
    plan_data = plan.model_dump()
    # reference_images are an intermediate Stage-1 artifact (often local paths);
    # the client only needs model_url, so drop them from the embedded bundle.
    for obj in plan_data.get("objects", []):
        obj.pop("reference_images", None)
    return {
        "plan": plan_data,
        "lighting": {k: LIGHTING_PRESETS[k] for k in used_lighting if k in LIGHTING_PRESETS},
        "cameras": {k: CAMERA_PRESETS[k] for k in used_cameras if k in CAMERA_PRESETS},
        "shader": plan.background_shader_glsl or get_shader(plan.global_style.background_shader),
    }


async def _localize_models(plan: SitePlan, site_dir: Path, settings: Settings, log: Logger) -> int:
    """Download remote GLB models into the site folder, rewriting to relative
    paths so the bundle stays self-contained after upstream URLs expire. On any
    failure the remote URL is kept (graceful degradation)."""
    models_dir = site_dir / "models"
    localized = 0
    async with httpx.AsyncClient(timeout=settings.request_timeout, follow_redirects=True) as client:
        for obj in plan.objects:
            url = obj.model_url
            if obj.model_format != "glb" or not url or not url.startswith("http"):
                continue
            try:
                resp = await client.get(url)
                resp.raise_for_status()
                models_dir.mkdir(parents=True, exist_ok=True)
                (models_dir / f"{obj.id}.glb").write_bytes(resp.content)
                obj.model_url = f"models/{obj.id}.glb"
                localized += 1
            except Exception as exc:  # noqa: BLE001
                await log(f"Could not localize GLB for '{obj.id}' ({exc}); keeping remote URL.")
    return localized


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
    localized = 0
    if settings.localize_assets:
        localized = await _localize_models(plan, site_dir, settings, log)
        if localized:
            await log(f"Localized {localized} GLB model(s) into the site folder.")
    html_str = render_site(plan)
    (site_dir / "index.html").write_text(html_str, encoding="utf-8")
    (site_dir / "plan.json").write_text(plan.model_dump_json(indent=2), encoding="utf-8")
    await log(f"Generated standalone site ({len(html_str) // 1024} KB) at sites/{job_id}/index.html.")
    return "codegen", {"bytes": len(html_str), "path": str(site_dir / "index.html"), "localized_models": localized}

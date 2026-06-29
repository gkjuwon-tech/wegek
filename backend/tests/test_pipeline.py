from __future__ import annotations

import asyncio

import pytest

from app.config import get_settings
from app.pipeline import stage3_animate, stage4_shaders, stage5_scene
from app.pipeline.stage0_planner import detect_category, heuristic_plan
from app.pipeline.stage6_codegen import render_site
from app.pipeline.stage7_review import structural_score
from app.presets.cameras import CAMERA_PRESETS
from app.presets.lighting import LIGHTING_PRESETS
from app.schemas import SitePlan


async def _noop(*_args, **_kwargs):
    return None


def test_detect_category_keywords():
    assert detect_category("luxury watch landing, 시계가 돌아가는") == "watch"
    assert detect_category("Nike 신발 스니커즈 회전") == "sneakers"
    assert detect_category("gaming 키보드 헤드셋 RGB") == "gaming"
    assert detect_category("random brief with no hint") == "tech"


def test_heuristic_plan_is_valid():
    plan = heuristic_plan("luxury watch landing page", None, 3)
    assert plan.project_name
    assert 3 <= len(plan.sections) <= 5
    assert 1 <= len(plan.objects) <= 3
    assert plan.sections[0].id == "hero"
    assert plan.sections[-1].type == "dom_section"
    # presets resolve to real definitions
    for sec in plan.sections:
        assert sec.lighting_preset in LIGHTING_PRESETS
        assert sec.camera_preset in CAMERA_PRESETS


def test_full_offline_pipeline_renders_site():
    async def run() -> str:
        s = get_settings()
        plan = heuristic_plan("Tesla EV landing, car rotates and doors open", None, 3)
        await stage3_animate.run(plan, s, _noop)
        await stage4_shaders.run(plan, s, _noop)
        await stage5_scene.run(plan, s, _noop)
        return render_site(plan), plan  # type: ignore[return-value]

    html, plan = asyncio.run(run())  # type: ignore[misc]
    assert isinstance(html, str)
    assert "gl_FragColor" in html  # custom GLSL embedded
    assert "importmap" in html
    assert "__ENGINE_JS__" not in html  # all placeholders resolved
    assert "data-wegek-section" in html
    # every object has authored keyframes
    assert all(o.keyframes for o in plan.objects)


def test_structural_score_passes_for_complete_plan():
    plan = heuristic_plan("gaming keyboard with neon", None, 3)

    async def enrich():
        s = get_settings()
        await stage4_shaders.run(plan, s, _noop)
        await stage5_scene.run(plan, s, _noop)

    asyncio.run(enrich())
    score, notes = structural_score(plan)
    assert score >= 0.78, f"low score {score}, notes={notes}"


def test_bundle_json_escaping_no_script_break():
    plan = heuristic_plan("tech gadget", None, 2)

    async def enrich():
        s = get_settings()
        await stage4_shaders.run(plan, s, _noop)
        await stage5_scene.run(plan, s, _noop)

    asyncio.run(enrich())
    html = render_site(plan)
    # no raw closing script tag inside the embedded JSON bundle
    bundle_start = html.index('id="wegek-bundle"')
    bundle_end = html.index("</script>", bundle_start)
    assert "</script" not in html[bundle_start + 20 : bundle_end]


@pytest.mark.parametrize("shader_name", ["gradient_noise_dark", "neon_cyber", "aurora_nebula"])
def test_shaders_have_required_uniforms(shader_name):
    from app.presets.shaders import get_shader

    code = get_shader(shader_name)
    for uniform in ("u_time", "u_mouse", "u_resolution", "u_color0", "gl_FragColor"):
        assert uniform in code


def test_siteplan_object_lookup():
    plan = SitePlan(project_name="X")
    assert plan.object_by_id("missing") is None

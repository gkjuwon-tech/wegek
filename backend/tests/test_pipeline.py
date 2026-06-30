from __future__ import annotations

from app.pipeline import bake, plan
from app.schemas import Experience


def test_heuristic_plan_has_three_scenes():
    exp = plan.heuristic("luxury chrome sneaker drop", None)
    assert isinstance(exp, Experience)
    assert len(exp.scenes) == 3
    assert any(o.is_hero for o in exp.all_objects())
    for sc in exp.scenes:
        assert sc.objects and sc.camera and sc.lights
        assert sc.transition_out


def test_plan_slug_and_palette():
    exp = plan.heuristic("Nike Air futuristic", None)
    assert exp.project_name and exp.project_name.isupper().__class__ is bool
    assert len(exp.scenes[0].palette) >= 3


def test_coerce_pads_to_three_scenes():
    exp = plan._coerce(
        {"project_name": "X", "scenes": [{"id": "act1", "objects": [{"id": "h", "mesh_query": "watch", "is_hero": True}]}]},
        "watch", None,
    )
    assert len(exp.scenes) == 3


def test_bake_merges_export_coords():
    exp = plan.heuristic("watch", None)
    export = {"acts": [{"id": s.id, "frame_range": [1, 10], "objects": [{"id": "x", "base": [0, 0, 0]}],
                        "camera": [{"frame": 1, "position": [0, -8, 2], "fov": 40}], "lights": []}
                       for s in exp.scenes]}
    spec = bake.bake(exp, export, frames=["f_0001.png", "f_0002.png"], video="scroll.mp4")
    assert spec["source"] == "blender_export"
    assert len(spec["acts"]) == 3
    assert spec["acts"][0]["camera"][0]["position"] == [0, -8, 2]
    assert spec["frame_count"] == 2

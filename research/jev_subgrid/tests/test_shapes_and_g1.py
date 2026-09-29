import json
from pathlib import Path

import numpy as np
import pytest

from jevsg.experiments import g1
from jevsg.shapes.library import FAMILIES, VARIANTS_PER_FAMILY, build_shape, g1_shape_ids
from jevsg.shapes.reference import build_reference


def test_shape_set_matches_the_proposal() -> None:
    ids = g1_shape_ids()
    assert len(ids) == len(FAMILIES) * VARIANTS_PER_FAMILY == 48
    assert len(set(ids)) == 48
    specs = [build_shape(s) for s in ids]
    assert all(s.split == "g1_roundtrip" for s in specs)
    # Deterministic: rebuilding gives identical parameters.
    assert build_shape("cup_5").params == build_shape("cup_5").params
    # Both poses and a spread of thin features in every family.
    for fam in FAMILIES:
        fs = [s for s in specs if s.family == fam]
        assert {s.params["pose"] for s in fs} == {"canonical", "rotated"}
        mf = [s.min_feature for s in fs]
        assert min(mf) < 0.05 and max(mf) > 0.09


@pytest.mark.parametrize("shape_id", g1_shape_ids())
def test_probes_are_on_the_designed_side_of_the_sdf(shape_id: str) -> None:
    spec = build_shape(shape_id)
    pts = np.array([p.point for p in spec.probes])
    val = spec.sdf(pts)
    for p, v in zip(spec.probes, val, strict=True):
        assert (v < 0) == (p.expect == "material"), (p.name, v)
        assert abs(v) > 0.2 * spec.min_feature, (p.name, v)
    assert any(p.expect == "air" for p in spec.probes)
    assert any(p.expect == "material" for p in spec.probes)


def test_coarse_reference_is_validated(tmp_path: Path) -> None:
    ref = build_reference(build_shape("ring_2"), tmp_path, voxel=0.03)
    assert ref.valid, ref.problems
    assert ref.topology["genus_signature"] == [1]
    assert all(c.ok for c in ref.checks)
    again = build_reference(build_shape("ring_2"), tmp_path, voxel=0.03)  # cache hit
    assert again.mesh.num_faces == ref.mesh.num_faces


def test_g1_smoke_run(tmp_path: Path) -> None:
    out = tmp_path / "g1"
    rc = g1.main(
        [
            "--out",
            str(out),
            "--cache",
            str(tmp_path / "cache"),
            "--resolutions",
            "6",
            "12",
            "--bits",
            "4",
            "8",
            "--caps",
            "1",
            "--samples",
            "2000",
            "--workers",
            "1",
            "--shapes",
            "ring_2",
            "multi_part_0",
            "--ref-voxel",
            "0.03",
        ]
    )
    assert rc == 0
    rows = [
        json.loads(x) for f in (out / "rows").glob("*.jsonl") for x in f.read_text().splitlines()
    ]
    data = [r for r in rows if r.get("_type") != "reference"]
    assert len(data) == 2 * 2 * 4  # shapes x resolutions x (float64, q4, q8, K1)
    f64 = [r for r in data if r["config"] == "float64"]
    assert all(r["odd_faces_A"] == 0 and r["non_even_tets"] == 0 for r in f64)
    assert all(r["xcheck_same_connectivity"] for r in f64)
    assert all(r["intersection_free"] for r in data)
    report = (out / "report.md").read_text(encoding="utf-8")
    assert "G1" in report and "왕복 오류 지도" in report
    summary = json.loads((out / "summary.json").read_text())
    assert summary["references_valid"] == 2


def test_empty_reconstruction_preserves_nothing() -> None:
    from jevsg.evaluate import finalize_row

    row = {
        "out_faces": 0,
        "valid_manifold": False,
        "topology_match": False,
        "probes_ok": True,  # air probes pass vacuously on an empty mesh ...
        "core_success": False,
        "struct_cavity": True,
    }
    out = finalize_row(row)
    assert out["failure_code"] == "E"
    assert out["probes_ok"] is False and out["struct_cavity"] is False  # ... but count as lost
    ok = finalize_row(
        {"out_faces": 10, "valid_manifold": True, "topology_match": False, "probes_ok": True}
    )
    assert ok["failure_code"] == "T"

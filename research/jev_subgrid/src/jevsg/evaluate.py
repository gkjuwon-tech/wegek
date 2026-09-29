"""Evaluation of a reconstruction against a validated reference (proposal §7).

``core_success`` is the G1 pass criterion ("핵심 구조 성공"): the reconstruction is a
closed orientable 2-manifold, has the designed number of surface components and the
designed genus of each, and every designed probe (coffee space, handle passage, gaps,
voids, thin-wall interiors ...) lands on the designed side.  Geometry (Chamfer, F-score,
Hausdorff, volume) is reported next to it, never instead of it — a single render or a
low Chamfer distance does not prove a handle is still a handle.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import numpy.typing as npt

from jevsg.mesh import TriMesh
from jevsg.metrics import SurfaceDistance, compare_surfaces, orient_outward, winding_number
from jevsg.selfintersect import self_intersections
from jevsg.shapes.reference import Reference
from jevsg.topology import analyze

FloatArray = npt.NDArray[np.float64]
TAUS = (0.005, 0.01)


def evaluate_reconstruction(
    ref: Reference,
    rec: TriMesh,
    *,
    samples: int = 30_000,
    seed: int = 0,
    ref_distance: SurfaceDistance | None = None,
    ref_samples: FloatArray | None = None,
    check_self_intersections: bool = True,
) -> dict[str, Any]:
    out: dict[str, Any] = {}
    spec = ref.spec
    topo = analyze(rec)
    out.update({f"out_{k}": v for k, v in topo.as_dict().items()})
    out["components_match"] = topo.components == spec.expected_components
    out["genus_match"] = topo.genus_signature == spec.expected_signature
    out["topology_match"] = bool(out["components_match"] and out["genus_match"])
    out["valid_manifold"] = topo.watertight_manifold

    if check_self_intersections:
        si = self_intersections(rec)
        out.update(si.as_dict())
        out["intersection_free"] = si.clean
    else:
        out["intersection_free"] = None

    if rec.num_faces == 0:
        out.update({"volume": 0.0, "volume_rel_err": 1.0})
        out.update(
            {"chamfer_l1": float("inf"), "chamfer_l2": float("inf"), "hausdorff": float("inf")}
        )
        for t in TAUS:
            out[f"fscore@{t:g}"] = 0.0
        winding = np.zeros(len(spec.probes))
    else:
        solid = orient_outward(rec)
        out["volume"] = solid.volume
        out["volume_rel_err"] = abs(solid.volume - ref.volume) / abs(ref.volume)
        cmp = compare_surfaces(
            ref.mesh,
            solid.mesh,
            samples=samples,
            taus=TAUS,
            seed=seed,
            reference_distance=ref_distance,
            reference_samples=ref_samples,
        )
        out.update(cmp.as_dict())
        winding = winding_number(solid.mesh, ref.probe_points)

    failed: list[str] = []
    by_structure: dict[str, list[bool]] = {}
    for probe, w in zip(spec.probes, winding, strict=True):
        ok = bool((w > 0.5) == (probe.expect == "material"))
        by_structure.setdefault(probe.structure, []).append(ok)
        if not ok:
            failed.append(probe.name)
    out["probes_total"] = len(spec.probes)
    out["probes_passed"] = len(spec.probes) - len(failed)
    out["probes_failed"] = ";".join(failed)
    out["probes_ok"] = not failed
    for structure, oks in by_structure.items():
        out[f"struct_{structure}"] = all(oks)
    out["core_success"] = bool(out["valid_manifold"] and out["topology_match"] and out["probes_ok"])
    reasons = []
    if not out["valid_manifold"]:
        reasons.append("V")
    if not out["topology_match"]:
        reasons.append("T")
    if not out["probes_ok"]:
        reasons.append("P")
    out["failure_code"] = "".join(reasons)
    return out

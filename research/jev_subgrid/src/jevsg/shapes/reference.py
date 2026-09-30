"""Reference meshes for the G1 shapes and their validation.

A shape's reference mesh is the marching-cubes surface of its SDF at a voxel size
fine enough that the thinnest designed feature spans >= 3 voxels.  Before a reference is
used we *verify* it against the design (proposal §6: 원본의 구멍·벽 두께·연결성을 명확히
측정할 수 있는 예제): closed 2-manifold, no self-intersections, the designed number of
components and genus, and every probe on the designed side with clearance.  A reference
that fails is reported and excluded — never silently repaired.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import numpy.typing as npt
from skimage.measure import marching_cubes

from jevsg.mesh import Normalization, TriMesh, fit_normalization, normalize
from jevsg.metrics import SurfaceDistance, orient_outward, winding_number
from jevsg.selfintersect import self_intersections
from jevsg.shapes.library import ShapeSpec
from jevsg.topology import analyze

FloatArray = npt.NDArray[np.float64]

#: Sub-voxel offset of the sampling lattice, so no lattice point lands exactly on the
#: axis-aligned planes the shapes are built from (avoids zero-area MC triangles).
_LATTICE_JITTER = np.array([0.3183099, 0.2718282, 0.1414214])
REFERENCE_VERSION = 3
#: Samples closer to zero than this (in voxel units) are pushed off zero.  Otherwise an
#: interpolated vertex can land exactly on a lattice corner, several MC vertices coincide
#: and the reference gets zero-area, touching faces (seen with v1 of this module).
ZERO_GUARD = 1e-4


def voxel_size(spec: ShapeSpec, max_voxel: float = 0.012, per_feature: float = 3.0) -> float:
    return float(min(max_voxel, spec.min_feature / per_feature))


def mesh_sdf(spec: ShapeSpec, h: float, slab_points: int = 2_000_000) -> TriMesh:
    """Marching cubes of ``spec.sdf`` on a lattice of spacing ``h`` (object units)."""
    lo = np.asarray(spec.bounds[0], dtype=np.float64) - 4 * h + _LATTICE_JITTER * h
    hi = np.asarray(spec.bounds[1], dtype=np.float64) + 4 * h
    counts = np.ceil((hi - lo) / h).astype(int) + 1
    xs, ys, zs = (lo[k] + h * np.arange(counts[k]) for k in range(3))
    vol = np.empty((counts[0], counts[1], counts[2]), dtype=np.float64)
    per_x = max(1, slab_points // (counts[1] * counts[2]))
    yy, zz = np.meshgrid(ys, zs, indexing="ij")
    for i0 in range(0, counts[0], per_x):
        xx = xs[i0 : i0 + per_x]
        pts = np.empty((xx.size, counts[1], counts[2], 3))
        pts[..., 0] = xx[:, None, None]
        pts[..., 1] = yy[None]
        pts[..., 2] = zz[None]
        vol[i0 : i0 + per_x] = spec.sdf(pts.reshape(-1, 3)).reshape(xx.size, counts[1], counts[2])
    if vol[0].min() <= 0 or vol[-1].min() <= 0 or vol[:, 0].min() <= 0 or vol[:, -1].min() <= 0:
        raise ValueError(f"{spec.shape_id}: shape touches the sampling box")
    if vol[:, :, 0].min() <= 0 or vol[:, :, -1].min() <= 0:
        raise ValueError(f"{spec.shape_id}: shape touches the sampling box")
    guard = ZERO_GUARD * h
    near = np.abs(vol) < guard
    vol[near] = np.where(vol[near] < 0, -guard, guard)
    verts, faces, _, _ = marching_cubes(  # type: ignore[no-untyped-call]
        vol, level=0.0, spacing=(h, h, h), allow_degenerate=True
    )
    return TriMesh(np.asarray(verts, dtype=np.float64) + lo, np.asarray(faces, dtype=np.int64))


@dataclass
class ProbeCheck:
    name: str
    expect: str
    structure: str
    point: tuple[float, float, float]  # grid coordinates
    winding: float
    clearance: float  # grid units
    ok: bool


@dataclass
class Reference:
    spec: ShapeSpec
    mesh: TriMesh  # oriented, grid coordinates
    normalization: Normalization
    voxel: float  # object units
    volume: float
    probe_points: FloatArray  # grid coordinates, spec.probes order
    checks: list[ProbeCheck] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)
    topology: dict[str, object] = field(default_factory=dict)
    self_intersections: int = 0

    @property
    def valid(self) -> bool:
        return not self.problems

    @property
    def min_feature_grid(self) -> float:
        return self.spec.min_feature * self.normalization.scale

    def summary(self) -> dict[str, object]:
        return {
            "shape_id": self.spec.shape_id,
            "family": self.spec.family,
            "variant": self.spec.variant,
            "valid": self.valid,
            "problems": list(self.problems),
            "faces": self.mesh.num_faces,
            "voxel_object": self.voxel,
            "scale": self.normalization.scale,
            "min_feature_object": self.spec.min_feature,
            "min_feature_grid": self.min_feature_grid,
            "expected_components": self.spec.expected_components,
            "expected_genus": list(self.spec.expected_signature),
            "volume_grid": self.volume,
            "self_intersecting_pairs": self.self_intersections,
            "topology": self.topology,
            "params": dict(self.spec.params),
            "probes": [c.__dict__ for c in self.checks],
        }


def _spec_hash(spec: ShapeSpec, h: float) -> str:
    payload = json.dumps(
        {
            "id": spec.shape_id,
            "params": spec.params,
            "h": h,
            "v": REFERENCE_VERSION,
            "bounds": spec.bounds,
            "probes": [p.__dict__ for p in spec.probes],
        },
        sort_keys=True,
        default=str,
    )
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def build_reference(
    spec: ShapeSpec,
    cache_dir: str | Path | None = None,
    check_self_intersections: bool = True,
    voxel: float | None = None,
) -> Reference:
    """Mesh, normalise, orient and validate the reference of ``spec``.

    ``voxel`` overrides the automatic marching-cubes voxel size (tests use a coarse one).
    """
    h = voxel_size(spec) if voxel is None else float(voxel)
    raw: TriMesh | None = None
    cached_si: int | None = None
    cache_file = None
    if cache_dir is not None:
        cache_file = Path(cache_dir) / f"{spec.shape_id}_{_spec_hash(spec, h)}.npz"
        if cache_file.exists():
            z = np.load(cache_file)
            raw = TriMesh(z["vertices"], z["faces"])
            cached_si = int(z["si_pairs"]) if "si_pairs" in z.files else None
    if raw is None:
        raw = mesh_sdf(spec, h)

    norm = fit_normalization(raw.vertices)
    mesh = normalize(raw, norm)
    solid = orient_outward(mesh)
    topo = analyze(solid.mesh)
    probes = norm.apply(np.array([p.point for p in spec.probes], dtype=np.float64))
    ref = Reference(
        spec=spec,
        mesh=solid.mesh,
        normalization=norm,
        voxel=h,
        volume=solid.volume,
        probe_points=probes,
        topology=topo.as_dict(),
    )
    if not topo.watertight_manifold:
        ref.problems.append("reference is not a closed orientable 2-manifold")
    if topo.components != spec.expected_components:
        ref.problems.append(f"components {topo.components} != designed {spec.expected_components}")
    if topo.genus_signature != spec.expected_signature:
        ref.problems.append(f"genus {topo.genus_signature} != designed {spec.expected_signature}")
    if check_self_intersections:
        # Orientation and normalisation do not change which faces intersect, so the
        # (expensive, exact) check is cached with the raw mesh.
        if cached_si is None:
            cached_si = self_intersections(solid.mesh).intersecting_pairs
        ref.self_intersections = cached_si
        if cached_si:
            ref.problems.append(f"{cached_si} self-intersecting face pairs")
    if cache_file is not None and not cache_file.exists():
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        arrays: dict[str, npt.NDArray[np.generic]] = {"vertices": raw.vertices, "faces": raw.faces}
        if cached_si is not None:
            arrays["si_pairs"] = np.asarray(cached_si, dtype=np.int64)
        np.savez_compressed(cache_file, **arrays)  # type: ignore[arg-type]
    w = winding_number(solid.mesh, probes)
    clearance = SurfaceDistance(solid.mesh)(probes)
    need = 0.25 * ref.min_feature_grid
    for p, pt, wn, cl in zip(spec.probes, probes, w, clearance, strict=True):
        is_material = wn > 0.5
        ok = (is_material == (p.expect == "material")) and cl >= need
        ref.checks.append(
            ProbeCheck(
                p.name,
                p.expect,
                p.structure,
                (float(pt[0]), float(pt[1]), float(pt[2])),
                float(wn),
                float(cl),
                bool(ok),
            )
        )
        if not ok:
            ref.problems.append(
                f"probe {p.name}: expected {p.expect}, winding {wn:.3f}, "
                f"clearance {cl:.4f} (need {need:.4f})"
            )
    return ref

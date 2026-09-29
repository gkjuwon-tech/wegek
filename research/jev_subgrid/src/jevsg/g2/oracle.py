"""Scoring a candidate completion by rebuilding the whole shape.

The oracle knows the reference and is used only to *grade* choices, never to make
them.  Separately, :func:`effects` computes what a candidate does using nothing but
the candidate's own reconstruction (no reference) — those numbers are what the
context levels may describe to a chooser.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

from jevsg.decode import decode_primal
from jevsg.encode import encode_mesh
from jevsg.g2.local import Block, Candidate, merge
from jevsg.grid import TetGrid
from jevsg.mesh import TriMesh
from jevsg.metrics import SurfaceDistance, orient_outward, sample_surface, winding_number
from jevsg.representation import EdgeCoordinates
from jevsg.shapes.library import ShapeSpec, build_shape
from jevsg.shapes.reference import Reference, build_reference
from jevsg.topology import analyze, face_components

FloatArray = npt.NDArray[np.float64]


@dataclass
class ShapeContext:
    spec: ShapeSpec
    ref: Reference
    grid: TetGrid
    truth: EdgeCoordinates
    ref_dist: SurfaceDistance
    ref_points: FloatArray  # dense reference samples for local errors


def build_shape_context(
    shape_id: str, cache_dir: str, n: int = 64, samples: int = 400_000
) -> ShapeContext:
    spec = build_shape(shape_id)
    ref = build_reference(spec, cache_dir)
    if not ref.valid:
        raise ValueError(f"{shape_id}: invalid reference: {ref.problems}")
    grid = TetGrid(n)
    truth, _ = encode_mesh(ref.mesh, grid)
    pts = sample_surface(ref.mesh, samples, np.random.default_rng(99))
    return ShapeContext(spec, ref, grid, truth, SurfaceDistance(ref.mesh), pts)


def block_box(grid: TetGrid, block: Block, pad: int = 1) -> tuple[FloatArray, FloatArray]:
    lo = grid.lattice_to_position(np.asarray(block.lo) - pad)
    hi = grid.lattice_to_position(np.asarray(block.lo) + block.size + pad)
    return lo, hi


def _in_box(p: FloatArray, lo: FloatArray, hi: FloatArray) -> npt.NDArray[np.bool_]:
    return np.asarray(np.all((p >= lo) & (p <= hi), axis=1), dtype=bool)


@dataclass
class Outcome:
    core_success: bool
    topology_match: bool
    probes_ok: bool
    valid: bool
    components: int
    genus: tuple[int, ...]
    local_err: float  # mean two-sided distance near the block, in grid-spacing units
    faces: int
    seconds: float
    effects: dict[str, object]

    def quality(self) -> tuple[int, float]:
        return (int(self.core_success), -self.local_err)


def effects(mesh: TriMesh, grid: TetGrid, block: Block) -> dict[str, object]:
    """What the completed object looks like, computed from the candidate alone."""
    topo = analyze(mesh)
    lo, hi = block_box(grid, block, pad=0)
    cent = mesh.triangles().mean(axis=1) if mesh.num_faces else np.zeros((0, 3))
    inside = _in_box(cent, lo, hi) if mesh.num_faces else np.zeros(0, dtype=bool)
    ncomp, comp = face_components(mesh) if mesh.num_faces else (0, np.zeros(0, dtype=np.int64))
    # A component entirely inside the (slightly padded) block is a new closed bubble.
    plo, phi = block_box(grid, block, pad=1)
    bubbles = 0
    for c in range(ncomp):
        if np.all(_in_box(cent[comp == c], plo, phi)):
            bubbles += 1
    local = TriMesh(mesh.vertices, mesh.faces[inside]) if np.any(inside) else None
    local_pieces = face_components(local)[0] if local is not None else 0
    return {
        "object_pieces": topo.components,
        "object_holes": topo.total_genus,
        "object_closed": topo.watertight_manifold,
        "bubbles_in_block": bubbles,
        "surface_pieces_in_block": local_pieces,
        "surface_faces_in_block": int(inside.sum()),
    }


def score(
    ctx: ShapeContext,
    block: Block,
    known: EdgeCoordinates,
    cand: Candidate,
    workdir: str | None = None,
) -> Outcome:
    t0 = time.perf_counter()
    a = merge(known, cand.fill)
    rec = decode_primal(a, ctx.grid, workdir=workdir).mesh
    topo = analyze(rec)
    spec = ctx.spec
    topo_ok = (
        topo.components == spec.expected_components
        and topo.genus_signature == spec.expected_signature
    )
    if rec.num_faces:
        solid = orient_outward(rec).mesh
        w = winding_number(solid, ctx.ref.probe_points)
        probes_ok = all(
            (wi > 0.5) == (p.expect == "material") for p, wi in zip(spec.probes, w, strict=True)
        )
    else:
        solid, probes_ok = rec, False
    valid = topo.watertight_manifold
    # Local two-sided error around the block.
    lo, hi = block_box(ctx.grid, block, pad=1)
    rp = ctx.ref_points[_in_box(ctx.ref_points, lo, hi)]
    cent = rec.triangles().mean(axis=1) if rec.num_faces else np.zeros((0, 3))
    near = _in_box(cent, lo, hi) if rec.num_faces else np.zeros(0, dtype=bool)
    errs = []
    if np.any(near):
        sub = TriMesh(rec.vertices, rec.faces[near])
        qp = sample_surface(sub, max(200, len(rp)), np.random.default_rng(5))
        errs.append(float(ctx.ref_dist(qp).mean()))
        if len(rp):
            errs.append(float(SurfaceDistance(sub)(rp).mean()))
    elif len(rp):
        errs.append(
            float(SurfaceDistance(rec)(rp).mean()) if rec.num_faces else 10.0 * ctx.grid.spacing
        )
    local_err = (float(np.mean(errs)) if errs else 0.0) / ctx.grid.spacing
    return Outcome(
        core_success=bool(valid and topo_ok and probes_ok),
        topology_match=bool(topo_ok),
        probes_ok=bool(probes_ok),
        valid=bool(valid),
        components=topo.components,
        genus=topo.genus_signature,
        local_err=local_err,
        faces=rec.num_faces,
        seconds=time.perf_counter() - t0,
        effects=effects(rec, ctx.grid, block),
    )

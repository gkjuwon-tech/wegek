"""A -> 3D with the *existing* primal Subgrid Marching Tetrahedra reconstructor.

We do not re-implement the reconstruction (proposal §2/§5.5: 기존 primal 복원 경로 사용,
복원기 버전 고정).  A is handed to the pinned ``subgrid-marching`` package through its
documented explicit-input format (``docs/explicit_input_format.md``): a tet mesh plus
per-edge sorted ``t`` values, edges stored as ``(i, j)`` with ``i < j``.

Only tetrahedra touching an active edge are written; tets without crossings produce no
geometry.  Vertex ids are compacted with an order-preserving map, so every ``i < j``
relation — which is all the reconstructor's signatures and tie-breaking look at — is
unchanged.  ``tests/test_decode.py`` checks this against the full-grid input.
"""

from __future__ import annotations

import os
import tempfile
import time
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

from jevsg.grid import TetGrid
from jevsg.mesh import TriMesh, polygons_to_triangles
from jevsg.representation import EdgeCoordinates, check

RECONSTRUCTOR_PACKAGE = "subgrid-marching"
RECONSTRUCTOR_VERSION = "1.0.0"


def reconstructor_version() -> str:
    import subgrid_marching as smt

    return str(smt.__version__)


def assert_pinned_reconstructor() -> None:
    v = reconstructor_version()
    if v != RECONSTRUCTOR_VERSION:
        raise RuntimeError(
            f"{RECONSTRUCTOR_PACKAGE}=={RECONSTRUCTOR_VERSION} is required for reproducible "
            f"results, found {v}"
        )


@dataclass(frozen=True)
class DecodeResult:
    mesh: TriMesh
    non_even_tets: int
    non_normal_tets: int
    non_zero_tets: int
    active_tets_written: int
    construction_seconds: float
    assembly_seconds: float
    total_seconds: float
    polygon_sizes: dict[int, int]

    def as_dict(self) -> dict[str, object]:
        return {
            "non_even_tets": self.non_even_tets,
            "non_normal_tets": self.non_normal_tets,
            "non_zero_tets": self.non_zero_tets,
            "active_tets_written": self.active_tets_written,
            "construction_seconds": self.construction_seconds,
            "assembly_seconds": self.assembly_seconds,
            "decode_seconds": self.total_seconds,
            "out_vertices": self.mesh.num_vertices,
            "out_faces": self.mesh.num_faces,
        }


def explicit_input_arrays(
    a: EdgeCoordinates, grid: TetGrid, *, full_grid: bool = False
) -> dict[str, npt.NDArray[np.generic]]:
    """Arrays of the reconstructor's ``.npz`` explicit-input format for A."""
    check(a, grid)
    tets = grid.tets
    if full_grid:
        keep_tets = np.ones(tets.shape[0], dtype=bool)
    else:
        active = np.zeros(grid.num_edges, dtype=bool)
        active[a.edge_ids] = True
        keep_tets = np.any(active[grid.tet_edge_ids], axis=1)
    sel = tets[keep_tets].astype(np.int64)
    if full_grid:
        used = np.arange(grid.num_nodes, dtype=np.int64)
    else:
        used = np.unique(np.concatenate([sel.reshape(-1), grid.edges[a.edge_ids].reshape(-1)]))
    remap = np.full(grid.num_nodes, -1, dtype=np.int64)
    remap[used] = np.arange(used.size, dtype=np.int64)  # monotone: preserves i < j
    edges = remap[grid.edges[a.edge_ids]]
    return {
        "vertices": np.ascontiguousarray(grid.node_positions[used], dtype=np.float64),
        "tets": np.ascontiguousarray(remap[sel], dtype=np.int32),
        "edges": np.ascontiguousarray(edges, dtype=np.int32),
        "isect_offsets": np.ascontiguousarray(a.offsets, dtype=np.int32),
        "isect_ts": np.ascontiguousarray(a.s, dtype=np.float64),
    }


def decode_primal(
    a: EdgeCoordinates,
    grid: TetGrid,
    *,
    scoop_bulge: float = 1e-3,
    full_grid: bool = False,
    workdir: str | None = None,
) -> DecodeResult:
    """Reconstruct a mesh from A with the reference primal pipeline.

    Combinatorial (exact) vertex merging and the reference's greedy face orientation are
    used, i.e. the package defaults.  The returned mesh is triangulated (the primal output
    is triangles already; n-gons, if any, are fan-split and counted in ``polygon_sizes``).
    """
    import subgrid_marching as smt

    assert_pinned_reconstructor()
    t0 = time.perf_counter()
    arrays = explicit_input_arrays(a, grid, full_grid=full_grid)
    if a.num_crossings == 0:
        empty = TriMesh(np.zeros((0, 3)), np.zeros((0, 3), dtype=np.int64))
        return DecodeResult(empty, 0, 0, 0, 0, 0.0, 0.0, time.perf_counter() - t0, {})
    fd, path = tempfile.mkstemp(suffix=".npz", dir=workdir)
    os.close(fd)
    try:
        np.savez(path, **arrays)  # type: ignore[arg-type]
        res = smt.primal_from_npz(path, scoop_bulge=scoop_bulge, merge="combinatorial")
    finally:
        os.unlink(path)
    offsets = np.asarray(res.face_offsets, dtype=np.int64)
    fv = np.asarray(res.face_vertices, dtype=np.int64)
    sizes, counts = np.unique(np.diff(offsets), return_counts=True)
    faces = polygons_to_triangles(offsets, fv)
    mesh = TriMesh(np.asarray(res.vertices, dtype=np.float64).copy(), faces)
    return DecodeResult(
        mesh=mesh,
        non_even_tets=int(res.non_even_tets),
        non_normal_tets=int(res.non_normal_tets),
        non_zero_tets=int(res.non_zero_tets),
        active_tets_written=int(arrays["tets"].shape[0]),
        construction_seconds=float(res.construction_time),
        assembly_seconds=float(res.assembly_time),
        total_seconds=time.perf_counter() - t0,
        polygon_sizes={int(s): int(c) for s, c in zip(sizes, counts, strict=True)},
    )


@dataclass(frozen=True)
class ReferencePipelineResult:
    mesh: TriMesh
    non_even_tets: int
    seconds: float


def reference_pipeline(
    mesh: TriMesh, grid: TetGrid, *, scoop_bulge: float = 1e-3
) -> ReferencePipelineResult:
    """The reference end-to-end pipeline (its own FCPW edge queries) on the same grid.

    Used only for cross-checking our encoder; ``preprocess=False`` keeps the mesh exactly
    where we put it.
    """
    import subgrid_marching as smt

    assert_pinned_reconstructor()
    t0 = time.perf_counter()
    res = smt.primal_from_mesh(
        mesh.vertices,
        mesh.faces.astype(np.int64),
        grid.n,
        preprocess=False,
        scoop_bulge=scoop_bulge,
        merge="combinatorial",
    )
    faces = polygons_to_triangles(res.face_offsets, res.face_vertices)
    out = TriMesh(np.asarray(res.vertices, dtype=np.float64).copy(), faces)
    return ReferencePipelineResult(out, int(res.non_even_tets), time.perf_counter() - t0)


def compare_with_reference_pipeline(
    ours: TriMesh, theirs: TriMesh
) -> dict[str, float | int | bool]:
    """Same connectivity and (near) same vertex positions as the reference pipeline?"""
    same_shape = (
        ours.vertices.shape == theirs.vertices.shape and ours.faces.shape == theirs.faces.shape
    )
    same_faces = bool(same_shape and np.array_equal(ours.faces, theirs.faces))
    vdiff = (
        float(np.abs(ours.vertices - theirs.vertices).max())
        if same_shape and ours.num_vertices
        else -1.0
    )
    return {
        "xcheck_same_connectivity": same_faces,
        "xcheck_max_vertex_diff": vdiff,
        "xcheck_faces_ours": ours.num_faces,
        "xcheck_faces_theirs": theirs.num_faces,
    }

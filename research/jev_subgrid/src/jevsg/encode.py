"""3D -> A: exact crossings of a triangle mesh with every edge of the tet grid.

For every triangle we visit the grid nodes of its (lattice) bounding box, evaluate on
which side of the triangle's plane each node lies, and test only the grid edges whose
endpoints disagree.  Those candidates get the three line-vs-triangle-edge tests.

All five predicates per (triangle, grid edge) pair are evaluated *exactly* on the float64
inputs and ties are broken by the symbolic perturbation of :mod:`jevsg.predicates`
(one global infinitesimal translation of the grid).  Consequences:

* no crossing is counted twice or lost where a grid edge passes exactly through a mesh
  edge or vertex, or where a grid node lies exactly on the surface;
* for a closed input mesh (watertight in the mod-2 sense, self-intersections allowed)
  every tet face carries an even number of crossings, so the reconstruction reports
  ``non_even_tets == 0`` *by construction* rather than "usually".

This is stricter than the reference query handler (FCPW rays on float32 positions plus a
random input offset), and the degeneracy counters are reported instead of hidden
(proposal §5.1: 퇴화 사례 ... 변환 실패·제외 비율을 모두 기록한다).
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

import numpy as np
import numpy.typing as npt

from jevsg.grid import TetGrid
from jevsg.mesh import TriMesh
from jevsg.predicates import PredicateStats, line_side, plane_side
from jevsg.representation import EdgeCoordinates

FloatArray = npt.NDArray[np.float64]
IntArray = npt.NDArray[np.int64]

#: Crossing positions are kept inside ``[T_MARGIN, 1 - T_MARGIN]``.
T_MARGIN = 2.0**-40


@dataclass
class EncodeStats:
    resolution: int
    triangles: int = 0
    degenerate_triangles: int = 0
    node_tests: int = 0
    candidate_segments: int = 0
    crossings: int = 0
    active_edges: int = 0
    t_clamped: int = 0
    t_nudged: int = 0
    seconds: float = 0.0
    predicates: PredicateStats = field(default_factory=PredicateStats)

    def as_dict(self) -> dict[str, float | int]:
        return {
            "resolution": self.resolution,
            "triangles": self.triangles,
            "degenerate_triangles": self.degenerate_triangles,
            "node_tests": self.node_tests,
            "candidate_segments": self.candidate_segments,
            "crossings": self.crossings,
            "active_edges": self.active_edges,
            "t_clamped": self.t_clamped,
            "t_nudged": self.t_nudged,
            "seconds": self.seconds,
            "predicate_evaluations": self.predicates.evaluations,
            "exact_fallbacks": self.predicates.exact_fallbacks,
            "exact_zeros": self.predicates.exact_zeros,
            "sos_resolved": self.predicates.sos_resolved,
        }


def _lattice_box(grid: TetGrid, tri: FloatArray) -> tuple[IntArray, IntArray]:
    """Inclusive lattice bounding boxes that contain every grid edge meeting a triangle."""
    u = (tri + 1.0) * (0.5 * (grid.n - 1))  # inverse of (i*dx - 0.5)*2, up to rounding
    tol = 1e-7
    lo = np.floor(u.min(axis=1) - tol).astype(np.int64)
    hi = np.ceil(u.max(axis=1) + tol).astype(np.int64)
    return np.clip(lo, 0, grid.n), np.clip(hi, 0, grid.n)


def _strictify(ids: IntArray, t: FloatArray) -> tuple[FloatArray, int]:
    """Make positions strictly increasing within each edge (ties only; rare)."""
    nudged = 0
    for _ in range(64):
        same = (np.diff(ids) == 0) & (np.diff(t) <= 0)
        if not np.any(same):
            return t, nudged
        idx = np.nonzero(same)[0] + 1
        # Process left to right so chains of equal values fan out monotonically.
        for i in idx:
            if ids[i] == ids[i - 1] and t[i] <= t[i - 1]:
                t[i] = np.nextafter(t[i - 1], 2.0)
                nudged += 1
    raise RuntimeError("could not make crossing positions strictly increasing")


def encode_mesh(
    mesh: TriMesh, grid: TetGrid, *, max_block: int = 400_000
) -> tuple[EdgeCoordinates, EncodeStats]:
    """Compute A for ``mesh`` (already in grid coordinates) on ``grid``."""
    t0 = time.perf_counter()
    stats = EncodeStats(resolution=grid.n, triangles=mesh.num_faces)
    lo_b, hi_b = grid.lower_bound, grid.upper_bound
    if mesh.num_faces and (mesh.vertices.min() <= lo_b or mesh.vertices.max() >= hi_b):
        raise ValueError(
            "mesh is not strictly inside the grid box; crossings outside it would be lost"
        )
    tri = mesh.triangles()
    if tri.shape[0] == 0:
        stats.seconds = time.perf_counter() - t0
        return EdgeCoordinates.empty(grid.n), stats

    lo, hi = _lattice_box(grid, tri)
    dims = hi - lo + 1
    directions = grid.edge_directions
    hit_edges: list[IntArray] = []
    hit_t: list[FloatArray] = []
    degenerate = np.zeros(tri.shape[0], dtype=bool)

    # Group triangles with identical box shapes so every block is a dense array.
    shape_key = (dims[:, 0] * 4096 + dims[:, 1]) * 4096 + dims[:, 2]
    order = np.argsort(shape_key, kind="stable")
    boundaries = np.nonzero(np.diff(shape_key[order]))[0] + 1
    for group in np.split(order, boundaries):
        sx, sy, sz = (int(v) for v in dims[group[0]])
        nodes_per = sx * sy * sz
        step = max(1, max_block // nodes_per)
        offs = np.stack(
            np.meshgrid(np.arange(sx), np.arange(sy), np.arange(sz), indexing="ij"), axis=-1
        ).reshape(-1, 3)
        for start in range(0, group.size, step):
            g = group[start : start + step]
            _process_block(
                grid,
                tri[g],
                lo[g],
                (sx, sy, sz),
                offs,
                directions,
                stats,
                hit_edges,
                hit_t,
                degenerate,
                g,
            )

    stats.degenerate_triangles = int(degenerate.sum())
    edges = np.concatenate(hit_edges) if hit_edges else np.zeros(0, dtype=np.int64)
    ts = np.concatenate(hit_t) if hit_t else np.zeros(0, dtype=np.float64)
    bad = (ts < T_MARGIN) | (ts > 1.0 - T_MARGIN) | ~np.isfinite(ts)
    stats.t_clamped = int(bad.sum())
    ts = np.clip(np.nan_to_num(ts, nan=0.5), T_MARGIN, 1.0 - T_MARGIN)
    order = np.lexsort((ts, edges))
    edges, ts = edges[order], ts[order]
    ts, stats.t_nudged = _strictify(edges, ts.copy())
    a = EdgeCoordinates.from_hits(grid.n, edges, ts)
    stats.crossings = a.num_crossings
    stats.active_edges = a.num_active_edges
    stats.seconds = time.perf_counter() - t0
    return a, stats


def _process_block(
    grid: TetGrid,
    tri: FloatArray,
    lo: IntArray,
    shape: tuple[int, int, int],
    offs: IntArray,
    directions: dict[tuple[int, int, int], npt.NDArray[np.bool_]],
    stats: EncodeStats,
    hit_edges: list[IntArray],
    hit_t: list[FloatArray],
    degenerate: npt.NDArray[np.bool_],
    tri_index: IntArray,
) -> None:
    sx, sy, sz = shape
    lat = lo[:, None, :] + offs[None, :, :]  # (G, M, 3) lattice coords
    pos = grid.lattice_to_position(lat)
    a = tri[:, None, 0, :]
    b = tri[:, None, 1, :]
    c = tri[:, None, 2, :]
    value, sign = plane_side(a, b, c, pos, stats.predicates)
    stats.node_tests += int(sign.size)
    zero_rows = np.any(sign == 0, axis=1)
    degenerate[tri_index[zero_rows]] = True
    val3 = value.reshape(-1, sx, sy, sz)
    sgn3 = sign.reshape(-1, sx, sy, sz)
    lat3 = lat.reshape(-1, sx, sy, sz, 3)

    for d, exists in directions.items():
        s0 = [slice(max(0, -d[k]), (sx, sy, sz)[k] - max(0, d[k])) for k in range(3)]
        s1 = [slice(sl.start + d[k], sl.stop + d[k]) for k, sl in enumerate(s0)]
        if any(sl.stop <= sl.start for sl in s0):
            continue
        a0 = sgn3[:, s0[0], s0[1], s0[2]]
        a1 = sgn3[:, s1[0], s1[1], s1[2]]
        change = (a0.astype(np.int16) * a1.astype(np.int16)) < 0
        if not np.any(change):
            continue
        gi, li, lj, lk = np.nonzero(change)
        gi_ = gi
        pi, pj, pk = li + s0[0].start, lj + s0[1].start, lk + s0[2].start
        start = lat3[gi_, pi, pj, pk]  # (C, 3)
        keep = exists[start[:, 0], start[:, 1], start[:, 2]]
        if not np.any(keep):
            continue
        gi_, pi, pj, pk, start = gi_[keep], pi[keep], pj[keep], pk[keep], start[keep]
        stats.candidate_segments += int(gi_.size)
        dv = np.asarray(d, dtype=np.int64)
        end = start + dv
        p = grid.lattice_to_position(start)
        q = grid.lattice_to_position(end)
        ta, tb, tc = tri[gi_, 0], tri[gi_, 1], tri[gi_, 2]
        s_ab = line_side(p, q, ta, tb, stats.predicates)
        s_bc = line_side(p, q, tb, tc, stats.predicates)
        s_ca = line_side(p, q, tc, ta, stats.predicates)
        hit = (s_ab == s_bc) & (s_bc == s_ca) & (s_ab != 0)
        if not np.any(hit):
            continue
        vp = val3[gi_[hit], pi[hit], pj[hit], pk[hit]]
        vq = val3[gi_[hit], pi[hit] + d[0], pj[hit] + d[1], pk[hit] + d[2]]
        with np.errstate(divide="ignore", invalid="ignore"):
            t = vp / (vp - vq)
        i_id = grid.node_id(start[hit, 0], start[hit, 1], start[hit, 2])
        j_id = grid.node_id(end[hit, 0], end[hit, 1], end[hit, 2])
        if np.any(i_id >= j_id):  # directions are lower id -> higher id by construction
            raise AssertionError("edge direction table is not canonical")
        hit_edges.append(grid.edge_ids(i_id, j_id))
        hit_t.append(np.asarray(t, dtype=np.float64))

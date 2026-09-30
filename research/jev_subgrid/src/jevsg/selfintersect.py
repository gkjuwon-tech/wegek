"""Exact self-intersection check for triangle meshes.

Two faces *intersect* when they share any point that is not explained by their shared
combinatorics: disjoint faces may not touch at all, faces sharing one vertex may touch
only at that vertex, faces sharing an edge only along that edge.  Every test uses the
exact predicates of :mod:`jevsg.predicates` (no epsilon, no symbolic perturbation), so a
reported intersection is real, including touching contacts, and near-misses are not
reported.  The paper proves the primal output is intersection-free (Appendix D); this
module lets the G1 study *check* that on every reconstruction instead of assuming it.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import numpy.typing as npt

from jevsg.mesh import TriMesh
from jevsg.predicates import orient2d, orient2d_scalar, orient3d

FloatArray = npt.NDArray[np.float64]
IntArray = npt.NDArray[np.int64]
BoolArray = npt.NDArray[np.bool_]
Pt2 = tuple[float, float]


@dataclass
class SelfIntersectionReport:
    faces: int
    candidate_pairs: int = 0
    intersecting_pairs: int = 0
    by_kind: dict[str, int] = field(default_factory=dict)
    intersecting_faces: int = 0
    degenerate_faces: int = 0
    examples: list[tuple[int, int]] = field(default_factory=list)

    @property
    def clean(self) -> bool:
        return self.intersecting_pairs == 0

    def as_dict(self) -> dict[str, object]:
        return {
            "si_candidate_pairs": self.candidate_pairs,
            "si_intersecting_pairs": self.intersecting_pairs,
            "si_intersecting_faces": self.intersecting_faces,
            "si_by_kind": dict(self.by_kind),
            "si_degenerate_faces": self.degenerate_faces,
        }


# --------------------------------------------------------------- candidates
def candidate_pairs(tri: FloatArray, max_pairs: int = 50_000_000) -> tuple[IntArray, IntArray]:
    """Face pairs with overlapping (closed) bounding boxes, via a uniform hash grid."""
    nf = tri.shape[0]
    if nf < 2:
        return np.zeros(0, np.int64), np.zeros(0, np.int64)
    lo = tri.min(axis=1)
    hi = tri.max(axis=1)
    ext = (hi - lo).max(axis=1)
    cell = float(np.quantile(ext, 0.9)) if nf > 10 else float(ext.max())
    span = float((hi.max(axis=0) - lo.min(axis=0)).max())
    cell = max(cell, span * 1e-6, 1e-300)
    origin = lo.min(axis=0)
    clo = np.floor((lo - origin) / cell).astype(np.int64)
    chi = np.floor((hi - origin) / cell).astype(np.int64)
    dims = chi - clo + 1
    ncell = int(chi.max()) + 2
    counts = dims.prod(axis=1)
    face = np.repeat(np.arange(nf, dtype=np.int64), counts)
    local = np.arange(int(counts.sum()), dtype=np.int64) - np.repeat(
        np.cumsum(counts) - counts, counts
    )
    dz = dims[face, 2]
    dy = dims[face, 1]
    cz = clo[face, 2] + local % dz
    cy = clo[face, 1] + (local // dz) % dy
    cx = clo[face, 0] + local // (dz * dy)
    key = (cx * ncell + cy) * ncell + cz
    order = np.lexsort((face, key))
    key, face = key[order], face[order]
    starts = np.concatenate([[0], np.nonzero(np.diff(key))[0] + 1])
    ends = np.concatenate([starts[1:], [key.size]])
    gsize = ends - starts
    group_end = np.repeat(ends, gsize)
    npair = group_end - np.arange(key.size) - 1
    total = int(npair.sum())
    if total > max_pairs:
        raise MemoryError(f"too many candidate pairs ({total})")
    rows = np.repeat(np.arange(key.size), npair)
    cols = rows + 1 + (np.arange(total) - np.repeat(np.cumsum(npair) - npair, npair))
    i, j = face[rows], face[cols]
    a, b = np.minimum(i, j), np.maximum(i, j)
    keep = a != b
    uk = np.unique(a[keep] * nf + b[keep])
    a, b = uk // nf, uk % nf
    overlap = np.all((lo[a] <= hi[b]) & (lo[b] <= hi[a]), axis=1)
    return a[overlap], b[overlap]


# --------------------------------------------------------- exact primitives
def _proj_axes(a: FloatArray, b: FloatArray, c: FloatArray) -> tuple[int, int] | None:
    """Two coordinate axes on which triangle abc projects non-degenerately (exact)."""
    n = np.cross(b - a, c - a)
    for k in np.argsort(-np.abs(n)):
        i0, i1 = (x for x in range(3) if x != int(k))
        if orient2d_scalar((a[i0], a[i1]), (b[i0], b[i1]), (c[i0], c[i1])) != 0:
            return i0, i1
    return None


def _on_segment_2d(p: Pt2, q: Pt2, r: Pt2) -> bool:
    """r collinear with pq (known) and inside the closed segment."""
    return bool(
        min(p[0], q[0]) <= r[0] <= max(p[0], q[0]) and min(p[1], q[1]) <= r[1] <= max(p[1], q[1])
    )


def _segments_intersect_2d(p1: Pt2, p2: Pt2, q1: Pt2, q2: Pt2) -> bool:
    d1 = orient2d_scalar(q1, q2, p1)
    d2 = orient2d_scalar(q1, q2, p2)
    d3 = orient2d_scalar(p1, p2, q1)
    d4 = orient2d_scalar(p1, p2, q2)
    if d1 * d2 < 0 and d3 * d4 < 0:
        return True
    return (
        (d1 == 0 and _on_segment_2d(q1, q2, p1))
        or (d2 == 0 and _on_segment_2d(q1, q2, p2))
        or (d3 == 0 and _on_segment_2d(p1, p2, q1))
        or (d4 == 0 and _on_segment_2d(p1, p2, q2))
    )


def _point_in_triangle_2d(p: Pt2, a: Pt2, b: Pt2, c: Pt2) -> bool:
    s = [orient2d_scalar(a, b, p), orient2d_scalar(b, c, p), orient2d_scalar(c, a, p)]
    return all(x >= 0 for x in s) or all(x <= 0 for x in s)


def _coplanar_segment_triangle(
    p: FloatArray, q: FloatArray, a: FloatArray, b: FloatArray, c: FloatArray
) -> bool:
    axes = _proj_axes(a, b, c)
    if axes is None:
        return False  # degenerate triangle; counted separately
    i0, i1 = axes
    p2, q2, a2, b2, c2 = ((float(v[i0]), float(v[i1])) for v in (p, q, a, b, c))
    if _point_in_triangle_2d(p2, a2, b2, c2) or _point_in_triangle_2d(q2, a2, b2, c2):
        return True
    return any(_segments_intersect_2d(p2, q2, u, v) for u, v in ((a2, b2), (b2, c2), (c2, a2)))


def _coplanar_segment_triangle_vec(
    p: FloatArray, q: FloatArray, a: FloatArray, b: FloatArray, c: FloatArray
) -> BoolArray:
    """Vectorised 2D version of :func:`_coplanar_segment_triangle` (inputs coplanar)."""
    m = p.shape[0]
    out = np.zeros(m, dtype=bool)
    if m == 0:
        return out
    n = np.cross(b - a, c - a)
    drop = np.argmax(np.abs(n), axis=1)
    keep = np.array([[1, 2], [0, 2], [0, 1]])[drop]
    r = np.arange(m)[:, None]

    def proj(x: FloatArray) -> FloatArray:
        return np.asarray(x[r, keep], dtype=np.float64)

    p2, q2, a2, b2, c2 = proj(p), proj(q), proj(a), proj(b), proj(c)
    s_tri = orient2d(a2, b2, c2)[1].astype(np.int16)
    good = s_tri != 0

    def inside(x: FloatArray) -> BoolArray:
        s1 = orient2d(a2, b2, x)[1].astype(np.int16) * s_tri
        s2 = orient2d(b2, c2, x)[1].astype(np.int16) * s_tri
        s3 = orient2d(c2, a2, x)[1].astype(np.int16) * s_tri
        return np.asarray((s1 >= 0) & (s2 >= 0) & (s3 >= 0), dtype=bool)

    def on_seg(u: FloatArray, v: FloatArray, w: FloatArray) -> BoolArray:
        lo = np.minimum(u, v)
        hi = np.maximum(u, v)
        return np.asarray(np.all((lo <= w) & (w <= hi), axis=1), dtype=bool)

    def seg_seg(u1: FloatArray, u2: FloatArray, v1: FloatArray, v2: FloatArray) -> BoolArray:
        d1 = orient2d(v1, v2, u1)[1].astype(np.int16)
        d2 = orient2d(v1, v2, u2)[1].astype(np.int16)
        d3 = orient2d(u1, u2, v1)[1].astype(np.int16)
        d4 = orient2d(u1, u2, v2)[1].astype(np.int16)
        proper = (d1 * d2 < 0) & (d3 * d4 < 0)
        touch = (
            ((d1 == 0) & on_seg(v1, v2, u1))
            | ((d2 == 0) & on_seg(v1, v2, u2))
            | ((d3 == 0) & on_seg(u1, u2, v1))
            | ((d4 == 0) & on_seg(u1, u2, v2))
        )
        return np.asarray(proper | touch, dtype=bool)

    res = inside(p2) | inside(q2)
    for u, v in ((a2, b2), (b2, c2), (c2, a2)):
        res |= seg_seg(p2, q2, u, v)
    out[good] = res[good]
    for k in np.nonzero(~good)[0]:  # degenerate projection: the scalar path picks axes
        out[k] = _coplanar_segment_triangle(p[k], q[k], a[k], b[k], c[k])
    return out


def segment_triangle_closed(
    p: FloatArray, q: FloatArray, a: FloatArray, b: FloatArray, c: FloatArray
) -> BoolArray:
    """Row-wise exact test: does closed segment pq meet closed triangle abc?"""
    if p.shape[0] == 0:
        return np.zeros(0, dtype=bool)
    _, op = orient3d(a, b, c, p)
    _, oq = orient3d(a, b, c, q)
    op = op.astype(np.int16)
    oq = oq.astype(np.int16)
    out = np.zeros(p.shape[0], dtype=bool)
    crossing = op * oq <= 0
    coplanar = (op == 0) & (oq == 0)
    gen = crossing & ~coplanar
    if np.any(gen):
        idx = np.nonzero(gen)[0]
        pp, qq, aa, bb, cc = p[idx], q[idx], a[idx], b[idx], c[idx]
        s1 = orient3d(aa, bb, qq, pp)[1].astype(np.int16)
        s2 = orient3d(bb, cc, qq, pp)[1].astype(np.int16)
        s3 = orient3d(cc, aa, qq, pp)[1].astype(np.int16)
        nondeg = ~((s1 == 0) & (s2 == 0) & (s3 == 0))
        inside = ((s1 >= 0) & (s2 >= 0) & (s3 >= 0)) | ((s1 <= 0) & (s2 <= 0) & (s3 <= 0))
        out[idx] = inside & nondeg
    if np.any(coplanar):
        idx = np.nonzero(coplanar)[0]
        out[idx] = _coplanar_segment_triangle_vec(p[idx], q[idx], a[idx], b[idx], c[idx])
    return out


# ------------------------------------------------------------------- driver
def self_intersections(mesh: TriMesh, max_examples: int = 20) -> SelfIntersectionReport:
    rep = SelfIntersectionReport(faces=mesh.num_faces)
    if mesh.num_faces < 2:
        return rep
    tri = mesh.triangles()
    f = mesh.faces
    cr = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    rep.degenerate_faces = int(np.count_nonzero(~np.any(cr != 0, axis=1)))
    i, j = candidate_pairs(tri)
    rep.candidate_pairs = int(i.size)
    fi, fj = f[i], f[j]
    eq = fi[:, :, None] == fj[:, None, :]  # (P, 3, 3)
    shared = eq.sum(axis=(1, 2))
    hit = np.zeros(i.size, dtype=bool)
    kinds: dict[str, int] = {}

    # --- disjoint faces: any edge of one meets the other
    s0 = np.nonzero(shared == 0)[0]
    if s0.size:
        res = np.zeros(s0.size, dtype=bool)
        for x, y in ((i[s0], j[s0]), (j[s0], i[s0])):
            tx, ty = tri[x], tri[y]
            for ka, kb in ((0, 1), (1, 2), (2, 0)):
                todo = ~res
                if not np.any(todo):
                    break
                sel = np.nonzero(todo)[0]
                res[sel] |= segment_triangle_closed(
                    tx[sel, ka], tx[sel, kb], ty[sel, 0], ty[sel, 1], ty[sel, 2]
                )
        hit[s0] = res
        kinds["disjoint"] = int(res.sum())

    # --- one shared vertex: the edge opposite the shared vertex must stay clear
    s1 = np.nonzero(shared == 1)[0]
    if s1.size:
        res = np.zeros(s1.size, dtype=bool)
        e1 = eq[s1]
        ki = np.argmax(e1.any(axis=2), axis=1)  # local index of shared vertex in face i
        kj = np.argmax(e1.any(axis=1), axis=1)
        for x, y, kx in ((i[s1], j[s1], ki), (j[s1], i[s1], kj)):
            tx, ty = tri[x], tri[y]
            r = np.arange(s1.size)
            u = tx[r, (kx + 1) % 3]
            v = tx[r, (kx + 2) % 3]
            res |= segment_triangle_closed(u, v, ty[:, 0], ty[:, 1], ty[:, 2])
        hit[s1] = res
        kinds["shared_vertex"] = int(res.sum())

    # --- shared edge: only a coplanar fold (apexes on the same side) intersects
    s2 = np.nonzero(shared == 2)[0]
    if s2.size:
        res = np.zeros(s2.size, dtype=bool)
        e2 = eq[s2]
        ai = np.argmin(e2.any(axis=2), axis=1)  # apex (unshared) of face i
        aj = np.argmin(e2.any(axis=1), axis=1)
        r = np.arange(s2.size)
        ti, tj = tri[i[s2]], tri[j[s2]]
        wi = ti[r, ai]
        wj = tj[r, aj]
        u = ti[r, (ai + 1) % 3]
        v = ti[r, (ai + 2) % 3]
        _, cop = orient3d(u, v, wi, wj)
        kk = np.nonzero(cop == 0)[0]
        if kk.size:
            # Coplanar pair: a fold iff both apexes lie on the same side of the shared
            # edge inside the common plane (exact 2D orientation on a projection).
            nrm = np.cross(v[kk] - u[kk], wi[kk] - u[kk])
            keep_ax = np.array([[1, 2], [0, 2], [0, 1]])[np.argmax(np.abs(nrm), axis=1)]
            rr = np.arange(kk.size)[:, None]
            u2, v2 = u[kk][rr, keep_ax], v[kk][rr, keep_ax]
            si = orient2d(u2, v2, wi[kk][rr, keep_ax])[1].astype(np.int16)
            sj = orient2d(u2, v2, wj[kk][rr, keep_ax])[1].astype(np.int16)
            fold = (si != 0) & ((si == sj) | (sj == 0))
            res[kk] = fold
            for m in np.nonzero(si == 0)[0]:  # degenerate projection: scalar exact path
                k = int(kk[m])
                axes = _proj_axes(u[k], v[k], wi[k])
                if axes is None:
                    res[k] = True
                    continue
                i0, i1 = axes
                uu, vv = (u[k][i0], u[k][i1]), (v[k][i0], v[k][i1])
                a_ = orient2d_scalar(uu, vv, (wi[k][i0], wi[k][i1]))
                b_ = orient2d_scalar(uu, vv, (wj[k][i0], wj[k][i1]))
                res[k] = a_ == b_ or b_ == 0
        hit[s2] = res
        kinds["shared_edge_fold"] = int(res.sum())

    s3 = np.nonzero(shared >= 3)[0]
    hit[s3] = True
    if s3.size:
        kinds["duplicate_face"] = int(s3.size)

    rep.intersecting_pairs = int(hit.sum())
    rep.by_kind = {k: v for k, v in kinds.items() if v}
    bad = np.unique(np.concatenate([i[hit], j[hit]]))
    rep.intersecting_faces = int(bad.size)
    rep.examples = [
        (int(x), int(y)) for x, y in zip(i[hit][:max_examples], j[hit][:max_examples], strict=True)
    ]
    return rep

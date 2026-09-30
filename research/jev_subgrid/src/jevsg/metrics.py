"""Geometric evaluation: exact point-to-surface distances, Chamfer / F-score / Hausdorff,
generalized winding numbers, oriented solid volume.

Distances are *point-to-triangle* distances (not point-to-sample), so the only sampling
error is in where we measure, not in what we measure.  Samples are drawn from the whole
surface, which includes inner surfaces (a cup's inner wall, a hollow shell's cavity) as
the proposal requires (§7: 내부 표면도 포함).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import numpy.typing as npt
from scipy.spatial import cKDTree

from jevsg.mesh import TriMesh
from jevsg.topology import face_components, orient_consistently

FloatArray = npt.NDArray[np.float64]
IntArray = npt.NDArray[np.int64]


# ------------------------------------------------------------------ sampling
def sample_surface(mesh: TriMesh, count: int, rng: np.random.Generator) -> FloatArray:
    """Area-uniform random points on the surface."""
    if mesh.num_faces == 0 or count <= 0:
        return np.zeros((0, 3))
    area = mesh.face_areas()
    total = float(area.sum())
    if total <= 0:
        return np.asarray(mesh.vertices[mesh.faces[:count, 0]], dtype=np.float64)
    fidx = rng.choice(mesh.num_faces, size=count, p=area / total)
    r1 = np.sqrt(rng.random(count))
    r2 = rng.random(count)
    t = mesh.triangles()[fidx]
    out = (
        (1.0 - r1)[:, None] * t[:, 0]
        + (r1 * (1.0 - r2))[:, None] * t[:, 1]
        + (r1 * r2)[:, None] * t[:, 2]
    )
    return np.asarray(out, dtype=np.float64)


# ------------------------------------------------------ point-triangle distance
def point_triangle_sqdist(p: FloatArray, a: FloatArray, b: FloatArray, c: FloatArray) -> FloatArray:
    """Squared distance from points to triangles (row-wise), Ericson's region method."""
    ab = b - a
    ac = c - a
    ap = p - a
    d1 = np.einsum("ij,ij->i", ab, ap)
    d2 = np.einsum("ij,ij->i", ac, ap)
    bp = p - b
    d3 = np.einsum("ij,ij->i", ab, bp)
    d4 = np.einsum("ij,ij->i", ac, bp)
    cp = p - c
    d5 = np.einsum("ij,ij->i", ab, cp)
    d6 = np.einsum("ij,ij->i", ac, cp)
    va = d3 * d6 - d5 * d4
    vb = d5 * d2 - d1 * d6
    vc = d1 * d4 - d3 * d2

    closest = np.empty_like(p)
    done = np.zeros(p.shape[0], dtype=bool)

    def put(mask: npt.NDArray[np.bool_], value: FloatArray) -> None:
        m = mask & ~done
        closest[m] = value[m]
        done[m] = True

    with np.errstate(divide="ignore", invalid="ignore"):
        put((d1 <= 0) & (d2 <= 0), a)
        put((d3 >= 0) & (d4 <= d3), b)
        put((d6 >= 0) & (d5 <= d6), c)
        v = d1 / (d1 - d3)
        put((vc <= 0) & (d1 >= 0) & (d3 <= 0), a + v[:, None] * ab)
        w = d2 / (d2 - d6)
        put((vb <= 0) & (d2 >= 0) & (d6 <= 0), a + w[:, None] * ac)
        w2 = (d4 - d3) / ((d4 - d3) + (d5 - d6))
        put((va <= 0) & ((d4 - d3) >= 0) & ((d5 - d6) >= 0), b + w2[:, None] * (c - b))
        denom = 1.0 / (va + vb + vc)
        vv = vb * denom
        ww = vc * denom
        interior = a + vv[:, None] * ab + ww[:, None] * ac
        put(np.ones(p.shape[0], dtype=bool), interior)
    bad = ~np.all(np.isfinite(closest), axis=1)
    if np.any(bad):  # degenerate triangle: fall back to its vertices / edges
        pts = p[bad]
        cand = np.stack([a[bad], b[bad], c[bad]], axis=1)
        dd = ((cand - pts[:, None, :]) ** 2).sum(axis=2)
        closest[bad] = cand[np.arange(pts.shape[0]), np.argmin(dd, axis=1)]
    diff = closest - p
    return np.asarray(np.einsum("ij,ij->i", diff, diff), dtype=np.float64)


class SurfaceDistance:
    """Exact unsigned distance from query points to a triangle mesh."""

    def __init__(self, mesh: TriMesh) -> None:
        if mesh.num_faces == 0:
            raise ValueError("empty mesh")
        self.tri = mesh.triangles()
        self.centroids = self.tri.mean(axis=1)
        self.tri_radius = np.linalg.norm(self.tri - self.centroids[:, None, :], axis=2).max(axis=1)
        self.radius = float(self.tri_radius.max())
        self.tree = cKDTree(self.centroids)
        # Size buckets (powers of two of the circumradius) keep the candidate balls tight
        # even when a few sliver triangles are orders of magnitude larger than the rest.
        level = np.floor(np.log2(np.maximum(self.tri_radius, 1e-300))).astype(np.int64)
        self.buckets: list[tuple[IntArray, float, cKDTree]] = []
        for lv in np.unique(level):
            ids = np.nonzero(level == lv)[0]
            self.buckets.append(
                (ids, float(self.tri_radius[ids].max()), cKDTree(self.centroids[ids]))
            )

    def __call__(
        self, points: FloatArray, k_seed: int = 8, chunk: int = 4_096, budget: int = 1_000_000
    ) -> FloatArray:
        out = np.empty(points.shape[0], dtype=np.float64)
        for s in range(0, points.shape[0], chunk):
            out[s : s + chunk] = self._query(points[s : s + chunk], k_seed, budget)
        return out

    def _pairs_sqdist(self, p: FloatArray, rows: IntArray, cols: IntArray) -> FloatArray:
        t = self.tri[cols]
        return point_triangle_sqdist(p[rows], t[:, 0], t[:, 1], t[:, 2])

    def _query(self, p: FloatArray, k_seed: int, budget: int) -> FloatArray:
        k = min(k_seed, self.centroids.shape[0])
        _, idx = self.tree.query(p, k=k)
        idx = np.asarray(idx).reshape(p.shape[0], k)
        rows = np.repeat(np.arange(p.shape[0]), k)
        d2 = self._pairs_sqdist(p, rows, idx.reshape(-1))
        best = d2.reshape(p.shape[0], k).min(axis=1)
        ub = np.sqrt(best)
        # Any triangle closer than ub has its centroid within ub + (its own radius).
        for ids, rad, tree in self.buckets:
            lists = tree.query_ball_point(p, ub + rad + 1e-12)
            lens = np.fromiter((len(x) for x in lists), dtype=np.int64, count=p.shape[0])
            if int(lens.sum()) == 0:
                continue
            cols_all = ids[
                np.fromiter((i for x in lists for i in x), dtype=np.int64, count=int(lens.sum()))
            ]
            rows_all = np.repeat(np.arange(p.shape[0]), lens)
            dc = np.linalg.norm(self.centroids[cols_all] - p[rows_all], axis=1)
            keep = dc <= ub[rows_all] + self.tri_radius[cols_all] + 1e-12
            rows_all, cols_all = rows_all[keep], cols_all[keep]
            for s in range(0, cols_all.size, budget):
                r, c = rows_all[s : s + budget], cols_all[s : s + budget]
                np.minimum.at(best, r, self._pairs_sqdist(p, r, c))
        return np.asarray(np.sqrt(best), dtype=np.float64)


# ----------------------------------------------------------- winding number
def winding_number(mesh: TriMesh, points: npt.ArrayLike, chunk_faces: int = 200_000) -> FloatArray:
    """Generalized winding number (Jacobson et al. 2013) of points w.r.t. an oriented mesh."""
    pts = np.atleast_2d(np.asarray(points, dtype=np.float64))
    w = np.zeros(pts.shape[0], dtype=np.float64)
    tri = mesh.triangles()
    for s in range(0, tri.shape[0], chunk_faces):
        t = tri[s : s + chunk_faces]
        a = t[None, :, 0, :] - pts[:, None, :]
        b = t[None, :, 1, :] - pts[:, None, :]
        c = t[None, :, 2, :] - pts[:, None, :]
        la, lb, lc = (np.linalg.norm(x, axis=2) for x in (a, b, c))
        num = np.einsum("pfi,pfi->pf", a, np.cross(b, c))
        den = (
            la * lb * lc
            + np.einsum("pfi,pfi->pf", a, b) * lc
            + np.einsum("pfi,pfi->pf", a, c) * lb
            + np.einsum("pfi,pfi->pf", b, c) * la
        )
        w += (2.0 * np.arctan2(num, den)).sum(axis=1)
    return np.asarray(w / (4.0 * np.pi), dtype=np.float64)


def _per_component_winding(
    mesh: TriMesh, fcomp: IntArray, ncomp: int, point: FloatArray
) -> FloatArray:
    t = mesh.triangles() - point[None, None, :]
    a, b, c = t[:, 0], t[:, 1], t[:, 2]
    la, lb, lc = (np.linalg.norm(x, axis=1) for x in (a, b, c))
    num = np.einsum("fi,fi->f", a, np.cross(b, c))
    den = la * lb * lc + (a * b).sum(1) * lc + (a * c).sum(1) * lb + (b * c).sum(1) * la
    omega = 2.0 * np.arctan2(num, den)
    return np.asarray(np.bincount(fcomp, weights=omega, minlength=ncomp) / (4.0 * np.pi))


def signed_volume_per_component(mesh: TriMesh, fcomp: IntArray, ncomp: int) -> FloatArray:
    t = mesh.triangles()
    v = np.einsum("fi,fi->f", t[:, 0], np.cross(t[:, 1], t[:, 2])) / 6.0
    return np.asarray(np.bincount(fcomp, weights=v, minlength=ncomp), dtype=np.float64)


@dataclass(frozen=True)
class OrientedSolid:
    mesh: TriMesh  # faces oriented so that normals point from material into air
    volume: float  # material volume
    component_depth: tuple[int, ...]  # nesting depth of each surface component


def orient_outward(mesh: TriMesh) -> OrientedSolid:
    """Orient every closed component so the mesh bounds a solid (nesting-parity rule).

    A component nested inside an odd number of other components bounds a void and must
    face inward; one nested in an even number faces outward.  Requires disjoint
    components (true for the self-intersection-free reconstructor output and for the
    marching-cubes references).
    """
    if mesh.num_faces == 0:
        return OrientedSolid(mesh, 0.0, ())
    m = orient_consistently(mesh)
    ncomp, fcomp = face_components(m)
    vol = signed_volume_per_component(m, fcomp, ncomp)
    first_face = np.full(ncomp, m.num_faces, dtype=np.int64)
    np.minimum.at(first_face, fcomp, np.arange(m.num_faces, dtype=np.int64))
    depth = np.zeros(ncomp, dtype=np.int64)
    if ncomp > 1:
        for c in range(ncomp):
            # Face centroid of c is on c but (disjointness) not on any other component.
            p = m.vertices[m.faces[first_face[c]]].mean(axis=0)
            w = _per_component_winding(m, fcomp, ncomp, p)
            w[c] = 0.0
            depth[c] = int(np.count_nonzero(np.abs(w) > 0.5))
    want = np.where(depth % 2 == 0, 1.0, -1.0)
    flip_comp = np.sign(vol) != want
    faces = m.faces.copy()
    flip = flip_comp[fcomp]
    faces[flip] = faces[flip][:, ::-1]
    out = TriMesh(m.vertices, faces)
    vol2 = signed_volume_per_component(out, fcomp, ncomp)
    return OrientedSolid(out, float(vol2.sum()), tuple(int(d) for d in depth))


# ------------------------------------------------------------- comparisons
@dataclass(frozen=True)
class SurfaceComparison:
    chamfer_l1: float  # mean of the two mean distances, / reference bbox diagonal
    chamfer_l2: float  # mean of the two mean squared distances, / diagonal^2
    hausdorff: float  # / diagonal
    accuracy_p95: float  # 95th percentile rec->ref distance / diagonal
    completeness_p95: float  # 95th percentile ref->rec distance / diagonal
    fscore: dict[float, float]  # tau (fraction of diagonal) -> F-score
    precision: dict[float, float]
    recall: dict[float, float]
    samples: int

    def as_dict(self) -> dict[str, float]:
        out: dict[str, float] = {
            "chamfer_l1": self.chamfer_l1,
            "chamfer_l2": self.chamfer_l2,
            "hausdorff": self.hausdorff,
            "accuracy_p95": self.accuracy_p95,
            "completeness_p95": self.completeness_p95,
        }
        for tau, f in self.fscore.items():
            out[f"fscore@{tau:g}"] = f
            out[f"precision@{tau:g}"] = self.precision[tau]
            out[f"recall@{tau:g}"] = self.recall[tau]
        return out


def compare_surfaces(
    reference: TriMesh,
    reconstruction: TriMesh,
    *,
    samples: int = 40_000,
    taus: tuple[float, ...] = (0.005, 0.01),
    seed: int = 0,
    reference_distance: SurfaceDistance | None = None,
    reference_samples: FloatArray | None = None,
) -> SurfaceComparison:
    """Symmetric surface comparison; all lengths are fractions of the reference diagonal."""
    diag = reference.bbox_diagonal()
    rng = np.random.default_rng(seed)
    ref_pts = (
        reference_samples
        if reference_samples is not None
        else sample_surface(reference, samples, rng)
    )
    if reconstruction.num_faces == 0 or reconstruction.face_areas().sum() <= 0:
        inf = float("inf")
        zeros = {t: 0.0 for t in taus}
        return SurfaceComparison(inf, inf, inf, inf, inf, zeros, zeros, zeros, samples)
    rec_pts = sample_surface(reconstruction, samples, rng)
    d_ref = reference_distance or SurfaceDistance(reference)
    d_rec = SurfaceDistance(reconstruction)
    acc = d_ref(rec_pts) / diag  # reconstruction -> reference
    comp = d_rec(ref_pts) / diag  # reference -> reconstruction
    prec = {t: float(np.mean(acc < t)) for t in taus}
    rec = {t: float(np.mean(comp < t)) for t in taus}
    f = {
        t: (2 * prec[t] * rec[t] / (prec[t] + rec[t]) if prec[t] + rec[t] > 0 else 0.0)
        for t in taus
    }
    return SurfaceComparison(
        chamfer_l1=float(0.5 * (acc.mean() + comp.mean())),
        chamfer_l2=float(0.5 * ((acc**2).mean() + (comp**2).mean())),
        hausdorff=float(max(acc.max(), comp.max())),
        accuracy_p95=float(np.quantile(acc, 0.95)),
        completeness_p95=float(np.quantile(comp, 0.95)),
        fscore=f,
        precision=prec,
        recall=rec,
        samples=samples,
    )

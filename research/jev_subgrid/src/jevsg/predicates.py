"""Exact geometric predicates on float64 inputs, vectorised with a floating-point filter.

Every predicate first evaluates the determinant in float64 together with Shewchuk's
static error bound (``orient3d`` bound A, ``orient2d`` bound A).  Only when the float
result cannot be trusted (``|det| <= bound``, which includes exact zeros) does the
predicate fall back to exact rational arithmetic on the float inputs.  The returned
signs are therefore the *exact* signs of the determinants of the given float values.

On top of the exact signs, :func:`plane_side` and :func:`line_side` implement a
symbolic perturbation (simulation of simplicity) that corresponds to one global,
infinitesimal translation of the grid by ``delta = (eps, eps**2, eps**3)``.  Because a
single genuine perturbation of the geometry explains every tie-break, all predicates
are mutually consistent: the encoder then counts crossings exactly as they would occur
for a grid in general position (see :mod:`jevsg.encode`).
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass, field
from fractions import Fraction

import numpy as np
import numpy.typing as npt

FloatArray = npt.NDArray[np.float64]
SignArray = npt.NDArray[np.int8]

_EPS = 2.0**-53
O3D_ERRBOUND_A = (7.0 + 56.0 * _EPS) * _EPS
O2D_ERRBOUND_A = (3.0 + 16.0 * _EPS) * _EPS


@dataclass
class PredicateStats:
    """Counters for how often the slow paths were needed (reported by the encoder)."""

    evaluations: int = 0
    exact_fallbacks: int = 0
    exact_zeros: int = 0
    sos_resolved: int = 0
    degenerate: int = 0
    notes: list[str] = field(default_factory=list)

    def merge(self, other: PredicateStats) -> None:
        self.evaluations += other.evaluations
        self.exact_fallbacks += other.exact_fallbacks
        self.exact_zeros += other.exact_zeros
        self.sos_resolved += other.sos_resolved
        self.degenerate += other.degenerate


def _sign(x: Fraction | int) -> int:
    return (x > 0) - (x < 0)


def _to_scaled_ints(values: Sequence[float]) -> tuple[list[int], int]:
    """Exact integers ``X_k`` and a shared exponent ``e`` with ``values[k] = X_k * 2**e``."""
    mant: list[int] = []
    exps: list[int] = []
    for v in values:
        m, e = math.frexp(v)
        mant.append(int(m * (1 << 53)))
        exps.append(e - 53)
    emin = min(exps)
    return [m << (e - emin) for m, e in zip(mant, exps, strict=True)], emin


def _exact_orient3d_int(
    a: np.ndarray, b: np.ndarray, c: np.ndarray, d: np.ndarray
) -> tuple[int, int]:
    """Exact ``det[a-d, b-d, c-d]`` as ``(integer, exponent)`` (value = integer * 2**exponent)."""
    x, e = _to_scaled_ints([float(v) for v in (*a, *b, *c, *d)])
    ax, ay, az, bx, by, bz, cx, cy, cz, dx, dy, dz = x
    adx, ady, adz = ax - dx, ay - dy, az - dz
    bdx, bdy, bdz = bx - dx, by - dy, bz - dz
    cdx, cdy, cdz = cx - dx, cy - dy, cz - dz
    det = (
        adx * (bdy * cdz - bdz * cdy)
        + bdx * (cdy * adz - cdz * ady)
        + cdx * (ady * bdz - adz * bdy)
    )
    return det, 3 * e


def _exact_orient2d_int(a: np.ndarray, b: np.ndarray, c: np.ndarray) -> tuple[int, int]:
    x, e = _to_scaled_ints([float(v) for v in (a[0], a[1], b[0], b[1], c[0], c[1])])
    ax, ay, bx, by, cx, cy = x
    return (ax - cx) * (by - cy) - (ay - cy) * (bx - cx), 2 * e


def _int_to_float(v: int, e: int) -> float:
    try:
        return math.ldexp(float(v), e)
    except OverflowError:
        return math.copysign(math.inf, v)


def _exact_orient3d(a: np.ndarray, b: np.ndarray, c: np.ndarray, d: np.ndarray) -> Fraction:
    v, e = _exact_orient3d_int(a, b, c, d)
    return Fraction(v) * (Fraction(2) ** e)


def _exact_cross(u0: np.ndarray, u1: np.ndarray, v0: np.ndarray, v1: np.ndarray) -> list[int]:
    """Signs-preserving exact ``(u1 - u0) x (v1 - v0)`` (all components share one scale)."""
    x, _ = _to_scaled_ints([float(t) for t in (*u0, *u1, *v0, *v1)])
    u = [x[3 + k] - x[k] for k in range(3)]
    v = [x[9 + k] - x[6 + k] for k in range(3)]
    return [u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0]]


def orient2d_scalar(a: Sequence[float], b: Sequence[float], c: Sequence[float]) -> int:
    """Exact sign of ``det[a-c, b-c]`` for plain 2D points (fast scalar path)."""
    acx = a[0] - c[0]
    acy = a[1] - c[1]
    bcx = b[0] - c[0]
    bcy = b[1] - c[1]
    left = acx * bcy
    right = acy * bcx
    det = left - right
    if abs(det) > O2D_ERRBOUND_A * (abs(left) + abs(right)):
        return 1 if det > 0 else -1
    v, _ = _exact_orient2d_int(np.asarray(a), np.asarray(b), np.asarray(c))
    return _sign(v)


def _rows_to_scaled_ints(vals: FloatArray) -> tuple[npt.NDArray[np.object_], npt.NDArray[np.int64]]:
    """Row-wise exact integer scaling: ``vals[r, k] == ints[r, k] * 2**exp[r]``.

    Vectorised with NumPy object arrays (Python ints), so the exact fallback costs a
    handful of C-level loops instead of one interpreted call per determinant.
    """
    mant, ex = np.frexp(vals)
    m = (mant * float(1 << 53)).astype(np.int64)
    e = ex.astype(np.int64) - 53
    zero = m == 0
    e = np.where(zero, np.iinfo(np.int64).max, e)
    emin = e.min(axis=1)
    emin = np.where(np.all(zero, axis=1), 0, emin)
    shift = np.where(zero, 0, e - emin[:, None])
    ints = np.left_shift(m.astype(object), shift.astype(object))
    return ints, emin


def _object_sign(v: npt.NDArray[np.object_]) -> SignArray:
    return ((v > 0).astype(np.int8) - (v < 0).astype(np.int8)).astype(np.int8)


def _exact_orient3d_rows(pts: FloatArray) -> tuple[SignArray, FloatArray]:
    """Exact sign and rounded value of det[a-d, b-d, c-d] for rows ``pts = (U, 4, 3)``."""
    u = pts.shape[0]
    sign = np.zeros(u, dtype=np.int8)
    val = np.zeros(u, dtype=np.float64)
    # Exactly zero without arithmetic: all four points share one coordinate value.
    flat = np.any(np.all(pts == pts[:, :1, :], axis=1), axis=1)
    todo = np.nonzero(~flat)[0]
    if todo.size == 0:
        return sign, val
    ints, emin = _rows_to_scaled_ints(pts[todo].reshape(todo.size, 12))
    ax, ay, az, bx, by, bz, cx, cy, cz, dx, dy, dz = (ints[:, k] for k in range(12))
    adx, ady, adz = ax - dx, ay - dy, az - dz
    bdx, bdy, bdz = bx - dx, by - dy, bz - dz
    cdx, cdy, cdz = cx - dx, cy - dy, cz - dz
    det = (
        adx * (bdy * cdz - bdz * cdy)
        + bdx * (cdy * adz - cdz * ady)
        + cdx * (ady * bdz - adz * bdy)
    )
    sign[todo] = _object_sign(det)
    with np.errstate(over="ignore"):
        val[todo] = np.ldexp(det.astype(np.float64), 3 * emin)
    return sign, val


def _exact_orient2d_rows(pts: FloatArray) -> tuple[SignArray, FloatArray]:
    """Exact sign and rounded value of det[a-c, b-c] for rows ``pts = (U, 3, 2)``."""
    u = pts.shape[0]
    sign = np.zeros(u, dtype=np.int8)
    val = np.zeros(u, dtype=np.float64)
    flat = np.any(np.all(pts == pts[:, :1, :], axis=1), axis=1)
    todo = np.nonzero(~flat)[0]
    if todo.size == 0:
        return sign, val
    ints, emin = _rows_to_scaled_ints(pts[todo].reshape(todo.size, 6))
    ax, ay, bx, by, cx, cy = (ints[:, k] for k in range(6))
    det = (ax - cx) * (by - cy) - (ay - cy) * (bx - cx)
    sign[todo] = _object_sign(det)
    with np.errstate(over="ignore"):
        val[todo] = np.ldexp(det.astype(np.float64), 2 * emin)
    return sign, val


def _broadcast(*arrs: npt.ArrayLike) -> list[FloatArray]:
    out = np.broadcast_arrays(*[np.asarray(a, dtype=np.float64) for a in arrs])
    return [np.ascontiguousarray(x) for x in out]


def orient3d(
    a: npt.ArrayLike,
    b: npt.ArrayLike,
    c: npt.ArrayLike,
    d: npt.ArrayLike,
    stats: PredicateStats | None = None,
) -> tuple[FloatArray, SignArray]:
    """``det[a-d, b-d, c-d]`` (float approximation) and its *exact* sign.

    Inputs broadcast against each other and have a trailing dimension of 3.
    """
    a_, b_, c_, d_ = _broadcast(a, b, c, d)
    lead = a_.shape[:-1]
    a_, b_, c_, d_ = (x.reshape(-1, 3) for x in (a_, b_, c_, d_))
    ad = a_ - d_
    bd = b_ - d_
    cd = c_ - d_
    adx, ady, adz = ad[..., 0], ad[..., 1], ad[..., 2]
    bdx, bdy, bdz = bd[..., 0], bd[..., 1], bd[..., 2]
    cdx, cdy, cdz = cd[..., 0], cd[..., 1], cd[..., 2]
    bdxcdy, cdxbdy = bdx * cdy, cdx * bdy
    cdxady, adxcdy = cdx * ady, adx * cdy
    adxbdy, bdxady = adx * bdy, bdx * ady
    det = adz * (bdxcdy - cdxbdy) + bdz * (cdxady - adxcdy) + cdz * (adxbdy - bdxady)
    permanent = (
        (np.abs(bdxcdy) + np.abs(cdxbdy)) * np.abs(adz)
        + (np.abs(cdxady) + np.abs(adxcdy)) * np.abs(bdz)
        + (np.abs(adxbdy) + np.abs(bdxady)) * np.abs(cdz)
    )
    sign = np.sign(det).astype(np.int8)
    uncertain = np.abs(det) <= O3D_ERRBOUND_A * permanent
    if stats is not None:
        stats.evaluations += int(det.size)
    if np.any(uncertain):
        sel = np.nonzero(uncertain)[0]
        if stats is not None:
            stats.exact_fallbacks += int(sel.size)
        ex_sign, ex_val = _exact_orient3d_rows(
            np.stack([a_[sel], b_[sel], c_[sel], d_[sel]], axis=1)
        )
        sign[sel] = ex_sign
        det[sel] = ex_val
        if stats is not None:
            stats.exact_zeros += int(np.count_nonzero(ex_sign == 0))
    return det.reshape(lead), sign.reshape(lead)


def orient2d(
    a: npt.ArrayLike, b: npt.ArrayLike, c: npt.ArrayLike, stats: PredicateStats | None = None
) -> tuple[FloatArray, SignArray]:
    """``det[a-c, b-c]`` (float approximation) and its exact sign; trailing dim 2."""
    a_, b_, c_ = _broadcast(a, b, c)
    lead = a_.shape[:-1]
    a_, b_, c_ = (x.reshape(-1, 2) for x in (a_, b_, c_))
    acx = a_[..., 0] - c_[..., 0]
    acy = a_[..., 1] - c_[..., 1]
    bcx = b_[..., 0] - c_[..., 0]
    bcy = b_[..., 1] - c_[..., 1]
    left = acx * bcy
    right = acy * bcx
    det = left - right
    sign = np.sign(det).astype(np.int8)
    uncertain = np.abs(det) <= O2D_ERRBOUND_A * (np.abs(left) + np.abs(right))
    if stats is not None:
        stats.evaluations += int(det.size)
    if np.any(uncertain):
        sel = np.nonzero(uncertain)[0]
        if stats is not None:
            stats.exact_fallbacks += int(sel.size)
        ex_sign, ex_val = _exact_orient2d_rows(np.stack([a_[sel], b_[sel], c_[sel]], axis=1))
        sign[sel] = ex_sign
        det[sel] = ex_val
        if stats is not None:
            stats.exact_zeros += int(np.count_nonzero(ex_sign == 0))
    return det.reshape(lead), sign.reshape(lead)


def plane_side(
    a: npt.ArrayLike,
    b: npt.ArrayLike,
    c: npt.ArrayLike,
    p: npt.ArrayLike,
    stats: PredicateStats | None = None,
) -> tuple[FloatArray, SignArray]:
    """Side of the (perturbed) point ``p + delta`` w.r.t. the plane of triangle ``abc``.

    Returns ``value ~= ((b-a) x (c-a)) . (p-a)`` and its exact, symbolically perturbed sign.
    The sign is 0 only for degenerate (zero-area) triangles.
    """
    a_, b_, c_, p_ = _broadcast(a, b, c, p)
    det, sign = orient3d(a_, b_, c_, p_, stats)
    value = -det
    sign = (-sign).astype(np.int8)
    zero = sign == 0
    if np.any(zero):
        for ix in map(tuple, np.argwhere(zero)):
            nrm = _exact_cross(a_[ix], b_[ix], a_[ix], c_[ix])  # (b-a) x (c-a)
            s = next((_sign(v) for v in nrm if v != 0), 0)
            sign[ix] = s
            if stats is not None:
                if s == 0:
                    stats.degenerate += 1
                else:
                    stats.sos_resolved += 1
    return value, sign


def line_side(
    p: npt.ArrayLike,
    q: npt.ArrayLike,
    x: npt.ArrayLike,
    y: npt.ArrayLike,
    stats: PredicateStats | None = None,
) -> SignArray:
    """Exact, perturbed sign of ``det[q-p, x-p, y-p]`` for the translated line ``pq + delta``.

    Geometrically: on which side the directed line ``p -> q`` passes the directed segment
    ``x -> y``.  The sign is 0 only when ``x - y`` is parallel to ``q - p`` (a case the
    encoder never reaches because the plane test rejects it first).
    """
    p_, q_, x_, y_ = _broadcast(p, q, x, y)
    _, sign = orient3d(x_, y_, q_, p_, stats)
    zero = sign == 0
    if np.any(zero):
        for ix in map(tuple, np.argwhere(zero)):
            cr = _exact_cross(y_[ix], x_[ix], p_[ix], q_[ix])  # (x - y) x (q - p)
            s = next((_sign(v) for v in cr if v != 0), 0)
            sign[ix] = s
            if stats is not None:
                if s == 0:
                    stats.degenerate += 1
                else:
                    stats.sos_resolved += 1
    return sign

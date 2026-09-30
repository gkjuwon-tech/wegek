"""Tiny signed-distance toolkit used to author the G1 test shapes.

Primitives are exact SDFs; CSG uses ``min``/``max`` so the result has the correct sign
(which is all marching cubes needs).  Distances of composite shapes are bounds, which is
why probe clearances are verified against the final reference *mesh*, not the SDF.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

FloatArray = npt.NDArray[np.float64]
SDFFn = Callable[[FloatArray], FloatArray]


@dataclass(frozen=True)
class SDF:
    fn: SDFFn

    def __call__(self, p: FloatArray) -> FloatArray:
        return self.fn(np.asarray(p, dtype=np.float64))

    def __or__(self, other: SDF) -> SDF:  # union
        return SDF(lambda p: np.minimum(self.fn(p), other.fn(p)))

    def __and__(self, other: SDF) -> SDF:  # intersection
        return SDF(lambda p: np.maximum(self.fn(p), other.fn(p)))

    def __sub__(self, other: SDF) -> SDF:  # difference
        return SDF(lambda p: np.maximum(self.fn(p), -other.fn(p)))

    def translate(self, t: npt.ArrayLike) -> SDF:
        tv = np.asarray(t, dtype=np.float64)
        return SDF(lambda p: self.fn(p - tv))

    def rotate(self, r: FloatArray) -> SDF:
        """Rotate the shape by the rotation matrix ``r`` (points map ``x -> r @ x``)."""
        rot = np.asarray(r, dtype=np.float64)
        return SDF(lambda p: self.fn(p @ rot))  # row-vector form of r.T @ p


def union(*parts: SDF) -> SDF:
    out = parts[0]
    for p in parts[1:]:
        out = out | p
    return out


def sphere(r: float, center: npt.ArrayLike = (0, 0, 0)) -> SDF:
    c = np.asarray(center, dtype=np.float64)
    return SDF(lambda p: np.linalg.norm(p - c, axis=-1) - r)


def box(half: npt.ArrayLike, center: npt.ArrayLike = (0, 0, 0)) -> SDF:
    h = np.asarray(half, dtype=np.float64)
    c = np.asarray(center, dtype=np.float64)

    def f(p: FloatArray) -> FloatArray:
        q = np.abs(p - c) - h
        outside = np.linalg.norm(np.maximum(q, 0.0), axis=-1)
        inside = np.minimum(np.max(q, axis=-1), 0.0)
        return np.asarray(outside + inside, dtype=np.float64)

    return SDF(f)


def cylinder_z(r: float, z0: float, z1: float, center_xy: npt.ArrayLike = (0, 0)) -> SDF:
    """Solid capped cylinder with axis along z from ``z0`` to ``z1``."""
    cxy = np.asarray(center_xy, dtype=np.float64)
    zc, hz = 0.5 * (z0 + z1), 0.5 * (z1 - z0)

    def f(p: FloatArray) -> FloatArray:
        d0 = np.linalg.norm(p[..., :2] - cxy, axis=-1) - r
        d1 = np.abs(p[..., 2] - zc) - hz
        outside = np.hypot(np.maximum(d0, 0.0), np.maximum(d1, 0.0))
        inside = np.minimum(np.maximum(d0, d1), 0.0)
        return np.asarray(outside + inside, dtype=np.float64)

    return SDF(f)


def capsule(a: npt.ArrayLike, b: npt.ArrayLike, r: float) -> SDF:
    av = np.asarray(a, dtype=np.float64)
    bv = np.asarray(b, dtype=np.float64)
    ab = bv - av
    denom = float(ab @ ab)

    def f(p: FloatArray) -> FloatArray:
        ap = p - av
        t = np.clip((ap @ ab) / denom, 0.0, 1.0)
        return np.asarray(np.linalg.norm(ap - t[..., None] * ab, axis=-1) - r, dtype=np.float64)

    return SDF(f)


def torus_z(major: float, minor: float, center: npt.ArrayLike = (0, 0, 0)) -> SDF:
    """Torus around the z axis (ring in the xy-plane)."""
    c = np.asarray(center, dtype=np.float64)

    def f(p: FloatArray) -> FloatArray:
        q = p - c
        rad = np.hypot(q[..., 0], q[..., 1]) - major
        return np.asarray(np.hypot(rad, q[..., 2]) - minor, dtype=np.float64)

    return SDF(f)


def halfspace(normal: npt.ArrayLike, offset: float) -> SDF:
    """``{x : n.x <= offset}`` with unit ``n``."""
    n = np.asarray(normal, dtype=np.float64)
    n = n / np.linalg.norm(n)
    return SDF(lambda p: p @ n - offset)


def polar_cap(alpha: float) -> SDF:
    """Points whose polar angle from +z is at most ``alpha`` (a cone through the origin).

    Cutting a spherical shell with this cone gives a rim face perpendicular to both shell
    surfaces (no acute wedge), unlike a planar cut below the equator.  The value is the
    exact distance to the cone for points whose projection falls on the cone's ray, which
    holds everywhere near a shell centred at the origin.
    """
    ca, sa = float(np.cos(alpha)), float(np.sin(alpha))

    def f(p: FloatArray) -> FloatArray:
        rho = np.hypot(p[..., 0], p[..., 1])
        return np.asarray(rho * ca - p[..., 2] * sa, dtype=np.float64)

    return SDF(f)


def rotation_x(angle: float) -> FloatArray:
    c, s = np.cos(angle), np.sin(angle)
    return np.array([[1, 0, 0], [0, c, -s], [0, s, c]], dtype=np.float64)


def rotation_y(angle: float) -> FloatArray:
    c, s = np.cos(angle), np.sin(angle)
    return np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]], dtype=np.float64)


def random_rotation(rng: np.random.Generator) -> FloatArray:
    """Uniformly random rotation (QR of a Gaussian matrix, sign-fixed, det +1)."""
    q, r = np.linalg.qr(rng.normal(size=(3, 3)))
    q = q @ np.diag(np.sign(np.diag(r)))
    if np.linalg.det(q) < 0:
        q[:, 0] = -q[:, 0]
    return np.asarray(q, dtype=np.float64)

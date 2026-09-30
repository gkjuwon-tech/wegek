"""Minimal triangle-mesh container, I/O and preprocessing.

Preprocessing follows the reference implementation's documented steps (weld identical
positions, centre, scale into 98 % of ``[-1, 1]^3``) except for one deliberate change:
the reference adds a fixed-seed rigid offset to dodge degenerate ray/grid coincidences.
Our encoder resolves those coincidences exactly (symbolic perturbation), so the offset is
optional here and, when used, recorded in the transform.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import numpy.typing as npt

FloatArray = npt.NDArray[np.float64]
IntArray = npt.NDArray[np.int64]


@dataclass(frozen=True)
class TriMesh:
    vertices: FloatArray  # (V, 3) float64
    faces: IntArray  # (F, 3) int64

    def __post_init__(self) -> None:
        v = np.ascontiguousarray(self.vertices, dtype=np.float64)
        f = np.ascontiguousarray(self.faces, dtype=np.int64)
        if v.ndim != 2 or v.shape[1] != 3:
            raise ValueError(f"vertices must be (V, 3), got {v.shape}")
        if f.ndim != 2 or (f.size and f.shape[1] != 3):
            raise ValueError(f"faces must be (F, 3), got {f.shape}")
        f = f.reshape(-1, 3)
        if f.size and (f.min() < 0 or f.max() >= len(v)):
            raise ValueError("face index out of range")
        if not np.all(np.isfinite(v)):
            raise ValueError("non-finite vertex coordinates")
        object.__setattr__(self, "vertices", v)
        object.__setattr__(self, "faces", f)

    @property
    def num_vertices(self) -> int:
        return int(self.vertices.shape[0])

    @property
    def num_faces(self) -> int:
        return int(self.faces.shape[0])

    def triangles(self) -> FloatArray:
        """``(F, 3, 3)`` corner positions."""
        return np.asarray(self.vertices[self.faces], dtype=np.float64)

    def face_areas(self) -> FloatArray:
        t = self.triangles()
        cr = np.cross(t[:, 1] - t[:, 0], t[:, 2] - t[:, 0])
        return np.asarray(0.5 * np.linalg.norm(cr, axis=1), dtype=np.float64)

    def bbox(self) -> tuple[FloatArray, FloatArray]:
        return self.vertices.min(axis=0), self.vertices.max(axis=0)

    def bbox_diagonal(self) -> float:
        lo, hi = self.bbox()
        return float(np.linalg.norm(hi - lo))

    def flipped(self) -> TriMesh:
        return TriMesh(self.vertices, self.faces[:, ::-1].copy())

    def transformed(self, scale: float, translation: npt.ArrayLike) -> TriMesh:
        t = np.asarray(translation, dtype=np.float64)
        return TriMesh(self.vertices * scale + t, self.faces)


def polygons_to_triangles(face_offsets: npt.ArrayLike, face_vertices: npt.ArrayLike) -> IntArray:
    """Fan-triangulate CSR polygons (the reconstructor may emit n-gons)."""
    off = np.asarray(face_offsets, dtype=np.int64)
    fv = np.asarray(face_vertices, dtype=np.int64)
    sizes = np.diff(off)
    if sizes.size == 0:
        return np.zeros((0, 3), dtype=np.int64)
    if np.all(sizes == 3):
        return np.asarray(fv.reshape(-1, 3).copy(), dtype=np.int64)
    if np.any(sizes < 3):
        raise ValueError("polygon with fewer than 3 vertices")
    tris = []
    for s in np.unique(sizes):
        idx = np.nonzero(sizes == s)[0]
        start = off[idx]
        for k in range(1, int(s) - 1):
            tris.append(np.stack([fv[start], fv[start + k], fv[start + k + 1]], axis=1))
    return np.concatenate(tris, axis=0)


def weld(mesh: TriMesh) -> TriMesh:
    """Merge vertices with bit-identical positions and drop unreferenced ones.

    Mirrors step 1 of the reference preprocessing ("soup representations of watertight
    meshes stay watertight").  No tolerance is used.
    """
    uniq, inv = np.unique(mesh.vertices, axis=0, return_inverse=True)
    faces = inv.reshape(-1)[mesh.faces]
    return compact(TriMesh(uniq, faces))


def compact(mesh: TriMesh) -> TriMesh:
    """Drop unreferenced vertices (order preserving)."""
    used = np.zeros(mesh.num_vertices, dtype=bool)
    used[mesh.faces.reshape(-1)] = True
    remap = np.cumsum(used) - 1
    return TriMesh(mesh.vertices[used], remap[mesh.faces])


def drop_collapsed_faces(mesh: TriMesh) -> tuple[TriMesh, int]:
    """Remove faces that repeat a vertex index (combinatorially collapsed)."""
    f = mesh.faces
    bad = (f[:, 0] == f[:, 1]) | (f[:, 1] == f[:, 2]) | (f[:, 0] == f[:, 2])
    return compact(TriMesh(mesh.vertices, f[~bad])), int(bad.sum())


@dataclass(frozen=True)
class Normalization:
    """``x_grid = x_world * scale + translation``."""

    scale: float
    translation: tuple[float, float, float]

    def apply(self, pts: npt.ArrayLike) -> FloatArray:
        out = np.asarray(pts, dtype=np.float64) * self.scale + np.asarray(self.translation)
        return np.asarray(out, dtype=np.float64)

    def invert(self, pts: npt.ArrayLike) -> FloatArray:
        out = (np.asarray(pts, dtype=np.float64) - np.asarray(self.translation)) / self.scale
        return np.asarray(out, dtype=np.float64)

    def as_dict(self) -> dict[str, object]:
        return {"scale": self.scale, "translation": list(self.translation)}


def fit_normalization(
    vertices: npt.ArrayLike,
    fill: float = 0.98,
    offset_seed: int | None = None,
    offset_magnitude: float | None = None,
) -> Normalization:
    """Centre the bounding box at the origin and scale its largest side to ``2*fill``.

    With ``offset_seed`` a rigid offset of magnitude ``(1 - fill)/2`` (0.01 by default,
    as in the reference) in a seeded random direction is added.
    """
    v = np.asarray(vertices, dtype=np.float64)
    lo, hi = v.min(axis=0), v.max(axis=0)
    centre = 0.5 * (lo + hi)
    extent = float(np.max(hi - lo))
    if extent <= 0:
        raise ValueError("degenerate mesh extent")
    scale = 2.0 * fill / extent
    translation = -centre * scale
    if offset_seed is not None:
        mag = (1.0 - fill) * 0.5 if offset_magnitude is None else offset_magnitude
        rng = np.random.default_rng(offset_seed)
        d = rng.normal(size=3)
        d /= np.linalg.norm(d)
        translation = translation + mag * d
    return Normalization(
        scale, (float(translation[0]), float(translation[1]), float(translation[2]))
    )


def normalize(mesh: TriMesh, norm: Normalization) -> TriMesh:
    return TriMesh(norm.apply(mesh.vertices), mesh.faces)


# ---------------------------------------------------------------------------- I/O
def save_obj(path: str | Path, mesh: TriMesh, header: str | None = None) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        if header:
            for line in header.splitlines():
                fh.write(f"# {line}\n")
        np.savetxt(fh, mesh.vertices, fmt="v %.17g %.17g %.17g")
        np.savetxt(fh, mesh.faces + 1, fmt="f %d %d %d")


def load_obj(path: str | Path) -> TriMesh:
    verts: list[list[float]] = []
    faces: list[list[int]] = []
    with Path(path).open(encoding="utf-8") as fh:
        for line in fh:
            if line.startswith("v "):
                verts.append([float(x) for x in line.split()[1:4]])
            elif line.startswith("f "):
                idx = [int(tok.split("/")[0]) for tok in line.split()[1:]]
                idx = [i - 1 if i > 0 else len(verts) + i for i in idx]
                for k in range(1, len(idx) - 1):
                    faces.append([idx[0], idx[k], idx[k + 1]])
    return TriMesh(np.array(verts, dtype=np.float64).reshape(-1, 3), np.array(faces).reshape(-1, 3))

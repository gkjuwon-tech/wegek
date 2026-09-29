"""Small analytic test meshes."""

from __future__ import annotations

import numpy as np

from jevsg.mesh import TriMesh


def icosphere(
    subdiv: int = 2, radius: float = 1.0, center: tuple[float, float, float] = (0, 0, 0)
) -> TriMesh:
    t = (1 + 5**0.5) / 2
    v = np.array(
        [
            [-1, t, 0],
            [1, t, 0],
            [-1, -t, 0],
            [1, -t, 0],
            [0, -1, t],
            [0, 1, t],
            [0, -1, -t],
            [0, 1, -t],
            [t, 0, -1],
            [t, 0, 1],
            [-t, 0, -1],
            [-t, 0, 1],
        ],
        dtype=float,
    )
    f = np.array(
        [
            [0, 11, 5],
            [0, 5, 1],
            [0, 1, 7],
            [0, 7, 10],
            [0, 10, 11],
            [1, 5, 9],
            [5, 11, 4],
            [11, 10, 2],
            [10, 7, 6],
            [7, 1, 8],
            [3, 9, 4],
            [3, 4, 2],
            [3, 2, 6],
            [3, 6, 8],
            [3, 8, 9],
            [4, 9, 5],
            [2, 4, 11],
            [6, 2, 10],
            [8, 6, 7],
            [9, 8, 1],
        ]
    )
    verts = list(v / np.linalg.norm(v, axis=1, keepdims=True))
    faces = [tuple(x) for x in f]
    for _ in range(subdiv):
        cache: dict[tuple[int, int], int] = {}

        def mid(a: int, b: int, cache: dict[tuple[int, int], int] = cache) -> int:
            key = (min(a, b), max(a, b))
            if key not in cache:
                m = verts[a] + verts[b]
                verts.append(m / np.linalg.norm(m))
                cache[key] = len(verts) - 1
            return cache[key]

        new = []
        for a, b, c in faces:
            ab, bc, ca = mid(a, b), mid(b, c), mid(c, a)
            new += [(a, ab, ca), (b, bc, ab), (c, ca, bc), (ab, bc, ca)]
        faces = new
    return TriMesh(np.array(verts) * radius + np.asarray(center, dtype=float), np.array(faces))


def torus(
    major: float = 0.6,
    minor: float = 0.2,
    nu: int = 48,
    nv: int = 24,
    center: tuple[float, float, float] = (0, 0, 0),
) -> TriMesh:
    u = np.linspace(0, 2 * np.pi, nu, endpoint=False)
    v = np.linspace(0, 2 * np.pi, nv, endpoint=False)
    uu, vv = np.meshgrid(u, v, indexing="ij")
    x = (major + minor * np.cos(vv)) * np.cos(uu)
    y = (major + minor * np.cos(vv)) * np.sin(uu)
    z = minor * np.sin(vv)
    verts = np.stack([x, y, z], axis=-1).reshape(-1, 3) + np.asarray(center, dtype=float)
    idx = np.arange(nu * nv).reshape(nu, nv)
    a = idx
    b = np.roll(idx, -1, axis=0)
    c = np.roll(np.roll(idx, -1, axis=0), -1, axis=1)
    d = np.roll(idx, -1, axis=1)
    faces = np.concatenate(
        [np.stack([a, b, c], -1).reshape(-1, 3), np.stack([a, c, d], -1).reshape(-1, 3)]
    )
    return TriMesh(verts, faces)


def box(lo: tuple[float, float, float], hi: tuple[float, float, float]) -> TriMesh:
    x0, y0, z0 = lo
    x1, y1, z1 = hi
    v = np.array(
        [
            [x0, y0, z0],
            [x1, y0, z0],
            [x1, y1, z0],
            [x0, y1, z0],
            [x0, y0, z1],
            [x1, y0, z1],
            [x1, y1, z1],
            [x0, y1, z1],
        ],
        dtype=float,
    )
    f = np.array(
        [
            [0, 2, 1],
            [0, 3, 2],
            [4, 5, 6],
            [4, 6, 7],
            [0, 1, 5],
            [0, 5, 4],
            [1, 2, 6],
            [1, 6, 5],
            [2, 3, 7],
            [2, 7, 6],
            [3, 0, 4],
            [3, 4, 7],
        ]
    )
    return TriMesh(v, f)


def concat(*meshes: TriMesh) -> TriMesh:
    verts, faces, off = [], [], 0
    for m in meshes:
        verts.append(m.vertices)
        faces.append(m.faces + off)
        off += m.num_vertices
    return TriMesh(np.concatenate(verts), np.concatenate(faces))


def mobius(n: int = 40, width: float = 0.3, radius: float = 0.6) -> TriMesh:
    t = np.linspace(0, 2 * np.pi, n, endpoint=False)
    verts = []
    for s in (-width, width):
        verts.append(
            np.stack(
                [
                    (radius + s * np.cos(t / 2)) * np.cos(t),
                    (radius + s * np.cos(t / 2)) * np.sin(t),
                    s * np.sin(t / 2),
                ],
                axis=1,
            )
        )
    v = np.concatenate(verts)
    faces = []
    for i in range(n):
        j = (i + 1) % n
        a, b = i, n + i
        if j == 0:  # the half twist swaps the two rails
            c, d = n + j, j
        else:
            c, d = j, n + j
        faces += [(a, c, b), (b, c, d)]
    return TriMesh(v, np.array(faces))

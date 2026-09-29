"""The fixed conforming tetrahedral grid ``T`` on which the representation A lives.

The grid reproduces, bit for bit, the implicit grid of the reference
implementation (``subgrid-marching`` 1.0.0, ``include/grid/grid_iterators.h``):

* ``n`` cubes per axis, ``(n + 1)**3`` nodes, node id ``z*(n+1)**2 + y*(n+1) + x``;
* node position ``(x*dx - 0.5) * 2`` per axis with ``dx = 1/(n-1)``, so node indices
  ``0 .. n-1`` span ``[-1, 1]`` exactly and the last layer sits slightly past ``+1``;
* every cube is split into 5 tetrahedra, with the split alternating by the parity of
  ``ix + iy + iz`` so that shared faces agree (the grid is conforming);
* tetrahedra are enumerated ``iz`` outermost, ``ix`` innermost, 5 per cube, and each
  tetrahedron keeps the reference vertex order.

Reproducing the order exactly matters: the reconstructor uses global vertex ids for its
orientation-independent tie-breaking, so an identical grid lets us check our encoder
against the reference query pipeline output for output (see ``tests/test_decode.py``).

Every grid edge gets a global, fixed id.  Edges are stored canonically as ``(i, j)``
with ``i < j`` and sorted lexicographically, and the id is the row in that table
(proposal §5.1: "모서리의 방향과 ID는 전역에서 고정한다").
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import cached_property

import numpy as np
import numpy.typing as npt

IntArray = npt.NDArray[np.int64]
FloatArray = npt.NDArray[np.float64]
BoolArray = npt.NDArray[np.bool_]

#: Tet-local edge order used by the reference implementation (``ALL_TET_PAIRS``).
TET_EDGE_PAIRS: tuple[tuple[int, int], ...] = ((0, 1), (0, 2), (0, 3), (1, 2), (1, 3), (2, 3))
#: The four faces of a tet as local vertex triples.
TET_FACE_TRIPLES: tuple[tuple[int, int, int], ...] = ((0, 1, 2), (0, 1, 3), (0, 2, 3), (1, 2, 3))

# Cube corners, reference layout (A..H), as (dx, dy, dz) offsets.
_CORNERS: dict[str, tuple[int, int, int]] = {
    "A": (0, 0, 0),
    "B": (1, 0, 0),
    "C": (1, 1, 0),
    "D": (0, 1, 0),
    "E": (0, 0, 1),
    "F": (1, 0, 1),
    "G": (0, 1, 1),
    "H": (1, 1, 1),
}
_EVEN_TETS = ("ACFG", "DAGC", "BACF", "EFGA", "HFCG")
_ODD_TETS = ("BEHD", "BEAD", "BCHD", "BEHF", "GEHD")

#: Identifier written into serialized A files; bump it if the grid layout ever changes.
GRID_SCHEME_ID = 1
GRID_SCHEME_NAME = "subgrid-marching-1.0.0/5-tet-alternating"


@dataclass(frozen=True)
class TetGrid:
    """Uniform conforming 5-tet grid with ``n`` cubes per axis (``n >= 2``)."""

    n: int

    def __post_init__(self) -> None:
        if not isinstance(self.n, int | np.integer) or self.n < 2:
            raise ValueError(f"grid resolution must be an integer >= 2, got {self.n!r}")
        if (self.n + 1) ** 3 >= 2**31:
            raise ValueError("grid too large for int32 vertex ids (reconstructor input format)")

    # ------------------------------------------------------------------ nodes
    @property
    def nodes_per_axis(self) -> int:
        return self.n + 1

    @property
    def num_nodes(self) -> int:
        return (self.n + 1) ** 3

    @property
    def spacing(self) -> float:
        """Distance between neighbouring nodes along an axis (``2 / (n - 1)``)."""
        return 2.0 / (self.n - 1)

    @property
    def dx(self) -> float:
        return 1.0 / (self.n - 1)

    def node_id(self, x: npt.ArrayLike, y: npt.ArrayLike, z: npt.ArrayLike) -> IntArray:
        m = self.n + 1
        return (np.asarray(z, dtype=np.int64) * m + np.asarray(y, dtype=np.int64)) * m + np.asarray(
            x, dtype=np.int64
        )

    def node_coords(self, ids: npt.ArrayLike) -> IntArray:
        """Integer lattice coordinates ``(x, y, z)`` of node ids, shape ``(..., 3)``."""
        ids = np.asarray(ids, dtype=np.int64)
        m = self.n + 1
        x = ids % m
        y = (ids // m) % m
        z = ids // (m * m)
        return np.stack([x, y, z], axis=-1)

    def lattice_to_position(self, xyz: npt.ArrayLike) -> FloatArray:
        """Exactly the reference float formula ``(i*dx - 0.5) * 2`` applied per axis."""
        xyz = np.asarray(xyz, dtype=np.float64)
        return (xyz * self.dx - 0.5) * 2.0

    @cached_property
    def node_positions(self) -> FloatArray:
        coords = self.node_coords(np.arange(self.num_nodes, dtype=np.int64))
        pos = self.lattice_to_position(coords)
        pos.setflags(write=False)
        return pos

    @cached_property
    def axis_positions(self) -> FloatArray:
        """The ``n + 1`` distinct node coordinates along any axis (identical per axis)."""
        return self.lattice_to_position(np.arange(self.n + 1))

    @property
    def lower_bound(self) -> float:
        return -1.0

    @property
    def upper_bound(self) -> float:
        return float(self.axis_positions[-1])

    # ------------------------------------------------------------------- tets
    @cached_property
    def tets(self) -> npt.NDArray[np.int32]:
        """``(5 n^3, 4)`` tetrahedra in the reference enumeration order."""
        n = self.n
        gz, gy, gx = np.meshgrid(np.arange(n), np.arange(n), np.arange(n), indexing="ij")
        ix, iy, iz = gx.ravel(), gy.ravel(), gz.ravel()  # ix fastest, iz slowest
        even = ((ix + iy + iz) % 2) == 0
        corner = {
            name: self.node_id(ix + off[0], iy + off[1], iz + off[2])
            for name, off in _CORNERS.items()
        }
        out = np.empty((ix.size, 5, 4), dtype=np.int64)
        for t in range(5):
            for v in range(4):
                even_id = corner[_EVEN_TETS[t][v]]
                odd_id = corner[_ODD_TETS[t][v]]
                out[:, t, v] = np.where(even, even_id, odd_id)
        tets = out.reshape(-1, 4).astype(np.int32)
        tets.setflags(write=False)
        return tets

    @property
    def num_tets(self) -> int:
        return 5 * self.n**3

    # ------------------------------------------------------------------ edges
    @cached_property
    def _edge_keys(self) -> IntArray:
        tets = self.tets.astype(np.int64)
        pairs = np.concatenate([tets[:, [a, b]] for a, b in TET_EDGE_PAIRS], axis=0)
        lo = pairs.min(axis=1)
        hi = pairs.max(axis=1)
        keys = np.unique(lo * self.num_nodes + hi)
        keys.setflags(write=False)
        return keys

    @cached_property
    def edges(self) -> IntArray:
        """``(E, 2)`` canonical edges ``(i, j)``, ``i < j``; the row index is the edge id."""
        keys = self._edge_keys
        e = np.stack([keys // self.num_nodes, keys % self.num_nodes], axis=1)
        e.setflags(write=False)
        return e

    @property
    def num_edges(self) -> int:
        return int(self._edge_keys.size)

    def edge_ids(self, i: npt.ArrayLike, j: npt.ArrayLike, *, strict: bool = True) -> IntArray:
        """Edge ids for node pairs given in either order; ``-1`` (or error) if absent."""
        i = np.asarray(i, dtype=np.int64)
        j = np.asarray(j, dtype=np.int64)
        lo = np.minimum(i, j)
        hi = np.maximum(i, j)
        keys = lo * self.num_nodes + hi
        pos = np.searchsorted(self._edge_keys, keys)
        pos_c = np.minimum(pos, self._edge_keys.size - 1)
        found = self._edge_keys[pos_c] == keys
        if strict and not bool(np.all(found)):
            raise KeyError("some node pairs are not edges of the grid")
        return np.where(found, pos_c, -1).astype(np.int64)

    @cached_property
    def tet_edge_ids(self) -> IntArray:
        """``(T, 6)`` global edge ids of every tet, in :data:`TET_EDGE_PAIRS` order."""
        tets = self.tets.astype(np.int64)
        cols = [self.edge_ids(tets[:, a], tets[:, b]) for a, b in TET_EDGE_PAIRS]
        out = np.stack(cols, axis=1)
        out.setflags(write=False)
        return out

    @cached_property
    def edge_directions(self) -> dict[tuple[int, int, int], BoolArray]:
        """For every lattice direction ``d`` (from the lower to the higher node id), a
        boolean ``(n+1, n+1, n+1)`` array indexed ``[x, y, z]`` marking the start nodes
        ``p`` for which ``(p, p + d)`` is a grid edge."""
        m = self.n + 1
        c = self.node_coords(self.edges)  # (E, 2, 3)
        d = c[:, 1, :] - c[:, 0, :]
        out: dict[tuple[int, int, int], BoolArray] = {}
        for vec in np.unique(d, axis=0):
            key = (int(vec[0]), int(vec[1]), int(vec[2]))
            sel = np.all(d == vec, axis=1)
            start = c[sel, 0, :]
            arr = np.zeros((m, m, m), dtype=bool)
            arr[start[:, 0], start[:, 1], start[:, 2]] = True
            out[key] = arr
        return out

    # ------------------------------------------------------------------ faces
    @cached_property
    def faces(self) -> IntArray:
        """``(Fc, 3)`` unique tet faces (sorted node triples)."""
        tets = self.tets.astype(np.int64)
        tri = np.concatenate([tets[:, list(t)] for t in TET_FACE_TRIPLES], axis=0)
        tri.sort(axis=1)
        tri = np.unique(tri, axis=0)
        tri.setflags(write=False)
        return tri

    @cached_property
    def face_edge_ids(self) -> IntArray:
        """``(Fc, 3)`` edge ids of the three edges bounding each tet face."""
        f = self.faces
        out = np.stack(
            [
                self.edge_ids(f[:, 0], f[:, 1]),
                self.edge_ids(f[:, 0], f[:, 2]),
                self.edge_ids(f[:, 1], f[:, 2]),
            ],
            axis=1,
        )
        out.setflags(write=False)
        return out

    def edge_lengths(self, edge_ids: npt.ArrayLike | None = None) -> FloatArray:
        e = self.edges if edge_ids is None else self.edges[np.asarray(edge_ids, dtype=np.int64)]
        p = self.node_positions
        return np.asarray(np.linalg.norm(p[e[:, 1]] - p[e[:, 0]], axis=1), dtype=np.float64)

    def describe(self) -> dict[str, object]:
        return {
            "scheme": GRID_SCHEME_NAME,
            "scheme_id": GRID_SCHEME_ID,
            "n": self.n,
            "nodes": self.num_nodes,
            "edges": self.num_edges,
            "tets": self.num_tets,
            "spacing": self.spacing,
            "bounds": [self.lower_bound, self.upper_bound],
        }

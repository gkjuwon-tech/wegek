"""Local problems and answer-free candidate completions.

Block and unknown edges
    A block is ``size^3`` grid cells.  Its *unknown* edges are the grid edges inside the
    closed block that do not lie on the block's boundary faces.  Every tet touching an
    unknown edge lies inside the block, so the rest of A (the context) is untouched.

Why labellings
    For a closed surface, the parity of ``k_e`` equals ``inside(i) xor inside(j)``
    (checked in G1's tests).  The boundary nodes' labels are fixed by the known edges;
    the ``(size-1)^3`` interior nodes are free.  Enumerating their labels therefore
    enumerates *exactly* the parity patterns that satisfy the even-sum condition — no
    candidate can break it.  Thin walls (``k = 2`` on an edge whose ends share a label)
    are added by one explicit rule: continue a double crossing from a parallel
    neighbouring edge outside the block.

Positions
    Every candidate — including the diagnostic "truth" candidate — gets crossing
    positions from the same rule (a signed distance estimate from nearby known crossings),
    so no candidate wins on geometry it was handed.  G2 measures structural choice.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass, field

import numpy as np
import numpy.typing as npt
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import breadth_first_order
from scipy.spatial import cKDTree

from jevsg.grid import TetGrid
from jevsg.representation import EdgeCoordinates

IntArray = npt.NDArray[np.int64]
FloatArray = npt.NDArray[np.float64]


@dataclass(frozen=True)
class Block:
    lo: tuple[int, int, int]  # lattice origin of the block
    size: int  # cells per side
    unknown_edges: IntArray  # sorted edge ids hidden in this block
    interior_nodes: IntArray  # node ids whose label is free
    boundary_nodes: IntArray  # node ids on the block boundary (labels fixed by context)


def make_block(grid: TetGrid, lo: tuple[int, int, int], size: int = 3) -> Block:
    if min(lo) < 0 or max(lo) + size > grid.n:
        raise ValueError("block outside the grid")
    c = grid.node_coords(grid.edges)  # (E, 2, 3)
    lo_a = np.asarray(lo)
    hi_a = lo_a + size
    inside = np.all((c >= lo_a) & (c <= hi_a), axis=(1, 2))
    on_face = np.zeros(inside.shape, dtype=bool)
    for ax in range(3):
        for v in (lo_a[ax], hi_a[ax]):
            on_face |= (c[:, 0, ax] == v) & (c[:, 1, ax] == v)
    unknown = np.nonzero(inside & ~on_face)[0].astype(np.int64)
    rng = [np.arange(lo_a[k], hi_a[k] + 1) for k in range(3)]
    xs, ys, zs = np.meshgrid(*rng, indexing="ij")
    nodes = grid.node_id(xs.ravel(), ys.ravel(), zs.ravel())
    nc = grid.node_coords(nodes)
    interior = np.all((nc > lo_a) & (nc < hi_a), axis=1)
    return Block(lo, size, unknown, np.sort(nodes[interior]), np.sort(nodes[~interior]))


def remove_edges(a: EdgeCoordinates, edges: IntArray) -> EdgeCoordinates:
    keep = ~np.isin(a.edge_ids, edges)
    counts = a.counts[keep]
    s = a.s[np.repeat(keep, a.counts)]
    return EdgeCoordinates(a.n, a.edge_ids[keep], np.concatenate([[0], np.cumsum(counts)]), s)


def restrict(a: EdgeCoordinates, edges: IntArray) -> dict[int, FloatArray]:
    """Crossings of ``a`` on the given edges (only edges with k > 0 appear)."""
    out: dict[int, FloatArray] = {}
    pos = np.searchsorted(a.edge_ids, edges)
    for e, p in zip(edges.tolist(), pos.tolist(), strict=True):
        if p < a.edge_ids.size and a.edge_ids[p] == e:
            out[e] = a.s[a.offsets[p] : a.offsets[p + 1]].copy()
    return out


def merge(known: EdgeCoordinates, fill: dict[int, FloatArray]) -> EdgeCoordinates:
    data = {
        int(e): known.s[known.offsets[i] : known.offsets[i + 1]].tolist()
        for i, e in enumerate(known.edge_ids.tolist())
    }
    for e, s in fill.items():
        if len(s):
            data[int(e)] = sorted(float(x) for x in s)
    return EdgeCoordinates.from_mapping(known.n, data)


def node_labels(known: EdgeCoordinates, grid: TetGrid, hidden: IntArray) -> npt.NDArray[np.int8]:
    """Inside(1)/outside(0) label of every node reachable through known edges.

    Node 0 (a grid corner) is outside.  Nodes reachable only through hidden edges get -1.
    """
    mask = np.ones(grid.num_edges, dtype=bool)
    mask[hidden] = False
    e = grid.edges[mask]
    parity = (known.dense_counts(grid.num_edges)[mask] % 2).astype(np.int8)
    nn = grid.num_nodes
    g = coo_matrix(
        (np.ones(2 * len(e)), (np.r_[e[:, 0], e[:, 1]], np.r_[e[:, 1], e[:, 0]])), shape=(nn, nn)
    ).tocsr()
    order, pred = breadth_first_order(g, 0, directed=False, return_predecessors=True)
    key = e[:, 0] * nn + e[:, 1]
    sorter = np.argsort(key)
    # int64 on purpose: csgraph returns int32 predecessors and ``lo * nn`` overflows
    # int32 from n = 64 on (the bug the first G2 validation run caught).
    v = order[1:].astype(np.int64)
    p = pred[order[1:]].astype(np.int64)
    lo, hi = np.minimum(p, v), np.maximum(p, v)
    idx = sorter[np.searchsorted(key, lo * nn + hi, sorter=sorter)]
    if not np.array_equal(key[idx], lo * nn + hi):
        raise AssertionError("BFS tree edge not found among known edges")
    edge_par = parity[idx]
    labels = np.full(nn, -1, dtype=np.int8)
    labels[0] = 0
    for node, parent, ep in zip(v.tolist(), p.tolist(), edge_par.tolist(), strict=True):
        labels[node] = labels[parent] ^ ep
    return labels


@dataclass
class Candidate:
    key: str  # stable identity of the structure (labels + wall flags)
    labels: tuple[int, ...]  # interior node labels
    walls: bool  # thin-wall continuation applied
    counts: dict[int, int]  # k per unknown edge (only k > 0)
    fill: dict[int, FloatArray] = field(default_factory=dict)  # positions (rule)
    area: int = 0  # number of crossings = surface-size proxy inside the block
    is_truth_structure: bool = False


def _truth_counts(truth: dict[int, FloatArray]) -> dict[int, int]:
    return {e: len(s) for e, s in truth.items() if len(s)}


def _surface_points(
    grid: TetGrid, known: EdgeCoordinates, around: FloatArray, radius: float
) -> FloatArray:
    """Known crossing points (3D) within ``radius`` of ``around``."""
    e = known.hit_edge_ids()
    ij = grid.edges[e]
    p = grid.node_positions
    pts = p[ij[:, 0]] + known.s[:, None] * (p[ij[:, 1]] - p[ij[:, 0]])
    near = np.linalg.norm(pts - around, axis=1) < radius
    return np.asarray(pts[near], dtype=np.float64)


class CandidateFactory:
    """Builds candidates for one block; every candidate gets positions from one rule."""

    def __init__(
        self, grid: TetGrid, block: Block, known: EdgeCoordinates, labels: npt.NDArray[np.int8]
    ) -> None:
        self.grid, self.block, self.known, self.labels = grid, block, known, labels
        ue = block.unknown_edges
        self.ends = grid.edges[ue]
        spacing = grid.spacing
        centre = grid.node_positions[block.interior_nodes].mean(axis=0)
        pts = _surface_points(grid, known, centre, (block.size + 2) * spacing)
        self.dist = np.full(grid.num_nodes, spacing, dtype=np.float64)
        node_ids = np.unique(self.ends.reshape(-1))
        if len(pts):
            d, _ = cKDTree(pts).query(grid.node_positions[node_ids])
            self.dist[node_ids] = np.maximum(d, 1e-6 * spacing)
        self.donors = self._find_donors()

    def _find_donors(self) -> dict[int, FloatArray]:
        """Parallel known neighbour edges carrying a double crossing (thin wall)."""
        grid, ue = self.grid, self.block.unknown_edges
        kd = self.known.dense_counts(grid.num_edges)
        cc = grid.node_coords(self.ends)
        dvec = cc[:, 1] - cc[:, 0]
        unknown = set(ue.tolist())
        donors: dict[int, FloatArray] = {}
        for idx, e in enumerate(ue.tolist()):
            for off in itertools.product((-1, 0, 1), repeat=3):
                if off == (0, 0, 0) or np.all(np.cross(off, dvec[idx]) == 0):
                    continue
                a0 = cc[idx, 0] + off
                a1 = cc[idx, 1] + off
                if min(a0.min(), a1.min()) < 0 or max(a0.max(), a1.max()) > grid.n:
                    continue
                n0, n1 = int(grid.node_id(*a0)), int(grid.node_id(*a1))
                ne = int(grid.edge_ids([n0], [n1], strict=False)[0])
                if ne >= 0 and ne not in unknown and kd[ne] == 2:
                    s = self.known.get(ne)
                    donors[e] = (1.0 - s[::-1]) if n0 > n1 else s
                    break
        return donors

    def _position(self, idx: int, k: int) -> FloatArray:
        i, j = int(self.ends[idx, 0]), int(self.ends[idx, 1])
        if k == 1:
            t = self.dist[i] / (self.dist[i] + self.dist[j])
            return np.array([min(max(t, 0.02), 0.98)])
        e = int(self.block.unknown_edges[idx])
        if k == 2 and e in self.donors:
            return self.donors[e].copy()
        return np.linspace(0.0, 1.0, k + 2)[1:-1]  # evenly spaced, no geometric claim

    def from_counts(
        self, counts: dict[int, int], key: str, labels: tuple[int, ...] = (), walls: bool = False
    ) -> Candidate:
        index = {int(e): i for i, e in enumerate(self.block.unknown_edges.tolist())}
        fill = {e: self._position(index[e], k) for e, k in counts.items() if k > 0}
        return Candidate(key, labels, walls, dict(counts), fill, sum(counts.values()))

    def enumerate(self) -> list[Candidate]:
        """All interior labellings, each with and without thin-wall continuation."""
        ue = self.block.unknown_edges.tolist()
        interior = self.block.interior_nodes
        lab = self.labels.copy()
        out: list[Candidate] = []
        seen: set[tuple[tuple[int, int], ...]] = set()
        for bits in itertools.product((0, 1), repeat=len(interior)):
            lab[interior] = bits
            li, lj = lab[self.ends[:, 0]], lab[self.ends[:, 1]]
            if np.any(li < 0) or np.any(lj < 0):
                raise RuntimeError("unlabelled boundary node next to the block")
            par = (li ^ lj).astype(bool)
            plain = {e: 1 for e, p in zip(ue, par.tolist(), strict=True) if p}
            variants = [(plain, False)]
            walled = dict(plain)
            for e, p in zip(ue, par.tolist(), strict=True):
                if not p and e in self.donors:
                    walled[e] = 2
            if walled != plain:
                variants.append((walled, True))
            for counts, walls in variants:
                sig = tuple(sorted(counts.items()))
                if sig in seen:
                    continue
                seen.add(sig)
                key = "".join(map(str, bits)) + ("w" if walls else "")
                out.append(self.from_counts(counts, key, tuple(int(b) for b in bits), walls))
        return out


def enumerate_candidates(
    grid: TetGrid, block: Block, known: EdgeCoordinates, labels: npt.NDArray[np.int8]
) -> list[Candidate]:
    return CandidateFactory(grid, block, known, labels).enumerate()


def truth_key(cands: list[Candidate], truth_counts: dict[int, int]) -> str | None:
    for c in cands:
        if c.counts == truth_counts:
            return c.key
    return None

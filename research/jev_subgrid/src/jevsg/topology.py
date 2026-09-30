"""Combinatorial topology of triangle meshes: manifoldness, components, genus, orientation.

Everything here is exact (integer / graph computations); no geometric tolerance is used.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import numpy.typing as npt
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components

from jevsg.mesh import TriMesh

IntArray = npt.NDArray[np.int64]


def _components(num_nodes: int, a: IntArray, b: IntArray) -> tuple[int, IntArray]:
    if num_nodes == 0:
        return 0, np.zeros(0, dtype=np.int64)
    g = coo_matrix((np.ones(a.size, dtype=np.int8), (a, b)), shape=(num_nodes, num_nodes))
    n, lab = connected_components(g, directed=False)
    return int(n), lab.astype(np.int64)


@dataclass(frozen=True)
class EdgeTable:
    """Undirected edges of a triangle mesh and their incident faces."""

    edges: IntArray  # (E, 2) sorted vertex pairs
    face_count: IntArray  # (E,) number of incident faces
    he_edge: IntArray  # (3F,) edge id of half-edge (f, k): v[k] -> v[k+1]
    he_forward: npt.NDArray[np.bool_]  # (3F,) half-edge runs from edges[:,0] to edges[:,1]


def edge_table(mesh: TriMesh) -> EdgeTable:
    f = mesh.faces
    src = f.reshape(-1)
    dst = f[:, [1, 2, 0]].reshape(-1)
    lo = np.minimum(src, dst)
    hi = np.maximum(src, dst)
    keys = lo * max(mesh.num_vertices, 1) + hi
    uniq, inv, counts = np.unique(keys, return_inverse=True, return_counts=True)
    nv = max(mesh.num_vertices, 1)
    edges = np.stack([uniq // nv, uniq % nv], axis=1)
    return EdgeTable(edges, counts.astype(np.int64), inv.reshape(-1).astype(np.int64), src < dst)


@dataclass(frozen=True)
class TopologyReport:
    vertices: int
    faces: int
    edges: int
    boundary_edges: int
    nonmanifold_edges: int
    nonmanifold_vertices: int
    collapsed_faces: int
    duplicate_faces: int
    components: int
    component_faces: tuple[int, ...]
    component_euler: tuple[int, ...]
    component_genus: tuple[int | None, ...]  # None for open / non-orientable components
    component_closed: tuple[bool, ...]
    orientable: bool
    consistently_oriented: bool
    boundary_loops: int

    @property
    def closed(self) -> bool:
        return self.boundary_edges == 0

    @property
    def edge_manifold(self) -> bool:
        return self.nonmanifold_edges == 0

    @property
    def watertight_manifold(self) -> bool:
        """Closed, edge- and vertex-manifold, orientable, no collapsed/duplicate faces."""
        return (
            self.faces > 0
            and self.closed
            and self.edge_manifold
            and self.nonmanifold_vertices == 0
            and self.orientable
            and self.collapsed_faces == 0
            and self.duplicate_faces == 0
        )

    @property
    def genus_signature(self) -> tuple[int, ...]:
        """Sorted genus of closed orientable components (-1 marks any other component)."""
        return tuple(sorted((-1 if g is None else g) for g in self.component_genus))

    @property
    def total_genus(self) -> int:
        return int(sum(g for g in self.component_genus if g is not None))

    def as_dict(self) -> dict[str, object]:
        return {
            "vertices": self.vertices,
            "faces": self.faces,
            "edges": self.edges,
            "boundary_edges": self.boundary_edges,
            "nonmanifold_edges": self.nonmanifold_edges,
            "nonmanifold_vertices": self.nonmanifold_vertices,
            "collapsed_faces": self.collapsed_faces,
            "duplicate_faces": self.duplicate_faces,
            "components": self.components,
            "genus_signature": list(self.genus_signature),
            "total_genus": self.total_genus,
            "orientable": self.orientable,
            "consistently_oriented": self.consistently_oriented,
            "boundary_loops": self.boundary_loops,
            "watertight_manifold": self.watertight_manifold,
        }


def face_components(mesh: TriMesh, et: EdgeTable | None = None) -> tuple[int, IntArray]:
    """Components of faces connected through shared edges."""
    et = et or edge_table(mesh)
    nf = mesh.num_faces
    face_of_he = np.repeat(np.arange(nf, dtype=np.int64), 3)
    # Connect every half-edge's face to a representative face of its edge.
    first = np.full(et.edges.shape[0], 3 * nf, dtype=np.int64)
    np.minimum.at(first, et.he_edge, np.arange(3 * nf, dtype=np.int64))
    rep_face = face_of_he[first[et.he_edge]]
    return _components(nf, face_of_he, rep_face)


def orientation_double_cover(
    mesh: TriMesh, et: EdgeTable | None = None
) -> tuple[npt.NDArray[np.bool_], npt.NDArray[np.bool_], int]:
    """Consistent orientation per component via the orientation double cover.

    Returns ``(flip, orientable_per_face, n_inconsistent_edges)``: flipping the faces
    marked ``flip`` makes every orientable component consistently oriented across its
    two-face (manifold) edges.
    """
    et = et or edge_table(mesh)
    nf = mesh.num_faces
    manifold = et.face_count == 2
    he_idx = np.nonzero(manifold[et.he_edge])[0]
    order = np.argsort(et.he_edge[he_idx], kind="stable")
    he_idx = he_idx[order]
    h0, h1 = he_idx[0::2], he_idx[1::2]
    f0, f1 = h0 // 3, h1 // 3
    same_dir = et.he_forward[h0] == et.he_forward[h1]  # same direction = inconsistent
    inconsistent = int(np.count_nonzero(same_dir))
    # Nodes: (face, 0) -> face, (face, 1) -> face + nf.
    a = np.concatenate([f0, f0 + nf])
    b = np.concatenate([np.where(same_dir, f1 + nf, f1), np.where(same_dir, f1, f1 + nf)])
    _, lab = _components(2 * nf, a, b)
    orientable = lab[:nf] != lab[nf:]
    _, fcomp = face_components(mesh, et)
    # Reference face per component: the lowest-index face keeps its orientation.
    ref = np.full(int(fcomp.max()) + 1 if nf else 0, nf, dtype=np.int64)
    np.minimum.at(ref, fcomp, np.arange(nf, dtype=np.int64))
    flip = lab[:nf] != lab[ref[fcomp]]
    return flip, orientable, inconsistent


def orient_consistently(mesh: TriMesh) -> TriMesh:
    flip, _, _ = orientation_double_cover(mesh)
    faces = mesh.faces.copy()
    faces[flip] = faces[flip][:, ::-1]
    return TriMesh(mesh.vertices, faces)


def _nonmanifold_vertices(mesh: TriMesh, et: EdgeTable) -> int:
    """Vertices whose incident faces do not form one edge-connected fan."""
    nf = mesh.num_faces
    if nf == 0:
        return 0
    corners_v = mesh.faces.reshape(-1)  # corner c = 3*f + k
    # For each edge, chain its incident faces; connect the corners at both endpoints.
    he = np.arange(3 * nf, dtype=np.int64)
    order = np.argsort(et.he_edge, kind="stable")
    sorted_he = he[order]
    same = et.he_edge[order][1:] == et.he_edge[order][:-1]
    ha, hb = sorted_he[:-1][same], sorted_he[1:][same]
    fa, fb = ha // 3, hb // 3

    def corner_of(face: IntArray, vert: IntArray) -> IntArray:
        fv = mesh.faces[face]
        k = np.argmax(fv == vert[:, None], axis=1)
        return np.asarray(face * 3 + k, dtype=np.int64)

    e = et.edges[et.he_edge[ha]]
    a = np.concatenate([corner_of(fa, e[:, 0]), corner_of(fa, e[:, 1])])
    b = np.concatenate([corner_of(fb, e[:, 0]), corner_of(fb, e[:, 1])])
    _, lab = _components(3 * nf, a, b)
    pairs = np.unique(corners_v * (3 * nf) + lab)
    fans_per_vertex = np.bincount(pairs // (3 * nf), minlength=mesh.num_vertices)
    return int(np.count_nonzero(fans_per_vertex > 1))


def analyze(mesh: TriMesh) -> TopologyReport:
    nf = mesh.num_faces
    f = mesh.faces
    collapsed = int(
        np.count_nonzero((f[:, 0] == f[:, 1]) | (f[:, 1] == f[:, 2]) | (f[:, 0] == f[:, 2]))
    )
    dup = nf - int(np.unique(np.sort(f, axis=1), axis=0).shape[0]) if nf else 0
    et = edge_table(mesh)
    boundary = int(np.count_nonzero(et.face_count == 1))
    nonman_e = int(np.count_nonzero(et.face_count > 2))
    ncomp, fcomp = face_components(mesh, et)
    _, orientable_face, inconsistent = orientation_double_cover(mesh, et)
    comp_orientable = np.ones(ncomp, dtype=bool)
    np.logical_and.at(comp_orientable, fcomp, orientable_face)

    # Per-component Euler characteristic V - E + F.
    fcount = np.bincount(fcomp, minlength=ncomp)
    edge_face = np.zeros(et.edges.shape[0], dtype=np.int64)
    edge_face[et.he_edge] = np.repeat(np.arange(nf, dtype=np.int64), 3)
    ecomp = fcomp[edge_face]
    ecount = np.bincount(ecomp, minlength=ncomp)
    vcomp_pairs = np.unique(f.reshape(-1) * max(ncomp, 1) + np.repeat(fcomp, 3))
    vcount = np.bincount(vcomp_pairs % max(ncomp, 1), minlength=ncomp)
    euler = vcount - ecount + fcount
    comp_boundary = np.bincount(ecomp[et.face_count == 1], minlength=ncomp)
    comp_nonman = np.bincount(ecomp[et.face_count > 2], minlength=ncomp)
    comp_closed = (comp_boundary == 0) & (comp_nonman == 0)
    genus: list[int | None] = []
    for c in range(ncomp):
        if comp_closed[c] and comp_orientable[c] and (2 - int(euler[c])) % 2 == 0:
            genus.append((2 - int(euler[c])) // 2)
        else:
            genus.append(None)

    # Boundary loops = components of the boundary-edge graph (vertices on the boundary).
    be = et.edges[et.face_count == 1]
    if be.size:
        verts, inv = np.unique(be.reshape(-1), return_inverse=True)
        inv = inv.reshape(-1, 2)
        loops, _ = _components(verts.size, inv[:, 0], inv[:, 1])
    else:
        loops = 0

    return TopologyReport(
        vertices=mesh.num_vertices,
        faces=nf,
        edges=int(et.edges.shape[0]),
        boundary_edges=boundary,
        nonmanifold_edges=nonman_e,
        nonmanifold_vertices=_nonmanifold_vertices(mesh, et),
        collapsed_faces=collapsed,
        duplicate_faces=dup,
        components=ncomp,
        component_faces=tuple(int(x) for x in fcount),
        component_euler=tuple(int(x) for x in euler),
        component_genus=tuple(genus),
        component_closed=tuple(bool(x) for x in comp_closed),
        orientable=bool(np.all(comp_orientable)),
        consistently_oriented=inconsistent == 0,
        boundary_loops=int(loops),
    )

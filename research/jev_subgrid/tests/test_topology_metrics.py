import numpy as np
import pytest

from jevsg.mesh import TriMesh, polygons_to_triangles, weld
from jevsg.metrics import (
    SurfaceDistance,
    compare_surfaces,
    orient_outward,
    point_triangle_sqdist,
    sample_surface,
    winding_number,
)
from jevsg.selfintersect import self_intersections
from jevsg.topology import analyze, orient_consistently
from meshgen import box, concat, icosphere, mobius, torus


def test_genus_and_components() -> None:
    assert analyze(icosphere(1)).genus_signature == (0,)
    t = analyze(torus())
    assert t.genus_signature == (1,) and t.watertight_manifold and t.components == 1
    two = analyze(concat(torus(center=(-2, 0, 0)), icosphere(1, center=(2, 0, 0))))
    assert two.components == 2 and two.genus_signature == (0, 1)


def test_open_nonmanifold_and_nonorientable() -> None:
    b = box((0, 0, 0), (1, 1, 1))
    open_box = analyze(TriMesh(b.vertices, b.faces[2:]))
    assert open_box.boundary_edges == 4 and open_box.boundary_loops == 1
    assert not open_box.watertight_manifold
    # Three faces on one edge -> non-manifold edge.
    fin = TriMesh(np.vstack([b.vertices, [[0.5, -1.0, 0.0]]]), np.vstack([b.faces, [[0, 1, 8]]]))
    assert analyze(fin).nonmanifold_edges == 1
    # Two tetrahedra glued at one vertex -> non-manifold vertex.
    tet = np.array([[0, 2, 1], [0, 1, 3], [1, 2, 3], [0, 3, 2]])
    v = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1.0]])
    bow = TriMesh(np.vstack([v, -v[1:]]), np.vstack([tet, np.where(tet == 0, 0, tet + 3)]))
    assert analyze(bow).nonmanifold_vertices == 1
    m = analyze(mobius())
    assert not m.orientable and m.boundary_loops == 1


def test_orientation_repair_and_outward_orientation() -> None:
    s = icosphere(2)
    rng = np.random.default_rng(0)
    flip = rng.random(s.num_faces) < 0.5
    f = s.faces.copy()
    f[flip] = f[flip][:, ::-1]
    scrambled = TriMesh(s.vertices, f)
    assert not analyze(scrambled).consistently_oriented
    fixed = orient_consistently(scrambled)
    assert analyze(fixed).consistently_oriented
    # Nested spheres: outer faces out, inner faces in -> material volume = difference.
    hollow = concat(icosphere(3, 1.0), icosphere(3, 0.5))
    solid = orient_outward(hollow)
    t = icosphere(3, 1.0).triangles()
    v1 = np.einsum("fi,fi->f", t[:, 0], np.cross(t[:, 1], t[:, 2])).sum() / 6
    assert solid.volume == pytest.approx(v1 * (1 - 0.125), rel=1e-9)
    assert sorted(solid.component_depth) == [0, 1]
    w = winding_number(solid.mesh, np.array([[0, 0, 0], [0.75, 0, 0], [1.5, 0, 0]]))
    assert np.allclose(w, [0, 1, 0], atol=1e-6)


def test_distance_matches_brute_force() -> None:
    m = torus(0.6, 0.2, 40, 16)
    rng = np.random.default_rng(3)
    pts = rng.uniform(-1, 1, (400, 3))
    fast = SurfaceDistance(m)(pts)
    t = m.triangles()
    brute = np.array(
        [
            np.sqrt(
                point_triangle_sqdist(
                    np.repeat(p[None], len(t), 0), t[:, 0], t[:, 1], t[:, 2]
                ).min()
            )
            for p in pts
        ]
    )
    assert np.allclose(fast, brute, atol=1e-12)


def test_point_triangle_regions() -> None:
    a, b, c = np.array([[0.0, 0, 0]]), np.array([[1.0, 0, 0]]), np.array([[0.0, 1, 0]])
    pts = np.array(
        [[0.2, 0.2, 1.0], [-1.0, -1.0, 0.0], [2.0, 0.0, 0.0], [0.5, -1.0, 0.0], [1.0, 1.0, 0.0]]
    )
    d2 = point_triangle_sqdist(pts, *(np.repeat(x, len(pts), 0) for x in (a, b, c)))
    assert np.allclose(d2, [1.0, 2.0, 1.0, 1.0, 0.5])


def test_compare_surfaces_identity_and_offset() -> None:
    s = icosphere(3)
    same = compare_surfaces(s, s, samples=5000)
    assert same.chamfer_l1 < 1e-12 and same.fscore[0.005] == 1.0
    bigger = TriMesh(s.vertices * 1.05, s.faces)
    cmp = compare_surfaces(s, bigger, samples=5000)
    diag = s.bbox_diagonal()
    assert cmp.chamfer_l1 == pytest.approx(0.05 / diag, rel=0.05)
    assert cmp.fscore[0.005] == 0.0


def test_sampling_is_area_uniform() -> None:
    b = box((0, 0, 0), (2, 1, 1))
    pts = sample_surface(b, 60_000, np.random.default_rng(1))
    on_big = (
        np.isclose(pts[:, 1], 0)
        | np.isclose(pts[:, 1], 1)
        | np.isclose(pts[:, 2], 0)
        | np.isclose(pts[:, 2], 1)
    )
    assert on_big.mean() == pytest.approx(8 / 10, abs=0.01)


def test_polygons_to_triangles_and_weld() -> None:
    tris = polygons_to_triangles([0, 4, 7], [0, 1, 2, 3, 4, 5, 6])
    assert tris.tolist() == [[4, 5, 6], [0, 1, 2], [0, 2, 3]] or tris.tolist() == [
        [0, 1, 2],
        [0, 2, 3],
        [4, 5, 6],
    ]
    b = box((0, 0, 0), (1, 1, 1))
    soup = TriMesh(b.vertices[b.faces.reshape(-1)], np.arange(3 * b.num_faces).reshape(-1, 3))
    assert analyze(weld(soup)).watertight_manifold


def test_self_intersection_detection() -> None:
    assert self_intersections(torus()).clean
    # Two crossing triangles.
    v = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0], [0.2, 0.2, -1], [0.3, 0.2, 1], [0.2, 0.3, 1.0]])
    rep = self_intersections(TriMesh(v, np.array([[0, 1, 2], [3, 4, 5]])))
    assert rep.intersecting_pairs == 1 and rep.by_kind == {"disjoint": 1}
    # Touching at a point that is not a shared vertex counts, a near miss does not.
    touch = np.array(
        [[0, 0, 0], [1, 0, 0], [0, 1, 0], [0.25, 0.25, 0], [0.3, 0.3, 1], [0.2, 0.4, 1.0]]
    )
    assert (
        self_intersections(TriMesh(touch, np.array([[0, 1, 2], [3, 4, 5]]))).intersecting_pairs == 1
    )
    miss = touch.copy()
    miss[3, 2] = np.nextafter(0.0, 1.0)
    assert (
        self_intersections(TriMesh(miss, np.array([[0, 1, 2], [3, 4, 5]]))).intersecting_pairs == 0
    )
    # Coplanar fold over a shared edge.
    fold = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0], [0.2, 0.5, 0.0]])
    assert self_intersections(TriMesh(fold, np.array([[0, 1, 2], [1, 0, 3]]))).by_kind == {
        "shared_edge_fold": 1
    }
    # Coplanar overlapping disjoint triangles.
    cop = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0], [0.1, 0.1, 0], [0.3, 0.1, 0], [0.1, 0.3, 0.0]])
    assert (
        self_intersections(TriMesh(cop, np.array([[0, 1, 2], [3, 4, 5]]))).intersecting_pairs == 1
    )
    # Shared vertex, second triangle pokes through the first.
    sv = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0], [0.5, 0.5, -1], [0.5, 0.5, 1.0]])
    assert self_intersections(TriMesh(sv, np.array([[0, 1, 2], [0, 3, 4]]))).by_kind == {
        "shared_vertex": 1
    }

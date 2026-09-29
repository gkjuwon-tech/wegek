import numpy as np
import pytest

from jevsg.encode import encode_mesh
from jevsg.grid import TetGrid
from jevsg.metrics import winding_number
from jevsg.representation import odd_faces, validate
from meshgen import box, concat, icosphere, torus


def _parity_matches_occupancy(mesh, grid, a) -> None:  # type: ignore[no-untyped-def]
    """For a closed mesh, k_e mod 2 must equal inside(i) xor inside(j) for every edge."""
    k = a.dense_counts(grid.num_edges)
    inside = np.abs(winding_number(mesh, grid.node_positions)) > 0.5
    e = grid.edges
    expect = inside[e[:, 0]] ^ inside[e[:, 1]]
    assert np.array_equal(k % 2 == 1, expect)


@pytest.mark.parametrize("n", [5, 8, 13])
def test_sphere_crossings_follow_occupancy(n: int) -> None:
    mesh = icosphere(2, radius=0.71, center=(0.013, -0.021, 0.007))
    g = TetGrid(n)
    a, st = encode_mesh(mesh, g)
    assert validate(a, g) == []
    assert odd_faces(a, g) == 0
    _parity_matches_occupancy(mesh, g, a)
    assert st.crossings == a.num_crossings > 0


def test_torus_and_self_intersecting_union_are_even() -> None:
    g = TetGrid(9)
    t = torus(0.55, 0.18, center=(0.02, 0.01, -0.03))
    a, _ = encode_mesh(t, g)
    assert odd_faces(a, g) == 0
    _parity_matches_occupancy(t, g, a)
    # Two overlapping closed spheres stored as one soup: closed in the mod-2 sense.
    soup = concat(icosphere(2, 0.45, (-0.2, 0.0, 0.0)), icosphere(2, 0.45, (0.25, 0.05, 0.0)))
    a2, _ = encode_mesh(soup, g)
    assert odd_faces(a2, g) == 0
    assert a2.max_k >= 2


def test_thin_wall_produces_double_crossings() -> None:
    # Two parallel planes 0.01 apart (a thin slab) inside a single grid cell.
    g = TetGrid(8)
    slab = box((-0.6, -0.6, 0.101), (0.6, 0.6, 0.111))
    a, _ = encode_mesh(slab, g)
    assert odd_faces(a, g) == 0
    assert 2 in a.k_histogram()  # vertical edges see both faces of the wall
    s = np.concatenate([a.get(int(e)) for e in a.edge_ids[a.counts == 2]])
    assert np.all(np.diff(s.reshape(-1, 2), axis=1) > 0)


def test_exact_degeneracies_are_resolved_consistently() -> None:
    # A box whose faces lie exactly on grid planes and whose corners are grid nodes:
    # every crossing is degenerate and must be resolved by the symbolic perturbation.
    g = TetGrid(9)
    x = g.axis_positions
    cube = box((x[2], x[2], x[3]), (x[6], x[5], x[7]))
    a, st = encode_mesh(cube, g)
    assert st.predicates.sos_resolved > 0
    assert validate(a, g) == []
    assert odd_faces(a, g) == 0
    assert st.t_clamped > 0  # crossings exactly at nodes sit just inside the edge


def test_rejects_mesh_outside_grid() -> None:
    with pytest.raises(ValueError):
        encode_mesh(icosphere(1, radius=1.5), TetGrid(4))


def test_open_surface_is_reported_through_odd_faces() -> None:
    g = TetGrid(6)
    tri = box((-0.5, -0.5, 0.05), (0.5, 0.5, 0.3))
    open_mesh = type(tri)(tri.vertices, tri.faces[2:])  # drop the bottom: open surface
    a, _ = encode_mesh(open_mesh, g)
    assert odd_faces(a, g) > 0

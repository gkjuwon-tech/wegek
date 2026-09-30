import numpy as np
import pytest

from jevsg.grid import TET_FACE_TRIPLES, TetGrid


@pytest.mark.parametrize("n", [2, 3, 5, 8])
def test_counts_and_positions(n: int) -> None:
    g = TetGrid(n)
    assert g.tets.shape == (5 * n**3, 4)
    assert g.node_positions.shape == ((n + 1) ** 3, 3)
    # Reference convention: nodes 0 .. n-1 span [-1, 1] exactly, node n sits past +1.
    assert g.axis_positions[0] == -1.0
    assert g.axis_positions[n - 1] == pytest.approx(1.0, abs=1e-15)
    assert g.axis_positions[n] > 1.0
    assert np.array_equal(
        g.node_positions[g.node_id(2 % (n + 1), 0, 1)],
        np.array([(2 % (n + 1)) * g.dx - 0.5, -0.5, g.dx - 0.5]) * 2.0,
    )


@pytest.mark.parametrize("n", [3, 4, 7])
def test_grid_is_a_conforming_tiling(n: int) -> None:
    g = TetGrid(n)
    p = g.node_positions[g.tets.astype(np.int64)]
    vol = (
        np.einsum("ij,ij->i", p[:, 1] - p[:, 0], np.cross(p[:, 2] - p[:, 0], p[:, 3] - p[:, 0])) / 6
    )
    assert np.all(np.abs(vol) > 0)
    side = g.upper_bound - g.lower_bound
    assert np.abs(vol).sum() == pytest.approx(side**3, rel=1e-12)
    # Every face is shared by exactly two tets, except faces on the outer boundary.
    tri = np.concatenate([g.tets[:, list(t)] for t in TET_FACE_TRIPLES]).astype(np.int64)
    tri.sort(axis=1)
    _, counts = np.unique(tri, axis=0, return_counts=True)
    assert set(np.unique(counts)) <= {1, 2}
    boundary_faces = 6 * 2 * n * n  # two triangles per boundary square
    assert int(np.sum(counts == 1)) == boundary_faces


def test_edge_ids_are_global_and_canonical() -> None:
    g = TetGrid(4)
    e = g.edges
    assert np.all(e[:, 0] < e[:, 1])
    assert np.all(np.diff(e[:, 0] * g.num_nodes + e[:, 1]) > 0)
    ids = g.edge_ids(e[:, 1], e[:, 0])  # reversed pairs map to the same id
    assert np.array_equal(ids, np.arange(g.num_edges))
    assert g.edge_ids([0], [g.num_nodes - 1], strict=False)[0] == -1
    with pytest.raises(KeyError):
        g.edge_ids([0], [g.num_nodes - 1])
    # tet_edge_ids agree with the tets.
    t = g.tets.astype(np.int64)
    assert np.array_equal(g.edges[g.tet_edge_ids[:, 0]], np.sort(t[:, [0, 1]], axis=1))


def test_edge_directions_cover_all_edges() -> None:
    g = TetGrid(5)
    total = sum(int(v.sum()) for v in g.edge_directions.values())
    assert total == g.num_edges
    for d, exists in g.edge_directions.items():
        start = np.argwhere(exists)
        i = g.node_id(start[:, 0], start[:, 1], start[:, 2])
        j = g.node_id(start[:, 0] + d[0], start[:, 1] + d[1], start[:, 2] + d[2])
        assert np.all(i < j)
        assert np.all(g.edge_ids(i, j) >= 0)


def test_rejects_bad_resolution() -> None:
    with pytest.raises(ValueError):
        TetGrid(1)

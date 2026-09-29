import numpy as np
import pytest

from jevsg.grid import TetGrid
from jevsg.representation import (
    EdgeCoordinates,
    cap_crossings,
    flip_positions,
    from_bytes,
    odd_faces,
    quantize,
    size_report,
    to_bytes,
    validate,
)


def _example(n: int = 4) -> EdgeCoordinates:
    return EdgeCoordinates.from_mapping(
        n, {3: [0.40, 0.43], 10: [0.5], 11: [0.1, 0.2, 0.3, 0.9], 250: [0.999999]}
    )


def test_basic_accessors() -> None:
    a = _example()
    assert a.num_active_edges == 4
    assert a.num_crossings == 8
    assert a.max_k == 4
    assert a.k_histogram() == {1: 2, 2: 1, 4: 1}
    assert np.allclose(a.get(3), [0.40, 0.43])
    assert a.get(4).size == 0
    assert list(a.hit_edge_ids()) == [3, 3, 10, 11, 11, 11, 11, 250]
    assert list(a.local_index()) == [0, 1, 0, 0, 1, 2, 3, 0]
    assert validate(a, TetGrid(4)) == []


def test_validate_catches_violations() -> None:
    bad = EdgeCoordinates(4, np.array([5, 5]), np.array([0, 1, 2]), np.array([0.5, 0.5]))
    assert any("strictly increasing" in p for p in validate(bad))
    bad = EdgeCoordinates(4, np.array([1]), np.array([0, 2]), np.array([0.6, 0.5]))
    assert any("within an edge" in p for p in validate(bad))
    bad = EdgeCoordinates(4, np.array([1]), np.array([0, 1]), np.array([1.0]))
    assert any("open interval" in p for p in validate(bad))


def test_flip_positions() -> None:
    assert np.allclose(flip_positions([0.1, 0.4]), [0.6, 0.9])


@pytest.mark.parametrize("bits", [None, 3, 8, 16])
def test_serialization_roundtrip_is_exact(bits: int | None) -> None:
    rng = np.random.default_rng(0)
    ids = np.unique(rng.integers(0, 10**7, 3000))
    data = {int(e): sorted(rng.uniform(0.01, 0.99, int(rng.integers(1, 5))).tolist()) for e in ids}
    a = EdgeCoordinates.from_mapping(64, data)
    a = quantize(a, bits)[0] if bits else a
    buf = to_bytes(a, bits)
    b, got_bits = from_bytes(buf)
    assert got_bits == bits
    assert b.equals(a)
    rep = size_report(a, bits)
    assert rep.raw_bytes == len(buf)
    assert rep.header_bytes + rep.edge_bytes + rep.position_bytes == rep.raw_bytes


def test_serialization_rejects_garbage() -> None:
    buf = to_bytes(_example())
    with pytest.raises(ValueError):
        from_bytes(b"XXXX" + buf[4:])
    with pytest.raises(ValueError):
        from_bytes(buf + b"\x00")


def test_quantize_keeps_counts_and_strict_order() -> None:
    a = EdgeCoordinates.from_mapping(8, {1: [0.40, 0.401, 0.402], 2: [0.97, 0.98, 0.99], 3: [0.5]})
    q, st = quantize(a, 3)  # 8 bins: the three close crossings share a bin
    assert np.array_equal(q.counts, a.counts)
    assert validate(q) == []
    assert st.bumped >= 2
    assert np.allclose(q.get(1), [3.5 / 8, 4.5 / 8, 5.5 / 8])
    assert np.allclose(q.get(2), [5.5 / 8, 6.5 / 8, 7.5 / 8])  # pulled back from the end
    with pytest.raises(ValueError):
        quantize(EdgeCoordinates.from_mapping(8, {1: [0.1, 0.2, 0.3]}), 1)  # 3 > 2 bins


def test_cap_preserves_parity_and_drops_thinnest_pair() -> None:
    a = EdgeCoordinates.from_mapping(8, {1: [0.1, 0.5, 0.52, 0.9], 2: [0.2, 0.3, 0.6], 3: [0.4]})
    c, st = cap_crossings(a, 2)
    assert np.allclose(c.get(1), [0.1, 0.9])  # the 0.5/0.52 wall is the one that goes
    assert np.allclose(c.get(2), [0.6])  # 3 -> 1 keeps parity
    assert np.allclose(c.get(3), [0.4])
    assert st.crossings_dropped == 4 and st.edges_over_cap == 2
    k1, _ = cap_crossings(a, 1)
    assert set(k1.edge_ids.tolist()) == {2, 3}  # even counts vanish entirely at K = 1
    assert np.all(k1.counts % 2 == 1)


def test_odd_faces_counts_parity_violations() -> None:
    g = TetGrid(3)
    assert odd_faces(EdgeCoordinates.empty(3), g) == 0
    one = EdgeCoordinates.from_mapping(3, {0: [0.5]})
    faces_with_edge0 = int(np.any(g.face_edge_ids == 0, axis=1).sum())
    assert odd_faces(one, g) == faces_with_edge0
    two = EdgeCoordinates.from_mapping(3, {0: [0.4, 0.6]})
    assert odd_faces(two, g) == 0

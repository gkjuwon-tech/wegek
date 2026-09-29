from fractions import Fraction

import numpy as np

from jevsg.predicates import (
    PredicateStats,
    line_side,
    orient2d,
    orient2d_scalar,
    orient3d,
    plane_side,
)


def _exact3(a, b, c, d) -> int:  # type: ignore[no-untyped-def]
    m = [[Fraction(float(x[k])) - Fraction(float(d[k])) for k in range(3)] for x in (a, b, c)]
    det = (
        m[0][0] * (m[1][1] * m[2][2] - m[1][2] * m[2][1])
        - m[0][1] * (m[1][0] * m[2][2] - m[1][2] * m[2][0])
        + m[0][2] * (m[1][0] * m[2][1] - m[1][1] * m[2][0])
    )
    return (det > 0) - (det < 0)


def test_orient3d_matches_rational_arithmetic_near_degeneracy() -> None:
    rng = np.random.default_rng(1)
    n = 3000
    a, b, c = rng.random((3, n, 3))
    t = rng.random((n, 2))
    d = a + t[:, :1] * (b - a) + t[:, 1:] * (c - a)
    d = d + rng.integers(-3, 4, (n, 3)) * np.spacing(d)
    stats = PredicateStats()
    _, s = orient3d(a, b, c, d, stats)
    expect = np.array([_exact3(a[i], b[i], c[i], d[i]) for i in range(n)])
    assert np.array_equal(s, expect)
    assert stats.exact_fallbacks > 0  # the test really exercised the slow path


def test_orient3d_exact_zero_on_exactly_coplanar_points() -> None:
    a = np.array([[0.0, 0.0, 0.0], [0.1, 0.7, 0.3]])
    b = np.array([[1.0, 0.0, 0.0], [0.1, 0.2, 0.9]])
    c = np.array([[0.0, 1.0, 0.0], [0.1, 0.5, 0.5]])
    d = np.array([[0.3, 0.3, 0.0], [0.1, 0.25, 0.125]])  # second row: all share x = 0.1
    _, s = orient3d(a, b, c, d)
    assert np.array_equal(s, [0, 0])
    # 3 * 0.1 is not 0.3 in floats: a genuinely non-coplanar configuration is detected.
    _, s2 = orient3d([0.0, 0.0, 0.0], [0.1, 0.1, 0.1], [0.2, 0.2, 0.3], [0.3, 0.3, 0.3])
    assert int(s2) == _exact3(
        *np.array([[0.0, 0.0, 0.0], [0.1, 0.1, 0.1], [0.2, 0.2, 0.3], [0.3, 0.3, 0.3]])
    )


def test_orient2d_vector_and_scalar_agree() -> None:
    rng = np.random.default_rng(2)
    p, q = rng.random((2, 2000, 2))
    r = p + rng.random((2000, 1)) * (q - p)
    r = r + rng.integers(-1, 2, (2000, 2)) * np.spacing(r)
    _, s = orient2d(p, q, r)
    s2 = np.array([orient2d_scalar(tuple(p[i]), tuple(q[i]), tuple(r[i])) for i in range(2000)])
    assert np.array_equal(s, s2)
    assert orient2d_scalar((0.0, 0.0), (1.0, 1.0), (0.5, 0.5)) == 0


def test_plane_side_perturbation_is_consistent() -> None:
    # A point exactly on the plane z = 0 of a CCW triangle (normal +z): the perturbation
    # delta = (e, e^2, e^3) resolves by the first non-zero normal component -> +1.
    a, b, c = np.array([0.0, 0, 0]), np.array([1.0, 0, 0]), np.array([0.0, 1, 0])
    stats = PredicateStats()
    _, s = plane_side(
        a, b, c, np.array([[0.2, 0.2, 0.0], [5.0, 5.0, 0.0], [0.2, 0.2, 1e-300]]), stats
    )
    assert list(s) == [1, 1, 1]
    assert stats.sos_resolved == 2
    # Flipping the triangle flips every sign, including resolved ties.
    _, s = plane_side(a, c, b, np.array([[0.2, 0.2, 0.0]]))
    assert list(s) == [-1]
    # Degenerate triangle -> 0.
    _, s = plane_side(a, b, 2 * b, np.array([[0.2, 0.2, 0.5]]))
    assert list(s) == [0]


def test_line_side_antisymmetric_and_resolves_ties() -> None:
    p, q = np.array([0.0, 0.0, -1.0]), np.array([0.0, 0.0, 1.0])
    x, y = np.array([-1.0, 0.0, 0.0]), np.array([1.0, 0.0, 0.0])  # line passes through xy
    s_xy = line_side(p, q, x, y)
    s_yx = line_side(p, q, y, x)
    assert int(s_xy) != 0 and int(s_xy) == -int(s_yx)

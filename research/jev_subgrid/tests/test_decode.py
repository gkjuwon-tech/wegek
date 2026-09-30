import numpy as np

from jevsg.decode import (
    RECONSTRUCTOR_VERSION,
    compare_with_reference_pipeline,
    decode_primal,
    reconstructor_version,
    reference_pipeline,
)
from jevsg.encode import encode_mesh
from jevsg.grid import TetGrid
from jevsg.representation import EdgeCoordinates, quantize
from jevsg.selfintersect import self_intersections
from jevsg.topology import analyze
from meshgen import icosphere, torus


def test_reconstructor_is_pinned() -> None:
    assert reconstructor_version() == RECONSTRUCTOR_VERSION


def test_compacted_input_equals_full_grid_input() -> None:
    g = TetGrid(10)
    a, _ = encode_mesh(torus(0.5, 0.2, center=(0.01, 0.02, 0.03)), g)
    compact = decode_primal(a, g)
    full = decode_primal(a, g, full_grid=True)
    assert np.array_equal(compact.mesh.faces, full.mesh.faces)
    assert np.array_equal(compact.mesh.vertices, full.mesh.vertices)
    assert compact.active_tets_written < full.active_tets_written


def test_encoder_matches_the_reference_pipeline() -> None:
    """Our exact A through the explicit-input path == the authors' own mesh pipeline."""
    for n in (8, 16):
        g = TetGrid(n)
        mesh = torus(0.55, 0.22, center=(0.031, -0.017, 0.009))
        a, _ = encode_mesh(mesh, g)
        ours = decode_primal(a, g)
        theirs = reference_pipeline(mesh, g)
        cmp = compare_with_reference_pipeline(ours.mesh, theirs.mesh)
        assert cmp["xcheck_same_connectivity"]
        assert 0 <= float(cmp["xcheck_max_vertex_diff"]) < 1e-5  # their BVH is float32


def test_roundtrip_is_closed_and_intersection_free() -> None:
    g = TetGrid(12)
    mesh = torus(0.55, 0.2, center=(0.01, 0.0, 0.02))
    a, _ = encode_mesh(mesh, g)
    for av in (a, quantize(a, 6)[0]):
        r = decode_primal(av, g)
        assert r.non_even_tets == 0
        topo = analyze(r.mesh)
        assert topo.watertight_manifold
        assert topo.genus_signature == (1,)
        assert self_intersections(r.mesh).clean


def test_empty_representation_decodes_to_empty_mesh() -> None:
    r = decode_primal(EdgeCoordinates.empty(6), TetGrid(6))
    assert r.mesh.num_faces == 0


def test_sphere_volume_converges() -> None:
    mesh = icosphere(3, 0.7, (0.01, 0.02, 0.0))
    errs = []
    for n in (8, 16, 32):
        g = TetGrid(n)
        a, _ = encode_mesh(mesh, g)
        m = decode_primal(a, g).mesh
        t = m.triangles()
        vol = abs(np.einsum("fi,fi->f", t[:, 0], np.cross(t[:, 1], t[:, 2])).sum() / 6)
        t0 = mesh.triangles()
        ref = abs(np.einsum("fi,fi->f", t0[:, 0], np.cross(t0[:, 1], t0[:, 2])).sum() / 6)
        errs.append(abs(vol - ref) / ref)
    assert errs[0] > errs[1] > errs[2]

import io
import json
import urllib.error
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from jevsg.encode import encode_mesh
from jevsg.g2 import jev as jevmod
from jevsg.g2.choosers import grade, jev_choose, random_expected, rule_min_area, rule_simplest
from jevsg.g2.describe import LEVELS, option_text, state_for
from jevsg.g2.local import CandidateFactory, make_block, merge, node_labels, remove_edges, restrict
from jevsg.grid import TetGrid
from jevsg.metrics import winding_number
from jevsg.representation import odd_faces
from meshgen import icosphere, torus


def _setup(n: int = 14) -> tuple[TetGrid, Any, Any]:
    g = TetGrid(n)
    mesh = torus(0.55, 0.2, center=(0.013, -0.021, 0.017))
    a, _ = encode_mesh(mesh, g)
    return g, mesh, a


def test_labels_match_winding_numbers_at_real_resolution() -> None:
    # n = 64 catches the int32 overflow that n = 12 did not.
    g = TetGrid(64)
    mesh = icosphere(2, 0.6, (0.011, 0.023, -0.017))
    a, _ = encode_mesh(mesh, g)
    lab = node_labels(a, g, np.zeros(0, dtype=np.int64))
    e = g.edges
    k = a.dense_counts(g.num_edges)
    assert np.array_equal(k % 2, lab[e[:, 0]] ^ lab[e[:, 1]])
    sample = np.arange(0, g.num_nodes, 97)
    inside = np.abs(winding_number(mesh, g.node_positions[sample])) > 0.5
    assert np.array_equal(lab[sample].astype(bool), inside)


def test_every_candidate_is_even_sum_and_truth_is_enumerated() -> None:
    g, _, a = _setup()
    # A block straddling the tube.
    u = ((np.array([0.55, 0.0, 0.0]) + 1.0) * (g.n - 1) / 2).astype(int) - 1
    block = make_block(g, tuple(int(x) for x in u), 3)
    known = remove_edges(a, block.unknown_edges)
    truth = restrict(a, block.unknown_edges)
    fac = CandidateFactory(g, block, known, node_labels(known, g, block.unknown_edges))
    cands = fac.enumerate()
    assert len(cands) >= 2 ** len(block.interior_nodes)
    assert all(odd_faces(merge(known, c.fill), g) == 0 for c in cands)
    tc = {e: len(s) for e, s in truth.items()}
    assert any(c.counts == tc for c in cands)
    assert all(0 < x < 1 for c in cands for s in c.fill.values() for x in s)


def _toy_problem() -> dict[str, Any]:
    def cand(
        key: str, area: int, core: bool, err: float, pieces: int, holes: int, bubbles: int
    ) -> dict[str, Any]:
        return {
            "key": key,
            "area": area,
            "walls": False,
            "labels": [0, 1, 0, 0, 0, 0, 0, 1],
            "k_per_edge": [1, 0, 2, 1][: 3 + (area % 2)],
            "effects": {
                "object_pieces": pieces,
                "object_holes": holes,
                "object_closed": True,
                "bubbles_in_block": bubbles,
                "surface_pieces_in_block": 1,
                "surface_faces_in_block": 10,
            },
            "oracle": {"core_success": core, "local_err": err},
        }

    cands = {
        "a": cand("a", 20, False, 0.09, 1, 2, 0),
        "b": cand("b", 30, True, 0.03, 1, 1, 0),
        "c": cand("c", 25, False, 0.08, 2, 1, 1),
        "truth": cand("truth", 31, True, 0.02, 1, 1, 0),
    }
    return {
        "problem_id": "toy#b0",
        "shape_id": "toy",
        "family": "cup",
        "stratum": "hard",
        "condition": "A drinking mug with a single handle.",
        "truth_key": "truth",
        "truth_in_real": False,
        "boundary_faces": {
            k: {"crossings": 3, "double": 0} for k in ("-x", "+x", "-y", "+y", "-z", "+z")
        },
        "real_set": ["a", "b", "c"],
        "diag_set": ["a", "b", "truth"],
        "candidates": cands,
    }


def test_option_descriptions_have_identical_fields() -> None:
    p = _toy_problem()
    for level in LEVELS:
        fields = {tuple(sorted(option_text(p, k, level))) for k in p["candidates"]}
        assert len(fields) == 1, (level, fields)
        assert "object_description" in state_for(p, level)
    bad = json.loads(json.dumps(p))
    bad["candidates"]["truth"]["labels"] = []
    with pytest.raises(ValueError):
        option_text(bad, "truth", "L1")


def test_rules_and_grading() -> None:
    p = _toy_problem()
    keys = p["real_set"]
    assert rule_min_area(p, keys) == "a"
    assert rule_simplest(p, keys) == "b"  # no bubble, fewest pieces + holes
    g = grade(p, keys, "a")
    assert g["core"] is False and g["best_core_available"] is True and g["optimal"] is False
    assert grade(p, keys, "b")["optimal"] is True
    r = random_expected(p, keys)
    assert r["core"] == pytest.approx(1 / 3)


class _Resp(io.BytesIO):
    def __enter__(self) -> "_Resp":
        return self

    def __exit__(self, *a: object) -> None:
        return None


def test_jev_client_caches_counts_cost_and_never_stores_the_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("JEV_API_KEY", "secret-key-123")
    calls: list[Any] = []

    def fake_urlopen(req: Any, timeout: float = 0) -> _Resp:
        calls.append(req)
        assert req.headers["Authorization"] == "Bearer secret-key-123"
        body = json.loads(req.data)
        if len(calls) == 1:  # first attempt is rate limited
            raise urllib.error.HTTPError(
                req.full_url, 429, "busy", {"retry-after": "0"}, io.BytesIO(b"{}")
            )  # type: ignore[arg-type]
        answers = {}
        for qid, q in body["questions"].items():
            opts = list(q["criteria"])
            answers[qid] = {
                "type": "choice",
                "choice": opts[-1],
                "confidence": 0.9,
                "probabilities": {o: (1.0 if o == opts[-1] else 0.0) for o in opts},
            }
        return _Resp(
            json.dumps(
                {
                    "model": "jev-1.13.0",
                    "answers": answers,
                    "usage": {"input_tokens": 1000, "output_tokens": 50},
                }
            ).encode()
        )

    monkeypatch.setattr(jevmod.urllib.request, "urlopen", fake_urlopen)
    client = jevmod.JevClient(tmp_path)
    p = _toy_problem()
    out = jev_choose(client, p, "L2")
    assert set(out) >= {"real_p0", "real_p1", "diag_p0", "diag_p1"}
    assert all(out[q]["chosen"] in p["candidates"] for q in ("real_p0", "diag_p1"))
    assert client.usage.requests == 1 and client.usage.retries == 1
    assert client.usage.usd == pytest.approx(1000 * 0.042 / 1e6)
    jev_choose(client, p, "L2")  # identical request -> cache
    assert client.usage.cache_hits == 1 and len(calls) == 2
    for f in tmp_path.rglob("*.json"):
        assert "secret-key-123" not in f.read_text()

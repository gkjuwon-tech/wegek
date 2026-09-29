"""Build the G2 local-problem set: blocks, answer-free candidate sets, oracle grades.

Per shape we sample blocks where the surface passes, enumerate all candidates, decode the
``pool`` smallest ones (fewest crossings) and keep, for every distinct *effect signature*
(object pieces, object holes, closed bubbles — computed from each candidate's own
reconstruction), its smallest representative.  Up to ``options`` of those form the
real candidate set shown to every chooser.  The diagnostic set is the real set with the
true structure forced in (replacing the last option) when it is missing.  Every
candidate in either set is graded by the oracle; the grades never reach a chooser.
"""

from __future__ import annotations

import json
import tempfile
from dataclasses import asdict
from pathlib import Path
from typing import Any

import numpy as np

from jevsg.g2.conditions import condition_text
from jevsg.g2.local import (
    Candidate,
    CandidateFactory,
    make_block,
    node_labels,
    remove_edges,
    restrict,
)
from jevsg.g2.oracle import ShapeContext, build_shape_context, score
from jevsg.metrics import sample_surface


def _signature(eff: dict[str, object]) -> tuple[object, ...]:
    return (
        eff["object_pieces"],
        eff["object_holes"],
        eff["bubbles_in_block"],
        eff["object_closed"],
    )


def _cand_record(c: Candidate, outcome: Any, block_edges: list[int]) -> dict[str, Any]:
    return {
        "key": c.key,
        "area": c.area,
        "walls": c.walls,
        "labels": list(c.labels),
        "k_per_edge": [int(c.counts.get(e, 0)) for e in block_edges],
        "effects": outcome.effects,
        "oracle": {k: v for k, v in asdict(outcome).items() if k not in ("effects",)},
    }


def sample_blocks(
    ctx: ShapeContext, count: int, rng: np.random.Generator, size: int = 3
) -> list[tuple[int, int, int]]:
    g = ctx.grid
    pts = sample_surface(ctx.ref.mesh, 40 * count, rng)
    u = (pts + 1.0) * (g.n - 1) / 2.0
    chosen: list[tuple[int, int, int]] = []
    for p in u:
        lo = tuple(int(x) for x in np.floor(p).astype(int) - 1)
        if min(lo) < 0 or max(lo) + size > g.n:
            continue
        if any(max(abs(a - b) for a, b in zip(lo, c, strict=True)) < size for c in chosen):
            continue  # no overlapping blocks within one shape
        chosen.append(lo)  # type: ignore[arg-type]
        if len(chosen) == count:
            break
    return chosen


def build_problems(
    shape_id: str, cache_dir: str, count: int = 10, pool: int = 32, options: int = 8, seed: int = 0
) -> list[dict[str, Any]]:
    ctx = build_shape_context(shape_id, cache_dir)
    g, truth_a = ctx.grid, ctx.truth
    rng = np.random.default_rng(seed + sum(map(ord, shape_id)))
    workdir = tempfile.mkdtemp(prefix="jevsg_g2_")
    problems = []
    for bi, lo in enumerate(sample_blocks(ctx, count, rng)):
        block = make_block(g, lo, 3)
        edges = block.unknown_edges.tolist()
        known = remove_edges(truth_a, block.unknown_edges)
        truth = restrict(truth_a, block.unknown_edges)
        truth_counts = {e: len(s) for e, s in truth.items() if len(s)}
        fac = CandidateFactory(g, block, known, node_labels(known, g, block.unknown_edges))
        cands = sorted(fac.enumerate(), key=lambda c: (c.area, c.key))
        # Pool: the smallest half by crossings plus an even spread over the rest, so larger
        # structural changes (extra holes, bubbles, merged sheets) are represented too.
        head = cands[: pool // 2]
        rest = cands[pool // 2 :]
        spread = [
            rest[i]
            for i in np.linspace(0, len(rest) - 1, min(pool - len(head), len(rest))).astype(int)
        ]
        pooled = list({c.key: c for c in head + spread}.values())
        graded: list[tuple[Candidate, Any]] = [
            (c, score(ctx, block, known, c, workdir)) for c in pooled
        ]
        # Options: smallest representative per effect signature, then second ones, until full.
        by_sig: dict[tuple[object, ...], list[tuple[Candidate, Any]]] = {}
        for c, o in graded:
            by_sig.setdefault(_signature(o.effects), []).append((c, o))
        real: list[tuple[Candidate, Any]] = []
        for rank in range(max(len(v) for v in by_sig.values())):
            for group in by_sig.values():
                if rank < len(group) and len(real) < options and (rank == 0 or rank < 2):
                    real.append(group[rank])
        truth_in_pool = next(((c, o) for c, o in graded if c.counts == truth_counts), None)
        truth_in_real = any(c.counts == truth_counts for c, _ in real)
        diag = list(real)
        if not truth_in_real:
            # The true structure gets its true inside/outside labels, so its description has
            # exactly the same fields as every other option (no tell-tale missing field).
            true_labels = node_labels(truth_a, g, np.zeros(0, dtype=np.int64))[block.interior_nodes]
            tcand = fac.from_counts(
                truth_counts,
                "truth",
                tuple(int(x) for x in true_labels),
                walls=any(v >= 2 for v in truth_counts.values()),
            )
            tc = truth_in_pool or (tcand, score(ctx, block, known, tcand, workdir))
            if len(diag) >= options:
                diag[-1] = tc
            else:
                diag.append(tc)
        # Boundary context for the descriptions: crossings on the block's boundary edges.
        k_all = truth_a.dense_counts(g.num_edges)
        ecoords = g.node_coords(g.edges)
        lo_a, hi_a = np.asarray(lo), np.asarray(lo) + 3
        in_box = np.all((ecoords >= lo_a) & (ecoords <= hi_a), axis=(1, 2))
        face_info = {}
        for ax, name in enumerate("xyz"):
            for side, v in (("-", lo_a[ax]), ("+", hi_a[ax])):
                on = in_box & (ecoords[:, 0, ax] == v) & (ecoords[:, 1, ax] == v)
                kk = k_all[on]
                face_info[f"{side}{name}"] = {
                    "crossings": int(kk.sum()),
                    "double": int((kk >= 2).sum()),
                }
        stratum = (
            "thin"
            if any(v >= 2 for v in truth_counts.values())
            else ("hard" if not any(ci.counts == truth_counts for ci in cands[:1]) else "easy")
        )
        cand_recs = {}
        for cc, oo in graded + diag:
            cand_recs[cc.key] = _cand_record(cc, oo, edges)
        problems.append(
            {
                "problem_id": f"{shape_id}#b{bi}",
                "shape_id": shape_id,
                "family": ctx.spec.family,
                "condition": condition_text(ctx.spec),
                "block_lo": list(lo),
                "block_edges": edges,
                "n_candidates_total": len(cands),
                "stratum": stratum,
                "truth_key": next((cc.key for cc in cands if cc.counts == truth_counts), "truth"),
                "truth_area": sum(truth_counts.values()),
                "truth_in_pool": truth_in_pool is not None,
                "truth_in_real": truth_in_real,
                "boundary_faces": face_info,
                "real_set": [cc.key for cc, _ in real],
                "diag_set": [cc.key for cc, _ in diag],
                "candidates": cand_recs,
            }
        )
    return problems


def save_problems(problems: list[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(problems, default=_json_default, ensure_ascii=False))
    tmp.rename(path)


def _json_default(o: object) -> object:
    if isinstance(o, np.integer):
        return int(o)
    if isinstance(o, np.floating):
        return float(o)
    if isinstance(o, np.bool_):
        return bool(o)
    if isinstance(o, tuple):
        return list(o)
    raise TypeError(type(o))

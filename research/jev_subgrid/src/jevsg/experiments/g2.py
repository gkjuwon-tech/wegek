"""G2 — selection diagnosis driver.

Subcommands::

    python -m jevsg.experiments.g2 build   # local problems + oracle grades (no model calls)
    python -m jevsg.experiments.g2 choose  # random / rules / Jev on every problem
    python -m jevsg.experiments.g2 report  # aggregate into results/g2/report.md

``build`` writes one ``problems/<shape>.json`` per shape (resumable).  ``choose`` caches
every Jev request/response by content hash, so re-running never pays twice.
"""

from __future__ import annotations

import argparse
import json
import multiprocessing as mp
import sys
import time
import traceback
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from jevsg.g2.choosers import grade, jev_choose, random_expected, rule_min_area, rule_simplest
from jevsg.g2.describe import LEVELS
from jevsg.g2.jev import JevClient
from jevsg.g2.problems import build_problems, save_problems
from jevsg.shapes.library import g2_shape_ids


def _build_one(args: tuple[str, str, str, int]) -> tuple[str, str]:
    shape_id, cache, out, count = args
    try:
        probs = build_problems(shape_id, cache, count=count)
        save_problems(probs, Path(out) / "problems" / f"{shape_id}.json")
        return shape_id, ""
    except Exception:
        return shape_id, traceback.format_exc()


def cmd_build(ns: argparse.Namespace) -> int:
    out = Path(ns.out)
    ids = ns.shapes or g2_shape_ids()
    todo = [s for s in ids if not (out / "problems" / f"{s}.json").exists()]
    print(f"[g2 build] {len(todo)} shapes to build ({len(ids) - len(todo)} cached)", flush=True)
    t0 = time.time()
    with mp.get_context("spawn").Pool(ns.workers, maxtasksperchild=2) as pool:
        for sid, err in pool.imap_unordered(
            _build_one, [(s, ns.cache, ns.out, ns.count) for s in todo]
        ):
            if err:
                print(f"[g2 build] {sid} FAILED\n{err}", file=sys.stderr, flush=True)
            else:
                print(f"[g2 build] {sid} done ({time.time() - t0:.0f}s)", flush=True)
    return 0


def load_problems(out: Path) -> list[dict[str, Any]]:
    probs: list[dict[str, Any]] = []
    for f in sorted((out / "problems").glob("*.json")):
        probs.extend(json.loads(f.read_text()))
    return probs


def _rows_for(problem: dict[str, Any], jev: dict[str, Any] | None) -> list[dict[str, Any]]:
    rows = []
    base = {k: problem[k] for k in ("problem_id", "shape_id", "family", "stratum", "truth_in_real")}
    for set_name in ("real", "diag"):
        keys = problem[f"{set_name}_set"]
        common = {**base, "set": set_name, "options": len(keys)}
        rexp = random_expected(problem, keys)
        rows.append(
            {
                **common,
                "chooser": "random",
                "perm": -1,
                "core": rexp["core"],
                "optimal": rexp["optimal"],
                "err_regret": rexp["err_regret"],
            }
        )
        for name, fn in (("R1_min_crossings", rule_min_area), ("R2_simplest", rule_simplest)):
            rows.append(
                {**common, "chooser": name, "perm": -1, **grade(problem, keys, fn(problem, keys))}
            )
        best = max(
            keys,
            key=lambda k: (
                problem["candidates"][k]["oracle"]["core_success"],
                -problem["candidates"][k]["oracle"]["local_err"],
            ),
        )
        rows.append({**common, "chooser": "oracle_best", "perm": -1, **grade(problem, keys, best)})
        if jev:
            for level, res in jev.items():
                for qid, ans in res.items():
                    if not qid.startswith(set_name + "_p"):
                        continue
                    g = grade(problem, keys, ans["chosen"])
                    rows.append(
                        {
                            **common,
                            "chooser": f"jev_{level}",
                            "perm": int(qid.split("_p")[1]),
                            **g,
                            "confidence": ans["confidence"],
                            "p_chosen": ans["probabilities"][ans["chosen"]],
                            "input_tokens": res["usage"].get("input_tokens", 0),
                            "model": res.get("model"),
                        }
                    )
    return rows


def cmd_choose(ns: argparse.Namespace) -> int:
    out = Path(ns.out)
    probs = load_problems(out)
    if not probs:
        print("[g2 choose] no problems; run build first", file=sys.stderr)
        return 1
    client = JevClient(Path(ns.jev_cache))
    levels = [] if ns.no_jev else list(LEVELS)

    def run(problem: dict[str, Any]) -> list[dict[str, Any]]:
        jev = {lvl: jev_choose(client, problem, lvl) for lvl in levels}
        return _rows_for(problem, jev)

    rows: list[dict[str, Any]] = []
    t0 = time.time()
    with ThreadPoolExecutor(ns.threads) as ex:
        for i, r in enumerate(ex.map(run, probs)):
            rows.extend(r)
            if (i + 1) % 20 == 0:
                u = client.usage
                print(
                    f"[g2 choose] {i + 1}/{len(probs)} problems, {u.requests} requests "
                    f"({u.cache_hits} cached), {u.input_tokens} input tokens, ${u.usd:.4f}, "
                    f"{time.time() - t0:.0f}s",
                    flush=True,
                )
    (out / "choices.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    (out / "jev_usage.json").write_text(json.dumps(client.usage.as_dict(), indent=1))
    print(f"[g2 choose] wrote {len(rows)} rows; usage {client.usage.as_dict()}", flush=True)
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build")
    b.add_argument("--out", default="results/g2")
    b.add_argument("--cache", default=".cache/g1/refs")
    b.add_argument("--workers", type=int, default=4)
    b.add_argument("--count", type=int, default=10)
    b.add_argument("--shapes", nargs="*", default=[])
    c = sub.add_parser("choose")
    c.add_argument("--out", default="results/g2")
    c.add_argument("--jev-cache", default=".cache/jev")
    c.add_argument("--threads", type=int, default=8)
    c.add_argument("--no-jev", action="store_true", help="baselines only (no API calls)")
    r = sub.add_parser("report")
    r.add_argument("--out", default="results/g2")
    ns = ap.parse_args(argv)
    if ns.cmd == "build":
        return cmd_build(ns)
    if ns.cmd == "choose":
        return cmd_choose(ns)
    if ns.cmd == "report":
        from jevsg.g2.report import write_report

        return write_report(Path(ns.out))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

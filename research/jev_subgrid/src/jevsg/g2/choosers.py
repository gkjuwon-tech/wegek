"""Choosers compared in G2 on identical candidate sets (proposal §5.3, §7).

* random   — uniform over the options (graded by its exact expectation);
* R1       — fewest crossings inside the block ("smallest surface");
* R2       — simplest resulting object: no sealed bubble, then fewest pieces + holes,
             then fewest crossings (uses the same computed effects Jev sees at L2);
* Jev      — argmax of the Choice probabilities, per context level and option order.

Grades use the oracle only after the choice is made.
"""

from __future__ import annotations

import random
from typing import Any

from jevsg.g2.describe import QUESTION, option_text, state_for
from jevsg.g2.jev import JevClient

OPTIMAL_TOL = 0.05  # grid cells: local error within this of the best counts as optimal


def grade(problem: dict[str, Any], keys: list[str], chosen: str) -> dict[str, Any]:
    cands = problem["candidates"]
    best = max(
        keys, key=lambda k: (cands[k]["oracle"]["core_success"], -cands[k]["oracle"]["local_err"])
    )
    b, c = cands[best]["oracle"], cands[chosen]["oracle"]
    return {
        "chosen": chosen,
        "core": bool(c["core_success"]),
        "best_core_available": bool(b["core_success"]),
        "optimal": bool(
            c["core_success"] == b["core_success"]
            and c["local_err"] <= b["local_err"] + OPTIMAL_TOL
        ),
        "err_regret": float(c["local_err"] - b["local_err"]),
        "is_truth_structure": chosen == problem["truth_key"],
    }


def random_expected(problem: dict[str, Any], keys: list[str]) -> dict[str, float]:
    gs = [grade(problem, keys, k) for k in keys]
    return {m: sum(float(g[m]) for g in gs) / len(gs) for m in ("core", "optimal", "err_regret")}


def rule_min_area(problem: dict[str, Any], keys: list[str]) -> str:
    c = problem["candidates"]
    return min(keys, key=lambda k: (c[k]["area"], k))


def rule_simplest(problem: dict[str, Any], keys: list[str]) -> str:
    c = problem["candidates"]

    def cost(k: str) -> tuple[int, int, int, int, str]:
        e = c[k]["effects"]
        return (
            int(e["bubbles_in_block"]),
            int(not e["object_closed"]),
            int(e["object_pieces"]) + int(e["object_holes"]),
            int(c[k]["area"]),
            k,
        )

    return min(keys, key=cost)


def permutation(problem_id: str, set_name: str, perm: int, keys: list[str]) -> list[str]:
    order = list(keys)
    random.Random(f"{problem_id}|{set_name}|{perm}").shuffle(order)
    return order


def jev_choose(
    client: JevClient, problem: dict[str, Any], level: str, perms: int = 2
) -> dict[str, Any]:
    """One request per (problem, level): real and diagnostic sets x option orders."""
    questions: dict[str, Any] = {}
    names: dict[str, dict[str, str]] = {}
    for set_name in ("real", "diag"):
        keys = problem[f"{set_name}_set"]
        for p in range(perms):
            order = permutation(problem["problem_id"], set_name, p, keys)
            qid = f"{set_name}_p{p}"
            names[qid] = {f"option_{i + 1}": k for i, k in enumerate(order)}
            questions[qid] = {
                "type": "choice",
                "instructions": QUESTION,
                "criteria": {
                    f"option_{i + 1}": option_text(problem, k, level) for i, k in enumerate(order)
                },
            }
    resp = client.ask(state_for(problem, level), questions)
    out: dict[str, Any] = {"model": resp.get("model"), "usage": resp.get("usage", {})}
    for qid, ans in resp["answers"].items():
        m = names[qid]
        out[qid] = {
            "chosen": m[ans["choice"]],
            "confidence": float(ans.get("confidence", float("nan"))),
            "probabilities": {m[o]: float(p) for o, p in ans["probabilities"].items()},
        }
    return out

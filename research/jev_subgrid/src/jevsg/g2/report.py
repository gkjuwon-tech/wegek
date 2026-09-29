"""G2 aggregation and the auto-generated Korean report.

The pass criterion was fixed before any Jev call was made (see ``PASS_RULE``); the
report states it verbatim and then applies it mechanically.
"""

from __future__ import annotations

import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Any

import numpy as np

PRIMARY = "jev_L2"
OPPONENTS = ("random", "R1_min_crossings", "R2_simplest")
PASS_RULE = (
    "실제 후보 집합(real)에서 Jev L2가 선택한 후보의 핵심 구조 성공률이 무작위·R1·R2 각각보다 높고, "
    "문제 단위 paired bootstrap 95% 신뢰구간이 0을 포함하지 않으며, 이 조건이 두 선택지 순서(p0, p1) "
    "모두에서 성립하면 G2 통과. (Jev 호출 전에 고정한 기준)"
)
CHOOSER_KO = {
    "random": "무작위(기댓값)",
    "R1_min_crossings": "R1 교차 최소",
    "R2_simplest": "R2 가장 단순한 물체",
    "jev_L0": "Jev L0 (숫자만)",
    "jev_L1": "Jev L1 (+주변 구조)",
    "jev_L2": "Jev L2 (+효과 요약)",
    "oracle_best": "후보 중 최선 (상한)",
}


def _load(out: Path) -> list[dict[str, Any]]:
    return [json.loads(x) for x in (out / "choices.jsonl").read_text().splitlines() if x]


def _pct(x: float) -> str:
    return "–" if not math.isfinite(x) else f"{100 * x:.1f}%"


def per_problem(
    rows: list[dict[str, Any]], chooser: str, set_name: str, perm: int | None
) -> dict[str, float]:
    """Mean core success per problem for one chooser (averaged over perms unless given)."""
    acc: dict[str, list[float]] = defaultdict(list)
    for r in rows:
        if (
            r["chooser"] == chooser
            and r["set"] == set_name
            and (perm is None or r["perm"] in (perm, -1))
        ):
            acc[r["problem_id"]].append(float(r["core"]))
    return {k: float(np.mean(v)) for k, v in acc.items()}


def paired(
    a: dict[str, float], b: dict[str, float], reps: int = 10_000, seed: int = 0
) -> dict[str, float]:
    ids = sorted(set(a) & set(b))
    d = np.array([a[i] - b[i] for i in ids])
    rng = np.random.default_rng(seed)
    boots = d[rng.integers(0, len(d), size=(reps, len(d)))].mean(axis=1) if len(d) else np.zeros(1)
    wins = int(np.sum(d > 0))
    losses = int(np.sum(d < 0))
    # Exact two-sided sign test on problems where they differ.
    n = wins + losses
    k = min(wins, losses)
    p = min(1.0, 2 * sum(math.comb(n, i) for i in range(k + 1)) / 2**n) if n else 1.0
    return {
        "diff": float(d.mean()) if len(d) else 0.0,
        "lo": float(np.quantile(boots, 0.025)),
        "hi": float(np.quantile(boots, 0.975)),
        "wins": wins,
        "losses": losses,
        "sign_p": p,
        "n": len(ids),
    }


def write_report(out: Path) -> int:
    rows = _load(out)
    probs = [
        p for f in sorted((out / "problems").glob("*.json")) for p in json.loads(f.read_text())
    ]
    usage = (
        json.loads((out / "jev_usage.json").read_text())
        if (out / "jev_usage.json").exists()
        else {}
    )
    L: list[str] = []
    w = L.append
    choosers = [c for c in CHOOSER_KO if any(r["chooser"] == c for r in rows)]
    w("# G2 선택 진단 보고서 — Jev가 좋은 후보를 고르는가")
    w("")
    w("> 자동 생성 문서입니다 (`python -m jevsg.experiments.g2 report`).")
    w("")
    w("## 0. 사전 고정한 통과 기준")
    w("")
    w(PASS_RULE)
    w("")
    w("## 1. 문제 집합")
    w("")
    n = len(probs)
    opts_real = [len(p["real_set"]) for p in probs]
    best_real = np.mean(
        [any(p["candidates"][k]["oracle"]["core_success"] for k in p["real_set"]) for p in probs]
    )
    best_diag = np.mean(
        [any(p["candidates"][k]["oracle"]["core_success"] for k in p["diag_set"]) for p in probs]
    )
    strata: dict[str, int] = defaultdict(int)
    for p in probs:
        strata[p["stratum"]] += 1
    w(
        f"- 형상 {len({p['shape_id'] for p in probs})}개(G1과 시드가 겹치지 않는 `g2_selection` 분할), 국소 문제 **{n}개**, 격자 n=64, 숨긴 블록 3×3×3칸."
    )
    w(
        f"- 실제 후보 수: 평균 {np.mean(opts_real):.1f}개 (최소 {min(opts_real)}, 최대 {max(opts_real)}). "
        f"후보 풀: 블록마다 전체 후보 중 교차가 적은 16개 + 나머지에서 고르게 16개를 복원해 보고, 효과가 다른 대표를 선택."
    )
    w(
        f"- 정답 구조가 실제 후보에 자연히 포함된 비율: {_pct(float(np.mean([p['truth_in_real'] for p in probs])))}"
    )
    w(
        f"- **후보 안에 핵심 구조를 보존하는 답이 하나라도 있는 비율**(후보 생성기의 상한): 실제 {_pct(float(best_real))}, 진단 {_pct(float(best_diag))}"
    )
    w(
        "- 층(분석용, 선택자에게는 비공개): "
        + ", ".join(f"{k} {v}" for k, v in sorted(strata.items()))
    )
    w("")
    for set_name, title in (
        ("real", "실제 후보 집합 (정답 강제 포함 없음) — 주 결과"),
        ("diag", "진단 집합 (정답 구조 강제 포함) — 선택 능력의 상한"),
    ):
        w(f"## {'2' if set_name == 'real' else '3'}. {title}")
        w("")
        w("| 선택자 | 핵심 구조 성공 | 최적 선택 | 국소 오차 후회(칸) | 비고 |")
        w("|---|---:|---:|---:|---|")
        for c in choosers:
            rs = [r for r in rows if r["chooser"] == c and r["set"] == set_name]
            if not rs:
                continue
            note = ""
            if c.startswith("jev"):
                p0 = np.mean([r["core"] for r in rs if r["perm"] == 0])
                p1 = np.mean([r["core"] for r in rs if r["perm"] == 1])
                note = f"순서 p0 {_pct(float(p0))} / p1 {_pct(float(p1))}"
            w(
                f"| {CHOOSER_KO[c]} | **{_pct(float(np.mean([r['core'] for r in rs])))}** | "
                f"{_pct(float(np.mean([r['optimal'] for r in rs])))} | {np.mean([r['err_regret'] for r in rs]):.3f} | {note} |"
            )
        w("")
    w("## 4. 통과 판정 (실제 집합, 문제 단위 paired 비교)")
    w("")
    verdict = True
    if not any(r["chooser"] == PRIMARY for r in rows):
        w("Jev 결과가 없습니다 (baseline만 실행).")
        verdict = False
    else:
        w("| 비교 | 순서 | 차이(성공률) | 95% CI | Jev 우세 / 열세 문제 | 부호검정 p |")
        w("|---|---|---:|---|---:|---:|")
        for opp in OPPONENTS:
            for perm in (0, 1):
                st = paired(
                    per_problem(rows, PRIMARY, "real", perm), per_problem(rows, opp, "real", None)
                )
                ok = st["lo"] > 0
                verdict &= ok
                w(
                    f"| Jev L2 vs {CHOOSER_KO[opp]} | p{perm} | {100 * st['diff']:+.1f}%p | "
                    f"[{100 * st['lo']:+.1f}, {100 * st['hi']:+.1f}] {'✅' if ok else '❌'} | {st['wins']} / {st['losses']} | {st['sign_p']:.3g} |"
                )
        w("")
        w(f"**판정: {'G2 통과' if verdict else 'G2 미통과'}** (기준은 0장).")
    w("")
    w("## 5. 문맥 수준별 비교 (제거 실험 §8.3)")
    w("")
    w("| 수준 | 실제 집합 성공 | 진단 집합 성공 | 두 순서 선택 일치율 | 평균 confidence |")
    w("|---|---:|---:|---:|---:|")
    for lvl in ("jev_L0", "jev_L1", "jev_L2"):
        rs = [r for r in rows if r["chooser"] == lvl]
        if not rs:
            continue
        agree = []
        for set_name in ("real", "diag"):
            by: dict[str, dict[int, str]] = defaultdict(dict)
            for r in rs:
                if r["set"] == set_name:
                    by[r["problem_id"]][r["perm"]] = r["chosen"]
            agree += [v.get(0) == v.get(1) for v in by.values()]
        w(
            f"| {CHOOSER_KO[lvl]} | {_pct(float(np.mean([r['core'] for r in rs if r['set'] == 'real'])))} | "
            f"{_pct(float(np.mean([r['core'] for r in rs if r['set'] == 'diag'])))} | {_pct(float(np.mean(agree)))} | "
            f"{np.mean([r['confidence'] for r in rs]):.2f} |"
        )
    w("")
    w("## 6. 계열별 (실제 집합, 핵심 구조 성공률)")
    w("")
    fams = sorted({r["family"] for r in rows})
    w("| 계열 | " + " | ".join(CHOOSER_KO[c] for c in choosers) + " |")
    w("|---|" + "---:|" * len(choosers))
    for f in fams:
        cells = [
            _pct(
                float(
                    np.mean(
                        [
                            r["core"]
                            for r in rows
                            if r["chooser"] == c and r["set"] == "real" and r["family"] == f
                        ]
                        or [float("nan")]
                    )
                )
            )
            for c in choosers
        ]
        w(f"| {f} | " + " | ".join(cells) + " |")
    w("")
    w("## 7. 보정(calibration): Jev L2가 고른 후보의 확률 vs 실제 성공 (실제+진단)")
    w("")
    rs = [r for r in rows if r["chooser"] == PRIMARY]
    if rs:
        w("| 선택 확률 구간 | 사례 수 | 실제 성공률 |")
        w("|---|---:|---:|")
        for lo, hi in ((0, 0.4), (0.4, 0.6), (0.6, 0.8), (0.8, 0.95), (0.95, 1.01)):
            b = [r for r in rs if lo <= r["p_chosen"] < hi]
            w(
                f"| {lo:.2f}–{min(hi, 1):.2f} | {len(b)} | {_pct(float(np.mean([r['core'] for r in b])) if b else float('nan'))} |"
            )
    w("")
    w("## 8. 비용")
    w("")
    if usage:
        w(
            f"- 요청 {usage.get('requests', 0)}회 (캐시 적중 {usage.get('cache_hits', 0)}), 입력 토큰 {usage.get('input_tokens', 0):,}, "
            f"출력 토큰 {usage.get('output_tokens', 0):,} (무료), 비용 **${usage.get('usd', 0):.4f}**, 재시도 {usage.get('retries', 0)}회."
        )
        req = max(usage.get("requests", 0), 1)
        w(
            f"- 요청당 평균 지연 {usage.get('seconds', 0) / req:.2f}s, 요청당 평균 입력 토큰 {usage.get('input_tokens', 0) / req:.0f}."
        )
        w(
            "- 모델: `jev-1.13.0` (버전 고정). 한 요청 = 한 문제·한 문맥 수준에서 실제/진단 × 두 순서, 네 질문."
        )
    w("")
    w("## 9. Jev L2와 R2가 갈린 문제 (실제 집합, 순서 p0)")
    w("")
    j = {
        r["problem_id"]: r
        for r in rows
        if r["chooser"] == PRIMARY and r["set"] == "real" and r["perm"] == 0
    }
    r2 = {r["problem_id"]: r for r in rows if r["chooser"] == "R2_simplest" and r["set"] == "real"}
    diff = [pid for pid in j if pid in r2 and j[pid]["core"] != r2[pid]["core"]]
    if not diff:
        w("없음.")
    for pid in sorted(diff):
        who = "Jev만 성공" if j[pid]["core"] else "R2만 성공"
        prob = next(p for p in probs if p["problem_id"] == pid)
        w(f'- `{pid}` — {who}. 조건: "{prob["condition"]}"')
    (out / "report.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"[g2 report] wrote {out / 'report.md'}")
    return 0

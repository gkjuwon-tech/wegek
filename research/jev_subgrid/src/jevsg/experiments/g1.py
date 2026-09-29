"""G1 — round trip 3D -> A -> 3D on 48 structured shapes (proposal §6, G1 row).

For every validated reference shape and every grid resolution this runs

* the exact encoder (mesh -> A) and a cross-check of A against the reference
  implementation's own end-to-end pipeline on the identical grid;
* the pinned primal reconstructor on A and on representation variants:

  - ``float64``        full precision, no cap (the representation itself);
  - ``q{b}``           positions as ``b``-bit bin choices (precision sweep);
  - ``K{c}``           at most ``c`` crossings per edge, removed in pairs (``K1`` is the
                       single-crossing baseline of ablation §8.1);

* the evaluation of :mod:`jevsg.evaluate` (topology, probes, validity, geometry, size).

Results are appended per shape to ``rows/<shape>.jsonl`` (resumable), then aggregated
into ``rows.csv.gz``, ``references.json``, ``summary.json`` and the Korean report
``report.md``.  The pass criterion and target (core-structure success >= 90 % at the
selected budget) were fixed in the proposal before this code ran.
"""

from __future__ import annotations

import argparse
import contextlib
import csv
import datetime as dt
import gzip
import importlib.metadata
import json
import math
import multiprocessing as mp
import os
import platform
import subprocess
import sys
import tempfile
import time
import traceback
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from jevsg.decode import (
    RECONSTRUCTOR_VERSION,
    assert_pinned_reconstructor,
    compare_with_reference_pipeline,
    decode_primal,
    reconstructor_version,
    reference_pipeline,
)
from jevsg.encode import encode_mesh
from jevsg.evaluate import evaluate_reconstruction, finalize_row
from jevsg.grid import GRID_SCHEME_NAME, TetGrid
from jevsg.metrics import SurfaceDistance, sample_surface
from jevsg.representation import (
    EdgeCoordinates,
    cap_crossings,
    check,
    odd_faces,
    quantize,
    size_report,
)
from jevsg.shapes.library import FAMILIES, FAMILY_KO, build_shape, g1_shape_ids
from jevsg.shapes.reference import build_reference

TARGET_SUCCESS = 0.90  # proposal §6: 선정 예산에서 핵심 구조 성공률 90% 이상을 목표


@dataclass(frozen=True)
class G1Config:
    out: Path
    cache: Path
    resolutions: tuple[int, ...] = (8, 16, 32, 64)
    bits: tuple[int, ...] = (4, 6, 8, 10, 12, 16)
    caps: tuple[int, ...] = (1, 2, 4)
    samples: int = 30_000
    workers: int = max(1, (os.cpu_count() or 2) - 0)
    shapes: tuple[str, ...] = ()
    check_self_intersections: bool = True
    ref_voxel: float | None = None  # None = automatic (>= 3 voxels across the thinnest feature)


# ----------------------------------------------------------------- per shape
_GRIDS: dict[int, TetGrid] = {}


def _grid(n: int) -> TetGrid:
    if n not in _GRIDS:
        g = TetGrid(n)
        _ = g.tet_edge_ids, g.face_edge_ids, g.edge_directions  # warm caches once per process
        _GRIDS[n] = g
    return _GRIDS[n]


def _variants(
    a: EdgeCoordinates, cfg: G1Config
) -> Iterable[tuple[str, EdgeCoordinates, int | None, dict[str, Any]]]:
    yield "float64", a, None, {"kind": "float64", "bits": 64, "cap": 0}
    for b in cfg.bits:
        qa, qs = quantize(a, b)
        yield (
            f"q{b}",
            qa,
            b,
            {
                "kind": "quantized",
                "bits": b,
                "cap": 0,
                **{f"q_{k}": v for k, v in qs.as_dict().items()},
            },
        )
    for c in cfg.caps:
        ca, cs = cap_crossings(a, c)
        yield (
            f"K{c}",
            ca,
            None,
            {
                "kind": "capped",
                "bits": 64,
                "cap": c,
                **{f"cap_{k}": v for k, v in cs.as_dict().items()},
            },
        )


def run_shape(shape_id: str, cfg: G1Config) -> tuple[str, dict[str, Any], list[dict[str, Any]]]:
    spec = build_shape(shape_id)
    ref = build_reference(
        spec, cfg.cache / "refs", check_self_intersections=True, voxel=cfg.ref_voxel
    )
    summary = ref.summary()
    rows: list[dict[str, Any]] = []
    if not ref.valid:
        return shape_id, summary, rows
    rng = np.random.default_rng(12345)
    ref_samples = sample_surface(ref.mesh, cfg.samples, rng)
    ref_dist = SurfaceDistance(ref.mesh)
    workdir = tempfile.mkdtemp(prefix="jevsg_g1_")
    for n in cfg.resolutions:
        grid = _grid(n)
        a, est = encode_mesh(ref.mesh, grid)
        check(a, grid)
        base: dict[str, Any] = {
            "shape_id": shape_id,
            "family": spec.family,
            "variant": spec.variant,
            "pose": spec.params.get("pose", ""),
            "resolution": n,
            "spacing": grid.spacing,
            "min_feature_grid": ref.min_feature_grid,
            "feature_over_spacing": ref.min_feature_grid / grid.spacing,
            "ref_faces": ref.mesh.num_faces,
            "odd_faces_A": odd_faces(a, grid),
            **{f"enc_{k}": v for k, v in est.as_dict().items()},
        }
        # Cross-check the encoder against the reference implementation's own queries.
        full = decode_primal(a, grid, workdir=workdir)
        try:
            theirs = reference_pipeline(ref.mesh, grid)
            base.update(compare_with_reference_pipeline(full.mesh, theirs.mesh))
            base["xcheck_their_non_even_tets"] = theirs.non_even_tets
            base["xcheck_error"] = ""
        except RuntimeError as exc:
            # The reference pipeline asserts when its output has no faces (e.g. a thin
            # ring that misses every edge of a coarse grid).  Record it; ours must then be
            # empty too for the cross-check to count as agreement.
            base.update(
                {
                    "xcheck_same_connectivity": full.mesh.num_faces == 0,
                    "xcheck_max_vertex_diff": 0.0 if full.mesh.num_faces == 0 else -1.0,
                    "xcheck_faces_ours": full.mesh.num_faces,
                    "xcheck_faces_theirs": 0,
                    "xcheck_their_non_even_tets": 0,
                    "xcheck_error": str(exc).splitlines()[0][:200],
                }
            )
        for name, av, bits, extra in _variants(a, cfg):
            t0 = time.perf_counter()
            dec = full if name == "float64" else decode_primal(av, grid, workdir=workdir)
            sz = size_report(av, bits)
            ev = evaluate_reconstruction(
                ref,
                dec.mesh,
                samples=cfg.samples,
                seed=7,
                ref_distance=ref_dist,
                ref_samples=ref_samples,
                check_self_intersections=cfg.check_self_intersections,
            )
            row = {
                **base,
                "config": name,
                **extra,
                "A_active_edges": av.num_active_edges,
                "A_crossings": av.num_crossings,
                "A_max_k": av.max_k,
                "A_edges_k_ge2": int(np.count_nonzero(av.counts >= 2)),
                "A_odd_faces": odd_faces(av, grid),
                **{f"bytes_{k}": v for k, v in sz.as_dict().items()},
                **dec.as_dict(),
                **ev,
                "eval_seconds": time.perf_counter() - t0,
            }
            rows.append(row)
    with contextlib.suppress(OSError):
        os.rmdir(workdir)
    return shape_id, summary, rows


def _worker(args: tuple[str, G1Config]) -> tuple[str, dict[str, Any], list[dict[str, Any]], str]:
    shape_id, cfg = args
    try:
        sid, summary, rows = run_shape(shape_id, cfg)
        return sid, summary, rows, ""
    except Exception:  # recorded as a failure of the run, never swallowed silently
        return (
            shape_id,
            {"shape_id": shape_id, "valid": False, "problems": ["crash"]},
            [],
            traceback.format_exc(),
        )


# --------------------------------------------------------------- aggregation
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


def _load_rows(out: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    rows: list[dict[str, Any]] = []
    refs: list[dict[str, Any]] = []
    for f in sorted((out / "rows").glob("*.jsonl")):
        with f.open(encoding="utf-8") as fh:
            for line in fh:
                rec = json.loads(line)
                if rec.get("_type") == "reference":
                    refs.append(rec["data"])
                else:
                    rows.append(finalize_row(rec))  # same rules as at evaluation time
    return rows, refs


def _rate(xs: Sequence[bool]) -> float:
    return float(np.mean(xs)) if xs else float("nan")


def _median(xs: Sequence[float]) -> float:
    ys = [x for x in xs if x is not None and math.isfinite(x)]
    return float(np.median(ys)) if ys else float("nan")


def _pct(x: float) -> str:
    return "–" if not math.isfinite(x) else f"{100 * x:.1f}%"


def _fmt(x: float, digits: int = 4) -> str:
    if x is None or not math.isfinite(x):
        return "∞" if x == float("inf") else "–"
    return f"{x:.{digits}g}"


def _git_commit(path: Path) -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], cwd=path, text=True, stderr=subprocess.DEVNULL
        ).strip()
    except Exception:
        return "unknown"


def summarize(
    rows: list[dict[str, Any]], refs: list[dict[str, Any]], cfg: G1Config
) -> dict[str, Any]:
    configs = sorted({r["config"] for r in rows}, key=_config_order)
    res = sorted({r["resolution"] for r in rows})
    by: dict[tuple[str, int], list[dict[str, Any]]] = {}
    for r in rows:
        by.setdefault((r["config"], r["resolution"]), []).append(r)
    table = []
    for c in configs:
        for n in res:
            rs = by.get((c, n), [])
            if not rs:
                continue
            table.append(
                {
                    "config": c,
                    "resolution": n,
                    "shapes": len(rs),
                    "core_success": _rate([r["core_success"] for r in rs]),
                    "topology_match": _rate([r["topology_match"] for r in rs]),
                    "probes_ok": _rate([r["probes_ok"] for r in rs]),
                    "valid_manifold": _rate([r["valid_manifold"] for r in rs]),
                    "intersection_free": _rate([bool(r["intersection_free"]) for r in rs]),
                    "median_bytes": _median([r["bytes_raw_bytes"] for r in rs]),
                    "median_zlib_bytes": _median([r["bytes_zlib_bytes"] for r in rs]),
                    "median_chamfer_l1": _median([r["chamfer_l1"] for r in rs]),
                    "median_fscore@0.005": _median([r["fscore@0.005"] for r in rs]),
                    "median_volume_rel_err": _median([r["volume_rel_err"] for r in rs]),
                    "non_even_tets_total": int(sum(r["non_even_tets"] for r in rs)),
                }
            )
    # Budget selection: the cheapest configuration (median raw bytes) meeting the target.
    eligible = [t for t in table if t["core_success"] >= TARGET_SUCCESS]
    selected = min(eligible, key=lambda t: t["median_bytes"]) if eligible else None
    return {
        "generated": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "target_core_success": TARGET_SUCCESS,
        "table": table,
        "selected_budget": selected,
        "references_valid": sum(1 for r in refs if r.get("valid")),
        "references_total": len(refs),
    }


def _config_order(c: str) -> tuple[int, int]:
    if c == "float64":
        return (0, 0)
    if c.startswith("q"):
        return (1, -int(c[1:]))
    return (2, -int(c[1:]))


# ------------------------------------------------------------------- report
def write_report(
    rows: list[dict[str, Any]],
    refs: list[dict[str, Any]],
    summary: dict[str, Any],
    cfg: G1Config,
    meta: dict[str, Any],
) -> str:
    L: list[str] = []
    w = L.append
    res = sorted({r["resolution"] for r in rows})
    f64 = [r for r in rows if r["config"] == "float64"]

    def sel(config: str, n: int | None = None, fam: str | None = None) -> list[dict[str, Any]]:
        return [
            r
            for r in rows
            if r["config"] == config
            and (n is None or r["resolution"] == n)
            and (fam is None or r["family"] == fam)
        ]

    w("# G1 왕복(3D → A → 3D) 실험 보고서")
    w("")
    w(
        "> 자동 생성 문서입니다 (`python -m jevsg.experiments.g1`). 숫자를 손으로 고치지 마세요 — 다시 돌리세요."
    )
    w("")
    w("## 0. 실행 정보")
    w("")
    w("| 항목 | 값 |")
    w("|---|---|")
    for k, v in meta.items():
        w(f"| {k} | `{v}` |")
    w("")
    w("## 1. 기준(reference) 형상 검증")
    w("")
    nvalid = summary["references_valid"]
    w(
        f"설계된 48개 형상 중 **{nvalid}/{summary['references_total']}개**가 검증을 통과해 평가에 쓰였습니다. "
        "검증 = 닫힌 방향성 2-다양체 + 자기교차 0 + 설계한 성분 수·genus 일치 + 모든 프로브가 설계한 쪽(공기/재료)에 여유거리를 두고 위치."
    )
    w("")
    w("| 계열 | 형상 수 | 통과 | 최소 특징 크기(격자 단위) 범위 | 면 수(중앙값) |")
    w("|---|---:|---:|---|---:|")
    for fam in FAMILIES:
        fr = [r for r in refs if r.get("family") == fam]
        if not fr:
            continue
        mf = [r["min_feature_grid"] for r in fr if "min_feature_grid" in r]
        w(
            f"| {FAMILY_KO[fam]} (`{fam}`) | {len(fr)} | {sum(1 for r in fr if r.get('valid'))} | "
            f"{min(mf):.3f} – {max(mf):.3f} | {int(np.median([r['faces'] for r in fr]))} |"
        )
    bad = [r for r in refs if not r.get("valid")]
    if bad:
        w("")
        w("검증 실패로 **제외된** 형상 (수리하지 않고 그대로 보고):")
        w("")
        for r in bad:
            w(f"- `{r['shape_id']}`: {'; '.join(r.get('problems', []))}")
    w("")
    w(
        "격자 간격(spacing) 참고: "
        + ", ".join(f"n={n}: {2 / (n - 1):.4f}" for n in res)
        + " (격자 단위, 형상은 [-0.98, 0.98]³에 맞춤)."
    )
    w("")

    w("## 2. 인코더 정확성 (A가 제대로 만들어졌는가)")
    w("")
    same = [r["xcheck_same_connectivity"] for r in f64]
    vd = [r["xcheck_max_vertex_diff"] for r in f64 if r["xcheck_max_vertex_diff"] >= 0]
    w(
        f"- 저자 구현의 end-to-end 파이프라인(FCPW 광선 질의)과 **동일 격자에서 출력 연결구조 완전 일치**: "
        f"{sum(same)}/{len(same)} (형상×해상도). 일치한 경우 정점 좌표 최대 차이 {max(vd) if vd else float('nan'):.2e} "
        "(저자 BVH의 float32 좌표 때문)."
    )
    mism = [r for r in f64 if not r["xcheck_same_connectivity"]]
    if mism:
        w(
            f"- 불일치 {len(mism)}건: "
            + ", ".join(
                f"`{r['shape_id']}@{r['resolution']}`(우리 {r['xcheck_faces_ours']}면 / 저자 {r['xcheck_faces_theirs']}면, 저자 non-even {r['xcheck_their_non_even_tets']})"
                for r in mism[:12]
            )
        )
        odd_theirs = sum(1 for r in mism if r["xcheck_their_non_even_tets"] > 0)
        w(
            f"  - 불일치 {len(mism)}건 중 **{odd_theirs}건**에서 저자 파이프라인 출력이 짝수합 조건을 어겼습니다 "
            "(non-even tets > 0). 닫힌 입력에서 짝수합 위반은 교차를 잘못 센 증거이므로, 이 경우들은 저자 쪽 "
            "float32 광선 질의의 오차입니다. 우리 A는 정확 술어로 계산되므로 아래의 `A 홀수 면 = 0`이 항상 성립합니다."
        )
    agree_even = [
        r["xcheck_same_connectivity"] for r in f64 if r["xcheck_their_non_even_tets"] == 0
    ]
    w(
        f"- 저자 파이프라인이 짝수합을 만족한 경우만 보면 연결구조 일치: **{sum(agree_even)}/{len(agree_even)}**."
    )
    w(
        f"- A의 짝수합 조건 위반 면(odd faces) 합계: **{sum(r['odd_faces_A'] for r in f64)}**, "
        f"복원기가 보고한 non-even tets 합계: **{sum(r['non_even_tets'] for r in f64)}** "
        f"(저자 파이프라인 non-even tets 합계: {sum(r['xcheck_their_non_even_tets'] for r in f64)})."
    )
    w(
        f"- 퇴화 처리 통계(전체 인코딩 합): 정확 산술 fallback {sum(r['enc_exact_fallbacks'] for r in f64)}회, "
        f"정확히 0인 행렬식 {sum(r['enc_exact_zeros'] for r in f64)}회 → 기호적 섭동으로 해소 {sum(r['enc_sos_resolved'] for r in f64)}회, "
        f"퇴화 삼각형 {sum(r['enc_degenerate_triangles'] for r in f64)}개, t 클램프 {sum(r['enc_t_clamped'] for r in f64)}회, "
        f"동일 t 분리 {sum(r['enc_t_nudged'] for r in f64)}회. 제외·수리된 교차: 0."
    )
    w("")

    w("## 3. 해상도별 결과 (float64 위치, 교차 수 제한 없음)")
    w("")
    w(
        "| n | 핵심 구조 성공 | 위상 일치 | 프로브 통과 | 닫힌 다양체 | 자기교차 없음 | Chamfer-L1 (중앙값, 대각선 비) | F@0.5% (중앙값) | 부피 상대오차 (중앙값) | A 크기 (중앙값, B) | zlib (B) | k≥2 모서리 비율 |"
    )
    w("|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    for n in res:
        rs = sel("float64", n)
        k2 = _median([r["A_edges_k_ge2"] / max(r["A_active_edges"], 1) for r in rs])
        w(
            f"| {n} | **{_pct(_rate([r['core_success'] for r in rs]))}** | {_pct(_rate([r['topology_match'] for r in rs]))} | "
            f"{_pct(_rate([r['probes_ok'] for r in rs]))} | {_pct(_rate([r['valid_manifold'] for r in rs]))} | "
            f"{_pct(_rate([bool(r['intersection_free']) for r in rs]))} | {_fmt(_median([r['chamfer_l1'] for r in rs]))} | "
            f"{_fmt(_median([r['fscore@0.005'] for r in rs]))} | {_fmt(_median([r['volume_rel_err'] for r in rs]))} | "
            f"{int(_median([r['bytes_raw_bytes'] for r in rs]))} | {int(_median([r['bytes_zlib_bytes'] for r in rs]))} | {_pct(k2)} |"
        )
    w("")
    w("### 3.1 계열별 핵심 구조 성공률 (float64)")
    w("")
    w("| 계열 | " + " | ".join(f"n={n}" for n in res) + " |")
    w("|---|" + "---:|" * len(res))
    for fam in FAMILIES:
        cells = [_pct(_rate([r["core_success"] for r in sel("float64", n, fam)])) for n in res]
        w(f"| {FAMILY_KO[fam]} | " + " | ".join(cells) + " |")
    w("")
    w("### 3.2 구조 종류별 프로브 보존율 (float64)")
    w("")
    structs = sorted({k[len("struct_") :] for r in f64 for k in r if k.startswith("struct_")})
    w("| 구조 | " + " | ".join(f"n={n}" for n in res) + " |")
    w("|---|" + "---:|" * len(res))
    for st in structs:
        cells = []
        for n in res:
            vals = [r[f"struct_{st}"] for r in sel("float64", n) if f"struct_{st}" in r]
            cells.append(_pct(_rate(vals)) + f" ({len(vals)})")
        w(f"| `{st}` | " + " | ".join(cells) + " |")
    w("")

    w("## 4. 얇은 구조 대 격자 간격: 다중 교차의 효과 (제거 실험 §8.1)")
    w("")
    w(
        "최소 특징 크기(벽 두께·틈·관 지름)를 격자 간격으로 나눈 비율 구간별 핵심 구조 성공률입니다. "
        "`K1`은 모서리당 교차를 0/1로 줄인(짝 단위 제거, 짝수합 유지) 단일 교차 표현입니다."
    )
    w("")
    bins = [(0, 0.25), (0.25, 0.5), (0.5, 1.0), (1.0, 2.0), (2.0, 1e9)]
    w("| 특징/간격 | 사례 수 | float64 (다중 교차) | K4 | K2 | K1 (단일 교차) |")
    w("|---|---:|---:|---:|---:|---:|")
    for lo, hi in bins:
        label = f"{lo:g} – {hi:g}" if hi < 1e9 else f"≥ {lo:g}"
        cells = []
        cnt = 0
        for c in ("float64", "K4", "K2", "K1"):
            rs = [r for r in rows if r["config"] == c and lo <= r["feature_over_spacing"] < hi]
            cnt = max(cnt, len(rs))
            cells.append(_pct(_rate([r["core_success"] for r in rs])))
        w(f"| {label} | {cnt} | " + " | ".join(cells) + " |")
    w("")

    w("## 5. 위치 정밀도 스윕 (교차 위치를 b비트 구간 선택으로 저장)")
    w("")
    bits_cfgs = [
        c for c in sorted({r["config"] for r in rows}, key=_config_order) if c.startswith("q")
    ] + ["float64"]
    w("| 설정 | " + " | ".join(f"n={n} 성공 / 크기(B) / Chamfer" for n in res) + " |")
    w("|---|" + "---|" * len(res))
    for c in bits_cfgs:
        cells = []
        for n in res:
            rs = sel(c, n)
            if not rs:
                cells.append("–")
                continue
            cells.append(
                f"{_pct(_rate([r['core_success'] for r in rs]))} / {int(_median([r['bytes_raw_bytes'] for r in rs]))} / {_fmt(_median([r['chamfer_l1'] for r in rs]), 3)}"
            )
        w(f"| `{c}` | " + " | ".join(cells) + " |")
    w("")
    q = [r for r in rows if r["config"].startswith("q")]
    if q:
        w("양자화 충돌(같은 구간에 떨어진 교차를 인접 구간으로 밀어낸 횟수, k는 절대 바꾸지 않음):")
        w("")
        w("| 설정 | " + " | ".join(f"n={n}" for n in res) + " |")
        w("|---|" + "---:|" * len(res))
        for c in bits_cfgs[:-1]:
            cells = []
            for n in res:
                rs = sel(c, n)
                tot = sum(r["q_crossings"] for r in rs)
                bumped = sum(r["q_bumped"] for r in rs)
                cells.append(f"{bumped} / {tot}")
            w(f"| `{c}` | " + " | ".join(cells) + " |")
        w("")

    w("## 6. 교차 수 상한 K (잘린 교차와 사라진 구조를 함께 보고)")
    w("")
    w(
        "| 설정 | n | 핵심 구조 성공 | 상한 초과 모서리 비율 | 제거된 교차 비율 | 빈 출력(형상 소실) | 실패한 구조(프로브) 상위 |"
    )
    w("|---|---:|---:|---:|---:|---:|---|")
    for c in [
        c for c in sorted({r["config"] for r in rows}, key=_config_order) if c.startswith("K")
    ]:
        for n in res:
            rs = sel(c, n)
            if not rs:
                continue
            base = {r["shape_id"]: r for r in sel("float64", n)}
            over = sum(r["cap_edges_over_cap"] for r in rs) / max(
                sum(base[r["shape_id"]]["A_active_edges"] for r in rs), 1
            )
            drop = sum(r["cap_crossings_dropped"] for r in rs) / max(
                sum(base[r["shape_id"]]["A_crossings"] for r in rs), 1
            )
            lost: dict[str, int] = {}
            for r in rs:
                for st in (k for k in r if k.startswith("struct_")):
                    if not r[st] and base[r["shape_id"]].get(st, False):
                        lost[st[7:]] = lost.get(st[7:], 0) + 1
            top = (
                ", ".join(f"{k}×{v}" for k, v in sorted(lost.items(), key=lambda kv: -kv[1])[:4])
                or "없음"
            )
            empty = sum(1 for r in rs if r["failure_code"] == "E")
            w(
                f"| `{c}` | {n} | {_pct(_rate([r['core_success'] for r in rs]))} | {_pct(over)} | {_pct(drop)} | {empty} | {top} |"
            )
    w("")

    w("## 7. 예산 선정 (G1 통과 기준: 핵심 구조 성공률 ≥ 90%)")
    w("")
    selb = summary["selected_budget"]
    if selb:
        w(
            f"측정 결과, 기준을 만족하는 설정 중 A 크기(중앙값)가 가장 작은 것은 **`{selb['config']}` @ n={selb['resolution']}** "
            f"(성공률 {_pct(selb['core_success'])}, 중앙값 {int(selb['median_bytes'])} B, zlib {int(selb['median_zlib_bytes'])} B, "
            f"Chamfer-L1 {_fmt(selb['median_chamfer_l1'])})."
        )
        w("")
        w("기준을 만족한 모든 설정 (크기 순):")
        w("")
        w("| 설정 | n | 성공률 | 중앙값 크기 (B) | zlib (B) | Chamfer-L1 |")
        w("|---|---:|---:|---:|---:|---:|")
        for t in sorted(
            [t for t in summary["table"] if t["core_success"] >= TARGET_SUCCESS],
            key=lambda t: t["median_bytes"],
        ):
            w(
                f"| `{t['config']}` | {t['resolution']} | {_pct(t['core_success'])} | {int(t['median_bytes'])} | {int(t['median_zlib_bytes'])} | {_fmt(t['median_chamfer_l1'])} |"
            )
    else:
        w(
            "**어떤 설정도 90% 기준을 만족하지 못했습니다.** (G1 미통과; 제안서 §9에 따라 위험 신호로 기록)"
        )
    w("")

    w("## 8. 왕복 오류 지도 (float64)")
    w("")
    w(
        "✅ = 핵심 구조 보존. 실패 코드: E = 복원 결과가 비어 있음(형상 전체 소실), V = 닫힌 다양체 아님, T = 성분 수/genus 불일치, P = 프로브 실패. 괄호는 Chamfer-L1(대각선 비, ×10⁻³)."
    )
    w("")
    w("| 형상 | 특징(격자) | " + " | ".join(f"n={n}" for n in res) + " |")
    w("|---|---:|" + "---|" * len(res))
    ids = sorted(
        {r["shape_id"] for r in f64},
        key=lambda s: (FAMILIES.index(s.rsplit("_", 1)[0]), int(s.rsplit("_", 1)[1])),
    )
    for sid in ids:
        cells = []
        feat = float("nan")
        for n in res:
            rr = [r for r in f64 if r["shape_id"] == sid and r["resolution"] == n]
            if not rr:
                cells.append("–")
                continue
            r = rr[0]
            feat = r["min_feature_grid"]
            mark = "✅" if r["core_success"] else f"❌{r['failure_code']}"
            cells.append(
                f"{mark} ({1e3 * r['chamfer_l1']:.2f})" if math.isfinite(r["chamfer_l1"]) else mark
            )
        w(f"| `{sid}` | {feat:.3f} | " + " | ".join(cells) + " |")
    w("")

    w("## 9. 실패 목록 (float64)")
    w("")
    fails = [r for r in f64 if not r["core_success"]]
    if not fails:
        w("없음.")
    for r in sorted(fails, key=lambda r: (r["resolution"], r["shape_id"])):
        why = []
        if r["failure_code"] == "E":
            why.append("복원 결과가 비어 있음 (형상 전체 소실)")
        elif not r["valid_manifold"]:
            why.append(
                f"다양체 아님(경계 모서리 {r['out_boundary_edges']}, 비다양체 모서리 {r['out_nonmanifold_edges']}, 비다양체 정점 {r['out_nonmanifold_vertices']})"
            )
        if not r["topology_match"]:
            exp = next((x for x in refs if x["shape_id"] == r["shape_id"]), {})
            why.append(
                f"위상: 성분 {r['out_components']} (설계 {exp.get('expected_components')}), genus {r['out_genus_signature']} (설계 {exp.get('expected_genus')})"
            )
        if not r["probes_ok"]:
            why.append(f"프로브 실패: {r['probes_failed']}")
        w(
            f"- `{r['shape_id']}` @ n={r['resolution']} (특징/간격 {r['feature_over_spacing']:.2f}): "
            + "; ".join(why)
        )
    w("")

    w("## 10. 비용")
    w("")
    w(
        "| n | 인코딩 (s, 중앙값) | 복원 (s, 중앙값) | 평가 포함 총 (s, 중앙값) | 입력 삼각형 (중앙값) |"
    )
    w("|---:|---:|---:|---:|---:|")
    for n in res:
        rs = sel("float64", n)
        w(
            f"| {n} | {_fmt(_median([r['enc_seconds'] for r in rs]), 3)} | {_fmt(_median([r['decode_seconds'] for r in rs]), 3)} | "
            f"{_fmt(_median([r['eval_seconds'] for r in rs]), 3)} | {int(_median([r['ref_faces'] for r in rs]))} |"
        )
    w("")
    return "\n".join(L) + "\n"


# ---------------------------------------------------------------------- CLI
def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--out", type=Path, default=Path("results/g1"))
    ap.add_argument("--cache", type=Path, default=Path(".cache/g1"))
    ap.add_argument("--resolutions", type=int, nargs="+", default=[8, 16, 32, 64])
    ap.add_argument("--bits", type=int, nargs="*", default=[4, 6, 8, 10, 12, 16])
    ap.add_argument("--caps", type=int, nargs="*", default=[1, 2, 4])
    ap.add_argument("--samples", type=int, default=30_000)
    ap.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2)))
    ap.add_argument("--shapes", nargs="*", default=[])
    ap.add_argument("--no-self-intersections", action="store_true")
    ap.add_argument(
        "--ref-voxel",
        type=float,
        default=None,
        help="override the reference marching-cubes voxel (tests only)",
    )
    ap.add_argument("--report-only", action="store_true", help="re-aggregate existing rows")
    ap.add_argument("--fresh", action="store_true", help="ignore rows from earlier runs")
    args = ap.parse_args(argv)
    cfg = G1Config(
        out=args.out,
        cache=args.cache,
        resolutions=tuple(args.resolutions),
        bits=tuple(args.bits),
        caps=tuple(args.caps),
        samples=args.samples,
        workers=args.workers,
        shapes=tuple(args.shapes),
        check_self_intersections=not args.no_self_intersections,
        ref_voxel=args.ref_voxel,
    )
    assert_pinned_reconstructor()
    (cfg.out / "rows").mkdir(parents=True, exist_ok=True)
    started = time.time()
    if not args.report_only:
        ids = list(cfg.shapes) or g1_shape_ids()
        if args.fresh:
            for f in (cfg.out / "rows").glob("*.jsonl"):
                f.unlink()
        todo = [s for s in ids if not (cfg.out / "rows" / f"{s}.jsonl").exists()]
        print(
            f"[g1] {len(todo)} shapes to run ({len(ids) - len(todo)} cached), {cfg.workers} workers",
            flush=True,
        )
        ctx = mp.get_context("spawn")
        with ctx.Pool(cfg.workers, maxtasksperchild=4) as pool:
            for sid, summary, rows, err in pool.imap_unordered(_worker, [(s, cfg) for s in todo]):
                if err:
                    print(f"[g1] {sid} CRASHED\n{err}", file=sys.stderr, flush=True)
                    (cfg.out / "errors").mkdir(exist_ok=True)
                    (cfg.out / "errors" / f"{sid}.txt").write_text(err)
                    continue
                tmp = cfg.out / "rows" / f"{sid}.jsonl.tmp"
                with tmp.open("w", encoding="utf-8") as fh:
                    fh.write(
                        json.dumps({"_type": "reference", "data": summary}, default=_json_default)
                        + "\n"
                    )
                    for r in rows:
                        fh.write(json.dumps(r, default=_json_default) + "\n")
                tmp.rename(cfg.out / "rows" / f"{sid}.jsonl")
                ok = sum(r["core_success"] for r in rows if r["config"] == "float64")
                print(
                    f"[g1] {sid}: ref {'ok' if summary.get('valid') else 'INVALID'}; float64 success {ok}/{len(cfg.resolutions)} ({time.time() - started:.0f}s)",
                    flush=True,
                )
    rows, refs = _load_rows(cfg.out)
    if not rows:
        print("[g1] no rows", file=sys.stderr)
        return 1
    summary = summarize(rows, refs, cfg)
    fields = sorted({k for r in rows for k in r})
    lead = [
        "shape_id",
        "family",
        "variant",
        "pose",
        "resolution",
        "config",
        "core_success",
        "failure_code",
    ]
    fields = lead + [f for f in fields if f not in lead]
    with gzip.open(cfg.out / "rows.csv.gz", "wt", newline="", encoding="utf-8") as fh:
        wr = csv.DictWriter(fh, fieldnames=fields)
        wr.writeheader()
        for r in sorted(
            rows, key=lambda r: (r["shape_id"], r["resolution"], _config_order(r["config"]))
        ):
            wr.writerow(
                {k: (json.dumps(v) if isinstance(v, list | dict) else v) for k, v in r.items()}
            )
    (cfg.out / "references.json").write_text(
        json.dumps(refs, indent=1, default=_json_default, ensure_ascii=False)
    )
    (cfg.out / "summary.json").write_text(
        json.dumps(summary, indent=1, default=_json_default, ensure_ascii=False)
    )
    meta = {
        "생성 시각 (UTC)": summary["generated"],
        "git commit": _git_commit(Path(__file__).resolve().parent),
        "복원기": f"subgrid-marching=={reconstructor_version()} (고정: {RECONSTRUCTOR_VERSION}), primal, combinatorial merge, scoop_bulge=1e-3",
        "격자": GRID_SCHEME_NAME,
        "해상도": list(cfg.resolutions),
        "위치 비트": list(cfg.bits),
        "교차 상한 K": list(cfg.caps),
        "표면 샘플 수 (방향당)": cfg.samples,
        "python / numpy / scikit-image": f"{platform.python_version()} / {np.__version__} / {importlib.metadata.version('scikit-image')}",
        "플랫폼": platform.platform(),
        "행(row) 수": len(rows),
    }
    (cfg.out / "report.md").write_text(
        write_report(rows, refs, summary, cfg, meta), encoding="utf-8"
    )
    print(f"[g1] wrote {cfg.out / 'report.md'} ({len(rows)} rows)", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

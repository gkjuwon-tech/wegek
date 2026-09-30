# G2 선택 진단 보고서 — Jev가 좋은 후보를 고르는가

> 자동 생성 문서입니다 (`python -m jevsg.experiments.g2 report`).

## 0. 사전 고정한 통과 기준

실제 후보 집합(real)에서 Jev L2가 선택한 후보의 핵심 구조 성공률이 무작위·R1·R2 각각보다 높고, 문제 단위 paired bootstrap 95% 신뢰구간이 0을 포함하지 않으며, 이 조건이 두 선택지 순서(p0, p1) 모두에서 성립하면 G2 통과. (Jev 호출 전에 고정한 기준)

## 1. 문제 집합

- 형상 24개(G1과 시드가 겹치지 않는 `g2_selection` 분할), 국소 문제 **240개**, 격자 n=64, 숨긴 블록 3×3×3칸.
- 실제 후보 수: 평균 6.3개 (최소 3, 최대 8). 후보 풀: 블록마다 전체 후보 중 교차가 적은 16개 + 나머지에서 고르게 16개를 복원해 보고, 효과가 다른 대표를 선택.
- 정답 구조가 실제 후보에 자연히 포함된 비율: 40.8%
- **후보 안에 핵심 구조를 보존하는 답이 하나라도 있는 비율**(후보 생성기의 상한): 실제 87.1%, 진단 87.5%
- 층(분석용, 선택자에게는 비공개): easy 58, hard 139, thin 43

## 2. 실제 후보 집합 (정답 강제 포함 없음) — 주 결과

| 선택자 | 핵심 구조 성공 | 최적 선택 | 국소 오차 후회(칸) | 비고 |
|---|---:|---:|---:|---|
| 무작위(기댓값) | **29.6%** | 39.1% | 0.041 |  |
| R1 교차 최소 | **75.0%** | 85.8% | 0.015 |  |
| R2 가장 단순한 물체 | **80.8%** | 92.5% | 0.011 |  |
| Jev L0 (숫자만) | **63.7%** | 74.0% | 0.019 | 순서 p0 63.7% / p1 63.7% |
| Jev L1 (+주변 구조) | **49.4%** | 59.0% | 0.023 | 순서 p0 49.2% / p1 49.6% |
| Jev L2 (+효과 요약) | **70.2%** | 80.4% | 0.020 | 순서 p0 70.8% / p1 69.6% |
| 후보 중 최선 (상한) | **87.1%** | 100.0% | 0.000 |  |

## 3. 진단 집합 (정답 구조 강제 포함) — 선택 능력의 상한

| 선택자 | 핵심 구조 성공 | 최적 선택 | 국소 오차 후회(칸) | 비고 |
|---|---:|---:|---:|---|
| 무작위(기댓값) | **34.5%** | 38.3% | 0.052 |  |
| R1 교차 최소 | **75.0%** | 69.2% | 0.031 |  |
| R2 가장 단순한 물체 | **80.8%** | 77.5% | 0.025 |  |
| Jev L0 (숫자만) | **63.5%** | 62.9% | 0.033 | 순서 p0 63.7% / p1 63.3% |
| Jev L1 (+주변 구조) | **54.4%** | 55.6% | 0.036 | 순서 p0 53.8% / p1 55.0% |
| Jev L2 (+효과 요약) | **71.0%** | 70.8% | 0.031 | 순서 p0 70.8% / p1 71.2% |
| 후보 중 최선 (상한) | **87.5%** | 100.0% | 0.000 |  |

## 4. 통과 판정 (실제 집합, 문제 단위 paired 비교)

| 비교 | 순서 | 차이(성공률) | 95% CI | Jev 우세 / 열세 문제 | 부호검정 p |
|---|---|---:|---|---:|---:|
| Jev L2 vs 무작위(기댓값) | p0 | +41.3%p | [+36.0, +46.4] ✅ | 170 / 39 | 1.07e-20 |
| Jev L2 vs 무작위(기댓값) | p1 | +40.0%p | [+34.7, +45.3] ✅ | 167 / 42 | 7.71e-19 |
| Jev L2 vs R1 교차 최소 | p0 | -4.2%p | [-10.0, +1.2] ❌ | 19 / 29 | 0.193 |
| Jev L2 vs R1 교차 최소 | p1 | -5.4%p | [-11.2, +0.4] ❌ | 20 / 33 | 0.0984 |
| Jev L2 vs R2 가장 단순한 물체 | p0 | -10.0%p | [-15.0, -5.4] ❌ | 6 / 30 | 6.96e-05 |
| Jev L2 vs R2 가장 단순한 물체 | p1 | -11.2%p | [-16.3, -6.2] ❌ | 7 / 34 | 2.53e-05 |

**판정: G2 미통과** (기준은 0장).

## 5. 문맥 수준별 비교 (제거 실험 §8.3)

| 수준 | 실제 집합 성공 | 진단 집합 성공 | 두 순서 선택 일치율 | 평균 confidence |
|---|---:|---:|---:|---:|
| Jev L0 (숫자만) | 63.7% | 63.5% | 43.1% | 0.18 |
| Jev L1 (+주변 구조) | 49.4% | 54.4% | 69.2% | 0.24 |
| Jev L2 (+효과 요약) | 70.2% | 71.0% | 62.1% | 0.38 |

## 6. 계열별 (실제 집합, 핵심 구조 성공률)

| 계열 | 무작위(기댓값) | R1 교차 최소 | R2 가장 단순한 물체 | Jev L0 (숫자만) | Jev L1 (+주변 구조) | Jev L2 (+효과 요약) | 후보 중 최선 (상한) |
|---|---:|---:|---:|---:|---:|---:|---:|
| cup | 34.1% | 77.5% | 100.0% | 68.8% | 62.5% | 90.0% | 100.0% |
| helmet | 25.3% | 70.0% | 75.0% | 53.8% | 40.0% | 66.2% | 75.0% |
| holed_plate | 18.2% | 42.5% | 50.0% | 41.2% | 22.5% | 50.0% | 50.0% |
| multi_part | 36.2% | 100.0% | 100.0% | 91.2% | 77.5% | 98.8% | 100.0% |
| ring | 27.0% | 85.0% | 85.0% | 67.5% | 42.5% | 96.2% | 97.5% |
| thin_shell | 36.6% | 75.0% | 75.0% | 60.0% | 51.2% | 20.0% | 100.0% |

## 7. 보정(calibration): Jev L2가 고른 후보의 확률 vs 실제 성공 (실제+진단)

| 선택 확률 구간 | 사례 수 | 실제 성공률 |
|---|---:|---:|
| 0.00–0.40 | 268 | 52.6% |
| 0.40–0.60 | 517 | 77.4% |
| 0.60–0.80 | 160 | 78.1% |
| 0.80–0.95 | 15 | 80.0% |
| 0.95–1.00 | 0 | – |

## 8. 비용

- 요청 600회 (캐시 적중 120), 입력 토큰 2,165,410, 출력 토큰 185,832 (무료), 비용 **$0.0909**, 재시도 0회.
- 요청당 평균 지연 0.37s, 요청당 평균 입력 토큰 3609.
- 모델: `jev-1.13.0` (버전 고정). 한 요청 = 한 문제·한 문맥 수준에서 실제/진단 × 두 순서, 네 질문.

## 9. Jev L2와 R2가 갈린 문제 (실제 집합, 순서 p0)

- `cup_100#b6` — R2만 성공. 조건: "A drinking mug with a single handle; it is open at the top so it can hold coffee."
- `cup_103#b1` — R2만 성공. 조건: "A plain tumbler cup without a handle; it is open at the top so it can hold liquid."
- `cup_103#b3` — R2만 성공. 조건: "A plain tumbler cup without a handle; it is open at the top so it can hold liquid."
- `cup_103#b9` — R2만 성공. 조건: "A plain tumbler cup without a handle; it is open at the top so it can hold liquid."
- `helmet_101#b1` — R2만 성공. 조건: "A thin-walled helmet shell, open at the bottom for a head, with two eye slits cut through the front and a thin crest fin on top."
- `helmet_101#b4` — R2만 성공. 조건: "A thin-walled helmet shell, open at the bottom for a head, with two eye slits cut through the front and a thin crest fin on top."
- `helmet_103#b5` — R2만 성공. 조건: "A thin-walled helmet shell, open at the bottom for a head, with three eye slits cut through the front and a thin crest fin on top."
- `multi_part_101#b1` — R2만 성공. 조건: "Three separate solid parts in a row with small gaps between them; no parts touch."
- `ring_100#b1` — Jev만 성공. 조건: "A single thin ring, like a torus-shaped band, with an open hole in the middle."
- `ring_100#b3` — Jev만 성공. 조건: "A single thin ring, like a torus-shaped band, with an open hole in the middle."
- `ring_100#b5` — Jev만 성공. 조건: "A single thin ring, like a torus-shaped band, with an open hole in the middle."
- `ring_100#b8` — Jev만 성공. 조건: "A single thin ring, like a torus-shaped band, with an open hole in the middle."
- `ring_101#b1` — Jev만 성공. 조건: "A single thin ring, like a torus-shaped band, with an open hole in the middle."
- `thin_shell_100#b7` — Jev만 성공. 조건: "A completely closed hollow ball with a thin wall and an empty sealed space inside."
- `thin_shell_101#b5` — R2만 성공. 조건: "A thin-walled round bowl, open at the top."
- `thin_shell_101#b7` — R2만 성공. 조건: "A thin-walled round bowl, open at the top."
- `thin_shell_101#b9` — R2만 성공. 조건: "A thin-walled round bowl, open at the top."
- `thin_shell_102#b0` — R2만 성공. 조건: "A hollow ball with a thin wall and one round opening into the empty inside."
- `thin_shell_102#b1` — R2만 성공. 조건: "A hollow ball with a thin wall and one round opening into the empty inside."
- `thin_shell_102#b2` — R2만 성공. 조건: "A hollow ball with a thin wall and one round opening into the empty inside."
- `thin_shell_102#b3` — R2만 성공. 조건: "A hollow ball with a thin wall and one round opening into the empty inside."
- `thin_shell_102#b4` — R2만 성공. 조건: "A hollow ball with a thin wall and one round opening into the empty inside."
- `thin_shell_102#b5` — R2만 성공. 조건: "A hollow ball with a thin wall and one round opening into the empty inside."
- `thin_shell_102#b6` — R2만 성공. 조건: "A hollow ball with a thin wall and one round opening into the empty inside."
- `thin_shell_102#b7` — R2만 성공. 조건: "A hollow ball with a thin wall and one round opening into the empty inside."
- `thin_shell_102#b8` — R2만 성공. 조건: "A hollow ball with a thin wall and one round opening into the empty inside."
- `thin_shell_102#b9` — R2만 성공. 조건: "A hollow ball with a thin wall and one round opening into the empty inside."
- `thin_shell_103#b1` — R2만 성공. 조건: "A hollow ball with a thin wall and two round openings into the empty inside."
- `thin_shell_103#b2` — R2만 성공. 조건: "A hollow ball with a thin wall and two round openings into the empty inside."
- `thin_shell_103#b3` — R2만 성공. 조건: "A hollow ball with a thin wall and two round openings into the empty inside."
- `thin_shell_103#b4` — R2만 성공. 조건: "A hollow ball with a thin wall and two round openings into the empty inside."
- `thin_shell_103#b5` — R2만 성공. 조건: "A hollow ball with a thin wall and two round openings into the empty inside."
- `thin_shell_103#b6` — R2만 성공. 조건: "A hollow ball with a thin wall and two round openings into the empty inside."
- `thin_shell_103#b7` — R2만 성공. 조건: "A hollow ball with a thin wall and two round openings into the empty inside."
- `thin_shell_103#b8` — R2만 성공. 조건: "A hollow ball with a thin wall and two round openings into the empty inside."
- `thin_shell_103#b9` — R2만 성공. 조건: "A hollow ball with a thin wall and two round openings into the empty inside."

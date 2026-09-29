# jevsg — Jev × Subgrid 교차 좌표 연구 코드

기획서: [`docs/proposal.md`](docs/proposal.md) — *Learning-Free Decision-Based 3D Generation in Subgrid Edge Coordinates*

이 디렉터리는 기획서의 실험 단계(G0–G5)를 순서대로 구현합니다. **현재 구현 범위는 G1(왕복)** 입니다.

| 단계 | 내용 | 상태 |
|---|---|---|
| G0 | 문헌 경계 | 기획서의 조사 결과 유지. 이번 작업에서는 저자 구현 검토만 추가 ([`docs/G1_design.md` §1](docs/G1_design.md)) |
| **G1** | **3D → A → 3D 표현 손실** | **완료 · 통과** — 결과 [`results/g1/report.md`](results/g1/report.md), 해석 [`docs/G1_findings.md`](docs/G1_findings.md) |
| G2–G5 | Jev 선택 진단 · 부분 완성 · 완전 생성 · 복잡 형상 | 미착수 |

## G1 결과 요약

48개 구조 형상(컵·고리·얇은 쉘·구멍 난 판·다중 부품·투구 × 8)을 A로 바꿨다가 저자 복원기로 되살린 결과:

| 격자 n | 핵심 구조 보존 | 자기교차 없음 | A 크기 중앙값 (`q4` / zlib) |
|---:|---:|---:|---:|
| 8 | 25.0% | 100% | 0.9 KB / 0.4 KB |
| 16 | 45.8% | 100% | 4.9 KB / 1.4 KB |
| 32 | 77.1% | 100% | 21.2 KB / 4.3 KB |
| **64** | **100%** | 100% | **88.9 KB / 14.7 KB** |

* 기획서 G1 기준(선정 예산에서 ≥ 90%) **통과**: 최소 예산 `q4`(위치 4비트) @ n=64.
* 컵의 커피 공간·손잡이 통로·속빈 공 내부는 다중 교차 A에서 **한 번도 메워지지 않음**. 실패는 주로 격자보다 얇은
  벽의 가짜 터널, 얇은 관의 파편화, 좁은 틈의 병합.
* 다중 교차를 모서리당 1개로 줄이면(제거 실험 8.1) 격자보다 얇은 구조의 보존율이 거의 0으로 떨어짐.
* 우리 인코더는 저자 파이프라인이 짝수합을 지킨 경우 180/180 면 단위 일치, 나머지 12건은 저자 쪽 float32 오차.

## 무엇이 들어 있나

```
src/jevsg/
  grid.py            저자 구현과 비트 단위로 같은 5-사면체 정합 격자, 전역 모서리 id
  predicates.py      정확 기하 술어(float 필터 + 벡터화 정확 산술) + 기호적 섭동
  encode.py          메쉬 → A  (정확한 모서리 교차; 닫힌 입력이면 even-sum 보장)
  representation.py  A 자료구조, 불변식 검증, 위치 양자화, 교차 상한 K, SGEA 직렬화
  decode.py          A → 메쉬  (고정 버전 subgrid-marching==1.0.0 primal 복원기)
  topology.py        다양체성·성분·genus·방향성
  metrics.py         정확 점-삼각형 거리, Chamfer/F-score/Hausdorff, 감김수, 부피
  selfintersect.py   정확 술어 자기교차 검사
  evaluate.py        G1 판정("핵심 구조 성공")과 모든 지표
  shapes/            48개 절차적 시험 형상(설계 위상 + 공기/재료 프로브), 기준 메쉬 생성·검증
  experiments/g1.py  G1 실행기 (재개 가능, 보고서 자동 생성)
tests/               101개 테스트
docs/                기획서, G1 설계 노트, G1 결과 해석
results/g1/          G1 결과 (report.md, rows.csv.gz, summary.json, references.json)
```

## 핵심 설계 결정 (자세한 근거는 [`docs/G1_design.md`](docs/G1_design.md))

1. **복원기는 새로 만들지 않는다.** 저자 공개 패키지를 버전 고정해 명시적 입력 형식으로 A를 넘긴다.
2. **격자는 저자 것과 비트 단위로 같다.** 그래서 우리 인코더의 A를 저자 end-to-end 파이프라인 출력과
   면 단위로 대조할 수 있다.
3. **인코더는 정확하다.** 모든 교차 판정이 float64 입력에 대한 정확한 부호이고, 퇴화는 "격자 전체의 무한소
   평행이동" 하나로 일관되게 해소된다. 닫힌 메쉬면 A의 모든 사면체 면이 짝수 교차를 가진다(증명 스케치 + 테스트).
4. **구조는 프로브로 판정한다.** 컵의 커피 공간, 손잡이 통로, 틈, 공동이 공기로 남았는지를 감김수로 확인한다.
   Chamfer가 낮아도 커피 공간이 메워졌으면 실패다.
5. **A 크기는 실제 바이트다.** 헤더와 격자 식별을 포함한 직렬화 결과를 잰다.

## 실행

```bash
pip install -e ".[dev]"
ruff check . && ruff format --check . && mypy && pytest -q

python -m jevsg.experiments.g1 --workers 4          # 전체 G1 (4코어 기준 수십 분)
python -m jevsg.experiments.g1 --shapes cup_0 ring_3 --resolutions 16 32
python -m jevsg.experiments.g1 --report-only        # rows/ 로부터 보고서 재생성
```

```python
from jevsg import TetGrid
from jevsg.encode import encode_mesh
from jevsg.decode import decode_primal
from jevsg.mesh import load_obj, weld, fit_normalization, normalize

mesh = weld(load_obj("cup.obj"))
mesh = normalize(mesh, fit_normalization(mesh.vertices))  # [-0.98, 0.98]^3
grid = TetGrid(32)
A, stats = encode_mesh(mesh, grid)  # A: EdgeCoordinates
out = decode_primal(A, grid).mesh  # 복원 메쉬
```

## 라이선스·출처

* 복원기: `subgrid-marching` (MIT) — Baktash, Gillespie, Crane, *Subgrid Marching Tetrahedra*, ACM TOG 45(4), 2026.
* 시험 형상은 모두 코드로 생성하므로 외부 데이터 라이선스 문제가 없습니다.

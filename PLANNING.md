# WEGEK: AI 3D Website Factory

## "씹고퀄 웹사이트를 공장처럼 찍어내는 기계"

> **한 줄 요약:** 사용자가 "나 이런 사이트 만들어줘" 하면, AI가 기획 → 이미지 생성 → 3D 모델링 → 리깅/애니메이션 → GLSL 배경 셰이더 → 조명/카메라 연출 → DOM 조합 → 렌더링 확인 → 개선 루프까지 전부 자동으로 돌려서 씹고퀄 3D 웹사이트를 뽑아내는 파이프라인 도구.

> **현실 인식:** 2026년 현재, AI가 "Three.js + GSAP + 커스텀 GLSL + 수작업 3D 모델링"을 한방에 뽑는 건 불가능함.
> 근데 각각의 단계를 전문 AI 도구에 위임하고, 오케스트레이터 AI가 조립하면? **가능함.** 이게 WEGEK의 핵심 아이디어.

---

## 목차

1. [왜 이게 되는가 (시장 분석)](#1-왜-이게-되는가)
2. [파이프라인 아키텍처 (전체 흐름)](#2-파이프라인-아키텍처)
3. [Stage 0: 기획 AI — "뭘 만들지 정하기"](#3-stage-0-기획-ai)
4. [Stage 1: 이미지 생성 — "레퍼런스 이미지 뽑기"](#4-stage-1-이미지-생성)
5. [Stage 2: 3D 모델 생성 — "이미지 → 3D 오브젝트"](#5-stage-2-3d-모델-생성)
6. [Stage 3: 리깅 & 애니메이션 — "움직이게 만들기"](#6-stage-3-리깅--애니메이션)
7. [Stage 4: GLSL 배경 셰이더 — "배경을 살려라"](#7-stage-4-glsl-배경-셰이더)
8. [Stage 5: 씬 조립 — "조명, 카메라, 키프레임"](#8-stage-5-씬-조립)
9. [Stage 6: DOM & 프론트엔드 — "웹사이트 완성"](#9-stage-6-dom--프론트엔드)
10. [Stage 7: 렌더링 확인 & 개선 루프](#10-stage-7-렌더링-확인--개선-루프)
11. [도구 선정 최종 결론](#11-도구-선정-최종-결론)
12. [비용 산정](#12-비용-산정)
13. [경쟁 분석](#13-경쟁-분석)
14. [로드맵](#14-로드맵)
15. [위험 요소 & 대응](#15-위험-요소--대응)

---

## 1. 왜 이게 되는가

### 현재 AI 웹사이트 빌더의 한계

Framer AI, Webflow AI, Relume, Lovable, Bolt — 다 있음. 근데 이것들이 뽑는 건 뭐냐?

**플랫한 2D 웹사이트.**

Tailwind으로 깔끔하게 정리된, 그래 예쁘긴 한데... **Apple.com 급의 3D 스크롤 인터랙션?** 절대 못 만듦.
**Nike.com 급 제품 회전 3D 뷰어?** 꿈도 못 꿈.
**Three.js + GSAP + ScrollTrigger로 카메라가 움직이면서 오브젝트가 등장하는 그 영화 같은 경험?** ㅋㅋ 그건 에이전시가 3개월 걸려서 만드는 거임. 최소 5천만원.

**여기가 블루오션이다.**

### 왜 지금 가능한가

| 2024년 | 2026년 |
|---------|---------|
| Image-to-3D 퀄리티 쓰레기 | Tripo P1, Rodin Gen-2.5, Hunyuan3D 2.1 — 프로덕션급 |
| 리깅은 사람이 해야 함 | Tripo Auto-Rig: 인간, 동물, 로봇, 사물 — 3분 컷 |
| GLSL은 전문가 영역 | ShaderGPT (14islands): 자연어 → 라이브 GLSL, 2400+ 커뮤니티 셰이더 |
| 3D 애니메이션 자동화 불가 | Meshy 500+ 프리셋, Tripo Retarget (quadruped/hexapod/aquatic까지), afk.ai (뼈 없는 메시도 자동 리깅) |
| 이미지 생성 불안정 | FLUX.2 (multi-reference 10장, 캐릭터 일관성), Imagen 3 ($0.03/장) |
| 웹 렌더링 자동 녹화 불가 | puppeteer-capture (CDP deterministic frame capture), Xvfb + ffmpeg |

**각 스테이지의 도구가 프로덕션 레벨에 도달했다.** 이제 필요한 건 이걸 하나로 엮는 오케스트레이터뿐이다.

---

## 2. 파이프라인 아키텍처

```
사용자 입력: "Nike Air Max 랜딩페이지 만들어줘, 신발이 공중에서 회전하면서 분해되고 재조립되는 느낌"

┌─────────────────────────────────────────────────────────────────────┐
│  STAGE 0: PLANNER AI (Claude/GPT)                                   │
│  → 사이트 구조 기획, 섹션 분리, 3D 오브젝트 목록 정의               │
│  → Output: site_plan.json                                           │
│     {                                                               │
│       sections: [                                                   │
│         { id: "hero", objects: ["shoe_main", "shoe_sole", ...],     │
│           camera: "orbit_zoom_in", lighting: "dramatic_rim" },      │
│         { id: "features", objects: ["shoe_mesh_cutaway"], ... }     │
│       ],                                                            │
│       background_shader: "gradient_noise_dark_dynamic",             │
│       color_palette: ["#1a1a2e", "#e94560", "#0f3460"]             │
│     }                                                               │
└──────────────────────────┬──────────────────────────────────────────┘
                           │
            ┌──────────────┼──────────────┐
            ▼              ▼              ▼
┌──────────────┐ ┌──────────────┐ ┌──────────────┐
│ STAGE 1      │ │ STAGE 1      │ │ STAGE 1      │
│ Image Gen    │ │ Image Gen    │ │ Image Gen    │   ← 오브젝트별 병렬
│ (FLUX.2)     │ │ (FLUX.2)     │ │ (FLUX.2)     │
│ shoe_main    │ │ shoe_sole    │ │ shoe_mesh    │
└──────┬───────┘ └──────┬───────┘ └──────┬───────┘
       ▼                ▼                ▼
┌──────────────┐ ┌──────────────┐ ┌──────────────┐
│ STAGE 2      │ │ STAGE 2      │ │ STAGE 2      │
│ Image→3D     │ │ Image→3D     │ │ Image→3D     │   ← 3D 모델 생성 병렬
│ (Tripo P1)   │ │ (Tripo P1)   │ │ (Tripo P1)   │
└──────┬───────┘ └──────┬───────┘ └──────┬───────┘
       ▼                ▼                ▼
┌──────────────┐ ┌──────────────┐ ┌──────────────┐
│ STAGE 3      │ │ STAGE 3      │ │ STAGE 3      │
│ Rig+Animate  │ │ Rig+Animate  │ │ Rig+Animate  │   ← 리깅/애니 병렬
│ (Tripo/afk)  │ │ (Tripo/afk)  │ │ (Tripo/afk)  │
└──────┬───────┘ └──────┬───────┘ └──────┬───────┘
       │                │                │
       └────────────────┼────────────────┘
                        ▼
              ┌──────────────────┐
              │ STAGE 4          │
              │ GLSL Background  │   ← ShaderGPT / ShaderToy MCP
              │ Shader Gen       │
              └────────┬─────────┘
                       ▼
              ┌──────────────────┐
              │ STAGE 5          │
              │ Scene Assembly   │   ← Three.js 씬: 조명 프리셋 매핑,
              │ (AI Orchestrator)│     카메라 경로, 키프레임, ScrollTrigger
              └────────┬─────────┘
                       ▼
              ┌──────────────────┐
              │ STAGE 6          │
              │ DOM + Frontend   │   ← HTML/CSS 오버레이, 폰트, 카피,
              │ Code Gen         │     R3F 컴포넌트, GSAP ScrollTrigger
              └────────┬─────────┘
                       ▼
              ┌──────────────────┐
              │ STAGE 7          │
              │ Render VM        │   ← Puppeteer 녹화, 스크린샷 비교,
              │ Review Loop      │     AI 시각 평가 → 개선 루프
              └──────────────────┘
                       ▼
              ✅ 최종 배포 패키지 (Vercel/Cloudflare Pages)
```

---

## 3. Stage 0: 기획 AI

### 뭘 하는가

사용자의 자연어 요청을 받아서 **구조화된 사이트 플랜**으로 변환.

```
사용자: "고급 시계 브랜드 랜딩 만들어줘. 시계가 돌아가면서 부품이 보이고,
         스크롤하면 시계가 손목에 착용되는 느낌"

AI 출력:
{
  "project_name": "CHRONOS_LANDING",
  "sections": [
    {
      "id": "hero",
      "type": "3d_product_showcase",
      "objects": [
        {
          "id": "watch_body",
          "description": "luxury silver watch body, front view, clean studio lighting",
          "animation": "slow_rotation_y",
          "needs_parts_separation": true
        },
        {
          "id": "watch_movement",
          "description": "exposed watch movement mechanism, gears and springs visible",
          "animation": "mechanical_tick"
        }
      ],
      "camera_preset": "orbit_to_closeup",
      "lighting_preset": "studio_dramatic",
      "background_shader": "dark_gradient_particles",
      "scroll_behavior": "zoom_in_with_rotation"
    },
    {
      "id": "mechanism",
      "type": "3d_exploded_view",
      "trigger": "scroll_50%",
      "animation": "explode_and_reassemble"
    },
    {
      "id": "lifestyle",
      "type": "3d_to_2d_transition",
      "objects": ["watch_on_wrist"],
      "camera_preset": "dolly_out_to_wide",
      "dom_overlay": true
    },
    {
      "id": "specs",
      "type": "dom_section",
      "style": "minimal_grid",
      "copy_tone": "luxury_restrained"
    },
    {
      "id": "cta",
      "type": "dom_section",
      "style": "full_bleed_dark"
    }
  ],
  "global": {
    "color_palette": ["#0a0a0a", "#c9b99a", "#ffffff", "#1a1a1a"],
    "typography": "serif_luxury",
    "scroll_engine": "lenis_gsap",
    "3d_engine": "r3f_drei"
  }
}
```

### 어떻게 만드는가

- **LLM 선택:** Claude Sonnet 4 or GPT-5 — 구조적 JSON 출력에 강함
- **프롬프트 엔지니어링:** 3D 웹사이트 전문 시스템 프롬프트 + 레퍼런스 사이트 DB 
- **레퍼런스 라이브러리:** Awwwards/FWA급 사이트 200개 분석해서 패턴 DB화
  - "product_orbit" → 카메라 오빗 + 배경 블러
  - "scroll_reveal" → 스크롤 트리거 등장
  - "exploded_view" → 부품 분해/조립
  - "lifestyle_transition" → 3D→2D 트랜지션
  - "parallax_depth" → 레이어별 속도 차이

### 핵심 결정사항

| 항목 | 결정 | 이유 |
|------|------|------|
| 기획 LLM | Claude Sonnet 4 | JSON 구조 출력 안정성, 긴 컨텍스트 |
| 출력 포맷 | 커스텀 JSON 스키마 | 다운스트림 파이프라인 자동화에 필수 |
| 레퍼런스 DB | 수동 큐레이션 + 자동 스크래핑 | 초기엔 수동, 점진적 자동화 |

---

## 4. Stage 1: 이미지 생성

### 왜 이미지를 먼저 만드는가

3D 모델 생성 도구들(Tripo, Rodin, Meshy)은 **이미지 입력**이 텍스트 입력보다 퀄리티가 훨씬 높음.
"luxury watch" 텍스트보다 **정확한 레퍼런스 이미지**를 넣으면 3D 출력 퀄리티가 2-3배 점프.

### 도구 비교

| 도구 | 강점 | 약점 | 가격 | 판정 |
|------|------|------|------|------|
| **FLUX.2 [pro]** | 4MP 출력, multi-ref 10장까지, 캐릭터 일관성 최강, 실사급 디테일 | 비쌈 | $0.03/MP | **1순위** |
| **FLUX.2 [max]** | Grounding Search (실시간 웹 검색으로 트렌드 반영), 최고 퀄 | 더 비쌈 | $0.07/MP | 특수 케이스 |
| **FLUX.2 [klein]** | 서브초 생성, 저렴 | 퀄리티 한계 | $0.014+ | 프리뷰/초안용 |
| **Imagen 3** | Google 최강 이미지 모델, $0.03/장 고정, 프롬프트 따라가기 좋음 | API 제한 많음 | $0.03/image | **백업** |
| **Midjourney** | 아트 스타일 최강 | API 불안정, 자동화 어려움 | 구독제 | 수동 보조 |
| **DALL-E 3** | 텍스트 렌더링 잘됨 | 3D 레퍼런스로 쓰기엔 퀄 부족 | API 가격 | 패스 |

### 최종 선택: **FLUX.2 [pro]** (메인) + **Imagen 3** (백업)

**FLUX.2를 선택한 핵심 이유:**

1. **Multi-Reference:** 이미지 10장까지 동시 참조 가능. "이 브랜드 스타일로, 이 각도에서, 이 소재감으로" 정밀 제어
2. **캐릭터/오브젝트 일관성:** 같은 제품을 여러 각도로 뽑을 때 일관성 유지 — 3D 변환 품질에 직결
3. **4MP 해상도:** 고해상도 이미지 → 3D 텍스처 디테일 극대화
4. **서브 10초 생성:** 파이프라인 전체 속도에 기여

### 이미지 생성 전략

```python
# 오브젝트당 3장 생성 (정면, 45도, 측면)
# → 멀티뷰 기반 3D 생성 정확도 극대화

for obj in site_plan.objects:
    images = []
    for angle in ["front_view", "45_degree", "side_view"]:
        prompt = f"""
        {obj.description}, {angle}, 
        isolated on pure white background, 
        studio lighting, 8K product photography,
        no shadows on background
        """
        img = flux2_pro.generate(
            prompt=prompt,
            reference_images=brand_style_refs,  # 브랜드 일관성
            aspect_ratio="1:1"
        )
        images.append(img)
    obj.reference_images = images
```

---

## 5. Stage 2: 3D 모델 생성

### 이게 WEGEK의 핵심이다

여기서 돈냄새가 남. 이미지 → 3D 모델 변환. 2026년 기준 주요 선수들:

### 풀 도구 비교 (존나 디테일)

| 도구 | Geometry 점수 | Texture 점수 | Topology | 속도 | 가격/모델 | API | 특이사항 |
|------|:---:|:---:|:---:|:---:|:---:|:---:|------|
| **Tripo P1** | 9/10 | 8.5/10 | Good | ~10초 | 50 credits | REST | 올인원 가격, 추가 파라미터 서차지 없음, H3 대비 프리미엄 |
| **Tripo H3** | 8.5/10 | 8/10 | Good | ~10초 | 20-30 credits | REST | H2 대비 새로운 퀄리티 컨트롤, `generate_parts` 지원 |
| **Rodin Gen-2.5** | 9.5/10 | 9/10 | **Excellent** | ~2분 | 0.5-1 credit | REST | 에디터블 토폴로지 최강, UV/PBR 분리 완벽, Blender/Maya 호환 최고 |
| **Meshy 6** | 8/10 | 8/10 | Good | ~90초 | 20-30 credits | REST | 게임 에셋에 최적화, 넓은 토폴로지 허용 범위 |
| **Hunyuan3D 2.1** | 9/10 | 9/10 | Fair | ~3분 | **무료** (오픈소스) | 셀프호스트 | Tencent 오픈소스, 벤치마크 1위, BUT 셀프호스팅 필요 (A100 GPU) |
| **Luma Genie 1.2** | 7/10 | 6/10 | Poor | ~40초 | $0.30-0.50 | REST | 비디오→3D 특화, 텍스처 낮음, triangle soup |
| **Kaedim** | 8/10 | 8.5/10 | **Excellent** | 수시간 | Per-asset | REST | Human-in-the-loop, 최고 퀄 but 느림 |

### 성능 벤치마크 요약 (2026년 독립 테스트 기반)

```
Geometry Quality (높을수록 좋음):
Rodin Gen-2.5  ████████████████████ 9.5
Hunyuan3D 2.1  ███████████████████  9.0
Tripo P1       ███████████████████  9.0
Meshy 6        ████████████████     8.0
Luma Genie     ██████████████       7.0

Texture Quality:
Rodin Gen-2.5  ██████████████████   9.0
Hunyuan3D 2.1  ██████████████████   9.0
Tripo P1       █████████████████    8.5
Meshy 6        ████████████████     8.0
Luma Genie     ████████████         6.0

Speed (빠를수록 좋음):
Tripo P1       ████████████████████ ~10s
Luma Genie     ████████████████     ~40s
Meshy 6        ██████████████       ~90s
Rodin Gen-2.5  ██████████           ~120s
Hunyuan3D 2.1  ████████             ~180s
```

### 최종 선택: **Tripo P1** (메인) + **Rodin Gen-2.5** (고퀄 필요시)

**Tripo P1을 1순위로 선택한 이유:**

1. **속도:** ~10초. 파이프라인에서 10개 오브젝트 병렬 돌리면 전부 합쳐서 15초면 끝남
2. **올인원 API:** Image-to-3D → Rig → Animate → Export가 하나의 API 체인. 다른 도구 조합 안 해도 됨
3. **멀티뷰 입력:** 3장의 레퍼런스 이미지를 동시에 넣으면 정확도가 크게 향상
4. **Parts Generation:** `generate_parts=true`로 오브젝트를 자동 분리 — 시계 본체/밴드/다이얼 따로 뽑기 가능
5. **Non-humanoid 지원:** 로봇, 동물, 사물, 기계 — 다 됨. 경쟁사 중 가장 넓은 범위

**Rodin Gen-2.5를 백업으로 둔 이유:**

- **토폴로지가 깨끗함.** Blender에서 추가 편집이 필요한 경우 Rodin 에셋이 압도적
- **PBR 채널 분리** (Albedo, Normal, Roughness, Metallic) — 조명 반응이 사실적
- **Creative Mode:** Gen-2.5-Medium/High에서 활성화 가능, 프롬프트 해석이 유연해짐

### Hunyuan3D — "무료인데 왜 안 쓰나?"

쓴다. **셀프호스팅 옵션으로.** 대량 생산 시 크레딧 비용 절감용.
- A100 GPU 1대면 자체 서버 운영 가능
- 퀄리티 벤치마크는 Tripo/Rodin과 대등하거나 우위
- BUT: 인프라 관리 오버헤드, 리깅/애니메이션 파이프라인은 별도 구축 필요
- **전략:** MVP는 Tripo API → 스케일업 단계에서 Hunyuan3D 셀프호스팅으로 전환하면서 비용 최적화

---

## 6. Stage 3: 리깅 & 애니메이션

### 이게 진짜 핵심 중의 핵심이다

3D 모델이 그냥 떡하니 서 있으면 웹사이트가 아니라 박물관임. **움직여야 한다.**

문제는: 우리가 만드는 건 캐릭터가 아님. **제품**임. 신발, 시계, 자동차, 가구.
"사람이 걷는" 애니메이션 프리셋은 쓸모가 없음. **신발끈이 풀리는, 시계 바늘이 돌아가는, 자동차 문이 열리는** 애니메이션이 필요함.

### 애니메이션 도구 대결

#### 1. Tripo Retarget API

**지원 범위가 미침:**
- `preset:idle`, `preset:walk`, `preset:run` — 기본 바이페드
- `preset:quadruped:walk` — 사족보행 (개, 고양이, 말)
- `preset:hexapod:walk` — 육족보행 (곤충)
- `preset:octopod:walk` — 팔족보행 (문어, 거미)
- `preset:serpentine:march` — 뱀형
- `preset:aquatic:march` — 수중 생물

**Rig Type도 다양:**
- `biped`, `quadruped`, `hexapod`, `octopod`, `avian`, `serpentine`, `aquatic`, `others`

장점:
- Image-to-3D → Rig → Retarget이 **하나의 task_id 체인**으로 연결
- 3분 컷. 제품 하나당 리깅+애니메이션 3분
- 비인간형도 꽤 잘 처리 (2026 StraySpark 비교 테스트에서 비인간형 1위)

단점:
- **커스텀 애니메이션 불가.** 프리셋만 가능. "신발끈이 풀리는" 같은 건 안 됨
- Facial weight가 약함 (클로즈업 대사 장면 X — 근데 우린 제품 사이트니까 상관없음)
- 기계/제품 오브젝트 전용 애니메이션은 아직 없음

**점수: 8/10** (바이페드/동물) / **5/10** (제품/기계)

#### 2. Meshy Animation API

**500개 이상 프리셋 라이브러리:**
- Walk & Run (걷기, 뛰기, 웅크려 걷기, 수영)
- Daily Actions (아이들, 주변 둘러보기, 상호작용, 물건 집기, 운동)
- Fighting (콤보 공격, 방어, 회피)
- Body Movements (춤, 감정 표현, 제스처)

장점:
- 프리셋 수가 압도적 (500+)
- `change_fps`, `fbx2usdz`, `extract_armature` 등 후처리 옵션
- Remesh API로 폴리곤 수 조절 가능 (리깅 전 300K 이하로)

단점:
- **Humanoid 전용.** "표준 인간형 바이페드 + 명확한 팔다리" 필수 조건
- Hip weighting이 약함 (StraySpark 테스트)
- 제품/기계 오브젝트 → **완전 불가**
- UE5 리타겟팅에 추가 매핑 필요

**점수: 9/10** (인간 캐릭터) / **0/10** (제품/기계 — 아예 안 됨)

#### 3. afk.ai — THE DARK HORSE 🐴

이게 존나 흥미로움. **뼈 없는 메시도 자동 리깅.**

```
"Can I animate objects without bones?"
"Yes. Our AI generates rigging from mesh geometry — no skeleton required."

"What types of robots work?"
"All types: industrial arms, humanoids, wheeled, drones, spider-bots, custom designs."

"Multi-part objects?"
"Fully supported. The AI understands parent-child mesh relationships."
```

장점:
- **비캐릭터 3D 오브젝트 애니메이션의 유일한 전문 도구**
- 로봇, 기계, 가구, 차량, 추상 오브젝트 전부 지원
- Mesh geometry 분석으로 자동 관절/articulation point 검출
- 기계적 움직임 (assembly sequences, drone flight, robot arm) 지원
- **무료.** 가입도 필요없음
- GLB/GLTF 입출력

단점:
- API 문서가 아직 정식 공개 안 됨 (웹 에디터 기반)
- 프로덕션 파이프라인 통합에 추가 작업 필요
- 애니메이션 퀄리티가 Cascadeur급은 아님

**점수: 6/10** (인간 캐릭터) / **8/10** (제품/기계 — 여기선 유일무이)

#### 4. Cascadeur — "장인의 도구"

물리 기반 키프레임 애니메이션 소프트웨어. AI-assisted posing.

장점:
- **물리적 사실성 최강.** AutoPhysics로 자연스러운 모션 자동 보정
- Animation Unbaking — 베이크된 모캡 데이터를 편집 가능하게 변환
- FBX/DAE/USD 호환
- Free 티어 존재 (CASC 포맷 전용)

단점:
- **자동화 불가.** GUI 전용. API 없음. CLI 없음
- 사람이 직접 포즈 잡아야 함
- Indie $96/년, Pro $396/년

**점수: 10/10** (수동 퀄리티) / **1/10** (자동화 파이프라인 적합성)

### 애니메이션 전략 최종 결론

```
제품/기계 오브젝트 → afk.ai (자동 관절 검출 + 애니메이션)
                   ↓ 퀄리티 부족 시
                   → Three.js 코드 기반 키프레임 (AI가 직접 코드 작성)

캐릭터/생물 → Tripo Retarget (speed + 비인간형 지원)
              ↓ 프리셋 부족 시
              → Meshy Animation (500+ 라이브러리)

최후의 수단 → AI가 Three.js AnimationClip을 직접 코드로 작성
              (position/rotation/scale 키프레임 — AI도 이 정도는 함)
```

### 진짜 비밀 병기: Three.js 코드 기반 애니메이션

솔직히 말하면, 제품 웹사이트에서 필요한 애니메이션의 80%는 이거임:
- 오브젝트 Y축 회전 (제품 쇼케이스)
- 위치 이동 (스크롤 트리거 등장/퇴장)
- 스케일 변화 (확대/축소)
- 분해/조립 (파츠별 position 애니메이션)
- 카메라 돌리/줌/패닝

이건 리깅이 필요없음. **Three.js 키프레임 코드면 충분.** 그리고 AI(Claude/GPT)가 이 수준의 코드는 잘 짬.

```javascript
// AI가 생성하는 코드 예시
const watchAnimation = {
  hero: {
    object: "watch_body",
    keyframes: [
      { time: 0, rotation: { y: 0 }, position: { y: 2 } },
      { time: 2, rotation: { y: Math.PI }, position: { y: 0 } },
      { time: 4, rotation: { y: Math.PI * 2 }, position: { y: 0 } }
    ],
    easing: "power2.inOut"
  },
  scroll_trigger: {
    start: "top top",
    end: "bottom bottom",
    scrub: 1
  }
}
```

---

## 7. Stage 4: GLSL 배경 셰이더

### 왜 GLSL인가

씹고퀄 3D 웹사이트의 배경은 그냥 검정이 아님.
- **입자 시스템** (파티클 노이즈가 천천히 흘러감)
- **그라디언트 노이즈** (컬러가 부드럽게 변하면서 depth 감)
- **와이어프레임 그리드** (테크 느낌)
- **Aurora/Nebula 효과** (프리미엄 감성)
- **마우스 인터랙티브** (커서 따라 반응하는 배경)

이건 CSS gradient로 절대 못 만듦. **Fragment shader (GLSL)** 영역.

### GLSL 전문 AI 도구 비교

#### 1. ShaderGPT (14islands) — **1순위 확정**

스톡홀름+레이캬비크의 크리에이티브 에이전시 14islands가 만든 도구.

**핵심 기능:**
- 자연어 → GLSL fragment shader 실시간 변환
- **7개 LLM 백엔드 지원:** Claude Sonnet 4.5, Claude Opus 4.6, GPT-5, GPT-5.2 Codex, Grok 4, Kimi K2.5, Gemini 3 Pro/Flash, DeepSeek V3.2
- 라이브 WebGL 프리뷰 + 코드 에디터
- 마우스 인터랙션(`u_mouse`) 자동 내장
- **커뮤니티 갤러리 2400+ 셰이더** — 학습/레퍼런스 DB로 활용 가능

**왜 좋은가:**
- 우리 파이프라인에서 배경 셰이더 요청을 ShaderGPT API(또는 같은 LLM + 셰이더 시스템 프롬프트)로 보내면 됨
- 출력이 바로 Three.js `ShaderMaterial`에 꽂을 수 있는 GLSL 코드
- uniform 컨벤션이 표준화됨 (`u_time`, `u_mouse`, `u_resolution`)

**제한사항:**
- 공식 API 없음 (웹 인터페이스만). BUT: 동일한 LLM + 셰이더 프롬프트를 자체 구축 가능
- 일일 무료 생성 14회 제한

#### 2. ShaderToy MCP (wilsonchenghy)

**Claude + ShaderToy 연결:**
- MCP(Model Context Protocol)로 Claude가 ShaderToy 검색/읽기/학습 가능
- 기존 셰이더를 참고해서 더 복잡한 셰이더 생성
- 2400+ 커뮤니티 셰이더 학습 기반

**왜 흥미로운가:**
- ShaderGPT가 "scratch에서 생성"이라면, ShaderToy MCP는 "기존 고퀄 셰이더를 참고해서 변형"
- 볼류메트릭 연기, 리퀴드 파이어, 오션 시뮬레이션 같은 복잡한 효과에 더 강함

#### 3. Img2Shadertoy (hughesdo)

**이미지 → GLSL 변환:**
- SIREN(Sinusoidal Representation Networks) 기반
- 이미지를 수학 함수로 학습시켜 셰이더로 재현
- 오디오 리액티브 4D 셰이더 생성 가능

**용도:** 브랜드 그래픽이나 텍스처를 프로시저럴 셰이더로 변환하고 싶을 때

#### 4. 자체 LLM 셰이더 생성

솔직히 **가장 현실적인 접근:**

```python
SHADER_SYSTEM_PROMPT = """
You are a GLSL fragment shader expert. Write WebGL-compatible 
fragment shaders for Three.js ShaderMaterial.

Rules:
- Use uniforms: u_time (float), u_mouse (vec2), u_resolution (vec2)
- Output to gl_FragColor
- Keep it under 100 lines for performance
- Use noise functions (simplex/perlin) for organic effects
- Mouse interaction: u_mouse.xy normalized to [0,1]
"""

def generate_background_shader(description: str, color_palette: list) -> str:
    prompt = f"""
    Create a GLSL fragment shader for a website background:
    Description: {description}
    Color palette: {color_palette}
    Requirements:
    - Smooth, ambient animation using u_time
    - Subtle mouse reactivity
    - Performance-optimized (mobile-friendly)
    """
    return llm.generate(system=SHADER_SYSTEM_PROMPT, user=prompt)
```

### GLSL 전략 최종 결론

| 용도 | 도구 | 방식 |
|------|------|------|
| 기본 배경 (그라디언트, 노이즈, 파티클) | 자체 LLM + 셰이더 프롬프트 | Claude/GPT가 직접 GLSL 코드 작성 |
| 고퀄 배경 (볼류메트릭, 리퀴드) | ShaderToy MCP + 레퍼런스 | 기존 ShaderToy 셰이더 참고 변형 |
| 브랜드 그래픽 → 셰이더 | Img2Shadertoy | SIREN 기반 이미지→수학 변환 |
| 셰이더 프리셋 라이브러리 | 자체 큐레이션 | ShaderGPT 갤러리 + ShaderToy에서 30개 엄선 |

**핵심 인사이트:** GLSL 셰이더는 사실 AI가 **가장 잘하는** 영역 중 하나임. 왜냐? 셰이더는:
- 짧음 (보통 50-150줄)
- 수학적 (sin, cos, noise — LLM이 좋아함)
- 독립적 (다른 코드와 의존성 없음)
- 즉시 검증 가능 (렌더링하면 바로 보임)

---

## 8. Stage 5: 씬 조립

### "조명, 카메라, 액션!"

3D 오브젝트 + 애니메이션 + 배경 셰이더가 준비되면, 이걸 하나의 씬으로 조립해야 함.

### 조명 프리셋 시스템

**왜 프리셋인가:**
AI한테 "조명 짜줘"라고 하면 개판남. 대신 **프로가 세팅한 조명 프리셋 10개**를 미리 만들어놓고 AI한테 고르게 하면 됨.

```javascript
const LIGHTING_PRESETS = {
  "studio_dramatic": {
    // 3-point lighting: 드라마틱한 제품 촬영 느낌
    key: { type: "spot", intensity: 2.5, angle: 0.5, position: [3, 5, 2], color: "#fff5e6" },
    fill: { type: "area", intensity: 0.8, position: [-3, 3, 2], color: "#e6f0ff" },
    rim: { type: "point", intensity: 1.2, position: [0, 2, -3], color: "#ffd4a3" },
    ambient: { intensity: 0.15 }
  },
  
  "studio_soft": {
    // 소프트박스 느낌: 뷰티/패션 제품
    key: { type: "area", intensity: 1.5, width: 4, height: 4, position: [2, 4, 3] },
    fill: { type: "area", intensity: 1.0, width: 3, height: 3, position: [-2, 3, 2] },
    ambient: { intensity: 0.3 }
  },
  
  "neon_cyber": {
    // 네온 사이버펑크: 테크/게이밍 제품
    key: { type: "point", intensity: 3.0, position: [3, 2, 0], color: "#ff00ff" },
    secondary: { type: "point", intensity: 2.5, position: [-3, 2, 0], color: "#00ffff" },
    rim: { type: "spot", intensity: 1.5, position: [0, 5, -2], color: "#ffffff" },
    ambient: { intensity: 0.05, color: "#0a0020" }
  },
  
  "golden_hour": {
    // 골든아워: 라이프스타일/럭셔리
    key: { type: "directional", intensity: 2.0, position: [5, 3, 2], color: "#ffb347" },
    fill: { type: "hemisphere", skyColor: "#ffcc80", groundColor: "#4a3520", intensity: 0.6 },
    ambient: { intensity: 0.2, color: "#1a1000" }
  },
  
  "minimal_white": {
    // 미니멀 화이트: Apple 스타일
    key: { type: "area", intensity: 1.0, width: 10, height: 10, position: [0, 5, 0] },
    fill: { type: "hemisphere", skyColor: "#ffffff", groundColor: "#f0f0f0", intensity: 0.8 },
    ambient: { intensity: 0.5 }
  },
  
  "dark_moody": {
    // 다크 무디: 프리미엄 주류/향수
    key: { type: "spot", intensity: 3.0, angle: 0.3, position: [2, 6, 1], color: "#ffeedd" },
    ambient: { intensity: 0.02, color: "#000000" }
  },
  
  "outdoor_natural": {
    // 아웃도어 자연광: 스포츠/아웃도어 제품
    key: { type: "directional", intensity: 1.5, position: [10, 10, 5], color: "#fff8f0" },
    fill: { type: "hemisphere", skyColor: "#87ceeb", groundColor: "#8b7355", intensity: 0.7 },
    ambient: { intensity: 0.3 }
  },
  
  "showcase_rim": {
    // 림 라이트 강조: 자동차/전자제품
    rim_front: { type: "area", intensity: 0.3, position: [0, 0, 5] },
    rim_left: { type: "spot", intensity: 2.0, position: [-4, 2, 0], color: "#ffffff" },
    rim_right: { type: "spot", intensity: 2.0, position: [4, 2, 0], color: "#ffffff" },
    ambient: { intensity: 0.08 }
  },
  
  "editorial_contrast": {
    // 에디토리얼: 패션/매거진 느낌
    key: { type: "spot", intensity: 4.0, angle: 0.2, position: [1, 8, 3], color: "#ffffff" },
    accent: { type: "point", intensity: 1.0, position: [-2, 1, -1], color: "#ff3366" },
    ambient: { intensity: 0.05 }
  },
  
  "warm_cozy": {
    // 따뜻한 아늑함: 가구/인테리어
    key: { type: "point", intensity: 1.5, position: [2, 3, 2], color: "#ffd699" },
    fill: { type: "area", intensity: 0.8, position: [-1, 4, 1], color: "#fff0dd" },
    accent: { type: "point", intensity: 0.5, position: [0, 0, -2], color: "#ff9966" },
    ambient: { intensity: 0.25, color: "#1a0f00" }
  }
};
```

### AI 자동 매핑 로직

```python
def auto_map_lighting(object_category: str, brand_mood: str) -> str:
    """AI가 오브젝트 카테고리 + 브랜드 무드에 맞는 조명 프리셋을 선택"""
    mapping = {
        ("tech", "premium"): "minimal_white",
        ("tech", "gaming"): "neon_cyber",
        ("fashion", "luxury"): "editorial_contrast",
        ("fashion", "casual"): "studio_soft",
        ("auto", "any"): "showcase_rim",
        ("watch", "luxury"): "dark_moody",
        ("food", "warm"): "warm_cozy",
        ("sports", "outdoor"): "outdoor_natural",
        ("furniture", "cozy"): "warm_cozy",
        ("beauty", "editorial"): "studio_dramatic",
    }
    # 정확한 매치 없으면 AI가 가장 가까운 프리셋 선택
    return mapping.get((object_category, brand_mood), ai_select_best_preset(...))
```

### 카메라 프리셋

```javascript
const CAMERA_PRESETS = {
  "orbit_showcase": {
    // 제품 360도 회전 뷰
    type: "orbit",
    target: [0, 0, 0],
    distance: 5,
    autoRotate: true,
    autoRotateSpeed: 0.5,
    enableDamping: true
  },
  
  "scroll_dolly": {
    // 스크롤에 따라 카메라가 다가감
    type: "path",
    keyframes: [
      { scroll: 0, position: [0, 2, 10], lookAt: [0, 0, 0] },
      { scroll: 0.5, position: [3, 1, 5], lookAt: [0, 0, 0] },
      { scroll: 1, position: [0, 0.5, 2], lookAt: [0, 0, 0] }
    ],
    easing: "power2.inOut"
  },
  
  "cinematic_reveal": {
    // 영화적 등장: 블랙에서 점점 밝아지면서 제품 등장
    type: "animated",
    duration: 3,
    keyframes: [
      { time: 0, position: [0, 0, 0.5], fov: 90, fog: 1.0 },
      { time: 1.5, position: [0, 1, 3], fov: 60, fog: 0.3 },
      { time: 3, position: [0, 1.5, 5], fov: 45, fog: 0.0 }
    ]
  },
  
  "top_down_to_perspective": {
    // 탑다운에서 퍼스펙티브로 전환
    type: "path",
    keyframes: [
      { scroll: 0, position: [0, 15, 0], lookAt: [0, 0, 0], fov: 30 },
      { scroll: 0.5, position: [5, 8, 5], lookAt: [0, 0, 0], fov: 40 },
      { scroll: 1, position: [3, 2, 6], lookAt: [0, 0, 0], fov: 50 }
    ]
  }
};
```

---

## 9. Stage 6: DOM & 프론트엔드

### 기술 스택

```
React 18 + TypeScript
├── React Three Fiber (R3F)     ← Three.js를 React 컴포넌트로
│   └── @react-three/drei       ← 유틸리티 (Environment, Float, Text3D...)
├── GSAP + ScrollTrigger        ← 스크롤 애니메이션 엔진
│   └── Lenis                   ← 스무스 스크롤
├── Tailwind CSS                ← 유틸리티 스타일링
├── Vite                        ← 빌드
└── Draco / KTX2 / Basis        ← 3D 에셋 압축
```

**왜 이 스택인가:**

| 선택 | 이유 |
|------|------|
| R3F over vanilla Three.js | React 컴포넌트 기반 = AI가 코드 생성하기 훨씬 쉬움 |
| GSAP over Framer Motion | ScrollTrigger 생태계, 프로덕션 검증, 3D 통합 성숙 |
| Lenis over native scroll | 부드러운 스크롤 = 3D 씬 전환이 영화처럼 느껴짐 |
| Tailwind over styled-components | AI 코드 생성에 유리, 인라인으로 의도 명확 |
| Drei | View 컴포넌트 (하나의 캔버스에 여러 3D 섹션), Float, Environment 프리셋 |

### "AI가 만든 티 안 나게" — 오픈소스 스킬 연결

핵심 전략: **R3F/Three.js 커뮤니티에서 검증된 패턴과 컴포넌트를 미리 수집**

```
오픈소스 레퍼런스 라이브러리:
├── codrops 예제 (tympanus.net)
│   ├── scroll-driven-3d-world (Three.js + GSAP)
│   ├── one-canvas-multi-section (Drei View)
│   └── 3d-product-showcase
├── R3F 에코시스템
│   ├── drei (공식 헬퍼)
│   ├── react-three-next (Next.js 보일러플레이트)
│   └── lamina (셰이더 레이어)
├── GSAP 예제
│   ├── ScrollTrigger 3D demos
│   └── Observer snap-scroll
└── 커뮤니티 프로젝트
    ├── virtuoso-3d-web-showcase (R3F + GSAP 랜딩)
    ├── LUME (시네마틱 제품 쇼케이스 + R3F + GSAP + Cloudflare R2)
    └── threeview-product-3d-landings (SaaS 3D 랜딩)
```

**AI가 코드 생성할 때 이 레퍼런스를 컨텍스트로 넣으면, 아웃풋이 "사람이 짠" 느낌으로 나옴.**

### DOM 오버레이 전략

```jsx
// AI가 생성하는 코드 구조
<LenisProvider>
  <Canvas>
    <View.Port />  {/* 모든 3D 섹션의 렌더 포트 */}
  </Canvas>
  
  {/* Section 1: Hero - 3D 배경 + DOM 오버레이 */}
  <section className="h-screen relative">
    <View className="absolute inset-0">
      <HeroScene />  {/* 3D 오브젝트 + 조명 + 배경 셰이더 */}
    </View>
    <div className="relative z-10 flex flex-col justify-center h-full px-12">
      <h1 className="text-8xl font-serif">CHRONOS</h1>
      <p className="text-xl text-gray-400 mt-4">Time, Engineered.</p>
    </div>
  </section>
  
  {/* Section 2: Features - 스크롤 트리거 */}
  <section className="h-[200vh]">
    <View className="sticky top-0 h-screen">
      <ExplodedViewScene />
    </View>
  </section>
  
  {/* Section 3: CTA - 순수 DOM */}
  <section className="h-screen bg-black flex items-center justify-center">
    <button className="px-8 py-4 border border-white text-white hover:bg-white hover:text-black transition">
      Pre-Order Now
    </button>
  </section>
</LenisProvider>
```

---

## 10. Stage 7: 렌더링 확인 & 개선 루프

### "만들고 보고 고치고"

웹사이트가 만들어졌으면 **AI가 직접 확인**해야 함. 렌더링 VM에서.

### 아키텍처

```
┌────────────────────────┐
│  Render VM             │
│  (Docker/Xvfb)         │
│                        │
│  1. Vite dev server    │
│     localhost:5173     │
│                        │
│  2. Puppeteer/CDP      │
│     ├── 스크린샷 캡처  │
│     ├── 스크롤 시뮬     │
│     └── 비디오 녹화     │
│                        │
│  3. puppeteer-capture  │
│     (deterministic     │
│      frame capture)    │
└───────────┬────────────┘
            │
            ▼
┌────────────────────────┐
│  Vision AI 평가        │
│  (Claude Vision /      │
│   GPT-4V)              │
│                        │
│  체크리스트:           │
│  □ 3D 오브젝트 렌더링  │
│  □ 텍스처 품질         │
│  □ 조명 자연스러움     │
│  □ 스크롤 애니메이션   │
│  □ DOM 가독성          │
│  □ 모바일 반응형       │
│  □ 로딩 성능           │
│  □ 전체적 "고퀄" 느낌  │
└───────────┬────────────┘
            │
            ▼
     Pass? ──Yes──→ ✅ 배포
      │
      No
      │
      ▼
┌────────────────────────┐
│  개선 루프             │
│                        │
│  AI가 문제점 분석 후   │
│  해당 스테이지로 복귀: │
│                        │
│  "텍스처 흐림"         │
│  → Stage 1 재생성      │
│    (더 고해상도 이미지) │
│                        │
│  "조명 부자연스러움"   │
│  → Stage 5 프리셋 교체 │
│                        │
│  "배경 너무 심심"      │
│  → Stage 4 셰이더 변경 │
│                        │
│  "DOM 겹침"            │
│  → Stage 6 레이아웃 수정│
└────────────────────────┘
```

### 녹화 도구

| 도구 | 방식 | 강점 | 약점 |
|------|------|------|------|
| **puppeteer-capture** | CDP `HeadlessExperimental.beginFrame` | **결정론적** 프레임 캡처, 재현 가능, 프레임 퍼펙트 | Linux/Windows만, `waitForTimeout`으로 가상 시간 제어 |
| **Puppeteer screencast** | `page.screencast()` API | 간편, 공식 API | 실시간 기반이라 프레임 일관성 부족 |
| **Xvfb + ffmpeg** | X11 가상 디스플레이 녹화 | 실제 브라우저 동작 그대로 캡처, 오디오 포함 | 셋업 복잡, 비결정론적 |

**선택: puppeteer-capture** (결정론적) + Xvfb+ffmpeg (최종 데모 영상)

---

## 11. 도구 선정 최종 결론

### 확정된 메인 스택

| 파이프라인 단계 | 1순위 (확정) | 2순위 (백업/보완) | 왜 이걸 골랐나 |
|:---:|:---:|:---:|---|
| **기획** | Claude Sonnet 4 | GPT-5 | JSON 구조 출력 안정성, 긴 컨텍스트 |
| **이미지 생성** | FLUX.2 [pro] | Imagen 3 | 4MP, multi-ref 10장, 캐릭터/오브젝트 일관성 |
| **3D 모델 생성** | Tripo P1 | Rodin Gen-2.5 | 속도 ~10초, 올인원 파이프라인, parts gen |
| **리깅 (캐릭터)** | Tripo Auto-Rig | Meshy Rigging | 비인간형 최강, 3분 컷 |
| **리깅 (제품/기계)** | afk.ai | Three.js 코드 | 뼈없는 메시 자동 리깅, 유일무이 |
| **애니메이션 (캐릭터)** | Tripo Retarget | Meshy (500+) | quadruped/hexapod/aquatic 지원 |
| **애니메이션 (제품)** | Three.js 키프레임 | afk.ai | AI가 코드로 직접 작성, 커스텀 자유도 |
| **GLSL 배경** | 자체 LLM + 셰이더 프롬프트 | ShaderToy MCP | AI가 GLSL 잘 짬, 프리셋 라이브러리 |
| **씬 조립** | AI (Claude) + 프리셋 | 수동 보정 | 조명/카메라 10개 프리셋, AI가 선택 |
| **프론트엔드** | R3F + GSAP + Lenis + Tailwind | — | 프로덕션 검증 스택, AI 코드젠에 최적 |
| **렌더링 확인** | puppeteer-capture | Xvfb + ffmpeg | 결정론적 프레임 캡처 |
| **시각 평가** | Claude Vision | GPT-4V | 스크린샷 분석 → 개선 피드백 |
| **배포** | Vercel / Cloudflare Pages | — | R3F/Next.js 최적화, CDN 글로벌 |

### "Tripo보다 퀄 좋은 게 있나?" — 질문에 대한 답변

**있다. Rodin Gen-2.5.** 토폴로지 퀄리티와 PBR 분리에서 Rodin이 확실히 우위.

BUT:
- Rodin은 느림 (2분 vs Tripo 10초)
- Rodin은 리깅/애니메이션 API가 없음 (별도 구축 필요)
- Rodin은 parts generation이 Tripo만큼 통합적이지 않음
- Rodin은 가격이 enterprise 급

**파이프라인 효율 관점에서 Tripo P1이 압도적 최적해.** 토폴로지 퀄이 부족한 특수 케이스(Blender 후가공 필요 에셋)에만 Rodin 사용.

**Hunyuan3D 2.1**은 스케일업 시 비용 최적화 카드로 보유. A100 인프라 확보 후 전환.

### "애니메이션 전문 ML이 Tripo/Meshy에 있는데 성능 어떤가?"

**Tripo:**
- Rig v2.5가 non-biped에 추천됨 (quadruped, hexapod, octopod, avian, serpentine, aquatic)
- Retarget 프리셋은 16종 + 100+ biped 확장
- **성능:** StraySpark 2026 비교에서 "비인간형 1위", UE5 리타겟 "가장 깔끔"
- **한계:** 커스텀 모션 불가, 프리셋 의존

**Meshy:**
- 500+ 프리셋 (Walk, Run, Fight, Daily, Body)
- **성능:** 폭넓은 토폴로지 허용, 프로토타이핑에 최강
- **한계:** Humanoid 전용. 제품/기계 = 불가. Hip weighting 약함

**결론:** 캐릭터 = Tripo > Meshy, 제품/기계 = afk.ai + Three.js 코드

### "GLSL 전문 AI 더 있나?"

**ShaderGPT (14islands)**가 현재 가장 완성된 버티컬. 근데 API가 없어서 자체 구축해야 함.

추가 옵션:
- **ShaderToy MCP:** Claude가 기존 셰이더 학습해서 생성. 복잡한 효과에 강함
- **Img2Shadertoy:** 이미지→셰이더 변환 (SIREN). 틈새 용도
- **자체 LLM:** 솔직히 이게 제일 현실적. Claude/GPT에 셰이더 전문 시스템 프롬프트 넣으면 80%는 바로 쓸 수 있는 GLSL 나옴

---

## 12. 비용 산정

### 사이트 1개 생성 비용 (오브젝트 5개 기준)

| 단계 | 도구 | 크레딧/비용 | 설명 |
|------|------|----------:|------|
| 이미지 생성 | FLUX.2 pro | $0.45 | 5개 오브젝트 × 3장(멀티뷰) × $0.03/MP |
| 3D 모델 생성 | Tripo P1 | 250 credits | 5개 × 50 credits |
| 리깅+애니메이션 | Tripo Rig+Retarget | 175 credits | 5개 × (25 rig + 10 retarget) |
| GLSL 셰이더 | Claude API | ~$0.10 | 1-2회 셰이더 생성 |
| 씬/코드 생성 | Claude API | ~$0.50 | 전체 프론트엔드 코드 |
| 렌더링 확인 | VM + Vision | ~$0.30 | 스크린샷 5장 분석 |
| **합계** | | **~$1.35 + 425 Tripo credits** | |

Tripo 크레딧 기준: 1000 credits ≈ $10 (대량 구매 시)
→ 425 credits ≈ **$4.25**

**사이트 1개 생성 총 비용: 약 $6.10 (원가)**

### 가격 모델 (판매)

| 티어 | 가격 | 포함 | 타겟 |
|------|------|------|------|
| **Basic** | $49 | 3D 오브젝트 3개, 3 섹션, 1 revision | 스타트업/인디 |
| **Pro** | $149 | 3D 오브젝트 8개, 5 섹션, 3 revisions | 에이전시 |
| **Enterprise** | $499 | 무제한 오브젝트, 커스텀, 전담 지원 | 대형 브랜드 |

**마진율:**
- Basic: $49 - $6 = **$43 마진 (88%)**
- Pro: $149 - $15 = **$134 마진 (90%)**
- Enterprise: $499 - $40 = **$459 마진 (92%)**

**이 마진율 실화냐? ㅋㅋㅋㅋㅋ**

에이전시한테 3D 웹사이트 맡기면 3천만원~1억임. 우리가 $149에 뽑아줌. 퀄리티 80%만 맞춰도 이건 게임 끝.

---

## 13. 경쟁 분석

### 현재 시장

| 경쟁자 | 하는 것 | 안 하는 것 |
|--------|---------|-----------|
| **Framer AI** | 2D 웹사이트 자동 생성 | 3D 없음 |
| **Webflow AI** | 2D 웹사이트 + CMS | 3D 없음 |
| **Relume AI** | 와이어프레임 → 2D 사이트 | 3D 없음 |
| **Lovable/Bolt** | AI 코딩 → 웹앱 | 3D/디자인 없음 |
| **Spline** | 3D 웹 에디터 (수동) | AI 자동 생성 없음 |
| **Readymag** | 디자인 중심 웹 빌더 | 3D 없음 |

**아무도 "AI로 3D 웹사이트를 자동 생성"을 안 하고 있음.**

Spline이 가장 가까운데, Spline은 **수동 에디터**지 자동 생성 아님.
"3D 오브젝트를 자동 생성하고, 자동으로 웹사이트에 배치하고, 배경 셰이더까지 자동" — 이 파이프라인을 가진 서비스는 **0개.**

### 해자 (Moat)

1. **파이프라인 통합:** 10개 도구를 하나로 엮는 오케스트레이터는 쉽게 복제 못 함
2. **프리셋 라이브러리:** 조명/카메라/셰이더 프리셋은 시간 투자 → 점점 누적
3. **레퍼런스 DB:** Awwwards급 사이트 분석 데이터
4. **개선 루프:** Vision AI 피드백 루프의 품질은 사용할수록 향상
5. **선점 효과:** 이 시장을 첫 번째로 장악하면 "3D 웹사이트 = WEGEK"

---

## 14. 로드맵

### Phase 1: Foundation (4주)

```
Week 1-2: Core Pipeline
├── [ ] site_plan.json 스키마 확정
├── [ ] Planner AI 프롬프트 엔지니어링
├── [ ] FLUX.2 API 연동 + 멀티뷰 생성
├── [ ] Tripo P1 API 연동 (Image→3D→Rig→Retarget)
└── [ ] 기본 Three.js 키프레임 애니메이션 코드젠

Week 3-4: Assembly & Preview
├── [ ] GLSL 셰이더 생성 모듈
├── [ ] 조명/카메라 프리셋 10세트
├── [ ] R3F 코드 생성 (씬 조립)
├── [ ] DOM 오버레이 생성
├── [ ] puppeteer-capture 렌더링 확인
└── [ ] Vision AI 평가 + 개선 루프 v0
```

### Phase 2: Quality (4주)

```
Week 5-6: Polish
├── [ ] Rodin Gen-2.5 백업 파이프라인
├── [ ] afk.ai 연동 (제품 오브젝트 애니메이션)
├── [ ] ShaderToy MCP 통합 (고급 셰이더)
├── [ ] 셰이더 프리셋 라이브러리 30개 큐레이션
└── [ ] 레퍼런스 사이트 DB 50개

Week 7-8: Scale
├── [ ] Meshy Animation 백업 연동
├── [ ] 브랜드 스타일 일관성 시스템
├── [ ] 멀티 페이지 지원
├── [ ] 배포 자동화 (Vercel/CF Pages)
└── [ ] 비용 최적화 (Hunyuan3D 셀프호스팅 테스트)
```

### Phase 3: Product (4주)

```
Week 9-10: User-Facing
├── [ ] 웹 인터페이스 (사용자 입력 → 결과물)
├── [ ] 실시간 프리뷰 시스템
├── [ ] 결제 연동 (Stripe)
└── [ ] 사용자 피드백 → 리비전 시스템

Week 11-12: Launch
├── [ ] 랜딩 페이지 (WEGEK 자체로 만든 3D 사이트)
├── [ ] 베타 사용자 10명 테스트
├── [ ] 성능 최적화 (Lighthouse 90+)
└── [ ] Product Hunt / Hacker News 런칭
```

---

## 15. 위험 요소 & 대응

| 위험 | 확률 | 영향 | 대응 |
|------|:----:|:----:|------|
| 3D 모델 퀄리티 불안정 | 중 | 높음 | Rodin 백업, 멀티뷰 이미지 전략, 개선 루프 |
| GLSL 셰이더 모바일 성능 | 높음 | 중 | 모바일 전용 간소화 셰이더 + fallback 그라디언트 |
| API 서비스 장애 | 낮음 | 높음 | 모든 스테이지에 백업 도구 배치 완료 |
| Tripo/Rodin 가격 인상 | 중 | 중 | Hunyuan3D 셀프호스팅 전환 준비 |
| "AI가 만든 티" | 중 | 높음 | 오픈소스 레퍼런스 스킬 라이브러리, 수동 후가공 옵션 |
| 법적 이슈 (3D 모델 저작권) | 낮음 | 높음 | AI 생성 에셋 라이선스 확인, 상업용 API만 사용 |
| 렌더링 확인 루프 무한 반복 | 중 | 중 | 최대 3회 반복 제한, 기준 점수 설정 |

---

## Appendix A: "씹고퀄"의 정의

우리가 말하는 "씹고퀄"은 Awwwards SOTD(Site of the Day) 수준을 의미함.

체크리스트:
- [ ] 3D 오브젝트 텍스처 해상도 2K 이상
- [ ] 부드러운 60fps 스크롤 애니메이션
- [ ] 커스텀 GLSL 배경 (CSS gradient 금지)
- [ ] 프로페셔널 3-point 조명
- [ ] 스크롤 기반 카메라 움직임
- [ ] 반응형 (데스크탑 + 모바일)
- [ ] Lighthouse Performance 85+
- [ ] 커스텀 타이포그래피
- [ ] 마이크로 인터랙션 (호버, 커서)
- [ ] 페이드 인/아웃 트랜지션

---

## Appendix B: 프리셋 조명과 오브젝트 자동 매핑 테이블

| 카테고리 | 예시 제품 | 1순위 조명 | 2순위 조명 | 배경 셰이더 |
|----------|----------|-----------|-----------|------------|
| 테크/가전 | 스마트폰, 노트북, 이어폰 | minimal_white | showcase_rim | gradient_noise_minimal |
| 럭셔리 시계 | 롤렉스, 오메가 | dark_moody | studio_dramatic | dark_particle_drift |
| 자동차 | 포르쉐, 테슬라 | showcase_rim | neon_cyber | volumetric_fog_dark |
| 스니커즈/신발 | 나이키, 아디다스 | studio_dramatic | neon_cyber | color_burst_dynamic |
| 뷰티/향수 | 샤넬, 디올 | editorial_contrast | golden_hour | silk_gradient_warm |
| 가구/인테리어 | 소파, 조명 | warm_cozy | studio_soft | warm_noise_organic |
| 스포츠/아웃도어 | 등산화, 텐트 | outdoor_natural | studio_dramatic | sky_gradient_dynamic |
| 푸드/음료 | 커피, 와인 | warm_cozy | golden_hour | bokeh_light_warm |
| 패션/의류 | 재킷, 드레스 | editorial_contrast | studio_soft | abstract_flow_monochrome |
| 게이밍 | 키보드, 마우스, 헤드셋 | neon_cyber | showcase_rim | matrix_rain_modified |

---

## Appendix C: 기술적 세부사항 — API 연동 예시

### Tripo P1 풀 파이프라인

```python
import httpx

TRIPO_API = "https://api.tripo3d.ai/v2/openapi"
TRIPO_KEY = "..."

async def generate_3d_asset(image_urls: list[str], animation: str = "preset:idle"):
    """이미지 → 3D → 리깅 → 애니메이션 풀 파이프라인"""
    
    # Step 1: Multiview Image → 3D Model
    resp = await httpx.post(f"{TRIPO_API}/task", json={
        "type": "multiview_to_model",
        "model_version": "p1.0-20250601",
        "files": [{"type": "jpg", "url": url} for url in image_urls],
        "texture_quality": "detailed",
        "generate_parts": True,  # 파츠 분리 자동화
    }, headers={"Authorization": f"Bearer {TRIPO_KEY}"})
    model_task_id = resp.json()["data"]["task_id"]
    
    # Step 2: Wait for model generation (~10s)
    model = await wait_for_task(model_task_id)
    
    # Step 3: Auto-Rig
    resp = await httpx.post(f"{TRIPO_API}/task", json={
        "type": "auto_rig",
        "original_model_task_id": model_task_id,
    }, headers={"Authorization": f"Bearer {TRIPO_KEY}"})
    rig_task_id = resp.json()["data"]["task_id"]
    rig = await wait_for_task(rig_task_id)
    
    # Step 4: Retarget Animation
    resp = await httpx.post(f"{TRIPO_API}/task", json={
        "type": "animate_retarget",
        "original_model_task_id": rig_task_id,
        "animation": animation,
        "out_format": "glb",
    }, headers={"Authorization": f"Bearer {TRIPO_KEY}"})
    anim_task_id = resp.json()["data"]["task_id"]
    result = await wait_for_task(anim_task_id)
    
    return result["output"]["model_url"]  # GLB 다운로드 URL
```

### FLUX.2 Multi-Reference 이미지 생성

```python
import httpx

BFL_API = "https://api.bfl.ai/v1"
BFL_KEY = "..."

async def generate_product_views(description: str, style_refs: list[str]):
    """제품 설명 → 멀티뷰 이미지 3장 생성"""
    angles = [
        "front view, centered, studio lighting",
        "45 degree angle view, three-quarter, studio lighting",
        "side profile view, studio lighting"
    ]
    
    images = []
    for angle in angles:
        resp = await httpx.post(f"{BFL_API}/flux2-pro", json={
            "prompt": f"{description}, {angle}, isolated on white background, 8K",
            "reference_images": style_refs[:8],  # max 8 refs in API
            "aspect_ratio": "1:1",
            "output_format": "png",
        }, headers={"x-key": BFL_KEY})
        
        task_id = resp.json()["id"]
        result = await poll_result(task_id)
        images.append(result["sample"])
    
    return images
```

---

*이 문서는 WEGEK 프로젝트의 v1.0 기획서입니다. 코드 구현은 이 문서의 확정 후 시작합니다.*

*"돈냄새 여기까지 난다" — 진짜 냄새 맡은 거 맞음. 이거 되면 씹고퀄 3D 웹사이트 에이전시 산업이 뒤집어짐.*

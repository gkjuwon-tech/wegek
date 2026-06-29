"""Stage 0 — Planner AI.

Turns a natural-language brief into a structured `SitePlan`. Uses the configured
LLM when available; otherwise a deterministic heuristic planner produces a fully
valid plan so the factory never stalls.
"""
from __future__ import annotations

import re

from ..clients.llm import LLMClient
from ..config import Settings
from ..presets.cameras import CAMERA_PRESETS
from ..presets.lighting import LIGHTING_PRESETS
from ..presets.mapping import map_category, primitive_for
from ..presets.shaders import SHADERS
from ..schemas import GlobalStyle, Object3D, Section, SitePlan

PLANNER_SYSTEM = f"""You are WEGEK's Planner AI, an expert creative director for award-winning
(Awwwards SOTD level) 3D scrollytelling websites built with Three.js + GSAP.

Given a brief, design a structured site plan as JSON with this exact schema:
{{
  "project_name": "UPPER_SNAKE_NAME",
  "tagline": "short punchy tagline",
  "brand_mood": "premium|luxury|gaming|playful|minimal|editorial",
  "global_style": {{
    "color_palette": ["#hex","#hex","#hex","#hex"],   // dark bg first, accent, secondary, light text
    "typography": "modern_sans|serif_luxury|mono_tech|editorial",
    "background_shader": one of {sorted(SHADERS.keys())},
    "accent": "#hex"
  }},
  "objects": [
    {{
      "id": "snake_id",
      "description": "vivid visual description for image/3D generation",
      "category": "tech|watch|auto|sneakers|beauty|furniture|sports|food|fashion|gaming|luxury",
      "animation": "slow_rotation_y|float_bob|explode_reassemble|mechanical_tick|spin_fast",
      "needs_parts_separation": false
    }}
  ],
  "sections": [
    {{
      "id": "hero",
      "type": "3d_product_showcase|3d_exploded_view|3d_to_2d_transition|dom_section",
      "headline": "big headline",
      "subcopy": "supporting line",
      "body": "optional paragraph for dom sections",
      "objects": ["object_id"],
      "camera_preset": one of {sorted(CAMERA_PRESETS.keys())},
      "lighting_preset": one of {sorted(LIGHTING_PRESETS.keys())},
      "scroll_behavior": "zoom_in_with_rotation|reveal|explode|parallax"
    }}
  ]
}}

Rules: 3-5 sections, 1-4 objects. First section is the hero. Always include a final
"dom_section" CTA. Make copy specific to the brief, confident and brand-appropriate."""


CATEGORY_KEYWORDS = {
    "watch": ["watch", "시계", "rolex", "롤렉스", "chronograph", "오메가", "omega"],
    "auto": ["car", "자동차", "차", "vehicle", "porsche", "tesla", "테슬라", "포르쉐", "ev"],
    "sneakers": ["shoe", "sneaker", "신발", "스니커즈", "nike", "나이키", "adidas", "아디다스", "running"],
    "beauty": ["perfume", "향수", "cosmetic", "화장품", "beauty", "뷰티", "serum", "skincare", "스킨케어"],
    "furniture": ["furniture", "가구", "chair", "의자", "sofa", "소파", "lamp", "조명", "interior", "인테리어"],
    "sports": ["sport", "스포츠", "outdoor", "아웃도어", "fitness", "운동", "gym", "bike", "자전거"],
    "food": ["coffee", "커피", "wine", "와인", "food", "음식", "drink", "음료", "beverage", "chocolate"],
    "fashion": ["fashion", "패션", "jacket", "dress", "의류", "clothing", "apparel", "bag", "가방"],
    "gaming": ["gaming", "게이밍", "keyboard", "키보드", "mouse", "headset", "헤드셋", "console", "game"],
    "luxury": ["luxury", "럭셔리", "고급", "premium", "프리미엄", "jewel", "보석", "diamond", "다이아"],
    "tech": ["phone", "스마트폰", "laptop", "노트북", "earbuds", "이어폰", "tech", "테크", "gadget", "device", "ai", "drone"],
}


def detect_category(text: str) -> str:
    low = text.lower()
    best, best_score = "tech", 0
    for cat, kws in CATEGORY_KEYWORDS.items():
        score = sum(1 for kw in kws if kw in low)
        if score > best_score:
            best, best_score = cat, score
    return best


def _slug(text: str) -> str:
    text = re.sub(r"[^a-zA-Z0-9가-힣\s]", "", text)
    words = text.split()[:3]
    base = "_".join(w.upper() for w in words) or "WEGEK_SITE"
    return re.sub(r"[^A-Z0-9_가-힣]", "", base)[:32]


async def run(prompt: str, settings: Settings, *, brand_mood: str | None, max_objects: int) -> tuple[SitePlan, str]:
    """Return (plan, provider_label)."""
    llm = LLMClient(settings)
    if llm.available:
        try:
            data = await llm.complete_json(PLANNER_SYSTEM, f"Brief: {prompt}")
            plan = _coerce_plan(data, prompt, brand_mood, max_objects)
            return plan, llm.label
        except Exception:  # noqa: BLE001 - any LLM/parse failure falls back gracefully
            pass
    return heuristic_plan(prompt, brand_mood, max_objects), "heuristic"


def heuristic_plan(prompt: str, brand_mood: str | None, max_objects: int) -> SitePlan:
    category = detect_category(prompt)
    cfg = map_category(category)
    name = _slug(prompt)
    mood = brand_mood or ("luxury" if category in ("watch", "luxury", "beauty") else "premium")

    n_obj = max(1, min(max_objects, 3))
    obj_descs = [
        f"{category} hero product, premium materials, dramatic studio lighting",
        f"{category} product detail / component close-up, exposed mechanism",
        f"{category} product in lifestyle context, cinematic",
    ]
    anims = ["slow_rotation_y", "explode_reassemble", "float_bob"]
    objects = [
        Object3D(
            id=f"obj_{i+1}",
            description=obj_descs[i],
            category=category,
            animation=anims[i % len(anims)],
            needs_parts_separation=(i == 1),
            primitive=primitive_for(category),
            color=cfg["palette"][1],
        )
        for i in range(n_obj)
    ]

    sections = [
        Section(
            id="hero",
            type="3d_product_showcase",
            headline=name.replace("_", " ").title(),
            subcopy=_tagline_for(category, mood),
            objects=[objects[0].id],
            camera_preset="cinematic_reveal",
            lighting_preset=cfg["lighting"],
            scroll_behavior="zoom_in_with_rotation",
        ),
        Section(
            id="showcase",
            type="3d_product_showcase",
            headline="Engineered to obsess over.",
            subcopy="Every angle considered. Every detail intentional.",
            objects=[objects[0].id],
            camera_preset=cfg["camera"],
            lighting_preset=cfg["lighting"],
            scroll_behavior="reveal",
        ),
    ]
    if n_obj > 1:
        sections.append(
            Section(
                id="mechanism",
                type="3d_exploded_view",
                headline="See what's inside.",
                subcopy="Precision you can feel before you can name it.",
                objects=[objects[1].id],
                camera_preset="scroll_dolly",
                lighting_preset="showcase_rim",
                scroll_behavior="explode",
            )
        )
    sections.append(
        Section(
            id="cta",
            type="dom_section",
            headline="Make it yours.",
            subcopy="Built to last. Designed to be remembered.",
            body="Join the people who refuse to settle for flat.",
            objects=[],
            camera_preset="static_hero",
            lighting_preset=cfg["lighting"],
            scroll_behavior="reveal",
            dom_overlay=True,
        )
    )

    return SitePlan(
        project_name=name,
        tagline=_tagline_for(category, mood),
        brand_mood=mood,
        sections=sections,
        objects=objects,
        global_style=GlobalStyle(
            color_palette=cfg["palette"],
            background_shader=cfg["shader"],
            accent=cfg["palette"][1],
            typography="serif_luxury" if mood in ("luxury",) else "modern_sans",
        ),
    )


def _tagline_for(category: str, mood: str) -> str:
    table = {
        "watch": "Time, engineered.",
        "auto": "Motion, perfected.",
        "sneakers": "Built for the next step.",
        "beauty": "Beauty in every wavelength.",
        "furniture": "Form that holds you.",
        "sports": "Outperform yesterday.",
        "food": "Crafted to savour.",
        "fashion": "Wear the future.",
        "gaming": "Enter the arena.",
        "luxury": "Quietly extraordinary.",
        "tech": "The future, in your hands.",
    }
    return table.get(category, "Designed to be remembered.")


def _coerce_plan(data: dict, prompt: str, brand_mood: str | None, max_objects: int) -> SitePlan:
    """Validate LLM output into a SitePlan, repairing missing presets."""
    plan = SitePlan.model_validate(
        {
            "project_name": data.get("project_name") or _slug(prompt),
            "tagline": data.get("tagline", ""),
            "brand_mood": brand_mood or data.get("brand_mood", "premium"),
            "global_style": data.get("global_style", {}),
            "objects": data.get("objects", [])[:max_objects],
            "sections": data.get("sections", []),
        }
    )
    if not plan.objects or not plan.sections:
        return heuristic_plan(prompt, brand_mood, max_objects)

    # repair invalid presets / fill procedural hints
    for obj in plan.objects:
        if not obj.primitive:
            obj.primitive = primitive_for(obj.category)
        if not obj.color:
            obj.color = plan.global_style.accent
    if plan.global_style.background_shader not in SHADERS:
        plan.global_style.background_shader = map_category(plan.objects[0].category)["shader"]
    valid_obj_ids = {o.id for o in plan.objects}
    for sec in plan.sections:
        if sec.lighting_preset not in LIGHTING_PRESETS:
            sec.lighting_preset = "studio_dramatic"
        if sec.camera_preset not in CAMERA_PRESETS:
            sec.camera_preset = "orbit_showcase"
        sec.objects = [o for o in sec.objects if o in valid_obj_ids]
    return plan

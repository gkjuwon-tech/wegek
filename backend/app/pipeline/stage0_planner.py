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
from ..presets.mapping import animation_for, map_category, primitive_for
from ..presets.shaders import SHADERS
from ..schemas import GlobalStyle, Object3D, Section, SitePlan

PLANNER_SYSTEM = f"""You are WEGEK's Planner AI — an award-winning (Awwwards SOTD) art director and
Three.js technical director. You DESIGN the site, you do not fill a template.

The most common failure is a boring, identical site every time: one 3D object floating
dead-center, spinning a little on scroll, with a headline pinned bottom-left. NEVER do that.
Real standout sites vary composition section to section: asymmetric layouts, scale
contrast, the product slammed into a corner or bleeding off-frame, dramatic camera
moves, text that is sometimes the hero and sometimes a whisper, moments with NO 3D
at all, moments with several objects. Compose each section deliberately and differently.

You have FULL control via this JSON schema. Coordinates are Three.js world units
(object normalized to ~2u; camera looks at origin by default; +x right, +y up, +z toward viewer):
{{
  "project_name": "UPPER_SNAKE_NAME",
  "tagline": "short punchy tagline",
  "brand_mood": "free text — premium, brutalist, playful, editorial, cyber, etc.",
  "global_style": {{
    "color_palette": ["#hex bg","#hex accent","#hex secondary","#hex text"],
    "typography": "modern_sans|serif_luxury|mono_tech|editorial",
    "background_shader": one of {sorted(SHADERS.keys())},
    "accent": "#hex"
  }},
  // ENGINE EFFECT PARAMS you art-direct (the engine renders these; tune for mood).
  // CRITICAL: keep bloom restrained so the scene is NEVER blown out to white — the
  // product and type must stay legible and detailed, not a glowing blob.
  "effects": {{
    "exposure": 0.85-1.05,
    "particles": {{ "count": 0-60000, "size": 0.01-0.04, "opacity": 0.3-0.85, "spread": 2.0-8.0 }},
    "bloom": {{ "strength": 0.15-0.55, "radius": 0.2-0.6, "threshold": 0.8-0.95 }},
    "fog": {{ "color": "#hex", "density": 0.0-0.12 }},
    "grade": {{ "aberration": 0.0-0.003, "grain": 0.0-0.1, "vignette": 0.15-0.5 }}
  }},
  "objects": [
    {{
      "id": "snake_id",
      "description": "vivid visual description for image/3D generation",
      "mesh_query": "clean concrete noun phrase to search a 3D-model library, e.g. 'high top sneaker shoe', 'human skull', 'street lamp post' — a real physical object, not an abstract concept",
      "category": "tech|watch|auto|sneakers|beauty|furniture|sports|food|fashion|gaming|luxury",
      "needs_parts_separation": false,
      // OPTIONAL: author the scroll-linked motion yourself (t in 0..1). Beats the canned presets.
      "keyframes": [
        {{"t":0.0,"position":[0,0,0],"rotation":[0,0,0],"scale":1.0}},
        {{"t":1.0,"position":[0,0.3,0],"rotation":[0,3.14,0],"scale":1.05}}
      ],
      // fallback only if you omit keyframes:
      "animation": "slow_rotation_y|float_bob|explode_reassemble|mechanical_tick|spin_fast"
    }}
  ],
  "sections": [
    {{
      "id": "hero",
      "type": "free label (3d_hero, editorial_split, full_bleed, manifesto, gallery, dom_section, ...)",
      "headline": "big headline",
      "subcopy": "supporting line",
      "body": "optional paragraph",
      "objects": ["object_id", ...],   // 0, 1 or several — empty is allowed for a text-only beat
      // COMPOSITION — vary these every section:
      "layout": {{
        "text_anchor": "top-left|mid-left|bottom-left|center|top-right|mid-right|bottom-right|top-center|bottom-center",
        "text_align": "left|center|right",
        "headline_scale": 0.6..1.8,     // relative size of the headline
        "width": "narrow|wide|full",
        "invert": false                  // true = light section on a bright product moment
      }},
      // per-object placement IN THIS SECTION (id -> transform). Move it off-center, scale it, tilt it.
      "object_layout": {{
        "object_id": {{"position":[-2.4,0.2,0.5],"scale":1.4,"rotation":[0.1,0.6,0]}}
      }},
      // CAMERA — author an inline move (preferred) OR name a preset.
      "camera": {{"keyframes":[
        {{"scroll":0.0,"position":[0,1,7],"lookAt":[0,0,0],"fov":45}},
        {{"scroll":1.0,"position":[3,0.5,3],"lookAt":[0,0,0],"fov":38}}
      ]}},
      "camera_preset": one of {sorted(CAMERA_PRESETS.keys())},   // fallback if no inline camera
      "lighting_preset": one of {sorted(LIGHTING_PRESETS.keys())},
      "scroll_behavior": "free label"
    }}
  ]
}}

Rules: 3-6 sections, 1-4 objects, first is the hero, end with a "dom_section" CTA.
Give at least HALF the sections a distinct text_anchor and a distinct camera move from the others.
Copy must be specific to the brief, confident, brand-appropriate. Output JSON only."""


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
    # Hero motion is templated per category; detail shots add variety.
    anims = [animation_for(category), "explode_reassemble", "float_bob"]
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
        effects={
            "exposure": 1.0,
            "particles": {"count": 20000, "size": 0.022, "opacity": 0.8, "spread": 4.2},
            "bloom": {"strength": 0.4, "radius": 0.5, "threshold": 0.86},
            "fog": {"color": cfg["palette"][0], "density": 0.05},
            "grade": {"aberration": 0.0016, "grain": 0.05, "vignette": 0.32},
        },
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
            "effects": data.get("effects", {}),
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

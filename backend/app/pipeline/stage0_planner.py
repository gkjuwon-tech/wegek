"""Stage 0 — Planner AI.

Turns a natural-language brief into a structured `SitePlan`. Uses the configured
LLM when available; otherwise a deterministic heuristic planner produces a fully
valid plan so the factory never stalls.
"""
from __future__ import annotations

import re

from ..clients.llm import LLMClient
from ..config import Settings
from ..factory import refrag
from ..presets.cameras import CAMERA_PRESETS
from ..presets.lighting import LIGHTING_PRESETS
from ..presets.mapping import animation_for, map_category, primitive_for
from ..presets.shaders import SHADERS
from ..schemas import GlobalStyle, Object3D, Section, SitePlan

PLANNER_SYSTEM = f"""You are WEGEK's Planner AI — an award-winning (Awwwards SOTD) art director and
Three.js technical director. You DESIGN the site, you do not fill a template.

Do NOT build "one product spinning on a background", and do NOT scatter meshes at random
coordinates — that reads as junk sprinkled in a void. Build a deliberately COMPOSED 3D SET,
an Active-Theory-style environment the camera travels through, organised like a stage:

- There is a reflective GROUND PLANE at y = -2.4. Everything RESTS on or rises from it —
  give meshes a y so their base sits near the floor (object-center y roughly -2.0 .. +1.5),
  not floating randomly in mid-air.
- FOCAL HIERARCHY: the hero product is the centrepiece — centred near [0, -0.4, 0], the
  largest and best-lit thing, on a pedestal/dais if the concept allows.
- SYMMETRY & FRAMING: place set-dressing in balanced, mostly MIRRORED pairs that frame and
  lead the eye to the hero — e.g. columns at [-5, -1, -4] and [+5, -1, -4]; lamps at
  [-3, 0, 2] and [+3, 0, 2]. Avoid lopsided clutter.
- DEPTH LAYERS: a few large elements far back (z = -12..-20, bigger scale) for a backdrop,
  midground framing around the hero, and 1-2 foreground pieces near the camera (z = +3..+6)
  for parallax. Build receding depth, not a flat row.
- An optional overhead/canopy element above the hero (y = +3..+6) to enclose the space.
Every mesh animates subtly. It must feel like a built place with a clear centre and structure.

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
    "exposure": 0.8-1.0,
    "particles": {{ "count": 0-60000, "size": 0.01-0.04, "opacity": 0.3-0.8, "spread": 2.0-8.0 }},
    "bloom": {{ "strength": 0.12-0.35, "radius": 0.2-0.6, "threshold": 0.85-0.95 }},
    "fog": {{ "color": "#hex", "density": 0.0-0.12 }},
    "grade": {{ "aberration": 0.0-0.003, "grain": 0.0-0.1, "vignette": 0.15-0.5 }},
    "ground": {{ "enabled": true, "color": "#hex deep", "y": -2.4, "metalness": 0.7-0.95, "roughness": 0.1-0.5 }}
  }},
  "objects": [
    {{
      "id": "snake_id",
      "description": "vivid visual description for image/3D generation",
      "mesh_query": "clean concrete noun phrase to search a 3D-model library, e.g. 'high top sneaker shoe', 'human skull', 'street lamp post' — a real physical object, not an abstract concept",
      "category": "tech|watch|auto|sneakers|beauty|furniture|sports|food|fashion|gaming|luxury",
      "needs_parts_separation": false,
      // ABSOLUTE world placement — this mesh's permanent spot in the set. Spread meshes
      // across x(-12..12), y(-6..6), z(-20..6) to build fore/mid/background depth.
      "placement": {{ "position":[x,y,z], "scale":0.5-4.0, "rotation":[x,y,z] }},
      // self-animation as the user scrolls (t = GLOBAL scroll 0..1): drift, spin, rise, orbit.
      "keyframes": [
        {{"t":0.0,"position":[0,0,0],"rotation":[0,0,0],"scale":1.0}},
        {{"t":1.0,"position":[0,0.6,0],"rotation":[0,3.14,0],"scale":1.0}}
      ],
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
      // The HERO/first section MUST open on a WIDE establishing shot that frames the
      // whole set (camera well back, e.g. position [0,2,18], lookAt [0,0,-4], fov ~32)
      // so the composition reads, THEN later sections push in. Never start nose-to-product.
      "camera": {{"keyframes":[
        {{"scroll":0.0,"position":[0,2,18],"lookAt":[0,0,-4],"fov":34}},
        {{"scroll":1.0,"position":[2,1,9],"lookAt":[0,0,-2],"fov":40}}
      ]}},
      "camera_preset": one of {sorted(CAMERA_PRESETS.keys())},   // fallback if no inline camera
      "lighting_preset": one of {sorted(LIGHTING_PRESETS.keys())},
      "scroll_behavior": "free label"
    }}
  ]
}}

Rules: 4-6 sections, 8-14 objects (a populated world; the hero product is one of them),
every object MUST have a "placement", end with a "dom_section" CTA.
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


_REF_SELECT_SYSTEM = (
    "You select reference compositions for a 3D website. Given a brief and a catalog of "
    "composition patterns, reply with ONLY 2-4 short comma-separated search phrases naming the "
    "kinds of 3D scene STRUCTURE that would best suit the brief. No prose."
)


async def _retrieve_refs(llm: LLMClient, prompt: str) -> str:
    """Agentic RAG: let the model pick which reference structures to study, then retrieve them."""
    queries = [prompt]
    try:
        raw = await llm.complete_text(
            _REF_SELECT_SYSTEM, f"Brief: {prompt}\n\nCatalog:\n{refrag.titles()}", max_tokens=200
        )
        queries += [q.strip() for q in raw.replace("\n", ",").split(",") if q.strip()][:4]
    except Exception:  # noqa: BLE001 - retrieval is best-effort
        pass
    picked: dict[str, dict] = {}
    for q in queries:
        for p in refrag.retrieve(q, k=2):
            picked[p["id"]] = p
    patterns = list(picked.values())[:4] or refrag.retrieve(prompt, k=3)
    return refrag.format_block(patterns)


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
            # RAG: ground the world design in real award-winning composition patterns.
            ref_block = await _retrieve_refs(llm, prompt)
            # A populated world (8-14 meshes with placements + keyframes) is a large
            # JSON doc, and the model reasons before emitting it — give it room.
            data = await llm.complete_json(
                PLANNER_SYSTEM, f"Brief: {prompt}\n\n{ref_block}", max_tokens=24000
            )
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
            "bloom": {"strength": 0.28, "radius": 0.5, "threshold": 0.9},
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

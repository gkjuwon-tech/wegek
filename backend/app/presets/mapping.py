"""Category -> preset auto-mapping (Planning doc Appendix B).

Used by the heuristic planner and as a guardrail to fill any presets the LLM
planner leaves unspecified.
"""
from __future__ import annotations

# category -> (lighting, background_shader, palette, camera)
CATEGORY_MAP: dict[str, dict] = {
    "tech": {
        "lighting": "minimal_white",
        "shader": "minimal_light",
        "palette": ["#0a0a0f", "#3a86ff", "#8338ec", "#f5f5f7"],
        "camera": "scroll_dolly",
    },
    "watch": {
        "lighting": "dark_moody",
        "shader": "dark_particle_drift",
        "palette": ["#0a0a0a", "#c9b99a", "#1a1a1a", "#ffffff"],
        "camera": "cinematic_reveal",
    },
    "auto": {
        "lighting": "showcase_rim",
        "shader": "volumetric_fog_dark",
        "palette": ["#06070a", "#e63946", "#1d3557", "#f1faee"],
        "camera": "top_down_to_perspective",
    },
    "sneakers": {
        "lighting": "studio_dramatic",
        "shader": "color_burst_dynamic",
        "palette": ["#1a1a2e", "#e94560", "#0f3460", "#ffffff"],
        "camera": "orbit_showcase",
    },
    "beauty": {
        "lighting": "editorial_contrast",
        "shader": "silk_gradient_warm",
        "palette": ["#1a0d14", "#ff6b9d", "#c44569", "#fdeff4"],
        "camera": "cinematic_reveal",
    },
    "furniture": {
        "lighting": "warm_cozy",
        "shader": "silk_gradient_warm",
        "palette": ["#1a120b", "#d4a373", "#8a5a44", "#faf3e0"],
        "camera": "orbit_showcase",
    },
    "sports": {
        "lighting": "outdoor_natural",
        "shader": "aurora_nebula",
        "palette": ["#0b1d2a", "#06d6a0", "#118ab2", "#ffffff"],
        "camera": "scroll_dolly",
    },
    "food": {
        "lighting": "warm_cozy",
        "shader": "silk_gradient_warm",
        "palette": ["#1a0f0a", "#e9a06b", "#7b3f00", "#fff4e6"],
        "camera": "orbit_showcase",
    },
    "fashion": {
        "lighting": "editorial_contrast",
        "shader": "gradient_noise_dark",
        "palette": ["#0a0a0a", "#e0e0e0", "#666666", "#ffffff"],
        "camera": "cinematic_reveal",
    },
    "gaming": {
        "lighting": "neon_cyber",
        "shader": "neon_cyber",
        "palette": ["#05030f", "#00f5d4", "#f15bb5", "#9b5de5"],
        "camera": "scroll_dolly",
    },
    "luxury": {
        "lighting": "dark_moody",
        "shader": "aurora_nebula",
        "palette": ["#0a0a0a", "#c9b99a", "#1a1a1a", "#ffffff"],
        "camera": "cinematic_reveal",
    },
}

DEFAULT_CATEGORY = "tech"

# Per-category procedural geometry hint, used when no AI 3D asset is available.
CATEGORY_PRIMITIVE: dict[str, str] = {
    "tech": "rounded_box",
    "watch": "torus",
    "auto": "capsule",
    "sneakers": "rounded_box",
    "beauty": "bottle",
    "furniture": "box",
    "sports": "icosahedron",
    "food": "cylinder",
    "fashion": "torus_knot",
    "gaming": "octahedron",
    "luxury": "diamond",
}


def map_category(category: str) -> dict:
    return CATEGORY_MAP.get(category, CATEGORY_MAP[DEFAULT_CATEGORY])


def primitive_for(category: str) -> str:
    return CATEGORY_PRIMITIVE.get(category, "rounded_box")

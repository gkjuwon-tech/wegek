"""Professional 3-point lighting presets (Stage 5).

Each preset is a plain dict consumed by the generated Three.js scene builder.
Light types map to Three.js lights: ambient, directional, point, spot,
hemisphere, area (-> RectAreaLight).
"""
from __future__ import annotations

LIGHTING_PRESETS: dict[str, dict] = {
    "studio_dramatic": {
        "ambient": {"intensity": 0.15, "color": "#ffffff"},
        "lights": [
            {"type": "spot", "intensity": 2.5, "angle": 0.5, "position": [3, 5, 2], "color": "#fff5e6"},
            {"type": "area", "intensity": 0.8, "position": [-3, 3, 2], "color": "#e6f0ff"},
            {"type": "point", "intensity": 1.2, "position": [0, 2, -3], "color": "#ffd4a3"},
        ],
    },
    "studio_soft": {
        "ambient": {"intensity": 0.3, "color": "#ffffff"},
        "lights": [
            {"type": "area", "intensity": 1.5, "position": [2, 4, 3], "color": "#ffffff"},
            {"type": "area", "intensity": 1.0, "position": [-2, 3, 2], "color": "#eef3ff"},
        ],
    },
    "neon_cyber": {
        "ambient": {"intensity": 0.05, "color": "#0a0020"},
        "lights": [
            {"type": "point", "intensity": 3.0, "position": [3, 2, 0], "color": "#ff00ff"},
            {"type": "point", "intensity": 2.5, "position": [-3, 2, 0], "color": "#00ffff"},
            {"type": "spot", "intensity": 1.5, "angle": 0.6, "position": [0, 5, -2], "color": "#ffffff"},
        ],
    },
    "golden_hour": {
        "ambient": {"intensity": 0.2, "color": "#1a1000"},
        "lights": [
            {"type": "directional", "intensity": 2.0, "position": [5, 3, 2], "color": "#ffb347"},
            {"type": "hemisphere", "intensity": 0.6, "skyColor": "#ffcc80", "groundColor": "#4a3520"},
        ],
    },
    "minimal_white": {
        "ambient": {"intensity": 0.5, "color": "#ffffff"},
        "lights": [
            {"type": "area", "intensity": 1.0, "position": [0, 5, 0], "color": "#ffffff"},
            {"type": "hemisphere", "intensity": 0.8, "skyColor": "#ffffff", "groundColor": "#f0f0f0"},
        ],
    },
    "dark_moody": {
        # Low-key but never black: a warm key, a cool rim to carve the silhouette,
        # and a soft fill so a metallic product stays readable instead of vanishing.
        "ambient": {"intensity": 0.12, "color": "#1a1d24"},
        "lights": [
            {"type": "spot", "intensity": 3.2, "angle": 0.45, "position": [3, 5, 3], "color": "#fff1de"},
            {"type": "spot", "intensity": 1.8, "angle": 0.5, "position": [-4, 2, -3], "color": "#9fc6ff"},
            {"type": "area", "intensity": 0.6, "width": 6, "height": 6, "position": [-2, 3, 4], "color": "#dfe7ff"},
        ],
    },
    "outdoor_natural": {
        "ambient": {"intensity": 0.3, "color": "#ffffff"},
        "lights": [
            {"type": "directional", "intensity": 1.5, "position": [10, 10, 5], "color": "#fff8f0"},
            {"type": "hemisphere", "intensity": 0.7, "skyColor": "#87ceeb", "groundColor": "#8b7355"},
        ],
    },
    "showcase_rim": {
        "ambient": {"intensity": 0.08, "color": "#ffffff"},
        "lights": [
            {"type": "area", "intensity": 0.4, "position": [0, 0, 5], "color": "#ffffff"},
            {"type": "spot", "intensity": 2.0, "angle": 0.5, "position": [-4, 2, 0], "color": "#ffffff"},
            {"type": "spot", "intensity": 2.0, "angle": 0.5, "position": [4, 2, 0], "color": "#ffffff"},
        ],
    },
    "editorial_contrast": {
        "ambient": {"intensity": 0.05, "color": "#ffffff"},
        "lights": [
            {"type": "spot", "intensity": 4.0, "angle": 0.2, "position": [1, 8, 3], "color": "#ffffff"},
            {"type": "point", "intensity": 1.0, "position": [-2, 1, -1], "color": "#ff3366"},
        ],
    },
    "warm_cozy": {
        "ambient": {"intensity": 0.25, "color": "#1a0f00"},
        "lights": [
            {"type": "point", "intensity": 1.5, "position": [2, 3, 2], "color": "#ffd699"},
            {"type": "area", "intensity": 0.8, "position": [-1, 4, 1], "color": "#fff0dd"},
            {"type": "point", "intensity": 0.5, "position": [0, 0, -2], "color": "#ff9966"},
        ],
    },
}

DEFAULT_LIGHTING = "studio_dramatic"


def get_lighting(name: str) -> dict:
    return LIGHTING_PRESETS.get(name, LIGHTING_PRESETS[DEFAULT_LIGHTING])

"""Camera presets (Stage 5).

Consumed by the generated scene to drive scroll-linked camera paths.
`keyframes` use a normalized `scroll` value [0,1] mapped to the section's
scroll progress, with `position`, `lookAt` and optional `fov`.
"""
from __future__ import annotations

CAMERA_PRESETS: dict[str, dict] = {
    "orbit_showcase": {
        "type": "orbit",
        "target": [0, 0, 0],
        "distance": 5.0,
        "autoRotate": True,
        "autoRotateSpeed": 0.5,
        "fov": 45,
    },
    "scroll_dolly": {
        "type": "path",
        "fov": 50,
        "keyframes": [
            {"scroll": 0.0, "position": [0, 2, 10], "lookAt": [0, 0, 0]},
            {"scroll": 0.5, "position": [3, 1, 5], "lookAt": [0, 0, 0]},
            {"scroll": 1.0, "position": [0, 0.5, 2.5], "lookAt": [0, 0, 0]},
        ],
    },
    # Slow cinematic push-in. Starts comfortably framed (no fish-eye 90° fov, no
    # 1-unit nose-to-glass distance that ballooned the subject) and eases closer.
    "cinematic_reveal": {
        "type": "path",
        "keyframes": [
            {"scroll": 0.0, "position": [0, 0.6, 6.4], "lookAt": [0, 0, 0], "fov": 50},
            {"scroll": 0.5, "position": [1.6, 0.8, 5.2], "lookAt": [0, 0, 0], "fov": 46},
            {"scroll": 1.0, "position": [0, 1.0, 4.2], "lookAt": [0, 0, 0], "fov": 42},
        ],
    },
    "top_down_to_perspective": {
        "type": "path",
        "keyframes": [
            {"scroll": 0.0, "position": [0, 12, 0.001], "lookAt": [0, 0, 0], "fov": 30},
            {"scroll": 0.5, "position": [5, 8, 5], "lookAt": [0, 0, 0], "fov": 40},
            {"scroll": 1.0, "position": [3, 2, 6], "lookAt": [0, 0, 0], "fov": 50},
        ],
    },
    "static_hero": {
        "type": "static",
        "position": [0, 1, 6],
        "lookAt": [0, 0, 0],
        "fov": 45,
    },
}

DEFAULT_CAMERA = "orbit_showcase"


def get_camera(name: str) -> dict:
    return CAMERA_PRESETS.get(name, CAMERA_PRESETS[DEFAULT_CAMERA])

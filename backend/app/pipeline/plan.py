"""Stage 1 — Plan: the LLM designs a 3-scene experience (Active-Theory grammar).

The plan is what the agent will build in Blender: three distinct scenes that hand
off on scroll, each with meshes (to be made by Tripo), keyframed animation, a camera
move, rim-lit lighting and an HDRI. An LLM authors it; a heuristic fallback keeps the
pipeline valid without a key.
"""
from __future__ import annotations

import math
import re

from ..clients.llm import LLMClient
from ..config import Settings
from ..schemas import (
    CameraKey,
    Experience,
    Keyframe,
    Light,
    Scene,
    SceneObject,
)

PLANNER_SYSTEM = """You are WEGEK's technical art director — Active Theory / Lusion calibre. You design a
3D experience that will be BUILT IN BLENDER and path-traced, then baked into a site.

Design EXACTLY THREE scenes that hand off on scroll (a scene holds; the user scrolls; it
transitions naturally into the next — never a hard cut). Coordinates are Blender world units
(Z up, -Y is into the screen; the reflective floor is at z=-1.6; camera looks toward origin).

Compose each scene like a real set, not scattered props:
- a clear hero on/near the centre, set-dressing in balanced (often mirrored) pairs, depth layers
  (background big & far on -Y, foreground framing near camera), everything resting on the floor.
- keyframed motion per object (slow rotation, rise, drift, assemble) over the scene's scroll t 0..1.
- a deliberate camera MOVE per scene (wide establishing -> push/orbit), and rim lighting that
  carves the silhouettes. Pick an HDRI mood and a restrained palette.
- the three scenes should feel like different rooms of one world (e.g. arrival shrine -> macro
  detail chamber -> lifestyle/abstract finale), with smooth transition_out between them.

Return ONLY JSON:
{
 "project_name":"UPPER_SNAKE","tagline":"...","mood":"...",
 "scenes":[ {
   "id":"act1","title":"...","narrative":"...",
   "hdri":"studio|sunset|night_city|void|warehouse","palette":["#bg","#accent","#secondary","#text"],
   "transition_out":"camera_fly|dissolve|push_through|morph",
   "objects":[ {
     "id":"snake_id","description":"vivid","mesh_query":"clean noun phrase for a 3D model (real object)",
     "is_hero":true,"material":"chrome|glass|matte|emissive",
     "position":[x,y,z],"rotation":[x,y,z],"scale":1.0,
     "keyframes":[{"t":0.0,"position":[0,0,0],"rotation":[0,0,0],"scale":1.0},
                  {"t":1.0,"position":[0,0.3,0],"rotation":[0,3.14,0],"scale":1.0}]
   } ],
   "camera":[{"t":0.0,"position":[0,-8,2.5],"look_at":[0,0,0],"fov":40},
             {"t":1.0,"position":[2.5,-4,1.2],"look_at":[0,0,0],"fov":48}],
   "lights":[{"type":"area","position":[5,-5,6],"energy":2000,"color":"#fff5e6","size":7,"is_rim":false},
             {"type":"area","position":[-4,5,3],"energy":1400,"color":"#00e5ff","size":4,"is_rim":true}]
 } ]
}
3-6 objects per scene, the first scene's main object is the overall hero. Be specific to the brief."""

TAU = math.pi * 2


def _slug(text: str) -> str:
    words = re.sub(r"[^a-zA-Z0-9\s]", "", text).split()[:3]
    return ("_".join(w.upper() for w in words) or "WEGEK_SITE")[:32]


async def run(prompt: str, settings: Settings, *, mood: str | None) -> tuple[Experience, str]:
    llm = LLMClient(settings)
    if llm.available:
        try:
            data = await llm.complete_json(PLANNER_SYSTEM, f"Brief: {prompt}", max_tokens=20000)
            exp = _coerce(data, prompt, mood)
            if len(exp.scenes) >= 1:
                return exp, llm.label
        except Exception:  # noqa: BLE001
            pass
    return heuristic(prompt, mood), "heuristic"


REVISE_SYSTEM = PLANNER_SYSTEM + """

You are REVISING this plan to fix an art director's critique of fast SOLID preview frames
(no materials/lighting yet — judge COMPOSITION, placement, scale, depth, camera moves and
whether the three scenes read as distinct, well-staged sets). Keep what works; change the JSON
to address every issue. Return the full improved Experience JSON (still exactly 3 scenes)."""


async def revise(exp: Experience, critique: dict, settings: Settings) -> Experience:
    import json
    llm = LLMClient(settings)
    if not llm.available:
        return exp
    try:
        data = await llm.complete_json(
            REVISE_SYSTEM,
            f"CRITIQUE:\n{json.dumps(critique)[:4000]}\n\nCURRENT PLAN:\n{json.dumps(exp.model_dump())[:14000]}",
            max_tokens=20000,
        )
        return _coerce(data, exp.project_name, exp.mood)
    except Exception:  # noqa: BLE001
        return exp


def _coerce(data: dict, prompt: str, mood: str | None) -> Experience:
    exp = Experience.model_validate({
        "project_name": data.get("project_name") or _slug(prompt),
        "tagline": data.get("tagline", ""),
        "mood": mood or data.get("mood", "premium neon-noir"),
        "scenes": data.get("scenes", []),
    })
    exp.scenes = exp.scenes[:3]
    while len(exp.scenes) < 3:  # pad to exactly three with a calm finale
        exp.scenes.append(_finale_scene(len(exp.scenes), exp))
    return exp


def _finale_scene(i: int, exp: Experience) -> Scene:
    hero = exp.all_objects()[0] if exp.all_objects() else None
    obj = hero.model_copy() if hero else SceneObject(id="hero", mesh_query="product", is_hero=True)
    obj.keyframes = [Keyframe(t=0, rotation=[0, 0, 0]), Keyframe(t=1, rotation=[0, math.pi, 0])]
    return Scene(
        id=f"act{i+1}", title="Finale", narrative="A quiet last look.",
        objects=[obj],
        camera=[CameraKey(t=0, position=[0, -6, 2]), CameraKey(t=1, position=[0, -3.5, 1])],
        lights=[Light(position=[4, -4, 5], energy=1800),
                Light(position=[-4, 4, 3], energy=1200, color="#a06bff", is_rim=True)],
    )


def heuristic(prompt: str, mood: str | None) -> Experience:
    name = _slug(prompt)
    pal = ["#06080d", "#00e5ff", "#a06bff", "#eef6ff"]

    def hero(idx: int) -> SceneObject:
        return SceneObject(
            id=f"hero_{idx}", description=f"{prompt} hero product", mesh_query=prompt,
            is_hero=(idx == 1), material="chrome", position=[0, 0, -0.4], scale=1.4,
            keyframes=[Keyframe(t=0, rotation=[0, 0, 0]), Keyframe(t=1, rotation=[0, TAU, 0])],
        )

    def lights(rim: str) -> list[Light]:
        return [
            Light(type="area", position=[5, -5, 6], energy=2200, color="#fff5e6", size=7),
            Light(type="area", position=[-6, -2, 3], energy=600, color="#cfe0ff", size=8),
            Light(type="area", position=[-4, 5, 3], energy=1500, color=rim, size=4, is_rim=True),
        ]

    scenes = [
        Scene(id="act1", title="Arrival", narrative="The object emerges.", hdri="void", palette=pal,
              transition_out="push_through", objects=[hero(1)],
              camera=[CameraKey(t=0, position=[0, -9, 2.6], fov=38),
                      CameraKey(t=1, position=[2.4, -5, 1.4], fov=46)], lights=lights("#00e5ff")),
        Scene(id="act2", title="Detail", narrative="Macro inspection.", hdri="studio", palette=pal,
              transition_out="dissolve", objects=[hero(2)],
              camera=[CameraKey(t=0, position=[0, -3.5, 0.8], fov=55),
                      CameraKey(t=1, position=[1.5, -2.4, 0.6], fov=50)], lights=lights("#a06bff")),
        Scene(id="act3", title="Finale", narrative="A last hero look.", hdri="sunset", palette=pal,
              transition_out="dissolve", objects=[hero(3)],
              camera=[CameraKey(t=0, position=[0, -7, 2.2], fov=42),
                      CameraKey(t=1, position=[-2.5, -5, 1.6], fov=44)], lights=lights("#ff7a3c")),
    ]
    return Experience(project_name=name, tagline="Engineered to be remembered.",
                      mood=mood or "premium neon-noir", scenes=scenes)

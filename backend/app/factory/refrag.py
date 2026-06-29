"""Composition RAG — a retrievable knowledge base of how award-winning WebGL sites
STRUCTURE and ARRANGE their 3D scenes.

Built by studying real reference stills (Active Theory, Lusion, Resn, Unseen, Igloo,
etc. — sourced via their og:image previews + provided screenshots). Each entry encodes
an actionable spatial grammar (object roles, placement, symmetry, depth layers, camera,
materials) so the planner can ground its world design in proven composition instead of
scattering meshes. The planner retrieves the patterns relevant to a brief and adapts them.
"""
from __future__ import annotations

import re

# Each pattern: concrete, emulatable composition grammar derived from real references.
CORPUS: list[dict] = [
    {
        "id": "reflective_stage_shrine",
        "title": "Reflective stage shrine (hero on a dais over a mirror floor)",
        "tags": "shrine altar product hero reverent dais platform reflection water temple luxury sneaker watch jewel",
        "refs": "Active Theory (chandelier hall), Unseen.co (island), Lusion",
        "structure": (
            "A single hero sits on a low circular DAIS at the exact centre (≈[0,-1.6,0]), resting on a "
            "REFLECTIVE FLOOR (glossy/water) that doubles the whole scene. Vertical framing rises "
            "symmetrically around it: paired columns/pillars at [-5,-1,-4] & [+5,-1,-4] and again deeper "
            "at [-7,-1,-12] & [+7,-1,-12], shrinking with distance for forced perspective. An overhead "
            "canopy/ring element hovers above the hero ([0,+5,-2]). A soft volumetric glow column descends "
            "onto the hero. Sparse hanging/floating accents (cables, motes) connect ceiling to floor. "
            "Camera: WIDE establishing eye-level over the floor (≈[0,1.5,16], fov 32) so the reflection and "
            "symmetry read, then slow push toward the hero. Deep desaturated palette, fog for depth."
        ),
    },
    {
        "id": "minimal_monument_negative_space",
        "title": "Minimal monument in vast negative space",
        "tags": "minimal single hero monument calm vast negative space fog horizon product luxury editorial igloo",
        "refs": "Igloo.inc, Resn (gem)",
        "structure": (
            "ONE hero object, off-centre on the rule-of-thirds, alone on an enormous near-empty ground plane "
            "that fades into fog at the horizon. Almost no set dressing — the power is restraint and scale. "
            "Eye-level camera fairly close to the ground, large empty sky/void above for the headline. "
            "Monochrome or 2-tone palette, soft single key light, gentle ground contact shadow. The hero is "
            "the ONLY bright/detailed thing; everything else is atmosphere. Great for a calm, premium reveal."
        ),
    },
    {
        "id": "dark_monolith_void",
        "title": "Dark monolith on the void (single rim-lit object)",
        "tags": "dark void black mysterious gem diamond monolith single object rim light drama luxury teaser",
        "refs": "Resn (black gem), Active Theory (loader)",
        "structure": (
            "A single faceted/glassy dark object centred on pure black, lit only by a tight rim/edge light so "
            "the silhouette and facets glint while the body stays near-black. No floor, no props — total void. "
            "Tiny particles drift for scale. Camera locked close and frontal, very slow orbit. Maximum mystery; "
            "ideal for a pre-launch teaser or a chapter break."
        ),
    },
    {
        "id": "layered_holographic_panels",
        "title": "Layered holographic glass panels + central mechanism",
        "tags": "holographic iridescent glass panels layers ui hud chrome mechanism tech cyber translucent depth",
        "refs": "Active Theory (social / logo reveal)",
        "structure": (
            "Several large semi-transparent glass/holographic PANELS stacked at staggered depths (z = +2, -1, -5), "
            "slightly rotated, with chromatic-aberration edges, framing a central chrome/iridescent mechanism or "
            "logo at [0,0,-1]. The panels carry kinetic mono text and parallax at different speeds on scroll. "
            "Depth comes from translucency overlap, not many solid meshes. Purple/blue/teal iridescence, bloom "
            "on highlights. Camera drifts laterally so the layers shear past each other. Very 'tech-luxury'."
        ),
    },
    {
        "id": "floating_island_diorama",
        "title": "Floating island / diorama on reflective water",
        "tags": "floating island diorama platform rock reflective water debris arches dawn soft surreal product world",
        "refs": "Unseen.co, Active Theory",
        "structure": (
            "A central rocky PLATFORM/island floats on a calm reflective water plane; the hero rests on it. "
            "Chunks of rock/debris and arch fragments float around at varied heights ([-6,2,-3], [5,1,-6], "
            "[3,-0.5,4]) drifting slowly, with larger silhouette landforms far back for a horizon. Soft dawn "
            "palette (rose/amber/lilac), gentle fog, true reflections in the water. Camera low near the water "
            "for maximum reflection, slow dolly. Dreamy, surreal, premium."
        ),
    },
    {
        "id": "particle_storm_hud_hero",
        "title": "Particle-storm hero with HUD typography",
        "tags": "particles storm swarm cloud hud telemetry mono kinetic type cyber energy hero product sneaker gaming",
        "refs": "Active Theory (provided hero shot)",
        "structure": (
            "The hero is enveloped in a dense volumetric PARTICLE cloud (tens of thousands) that forms/erodes "
            "around it; particles are fine, iridescent, additive (glow under bloom). Mono/technical typography is "
            "laid out like a HUD — corner telemetry readouts, an eyebrow tag, a big kinetic headline that the "
            "geometry occludes. Few or no solid props; the PARTICLES are the environment. Deep palette, restrained "
            "exposure so the centre never blows out. Camera slow push with subtle handheld drift."
        ),
    },
    {
        "id": "glass_card_world_ui",
        "title": "Glass-card UI floating over a 3D world",
        "tags": "glass card ui menu navigation frosted hud overlay world background contact work prompt interface",
        "refs": "Active Theory (menu / search)",
        "structure": (
            "A clean frosted-GLASS card or pill-nav floats in front of a living 3D world (a column/spine of "
            "particles, a set behind). The DOM is minimal and intentional — a pill 'WORK — CONTACT' nav top-centre "
            "with a soft glow, a short list, maybe an input — never walls of text. The 3D continues behind and "
            "around the card with parallax. Use sparingly for menu/CTA beats. Glassmorphism + bloom + grain."
        ),
    },
    {
        "id": "infinite_corridor_travel",
        "title": "Infinite corridor / tunnel the camera flies through",
        "tags": "corridor tunnel travel flythrough repeating arches gates speed motion depth journey procession",
        "refs": "Active Theory, Resn",
        "structure": (
            "Repeating gateway/arch/pillar elements recede down the -z axis in mirrored pairs ([-4,0,-z] & "
            "[+4,0,-z] for z = 4,10,18,28), forming a corridor the camera flies through on scroll. The hero waits "
            "at the end of the tunnel as the payoff. Strong central vanishing point, fog fading the far end, light "
            "streaks/particles rushing past for speed. Great for building anticipation before a reveal."
        ),
    },
]


def _tok(s: str) -> list[str]:
    return [t for t in re.split(r"[^a-z0-9]+", s.lower()) if len(t) > 2]


def retrieve(query: str, k: int = 3) -> list[dict]:
    """Return the top-k composition patterns most relevant to a query."""
    q = set(_tok(query))
    scored: list[tuple[float, dict]] = []
    for e in CORPUS:
        hay = _tok(e["tags"] + " " + e["title"] + " " + e["structure"])
        score = sum(hay.count(t) for t in q) + 2 * len(q & set(_tok(e["tags"])))
        scored.append((score, e))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [e for s, e in scored[:k] if s > 0] or [CORPUS[0]]


def format_block(patterns: list[dict]) -> str:
    lines = ["REFERENCE COMPOSITIONS (study these proven structures from award-winning sites and ADAPT "
             "one or blend a few to the brief — do not copy literally, but match this level of deliberate "
             "spatial design):"]
    for p in patterns:
        lines.append(f"\n• {p['title']}  [refs: {p['refs']}]\n  {p['structure']}")
    return "\n".join(lines)


def titles() -> str:
    return "\n".join(f"- {e['id']}: {e['title']}" for e in CORPUS)

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


# How award-winning sites CHOREOGRAPH scroll — temporal grammar: what animates, how
# the camera travels, and how one scene TRANSITIONS into the next as you scroll.
CHOREO: list[dict] = [
    {
        "id": "assemble_on_scroll",
        "title": "Assemble / explode on scroll",
        "tags": "assemble explode parts components build mechanism reveal engineering watch product disassemble",
        "structure": (
            "Open with the hero's parts SCATTERED and drifting apart in space; as the user scrolls they fly "
            "inward and lock together into the finished product by mid-page, then the camera orbits the whole. "
            "Per-object keyframes move each piece from an exploded position (t=0) to its assembled slot (t≈0.5); "
            "stagger each part's timing slightly. Reverse near the end for a breathing loop."
        ),
    },
    {
        "id": "fly_through_portal",
        "title": "Fly-through transition (camera dives through an object into the next scene)",
        "tags": "transition portal gateway fly through dive zoom warp scene change chapter travel tunnel door",
        "structure": (
            "Each chapter ends by the camera ACCELERATING toward a portal/arch/aperture in the current scene; as "
            "it passes through, the previous set's objects scroll_out (fade+recede) and the next chapter's objects "
            "scroll_in on the far side — a seamless scene CHANGE with no hard cut. Drive object scroll_in/scroll_out "
            "windows so each beat owns a slice of the scroll, and the camera z accelerates at the hand-off."
        ),
    },
    {
        "id": "scene_morph_chapters",
        "title": "Distinct scene per chapter (the world changes as you scroll)",
        "tags": "chapters scenes change worlds morph swap sections distinct environments narrative journey sequence",
        "structure": (
            "The page is several DIFFERENT little worlds, not one static set. Each section owns a scroll range; its "
            "meshes scroll_in at the start of the range and scroll_out at the end, while the camera relocates to a "
            "fresh vantage. Beat 1: product hero shrine. Beat 2: macro detail (camera tight, different props). "
            "Beat 3: lifestyle/context world. The hero may persist while everything AROUND it is replaced — that "
            "continuity + changing context is the signature of premium scrollytelling."
        ),
    },
    {
        "id": "pin_and_animate",
        "title": "Pinned beat with scrubbed internal animation",
        "tags": "pin sticky scrub timeline hold rotate spin internal animation detail dwell focus product turntable",
        "structure": (
            "Hold the camera still on the hero for a stretch of scroll while an internal animation is SCRUBBED by "
            "scroll position — the product slowly rotates 360°, a cutaway opens, labels draw on, a shader morphs. "
            "Maps scroll progress directly to one object's keyframe t so the user 'drives' the animation. Use for a "
            "single deliberate detail moment between travel beats."
        ),
    },
    {
        "id": "focus_handoff",
        "title": "Focus hand-off (one object passes the spotlight to the next)",
        "tags": "handoff sequence relay focus pass baton multiple products lineup gallery one by one parade",
        "structure": (
            "For multi-product stories: object A is centred and lit; on scroll it drifts off and recedes while "
            "object B rises from the back into the focal centre, inheriting the key light — a relay. Stagger each "
            "object's scroll_in/scroll_out so exactly one owns the centre at a time, with brief overlaps for grace."
        ),
    },
    {
        "id": "scroll_rotate_reveal",
        "tags": "rotate spin reveal on scroll turntable 3d image card flip orientation inspect product detail",
        "title": "Scroll-driven rotation reveal (object turns to reveal faces)",
        "structure": (
            "As the user scrolls, the hero rotates on Y (and a little X) so successive faces/angles come into "
            "view — front → profile → back → detail — each angle paired with a different copy block fading in. "
            "Map global scroll directly to the object's Y rotation keyframes (0 → 2π over the beat). Inspired by "
            "Codrops '3D image rotations on scroll'. Great for a single-product inspection chapter."
        ),
    },
    {
        "id": "horizontal_pinned_gallery",
        "tags": "horizontal scroll pinned gallery lineup sideways pan lateral lineup collection multiple",
        "title": "Pinned horizontal lateral pan",
        "structure": (
            "Pin a section and translate the camera (or the world) LATERALLY on +x as the user scrolls vertically, "
            "panning across a row of staged objects/scenes like a tracking shot. Each object owns an x-slice; the "
            "camera trucks left→right. Good for showing a collection or a timeline within one beat."
        ),
    },
    {
        "id": "parallax_depth_drift",
        "title": "Multi-layer parallax drift",
        "tags": "parallax layers depth foreground background drift float subtle continuous ambient motion calm",
        "structure": (
            "Foreground, midground and background mesh layers scroll at different rates (foreground fastest) so the "
            "set has continuous depth even in calm sections. Combine with slow idle rotation/bob on each object and "
            "a gentle camera truck. The connective tissue between bigger set-pieces — never let the scene sit dead."
        ),
    },
]


def _tok(s: str) -> list[str]:
    return [t for t in re.split(r"[^a-z0-9]+", s.lower()) if len(t) > 2]


def _retrieve(corpus: list[dict], query: str, k: int) -> list[dict]:
    q = set(_tok(query))
    scored: list[tuple[float, dict]] = []
    for e in corpus:
        hay = _tok(e["tags"] + " " + e["title"] + " " + e["structure"])
        score = sum(hay.count(t) for t in q) + 2 * len(q & set(_tok(e["tags"])))
        scored.append((score, e))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [e for s, e in scored[:k] if s > 0] or [corpus[0]]


def retrieve(query: str, k: int = 3) -> list[dict]:
    """Top-k spatial COMPOSITION patterns for a query."""
    return _retrieve(CORPUS, query, k)


def retrieve_choreo(query: str, k: int = 2) -> list[dict]:
    """Top-k scroll CHOREOGRAPHY / scene-transition patterns for a query."""
    return _retrieve(CHOREO, query, k)


def format_block(patterns: list[dict], choreo: list[dict] | None = None) -> str:
    lines = ["REFERENCE COMPOSITIONS (study these proven spatial structures from award-winning sites and "
             "ADAPT/blend them — match this level of deliberate design, don't copy literally):"]
    for p in patterns:
        lines.append(f"\n• {p['title']}  [refs: {p.get('refs', '')}]\n  {p['structure']}")
    if choreo:
        lines.append("\nREFERENCE SCROLL CHOREOGRAPHY (how the scene ANIMATES and CHANGES across scroll — "
                     "design a sequence like this, not one static frame):")
        for c in choreo:
            lines.append(f"\n• {c['title']}\n  {c['structure']}")
    return "\n".join(lines)


def titles() -> str:
    comp = "\n".join(f"- {e['id']}: {e['title']}" for e in CORPUS)
    cho = "\n".join(f"- {e['id']}: {e['title']}" for e in CHOREO)
    return f"COMPOSITIONS:\n{comp}\n\nSCROLL CHOREOGRAPHY:\n{cho}"

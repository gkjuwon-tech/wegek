"""The user-side text condition for each shape (what a person would type).

Written in plain English (Jev's strongest language, per its model docs) from the shape's
design parameters.  It names the kind of object and its countable features the way a
person would ("a mug with a handle", "a plate with four round holes"); it never states
genus or component numbers in topological terms.
"""

from __future__ import annotations

from jevsg.shapes.library import ShapeSpec

_NUM = {1: "one", 2: "two", 3: "three", 4: "four", 5: "five", 6: "six"}


def condition_text(spec: ShapeSpec) -> str:
    p = spec.params
    fam = spec.family
    if fam == "cup":
        return (
            "A drinking mug with a single handle; it is open at the top so it can hold coffee."
            if p.get("handle")
            else "A plain tumbler cup without a handle; it is open at the top so it can hold liquid."
        )
    if fam == "ring":
        if p.get("links", 1) == 2:
            return "Two separate ring-shaped chain links that pass through each other without touching."
        return "A single thin ring, like a torus-shaped band, with an open hole in the middle."
    if fam == "thin_shell":
        kind = p.get("kind")
        if kind == "hollow_ball":
            return (
                "A completely closed hollow ball with a thin wall and an empty sealed space inside."
            )
        if kind == "bowl":
            return "A thin-walled round bowl, open at the top."
        if kind == "vented_ball":
            return "A hollow ball with a thin wall and one round opening into the empty inside."
        return "A hollow ball with a thin wall and two round openings into the empty inside."
    if fam == "holed_plate":
        k = int(p.get("holes", 1))
        return (
            f"A flat thin plate with {_NUM[k]} round hole{'s' if k > 1 else ''} going through it."
        )
    if fam == "multi_part":
        k = int(p.get("parts", 2))
        kinds = str(p.get("kinds", "")).split(",")
        ring = " One of the parts is a small ring with a hole." if "torus" in kinds else ""
        return f"{_NUM[k].capitalize()} separate solid parts in a row with small gaps between them; no parts touch.{ring}"
    if fam == "helmet":
        k = int(p.get("slits", 1))
        crest = " and a thin crest fin on top" if p.get("crest") else ""
        return (
            f"A thin-walled helmet shell, open at the bottom for a head, with {_NUM[k]} "
            f"eye slit{'s' if k > 1 else ''} cut through the front{crest}."
        )
    raise KeyError(fam)

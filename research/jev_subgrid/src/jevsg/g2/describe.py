"""State and option descriptions for the three context levels (proposal §5.2, §8.3).

* ``L0`` numbers only — the raw crossing counts, as the representation stores them;
* ``L1`` + neighbour structure — the surfaces entering the hidden block, in words, and
  each option's inside/outside pattern and crossing total;
* ``L2`` + computed summary — each option's *effect* on the whole object (pieces,
  through-holes, sealed bubbles), computed from that option's own reconstruction.

Nothing here reads the reference or the oracle grades.  Option descriptions state only
what the option does ("computed effects"), never whether it is good (proposal §5.3).
"""

from __future__ import annotations

from typing import Any

LEVELS = ("L0", "L1", "L2")
_SIDE = {"-x": "left", "+x": "right", "-y": "front", "+y": "back", "-z": "bottom", "+z": "top"}
_NUM = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten"]


def _n(k: int) -> str:
    return _NUM[k] if 0 <= k < len(_NUM) else str(k)


def _plural(k: int, word: str) -> str:
    return f"{_n(k)} {word}{'' if k == 1 else 's'}"


def state_for(problem: dict[str, Any], level: str) -> dict[str, Any]:
    task = (
        "A small cube-shaped region of a 3D object's surface data was hidden. "
        "Each option is one way to fill the hidden region back in. Only one filling is "
        "needed; the rest of the object is fixed."
    )
    state: dict[str, Any] = {"object_description": problem["condition"], "task": task}
    faces = problem["boundary_faces"]
    if level == "L0":
        state["boundary_crossing_counts"] = {k: v["crossings"] for k, v in faces.items()}
        return state
    sides = []
    for key, info in faces.items():
        c, d = info["crossings"], info["double"]
        if c == 0:
            sides.append(f"{_SIDE[key]} side: no surface passes through")
        else:
            wall = (
                f", including {_plural(d, 'thin-wall spot')} where two surfaces pass very close together"
                if d
                else ""
            )
            sides.append(f"{_SIDE[key]} side: the surface crosses it {_plural(c, 'time')}{wall}")
    state["surroundings"] = sides
    return state


def option_text(problem: dict[str, Any], key: str, level: str) -> Any:
    c = problem["candidates"][key]
    if level == "L0":
        return {"crossings_per_hidden_edge": " ".join(str(k) for k in c["k_per_edge"])}
    if not c["labels"]:
        raise ValueError(f"option {key} has no inside/outside labels; its description would differ")
    solid = sum(c["labels"])
    desc: dict[str, Any] = {
        "surface_crossings_inside_region": c["area"],
        # From the option's content, identically for every option (never from how it was made).
        "has_thin_wall_double_crossings": "yes" if max(c["k_per_edge"], default=0) >= 2 else "no",
    }
    desc["hidden_points_inside_material"] = f"{solid} of {len(c['labels'])}"
    if level == "L1":
        return desc
    e = c["effects"]
    parts = [
        f"The whole object becomes {_plural(int(e['object_pieces']), 'separate piece')} "
        f"with {_plural(int(e['object_holes']), 'through-hole')} in total."
    ]
    b = int(e["bubbles_in_block"])
    parts.append(
        f"It creates {_plural(b, 'small sealed bubble')} inside the region."
        if b
        else "It creates no sealed bubble inside the region."
    )
    parts.append(
        f"Inside the region the surface forms {_plural(int(e['surface_pieces_in_block']), 'separate sheet')}."
    )
    if not e["object_closed"]:
        parts.append("The surface is left broken (not closed).")
    desc["effect_on_object"] = " ".join(parts)
    return desc


QUESTION = (
    "Which option fills the hidden region so that the whole object best matches "
    "`object_description`?"
)

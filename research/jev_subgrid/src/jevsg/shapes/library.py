"""The G1 shape set: 6 structural families x 8 procedurally generated shapes = 48.

Proposal §6 (G1): 컵, 고리, 얇은 쉘, 구멍 난 판, 다중 부품, 투구 유사 형상, 8 each, with
examples whose holes, wall thickness and connectivity can be measured.  Every shape is
generated from a family-specific seed, so the set is reproducible, license-free, and
disjoint by construction from any later-stage data (G2+ must use other seeds/IDs;
proposal §5.1 split rule).

Each :class:`ShapeSpec` carries its *designed* ground truth:

* ``expected_components`` / ``expected_genus`` — surface components and the sorted genus
  of each (a cup with a handle is one genus-1 surface; a closed hollow ball is two
  nested genus-0 surfaces);
* probes — named points that must be *air* (the coffee space of a cup, the passage of a
  handle, the gap between parts, the void of a hollow shell, an eye slit) or *material*
  (the middle of a thin wall).  They turn "핵심 구조 보존" into yes/no checks;
* ``min_feature`` — the thinnest designed wall / gap / tube diameter in object units.

Within each family, variants 0-3 keep the canonical pose and variants 4-7 get a random
rotation, so both grid-aligned and oblique thin structures are covered.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

import numpy as np
import numpy.typing as npt

from jevsg.shapes.sdf import (
    SDF,
    box,
    capsule,
    cylinder_z,
    halfspace,
    polar_cap,
    random_rotation,
    rotation_x,
    sphere,
    torus_z,
    union,
)

FloatArray = npt.NDArray[np.float64]

FAMILIES = ("cup", "ring", "thin_shell", "holed_plate", "multi_part", "helmet")
FAMILY_KO = {
    "cup": "컵",
    "ring": "고리",
    "thin_shell": "얇은 쉘",
    "holed_plate": "구멍 난 판",
    "multi_part": "다중 부품",
    "helmet": "투구 유사",
}
VARIANTS_PER_FAMILY = 8
SPLIT = "g1_roundtrip"
_FAMILY_SEED = {name: 1000 * (i + 1) for i, name in enumerate(FAMILIES)}


@dataclass(frozen=True)
class Probe:
    name: str
    point: tuple[float, float, float]
    expect: str  # "air" | "material"
    structure: str  # which designed structure the probe certifies


@dataclass(frozen=True)
class ShapeSpec:
    shape_id: str
    family: str
    variant: int
    sdf: SDF = field(repr=False, compare=False)
    bounds: tuple[tuple[float, float, float], tuple[float, float, float]]
    expected_components: int
    expected_genus: tuple[int, ...]
    probes: tuple[Probe, ...]
    min_feature: float
    params: dict[str, float | int | str] = field(default_factory=dict)
    split: str = SPLIT

    @property
    def expected_signature(self) -> tuple[int, ...]:
        return tuple(sorted(self.expected_genus))


def _pt(v: npt.ArrayLike) -> tuple[float, float, float]:
    x = np.asarray(v, dtype=np.float64).reshape(3)
    return (float(x[0]), float(x[1]), float(x[2]))


def _log_uniform(rng: np.random.Generator, lo: float, hi: float) -> float:
    return float(np.exp(rng.uniform(np.log(lo), np.log(hi))))


def _thickness_schedule(variant: int, lo: float, hi: float, rng: np.random.Generator) -> float:
    """Spread the 8 variants over [lo, hi] (log scale) with a little jitter, so every
    family contains both sub-cell and multi-cell walls at every tested resolution."""
    k = variant % 4  # the same thickness ladder in the canonical and rotated halves
    base = np.exp(np.log(lo) + (np.log(hi) - np.log(lo)) * (k + rng.uniform(0.15, 0.85)) / 4.0)
    return float(base)


def _finish(
    shape_id: str,
    family: str,
    variant: int,
    sdf: SDF,
    half_extent: FloatArray,
    components: int,
    genus: list[int],
    probes: list[Probe],
    min_feature: float,
    params: dict[str, float | int | str],
    rng: np.random.Generator,
) -> ShapeSpec:
    """Apply the pose (rotation for variants 4-7) and package the spec."""
    if variant >= 4:
        rot = random_rotation(rng)
        sdf = sdf.rotate(rot)
        probes = [
            Probe(p.name, _pt(rot @ np.asarray(p.point)), p.expect, p.structure) for p in probes
        ]
        r = float(np.linalg.norm(half_extent))
        lo, hi = (-r, -r, -r), (r, r, r)
        params = {**params, "pose": "rotated"}
    else:
        lo, hi = _pt(-np.asarray(half_extent)), _pt(half_extent)
        params = {**params, "pose": "canonical"}
    return ShapeSpec(
        shape_id=shape_id,
        split=split_of_variant(variant),
        family=family,
        variant=variant,
        sdf=sdf,
        bounds=(lo, hi),
        expected_components=components,
        expected_genus=tuple(sorted(genus)),
        probes=tuple(probes),
        min_feature=min_feature,
        params=params,
    )


# ------------------------------------------------------------------------ cup
def make_cup(variant: int) -> ShapeSpec:
    rng = np.random.default_rng(_FAMILY_SEED["cup"] + variant)
    radius = rng.uniform(0.5, 0.65)
    height = rng.uniform(1.3, 1.7)
    wall = _thickness_schedule(variant, 0.03, 0.16, rng)
    bottom = max(1.5 * wall, 0.06)
    has_handle = variant % 4 != 3
    z0, z1 = -height / 2, height / 2
    body = cylinder_z(radius, z0, z1) - cylinder_z(radius - wall, z0 + bottom, z1 + 1.0)
    probes = [
        Probe("coffee_space", (0.0, 0.0, z0 + bottom + 0.5 * (height - bottom)), "air", "cavity"),
        Probe(
            "coffee_space_low", (0.0, 0.0, z0 + bottom + 0.15 * (height - bottom)), "air", "cavity"
        ),
        Probe("wall", (0.0, -(radius - wall / 2), 0.1 * height), "material", "thin_wall"),
        Probe("wall_back", (-(radius - wall / 2), 0.0, -0.1 * height), "material", "thin_wall"),
        Probe("bottom", (0.0, 0.0, z0 + bottom / 2), "material", "bottom"),
    ]
    half = np.array([radius, radius, height / 2])
    genus = [0]
    min_feature = min(wall, bottom)
    params: dict[str, float | int | str] = {
        "radius": radius,
        "height": height,
        "wall": wall,
        "bottom": bottom,
        "handle": int(has_handle),
    }
    if has_handle:
        tube = float(np.clip(rng.uniform(0.9, 1.4) * max(wall, 0.05), 0.045, 0.1))
        major = rng.uniform(0.28, 0.38)
        cx = radius + 0.45 * major
        ring = torus_z(major, tube).rotate(rotation_x(np.pi / 2)).translate((cx, 0.0, 0.0))
        handle = ring & halfspace((-1, 0, 0), -(radius - 0.5 * wall))  # keep x >= radius - wall/2
        body = (body | handle) - cylinder_z(radius - wall, z0 + bottom, z1 + 1.0)
        inner_edge = cx + major - tube
        probes.append(
            Probe("handle_passage", ((radius + inner_edge) / 2, 0.0, 0.0), "air", "handle_hole")
        )
        probes.append(Probe("handle_tube", (cx + major, 0.0, 0.0), "material", "handle"))
        half = np.array([cx + major + tube, radius, height / 2])
        genus = [1]
        min_feature = min(min_feature, 2 * tube, inner_edge - radius)
        params.update({"handle_major": major, "handle_tube": tube})
    return _finish(
        f"cup_{variant}", "cup", variant, body, half, 1, genus, probes, min_feature, params, rng
    )


# ----------------------------------------------------------------------- ring
def make_ring(variant: int) -> ShapeSpec:
    rng = np.random.default_rng(_FAMILY_SEED["ring"] + variant)
    tube = _thickness_schedule(variant, 0.03, 0.16, rng) / 2  # tube radius; diameter on ladder
    major = rng.uniform(0.5, 0.75)
    chain = variant % 4 == 3
    if not chain:
        sdf = torus_z(major, tube)
        probes = [
            Probe("ring_hole", (0.0, 0.0, 0.0), "air", "hole"),
            Probe("ring_hole_off", (0.4 * major, -0.3 * major, 0.0), "air", "hole"),
            Probe("tube", (major, 0.0, 0.0), "material", "thin_tube"),
            Probe("tube_2", (-major * 0.6, major * 0.8, 0.0), "material", "thin_tube"),
        ]
        half = np.array([major + tube, major + tube, tube])
        return _finish(
            f"ring_{variant}",
            "ring",
            variant,
            sdf,
            half,
            1,
            [1],
            probes,
            2 * tube,
            {"major": major, "tube": tube, "links": 1},
            rng,
        )
    # Two interlocked links (chain): A in the xy-plane, B in the xz-plane through A's hole.
    a = torus_z(major, tube)
    b = torus_z(major, tube).rotate(rotation_x(np.pi / 2)).translate((major, 0.0, 0.0))
    # Clearance between the two centre circles, measured numerically.
    th = np.linspace(0, 2 * np.pi, 2048, endpoint=False)
    ca = np.stack([major * np.cos(th), major * np.sin(th), 0 * th], axis=1)
    cb = np.stack([major + major * np.cos(th), 0 * th, major * np.sin(th)], axis=1)
    dmin = float(np.min(np.linalg.norm(ca[:, None, :] - cb[None, :, :], axis=2)))
    gap = dmin - 2 * tube
    probes = [
        Probe("link_a_tube", (0.0, major, 0.0), "material", "thin_tube"),
        Probe("link_b_tube", (major, 0.0, major), "material", "thin_tube"),
        Probe("link_a_hole", (-0.5 * major, 0.0, 0.0), "air", "hole"),
        Probe("link_b_hole", (1.5 * major, 0.0, 0.0), "air", "hole"),
    ]
    center_shift = np.array([-0.5 * major, 0.0, 0.0])
    sdf = (a | b).translate(center_shift)
    probes = [
        Probe(p.name, _pt(np.asarray(p.point) + center_shift), p.expect, p.structure)
        for p in probes
    ]
    half = np.array([1.5 * major + tube, major + tube, major + tube])
    return _finish(
        f"ring_{variant}",
        "ring",
        variant,
        sdf,
        half,
        2,
        [1, 1],
        probes,
        min(2 * tube, gap),
        {"major": major, "tube": tube, "links": 2, "link_gap": gap},
        rng,
    )


# ----------------------------------------------------------------- thin shell
def make_thin_shell(variant: int) -> ShapeSpec:
    rng = np.random.default_rng(_FAMILY_SEED["thin_shell"] + variant)
    radius = rng.uniform(0.75, 0.95)
    wall = _thickness_schedule(variant, 0.03, 0.16, rng)
    kind = ("hollow_ball", "bowl", "vented_ball", "two_vent_ball")[variant % 4]
    shell = sphere(radius) - sphere(radius - wall)
    mid = radius - wall / 2
    probes = [
        Probe("shell_bottom", (0.0, 0.0, -mid), "material", "thin_wall"),
        Probe("shell_side", (mid * 0.6, -mid * 0.8, 0.0), "material", "thin_wall"),
    ]
    half = np.array([radius, radius, radius])
    params: dict[str, float | int | str] = {"radius": radius, "wall": wall, "kind": kind}
    if kind == "hollow_ball":
        probes.append(Probe("inner_void", (0.0, 0.0, 0.0), "air", "void"))
        probes.append(
            Probe("inner_void_off", (0.3 * radius, 0.2 * radius, -0.2 * radius), "air", "void")
        )
        comps, genus, sdf = 2, [0, 0], shell
    elif kind == "bowl":
        cut = rng.uniform(0.0, 0.3) * radius
        sdf = shell & halfspace((0, 0, 1), cut)
        probes.append(Probe("bowl_space", (0.0, 0.0, -0.5 * radius + 0.5 * cut), "air", "cavity"))
        half = np.array([radius, radius, radius])
        comps, genus = 1, [0]
        params["cut"] = cut
    else:
        n_vents = 1 if kind == "vented_ball" else 2
        vent_r = rng.uniform(0.18, 0.3) * radius
        sdf = shell
        dirs = [np.array([0.0, 0.0, 1.0]), np.array([1.0, 0.0, 0.0])][:n_vents]
        for k, d in enumerate(dirs):
            sdf = sdf - capsule(d * (radius - 3 * wall - 0.05), d * (radius + 0.3), vent_r)
            probes.append(Probe(f"vent_{k}", _pt(d * mid), "air", "hole"))
        probes.append(Probe("inner_space", (0.0, 0.0, 0.0), "air", "cavity"))
        comps, genus = 1, [n_vents - 1]
        params["vent_radius"] = vent_r
    return _finish(
        f"thin_shell_{variant}",
        "thin_shell",
        variant,
        sdf,
        half,
        comps,
        genus,
        probes,
        wall,
        params,
        rng,
    )


# ---------------------------------------------------------------- holed plate
def make_holed_plate(variant: int) -> ShapeSpec:
    rng = np.random.default_rng(_FAMILY_SEED["holed_plate"] + variant)
    thick = _thickness_schedule(variant, 0.03, 0.16, rng)
    hx, hy = rng.uniform(0.85, 0.95), rng.uniform(0.5, 0.7)
    n_holes = (1, 2, 4, 6)[variant % 4]
    plate = box((hx, hy, thick / 2))
    # Holes on a jittered grid: each stays inside its own cell with clearance.
    cols = min(n_holes, 3)
    rows = int(np.ceil(n_holes / cols))
    cell_w, cell_h = 2 * hx / cols, 2 * hy / rows
    hole_r = float(min(cell_w, cell_h) * rng.uniform(0.18, 0.28))
    centres = np.array(
        [
            (
                -hx + cell_w * (k % cols + 0.5) + rng.uniform(-0.1, 0.1) * cell_w,
                -hy + cell_h * (k // cols + 0.5) + rng.uniform(-0.1, 0.1) * cell_h,
            )
            for k in range(n_holes)
        ]
    )
    sdf = plate
    probes = []
    for k, (cx, cy) in enumerate(centres):
        sdf = sdf - cylinder_z(hole_r, -1.0, 1.0, (cx, cy))
        probes.append(Probe(f"hole_{k}", (float(cx), float(cy), 0.0), "air", "hole"))

    def clearance(pts: FloatArray) -> FloatArray:
        border = np.minimum(hx - np.abs(pts[:, 0]), hy - np.abs(pts[:, 1]))
        dh = np.linalg.norm(pts[:, None, :] - centres[None, :, :], axis=2).min(axis=1) - hole_r
        return np.asarray(np.minimum(border, dh), dtype=np.float64)

    gx, gy = np.meshgrid(np.linspace(-hx, hx, 91), np.linspace(-hy, hy, 61))
    cand = np.stack([gx.ravel(), gy.ravel()], axis=1)
    cl = clearance(cand)
    first = cand[int(np.argmax(cl))]
    far = np.linalg.norm(cand - first, axis=1) > 0.6
    second = cand[int(np.argmax(np.where(far, cl, -np.inf)))]
    for name, pt in (("ligament_a", first), ("ligament_b", second)):
        probes.append(Probe(name, (float(pt[0]), float(pt[1]), 0.0), "material", "thin_wall"))
    # Thinnest ligament: between two holes, or between a hole and the plate border.
    dcc = np.linalg.norm(centres[:, None] - centres[None], axis=2) + np.eye(n_holes) * 1e9
    to_border = np.minimum(hx - np.abs(centres[:, 0]), hy - np.abs(centres[:, 1])) - hole_r
    ligament = float(min(dcc.min() - 2 * hole_r, to_border.min()))
    return _finish(
        f"holed_plate_{variant}",
        "holed_plate",
        variant,
        sdf,
        np.array([hx, hy, thick / 2]),
        1,
        [n_holes],
        probes,
        min(thick, ligament),
        {"thickness": thick, "holes": n_holes, "hole_radius": hole_r, "ligament": ligament},
        rng,
    )


# ----------------------------------------------------------------- multi-part
@dataclass(frozen=True)
class _Part:
    kind: str
    half_x: float  # half extent along x (the arrangement axis)
    half_yz: float
    genus: int
    build: Callable[[float], SDF]
    tube_offset: float = 0.0  # torus only: x offset of the tube centre from the part centre


def _random_part(kind: str, rng: np.random.Generator) -> _Part:
    if kind == "sphere":
        r = rng.uniform(0.12, 0.3)
        return _Part(kind, r, r, 0, lambda c: sphere(r, (c, 0, 0)))
    if kind == "box":
        h = (rng.uniform(0.1, 0.25), rng.uniform(0.15, 0.35), rng.uniform(0.15, 0.35))
        return _Part(kind, h[0], max(h[1], h[2]), 0, lambda c: box(h, (c, 0, 0)))
    if kind == "capsule":
        r, ln = rng.uniform(0.07, 0.15), rng.uniform(0.15, 0.35)
        return _Part(kind, r, ln + r, 0, lambda c: capsule((c, -ln, 0), (c, ln, 0), r))
    maj, mi = rng.uniform(0.15, 0.25), rng.uniform(0.05, 0.08)
    return _Part(kind, maj + mi, maj + mi, 1, lambda c: torus_z(maj, mi, (c, 0, 0)), maj)


def make_multi_part(variant: int) -> ShapeSpec:
    rng = np.random.default_rng(_FAMILY_SEED["multi_part"] + variant)
    n_parts = (2, 3, 4, 5)[variant % 4]
    gap = _thickness_schedule(variant, 0.03, 0.16, rng)
    kinds = ("sphere", "box", "capsule", "torus")
    parts = [
        _random_part("sphere" if k == 0 else kinds[int(rng.integers(0, 4))], rng)
        for k in range(n_parts)
    ]
    # Centres on the x axis: the closest points of neighbouring parts then lie on the
    # axis too (all parts are symmetric about it), so ``gap`` is the exact clearance.
    total = sum(2 * p.half_x for p in parts) + gap * (n_parts - 1)
    x = -total / 2
    sdfs: list[SDF] = []
    probes: list[Probe] = []
    for k, part in enumerate(parts):
        c = x + part.half_x
        sdfs.append(part.build(c))
        if part.kind == "torus":
            probes.append(Probe(f"part{k}_torus_hole", (c, 0.0, 0.0), "air", "hole"))
            probes.append(
                Probe(f"part{k}_tube", (c + part.tube_offset, 0.0, 0.0), "material", "part")
            )
        else:
            probes.append(Probe(f"part{k}_core", (c, 0.0, 0.0), "material", "part"))
        if k > 0:
            probes.append(Probe(f"gap_{k - 1}_{k}", (x - gap / 2, 0.0, 0.0), "air", "gap"))
        x += 2 * part.half_x + gap
    half_yz = max(p.half_yz for p in parts)
    return _finish(
        f"multi_part_{variant}",
        "multi_part",
        variant,
        union(*sdfs),
        np.array([total / 2, half_yz, half_yz]),
        n_parts,
        [p.genus for p in parts],
        probes,
        gap,
        {"parts": n_parts, "gap": gap, "kinds": ",".join(p.kind for p in parts)},
        rng,
    )


# --------------------------------------------------------------------- helmet
def _slot(d: FloatArray, side: FloatArray, half_len: float, r: float, u0: float, u1: float) -> SDF:
    """Stadium-shaped slot (segment of half length ``half_len`` along ``side``, radius
    ``r``) extruded along the unit direction ``d`` from ``u0`` to ``u1``."""
    up = np.cross(d, side)

    def f(p: FloatArray) -> FloatArray:
        u, v, w = p @ d, p @ side, p @ up
        stadium = np.hypot(np.maximum(np.abs(v) - half_len, 0.0), w) - r
        slab = np.maximum(u0 - u, u - u1)
        return np.asarray(np.maximum(stadium, slab), dtype=np.float64)

    return SDF(f)


def make_helmet(variant: int) -> ShapeSpec:
    rng = np.random.default_rng(_FAMILY_SEED["helmet"] + variant)
    radius = rng.uniform(0.8, 0.95)
    wall = _thickness_schedule(variant, 0.03, 0.14, rng)
    skirt = rng.uniform(0.45, 0.6) * radius  # the shell reaches down to z = -skirt
    n_slits = (1, 2, 2, 3)[variant % 4]
    crest = variant % 2 == 1
    # Rim cut by a cone through the centre, not a plane: a planar cut below the equator
    # leaves an acute wedge on the inner rim (marching cubes then emits isolated specks).
    shell = (sphere(radius) - sphere(radius - wall)) & polar_cap(
        0.5 * np.pi + float(np.arcsin(skirt / radius))
    )
    mid = radius - wall / 2
    probes = [
        Probe("head_space", (0.0, 0.0, 0.1 * radius), "air", "cavity"),
        Probe("head_space_low", (0.0, 0.0, -0.5 * skirt), "air", "cavity"),
        Probe("dome", (0.0, 0.0, mid), "material", "thin_wall"),
        Probe("back", (0.0, -mid * np.cos(0.3), mid * np.sin(0.3)), "material", "thin_wall"),
    ]
    elev = rng.uniform(0.05, 0.2)
    slit_r = rng.uniform(0.06, 0.08)
    slit_half = rng.uniform(0.08, 0.13)
    layout = {
        1: [(0.0, elev)],
        2: [(-0.35, elev), (0.35, elev)],
        3: [(-0.35, elev), (0.35, elev), (0.0, elev - 0.32)],
    }[n_slits]
    sdf = shell
    for k, (az, el) in enumerate(layout):
        d = np.array([np.sin(az) * np.cos(el), np.cos(az) * np.cos(el), np.sin(el)])
        side = np.array([np.cos(az), -np.sin(az), 0.0])
        sdf = sdf - _slot(d, side, slit_half, slit_r, radius - wall - 0.15, radius + 0.15)
        probes.append(Probe(f"eye_slit_{k}", _pt(d * mid), "air", "hole"))
    top = radius
    params: dict[str, float | int | str] = {
        "radius": radius,
        "wall": wall,
        "slits": n_slits,
        "crest": int(crest),
        "skirt": skirt,
    }
    if crest:
        fin_h = rng.uniform(0.12, 0.2)
        fin_t = max(wall, 0.05)
        fin = box((fin_t / 2, 0.55 * radius, fin_h / 2 + 0.1), (0.0, 0.0, radius + fin_h / 2 - 0.1))
        sdf = sdf | ((fin & sphere(radius + fin_h)) - sphere(radius - wall))
        probes.append(Probe("crest", (0.0, 0.0, radius + 0.5 * fin_h), "material", "crest"))
        top = radius + fin_h
        params["crest_height"] = fin_h
    half = np.array([radius, radius, max(top, skirt)])
    # Centre the bounding box vertically is not needed: bounds are symmetric and padded.
    return _finish(
        f"helmet_{variant}",
        "helmet",
        variant,
        sdf,
        half,
        1,
        [n_slits],
        probes,
        min(wall, 2 * slit_r),
        params,
        rng,
    )


_BUILDERS: dict[str, Callable[[int], ShapeSpec]] = {
    "cup": make_cup,
    "ring": make_ring,
    "thin_shell": make_thin_shell,
    "holed_plate": make_holed_plate,
    "multi_part": make_multi_part,
    "helmet": make_helmet,
}


#: Variants 0-7 are the G1 round-trip set; 100-103 are the G2 selection set.  The seeds
#: (family seed + variant) never overlap, so no G2 object is a G1 object (proposal §5.1).
G2_VARIANTS = (100, 101, 102, 103)
SPLIT_G2 = "g2_selection"


def split_of_variant(variant: int) -> str:
    return SPLIT if variant < 100 else SPLIT_G2


def g2_shape_ids() -> list[str]:
    return [f"{fam}_{v}" for fam in FAMILIES for v in G2_VARIANTS]


def build_shape(shape_id: str) -> ShapeSpec:
    family, _, variant = shape_id.rpartition("_")
    if family not in _BUILDERS:
        raise KeyError(f"unknown shape family in {shape_id!r}")
    return _BUILDERS[family](int(variant))


def g1_shape_ids() -> list[str]:
    return [f"{fam}_{v}" for fam in FAMILIES for v in range(VARIANTS_PER_FAMILY)]

"""GLSL technique RAG — proven, convention-conformant shader building blocks the
shader stage retrieves and composes, instead of the LLM inventing weak grids.

Techniques are canonical (IQ cosine palettes, fbm domain warping, aurora, volumetric
haze, voronoi, starfield, flow), adapted to the WEGEK background-shader convention:
  available: float snoise(vec2); float fbm(vec2);
  uniforms : float u_time; vec2 u_mouse; vec2 u_resolution; vec3 u_color0..2;
  varying  : vec2 vUv;  output: gl_FragColor;  no texture samplers.
Sourced/derived from public-domain shader work (Inigo Quilez, The Book of Shaders,
Ashima webgl-noise) — used as reference snippets the model adapts and blends.
"""
from __future__ import annotations

import re

TECHNIQUES: list[dict] = [
    {
        "id": "iq_cosine_palette",
        "title": "IQ cosine palette (rich, controllable colour gradients)",
        "tags": "color palette gradient vibrant smooth iridescent rainbow tone mapping warm cool any",
        "snippet": (
            "// Inigo Quilez cosine palette — feed a scalar t to get a smooth colour.\n"
            "vec3 pal(float t, vec3 a, vec3 b, vec3 c, vec3 d){ return a + b*cos(6.28318*(c*t+d)); }\n"
            "// usage: drive t by fbm/height, bias the palette toward u_color0..2\n"
            "vec3 col = pal(t, vec3(0.5), vec3(0.5), vec3(1.0), vec3(0.0,0.33,0.67));\n"
            "col = mix(col, u_color1, 0.4); // tint toward brand accent"
        ),
    },
    {
        "id": "domain_warp",
        "title": "fbm domain warping (organic, flowing fields — no grids)",
        "tags": "domain warp organic flow liquid smoke cloud nebula fluid soft premium swirl flow",
        "snippet": (
            "// IQ domain warping: warp the lookup of fbm by fbm for organic flow.\n"
            "vec2 p = vUv*3.0; p.x *= u_resolution.x/u_resolution.y;\n"
            "vec2 q = vec2(fbm(p + 0.0), fbm(p + vec2(5.2,1.3)));\n"
            "vec2 r = vec2(fbm(p + 4.0*q + vec2(1.7,9.2) + 0.15*u_time),\n"
            "              fbm(p + 4.0*q + vec2(8.3,2.8) + 0.12*u_time));\n"
            "float f = fbm(p + 4.0*r);\n"
            "vec3 col = mix(u_color0, u_color2, clamp(f*f*1.6,0.0,1.0));\n"
            "col = mix(col, u_color1, clamp(length(q),0.0,1.0)*0.5);"
        ),
    },
    {
        "id": "aurora_curtains",
        "title": "Aurora / nebula curtains (vertical luminous bands)",
        "tags": "aurora nebula curtain bands glow cosmic space ethereal northern lights cyber teal violet",
        "snippet": (
            "vec3 col = u_color0;\n"
            "for(float i=0.0;i<4.0;i++){\n"
            "  float o = i*1.3;\n"
            "  float n = fbm(vec2(vUv.x*3.0 + o, vUv.y*1.5 - u_time*0.15 + o));\n"
            "  float band = smoothstep(0.0,0.6, n) * smoothstep(1.0,0.4, vUv.y + n*0.3);\n"
            "  vec3 tint = mix(u_color1, u_color2, i/3.0);\n"
            "  col += tint * band * 0.35;\n"
            "}"
        ),
    },
    {
        "id": "volumetric_haze_vignette",
        "title": "Volumetric depth haze + vignette (dark, atmospheric, product-first)",
        "tags": "volumetric haze fog depth dark moody atmospheric vignette minimal premium dark cinematic",
        "snippet": (
            "vec2 uv = vUv - 0.5; uv.x *= u_resolution.x/u_resolution.y;\n"
            "float haze = fbm(uv*2.5 + vec2(0.0, u_time*0.05));\n"
            "haze += 0.5*fbm(uv*5.0 - u_time*0.03);\n"
            "vec3 col = mix(u_color0, u_color2, haze*0.5);\n"
            "float vig = smoothstep(0.95,0.25, length(uv));\n"
            "col *= vig; col = mix(col, u_color0, 1.0-vig);"
        ),
    },
    {
        "id": "starfield",
        "title": "Twinkling starfield (deep space dust)",
        "tags": "stars starfield space dust sparkle night cosmic dark particles points twinkle",
        "snippet": (
            "float hash(vec2 p){ return fract(sin(dot(p,vec2(127.1,311.7)))*43758.5453); }\n"
            "vec2 g = vUv * vec2(u_resolution.x/u_resolution.y,1.0) * 80.0;\n"
            "vec2 id = floor(g); float h = hash(id);\n"
            "float star = step(0.985, h) * (0.5+0.5*sin(u_time*2.0 + h*30.0));\n"
            "float d = length(fract(g)-0.5);\n"
            "vec3 col = u_color0 + u_color1 * star * smoothstep(0.5,0.0,d);"
        ),
    },
    {
        "id": "voronoi_cells",
        "title": "Voronoi cells (tech / crystalline / cellular structure)",
        "tags": "voronoi cells crystalline tech grid-alternative cellular shards facets structure gaming",
        "snippet": (
            "float voro(vec2 x){ vec2 n=floor(x), f=fract(x); float md=1.0;\n"
            "  for(int j=-1;j<=1;j++)for(int i=-1;i<=1;i++){ vec2 g=vec2(float(i),float(j));\n"
            "    vec2 o=vec2(fract(sin(dot(n+g,vec2(127.1,311.7)))*43758.5453));\n"
            "    o=0.5+0.5*sin(u_time*0.6+6.2831*o); vec2 r=g+o-f; md=min(md,dot(r,r)); }\n"
            "  return sqrt(md); }\n"
            "float v = voro(vUv*6.0*vec2(u_resolution.x/u_resolution.y,1.0));\n"
            "vec3 col = mix(u_color2, u_color1, smoothstep(0.0,0.7,v)); col = mix(u_color0,col,0.7);"
        ),
    },
    {
        "id": "flow_streaks",
        "title": "Directional flow streaks (energy / speed / motion)",
        "tags": "flow streaks energy speed motion lines streaming kinetic dynamic light trails",
        "snippet": (
            "vec2 uv = vUv; float n = fbm(vec2(uv.x*8.0, uv.y*2.0 - u_time*0.4));\n"
            "float streak = smoothstep(0.45,0.55, fract(uv.y*6.0 + n));\n"
            "vec3 col = mix(u_color0, u_color1, streak*0.6);\n"
            "col += u_color2 * pow(streak,3.0) * 0.4;"
        ),
    },
]


def _tok(s: str) -> list[str]:
    return [t for t in re.split(r"[^a-z0-9]+", s.lower()) if len(t) > 2]


def retrieve(query: str, k: int = 3) -> list[dict]:
    q = set(_tok(query))
    scored = []
    for e in TECHNIQUES:
        hay = _tok(e["tags"] + " " + e["title"])
        score = sum(hay.count(t) for t in q) + 2 * len(q & set(_tok(e["tags"])))
        scored.append((score, e))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [e for s, e in scored[:k] if s > 0] or TECHNIQUES[:k]


def format_block(techs: list[dict]) -> str:
    lines = ["PROVEN GLSL BUILDING BLOCKS (these conform to the convention — adapt and COMBINE "
             "2-3 of them into one cohesive background; do not paste verbatim, blend with the palette):"]
    for t in techs:
        lines.append(f"\n// === {t['title']} ===\n{t['snippet']}")
    return "\n".join(lines)

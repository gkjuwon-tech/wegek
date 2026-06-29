"""Curated GLSL fragment-shader library for animated website backgrounds.

Every shader is a real, drop-in Three.js `ShaderMaterial` fragment shader using
the standard uniform convention: `u_time` (float), `u_mouse` (vec2, normalized),
`u_resolution` (vec2) and `u_color0..u_color2` (vec3 palette colours).

These are used directly when no LLM key is present, and as few-shot references /
fallback when the LLM shader generator (Stage 4) is enabled.
"""
from __future__ import annotations

# Shared simplex-ish noise helpers prepended to every shader.
NOISE_CHUNK = """
vec3 mod289(vec3 x){return x-floor(x*(1.0/289.0))*289.0;}
vec2 mod289(vec2 x){return x-floor(x*(1.0/289.0))*289.0;}
vec3 permute(vec3 x){return mod289(((x*34.0)+1.0)*x);}
float snoise(vec2 v){
  const vec4 C=vec4(0.211324865,0.366025403,-0.577350269,0.024390243);
  vec2 i=floor(v+dot(v,C.yy));
  vec2 x0=v-i+dot(i,C.xx);
  vec2 i1=(x0.x>x0.y)?vec2(1.0,0.0):vec2(0.0,1.0);
  vec4 x12=x0.xyxy+C.xxzz; x12.xy-=i1;
  i=mod289(i);
  vec3 p=permute(permute(i.y+vec3(0.0,i1.y,1.0))+i.x+vec3(0.0,i1.x,1.0));
  vec3 m=max(0.5-vec3(dot(x0,x0),dot(x12.xy,x12.xy),dot(x12.zw,x12.zw)),0.0);
  m=m*m; m=m*m;
  vec3 x=2.0*fract(p*C.www)-1.0;
  vec3 h=abs(x)-0.5; vec3 ox=floor(x+0.5); vec3 a0=x-ox;
  m*=1.79284291-0.85373472*(a0*a0+h*h);
  vec3 g; g.x=a0.x*x0.x+h.x*x0.y;
  g.yz=a0.yz*x12.xz+h.yz*x12.yw;
  return 130.0*dot(m,g);
}
float fbm(vec2 p){
  float v=0.0; float a=0.5;
  for(int i=0;i<5;i++){ v+=a*snoise(p); p*=2.0; a*=0.5; }
  return v;
}
"""

_HEADER = """
precision highp float;
varying vec2 vUv;
uniform float u_time;
uniform vec2  u_mouse;
uniform vec2  u_resolution;
uniform vec3  u_color0;
uniform vec3  u_color1;
uniform vec3  u_color2;
"""

SHADERS: dict[str, str] = {}


def _register(name: str, body: str) -> None:
    SHADERS[name] = _HEADER + NOISE_CHUNK + body


_register(
    "gradient_noise_dark",
    """
void main(){
  vec2 uv = vUv;
  vec2 m = (u_mouse - 0.5) * 0.6;
  float n = fbm(uv * 3.0 + m + vec2(0.0, u_time * 0.05));
  float n2 = fbm(uv * 1.5 - vec2(u_time * 0.03, 0.0));
  float t = smoothstep(-0.6, 0.8, n + uv.y * 0.6);
  vec3 col = mix(u_color0, u_color1, t);
  col = mix(col, u_color2, smoothstep(0.4, 1.0, n2) * 0.35);
  float vig = smoothstep(1.3, 0.2, length(uv - 0.5));
  col *= 0.55 + 0.45 * vig;
  gl_FragColor = vec4(col, 1.0);
}
""",
)

_register(
    "dark_particle_drift",
    """
float layer(vec2 uv, float scale, float speed, float seed){
  uv *= scale;
  uv.y += u_time * speed;
  vec2 g = floor(uv);
  vec2 f = fract(uv);
  float acc = 0.0;
  for(int y=-1;y<=1;y++) for(int x=-1;x<=1;x++){
    vec2 o = vec2(float(x), float(y));
    vec2 cell = g + o;
    float r = fract(sin(dot(cell, vec2(127.1,311.7)) + seed) * 43758.5453);
    vec2 p = o + vec2(r, fract(r*7.0)) - f;
    float d = length(p);
    acc += smoothstep(0.18, 0.0, d) * (0.4 + 0.6*r);
  }
  return acc;
}
void main(){
  vec2 uv = vUv;
  vec2 m = (u_mouse - 0.5);
  vec3 col = mix(u_color0, u_color0*0.4, uv.y);
  float bg = fbm(uv*2.0 + m*0.4 + u_time*0.02);
  col += u_color2 * smoothstep(0.2,0.9,bg) * 0.08;
  float p = layer(uv + m*0.05, 8.0, 0.04, 1.0)
          + layer(uv + m*0.1, 14.0, 0.07, 9.0)*0.6;
  col += u_color1 * p * 0.7;
  gl_FragColor = vec4(col, 1.0);
}
""",
)

_register(
    "neon_cyber",
    """
void main(){
  vec2 uv = vUv;
  vec2 m = (u_mouse - 0.5) * 2.0;
  vec2 p = (uv - 0.5);
  p.x *= u_resolution.x / max(u_resolution.y, 1.0);
  float grid = 0.0;
  vec2 gp = p * 12.0 + vec2(0.0, u_time*0.6) + m;
  vec2 gf = abs(fract(gp) - 0.5);
  float line = min(gf.x, gf.y);
  grid = smoothstep(0.06, 0.0, line);
  float glow = exp(-3.0*length(p - m*0.1));
  vec3 col = u_color0;
  col += mix(u_color1, u_color2, uv.x) * grid * 0.8;
  col += u_color1 * glow * 0.6;
  col += u_color2 * pow(max(0.0,1.0-length(p)),3.0)*0.3;
  gl_FragColor = vec4(col, 1.0);
}
""",
)

_register(
    "aurora_nebula",
    """
void main(){
  vec2 uv = vUv;
  vec2 m = (u_mouse - 0.5);
  vec3 col = u_color0;
  for(float i=1.0;i<=4.0;i++){
    float n = fbm(uv*vec2(2.0,3.0)*i + vec2(u_time*0.05*i, -u_time*0.03) + m);
    float band = smoothstep(0.1, 0.6, n) * (1.0/i);
    vec3 c = mix(u_color1, u_color2, fract(i*0.37 + n));
    col += c * band * 0.5;
  }
  float stars = step(0.995, fract(sin(dot(floor(uv*vec2(220.0)),vec2(12.9,78.2)))*43758.0));
  col += vec3(stars) * 0.6;
  gl_FragColor = vec4(col, 1.0);
}
""",
)

_register(
    "silk_gradient_warm",
    """
void main(){
  vec2 uv = vUv;
  vec2 m = (u_mouse - 0.5)*0.5;
  float w = sin(uv.x*4.0 + u_time*0.4 + fbm(uv*2.0+m)*3.0)*0.5+0.5;
  float w2 = fbm(uv*2.5 + vec2(u_time*0.04, 0.0) + m);
  vec3 col = mix(u_color0, u_color1, smoothstep(0.0,1.0,uv.y*0.7 + w*0.3));
  col = mix(col, u_color2, smoothstep(0.3,0.9,w2)*0.4);
  col *= 0.7 + 0.3*w;
  gl_FragColor = vec4(col, 1.0);
}
""",
)

_register(
    "volumetric_fog_dark",
    """
void main(){
  vec2 uv = vUv;
  vec2 m = (u_mouse - 0.5);
  float d = 0.0; float a = 0.6; vec2 p = uv*3.0 + m*0.5;
  for(int i=0;i<6;i++){ d += a*abs(snoise(p + u_time*0.05)); p*=1.8; a*=0.55; }
  vec3 col = mix(u_color0, u_color1, smoothstep(0.2,1.4,d));
  col = mix(col, u_color2, smoothstep(0.8,1.6,d)*0.5);
  col *= smoothstep(1.4,0.1,length(uv-vec2(0.5)));
  gl_FragColor = vec4(col, 1.0);
}
""",
)

_register(
    "color_burst_dynamic",
    """
void main(){
  vec2 uv = vUv;
  vec2 m = (u_mouse - 0.5);
  vec2 p = uv - 0.5 - m*0.15;
  float ang = atan(p.y, p.x);
  float rad = length(p);
  float w = sin(ang*6.0 + u_time*0.8 + rad*8.0)*0.5+0.5;
  float n = fbm(uv*3.0 + u_time*0.04);
  vec3 col = mix(u_color0, u_color1, w*smoothstep(0.6,0.0,rad));
  col = mix(col, u_color2, n*0.4);
  col += u_color1 * exp(-6.0*rad)*0.5;
  gl_FragColor = vec4(col, 1.0);
}
""",
)

_register(
    "minimal_light",
    """
void main(){
  vec2 uv = vUv;
  vec2 m = (u_mouse - 0.5)*0.4;
  float n = fbm(uv*2.0 + m + u_time*0.02);
  vec3 base = mix(u_color2, u_color0, uv.y*0.15 + n*0.05);
  base = mix(base, u_color1, smoothstep(0.85,1.0,n)*0.06);
  gl_FragColor = vec4(base, 1.0);
}
""",
)

DEFAULT_SHADER = "gradient_noise_dark"


def get_shader(name: str) -> str:
    return SHADERS.get(name, SHADERS[DEFAULT_SHADER])

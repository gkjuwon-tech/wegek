// WEGEK runtime engine — turns a site plan into a live 3D scrollytelling site.
// Loaded as an ES module. Reads window.__WEGEK__ (plan + presets + shader).
import * as THREE from "three";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";
import { RoundedBoxGeometry } from "three/addons/geometries/RoundedBoxGeometry.js";
import { RoomEnvironment } from "three/addons/environments/RoomEnvironment.js";
import { RectAreaLightUniformsLib } from "three/addons/lights/RectAreaLightUniformsLib.js";
import { EffectComposer } from "three/addons/postprocessing/EffectComposer.js";
import { RenderPass } from "three/addons/postprocessing/RenderPass.js";
import { UnrealBloomPass } from "three/addons/postprocessing/UnrealBloomPass.js";
import { ShaderPass } from "three/addons/postprocessing/ShaderPass.js";
import { OutputPass } from "three/addons/postprocessing/OutputPass.js";

// gsap, ScrollTrigger and Lenis are loaded as UMD globals (vendored locally).
const gsap = window.gsap;
const ScrollTrigger = window.ScrollTrigger;
const Lenis = window.Lenis;

gsap.registerPlugin(ScrollTrigger);
RectAreaLightUniformsLib.init();

const BUNDLE = window.__WEGEK__;
const PLAN = BUNDLE.plan;
const LIGHTING = BUNDLE.lighting;
const CAMERAS = BUNDLE.cameras;
const SHADER = BUNDLE.shader;
// AI-authored effect parameters (the engine only executes; the art direction —
// particle look, bloom, fog, colour grade, exposure — comes from the spec).
const EFF = PLAN.effects || {};
const P_EFF = EFF.particles || {};
const B_EFF = EFF.bloom || {};
const F_EFF = EFF.fog || {};
const G_EFF = EFF.grade || {};
const num = (v, d) => (typeof v === "number" ? v : d);

const lerp = (a, b, t) => a + (b - a) * t;
const clamp01 = (x) => Math.max(0, Math.min(1, x));
const damp = (cur, target, lambda, dt) => lerp(cur, target, 1 - Math.exp(-lambda * dt));
const hexToRGB = (hex) => {
  const c = new THREE.Color(hex);
  return [c.r, c.g, c.b];
};

// --------------------------------------------------------------------------
// Renderer
// --------------------------------------------------------------------------
const canvas = document.getElementById("wegek-canvas");
const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: false });
renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
renderer.setSize(window.innerWidth, window.innerHeight);
renderer.toneMapping = THREE.ACESFilmicToneMapping;
renderer.toneMappingExposure = num(EFF.exposure, 1.0);

const palette = PLAN.global_style.color_palette;
const ACCENT = new THREE.Color(palette[1] || "#e94560");
const SECONDARY = new THREE.Color(palette[2] || "#3a86ff");

// --------------------------------------------------------------------------
// Background shader (rendered as its own full-screen pass inside the composer)
// --------------------------------------------------------------------------
const bgScene = new THREE.Scene();
const bgCamera = new THREE.OrthographicCamera(-1, 1, 1, -1, 0, 1);
const bgUniforms = {
  u_time: { value: 0 },
  u_mouse: { value: new THREE.Vector2(0.5, 0.5) },
  u_resolution: { value: new THREE.Vector2(window.innerWidth, window.innerHeight) },
  u_color0: { value: new THREE.Vector3(...hexToRGB(palette[0] || "#0a0a0f")) },
  u_color1: { value: new THREE.Vector3(...hexToRGB(palette[1] || "#e94560")) },
  u_color2: { value: new THREE.Vector3(...hexToRGB(palette[2] || "#0f3460")) },
  u_dim: { value: 0.55 }, // tame loud background presets so the product leads
};
const bgMaterial = new THREE.ShaderMaterial({
  uniforms: bgUniforms,
  vertexShader: "varying vec2 vUv; void main(){ vUv = uv; gl_Position = vec4(position, 1.0); }",
  fragmentShader: SHADER,
  depthTest: false,
  depthWrite: false,
});
bgScene.add(new THREE.Mesh(new THREE.PlaneGeometry(2, 2), bgMaterial));

// --------------------------------------------------------------------------
// Main scene + camera + image-based lighting
// --------------------------------------------------------------------------
const scene = new THREE.Scene();
// Atmospheric depth — distant particles/geometry dissolve into the bg tone.
scene.fog = new THREE.FogExp2(new THREE.Color(F_EFF.color || palette[0] || "#06080d"), num(F_EFF.density, 0.05));
const pmrem = new THREE.PMREMGenerator(renderer);
pmrem.compileEquirectangularShader();
scene.environment = pmrem.fromScene(new RoomEnvironment(), 0.04).texture;

const camera = new THREE.PerspectiveCamera(45, window.innerWidth / window.innerHeight, 0.1, 100);
camera.position.set(0, 0.6, 7);
const camTarget = new THREE.Vector3(0, 0, 0);

const lightGroup = new THREE.Group();
scene.add(lightGroup);

// Always-on coloured rim rig so metallic products read as chrome regardless of preset.
const rimA = new THREE.PointLight(ACCENT, 18, 0, 1.4);
rimA.position.set(-4, 1.5, -3);
const rimB = new THREE.PointLight(SECONDARY, 16, 0, 1.4);
rimB.position.set(4, -1, -2);
scene.add(rimA, rimB);

function buildLights(presetName) {
  lightGroup.clear();
  const preset = LIGHTING[presetName] || Object.values(LIGHTING)[0];
  if (preset.ambient) {
    lightGroup.add(new THREE.AmbientLight(preset.ambient.color || "#ffffff", preset.ambient.intensity));
  }
  for (const l of preset.lights || []) {
    let light;
    const color = l.color || "#ffffff";
    switch (l.type) {
      case "spot":
        light = new THREE.SpotLight(color, l.intensity * 6, 0, l.angle || 0.5, 0.4, 1.2);
        if (l.position) light.position.set(...l.position);
        light.target.position.set(0, 0, 0);
        lightGroup.add(light.target);
        break;
      case "point":
        light = new THREE.PointLight(color, l.intensity * 4, 0, 1.2);
        if (l.position) light.position.set(...l.position);
        break;
      case "directional":
        light = new THREE.DirectionalLight(color, l.intensity);
        if (l.position) light.position.set(...l.position);
        break;
      case "hemisphere":
        light = new THREE.HemisphereLight(l.skyColor || "#ffffff", l.groundColor || "#444444", l.intensity);
        if (l.position) light.position.set(...l.position);
        break;
      case "area":
      default: {
        light = new THREE.RectAreaLight(color, l.intensity * 4, l.width || 5, l.height || 5);
        if (l.position) light.position.set(...l.position);
        light.lookAt(0, 0, 0);
        break;
      }
    }
    lightGroup.add(light);
  }
}

// --------------------------------------------------------------------------
// Particle field — drifting motes, additive so bloom makes them glow.
// --------------------------------------------------------------------------
function buildParticles() {
  const N = Math.max(0, Math.floor(num(P_EFF.count, 20000)));
  if (N === 0) return new THREE.Points(new THREE.BufferGeometry(), new THREE.PointsMaterial());
  const SPREAD = num(P_EFF.spread, 4.2);
  const pos = new Float32Array(N * 3);
  const col = new Float32Array(N * 3);
  const seed = new Float32Array(N);
  const c = new THREE.Color();
  for (let i = 0; i < N; i++) {
    // Two populations: a dense central "cloud" and a sparse ambient field, so it
    // reads as a shimmering volume around the product rather than even noise.
    const central = Math.random() < 0.6;
    if (central) {
      const r = Math.pow(Math.random(), 0.6) * SPREAD;
      const th = Math.random() * Math.PI * 2;
      const ph = Math.acos(2 * Math.random() - 1);
      pos[i * 3] = Math.sin(ph) * Math.cos(th) * r;
      pos[i * 3 + 1] = Math.cos(ph) * r * 0.8;
      pos[i * 3 + 2] = Math.sin(ph) * Math.sin(th) * r;
    } else {
      pos[i * 3] = (Math.random() - 0.5) * 30;
      pos[i * 3 + 1] = (Math.random() - 0.5) * 18;
      pos[i * 3 + 2] = (Math.random() - 0.5) * 26 - 3;
    }
    // iridescent tint: lerp across accent..secondary..white with a hue jitter
    const t = Math.random();
    c.copy(ACCENT).lerp(SECONDARY, t);
    c.offsetHSL((Math.random() - 0.5) * 0.12, 0.1, Math.random() * 0.35);
    col[i * 3] = c.r; col[i * 3 + 1] = c.g; col[i * 3 + 2] = c.b;
    seed[i] = Math.random() * 6.28;
  }
  const g = new THREE.BufferGeometry();
  g.setAttribute("position", new THREE.BufferAttribute(pos, 3));
  g.setAttribute("color", new THREE.BufferAttribute(col, 3));
  const m = new THREE.PointsMaterial({
    size: num(P_EFF.size, 0.022), vertexColors: true, transparent: true,
    opacity: num(P_EFF.opacity, 0.8), depthWrite: false,
    blending: THREE.AdditiveBlending, sizeAttenuation: true,
  });
  const points = new THREE.Points(g, m);
  points.userData = { basePos: pos.slice(0), seed };
  scene.add(points);
  return points;
}
const particles = buildParticles();

// --------------------------------------------------------------------------
// Object factory (procedural primitives + GLB), built once and persistent.
// --------------------------------------------------------------------------
const loader = new GLTFLoader();

function makeMaterial(color) {
  // Iridescent chrome/glass — the holographic thin-film look, not matte metal.
  return new THREE.MeshPhysicalMaterial({
    color: color || "#cdd2dc", metalness: 0.85, roughness: 0.18, envMapIntensity: 1.25,
    clearcoat: 1.0, clearcoatRoughness: 0.15, iridescence: 1.0, iridescenceIOR: 1.6,
    iridescenceThicknessRange: [120, 520],
  });
}

function primitiveGeometry(kind) {
  switch (kind) {
    case "torus": return new THREE.TorusGeometry(1, 0.38, 48, 120);
    case "torus_knot": return new THREE.TorusKnotGeometry(0.85, 0.28, 200, 32);
    case "capsule": return new THREE.CapsuleGeometry(0.7, 1.4, 16, 32);
    case "cylinder": return new THREE.CylinderGeometry(0.8, 0.8, 1.6, 64);
    case "icosahedron": return new THREE.IcosahedronGeometry(1.2, 1);
    case "octahedron": return new THREE.OctahedronGeometry(1.3, 0);
    case "diamond": return new THREE.OctahedronGeometry(1.2, 0);
    case "box": return new THREE.BoxGeometry(1.6, 1.6, 1.6);
    case "rounded_box":
    default: return new RoundedBoxGeometry(1.7, 1.1, 0.5, 6, 0.18);
  }
}

function buildObjectNode(objSpec) {
  const holder = new THREE.Group();
  if (objSpec.model_format === "glb" && objSpec.model_url) {
    loader.load(
      objSpec.model_url,
      (gltf) => {
        const model = gltf.scene;
        const box = new THREE.Box3().setFromObject(model);
        const size = box.getSize(new THREE.Vector3());
        const s = 2.4 / (Math.max(size.x, size.y, size.z) || 1);
        model.scale.setScalar(s);
        const center = box.getCenter(new THREE.Vector3());
        model.position.sub(center.multiplyScalar(s));
        model.traverse((c) => {
          if (c.isMesh && c.material) {
            const mats = Array.isArray(c.material) ? c.material : [c.material];
            for (const m of mats) {
              m.transparent = false; m.depthWrite = true;
              if ("envMapIntensity" in m) m.envMapIntensity = 1.1;
              if ("metalness" in m && m.metalness < 0.2) m.metalness = 0.6;
            }
          }
        });
        holder.add(model);
      },
      undefined,
      () => holder.add(new THREE.Mesh(primitiveGeometry(objSpec.primitive), makeMaterial(objSpec.color))),
    );
  } else {
    holder.add(new THREE.Mesh(primitiveGeometry(objSpec.primitive), makeMaterial(objSpec.color)));
  }
  return holder;
}

// One persistent node per unique object. Sections retarget its pose; it travels
// smoothly between them (no cross-fade duplicates → no ghosting).
const objectNodes = new Map();
function buildObjects() {
  for (const spec of PLAN.objects) {
    const node = buildObjectNode(spec);
    node.userData.spec = spec;
    node.userData.cur = { px: 0, py: 0, pz: 0, rx: 0, ry: 0, rz: 0, sc: 0.001 };
    node.scale.setScalar(0.001);
    scene.add(node);
    objectNodes.set(spec.id, node);
  }
}

function sectionPose(sec, oid) {
  const L = (sec.object_layout || {})[oid] || {};
  return { pos: L.position || [0, 0, 0], rot: L.rotation || [0, 0, 0], scale: L.scale ?? 1 };
}

// --------------------------------------------------------------------------
// Animation sampling (object keyframes = micro-motion deltas)
// --------------------------------------------------------------------------
function sampleTrack(keyframes, t) {
  if (!keyframes || keyframes.length === 0) return null;
  if (t <= keyframes[0].t) return keyframes[0];
  for (let i = 0; i < keyframes.length - 1; i++) {
    const a = keyframes[i], b = keyframes[i + 1];
    if (t >= a.t && t <= b.t) {
      const f = (t - a.t) / (b.t - a.t || 1);
      const l3 = (x, y) => x.map((v, j) => lerp(v, y[j], f));
      return {
        rotation: l3(a.rotation, b.rotation), position: l3(a.position, b.position),
        scale: lerp(a.scale ?? 1, b.scale ?? 1, f), explode: lerp(a.explode ?? 0, b.explode ?? 0, f),
      };
    }
  }
  return keyframes[keyframes.length - 1];
}

function sampleCamera(preset, localT) {
  if (!preset) return { pos: new THREE.Vector3(0, 0.6, 7), look: new THREE.Vector3(0, 0, 0), fov: 45 };
  const kfs = preset.keyframes || [];
  if (kfs.length === 0 && preset.type === "orbit") {
    const d = preset.distance || 6;
    const a = performance.now() * 0.0002 * (preset.autoRotateSpeed || 0.4);
    return { pos: new THREE.Vector3(Math.sin(a) * d, 1.0, Math.cos(a) * d), look: new THREE.Vector3(0, 0, 0), fov: preset.fov || 45 };
  }
  if (kfs.length === 0 && preset.position) {
    return { pos: new THREE.Vector3(...preset.position), look: new THREE.Vector3(...(preset.lookAt || [0, 0, 0])), fov: preset.fov || 45 };
  }
  if (kfs.length === 0) return { pos: new THREE.Vector3(0, 0.6, 7), look: new THREE.Vector3(0, 0, 0), fov: 45 };
  let a = kfs[0], b = kfs[kfs.length - 1];
  for (let i = 0; i < kfs.length - 1; i++) {
    if (localT >= kfs[i].scroll && localT <= kfs[i + 1].scroll) { a = kfs[i]; b = kfs[i + 1]; break; }
  }
  const f = clamp01((localT - a.scroll) / ((b.scroll - a.scroll) || 1));
  const mix = (x, y) => x.map((v, j) => lerp(v, y[j], f));
  return {
    pos: new THREE.Vector3(...mix(a.position, b.position)),
    look: new THREE.Vector3(...mix(a.lookAt, b.lookAt)),
    fov: lerp(a.fov || preset.fov || 45, b.fov || preset.fov || 45, f),
  };
}

// --------------------------------------------------------------------------
// Scroll state
// --------------------------------------------------------------------------
let activeSectionId = PLAN.sections[0]?.id;
const scrollState = new Map(PLAN.sections.map((s) => [s.id, 0]));

PLAN.sections.forEach((sec) => {
  const el = document.querySelector(`[data-wegek-section="${sec.id}"]`);
  if (!el) return;
  ScrollTrigger.create({
    trigger: el, start: "top bottom", end: "bottom top",
    onUpdate: (self) => scrollState.set(sec.id, self.progress),
    onToggle: (self) => { if (self.isActive) setActive(sec.id); },
  });
  gsap.utils.toArray(el.querySelectorAll(".reveal")).forEach((node) => {
    gsap.from(node, { yPercent: 30, opacity: 0, duration: 1.1, ease: "power3.out",
      scrollTrigger: { trigger: node, start: "top 88%" } });
  });
});

function setActive(id) {
  if (activeSectionId === id) return;
  activeSectionId = id;
  const sec = PLAN.sections.find((s) => s.id === id);
  if (sec) buildLights(sec.lighting_preset);
}

// --------------------------------------------------------------------------
// Lenis + composer + interaction
// --------------------------------------------------------------------------
const lenis = new Lenis({ duration: 1.15, smoothWheel: true });
lenis.on("scroll", ScrollTrigger.update);
gsap.ticker.add((t) => lenis.raf(t * 1000));
gsap.ticker.lagSmoothing(0);

const composer = new EffectComposer(renderer);
const bgPass = new RenderPass(bgScene, bgCamera);
composer.addPass(bgPass);
const mainPass = new RenderPass(scene, camera);
mainPass.clear = false; // draw product over the background
composer.addPass(mainPass);
const bloom = new UnrealBloomPass(
  new THREE.Vector2(window.innerWidth, window.innerHeight),
  num(B_EFF.strength, 0.6), num(B_EFF.radius, 0.5), num(B_EFF.threshold, 0.8),
);
composer.addPass(bloom);

// Cinematic grade: chromatic aberration + film grain + vignette (AI-tunable).
const gradePass = new ShaderPass({
  uniforms: {
    tDiffuse: { value: null },
    uTime: { value: 0 },
    uAberration: { value: num(G_EFF.aberration, 0.0016) },
    uGrain: { value: num(G_EFF.grain, 0.05) },
    uVignette: { value: num(G_EFF.vignette, 0.32) },
  },
  vertexShader: "varying vec2 vUv; void main(){ vUv=uv; gl_Position=vec4(position,1.0); }",
  fragmentShader: `
    varying vec2 vUv; uniform sampler2D tDiffuse;
    uniform float uTime, uAberration, uGrain, uVignette;
    float hash(vec2 p){ return fract(sin(dot(p, vec2(127.1,311.7)))*43758.5453); }
    void main(){
      vec2 d = vUv - 0.5;
      float r2 = dot(d,d);
      vec2 off = d * uAberration * (1.0 + r2*2.0);
      vec3 col;
      col.r = texture2D(tDiffuse, vUv + off).r;
      col.g = texture2D(tDiffuse, vUv).g;
      col.b = texture2D(tDiffuse, vUv - off).b;
      col *= 1.0 - uVignette * smoothstep(0.2, 0.85, length(d));
      col += (hash(vUv*vec2(1920.0,1080.0)+uTime) - 0.5) * uGrain;
      gl_FragColor = vec4(col, 1.0);
    }`,
});
composer.addPass(gradePass);
composer.addPass(new OutputPass());

const mouse = new THREE.Vector2(0, 0);
window.addEventListener("pointermove", (e) => {
  mouse.set(e.clientX / window.innerWidth - 0.5, e.clientY / window.innerHeight - 0.5);
  bgUniforms.u_mouse.value.set(e.clientX / window.innerWidth, 1 - e.clientY / window.innerHeight);
});
window.addEventListener("resize", () => {
  renderer.setSize(window.innerWidth, window.innerHeight);
  composer.setSize(window.innerWidth, window.innerHeight);
  camera.aspect = window.innerWidth / window.innerHeight;
  camera.updateProjectionMatrix();
  bgUniforms.u_resolution.value.set(window.innerWidth, window.innerHeight);
  ScrollTrigger.refresh();
});

// --------------------------------------------------------------------------
// Render loop
// --------------------------------------------------------------------------
const clock = new THREE.Clock();
function frame() {
  const dt = Math.min(clock.getDelta(), 0.05);
  const now = performance.now();
  bgUniforms.u_time.value += dt;

  const sec = PLAN.sections.find((s) => s.id === activeSectionId) || PLAN.sections[0];
  const localT = clamp01(scrollState.get(sec.id) ?? 0);

  // drive each persistent object toward its pose for the active section
  for (const [oid, node] of objectNodes) {
    const inSec = (sec.objects || []).includes(oid);
    const spec = node.userData.spec;
    const base = sectionPose(sec, oid);
    const kf = sampleTrack(spec.keyframes, localT) || { position: [0, 0, 0], rotation: [0, 0, 0], scale: 1, explode: 0 };
    const ex = 1 + (kf.explode || 0);
    const idle = now * 0.00008; // subtle perpetual life
    const tgt = {
      px: base.pos[0] + kf.position[0] * ex + mouse.x * 0.4,
      py: base.pos[1] + kf.position[1] - mouse.y * 0.3,
      pz: base.pos[2] + kf.position[2] * ex,
      rx: base.rot[0] + kf.rotation[0] + mouse.y * 0.15,
      ry: base.rot[1] + kf.rotation[1] + idle + mouse.x * 0.25,
      rz: base.rot[2] + kf.rotation[2],
      sc: inSec ? base.scale * kf.scale : 0.001,
    };
    const c = node.userData.cur;
    const k = 5.5;
    c.px = damp(c.px, tgt.px, k, dt); c.py = damp(c.py, tgt.py, k, dt); c.pz = damp(c.pz, tgt.pz, k, dt);
    c.rx = damp(c.rx, tgt.rx, k, dt); c.ry = damp(c.ry, tgt.ry, k, dt); c.rz = damp(c.rz, tgt.rz, k, dt);
    c.sc = damp(c.sc, tgt.sc, k, dt);
    node.position.set(c.px, c.py, c.pz);
    node.rotation.set(c.rx, c.ry, c.rz);
    node.scale.setScalar(Math.max(c.sc, 0.0001));
    node.visible = c.sc > 0.01;
  }

  // particles drift + gentle parallax
  particles.rotation.y += dt * 0.015;
  particles.position.x = damp(particles.position.x, mouse.x * 1.2, 2, dt);
  particles.position.y = damp(particles.position.y, -mouse.y * 0.8, 2, dt);

  // camera — inline AI move wins, else preset; smoothed
  const camPreset = sec.camera || CAMERAS[sec.camera_preset] || Object.values(CAMERAS)[0];
  const tc = sampleCamera(camPreset, localT);
  camera.position.lerp(tc.pos, 1 - Math.exp(-3.5 * dt));
  camTarget.lerp(tc.look, 1 - Math.exp(-3.5 * dt));
  camera.lookAt(camTarget);
  if (Math.abs(camera.fov - tc.fov) > 0.04) {
    camera.fov = lerp(camera.fov, tc.fov, 1 - Math.exp(-3.5 * dt));
    camera.updateProjectionMatrix();
  }

  gradePass.uniforms.uTime.value = bgUniforms.u_time.value;
  composer.render();
  requestAnimationFrame(frame);
}

buildObjects();
buildLights(PLAN.sections[0]?.lighting_preset || "studio_dramatic");
ScrollTrigger.refresh();
frame();

// signal readiness for the render-review harness
window.__WEGEK_READY__ = true;
document.documentElement.setAttribute("data-wegek-ready", "true");

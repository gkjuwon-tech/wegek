// WEGEK runtime engine — turns a site plan into a live 3D scrollytelling site.
// Loaded as an ES module. Reads window.__WEGEK__ (plan + presets + shader).
import * as THREE from "three";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";
import { RoundedBoxGeometry } from "three/addons/geometries/RoundedBoxGeometry.js";
import { RoomEnvironment } from "three/addons/environments/RoomEnvironment.js";
import { RectAreaLightUniformsLib } from "three/addons/lights/RectAreaLightUniformsLib.js";
import gsap from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";
import Lenis from "lenis";

gsap.registerPlugin(ScrollTrigger);
RectAreaLightUniformsLib.init();

const BUNDLE = window.__WEGEK__;
const PLAN = BUNDLE.plan;
const LIGHTING = BUNDLE.lighting;
const CAMERAS = BUNDLE.cameras;
const SHADER = BUNDLE.shader;

const lerp = (a, b, t) => a + (b - a) * t;
const clamp01 = (x) => Math.max(0, Math.min(1, x));
const hexToRGB = (hex) => {
  const c = new THREE.Color(hex);
  return [c.r, c.g, c.b];
};

// --------------------------------------------------------------------------
// Renderer + canvas
// --------------------------------------------------------------------------
const canvas = document.getElementById("wegek-canvas");
const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true });
renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
renderer.setSize(window.innerWidth, window.innerHeight);
renderer.autoClear = false;
renderer.toneMapping = THREE.ACESFilmicToneMapping;
renderer.toneMappingExposure = 1.1;

// --------------------------------------------------------------------------
// Background shader (full-screen pass)
// --------------------------------------------------------------------------
const bgScene = new THREE.Scene();
const bgCamera = new THREE.OrthographicCamera(-1, 1, 1, -1, 0, 1);
const palette = PLAN.global_style.color_palette;
const bgUniforms = {
  u_time: { value: 0 },
  u_mouse: { value: new THREE.Vector2(0.5, 0.5) },
  u_resolution: { value: new THREE.Vector2(window.innerWidth, window.innerHeight) },
  u_color0: { value: new THREE.Vector3(...hexToRGB(palette[0] || "#0a0a0f")) },
  u_color1: { value: new THREE.Vector3(...hexToRGB(palette[1] || "#e94560")) },
  u_color2: { value: new THREE.Vector3(...hexToRGB(palette[2] || "#0f3460")) },
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
// Main scene + camera
// --------------------------------------------------------------------------
const scene = new THREE.Scene();

// Image-based lighting: without an environment, metallic/PBR surfaces reflect
// pure black and read as dead, unlit blobs. A PMREM-filtered RoomEnvironment
// gives every material real reflections so the analytic lights can sculpt on top.
const pmrem = new THREE.PMREMGenerator(renderer);
pmrem.compileEquirectangularShader();
const envTexture = pmrem.fromScene(new RoomEnvironment(), 0.04).texture;
scene.environment = envTexture;

const camera = new THREE.PerspectiveCamera(45, window.innerWidth / window.innerHeight, 0.1, 100);
camera.position.set(0, 1, 6);
const camTarget = new THREE.Vector3(0, 0, 0);
const desired = { pos: new THREE.Vector3(0, 1, 6), look: new THREE.Vector3(0, 0, 0), fov: 45 };

const lightGroup = new THREE.Group();
scene.add(lightGroup);

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
        // A real RectAreaLight (soft studio panel) instead of a fake directional —
        // it must face the subject, so orient it toward the origin after placement.
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
// Object factory (procedural primitives + GLB)
// --------------------------------------------------------------------------
const loader = new GLTFLoader();

function makeMaterial(color) {
  // Opaque by default — transparency is only toggled on during cross-fades.
  // A persistently-transparent metallic surface reads as a ghost: you see the
  // background and the object's own back faces straight through it.
  return new THREE.MeshStandardMaterial({
    color: color || "#cfcfd6",
    metalness: 0.85,
    roughness: 0.25,
    envMapIntensity: 1.0,
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
    case "bottle": {
      const g1 = new THREE.CylinderGeometry(0.55, 0.55, 1.6, 48);
      return g1;
    }
    case "box": return new THREE.BoxGeometry(1.6, 1.6, 1.6);
    case "rounded_box":
    default: return new RoundedBoxGeometry(1.7, 1.1, 0.5, 6, 0.18);
  }
}

const sectionGroups = new Map(); // sectionId -> { group, objects:[{obj, node, baseScale}] }

function buildObjectNode(objSpec) {
  if (objSpec.model_format === "glb" && objSpec.model_url) {
    const placeholder = new THREE.Group();
    loader.load(
      objSpec.model_url,
      (gltf) => {
        const model = gltf.scene;
        // normalize size into a consistent ~2-unit footprint and recentre on origin
        const box = new THREE.Box3().setFromObject(model);
        const size = box.getSize(new THREE.Vector3());
        const scale = 2.0 / (Math.max(size.x, size.y, size.z) || 1);
        model.scale.setScalar(scale);
        const center = box.getCenter(new THREE.Vector3());
        model.position.sub(center.multiplyScalar(scale));
        model.traverse((c) => {
          // Keep imported materials opaque (the fade pass manages transparency)
          // and let them pick up the scene environment for believable reflections.
          if (c.isMesh && c.material) {
            const mats = Array.isArray(c.material) ? c.material : [c.material];
            for (const m of mats) {
              m.transparent = false;
              m.depthWrite = true;
              if ("envMapIntensity" in m) m.envMapIntensity = 1.0;
            }
          }
        });
        placeholder.add(model);
      },
      undefined,
      () => { placeholder.add(new THREE.Mesh(primitiveGeometry(objSpec.primitive), makeMaterial(objSpec.color))); }
    );
    return placeholder;
  }
  return new THREE.Mesh(primitiveGeometry(objSpec.primitive), makeMaterial(objSpec.color));
}

function buildSections() {
  for (const sec of PLAN.sections) {
    const group = new THREE.Group();
    group.visible = false;
    const objects = [];
    const ids = sec.objects || [];
    const layouts = sec.object_layout || {};
    ids.forEach((oid, i) => {
      const spec = PLAN.objects.find((o) => o.id === oid);
      if (!spec) return;
      const node = buildObjectNode(spec);
      // Base transform: AI-authored per-section placement wins; otherwise fall back
      // to an auto-spread so multi-object sections don't pile up at the origin.
      const L = layouts[oid] || {};
      const autoX = (i - (ids.length - 1) / 2) * 2.6;
      const base = {
        pos: L.position || [autoX, 0, 0],
        rot: L.rotation || [0, 0, 0],
        scale: L.scale ?? 1,
      };
      node.position.set(base.pos[0], base.pos[1], base.pos[2]);
      node.userData.base = base;
      node.userData.spec = spec;
      group.add(node);
      objects.push({ spec, node });
    });
    scene.add(group);
    sectionGroups.set(sec.id, { group, objects });
  }
}

// --------------------------------------------------------------------------
// Animation sampling
// --------------------------------------------------------------------------
function sampleTrack(keyframes, t) {
  if (!keyframes || keyframes.length === 0) return null;
  if (t <= keyframes[0].t) return keyframes[0];
  for (let i = 0; i < keyframes.length - 1; i++) {
    const a = keyframes[i], b = keyframes[i + 1];
    if (t >= a.t && t <= b.t) {
      const f = (t - a.t) / (b.t - a.t || 1);
      const lerp3 = (x, y) => x.map((v, j) => lerp(v, y[j], f));
      return {
        rotation: lerp3(a.rotation, b.rotation),
        position: lerp3(a.position, b.position),
        scale: lerp(a.scale ?? 1, b.scale ?? 1, f),
        explode: lerp(a.explode ?? 0, b.explode ?? 0, f),
      };
    }
  }
  return keyframes[keyframes.length - 1];
}

function applyObject(node, spec, localT) {
  const base = node.userData.base || { pos: [0, 0, 0], rot: [0, 0, 0], scale: 1 };
  const s = sampleTrack(spec.keyframes, localT);
  if (!s) {
    node.position.set(base.pos[0], base.pos[1], base.pos[2]);
    node.rotation.set(base.rot[0], base.rot[1], base.rot[2]);
    node.scale.setScalar(base.scale);
    return;
  }
  // Keyframes are deltas layered on top of the section's base placement, so the
  // AI's composition (where/how big) and motion (how it moves) compose cleanly.
  const ex = 1 + (s.explode || 0);
  node.position.set(
    base.pos[0] + s.position[0] * ex,
    base.pos[1] + s.position[1],
    base.pos[2] + s.position[2] * ex,
  );
  node.rotation.set(base.rot[0] + s.rotation[0], base.rot[1] + s.rotation[1], base.rot[2] + s.rotation[2]);
  node.scale.setScalar(base.scale * s.scale);
}

function sampleCamera(preset, localT) {
  if (!preset) return { pos: new THREE.Vector3(0, 1, 6), look: new THREE.Vector3(0, 0, 0), fov: 45 };
  const kfs = preset.keyframes || [];
  // Inline AI cameras and presets may omit `type`; prefer keyframes when present.
  if (kfs.length === 0 && preset.type === "orbit") {
    const d = preset.distance || 5;
    const a = performance.now() * 0.0002 * (preset.autoRotateSpeed || 0.5);
    return { pos: new THREE.Vector3(Math.sin(a) * d, 1.2, Math.cos(a) * d), look: new THREE.Vector3(0, 0, 0), fov: preset.fov || 45 };
  }
  if (kfs.length === 0 && preset.position) {
    return { pos: new THREE.Vector3(...preset.position), look: new THREE.Vector3(...(preset.lookAt || [0, 0, 0])), fov: preset.fov || 45 };
  }
  if (kfs.length === 0) return { pos: new THREE.Vector3(0, 1, 6), look: new THREE.Vector3(0, 0, 0), fov: 45 };
  let a = kfs[0], b = kfs[kfs.length - 1];
  for (let i = 0; i < kfs.length - 1; i++) {
    if (localT >= kfs[i].scroll && localT <= kfs[i + 1].scroll) { a = kfs[i]; b = kfs[i + 1]; break; }
  }
  const f = (localT - a.scroll) / ((b.scroll - a.scroll) || 1);
  const mix = (x, y) => x.map((v, j) => lerp(v, y[j], clamp01(f)));
  return {
    pos: new THREE.Vector3(...mix(a.position, b.position)),
    look: new THREE.Vector3(...mix(a.lookAt, b.lookAt)),
    fov: lerp(a.fov || preset.fov || 45, b.fov || preset.fov || 45, clamp01(f)),
  };
}

// --------------------------------------------------------------------------
// Scroll state
// --------------------------------------------------------------------------
let activeSectionId = PLAN.sections[0]?.id;
const sectionEls = [...document.querySelectorAll("[data-wegek-section]")];
const scrollState = new Map(PLAN.sections.map((s) => [s.id, 0]));

PLAN.sections.forEach((sec) => {
  const el = document.querySelector(`[data-wegek-section="${sec.id}"]`);
  if (!el) return;
  ScrollTrigger.create({
    trigger: el,
    start: "top bottom",
    end: "bottom top",
    onUpdate: (self) => scrollState.set(sec.id, self.progress),
    onToggle: (self) => { if (self.isActive) setActive(sec.id); },
  });
  gsap.utils.toArray(el.querySelectorAll(".reveal")).forEach((node) => {
    gsap.from(node, {
      yPercent: 40, opacity: 0, duration: 1, ease: "power3.out",
      scrollTrigger: { trigger: node, start: "top 85%" },
    });
  });
});

function setActive(id) {
  if (activeSectionId === id) return;
  activeSectionId = id;
  const sec = PLAN.sections.find((s) => s.id === id);
  if (sec) buildLights(sec.lighting_preset);
}

// --------------------------------------------------------------------------
// Lenis smooth scroll + GSAP ticker
// --------------------------------------------------------------------------
const lenis = new Lenis({ duration: 1.1, smoothWheel: true });
lenis.on("scroll", ScrollTrigger.update);
gsap.ticker.add((time) => lenis.raf(time * 1000));
gsap.ticker.lagSmoothing(0);

window.addEventListener("pointermove", (e) => {
  bgUniforms.u_mouse.value.set(e.clientX / window.innerWidth, 1 - e.clientY / window.innerHeight);
});
window.addEventListener("resize", () => {
  renderer.setSize(window.innerWidth, window.innerHeight);
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
  const dt = clock.getDelta();
  bgUniforms.u_time.value += dt;

  const sec = PLAN.sections.find((s) => s.id === activeSectionId) || PLAN.sections[0];
  const localT = clamp01(scrollState.get(sec.id) ?? 0);

  // fade groups
  for (const [sid, entry] of sectionGroups) {
    const target = sid === sec.id ? 1 : 0;
    entry.group.visible = target > 0 || entry.group.userData.op > 0.01;
    entry.group.userData.op = lerp(entry.group.userData.op ?? (sid === sec.id ? 1 : 0), target, 0.12);
    const op = entry.group.userData.op;
    const fading = op < 0.995;
    entry.group.traverse((c) => {
      if (c.isMesh && c.material) {
        const mats = Array.isArray(c.material) ? c.material : [c.material];
        for (const m of mats) {
          m.transparent = fading;     // only translucent mid cross-fade
          m.depthWrite = !fading;     // opaque objects keep writing depth (no ghosting)
          m.opacity = op;
        }
      }
    });
    if (sid === sec.id) {
      for (const { node, spec } of entry.objects) applyObject(node, spec, localT);
    }
  }

  // camera — inline AI-authored move wins, else the named preset
  const camPreset = sec.camera || CAMERAS[sec.camera_preset] || Object.values(CAMERAS)[0];
  const target = sampleCamera(camPreset, localT);
  desired.pos.copy(target.pos); desired.look.copy(target.look); desired.fov = target.fov;
  camera.position.lerp(desired.pos, 0.08);
  camTarget.lerp(desired.look, 0.08);
  camera.lookAt(camTarget);
  if (Math.abs(camera.fov - desired.fov) > 0.05) {
    camera.fov = lerp(camera.fov, desired.fov, 0.08);
    camera.updateProjectionMatrix();
  }

  renderer.clear();
  renderer.render(bgScene, bgCamera);
  renderer.clearDepth();
  renderer.render(scene, camera);
  requestAnimationFrame(frame);
}

buildSections();
buildLights(PLAN.sections[0]?.lighting_preset || "studio_dramatic");
ScrollTrigger.refresh();
frame();

// signal readiness for the render-review harness
window.__WEGEK_READY__ = true;
document.documentElement.setAttribute("data-wegek-ready", "true");

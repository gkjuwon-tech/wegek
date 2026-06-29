import { Cube, Layers, Bolt, Lock } from "./icons";

const FLOW = ["Plan", "Images", "3D", "Animate", "Shaders", "Scene", "Code", "Review"];

const FEATURES = [
  { icon: <Cube size={16} />, title: "Real 3D, real code", body: "A single index.html built with Three.js, GSAP and GLSL — not a mockup, but a site you can ship." },
  { icon: <Layers size={16} />, title: "7-stage pipeline", body: "Planning through models, shaders and scroll choreography in one flow. Every stage streams live." },
  { icon: <Bolt size={16} />, title: "Works without keys", body: "Falls back to procedural generation when no API key is set. Add keys to raise quality stage by stage." },
];

export function Hero({ live }: { live: boolean }) {
  return (
    <div className="hero">
      <span className="hero-eyebrow">
        <span className="live-dot" />
        {live ? "Pipeline ready" : "Procedural mode · runs without keys"}
      </span>

      <h1>
        From one prompt to a<br />
        <em>production-grade 3D site.</em>
      </h1>

      <p>
        WEGEK turns a natural-language brief into planning, 3D assets, animation and
        shaders — then ships it as a single, self-contained scrollytelling website, code included.
      </p>

      <div className="hero-flow">
        {FLOW.map((s, i) => (
          <span key={s} style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
            <span className="flow-step">
              <span className="flow-num">{String(i).padStart(2, "0")}</span>
              {s}
            </span>
            {i < FLOW.length - 1 && <span className="flow-arrow">→</span>}
          </span>
        ))}
      </div>

      <div className="hero-features">
        {FEATURES.map((f) => (
          <div key={f.title} className="feature">
            <div className="feature-ico">{f.icon}</div>
            <h3>{f.title}</h3>
            <p>{f.body}</p>
          </div>
        ))}
      </div>

      <div className="hero-trust">
        <span style={{ display: "inline-flex", alignItems: "center", gap: 7 }}>
          <Lock size={13} /> You own the output
        </span>
        <span className="sep" />
        <span>Real-time over <b>WebSocket</b></span>
        <span className="sep" />
        <span>Single-file <b>HTML</b> export</span>
      </div>
    </div>
  );
}

import type { SitePlan } from "../lib/api";

export function PlanViewer({ plan }: { plan: SitePlan }) {
  return (
    <div className="plan-viewer">
      <div className="plan-head">
        <div>
          <div className="plan-name">{plan.project_name.replace(/_/g, " ")}</div>
          <div className="plan-tagline">{plan.tagline}</div>
        </div>
        <div className="palette">
          {plan.global_style.color_palette.map((c, i) => (
            <span key={i} className="swatch" style={{ background: c }} title={c} />
          ))}
        </div>
      </div>

      <div className="plan-meta">
        <span className="tag">mood: {plan.brand_mood}</span>
        <span className="tag">type: {plan.global_style.typography}</span>
        <span className="tag">shader: {plan.global_style.background_shader}</span>
      </div>

      <div className="plan-cols">
        <div className="plan-col">
          <h4>Sections ({plan.sections.length})</h4>
          {plan.sections.map((s) => (
            <div key={s.id} className="card">
              <div className="card-title">{s.id}</div>
              <div className="card-sub">{s.headline}</div>
              <div className="card-tags">
                <span>{s.type}</span>
                <span>📷 {s.camera_preset}</span>
                <span>💡 {s.lighting_preset}</span>
              </div>
            </div>
          ))}
        </div>
        <div className="plan-col">
          <h4>3D Objects ({plan.objects.length})</h4>
          {plan.objects.map((o) => (
            <div key={o.id} className="card">
              <div className="card-title">
                {o.id} <span className={`badge badge--${o.model_format}`}>{o.model_format}</span>
              </div>
              <div className="card-sub">{o.description}</div>
              <div className="card-tags">
                <span>{o.category}</span>
                <span>🎞 {o.animation}</span>
                {o.primitive && <span>▢ {o.primitive}</span>}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

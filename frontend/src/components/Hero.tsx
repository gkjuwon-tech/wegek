import { Cube, Layers, Bolt, Lock } from "./icons";

const FLOW = ["Plan", "Images", "3D", "Animate", "Shaders", "Scene", "Code", "Review"];

const FEATURES = [
  { icon: <Cube size={16} />, title: "진짜 3D, 진짜 코드", body: "Three.js · GSAP · GLSL로 짜인 단일 index.html. 목업이 아니라 바로 배포되는 사이트." },
  { icon: <Layers size={16} />, title: "7-스테이지 파이프라인", body: "기획부터 모델·셰이더·스크롤 연출까지 한 흐름으로. 각 단계가 실시간으로 보입니다." },
  { icon: <Bolt size={16} />, title: "키 없이도 완성", body: "API 키가 없으면 절차적 생성으로 폴백. 키를 더하면 단계별로 품질이 올라갑니다." },
];

export function Hero({ live }: { live: boolean }) {
  return (
    <div className="hero">
      <span className="hero-eyebrow">
        <span className="live-dot" />
        {live ? "파이프라인 가동 준비 완료" : "프로시저럴 모드 · 키 없이 동작"}
      </span>

      <h1>
        한 줄의 프롬프트를<br />
        <em>프로덕션급 3D 사이트</em>로.
      </h1>

      <p>
        WEGEK은 자연어 브리프를 받아 기획·3D 에셋·애니메이션·셰이더를 생성하고,
        스스로 완결된 스크롤리텔링 웹사이트 하나로 코드까지 뽑아냅니다.
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
          <Lock size={13} /> 결과물 100% 소유
        </span>
        <span className="sep" />
        <span><b>WebSocket</b> 실시간 진행</span>
        <span className="sep" />
        <span>단일 <b>HTML</b> 다운로드</span>
      </div>
    </div>
  );
}

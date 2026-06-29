import { useState } from "react";

const EXAMPLES = [
  "고급 시계 브랜드 랜딩, 시계가 돌아가며 부품이 분해됐다 재조립되는 느낌",
  "Nike Air Max landing — shoe floating, rotating, exploding into parts",
  "네온 게이밍 키보드 랜딩, 사이버펑크 무드 RGB",
  "Tesla EV landing page, car rotates and doors reveal interior",
];

interface Props {
  onSubmit: (prompt: string, brandMood?: string) => void;
  busy: boolean;
}

export function PromptForm({ onSubmit, busy }: Props) {
  const [prompt, setPrompt] = useState("");
  const [mood, setMood] = useState("");

  return (
    <form
      className="prompt-form"
      onSubmit={(e) => {
        e.preventDefault();
        if (prompt.trim().length >= 3) onSubmit(prompt.trim(), mood || undefined);
      }}
    >
      <label className="field-label">무엇을 만들까요?</label>
      <textarea
        className="prompt-input"
        placeholder="만들고 싶은 3D 웹사이트를 자연어로 설명하세요…"
        value={prompt}
        rows={3}
        onChange={(e) => setPrompt(e.target.value)}
      />
      <div className="prompt-row">
        <select className="mood-select" value={mood} onChange={(e) => setMood(e.target.value)}>
          <option value="">무드 자동</option>
          <option value="premium">premium</option>
          <option value="luxury">luxury</option>
          <option value="gaming">gaming</option>
          <option value="minimal">minimal</option>
          <option value="editorial">editorial</option>
        </select>
        <button className="generate-btn" type="submit" disabled={busy || prompt.trim().length < 3}>
          {busy ? "공장 가동 중…" : "사이트 찍어내기 →"}
        </button>
      </div>
      <div className="examples">
        {EXAMPLES.map((ex) => (
          <button type="button" key={ex} className="example-chip" onClick={() => setPrompt(ex)}>
            {ex.length > 42 ? ex.slice(0, 42) + "…" : ex}
          </button>
        ))}
      </div>
    </form>
  );
}

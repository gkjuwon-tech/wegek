import { useState } from "react";
import { Spark, Arrow } from "./icons";

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

  const valid = prompt.trim().length >= 3;
  const submit = () => valid && onSubmit(prompt.trim(), mood || undefined);

  return (
    <>
      <form
        className="composer"
        onSubmit={(e) => {
          e.preventDefault();
          submit();
        }}
      >
        <div className="composer-head">
          <span className="composer-label">무엇을 만들까요?</span>
          <span className="composer-kbd">
            <kbd>⌘</kbd> <kbd>↵</kbd> 전송
          </span>
        </div>

        <textarea
          className="prompt-input"
          placeholder="만들고 싶은 3D 웹사이트를 자연어로 설명하세요. 브랜드 무드, 움직임, 분위기까지 자세할수록 좋아요…"
          value={prompt}
          rows={3}
          onChange={(e) => setPrompt(e.target.value)}
          onKeyDown={(e) => {
            if ((e.metaKey || e.ctrlKey) && e.key === "Enter") submit();
          }}
        />

        <div className="composer-controls">
          <span className="mood-wrap">
            <select
              className="mood-select"
              value={mood}
              onChange={(e) => setMood(e.target.value)}
              aria-label="brand mood"
            >
              <option value="">무드 자동</option>
              <option value="premium">premium</option>
              <option value="luxury">luxury</option>
              <option value="gaming">gaming</option>
              <option value="minimal">minimal</option>
              <option value="editorial">editorial</option>
            </select>
          </span>
          <button className="generate-btn" type="submit" disabled={busy || !valid}>
            {busy ? (
              <>
                <span className="spinner" /> 공장 가동 중…
              </>
            ) : (
              <>
                <Spark size={15} /> 사이트 생성
              </>
            )}
          </button>
        </div>
      </form>

      <div>
        <div className="examples-label" style={{ marginBottom: 10 }}>예시 프롬프트</div>
        <div className="examples">
          {EXAMPLES.map((ex) => (
            <button type="button" key={ex} className="example-chip" onClick={() => setPrompt(ex)}>
              {ex}
              <Arrow size={14} className="ex-arrow" />
            </button>
          ))}
        </div>
      </div>
    </>
  );
}

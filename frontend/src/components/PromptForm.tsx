import { useState } from "react";
import { Spark, Arrow } from "./icons";

const EXAMPLES = [
  "Luxury watch brand landing — timepiece rotates as components disassemble and reassemble",
  "Nike Air Max landing — shoe floating, rotating, exploding into parts",
  "Neon gaming keyboard landing, cyberpunk RGB mood",
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
          <span className="composer-label">What should we build?</span>
          <span className="composer-kbd">
            <kbd>⌘</kbd> <kbd>↵</kbd> to send
          </span>
        </div>

        <textarea
          className="prompt-input"
          placeholder="Describe the 3D website you want in plain language — brand mood, motion, atmosphere. The more detail, the better…"
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
              <option value="">Auto mood</option>
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
                <span className="spinner" /> Generating…
              </>
            ) : (
              <>
                <Spark size={15} /> Generate site
              </>
            )}
          </button>
        </div>
      </form>

      <div>
        <div className="examples-label" style={{ marginBottom: 10 }}>Example prompts</div>
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

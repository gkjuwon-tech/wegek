import { useEffect, useRef } from "react";
import type { LogEntry } from "../lib/api";

export function JobLog({ logs }: { logs: LogEntry[] }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    ref.current?.scrollTo({ top: ref.current.scrollHeight });
  }, [logs.length]);

  return (
    <div className="panel">
      <div className="panel-head">
        <span className="panel-eyebrow">Live log</span>
        <span className="panel-count">{logs.length}</span>
      </div>
      <div className="joblog" ref={ref}>
        {logs.length === 0 && <div className="log-empty">로그 대기 중…</div>}
        {logs.map((l, i) => (
          <div key={i} className={`log-line log-${l.level}`}>
            <span className="log-stage">{l.stage ?? "·"}</span>
            <span className="log-msg">{l.message}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

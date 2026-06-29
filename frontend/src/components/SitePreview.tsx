interface Props {
  siteUrl: string;
  score: number | null;
}

export function SitePreview({ siteUrl, score }: Props) {
  return (
    <div className="preview">
      <div className="preview-bar">
        <span className="preview-dot" /> <span className="preview-dot" /> <span className="preview-dot" />
        <span className="preview-url">{siteUrl}</span>
        <div className="preview-actions">
          {score !== null && <span className="score">QA {Math.round(score * 100)}</span>}
          <a className="ghost-btn" href={siteUrl} target="_blank" rel="noreferrer">
            새 탭에서 열기 ↗
          </a>
          <a className="ghost-btn" href={siteUrl} download>
            HTML 다운로드 ⬇
          </a>
        </div>
      </div>
      <iframe className="preview-frame" src={siteUrl} title="Generated site" />
    </div>
  );
}

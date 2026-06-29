import { ArrowUpRight, Download, Check } from "./icons";

interface Props {
  siteUrl: string;
  score: number | null;
}

export function SitePreview({ siteUrl, score }: Props) {
  return (
    <div className="panel preview">
      <div className="preview-bar">
        <span className="traffic">
          <span /><span /><span />
        </span>
        <span className="preview-url">{siteUrl}</span>
        <div className="preview-actions">
          {score !== null && (
            <span className="score">
              <Check size={12} /> QA {Math.round(score * 100)}
            </span>
          )}
          <a className="ghost-btn" href={siteUrl} target="_blank" rel="noreferrer">
            Open <ArrowUpRight size={13} />
          </a>
          <a className="ghost-btn" href={siteUrl} download>
            HTML <Download size={13} />
          </a>
        </div>
      </div>
      <iframe className="preview-frame" src={siteUrl} title="Generated site" />
    </div>
  );
}

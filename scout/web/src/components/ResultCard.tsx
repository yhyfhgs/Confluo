import type { Result } from "../types";
import { authorsShort, labelClass, labelText, pct } from "../lib/format";

interface Props {
  r: Result;
  fresh: boolean;
  onOpen: (r: Result) => void;
}

export function ResultCard({ r, fresh, onOpen }: Props) {
  const label = labelText(r.decision_label, r.status);
  const rv = r.review;
  return (
    <article className={`card${fresh ? " is-fresh" : ""}`} onClick={() => onOpen(r)}>
      <div className="card-meta">
        <span className="venue">{r.venue}</span>
        {label && <span className={labelClass(r.decision_label, r.status)}>{label}</span>}
        {r.track && !/^(Long|Short) papers$/.test(r.track) && r.track !== label && <span className="track">{r.track}</span>}
        {r.hop > 1 && (
          <span className="hop" title={`第 ${r.hop} 轮经扩展线索找到：${r.via.join("、")}`}>第 {r.hop} 跳</span>
        )}
        <span className="spacer" />
        {rv && (
          <span className="review" title={`${rv.n} 位审稿人，分数 ${rv.min}–${rv.max}，平均置信 ${rv.confidence ?? "–"}；本届百分位 ${pct(rv.R)}`}>
            <span className="review-score">{rv.mean.toFixed(1)}</span>
            <span className="review-sub">{rv.n} 份审稿 · 置信 {rv.confidence?.toFixed(1) ?? "–"}</span>
            {rv.R !== undefined && <span className="review-bar"><i style={{ width: `${Math.round((rv.R ?? 0) * 100)}%` }} /></span>}
          </span>
        )}
      </div>
      <h3 className="card-title" dangerouslySetInnerHTML={{ __html: r.title }} />
      <div className="card-authors">{authorsShort(r.authors)}</div>
      {r.snippet ? (
        <p className="card-snippet" dangerouslySetInnerHTML={{ __html: r.snippet }} />
      ) : (
        <p className="card-snippet muted">摘要尚未抓取</p>
      )}
      <div className="card-foot">
        <div className="chips">
          {r.matched.exact.map((k) => <span key={"e" + k} className="chip chip-hit">{k}</span>)}
          {r.matched.near.slice(0, 4).map((k) => <span key={"n" + k} className="chip chip-near">{k}</span>)}
        </div>
        <div className="links" onClick={(e) => e.stopPropagation()}>
          {r.links.forum && <a href={r.links.forum} target="_blank" rel="noreferrer">OpenReview</a>}
          {r.links.proceedings && <a href={r.links.proceedings} target="_blank" rel="noreferrer">论文页</a>}
          {r.links.pdf && <a href={r.links.pdf} target="_blank" rel="noreferrer">PDF</a>}
        </div>
      </div>
    </article>
  );
}

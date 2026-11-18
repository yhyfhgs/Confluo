import { useEffect, useState } from "react";
import { api } from "../api";
import type { PaperDetail, Result } from "../types";
import { labelClass, labelText, markText, pct } from "../lib/format";
import { CloseIcon, CopyIcon } from "./icons";

interface Props {
  result: Result | null;
  onClose: () => void;
}

const SUB_LABELS: Record<string, string> = {
  soundness: "可靠性", presentation: "表达", contribution: "贡献", quality: "质量", clarity: "清晰度",
  significance: "重要性", originality: "原创性", informativeness: "信息量", novelty: "新颖性",
};

function Bar({ v }: { v: number }) {
  return <span className="bar"><i style={{ width: `${Math.round(Math.max(0, Math.min(1, v)) * 100)}%` }} /></span>;
}

export function PaperDrawer({ result, onClose }: Props) {
  const [p, setP] = useState<PaperDetail | null>(null);
  const [copied, setCopied] = useState(false);
  useEffect(() => {
    setP(null);
    if (!result) return;
    api.paper(result.id).then(setP).catch(() => setP(null));
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [result, onClose]);
  if (!result) return null;
  const exact = result.matched.exact;
  const near = result.matched.near;
  const label = labelText(result.decision_label, result.status);
  const subKeys = p ? [...new Set(p.reviews.flatMap((r) => Object.keys(r.subscores)))].slice(0, 5) : [];
  return (
    <div className="drawer-wrap" onClick={onClose}>
      <aside className="drawer" onClick={(e) => e.stopPropagation()} aria-label="论文详情">
        <header className="drawer-head">
          <div className="card-meta">
            <span className="venue">{result.venue}</span>
            {label && <span className={labelClass(result.decision_label, result.status)}>{label}</span>}
            {result.track && <span className="track">{result.track}</span>}
          </div>
          <button className="icon-btn" onClick={onClose} aria-label="关闭"><CloseIcon /></button>
        </header>
        <h2 className="drawer-title" dangerouslySetInnerHTML={{ __html: result.title }} />
        <p className="drawer-authors">{result.authors.join(", ")}</p>
        {!p && <div className="skeleton" />}
        {p && (
          <>
            {p.tldr && <p className="tldr">{p.tldr}</p>}
            <section>
              <h4>摘要</h4>
              <p className="abstract" dangerouslySetInnerHTML={{ __html: p.abstract ? markText(p.abstract, exact, near) : "摘要尚未抓取" }} />
            </section>
            {(p.keywords.length > 0 || p.area_native || p.area_unified_label) && (
              <section>
                <h4>关键词与领域</h4>
                <div className="chips">
                  {p.area_unified_label && <span className="chip chip-area" title="统一领域（按论文向量归类）">{p.area_unified_label}</span>}
                  {p.area_native && <span className="chip chip-area" title="会议原生领域">{p.area_native}</span>}
                  {p.keywords.map((k) => <span key={k} className="chip">{k}</span>)}
                </div>
              </section>
            )}
            {p.reviews.length > 0 && p.review_stats && (
              <section>
                <h4>审稿分</h4>
                <div className="review-summary">
                  <div><b>{p.review_stats.mean.toFixed(2)}</b><span>平均分</span></div>
                  <div><b>{p.review_stats.min}–{p.review_stats.max}</b><span>区间</span></div>
                  <div><b>{p.review_stats.confidence?.toFixed(1) ?? "–"}</b><span>平均置信</span></div>
                  <div><b>{pct(p.review_stats.R)}</b><span>本届百分位</span></div>
                  {p.edition_stats?.rating_mean != null && (
                    <div><b>{p.edition_stats.rating_mean.toFixed(2)}</b><span>本届均分</span></div>
                  )}
                </div>
                <table className="reviews">
                  <thead>
                    <tr><th>审稿</th><th>总分</th><th>置信</th>{subKeys.map((k) => <th key={k}>{SUB_LABELS[k] ?? k}</th>)}</tr>
                  </thead>
                  <tbody>
                    {p.reviews.map((r, i) => (
                      <tr key={r.review_key}>
                        <td>#{i + 1}</td>
                        <td title={r.rating_raw ?? ""}>{r.rating ?? "–"}</td>
                        <td>{r.confidence ?? "–"}</td>
                        {subKeys.map((k) => <td key={k}>{r.subscores[k] ?? "–"}</td>)}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </section>
            )}
            {result.decision && (
              <section>
                <h4>相关性评审 <span className="muted">{result.decision.source === "local" ? "本地评分" : result.decision.source}</span></h4>
                <div className="judge">
                  <div className="judge-row"><span>相关度</span><Bar v={result.decision.relevance / 4} /><b>{result.decision.relevance.toFixed(1)} / 4</b></div>
                  <div className="judge-row"><span>逻辑延伸</span><Bar v={result.decision.extension} /><b>{pct(result.decision.extension)}%</b></div>
                  {Object.entries(result.decision.keywords).map(([k, v]) => (
                    <div className="judge-row" key={k}><span title={k}>覆盖「{k}」</span><Bar v={v} /><b>{pct(v)}%</b></div>
                  ))}
                </div>
              </section>
            )}
            <section>
              <h4>链接</h4>
              <div className="links big">
                {p.forum_url && <a href={p.forum_url} target="_blank" rel="noreferrer">OpenReview</a>}
                {p.proceedings_url && <a href={p.proceedings_url} target="_blank" rel="noreferrer">论文页</a>}
                {p.pdf_url && <a href={p.pdf_url} target="_blank" rel="noreferrer">PDF</a>}
                {p.doi && <a href={`https://doi.org/${p.doi}`} target="_blank" rel="noreferrer">DOI</a>}
                <button className="text-btn" onClick={() => {
                  navigator.clipboard?.writeText(p.bibtex).then(() => { setCopied(true); window.setTimeout(() => setCopied(false), 1500); });
                }}><CopyIcon width={15} height={15} /> {copied ? "已复制" : "BibTeX"}</button>
              </div>
              <p className="muted small">来源：{p.sources.join("、")}</p>
            </section>
          </>
        )}
      </aside>
    </div>
  );
}

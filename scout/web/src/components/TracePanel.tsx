import type { Final, Keyword, Plan, RoundInfo } from "../types";
import { REASONS } from "../lib/format";

interface Props {
  plan: Plan | null;
  rounds: RoundInfo[];
  final: Final | null;
  running: boolean;
}

function Kw({ k }: { k: Keyword }) {
  const title = [
    k.source ? `来自：${k.source}` : null,
    k.synonyms.length ? `同义：${k.synonyms.join("、")}` : null,
    k.fuzzy.length ? `模糊：${k.fuzzy.join("、")}` : null,
  ].filter(Boolean).join("\n");
  return (
    <span className={`kw kw-${k.origin}`} title={title || undefined}>
      {k.text}
      {k.origin === "translation" && k.source && <small>{k.source}</small>}
    </span>
  );
}

export function TracePanel({ plan, rounds, final, running }: Props) {
  if (!plan) return null;
  const initial = plan.keywords.filter((k) => k.round === 1);
  return (
    <aside className="trace" aria-label="检索过程">
      <h4>检索过程</h4>
      <div className="trace-block">
        <div className="trace-label">关键词</div>
        <div className="kws">{initial.map((k) => <Kw key={k.text} k={k} />)}</div>
        {initial.some((k) => k.synonyms.length) && (
          <div className="syn">
            {initial.filter((k) => k.synonyms.length).map((k) => (
              <div key={k.text}><b>{k.text}</b> ≈ {k.synonyms.join("、")}</div>
            ))}
          </div>
        )}
      </div>
      {plan.mode === "smart" && (
        <div className="trace-block">
          <div className="trace-label">决策模型</div>
          <div className="small">{plan.decision.remote ? plan.decision.model : "未配置 Gemini key，使用本地评分"}</div>
        </div>
      )}
      <ol className="rounds">
        {rounds.map((r) => (
          <li key={r.round}>
            <div className="round-head"><b>第 {r.round} 轮</b><span>{r.ms} ms</span></div>
            <div className="small">新增候选 {r.added}，候选池 {r.pool}{r.judged ? `，评审 ${r.judged} 篇` : ""}</div>
            {r.new_keywords.length > 0 && (
              <div className="kws">{r.new_keywords.map((k) => <Kw key={k.text} k={k} />)}</div>
            )}
            {r.round > 1 && <div className="small muted">前列变化：进 {r.entered.length}，出 {r.left.length}</div>}
          </li>
        ))}
        {running && <li className="pending">检索中…</li>}
      </ol>
      {final && (
        <div className="trace-final">
          {REASONS[final.converged.reason] ?? final.converged.reason} · {final.converged.rounds} 轮 · {(final.elapsed_ms / 1000).toFixed(1)} s
        </div>
      )}
    </aside>
  );
}

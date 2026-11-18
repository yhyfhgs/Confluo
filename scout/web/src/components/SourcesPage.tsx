import { useCallback, useEffect, useState } from "react";
import { api, type SchedulerStatus } from "../api";
import type { Edition, Series, Stats } from "../types";
import { ago, nf } from "../lib/format";
import { RefreshIcon } from "./icons";

const PHASE: Record<string, string> = { in_review: "审稿中", decided: "已出结果", published: "已出版", unknown: "未抓取" };

function EditionRow({ e, onToggle, onCrawl }: { e: Edition; onToggle: (on: boolean) => void; onCrawl: () => void }) {
  const status = e.status === "running" ? "抓取中" : e.status === "queued" ? "排队中" : e.status === "error" || e.status === "attention" ? "异常" : null;
  return (
    <div className={`ed${e.enabled ? "" : " is-off"}`}>
      <label className="switch" title={e.enabled ? "已启用：参与抓取与检索" : "已停用"}>
        <input type="checkbox" checked={e.enabled} onChange={(ev) => onToggle(ev.target.checked)} />
        <span />
      </label>
      <span className="ed-year">{e.year}</span>
      <span className="ed-phase">{PHASE[e.phase] ?? e.phase}</span>
      <span className="ed-num" title="论文 / 有摘要 / 已向量化">
        {nf.format(e.paper_count)}
        <small> / {nf.format(e.abstract_count)} / {nf.format(e.embedded_count)}</small>
      </span>
      <span className="ed-num" title="审稿条数">{e.review_count ? nf.format(e.review_count) : "–"}</span>
      <span className="ed-time" title={e.last_error ?? undefined}>
        {status ? <b className={`st st-${e.status}`}>{status}</b> : ago(e.last_success_at)}
      </span>
      <button className="icon-btn" title="立即更新" onClick={onCrawl} disabled={!e.enabled || e.status === "running"}>
        <RefreshIcon width={16} height={16} />
      </button>
    </div>
  );
}

export function SourcesPage() {
  const [series, setSeries] = useState<Series[]>([]);
  const [stats, setStats] = useState<Stats | null>(null);
  const [sched, setSched] = useState<SchedulerStatus | null>(null);
  const load = useCallback(() => {
    api.venues().then((v) => setSeries(v.series)).catch(() => undefined);
    api.stats().then(setStats).catch(() => undefined);
    api.jobs().then((j) => setSched(j.scheduler)).catch(() => undefined);
  }, []);
  useEffect(() => {
    load();
    const t = window.setInterval(load, 8000);
    return () => window.clearInterval(t);
  }, [load]);
  const groups = new Map<string, Series[]>();
  for (const s of series) {
    const k = s.area ?? "其他";
    groups.set(k, [...(groups.get(k) ?? []), s]);
  }
  const running = sched ? Object.values(sched.running) : [];
  return (
    <div className="sources">
      <div className="sources-head">
        <h1>来源</h1>
        {stats && (
          <p className="muted">
            已启用 {stats.editions_enabled} 届 · 论文 {nf.format(stats.papers)} · 摘要 {nf.format(stats.abstracts)} ·
            向量 {nf.format(stats.embedded)} · 审稿 {nf.format(stats.reviews)}
          </p>
        )}
        {sched && (
          <p className="small muted">
            {running.length ? `正在抓取：${running.join("、")}` : "抓取空闲"}
            {sched.indexer.running ? ` · 向量化中（${sched.indexer.rate}/s）` : ""}
          </p>
        )}
      </div>
      <div className="ed ed-legend" aria-hidden>
        <span>启用</span><span>年份</span><span>阶段</span><span>论文 / 摘要 / 向量</span><span>审稿</span><span>状态</span><span />
      </div>
      {[...groups.entries()].map(([area, list]) => (
        <section key={area} className="area">
          <h2>{area}</h2>
          {list.map((s) => (
            <div key={s.id} className="series">
              <div className="series-head">
                <div>
                  <b>{s.short}</b>
                  <span className="muted"> {s.name}</span>
                </div>
                <div className="tags">{s.ratings.slice(0, 3).map((r) => <span key={r} className="tag">{r}</span>)}</div>
              </div>
              <div className="eds">
                {s.editions.map((e) => (
                  <EditionRow key={e.id} e={e}
                    onToggle={(on) => api.toggle(e.id, on).then(load)}
                    onCrawl={() => api.crawl(e.id).then(load)} />
                ))}
              </div>
            </div>
          ))}
        </section>
      ))}
    </div>
  );
}

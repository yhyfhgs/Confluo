import { useCallback, useEffect, useRef, useState } from "react";
import { api, streamSearch } from "./api";
import { PaperDrawer } from "./components/PaperDrawer";
import { ResultCard } from "./components/ResultCard";
import { type Scope, ScopePicker } from "./components/ScopePicker";
import { SearchBox } from "./components/SearchBox";
import { SourcesPage } from "./components/SourcesPage";
import { TracePanel } from "./components/TracePanel";
import { LayersIcon } from "./components/icons";
import { nf, REASONS } from "./lib/format";
import type { Final, Mode, Plan, Result, RoundInfo, Series, Sort, Stats } from "./types";

const SORTS: { id: Sort; label: string }[] = [
  { id: "mix", label: "综合" },
  { id: "relevance", label: "相关度" },
  { id: "review", label: "审稿分" },
  { id: "tier", label: "录用等级" },
  { id: "recent", label: "最新" },
];
const EXAMPLES = ["如何让大语言模型更准确地报告自己的置信度", "sparse autoencoders for interpretability", "图神经网络在分子性质预测中的应用"];

type View = "search" | "sources";

function readUrl() {
  const p = new URLSearchParams(window.location.search);
  return {
    view: (window.location.pathname.startsWith("/sources") ? "sources" : "search") as View,
    q: p.get("q") ?? "",
    mode: (p.get("mode") as Mode) || "smart",
    sort: (p.get("sort") as Sort) || "mix",
    scope: { venues: (p.get("venues") ?? "").split(",").filter(Boolean), yearFrom: p.get("from") ?? "", yearTo: p.get("to") ?? "" },
  };
}

export default function App() {
  const init = readUrl();
  const [view, setView] = useState<View>(init.view);
  const [input, setInput] = useState(init.q);
  const [query, setQuery] = useState(init.q);
  const [mode, setMode] = useState<Mode>(init.mode);
  const [sort, setSort] = useState<Sort>(init.sort);
  const [scope, setScope] = useState<Scope>(init.scope);
  const [series, setSeries] = useState<Series[]>([]);
  const [stats, setStats] = useState<Stats | null>(null);
  const [plan, setPlan] = useState<Plan | null>(null);
  const [rounds, setRounds] = useState<RoundInfo[]>([]);
  const [results, setResults] = useState<Result[]>([]);
  const [fresh, setFresh] = useState<Set<string>>(new Set());
  const [final, setFinal] = useState<Final | null>(null);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showTrace, setShowTrace] = useState(false);
  const [open, setOpen] = useState<Result | null>(null);
  const stopRef = useRef<(() => void) | null>(null);
  const seenRef = useRef<Set<string>>(new Set());

  useEffect(() => {
    api.venues().then((v) => setSeries(v.series)).catch(() => undefined);
    api.stats().then(setStats).catch(() => undefined);
    const onPop = () => {
      const u = readUrl();
      setView(u.view);
      setInput(u.q);
      setQuery(u.q);
      setMode(u.mode);
      setSort(u.sort);
      setScope(u.scope);
    };
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, []);

  const pushUrl = useCallback((v: View, q: string, m: Mode, s: Sort, sc: Scope) => {
    const p = new URLSearchParams();
    if (q) p.set("q", q);
    if (m !== "smart") p.set("mode", m);
    if (s !== "mix") p.set("sort", s);
    if (sc.venues.length) p.set("venues", sc.venues.join(","));
    if (sc.yearFrom) p.set("from", sc.yearFrom);
    if (sc.yearTo) p.set("to", sc.yearTo);
    const url = (v === "sources" ? "/sources" : "/") + (p.toString() ? `?${p}` : "");
    if (url !== window.location.pathname + window.location.search) window.history.pushState(null, "", url);
  }, []);

  const run = useCallback((q: string, m: Mode, s: Sort, sc: Scope) => {
    stopRef.current?.();
    if (!q.trim()) {
      setQuery("");
      setPlan(null);
      setResults([]);
      setFinal(null);
      return;
    }
    setQuery(q);
    setPlan(null);
    setRounds([]);
    setFinal(null);
    setError(null);
    setRunning(true);
    seenRef.current = new Set();
    const params: Record<string, string> = { q, mode: m, sort: s };
    if (sc.venues.length) params.venues = sc.venues.join(",");
    if (sc.yearFrom) params.year_from = sc.yearFrom;
    if (sc.yearTo) params.year_to = sc.yearTo;
    stopRef.current = streamSearch(params, {
      plan: setPlan,
      round: (r) => setRounds((rs) => [...rs, r]),
      results: (round, rs) => {
        const nowFresh = new Set<string>();
        if (round > 1) rs.slice(0, 10).forEach((r) => !seenRef.current.has(r.uid) && nowFresh.add(r.uid));
        rs.slice(0, 10).forEach((r) => seenRef.current.add(r.uid));
        setFresh(nowFresh);
        setResults(rs);
      },
      done: (f) => {
        setFinal(f);
        setResults(f.results);
        setRunning(false);
      },
      error: (msg) => {
        setError(msg);
        setRunning(false);
      },
    });
  }, []);

  useEffect(() => {
    if (init.q && init.view === "search") run(init.q, init.mode, init.sort, init.scope);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const submit = (q: string, m = mode, s = sort, sc = scope) => {
    setView("search");
    pushUrl("search", q, m, s, sc);
    run(q, m, s, sc);
  };

  const goHome = () => {
    stopRef.current?.();
    setInput("");
    setQuery("");
    setPlan(null);
    setResults([]);
    setFinal(null);
    setRunning(false);
    setView("search");
    pushUrl("search", "", mode, sort, scope);
  };

  const hero = view === "search" && !query;
  const enabledSeries = series.filter((s) => s.editions.some((e) => e.enabled)).length;

  return (
    <div className={`app${hero ? " is-hero" : ""}`}>
      {!hero && (
        <header className="topbar">
          <button className="wordmark small" onClick={goHome} aria-label="回到首页">
            Confluo <span>Scout</span>
          </button>
          {view === "search" ? (
            <SearchBox value={input} mode={mode} size="bar" busy={running} onChange={setInput}
              onMode={(m) => { setMode(m); if (query) submit(input, m); }} onSubmit={(q) => submit(q)} />
          ) : <div className="topbar-fill" />}
          <nav className="nav">
            <button className={view === "search" ? "on" : ""} onClick={() => { setView("search"); pushUrl("search", query, mode, sort, scope); }}>检索</button>
            <button className={view === "sources" ? "on" : ""} onClick={() => { setView("sources"); pushUrl("sources", query, mode, sort, scope); }}>来源</button>
          </nav>
        </header>
      )}

      {hero && (
        <main className="hero">
          <div className="hero-inner">
            <h1 className="wordmark">Confluo <span>Scout</span></h1>
            <p className="hero-sub">
              AI 会议论文检索
              {stats ? ` · ${nf.format(stats.papers)} 篇 · ${enabledSeries} 个会议 · ${nf.format(stats.reviews)} 条审稿` : ""}
            </p>
            <SearchBox value={input} mode={mode} size="hero" busy={running} onChange={setInput} onMode={setMode} onSubmit={(q) => submit(q)} />
            <div className="hero-row">
              <ScopePicker series={series} scope={scope} onChange={setScope} />
              <button className="text-btn" onClick={() => { setView("sources"); pushUrl("sources", "", mode, sort, scope); }}>管理来源</button>
            </div>
            <div className="examples">
              {EXAMPLES.map((e) => (
                <button key={e} className="example" onClick={() => { setInput(e); submit(e); }}>{e}</button>
              ))}
            </div>
          </div>
        </main>
      )}

      {view === "sources" && <SourcesPage />}

      {view === "search" && !hero && (
        <div className={`results-layout${showTrace ? " with-trace" : ""}`}>
          <main className="results">
            <div className="results-head">
              <div className="results-info">
                {error ? <span className="err">检索失败：{error}</span> : (
                  <>
                    {running && <span className="pulse" aria-hidden />}
                    <span>
                      {final ? `${nf.format(final.total_candidates)} 篇候选` : rounds.length ? `第 ${rounds.length} 轮…` : "检索中…"}
                      {final && ` · ${REASONS[final.converged.reason] ?? final.converged.reason}（${final.converged.rounds} 轮，${(final.elapsed_ms / 1000).toFixed(1)} s）`}
                    </span>
                  </>
                )}
              </div>
              <div className="results-tools">
                <ScopePicker series={series} scope={scope} onChange={(sc) => { setScope(sc); submit(query, mode, sort, sc); }} />
                <label className="sort">
                  <span>排序</span>
                  <select value={sort} onChange={(e) => { const s = e.target.value as Sort; setSort(s); submit(query, mode, s); }}>
                    {SORTS.map((s) => <option key={s.id} value={s.id}>{s.label}</option>)}
                  </select>
                </label>
                <button className={`text-btn${showTrace ? " on" : ""}`} onClick={() => setShowTrace((v) => !v)} title="检索过程">
                  <LayersIcon width={16} height={16} /> 过程
                </button>
              </div>
            </div>
            {plan && plan.keywords.length > 0 && (
              <div className="kwline">
                {plan.keywords.filter((k) => k.round === 1).map((k) => (
                  <span key={k.text} className="kwtag" title={k.synonyms.length ? `同义：${k.synonyms.join("、")}` : undefined}>
                    {k.text}{k.origin === "translation" && k.source ? <small>{k.source}</small> : null}
                  </span>
                ))}
                {final && final.keywords.some((k) => k.round > 1) && (
                  <span className="kwmore">+ {final.keywords.filter((k) => k.round > 1).length} 个扩展词</span>
                )}
              </div>
            )}
            {results.map((r) => <ResultCard key={r.uid} r={r} fresh={fresh.has(r.uid)} onOpen={setOpen} />)}
            {!running && final && results.length === 0 && (
              <div className="empty">没有找到匹配的论文。可以换个说法，或在“范围”里放宽会议与年份。</div>
            )}
          </main>
          {showTrace && <TracePanel plan={plan} rounds={rounds} final={final} running={running} />}
        </div>
      )}
      <PaperDrawer result={open} onClose={() => setOpen(null)} />
    </div>
  );
}

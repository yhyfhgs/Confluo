import type { Final, PaperDetail, Plan, Result, RoundInfo, Series, Stats } from "./types";

async function json<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, init);
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return (await res.json()) as T;
}

export const api = {
  stats: () => json<Stats>("/api/stats"),
  venues: () => json<{ series: Series[] }>("/api/venues"),
  toggle: (edition: string, enabled: boolean) =>
    json(`/api/venues/${encodeURIComponent(edition)}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ enabled }),
    }),
  crawl: (edition: string) => json(`/api/venues/${encodeURIComponent(edition)}/crawl`, { method: "POST" }),
  jobs: () => json<{ scheduler: SchedulerStatus | null }>("/api/jobs?limit=10"),
  paper: (id: number | string) => json<PaperDetail>(`/api/papers/${encodeURIComponent(String(id))}`),
  suggest: (q: string) => json<{ items: { term: string; df: number }[] }>(`/api/suggest?q=${encodeURIComponent(q)}`),
  health: () => json<Record<string, unknown>>("/api/health"),
};

export interface SchedulerStatus {
  running: Record<string, string>;
  queued: Record<string, string[]>;
  indexer: { embedded: number; pending: number; rate: number; running: boolean };
}

export interface StreamHandlers {
  plan: (p: Plan) => void;
  round: (r: RoundInfo) => void;
  results: (round: number, results: Result[]) => void;
  done: (f: Final) => void;
  error: (message: string) => void;
}

export function streamSearch(params: Record<string, string>, h: StreamHandlers): () => void {
  const qs = new URLSearchParams(params).toString();
  const es = new EventSource(`/api/search/stream?${qs}`);
  let finished = false;
  es.addEventListener("plan", (e) => h.plan(JSON.parse((e as MessageEvent).data)));
  es.addEventListener("round", (e) => h.round(JSON.parse((e as MessageEvent).data)));
  es.addEventListener("results", (e) => {
    const d = JSON.parse((e as MessageEvent).data);
    h.results(d.round, d.results);
  });
  es.addEventListener("done", (e) => {
    finished = true;
    h.done(JSON.parse((e as MessageEvent).data));
    es.close();
  });
  es.addEventListener("error", (e) => {
    const data = (e as MessageEvent).data;
    if (data) {
      try {
        h.error(JSON.parse(data).message);
      } catch {
        h.error(String(data));
      }
    } else if (!finished) {
      h.error("连接中断");
    }
    es.close();
  });
  return () => es.close();
}

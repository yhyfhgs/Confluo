export const nf = new Intl.NumberFormat("zh-CN");

export function labelClass(label: string | null, status: string): string {
  if (status === "under_review") return "badge badge-review";
  switch ((label || "").toLowerCase()) {
    case "oral":
      return "badge badge-oral";
    case "spotlight":
    case "highlight":
      return "badge badge-spot";
    case "findings":
    case "industry":
    case "demo":
    case "srw":
      return "badge badge-muted";
    default:
      return "badge badge-poster";
  }
}

export function labelText(label: string | null, status: string): string | null {
  if (status === "under_review") return "审稿中";
  if (status === "rejected") return "未录用";
  if (status === "withdrawn") return "已撤稿";
  return label;
}

export function authorsShort(a: string[], n = 4): string {
  if (a.length <= n) return a.join(", ");
  return `${a.slice(0, n).join(", ")} 等 ${a.length} 人`;
}

export function pct(x: number | undefined | null): string {
  if (x === undefined || x === null) return "–";
  return `${Math.round(x * 100)}`;
}

export function ago(iso: string | null): string {
  if (!iso) return "从未";
  const t = new Date(iso).getTime();
  const d = (Date.now() - t) / 1000;
  if (d < 90) return "刚刚";
  if (d < 3600) return `${Math.round(d / 60)} 分钟前`;
  if (d < 86400) return `${Math.round(d / 3600)} 小时前`;
  return `${Math.round(d / 86400)} 天前`;
}

export const REASONS: Record<string, string> = {
  stable: "前 n 名已稳定",
  max_rounds: "达到最多轮数",
  time_budget: "达到时间上限",
  exhausted: "没有新线索",
  exact: "精确匹配",
  empty: "空查询",
};

export function escapeRe(s: string): string {
  return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

/** Client-side highlight for the detail view (the server already marks titles and snippets). */
export function markText(text: string, exact: string[], near: string[]): string {
  const esc = (s: string) => s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  let html = esc(text);
  const apply = (terms: string[], cls: string) => {
    const sorted = [...new Set(terms.filter((t) => t.trim().length > 1))].sort((a, b) => b.length - a.length);
    for (const t of sorted) {
      const re = new RegExp(`(?<![\\w>])(${escapeRe(esc(t))}\\w*)(?![^<]*>)`, "gi");
      html = html.replace(re, `<mark class="${cls}">$1</mark>`);
    }
  };
  apply(exact, "hit");
  apply(near, "near");
  return html;
}

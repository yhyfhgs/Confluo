import { useEffect, useRef, useState } from "react";
import type { Series } from "../types";

export interface Scope {
  venues: string[];
  yearFrom: string;
  yearTo: string;
}

interface Props {
  series: Series[];
  scope: Scope;
  onChange: (s: Scope) => void;
}

export function scopeSummary(series: Series[], scope: Scope): string {
  const enabled = series.filter((s) => s.editions.some((e) => e.enabled));
  const names = scope.venues.length
    ? series.filter((s) => scope.venues.includes(s.id)).map((s) => s.short)
    : [];
  const v = names.length ? names.slice(0, 4).join("、") + (names.length > 4 ? ` 等 ${names.length} 个` : "") : `全部 ${enabled.length} 个会议`;
  const y = scope.yearFrom || scope.yearTo ? ` · ${scope.yearFrom || "…"}–${scope.yearTo || "…"}` : "";
  return v + y;
}

export function ScopePicker({ series, scope, onChange }: Props) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const close = (e: MouseEvent) => ref.current && !ref.current.contains(e.target as Node) && setOpen(false);
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, []);
  const active = series.filter((s) => s.editions.some((e) => e.enabled));
  const years = [...new Set(active.flatMap((s) => s.editions.filter((e) => e.enabled).map((e) => e.year)))].sort();
  const toggle = (id: string) => {
    const v = scope.venues.includes(id) ? scope.venues.filter((x) => x !== id) : [...scope.venues, id];
    onChange({ ...scope, venues: v });
  };
  return (
    <div className="scope" ref={ref}>
      <button type="button" className="scope-btn" onClick={() => setOpen((o) => !o)} aria-expanded={open}>
        范围：{scopeSummary(series, scope)}
      </button>
      {open && (
        <div className="scope-pop">
          <div className="scope-grid">
            {active.map((s) => (
              <label key={s.id} className={scope.venues.includes(s.id) ? "on" : ""}>
                <input type="checkbox" checked={scope.venues.includes(s.id)} onChange={() => toggle(s.id)} />
                {s.short}
              </label>
            ))}
          </div>
          <div className="scope-years">
            <span>年份</span>
            <select value={scope.yearFrom} onChange={(e) => onChange({ ...scope, yearFrom: e.target.value })}>
              <option value="">不限</option>
              {years.map((y) => <option key={y} value={y}>{y}</option>)}
            </select>
            <span>至</span>
            <select value={scope.yearTo} onChange={(e) => onChange({ ...scope, yearTo: e.target.value })}>
              <option value="">不限</option>
              {years.map((y) => <option key={y} value={y}>{y}</option>)}
            </select>
            <button type="button" className="text-btn" onClick={() => onChange({ venues: [], yearFrom: "", yearTo: "" })}>清空</button>
          </div>
        </div>
      )}
    </div>
  );
}

import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import type { Mode } from "../types";
import { SearchIcon } from "./icons";

interface Props {
  value: string;
  mode: Mode;
  size: "hero" | "bar";
  busy: boolean;
  onChange: (v: string) => void;
  onMode: (m: Mode) => void;
  onSubmit: (v: string) => void;
}

export function SearchBox({ value, mode, size, busy, onChange, onMode, onSubmit }: Props) {
  const [items, setItems] = useState<string[]>([]);
  const [active, setActive] = useState(-1);
  const [open, setOpen] = useState(false);
  const timer = useRef<number | undefined>(undefined);
  const input = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (size === "hero") input.current?.focus();
  }, [size]);

  useEffect(() => {
    window.clearTimeout(timer.current);
    const last = value.split(/\s+/).slice(-3).join(" ").trim();
    if (!open || last.length < 2 || /[:"]/.test(last)) {
      setItems([]);
      return;
    }
    timer.current = window.setTimeout(() => {
      api.suggest(last).then((r) => setItems(r.items.map((x) => x.term).filter((t) => t !== last.toLowerCase())))
        .catch(() => setItems([]));
    }, 160);
  }, [value, open]);

  const pick = (term: string) => {
    const words = value.split(/\s+/);
    // Replace the partial tail that the suggestion completes.
    let cut = words.length;
    for (let k = Math.min(3, words.length); k >= 1; k--) {
      const tail = words.slice(-k).join(" ").toLowerCase();
      if (term.startsWith(tail)) {
        cut = words.length - k;
        break;
      }
    }
    const next = [...words.slice(0, cut), term].join(" ").trim() + " ";
    onChange(next);
    setItems([]);
    setActive(-1);
    input.current?.focus();
  };

  return (
    <form
      className={`search search-${size}${busy ? " is-busy" : ""}`}
      onSubmit={(e) => {
        e.preventDefault();
        setOpen(false);
        setItems([]);
        onSubmit(value);
      }}
      role="search"
    >
      <SearchIcon className="search-icon" aria-hidden />
      <input
        ref={input}
        value={value}
        onChange={(e) => {
          onChange(e.target.value);
          setOpen(true);
          setActive(-1);
        }}
        onKeyDown={(e) => {
          if (!items.length) return;
          if (e.key === "ArrowDown") {
            e.preventDefault();
            setActive((a) => Math.min(items.length - 1, a + 1));
          } else if (e.key === "ArrowUp") {
            e.preventDefault();
            setActive((a) => Math.max(-1, a - 1));
          } else if (e.key === "Tab" || (e.key === "Enter" && active >= 0)) {
            e.preventDefault();
            pick(items[Math.max(0, active)]);
          } else if (e.key === "Escape") {
            setItems([]);
          }
        }}
        onBlur={() => window.setTimeout(() => setOpen(false), 120)}
        placeholder={mode === "smart" ? "用一句话描述想找的研究，中英文都可以" : "关键词、\"短语\"、AND / OR / NOT、venue:iclr year:2025..2027"}
        aria-label="检索"
        spellCheck={false}
        autoComplete="off"
      />
      <div className="mode" role="radiogroup" aria-label="检索方式">
        {(["smart", "exact"] as Mode[]).map((m) => (
          <button
            key={m}
            type="button"
            role="radio"
            aria-checked={mode === m}
            className={mode === m ? "on" : ""}
            onClick={() => onMode(m)}
            title={m === "smart" ? "多跳语义检索：关键词、同义词、向量与决策模型" : "传统关键词匹配：BM25 与布尔语法"}
          >
            {m === "smart" ? "智能" : "精确"}
          </button>
        ))}
      </div>
      {open && items.length > 0 && (
        <ul className="suggest" role="listbox">
          {items.map((t, i) => (
            <li key={t} role="option" aria-selected={i === active} className={i === active ? "on" : ""}
              onMouseDown={(e) => { e.preventDefault(); pick(t); }}>
              {t}
            </li>
          ))}
        </ul>
      )}
      <div className="search-progress" aria-hidden />
    </form>
  );
}

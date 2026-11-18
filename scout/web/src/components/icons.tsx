import type { SVGProps } from "react";

const base = { width: 18, height: 18, viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", strokeWidth: 1.8,
  strokeLinecap: "round" as const, strokeLinejoin: "round" as const };

export const SearchIcon = (p: SVGProps<SVGSVGElement>) => (
  <svg {...base} {...p}><circle cx="11" cy="11" r="6.5" /><path d="M16 16l4.5 4.5" /></svg>
);
export const CloseIcon = (p: SVGProps<SVGSVGElement>) => (
  <svg {...base} {...p}><path d="M6 6l12 12M18 6L6 18" /></svg>
);
export const RefreshIcon = (p: SVGProps<SVGSVGElement>) => (
  <svg {...base} {...p}><path d="M20 11a8 8 0 1 0-2.3 5.7" /><path d="M20 5v6h-6" /></svg>
);
export const ChevronIcon = (p: SVGProps<SVGSVGElement>) => (
  <svg {...base} {...p}><path d="M9 6l6 6-6 6" /></svg>
);
export const CopyIcon = (p: SVGProps<SVGSVGElement>) => (
  <svg {...base} {...p}><rect x="8" y="8" width="12" height="12" rx="2" /><path d="M16 8V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h2" /></svg>
);
export const LayersIcon = (p: SVGProps<SVGSVGElement>) => (
  <svg {...base} {...p}><path d="M12 3l9 5-9 5-9-5 9-5z" /><path d="M3 13l9 5 9-5" /></svg>
);

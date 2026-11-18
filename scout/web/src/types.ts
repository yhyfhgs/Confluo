export type Mode = "smart" | "exact";
export type Sort = "mix" | "relevance" | "review" | "tier" | "recent";

export interface Keyword {
  text: string;
  weight: number;
  round: number;
  origin: "query" | "translation" | "seed";
  source: string | null;
  synonyms: string[];
  fuzzy: string[];
}

export interface ReviewStats {
  n: number;
  mean: number;
  min: number;
  max: number;
  std: number;
  confidence: number | null;
  z?: number;
  R?: number;
}

export interface Judgment {
  source: string;
  relevance: number;
  keywords: Record<string, number>;
  extension: number;
  confidence: number;
}

export interface Result {
  rank: number;
  id: number;
  uid: string;
  title: string;
  title_plain: string;
  authors: string[];
  venue: string;
  series: string;
  year: number;
  edition: string;
  status: string;
  decision_label: string | null;
  tier: number | null;
  track: string | null;
  area: string | null;
  keywords: string[];
  tldr: string | null;
  snippet: string;
  has_abstract: boolean;
  review: ReviewStats | null;
  quality: number;
  score: number;
  relevance: number;
  components: Record<string, number>;
  matched: { exact: string[]; near: string[] };
  hop: number;
  via: string[];
  decision: Judgment | null;
  links: { forum: string | null; pdf: string | null; proceedings: string | null; doi: string | null };
}

export interface RoundInfo {
  round: number;
  new_keywords: Keyword[];
  seeds: string[];
  added: number;
  pool: number;
  judged: number;
  top: string[];
  entered: string[];
  left: string[];
  ms: number;
}

export interface Plan {
  mode: Mode;
  keywords: Keyword[];
  expression?: string | null;
  decision: { model: string; remote: boolean; available?: boolean };
  scope: { editions: number; statuses: string[]; min_tier: number | null; restricted: number | null };
  cjk?: boolean;
}

export interface Final {
  query: string;
  mode: Mode;
  keywords: Keyword[];
  results: Result[];
  trace: RoundInfo[];
  converged: { reason: string; rounds: number; stable: boolean };
  total_candidates: number;
  elapsed_ms: number;
}

export interface Edition {
  id: string;
  year: number;
  label: string;
  phase: string;
  enabled: boolean;
  status: string;
  paper_count: number;
  abstract_count: number;
  review_count: number;
  embedded_count: number;
  last_success_at: string | null;
  last_crawl_at: string | null;
  next_due_at: string | null;
  last_error: string | null;
  discovered: number;
  sources: string[];
}

export interface Series {
  id: string;
  short: string;
  name: string;
  kind: string;
  area: string | null;
  ratings: string[];
  homepage: string | null;
  editions: Edition[];
}

export interface Stats {
  papers: number;
  abstracts: number;
  embedded: number;
  with_reviews: number;
  reviews: number;
  editions_enabled: number;
  concepts: number;
}

export interface Review {
  review_key: string;
  rating: number | null;
  rating_raw: string | null;
  confidence: number | null;
  subscores: Record<string, number>;
  updated_at: string | null;
}

export interface PaperDetail {
  id: number;
  uid: string;
  title: string;
  authors: string[];
  keywords: string[];
  area_native: string | null;
  area_secondary: string | null;
  tldr: string | null;
  status: string;
  decision_label: string | null;
  tier: number | null;
  track: string | null;
  forum_url: string | null;
  pdf_url: string | null;
  proceedings_url: string | null;
  doi: string | null;
  abstract: string;
  venue: string;
  year: number | null;
  series: { short: string; name: string; ratings: string[] } | null;
  review_stats: ReviewStats | null;
  edition_stats: { rating_mean: number | null; rating_std: number | null; n_reviews: number } | null;
  reviews: Review[];
  sources: string[];
  bibtex: string;
  quality: number | null;
}

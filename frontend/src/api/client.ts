import type {
  AgentPerformanceSummary,
  AnalysisHistoryItem,
  BacktestSummary,
  CEOReport,
  HotSectorsReport,
  PortfolioAdvice,
  SearchResults,
  ScreeningResult,
  WatchlistAddRequest,
  WatchlistItem,
  WatchlistSummaryItem,
} from "@/types/api";

/**
 * API 기본 경로 — 개발(Vite `/api` 프록시)과 프로덕션(동일 출처 `/api`) 동일
 */
const BASE = "/api";

async function fetchJson<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    headers: {
      Accept: "application/json",
      ...init?.headers,
    },
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = (await res.json()) as { detail?: unknown };
      if (typeof body.detail === "string") detail = body.detail;
      else if (body.detail !== undefined) detail = JSON.stringify(body.detail);
    } catch {
      /* ignore */
    }
    throw new Error(detail || `HTTP ${res.status}`);
  }
  if (res.status === 204) {
    return undefined as T;
  }
  return res.json() as Promise<T>;
}

export async function getHealth(): Promise<{
  status: string;
  timestamp: string;
  listen_port?: number;
}> {
  return fetchJson("/health");
}

export async function analyzeTicker(
  ticker: string,
  opts?: { persist?: boolean; useStatsWeights?: boolean }
): Promise<CEOReport> {
  const p = new URLSearchParams();
  if (opts?.persist === false) p.set("persist", "false");
  if (opts?.useStatsWeights === false) p.set("use_stats_weights", "false");
  const q = p.toString();
  return fetchJson(`/analyze/${encodeURIComponent(ticker)}${q ? `?${q}` : ""}`);
}

export async function screenTickers(
  tickers: string,
  useStatsWeights = false
): Promise<ScreeningResult[]> {
  const p = new URLSearchParams({ tickers });
  if (useStatsWeights) p.set("use_stats_weights", "true");
  return fetchJson(`/screen?${p.toString()}`);
}

export async function getHotSectors(pool = 12, top = 5): Promise<HotSectorsReport> {
  const p = new URLSearchParams({
    pool: String(pool),
    top: String(top),
  });
  return fetchJson(`/sector/hot?${p.toString()}`);
}

export async function searchSymbols(q: string, limit = 8): Promise<SearchResults> {
  const p = new URLSearchParams({
    q,
    limit: String(limit),
  });
  return fetchJson(`/search?${p.toString()}`);
}

export async function getPortfolioAdvice(
  holdings: string,
  focus?: string
): Promise<PortfolioAdvice> {
  const p = new URLSearchParams({ holdings });
  if (focus) p.set("focus", focus);
  return fetchJson(`/portfolio/advice?${p.toString()}`);
}

export async function getAgentsStats(
  horizon: 30 | 60 | 90 = 30
): Promise<AgentPerformanceSummary> {
  const p = new URLSearchParams({ horizon: String(horizon) });
  return fetchJson(`/agents/stats?${p.toString()}`);
}

export async function getRecentReports(limit = 50): Promise<AnalysisHistoryItem[]> {
  const p = new URLSearchParams({ limit: String(limit) });
  return fetchJson(`/reports/recent?${p.toString()}`);
}

export async function getBacktestSummary(
  horizon: 30 | 60 | 90 = 30,
  limit = 100
): Promise<BacktestSummary> {
  const p = new URLSearchParams({
    horizon: String(horizon),
    limit: String(limit),
  });
  return fetchJson(`/backtest/summary?${p.toString()}`);
}

export async function getWatchlistSummary(): Promise<WatchlistSummaryItem[]> {
  return fetchJson("/watchlist/summary");
}

export async function addWatchlistItem(body: WatchlistAddRequest): Promise<WatchlistItem> {
  return fetchJson("/watchlist", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(body),
  });
}

export async function removeWatchlistItem(ticker: string): Promise<void> {
  await fetchJson<void>(`/watchlist/${encodeURIComponent(ticker)}`, {
    method: "DELETE",
  });
}

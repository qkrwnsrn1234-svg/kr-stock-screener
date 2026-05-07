/** 백엔드 API와 맞춘 TypeScript 타입 정의 */

export interface AgentResponse {
  opinion: string;
  confidence: number;
  score: number;
  reasoning: string;
  signals: Record<string, unknown>;
  agent_name: string;
  timestamp: string;
}

/** 퀀트 `consensus_gap_proxy` — 동종 PER/PBR 중앙값 기준 내재가 vs 현재가 */
export interface ConsensusGapProxy {
  note?: string;
  median_per_implied_price?: number | null;
  median_pbr_implied_price?: number | null;
  current_price_krw?: number | null;
  gap_pct_vs_median_per?: number | null;
  gap_pct_vs_median_pbr?: number | null;
  blended_gap_pct?: number | null;
  peer_sector?: string | null;
  peer_count?: number | null;
}

export interface AnnualNetIncomeRow {
  year: number;
  net_income_krw: number;
  fs_div?: string;
  yoy_pct?: number | null;
}

/** 퀀트 `earnings_surprise_proxy` — 연간 순이익 YoY·가속도(컨센 서프라이즈는 별도 데이터) */
export interface EarningsSurpriseProxy {
  annual_net_income: AnnualNetIncomeRow[];
  yoy_acceleration_pp?: number | null;
  positive_yoy_streak_years?: number;
  interpretation_note?: string;
}

/** 퀀트 `insider_disclosure_hints` — 공시 제목 휴리스틱 */
export interface InsiderDisclosureHints {
  window_days?: number;
  buy_like_disclosure_titles?: number;
  sell_like_disclosure_titles?: number;
  major_holder_related_titles?: number;
  sample_titles?: string[];
  heuristic_bias?: string;
  note?: string;
}

export interface UndervalueBreakdown {
  per_score: number;
  pbr_score: number;
  fcf_yield_score: number;
  fscore_score: number;
  combined: number;
  peer_count: number;
  sector_label?: string | null;
  fcf_note: string;
}

export interface OverheatAlert {
  level: string;
  heat_score: number;
  reasons: string[];
}

export interface ScreeningResult {
  ticker: string;
  undervalue_score: number;
  overheat_flag: boolean;
  undervalue_breakdown?: UndervalueBreakdown | null;
  overheat_alert?: OverheatAlert | null;
  agent_reports: AgentResponse[];
  timestamp: string;
}

export interface CEOReport {
  ticker: string;
  final_opinion: string;
  buy_pct: number;
  neutral_pct: number;
  sell_pct: number;
  summary_lines: string[];
  agent_reports: AgentResponse[];
  risk_rebuttal: string;
  timestamp: string;
  stats_weights_applied?: boolean;
  agent_weight_multipliers?: Record<string, number>;
  claude_summary_applied?: boolean;
  claude_model?: string | null;
}

export interface HotSectorItem {
  sector_name: string;
  representative_ticker: string;
  relative_outperformance_60d: number | null;
  strength_score: number;
  summary: string;
  etf_proxy_code?: string | null;
  etf_proxy_label?: string | null;
  etf_flow_summary?: string | null;
  earnings_revision_note?: string | null;
}

export interface HotSectorsReport {
  items: HotSectorItem[];
  timestamp: string;
}

export interface SearchResultItem {
  ticker: string;
  name: string;
  market?: string | null;
  sector?: string | null;
}

export interface SearchResults {
  items: SearchResultItem[];
  timestamp: string;
}

export interface PortfolioAdvice {
  weight_suggestion: Record<string, number>;
  risk_level: string;
  advice: string;
  timestamp: string;
}

export interface AnalysisHistoryItem {
  id: number;
  ticker: string;
  analyzed_at: string;
  ref_price: number | null;
  final_opinion: string | null;
  return_30d: number | null;
  return_60d: number | null;
  return_90d: number | null;
}

export interface BacktestOpinionBucket {
  opinion: string;
  samples: number;
  hit_rate: number | null;
  average_return: number | null;
}

export interface BacktestRecordItem {
  id: number;
  ticker: string;
  analyzed_at: string;
  final_opinion: string;
  ref_price: number | null;
  forward_return: number;
  hit: boolean;
  equity_curve: number;
}

export interface BacktestSummary {
  horizon_trading_days: number;
  total_records: number;
  evaluated_records: number;
  hit_rate: number | null;
  average_return: number | null;
  cumulative_return: number | null;
  by_opinion: BacktestOpinionBucket[];
  records: BacktestRecordItem[];
  timestamp: string;
}

export interface AgentStatRow {
  agent_name: string;
  samples: number;
  hits: number;
  hit_rate: number | null;
}

export interface WatchlistItem {
  id: number;
  ticker: string;
  added_at: string;
  memo: string;
}

export interface WatchlistSummaryItem extends WatchlistItem {
  name: string;
  market?: string | null;
  sector?: string | null;
  current_price?: number | null;
  change_pct?: number | null;
}

export interface WatchlistAddRequest {
  ticker: string;
  memo?: string;
}

export interface AgentPerformanceSummary {
  evaluated_records: number;
  horizon_trading_days: number;
  by_agent: AgentStatRow[];
  ceo: AgentStatRow;
  timestamp: string;
}

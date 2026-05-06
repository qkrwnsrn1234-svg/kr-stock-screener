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

export interface AgentStatRow {
  agent_name: string;
  samples: number;
  hits: number;
  hit_rate: number | null;
}

export interface AgentPerformanceSummary {
  evaluated_records: number;
  horizon_trading_days: number;
  by_agent: AgentStatRow[];
  ceo: AgentStatRow;
  timestamp: string;
}

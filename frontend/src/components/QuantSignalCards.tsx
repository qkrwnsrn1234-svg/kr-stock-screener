import type {
  AgentResponse,
  AnnualNetIncomeRow,
  CEOReport,
  ConsensusGapProxy,
  EarningsSurpriseProxy,
  InsiderDisclosureHints,
} from "@/types/api";

function isRecord(x: unknown): x is Record<string, unknown> {
  return typeof x === "object" && x !== null && !Array.isArray(x);
}

function asConsensusGap(x: unknown): ConsensusGapProxy | null {
  if (!isRecord(x)) return null;
  return x as ConsensusGapProxy;
}

function asEarningsSurprise(x: unknown): EarningsSurpriseProxy | null {
  if (!isRecord(x)) return null;
  const rows = x.annual_net_income;
  if (rows !== undefined && !Array.isArray(rows)) return null;
  const normalized: EarningsSurpriseProxy = {
    annual_net_income: Array.isArray(rows) ? (rows as AnnualNetIncomeRow[]) : [],
    yoy_acceleration_pp: x.yoy_acceleration_pp as number | null | undefined,
    positive_yoy_streak_years: x.positive_yoy_streak_years as number | undefined,
    interpretation_note: x.interpretation_note as string | undefined,
  };
  return normalized;
}

function asInsiderHints(x: unknown): InsiderDisclosureHints | null {
  if (!isRecord(x)) return null;
  return x as InsiderDisclosureHints;
}

function pickQuantAgent(reports: AgentResponse[]): AgentResponse | null {
  const found = reports.find(
    (r) => (r.agent_name ?? "").includes("퀀트") || (r.agent_name ?? "").toLowerCase().includes("quant"),
  );
  return found ?? null;
}

function formatKrw(n: number): string {
  return `${n.toLocaleString("ko-KR", { maximumFractionDigits: 0 })}원`;
}

function formatEok(n: number): string {
  return `${(n / 1e8).toLocaleString("ko-KR", { maximumFractionDigits: 1 })}억`;
}

function gapColorClass(pct: number): string {
  if (pct > 3) return "var(--color-up)";
  if (pct < -3) return "var(--color-down)";
  return "var(--color-text-secondary)";
}

function yoyColorClass(pct: number): string {
  if (pct > 0) return "var(--color-up)";
  if (pct < 0) return "var(--color-down)";
  return "var(--color-text-secondary)";
}

interface QuantSignalCardsProps {
  report: CEOReport;
}

/**
 * 퀀트 에이전트 신호(동종 괴리·연간 YoY·공시 힌트)를 카드 그리드로 표시합니다.
 */
export function QuantSignalCards({ report }: QuantSignalCardsProps) {
  const quant = pickQuantAgent(report.agent_reports);
  if (!quant) {
    return (
      <div className="card muted" style={{ marginTop: "1rem" }}>
        퀀트 에이전트 응답이 없어 시그널 카드를 표시하지 않습니다.
      </div>
    );
  }

  const gap = asConsensusGap(quant.signals.consensus_gap_proxy);
  const earn = asEarningsSurprise(quant.signals.earnings_surprise_proxy);
  const ins = asInsiderHints(quant.signals.insider_disclosure_hints);

  const blend = gap?.blended_gap_pct;

  const annualRows: AnnualNetIncomeRow[] = earn?.annual_net_income ?? [];
  const displayRows = [...annualRows].sort((a, b) => b.year - a.year).slice(0, 5);

  return (
    <section style={{ marginTop: "1.25rem" }}>
      <h2 style={{ marginBottom: "0.75rem" }}>퀀트 시그널</h2>
      <div
        className="row"
        style={{
          alignItems: "stretch",
          flexWrap: "wrap",
          gap: "1rem",
        }}
      >
        {/* 동종 밸류 괴리 */}
        <div className="card" style={{ flex: "1 1 280px", minWidth: 260 }}>
          <h3 style={{ marginTop: 0, fontSize: "1rem", color: "var(--color-accent)" }}>
            동종 밸류 괴리
          </h3>
          <p className="muted" style={{ fontSize: "0.8rem", marginTop: 0 }}>
            애널 목표가 대신 동종 PER·PBR 중앙값으로 본 근사 내재가
          </p>
          {typeof blend === "number" ? (
            <p
              style={{
                fontFamily: "var(--font-mono)",
                fontSize: "1.35rem",
                fontWeight: 600,
                margin: "0.5rem 0",
                color: gapColorClass(blend),
              }}
            >
              {blend >= 0 ? "+" : ""}
              {blend.toFixed(1)}%
              <span className="muted" style={{ fontSize: "0.75rem", marginLeft: 8, fontWeight: 400 }}>
                (현재가 대비)
              </span>
            </p>
          ) : (
            <p className="muted">표본·가격·EPS 부족으로 괴리율을 계산하지 못했습니다.</p>
          )}
          {gap?.current_price_krw != null ? (
            <p className="muted" style={{ fontSize: "0.85rem", margin: "0.25rem 0" }}>
              종가:{" "}
              <span style={{ fontFamily: "var(--font-mono)", color: "var(--color-text-primary)" }}>
                {formatKrw(gap.current_price_krw)}
              </span>
            </p>
          ) : null}
          {gap?.median_per_implied_price != null ? (
            <p className="muted" style={{ fontSize: "0.85rem", margin: "0.25rem 0" }}>
              PER중앙 내재가:{" "}
              <span style={{ fontFamily: "var(--font-mono)", color: "var(--color-text-primary)" }}>
                {formatKrw(gap.median_per_implied_price)}
              </span>
              {gap.gap_pct_vs_median_per != null ? (
                <span style={{ color: gapColorClass(gap.gap_pct_vs_median_per), marginLeft: 6 }}>
                  ({gap.gap_pct_vs_median_per >= 0 ? "+" : ""}
                  {gap.gap_pct_vs_median_per}%)
                </span>
              ) : null}
            </p>
          ) : null}
          {gap?.median_pbr_implied_price != null ? (
            <p className="muted" style={{ fontSize: "0.85rem", margin: "0.25rem 0" }}>
              PBR중앙 내재가:{" "}
              <span style={{ fontFamily: "var(--font-mono)", color: "var(--color-text-primary)" }}>
                {formatKrw(gap.median_pbr_implied_price)}
              </span>
              {gap.gap_pct_vs_median_pbr != null ? (
                <span style={{ color: gapColorClass(gap.gap_pct_vs_median_pbr), marginLeft: 6 }}>
                  ({gap.gap_pct_vs_median_pbr >= 0 ? "+" : ""}
                  {gap.gap_pct_vs_median_pbr}%)
                </span>
              ) : null}
            </p>
          ) : null}
          {gap?.peer_sector ? (
            <p className="muted" style={{ fontSize: "0.75rem", marginTop: "0.75rem" }}>
              동종 Dept: {gap.peer_sector}
              {typeof gap.peer_count === "number" ? ` · 표본 ${gap.peer_count}종` : null}
            </p>
          ) : null}
          {gap?.note ? (
            <p className="muted" style={{ fontSize: "0.72rem", marginTop: "0.5rem", lineHeight: 1.4 }}>
              {gap.note}
            </p>
          ) : null}
        </div>

        {/* 연간 실적 YoY */}
        <div className="card" style={{ flex: "1 1 280px", minWidth: 260 }}>
          <h3 style={{ marginTop: 0, fontSize: "1rem", color: "var(--color-accent)" }}>
            연간 실적·YoY
          </h3>
          {typeof earn?.yoy_acceleration_pp === "number" ? (
            <p style={{ margin: "0.35rem 0", fontFamily: "var(--font-mono)", fontSize: "0.95rem" }}>
              YoY 가속도:{" "}
              <span style={{ color: gapColorClass(earn.yoy_acceleration_pp) }}>
                {earn.yoy_acceleration_pp >= 0 ? "+" : ""}
                {earn.yoy_acceleration_pp.toFixed(1)}pp
              </span>
            </p>
          ) : (
            <p className="muted" style={{ fontSize: "0.85rem" }}>
              가속도는 연도별 데이터가 2개 이상일 때만 계산됩니다.
            </p>
          )}
          {typeof earn?.positive_yoy_streak_years === "number" && earn.positive_yoy_streak_years > 0 ? (
            <p className="muted" style={{ fontSize: "0.85rem", margin: "0.25rem 0" }}>
              순이익 YoY 플러스 연속:{" "}
              <strong style={{ color: "var(--color-hold)" }}>{earn.positive_yoy_streak_years}년</strong>
            </p>
          ) : null}
          {displayRows.length > 0 ? (
            <table
              style={{
                width: "100%",
                fontSize: "0.8rem",
                borderCollapse: "collapse",
                marginTop: "0.5rem",
              }}
            >
              <thead>
                <tr style={{ color: "var(--color-text-secondary)", textAlign: "left" }}>
                  <th style={{ padding: "4px 6px 4px 0", borderBottom: "1px solid var(--color-border)" }}>
                    연도
                  </th>
                  <th style={{ padding: "4px 6px", borderBottom: "1px solid var(--color-border)" }}>
                    당기순이익
                  </th>
                  <th style={{ padding: "4px 0 4px 6px", borderBottom: "1px solid var(--color-border)" }}>
                    YoY
                  </th>
                </tr>
              </thead>
              <tbody>
                {displayRows.map((row) => (
                  <tr key={row.year}>
                    <td style={{ padding: "4px 6px 4px 0", fontFamily: "var(--font-mono)" }}>{row.year}</td>
                    <td style={{ padding: "4px 6px", fontFamily: "var(--font-mono)" }}>
                      {formatEok(row.net_income_krw)}
                    </td>
                    <td
                      style={{
                        padding: "4px 0 4px 6px",
                        fontFamily: "var(--font-mono)",
                        color:
                          row.yoy_pct == null
                            ? "var(--color-text-secondary)"
                            : yoyColorClass(row.yoy_pct),
                      }}
                    >
                      {row.yoy_pct == null ? "—" : `${row.yoy_pct >= 0 ? "+" : ""}${row.yoy_pct}%`}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <p className="muted" style={{ fontSize: "0.85rem" }}>
              DART 사업보고서 기반 순이익 시계열이 없습니다.
            </p>
          )}
          {earn?.interpretation_note ? (
            <p className="muted" style={{ fontSize: "0.72rem", marginTop: "0.65rem", lineHeight: 1.4 }}>
              {earn.interpretation_note}
            </p>
          ) : null}
        </div>

        {/* 공시 힌트 */}
        <div className="card" style={{ flex: "1 1 280px", minWidth: 260 }}>
          <h3 style={{ marginTop: 0, fontSize: "1rem", color: "var(--color-accent)" }}>
            공시 힌트 (자사주·주요주주)
          </h3>
          <p className="muted" style={{ fontSize: "0.8rem", marginTop: 0 }}>
            최근 {ins?.window_days ?? "—"}일 공시 제목 패턴(참고용)
          </p>
          <ul
            style={{
              margin: "0.5rem 0",
              paddingLeft: "1rem",
              fontFamily: "var(--font-mono)",
              fontSize: "0.85rem",
              lineHeight: 1.6,
            }}
          >
            <li>
              매수 연계 추정:{" "}
              <strong>{ins?.buy_like_disclosure_titles ?? 0}</strong>건
            </li>
            <li>
              매도 연계 추정:{" "}
              <strong>{ins?.sell_like_disclosure_titles ?? 0}</strong>건
            </li>
            <li>
              주요주주·소유상황류:{" "}
              <strong>{ins?.major_holder_related_titles ?? 0}</strong>건
            </li>
          </ul>
          {ins?.heuristic_bias && ins.heuristic_bias !== "중립" ? (
            <p style={{ fontSize: "0.82rem", margin: "0.35rem 0" }}>
              휴리스틱 성향: <span className="tag tag-neutral">{ins.heuristic_bias}</span>
            </p>
          ) : (
            <p className="muted" style={{ fontSize: "0.82rem" }}>
              휴리스틱 성향: 중립 (건수 부족 또는 균형)
            </p>
          )}
          {ins?.sample_titles && ins.sample_titles.length > 0 ? (
            <div style={{ marginTop: "0.5rem" }}>
              <p className="muted" style={{ fontSize: "0.72rem", margin: "0 0 0.25rem" }}>
                샘플 제목
              </p>
              <ul
                style={{
                  margin: 0,
                  paddingLeft: "1rem",
                  fontSize: "0.72rem",
                  color: "var(--color-text-secondary)",
                  lineHeight: 1.45,
                }}
              >
                {ins.sample_titles.map((t) => (
                  <li key={t}>{t}</li>
                ))}
              </ul>
            </div>
          ) : null}
          {ins?.note ? (
            <p className="muted" style={{ fontSize: "0.72rem", marginTop: "0.65rem", lineHeight: 1.4 }}>
              {ins.note}
            </p>
          ) : null}
        </div>
      </div>
    </section>
  );
}

/** 에이전트 상세에서 퀀트 JSON 덤프를 숨길지 여부 */
export function shouldHideQuantSignalsRaw(agent: AgentResponse): boolean {
  return (agent.agent_name ?? "").includes("퀀트");
}

import { useEffect, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { getBacktestSummary } from "@/api/client";
import type { BacktestSummary } from "@/types/api";

type Horizon = 30 | 60 | 90;

function formatPercent(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined) return "-";
  const pct = value * 100;
  return `${pct >= 0 ? "+" : ""}${pct.toFixed(digits)}%`;
}

function percentClass(value: number | null | undefined): string {
  if (value === null || value === undefined) return "muted";
  return value >= 0 ? "text-positive font-tabular" : "text-negative font-tabular";
}

/**
 * 저장된 분석 이력 기반 백테스트 결과 대시보드
 */
export function BacktestPage() {
  const [horizon, setHorizon] = useState<Horizon>(30);
  const [summary, setSummary] = useState<BacktestSummary | null>(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const load = async (nextHorizon = horizon) => {
    setLoading(true);
    setErr(null);
    try {
      const data = await getBacktestSummary(nextHorizon, 150);
      setSummary(data);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "백테스트 조회 실패");
      setSummary(null);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const curveData =
    summary?.records.map((row, index) => ({
      index: index + 1,
      ticker: row.ticker,
      analyzed_at: row.analyzed_at.slice(0, 10),
      equity: row.equity_curve * 100,
      forward_return: row.forward_return * 100,
    })) ?? [];

  const opinionData =
    summary?.by_opinion.map((row) => ({
      opinion: row.opinion,
      samples: row.samples,
      hit_rate: row.hit_rate != null ? row.hit_rate * 100 : 0,
      average_return: row.average_return != null ? row.average_return * 100 : 0,
    })) ?? [];

  return (
    <>
      <h1 style={{ marginTop: 0 }}>백테스트</h1>
      <div className="card">
        <p className="muted">
          저장된 CEO 분석 의견을 기준으로 선택한 거래일 뒤 수익률과 방향 적중률을 계산합니다.
        </p>
        <div className="row" style={{ alignItems: "center" }}>
          <label className="muted">
            평가 거래일
            <select
              className="input"
              style={{ marginLeft: 8 }}
              value={horizon}
              onChange={(e) => {
                const next = Number(e.target.value) as Horizon;
                setHorizon(next);
                void load(next);
              }}
            >
              <option value={30}>30일</option>
              <option value={60}>60일</option>
              <option value={90}>90일</option>
            </select>
          </label>
          <button type="button" className="btn" disabled={loading} onClick={() => void load()}>
            {loading ? "조회 중..." : "백테스트 갱신"}
          </button>
        </div>
        {err ? <p className="error">{err}</p> : null}
      </div>

      {summary ? (
        <>
          <div className="backtest-kpi-grid">
            <div className="card">
              <h2>평가 표본</h2>
              <p className="backtest-kpi">{summary.evaluated_records.toLocaleString("ko-KR")}건</p>
              <p className="muted">저장 이력 {summary.total_records.toLocaleString("ko-KR")}건 중 평가 가능</p>
            </div>
            <div className="card">
              <h2>방향 적중률</h2>
              <p className="backtest-kpi">{summary.hit_rate != null ? `${(summary.hit_rate * 100).toFixed(1)}%` : "-"}</p>
              <p className="muted">매수는 상승, 매도는 하락, 중립은 ±4% 이내 기준</p>
            </div>
            <div className="card">
              <h2>평균 수익률</h2>
              <p className={`backtest-kpi ${percentClass(summary.average_return)}`}>
                {formatPercent(summary.average_return)}
              </p>
              <p className="muted">{summary.horizon_trading_days}거래일 뒤 단순 평균</p>
            </div>
            <div className="card">
              <h2>누적 수익률</h2>
              <p className={`backtest-kpi ${percentClass(summary.cumulative_return)}`}>
                {formatPercent(summary.cumulative_return)}
              </p>
              <p className="muted">평가 건을 동일 비중으로 순차 투자한 근사값</p>
            </div>
          </div>

          {curveData.length > 0 ? (
            <div className="card">
              <h2>누적 수익 곡선</h2>
              <div style={{ width: "100%", height: 300 }}>
                <ResponsiveContainer>
                  <LineChart data={curveData} margin={{ left: 12, right: 24 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" />
                    <XAxis dataKey="index" tick={{ fill: "var(--color-text-secondary)", fontSize: 12 }} />
                    <YAxis tick={{ fill: "var(--color-text-secondary)", fontSize: 12 }} />
                    <Tooltip
                      formatter={(v: number, name) => [
                        `${v.toFixed(1)}%`,
                        name === "equity" ? "누적 수익률" : "개별 수익률",
                      ]}
                      labelFormatter={(_, rows) => {
                        const payload = rows?.[0]?.payload as { analyzed_at?: string; ticker?: string } | undefined;
                        return payload ? `${payload.analyzed_at} · ${payload.ticker}` : "";
                      }}
                      contentStyle={{
                        background: "var(--color-bg-surface)",
                        border: "1px solid var(--color-border)",
                      }}
                    />
                    <Line type="monotone" dataKey="equity" stroke="var(--color-accent)" dot={false} strokeWidth={2} />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </div>
          ) : null}

          {opinionData.length > 0 ? (
            <div className="card">
              <h2>의견별 적중률</h2>
              <div style={{ width: "100%", height: 260 }}>
                <ResponsiveContainer>
                  <BarChart data={opinionData} margin={{ left: 12, right: 24 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" />
                    <XAxis dataKey="opinion" tick={{ fill: "var(--color-text-secondary)", fontSize: 12 }} />
                    <YAxis domain={[0, 100]} tick={{ fill: "var(--color-text-secondary)", fontSize: 12 }} />
                    <Tooltip
                      formatter={(v: number, name) => [
                        `${v.toFixed(1)}%`,
                        name === "hit_rate" ? "적중률" : "평균 수익률",
                      ]}
                      contentStyle={{
                        background: "var(--color-bg-surface)",
                        border: "1px solid var(--color-border)",
                      }}
                    />
                    <Bar dataKey="hit_rate" fill="var(--color-accent)" radius={[4, 4, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </div>
          ) : null}

          {summary.records.length > 0 ? (
            <div className="card">
              <h2>평가 이력</h2>
              <div className="watchlist-table-wrap">
                <table className="watchlist-table">
                  <thead>
                    <tr>
                      <th>분석일</th>
                      <th>종목</th>
                      <th>CEO 의견</th>
                      <th>선행 수익률</th>
                      <th>적중</th>
                      <th>누적</th>
                    </tr>
                  </thead>
                  <tbody>
                    {[...summary.records].reverse().map((row) => (
                      <tr key={row.id}>
                        <td className="font-tabular">{row.analyzed_at.slice(0, 10)}</td>
                        <td>{row.ticker}</td>
                        <td>{row.final_opinion}</td>
                        <td className={percentClass(row.forward_return)}>{formatPercent(row.forward_return)}</td>
                        <td>{row.hit ? "적중" : "미적중"}</td>
                        <td className={percentClass(row.equity_curve)}>{formatPercent(row.equity_curve)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          ) : null}
        </>
      ) : null}
    </>
  );
}

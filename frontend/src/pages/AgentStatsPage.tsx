import { useEffect, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { getAgentsStats, getRecentReports } from "@/api/client";
import type { AgentPerformanceSummary, AnalysisHistoryItem } from "@/types/api";

/**
 * 에이전트·CEO 적중률 바 차트 + 최근 이력 테이블
 */
export function AgentStatsPage() {
  const [horizon, setHorizon] = useState<30 | 60 | 90>(30);
  const [summary, setSummary] = useState<AgentPerformanceSummary | null>(null);
  const [history, setHistory] = useState<AnalysisHistoryItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const load = async () => {
    setLoading(true);
    setErr(null);
    try {
      const [s, h] = await Promise.all([getAgentsStats(horizon), getRecentReports(30)]);
      setSummary(s);
      setHistory(h);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "통계 조회 실패");
      setSummary(null);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const chartData =
    summary == null
      ? []
      : [
          {
            name: "CEO",
            rate: summary.ceo.hit_rate != null ? summary.ceo.hit_rate * 100 : 0,
            samples: summary.ceo.samples,
          },
          ...summary.by_agent.map((r) => ({
            name: r.agent_name.slice(0, 12) + (r.agent_name.length > 12 ? "…" : ""),
            rate: r.hit_rate != null ? r.hit_rate * 100 : 0,
            samples: r.samples,
          })),
        ].filter((row) => row.samples > 0);

  return (
    <>
      <h1 style={{ marginTop: 0 }}>에이전트 성적표</h1>
      <div className="card">
        <p className="muted">
          첫 요청 시 저장된 분석 대비 선행 수익률을 채우느라 시간이 걸릴 수 있습니다.
        </p>
        <div className="row" style={{ alignItems: "center" }}>
          <label className="muted">
            평가 거래일
            <select
              className="input"
              style={{ marginLeft: 8 }}
              value={horizon}
              onChange={(e) => setHorizon(Number(e.target.value) as 30 | 60 | 90)}
            >
              <option value={30}>30일</option>
              <option value={60}>60일</option>
              <option value={90}>90일</option>
            </select>
          </label>
          <button type="button" className="btn" disabled={loading} onClick={() => void load()}>
            {loading ? "조회 중…" : "통계 불러오기"}
          </button>
        </div>
        {err ? <p className="error">{err}</p> : null}
        {summary ? (
          <p className="muted">
            평가 레코드 {summary.evaluated_records}건 · horizon {summary.horizon_trading_days}일 ·{" "}
            {summary.timestamp}
          </p>
        ) : null}
      </div>

      {chartData.length > 0 ? (
        <div className="card">
          <h2>방향 적중률 (%)</h2>
          <div style={{ width: "100%", height: 320 }}>
            <ResponsiveContainer>
              <BarChart data={chartData} layout="vertical" margin={{ left: 12, right: 24 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" />
                <XAxis type="number" domain={[0, 100]} tick={{ fill: "var(--color-text-secondary)", fontSize: 12 }} />
                <YAxis
                  type="category"
                  dataKey="name"
                  width={100}
                  tick={{ fill: "var(--color-text-secondary)", fontSize: 11 }}
                />
                <Tooltip
                  formatter={(v: number) => [`${v.toFixed(1)}%`, "적중률"]}
                  contentStyle={{
                    background: "var(--color-bg-surface)",
                    border: "1px solid var(--color-border)",
                  }}
                />
                <Bar dataKey="rate" fill="var(--color-accent)" radius={[0, 4, 4, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      ) : null}

      {history.length > 0 ? (
        <div className="card" style={{ overflowX: "auto" }}>
          <h2>최근 분석 이력</h2>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.85rem" }}>
            <thead>
              <tr style={{ textAlign: "left", borderBottom: "1px solid var(--color-border)" }}>
                <th style={{ padding: "0.5rem" }}>일시</th>
                <th>종목</th>
                <th>CEO</th>
                <th>30d</th>
                <th>60d</th>
                <th>90d</th>
              </tr>
            </thead>
            <tbody>
              {history.map((row) => (
                <tr key={row.id} style={{ borderBottom: "1px solid var(--color-border-subtle)" }}>
                  <td style={{ padding: "0.45rem", whiteSpace: "nowrap" }}>{row.analyzed_at}</td>
                  <td>{row.ticker}</td>
                  <td>{row.final_opinion ?? "—"}</td>
                  <td>{row.return_30d != null ? `${(row.return_30d * 100).toFixed(1)}%` : "—"}</td>
                  <td>{row.return_60d != null ? `${(row.return_60d * 100).toFixed(1)}%` : "—"}</td>
                  <td>{row.return_90d != null ? `${(row.return_90d * 100).toFixed(1)}%` : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
    </>
  );
}

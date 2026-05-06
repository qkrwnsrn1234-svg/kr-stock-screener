import { useCallback, useEffect, useRef, useState } from "react";
import { useParams } from "react-router-dom";
import { analyzeTicker } from "@/api/client";
import { ConfidencePie } from "@/components/ConfidencePie";
import type { CEOReport } from "@/types/api";

function opinionClass(op: string): string {
  if (op.includes("매수")) return "tag tag-buy";
  if (op.includes("매도")) return "tag tag-sell";
  return "tag tag-neutral";
}

/**
 * 단일 종목 분석 + 에이전트 토론(펼침 목록)
 */
export function AnalyzePage() {
  const { ticker: routeTicker } = useParams<{ ticker?: string }>();
  const lastAutoRunTickerRef = useRef<string | null>(null);
  const [ticker, setTicker] = useState(routeTicker ?? "005930");
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [report, setReport] = useState<CEOReport | null>(null);

  const run = useCallback(async (targetTicker?: string) => {
    const rawTicker = targetTicker ?? ticker;
    const code = rawTicker.trim().replace(/\D/g, "").slice(0, 6).padStart(6, "0");
    if (code.length !== 6) {
      setErr("6자리 숫자 종목코드를 입력하세요.");
      return;
    }
    setLoading(true);
    setErr(null);
    setReport(null);
    try {
      const r = await analyzeTicker(code, { persist: true, useStatsWeights: true });
      setReport(r);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "분석 실패");
    } finally {
      setLoading(false);
    }
  }, [ticker]);

  useEffect(() => {
    const code = routeTicker?.trim().replace(/\D/g, "").slice(0, 6).padStart(6, "0");
    if (!code || code.length !== 6 || lastAutoRunTickerRef.current === code) return;
    lastAutoRunTickerRef.current = code;
    setTicker(code);
    void run(code);
  }, [routeTicker, run]);

  return (
    <>
      <h1 style={{ marginTop: 0 }}>종목 분석</h1>
      <div className="card">
        <div className="row" style={{ alignItems: "center" }}>
          <label htmlFor="ticker" className="muted">
            종목코드
          </label>
          <input
            id="ticker"
            className="input"
            value={ticker}
            onChange={(e) => setTicker(e.target.value)}
            placeholder="005930"
            maxLength={10}
          />
          <button type="button" className="btn" disabled={loading} onClick={() => void run()}>
            {loading ? "분석 중…" : "분석 실행"}
          </button>
        </div>
        {err ? <p className="error">{err}</p> : null}
      </div>

      {report ? (
        <>
          <div className="row">
            <div className="card" style={{ flex: "1 1 320px" }}>
              <h2>
                CEO 종합 · {report.ticker}{" "}
                <span className={opinionClass(report.final_opinion)}>{report.final_opinion}</span>
              </h2>
              {report.stats_weights_applied ? (
                <p className="muted">성적표 기반 신뢰도 가중이 적용되었습니다.</p>
              ) : null}
              <ConfidencePie report={report} />
              {report.summary_lines.length > 0 ? (
                <ul style={{ margin: "1rem 0 0", paddingLeft: "1.2rem" }}>
                  {report.summary_lines.map((ln) => (
                    <li key={ln}>{ln}</li>
                  ))}
                </ul>
              ) : null}
              {report.risk_rebuttal ? (
                <p style={{ marginTop: "1rem", color: "var(--color-warning)" }}>
                  <strong>리스크 반론:</strong> {report.risk_rebuttal}
                </p>
              ) : null}
            </div>
          </div>
          <div className="card agent-list">
            <h2>에이전트별 의견</h2>
            {report.agent_reports.map((a) => (
              <details key={a.agent_name + a.timestamp}>
                <summary>
                  {a.agent_name || "에이전트"}{" "}
                  <span className={opinionClass(a.opinion)}>{a.opinion}</span>
                  <span className="muted" style={{ fontWeight: 400, marginLeft: 8 }}>
                    신뢰도 {(a.confidence * 100).toFixed(0)}%
                  </span>
                </summary>
                <p style={{ margin: "0.5rem 0" }}>{a.reasoning}</p>
                {Object.keys(a.signals).length > 0 ? (
                  <pre
                    style={{
                      fontSize: "0.75rem",
                      overflow: "auto",
                      background: "var(--color-bg-page)",
                      padding: "0.5rem",
                      borderRadius: "var(--radius-control)",
                    }}
                  >
                    {JSON.stringify(a.signals, null, 2)}
                  </pre>
                ) : null}
              </details>
            ))}
          </div>
        </>
      ) : null}
    </>
  );
}

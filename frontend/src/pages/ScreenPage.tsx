import { useState } from "react";
import { screenTickers } from "@/api/client";
import { OverheatBadge } from "@/components/OverheatBadge";
import { UndervalueMeter } from "@/components/UndervalueMeter";
import type { ScreeningResult } from "@/types/api";

/**
 * 다종목 스크리닝 (최대 8개 — 백엔드 제한)
 */
export function ScreenPage() {
  const [raw, setRaw] = useState("005930,000660");
  const [useW, setUseW] = useState(false);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [rows, setRows] = useState<ScreeningResult[] | null>(null);

  const run = async () => {
    const tickers = raw
      .split(/[\s,]+/)
      .map((s) => s.replace(/\D/g, "").padStart(6, "0"))
      .filter((s) => s.length === 6);
    const uniq = [...new Set(tickers)];
    if (!uniq.length) {
      setErr("유효한 종목코드를 입력하세요.");
      return;
    }
    if (uniq.length > 8) {
      setErr("한 번에 최대 8개까지 조회할 수 있습니다.");
      return;
    }

    setLoading(true);
    setErr(null);
    setRows(null);
    try {
      const list = await screenTickers(uniq.join(","), useW);
      setRows(list);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "스크리닝 실패");
    } finally {
      setLoading(false);
    }
  };

  return (
    <>
      <h1 style={{ marginTop: 0 }}>스크리닝</h1>
      <div className="card">
        <p className="muted">
          콤마 또는 공백으로 구분 · 최대 8종목. 성적표 가중은 다종목에서 부담이 커질 수 있습니다.
        </p>
        <textarea
          className="input"
          style={{ width: "100%", minHeight: 72, resize: "vertical" }}
          value={raw}
          onChange={(e) => setRaw(e.target.value)}
        />
        <div className="row" style={{ marginTop: "0.75rem", alignItems: "center" }}>
          <label className="muted" style={{ display: "flex", gap: 8, alignItems: "center" }}>
            <input
              type="checkbox"
              checked={useW}
              onChange={(e) => setUseW(e.target.checked)}
            />
            CEO에 성적표 가중 적용
          </label>
          <button type="button" className="btn" disabled={loading} onClick={() => void run()}>
            {loading ? "실행 중…" : "스크리닝 실행"}
          </button>
        </div>
        {err ? <p className="error">{err}</p> : null}
      </div>

      {rows
        ? rows.map((r) => (
            <div key={r.ticker} className="card">
              <h2 style={{ display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
                {r.ticker}
                <OverheatBadge alert={r.overheat_alert ?? undefined} flag={r.overheat_flag} />
              </h2>
              <h3 className="muted" style={{ fontSize: "0.9rem", margin: "0.5rem 0" }}>
                언더밸류에이션
              </h3>
              <UndervalueMeter score={r.undervalue_score} breakdown={r.undervalue_breakdown} />
              {r.overheat_alert?.reasons?.length ? (
                <ul className="muted" style={{ marginTop: "0.75rem" }}>
                  {r.overheat_alert.reasons.map((x) => (
                    <li key={x}>{x}</li>
                  ))}
                </ul>
              ) : null}
              <details style={{ marginTop: "0.75rem" }}>
                <summary>에이전트 요약 ({r.agent_reports.length})</summary>
                <ul>
                  {r.agent_reports.map((a) => (
                    <li key={a.agent_name}>
                      <strong>{a.agent_name}</strong>: {a.opinion} ({(a.confidence * 100).toFixed(0)}
                      %)
                    </li>
                  ))}
                </ul>
              </details>
            </div>
          ))
        : null}
    </>
  );
}

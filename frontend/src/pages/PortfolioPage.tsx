import { useState } from "react";
import { getPortfolioAdvice } from "@/api/client";
import type { PortfolioAdvice } from "@/types/api";

function riskLabel(level: string): string {
  if (level === "high") return "높음";
  if (level === "medium") return "중간";
  if (level === "low") return "낮음";
  return level;
}

/**
 * 보유 비중 문자열로 포트폴리오 조언 조회
 */
export function PortfolioPage() {
  const [holdings, setHoldings] = useState("005930:0.6,000660:0.4");
  const [focus, setFocus] = useState("");
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [adv, setAdv] = useState<PortfolioAdvice | null>(null);

  const run = async () => {
    setLoading(true);
    setErr(null);
    setAdv(null);
    try {
      const r = await getPortfolioAdvice(
        holdings.replace(/\s/g, ""),
        focus.trim() ? focus.trim().replace(/\D/g, "").padStart(6, "0") : undefined
      );
      setAdv(r);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "조회 실패");
    } finally {
      setLoading(false);
    }
  };

  return (
    <>
      <h1 style={{ marginTop: 0 }}>포트폴리오 조언</h1>
      <div className="card">
        <p className="muted">
          형식: <code>종목코드:비중</code> 콤마 구분 (예: 005930:0.6,000660:0.4). 합이 1에 가까울수록
          해석이 분명합니다.
        </p>
        <label htmlFor="holdings" className="muted" style={{ display: "block", marginBottom: 6 }}>
          보유 비중
        </label>
        <textarea
          id="holdings"
          className="input"
          style={{ width: "100%", minHeight: 64, resize: "vertical" }}
          value={holdings}
          onChange={(e) => setHoldings(e.target.value)}
        />
        <label htmlFor="focus" className="muted" style={{ display: "block", marginTop: 12 }}>
          조언 기준 종목(선택, 6자리)
        </label>
        <input
          id="focus"
          className="input"
          value={focus}
          onChange={(e) => setFocus(e.target.value)}
          placeholder="비우면 비중 최대 종목"
        />
        <button
          type="button"
          className="btn"
          style={{ marginTop: "0.75rem" }}
          disabled={loading}
          onClick={() => void run()}
        >
          {loading ? "조회 중…" : "조언 받기"}
        </button>
        {err ? <p className="error">{err}</p> : null}
      </div>

      {adv ? (
        <div className="card">
          <h2>
            리스크 수준: {riskLabel(adv.risk_level)} <span className="muted">({adv.risk_level})</span>
          </h2>
          <p style={{ lineHeight: 1.6 }}>{adv.advice}</p>
          <h3 className="muted" style={{ fontSize: "0.9rem" }}>
            제안 비중
          </h3>
          <ul>
            {Object.entries(adv.weight_suggestion)
              .sort((a, b) => b[1] - a[1])
              .map(([code, w]) => (
                <li key={code}>
                  <strong>{code}</strong>: {(w * 100).toFixed(1)}%
                </li>
              ))}
          </ul>
          <p className="muted" style={{ marginBottom: 0 }}>
            {adv.timestamp}
          </p>
        </div>
      ) : null}
    </>
  );
}

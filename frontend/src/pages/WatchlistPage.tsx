import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  addWatchlistItem,
  getWatchlistSummary,
  removeWatchlistItem,
  screenTickers,
} from "@/api/client";
import { OverheatBadge } from "@/components/OverheatBadge";
import type { ScreeningResult, WatchlistSummaryItem } from "@/types/api";

const MAX_SCREENING_TICKERS = 8;

function formatPrice(value?: number | null): string {
  if (value === null || value === undefined) return "-";
  return `${Math.round(value).toLocaleString("ko-KR")}원`;
}

function formatChangePct(value?: number | null): { text: string; className: string } {
  if (value === null || value === undefined) return { text: "-", className: "muted" };
  const pct = value * 100;
  return {
    text: `${pct >= 0 ? "+" : ""}${pct.toFixed(2)}%`,
    className: pct >= 0 ? "text-positive font-tabular" : "text-negative font-tabular",
  };
}

/**
 * 백엔드 SQLite 기반 관심 종목 관리 화면
 */
export function WatchlistPage() {
  const navigate = useNavigate();
  const [items, setItems] = useState<WatchlistSummaryItem[]>([]);
  const [screeningByTicker, setScreeningByTicker] = useState<Record<string, ScreeningResult>>({});
  const [ticker, setTicker] = useState("");
  const [memo, setMemo] = useState("");
  const [loading, setLoading] = useState(false);
  const [screeningLoading, setScreeningLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const tickers = useMemo(() => items.map((item) => item.ticker), [items]);
  const canScreenAll = tickers.length > 0 && tickers.length <= MAX_SCREENING_TICKERS;

  const refresh = useCallback(async () => {
    setLoading(true);
    setErr(null);
    try {
      const list = await getWatchlistSummary();
      setItems(list);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "관심 종목 조회 실패");
    } finally {
      setLoading(false);
    }
  }, []);

  const refreshScreening = useCallback(async (targetTickers = tickers) => {
    const uniq = [...new Set(targetTickers)].slice(0, MAX_SCREENING_TICKERS);
    if (!uniq.length) return;
    setScreeningLoading(true);
    setErr(null);
    try {
      const rows = await screenTickers(uniq.join(","), false);
      const next = Object.fromEntries(rows.map((row) => [row.ticker, row]));
      setScreeningByTicker((prev) => ({ ...prev, ...next }));
    } catch (e) {
      setErr(e instanceof Error ? e.message : "관심 종목 스크리닝 실패");
    } finally {
      setScreeningLoading(false);
    }
  }, [tickers]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  useEffect(() => {
    if (canScreenAll) {
      void refreshScreening(tickers);
    }
  }, [canScreenAll, refreshScreening, tickers]);

  const addItem = async () => {
    const code = ticker.trim().replace(/\D/g, "").slice(0, 6).padStart(6, "0");
    if (code.length !== 6) {
      setErr("6자리 숫자 종목코드를 입력하세요.");
      return;
    }
    setSaving(true);
    setErr(null);
    try {
      await addWatchlistItem({ ticker: code, memo: memo.trim() });
      setTicker("");
      setMemo("");
      await refresh();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "관심 종목 저장 실패");
    } finally {
      setSaving(false);
    }
  };

  const removeItem = async (code: string) => {
    setErr(null);
    try {
      await removeWatchlistItem(code);
      setItems((prev) => prev.filter((item) => item.ticker !== code));
      setScreeningByTicker((prev) => {
        const next = { ...prev };
        delete next[code];
        return next;
      });
    } catch (e) {
      setErr(e instanceof Error ? e.message : "관심 종목 삭제 실패");
    }
  };

  return (
    <>
      <h1 style={{ marginTop: 0 }}>관심 종목</h1>
      <div className="card">
        <p className="muted">
          관심 종목은 백엔드 SQLite에 저장됩니다. 스크리닝 지표는 최대 8종목까지 한 번에 갱신합니다.
        </p>
        <div className="row" style={{ alignItems: "center" }}>
          <input
            className="input"
            value={ticker}
            onChange={(e) => setTicker(e.target.value)}
            placeholder="종목코드 005930"
            maxLength={10}
            aria-label="관심 종목 코드"
          />
          <input
            className="input"
            value={memo}
            onChange={(e) => setMemo(e.target.value)}
            placeholder="메모(선택)"
            maxLength={200}
            aria-label="관심 종목 메모"
          />
          <button type="button" className="btn" disabled={saving} onClick={() => void addItem()}>
            {saving ? "저장 중..." : "관심 종목 추가"}
          </button>
          <button type="button" className="btn btn-secondary" disabled={loading} onClick={() => void refresh()}>
            목록 새로고침
          </button>
          <button
            type="button"
            className="btn btn-secondary"
            disabled={!canScreenAll || screeningLoading}
            onClick={() => void refreshScreening()}
          >
            {screeningLoading ? "지표 갱신 중..." : "스크리닝 지표 갱신"}
          </button>
        </div>
        {tickers.length > MAX_SCREENING_TICKERS ? (
          <p className="muted" style={{ color: "var(--color-warning)" }}>
            관심 종목이 {MAX_SCREENING_TICKERS}개를 초과해 스크리닝 지표 자동 갱신은 건너뜁니다.
          </p>
        ) : null}
        {err ? <p className="error">{err}</p> : null}
      </div>

      <div className="card">
        <h2>목록</h2>
        {loading ? <div className="skeleton" style={{ height: 96 }} /> : null}
        {!loading && items.length === 0 ? <p className="muted">아직 저장된 관심 종목이 없습니다.</p> : null}
        {!loading && items.length > 0 ? (
          <div className="watchlist-table-wrap">
            <table className="watchlist-table">
              <thead>
                <tr>
                  <th>종목</th>
                  <th>현재가</th>
                  <th>등락률</th>
                  <th>언더밸류</th>
                  <th>과열</th>
                  <th>메모</th>
                  <th>액션</th>
                </tr>
              </thead>
              <tbody>
                {items.map((item) => {
                  const screening = screeningByTicker[item.ticker];
                  const change = formatChangePct(item.change_pct);
                  return (
                    <tr key={item.ticker}>
                      <td>
                        <strong>{item.name}</strong>
                        <div className="muted">
                          {item.ticker} · {[item.market, item.sector].filter(Boolean).join(" · ")}
                        </div>
                      </td>
                      <td className="font-tabular">{formatPrice(item.current_price)}</td>
                      <td className={change.className}>{change.text}</td>
                      <td className="font-tabular">
                        {screening ? `${screening.undervalue_score.toFixed(1)} / 100` : "-"}
                      </td>
                      <td>
                        {screening ? (
                          <OverheatBadge
                            alert={screening.overheat_alert ?? undefined}
                            flag={screening.overheat_flag}
                          />
                        ) : (
                          <span className="muted">-</span>
                        )}
                      </td>
                      <td className="muted">{item.memo || "-"}</td>
                      <td>
                        <div className="row" style={{ gap: "0.5rem" }}>
                          <button
                            type="button"
                            className="btn btn-secondary"
                            onClick={() => navigate(`/analyze/${item.ticker}`)}
                          >
                            빠른 분석
                          </button>
                          <button
                            type="button"
                            className="btn btn-secondary"
                            onClick={() => void removeItem(item.ticker)}
                          >
                            삭제
                          </button>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        ) : null}
      </div>
    </>
  );
}

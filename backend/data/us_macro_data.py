"""
미국 달러·단기금리 프록시 조회(별도 API 키 불필요).

`yfinance`로 DXY·3개월 국채 수익률(^IRX) 스냅샷을 캐시합니다. 네트워크 실패 시 ``ok: false`` 를 반환합니다.
"""

from __future__ import annotations

import logging
from typing import Any

import pandas as pd

from backend.data.cache import DEFAULT_TTL_SECONDS, build_cache_key, load_cached

logger = logging.getLogger(__name__)

# yfinance 심볼: 달러 인덱스, 미국 3개월 국채 수익률(%)
TICKER_DXY = "DX-Y.NYB"
TICKER_IRX = "^IRX"


def _snapshot_fetch() -> dict[str, Any]:
    """yfinance에서 최근 종가·대략 1개월 변화를 읽습니다."""
    try:
        import yfinance as yf
    except ImportError as exc:
        logger.warning("yfinance 미설치 — US 거시 프록시 생략: %s", exc)
        return {"ok": False, "error": "yfinance_import"}

    out: dict[str, Any] = {
        "ok": True,
        "tickers": {"dxy": TICKER_DXY, "irx": TICKER_IRX},
    }

    try:
        dxy = yf.Ticker(TICKER_DXY)
        irx = yf.Ticker(TICKER_IRX)
        h_d = dxy.history(period="3mo", auto_adjust=False)
        h_i = irx.history(period="3mo", auto_adjust=False)
    except Exception as exc:
        logger.info("yfinance history 실패: %s", exc)
        return {"ok": False, "error": "history"}

    def _dxy_metrics(hist: pd.DataFrame) -> tuple[float | None, float | None]:
        if hist is None or hist.empty or "Close" not in hist.columns:
            return None, None
        close = pd.to_numeric(hist["Close"], errors="coerce").dropna()
        if len(close) < 2:
            return (float(close.iloc[-1]) if len(close) else None), None
        last = float(close.iloc[-1])
        prev = float(close.iloc[-22]) if len(close) >= 22 else float(close.iloc[0])
        ratio = (last - prev) / prev if prev else None
        return last, ratio

    def _irx_metrics(hist: pd.DataFrame) -> tuple[float | None, float | None]:
        if hist is None or hist.empty or "Close" not in hist.columns:
            return None, None
        close = pd.to_numeric(hist["Close"], errors="coerce").dropna()
        if len(close) < 2:
            return (float(close.iloc[-1]) if len(close) else None), None
        last = float(close.iloc[-1])
        prev = float(close.iloc[-22]) if len(close) >= 22 else float(close.iloc[0])
        return last, last - prev

    dxy_lvl, dxy_ch = _dxy_metrics(h_d)
    irx_lvl, irx_pp = _irx_metrics(h_i)

    out["dxy_last"] = dxy_lvl
    out["dxy_change_approx_1m_ratio"] = dxy_ch
    out["us_tbill_3mo_yield_last_pct"] = irx_lvl
    out["us_tbill_3mo_yield_change_approx_1m_pp"] = irx_pp

    if dxy_lvl is None and irx_lvl is None:
        out["ok"] = False
        out["error"] = "empty_series"

    return out


def fetch_us_dollar_rate_snapshot(*, ttl_seconds: int = DEFAULT_TTL_SECONDS) -> dict[str, Any]:
    """
    DXY·^IRX 기반 미국 쪽 거시 프록시를 반환합니다.

    Returns:
        수익률·환율 지표와 ``ok`` 성공 여부.
    """
    key = build_cache_key("us_macro", "v1")
    return load_cached("us_macro", key, _snapshot_fetch, ttl_seconds=ttl_seconds)

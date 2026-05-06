"""
관심 종목 화면에 필요한 가벼운 시세·종목명 요약을 생성합니다.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Any

import pandas as pd

from backend.data.finance_data import fetch_ohlcv, list_krx_symbols

logger = logging.getLogger(__name__)

LOOKBACK_DAYS_FOR_QUOTE = 14


def _clean_text(value: Any) -> str:
    """표시용 문자열을 안전하게 정리합니다."""
    if value is None or pd.isna(value):
        return ""
    return str(value).strip()


def _listing_map() -> dict[str, dict[str, str | None]]:
    """상장 목록을 종목코드 기준 메타 정보 맵으로 변환합니다."""
    try:
        listing = list_krx_symbols(None)
    except Exception as exc:
        logger.warning("관심 종목 메타 조회 실패: %s", exc)
        return {}

    if listing is None or listing.empty or "Code" not in listing.columns:
        return {}

    out: dict[str, dict[str, str | None]] = {}
    for _, row in listing.iterrows():
        ticker = _clean_text(row.get("Code")).zfill(6)
        if not ticker.isdigit():
            continue
        out[ticker] = {
            "name": _clean_text(row.get("Name")) or ticker,
            "market": _clean_text(row.get("Market")) or None,
            "sector": _clean_text(row.get("Dept")) or None,
        }
    return out


def _latest_quote(ticker: str) -> tuple[float | None, float | None]:
    """최근 종가와 직전 종가 대비 등락률을 계산합니다."""
    end = date.today()
    start = end - timedelta(days=LOOKBACK_DAYS_FOR_QUOTE)
    try:
        df = fetch_ohlcv(ticker, start, end)
    except Exception as exc:
        logger.warning("관심 종목 최근 시세 조회 실패 ticker=%s: %s", ticker, exc)
        return None, None

    if df is None or df.empty or "Close" not in df.columns:
        return None, None

    closes = pd.to_numeric(df["Close"], errors="coerce").dropna()
    if closes.empty:
        return None, None

    current = float(closes.iloc[-1])
    if len(closes) < 2:
        return current, None

    prev = float(closes.iloc[-2])
    if prev == 0:
        return current, None
    return current, (current - prev) / prev


def build_watchlist_summary(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    관심 종목 DB 행에 종목명·시장·최근가·등락률을 붙입니다.

    Args:
        rows: ``backend.storage.watchlist.list_tickers``가 반환한 행 목록.

    Returns:
        화면 표시용 관심 종목 요약 목록.
    """
    meta_by_ticker = _listing_map()
    items: list[dict[str, Any]] = []

    for row in rows:
        ticker = str(row.get("ticker", "")).strip().zfill(6)
        meta = meta_by_ticker.get(ticker, {})
        current_price, change_pct = _latest_quote(ticker)
        items.append(
            {
                "id": int(row["id"]),
                "ticker": ticker,
                "added_at": str(row.get("added_at", "")),
                "memo": str(row.get("memo", "")),
                "name": meta.get("name") or ticker,
                "market": meta.get("market"),
                "sector": meta.get("sector"),
                "current_price": current_price,
                "change_pct": change_pct,
            }
        )

    return items

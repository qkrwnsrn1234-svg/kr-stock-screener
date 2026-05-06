"""
FinanceDataReader 기반 주가·ETF OHLCV 조회 모듈입니다.
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any

import FinanceDataReader as fdr
import pandas as pd

from backend.data.cache import DEFAULT_TTL_SECONDS, build_cache_key, load_cached

logger = logging.getLogger(__name__)


def _normalize_date(value: date | datetime | str | None) -> str | None:
    """날짜를 ``YYYY-MM-DD`` 문자열로 통일합니다."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def fetch_ohlcv(
    ticker: str,
    start: date | datetime | str,
    end: date | datetime | str | None = None,
    *,
    exchange: str | None = None,
    data_source: str | None = None,
    ttl_seconds: int = DEFAULT_TTL_SECONDS,
) -> pd.DataFrame:
    """
    FinanceDataReader로 일별 OHLCV 시계열을 조회합니다 (코스피·코스닥·ETF 등).

    Args:
        ticker: 종목코드 6자리 등 FinanceDataReader가 허용하는 심볼.
        start: 시작일.
        end: 종료일(포함). ``None``이면 데이터 소스 기본 동작에 따름.
        exchange: 거래소 지정이 필요할 때만 전달.
        data_source: FinanceDataReader ``data_source`` 인자 (예: ``'naver'``).
        ttl_seconds: 디스크 캐시 TTL.

    Returns:
        인덱스가 날짜형인 OHLCV ``DataFrame``.

    Raises:
        RuntimeError: 데이터가 비어 있거나 조회에 실패한 경우.
    """
    start_s = _normalize_date(start)
    end_s = _normalize_date(end)

    def _fetch() -> pd.DataFrame:
        kwargs: dict[str, Any] = {}
        if exchange is not None:
            kwargs["exchange"] = exchange
        if data_source is not None:
            kwargs["data_source"] = data_source
        try:
            df = fdr.DataReader(ticker, start_s, end_s, **kwargs)
        except Exception as exc:
            logger.exception("FinanceDataReader 조회 실패 ticker=%s", ticker)
            raise RuntimeError(f"FinanceDataReader 조회 실패: {ticker}") from exc

        if df is None or df.empty:
            raise RuntimeError(f"FinanceDataReader 결과가 비어 있습니다: {ticker}")
        return df

    cache_key = build_cache_key(
        "ohlcv", ticker, start_s or "", end_s or "", exchange or "", data_source or ""
    )
    return load_cached("fdr", cache_key, _fetch, ttl_seconds=ttl_seconds)


def list_krx_symbols(market: str | None = None) -> pd.DataFrame:
    """
    KRX 상장 종목 메타 목록을 조회합니다.

    Args:
        market: ``'KOSPI'``, ``'KOSDAQ'`` 등 필터 (FinanceDataReader 규약 따름).

    Returns:
        상장 종목 정보 테이블.

    Raises:
        RuntimeError: 조회 결과가 비어 있는 경우.
    """

    def _fetch() -> pd.DataFrame:
        try:
            df = fdr.StockListing(market) if market else fdr.StockListing("KRX")
        except Exception as exc:
            logger.exception("StockListing 조회 실패 market=%s", market)
            raise RuntimeError("StockListing 조회 실패") from exc
        if df is None or df.empty:
            raise RuntimeError("StockListing 결과가 비어 있습니다.")
        return df

    cache_key = build_cache_key("listing", market or "KRX")
    # 종목 리스트는 자주 바뀌지 않음 — TTL을 길게
    return load_cached("fdr_listing", cache_key, _fetch, ttl_seconds=6 * DEFAULT_TTL_SECONDS)

"""
pykrx 기반 KRX 시세·시총·투자주체별 순매수 데이터 조회 모듈입니다.

일부 기능은 KRX 정책에 따라 ``KRX_ID`` / ``KRX_PW`` 환경 변수 설정이 필요할 수 있습니다.
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Literal

import pandas as pd

from backend.data.cache import DEFAULT_TTL_SECONDS, build_cache_key, load_cached
from backend.utils.pykrx_silent import stock

logger = logging.getLogger(__name__)

MarketLiteral = Literal["KOSPI", "KOSDAQ", "KONEX", "ALL"]


def _fmt_yyyymmdd(value: date | datetime | str) -> str:
    """날짜를 pykrx 형식 ``YYYYMMDD`` 문자열로 변환합니다."""
    if isinstance(value, datetime):
        value = value.date()
    if isinstance(value, date):
        return value.strftime("%Y%m%d")
    s = str(value).replace("-", "")
    if len(s) == 8 and s.isdigit():
        return s
    raise ValueError(f"지원하지 않는 날짜 형식입니다: {value}")


def fetch_daily_ohlcv(
    ticker: str,
    start: date | datetime | str,
    end: date | datetime | str,
    *,
    freq: str = "d",
    adjusted: bool = True,
    ttl_seconds: int = DEFAULT_TTL_SECONDS,
) -> pd.DataFrame:
    """
    pykrx로 특정 종목의 기간별 OHLCV를 조회합니다.

    Args:
        ticker: 6자리 종목코드.
        start: 시작일.
        end: 종료일.
        freq: 주기 (기본 일봉 ``d``).
        adjusted: 수정주가 반영 여부.
        ttl_seconds: 디스크 캐시 TTL.

    Returns:
        일자 인덱스 OHLCV ``DataFrame``.

    Raises:
        RuntimeError: 결과가 비어 있는 경우.
    """
    start_s = _fmt_yyyymmdd(start)
    end_s = _fmt_yyyymmdd(end)

    def _fetch() -> pd.DataFrame:
        try:
            df = stock.get_market_ohlcv_by_date(start_s, end_s, ticker, freq=freq, adjusted=adjusted)
        except Exception as exc:
            logger.exception("pykrx OHLCV 조회 실패 ticker=%s", ticker)
            raise RuntimeError(f"pykrx OHLCV 조회 실패: {ticker}") from exc
        if df is None or df.empty:
            raise RuntimeError(f"pykrx OHLCV 결과가 비어 있습니다: {ticker}")
        return df

    key = build_cache_key("ohlcv", ticker, start_s, end_s, freq, str(adjusted))
    return load_cached("pykrx_ohlcv", key, _fetch, ttl_seconds=ttl_seconds)


def fetch_market_cap_on_date(
    query_date: date | datetime | str,
    *,
    market: MarketLiteral = "ALL",
    ttl_seconds: int = DEFAULT_TTL_SECONDS,
) -> pd.DataFrame:
    """
    특정 거래일 기준 전 종목 시가총액 스냅샷을 조회합니다.

    Args:
        query_date: 조회 일자 (영업일 기준).
        market: 시장 구분.
        ttl_seconds: 디스크 캐시 TTL.

    Returns:
        시총 관련 컬럼을 포함한 ``DataFrame``.

    Raises:
        RuntimeError: 결과가 비어 있는 경우.
    """
    d = _fmt_yyyymmdd(query_date)

    def _fetch() -> pd.DataFrame:
        try:
            df = stock.get_market_cap_by_ticker(d, market=market)
        except Exception as exc:
            logger.exception("pykrx 시총 조회 실패 date=%s market=%s", d, market)
            raise RuntimeError("pykrx 시총 조회 실패") from exc
        if df is None or df.empty:
            raise RuntimeError(f"pykrx 시총 결과가 비어 있습니다: {d}")
        return df

    key = build_cache_key("mcap", d, market)
    return load_cached("pykrx_mcap", key, _fetch, ttl_seconds=ttl_seconds)


def fetch_net_purchases_by_ticker(
    start: date | datetime | str,
    end: date | datetime | str,
    *,
    market: MarketLiteral = "KOSPI",
    investor: str = "외국인",
    ttl_seconds: int = DEFAULT_TTL_SECONDS,
) -> pd.DataFrame:
    """
    기간·시장·투자주체 기준 종목별 순매수(매수-매도) 집계를 조회합니다.

    Args:
        start: 시작일.
        end: 종료일.
        market: 시장 구분.
        investor: 투자주체 구분 (예: ``외국인``, ``기관합계``, ``개인``).
        ttl_seconds: 디스크 캐시 TTL.

    Returns:
        종목별 순매수 관련 ``DataFrame``.

    Raises:
        RuntimeError: 결과가 비어 있는 경우.
    """
    start_s = _fmt_yyyymmdd(start)
    end_s = _fmt_yyyymmdd(end)

    def _fetch() -> pd.DataFrame:
        try:
            df = stock.get_market_net_purchases_of_equities_by_ticker(
                start_s, end_s, market=market, investor=str(investor)
            )
        except Exception as exc:
            logger.exception(
                "pykrx 순매수 조회 실패 market=%s investor=%s", market, investor
            )
            raise RuntimeError("pykrx 순매수 조회 실패") from exc
        if df is None or df.empty:
            raise RuntimeError("pykrx 순매수 결과가 비어 있습니다.")
        return df

    key = build_cache_key("netbuy", start_s, end_s, market, str(investor))
    return load_cached("pykrx_netbuy", key, _fetch, ttl_seconds=ttl_seconds)

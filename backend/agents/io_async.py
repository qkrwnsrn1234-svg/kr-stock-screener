"""
블로킹 데이터 조회를 asyncio 스레드로 감싼 헬퍼입니다.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import date, timedelta

import pandas as pd

from backend.data import finance_data

logger = logging.getLogger(__name__)


async def fetch_equity_ohlcv_async(ticker: str, lookback_days: int = 420) -> pd.DataFrame:
    """
    FinanceDataReader 기반 일별 OHLCV를 비동기로 조회합니다.

    Args:
        ticker: 종목코드.
        lookback_days: 과거 거래일 근사 범위(달력일).

    Returns:
        OHLCV ``DataFrame``.
    """
    end = date.today()
    start = end - timedelta(days=lookback_days)
    return await asyncio.to_thread(finance_data.fetch_ohlcv, ticker, start, end)


async def fetch_index_ohlcv_async(symbol: str = "KS11", lookback_days: int = 420) -> pd.DataFrame:
    """
    벤치마크 지수(KOSPI 등) OHLCV를 조회합니다.

    Args:
        symbol: FinanceDataReader 심볼(기본 ``KS11``).
        lookback_days: 과거 달력일 범위.

    Returns:
        지수 OHLCV ``DataFrame``.
    """
    end = date.today()
    start = end - timedelta(days=lookback_days)
    return await asyncio.to_thread(finance_data.fetch_ohlcv, symbol, start, end)

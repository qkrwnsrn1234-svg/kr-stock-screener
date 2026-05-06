"""
주가 시계열 기반 기술적 지표 계산 유틸입니다.

외부 TA 라이브러리 없이 pandas만 사용합니다.
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


def _ensure_close_volume(df: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    """OHLCV 프레임에서 종가·거래량 시계열을 추출합니다."""
    if df.empty:
        raise ValueError("가격 데이터가 비어 있습니다.")
    close = df["Close"] if "Close" in df.columns else df["close"]
    vol_col = "Volume" if "Volume" in df.columns else "volume"
    volume = df[vol_col] if vol_col in df.columns else pd.Series(np.nan, index=df.index)
    return close.astype(float), volume.astype(float)


def rsi(close: pd.Series, period: int = 14) -> float | None:
    """
    Wilder RSI의 최신값을 계산합니다.

    Args:
        close: 종가 시계열(오름차순 인덱스).
        period: 기간(기본 14).

    Returns:
        RSI 값 또는 데이터 부족 시 ``None``.
    """
    if len(close) < period + 1:
        return None
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = (-delta).clip(lower=0.0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi_series = 100 - (100 / (1 + rs))
    last = float(rsi_series.iloc[-1])
    if np.isnan(last):
        return None
    return last


def macd_snapshot(close: pd.Series) -> dict[str, Any]:
    """
    MACD·시그널·히스토그램 최신 스냅샷을 반환합니다.

    Args:
        close: 종가 시계열.

    Returns:
        ``macd``, ``signal``, ``histogram``, ``bullish_cross_recent`` 키를 가진 dict.
    """
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    macd_line = ema12 - ema26
    signal_line = macd_line.ewm(span=9, adjust=False).mean()
    hist = macd_line - signal_line
    out = {
        "macd": float(macd_line.iloc[-1]),
        "signal": float(signal_line.iloc[-1]),
        "histogram": float(hist.iloc[-1]),
        "bullish_cross_recent": False,
    }
    if len(hist) >= 2:
        prev_d = float(macd_line.iloc[-2] - signal_line.iloc[-2])
        cur_d = float(macd_line.iloc[-1] - signal_line.iloc[-1])
        out["bullish_cross_recent"] = prev_d <= 0 < cur_d
    return out


def moving_averages(close: pd.Series, windows: tuple[int, ...] = (20, 60, 120, 200)) -> dict[str, float]:
    """지정 기간 단순이동평균 최신값들을 반환합니다."""
    result: dict[str, float] = {}
    for w in windows:
        if len(close) >= w:
            result[f"sma_{w}"] = float(close.rolling(w).mean().iloc[-1])
    return result


def golden_death_cross_flags(close: pd.Series, short: int = 50, long: int = 200) -> dict[str, Any]:
    """
    단기/장기 SMA 교차 여부를 최근 5거래일 내에서 탐지합니다.

    데이터가 짧으면 단기·장기 윈도우를 자동으로 축소합니다.
    """
    n = len(close)
    long_w = min(long, max(20, n // 2))
    short_w = min(short, max(5, long_w // 2))
    if n < long_w + 2:
        return {"golden_cross_recent": False, "death_cross_recent": False, "short_window": short_w, "long_window": long_w}
    sma_s = close.rolling(short_w).mean()
    sma_l = close.rolling(long_w).mean()
    tail_s = sma_s.iloc[-6:]
    tail_l = sma_l.iloc[-6:]
    golden = False
    death = False
    for i in range(1, len(tail_s)):
        prev_d = float(tail_s.iloc[i - 1] - tail_l.iloc[i - 1])
        cur_d = float(tail_s.iloc[i] - tail_l.iloc[i])
        if prev_d <= 0 < cur_d:
            golden = True
        if prev_d >= 0 > cur_d:
            death = True
    return {
        "golden_cross_recent": golden,
        "death_cross_recent": death,
        "short_window": short_w,
        "long_window": long_w,
    }


def bollinger_band_pctb(close: pd.Series, window: int = 20, num_std: float = 2.0) -> dict[str, float] | None:
    """
    볼린저 밴드 내 종가 위치(%B)와 밴드폭 관련 값을 반환합니다.

    Returns:
        ``pct_b``, ``upper``, ``middle``, ``lower`` 또는 데이터 부족 시 ``None``.
    """
    if len(close) < window:
        return None
    mid = close.rolling(window).mean()
    std = close.rolling(window).std(ddof=0)
    upper = mid + num_std * std
    lower = mid - num_std * std
    last_close = float(close.iloc[-1])
    up = float(upper.iloc[-1])
    lo = float(lower.iloc[-1])
    mid_v = float(mid.iloc[-1])
    denom = up - lo
    pct_b = (last_close - lo) / denom if denom != 0 else 0.5
    return {"pct_b": float(pct_b), "upper": up, "middle": mid_v, "lower": lo}


def obv_last(close: pd.Series, volume: pd.Series) -> float | None:
    """OBV 최종값을 계산합니다."""
    if volume.isna().all():
        return None
    direction = np.sign(close.diff().fillna(0.0))
    obv = (direction * volume.fillna(0.0)).cumsum()
    return float(obv.iloc[-1])


def total_return(close: pd.Series, days: int) -> float | None:
    """최근 ``days`` 거래일 총수익률을 반환합니다."""
    if len(close) <= days:
        return None
    start = float(close.iloc[-days - 1])
    end = float(close.iloc[-1])
    if start == 0:
        return None
    return (end - start) / start


def relative_strength_vs_benchmark(stock_close: pd.Series, bench_close: pd.Series, days: int = 60) -> float | None:
    """
    벤치마크 대비 상대강도(주식수익률/벤치수익률 - 1) 근사치를 계산합니다.

    공통 거래일로 정렬합니다.
    """
    aligned = pd.concat([stock_close.rename("s"), bench_close.rename("b")], axis=1).dropna()
    if len(aligned) <= days:
        return None
    sub = aligned.iloc[-days - 1 :]
    rs_stock = total_return(sub["s"], days)
    rs_bench = total_return(sub["b"], days)
    if rs_stock is None or rs_bench is None or rs_bench == 0:
        return None
    return rs_stock / rs_bench - 1.0


def max_drawdown(close: pd.Series) -> float | None:
    """전 구간 최대낙폭(MDD)을 0~1 사이 비율로 반환합니다 (양수 값)."""
    if close.empty:
        return None
    cummax = close.cummax()
    dd = close / cummax - 1.0
    return float(dd.min())


def realized_volatility(close: pd.Series, window: int = 60, annualize: int = 252) -> float | None:
    """
    로그수익률 기준 변동성을 연율화하여 반환합니다.
    """
    if len(close) < window + 1:
        return None
    lr = np.log(close / close.shift(1)).dropna()
    seg = lr.iloc[-window:]
    if seg.empty:
        return None
    daily_vol = float(seg.std(ddof=0))
    return daily_vol * np.sqrt(annualize)

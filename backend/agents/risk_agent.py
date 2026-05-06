"""
리스크·하방 시나리오·변동성 중심 에이전트입니다.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import date, timedelta

import numpy as np
import pandas as pd
from pykrx import stock

from . import technical_indicators as ti
from backend.agents.base_agent import BaseAgent
from backend.agents.io_async import fetch_equity_ohlcv_async, fetch_index_ohlcv_async
from backend.agents.models import AgentResponse

logger = logging.getLogger(__name__)


def _beta_vs_benchmark(stock_close: pd.Series, bench_close: pd.Series, window: int = 120) -> float | None:
    """단순 회귀 기반 베타 근사값을 계산합니다."""
    aligned = pd.concat([stock_close.rename("s"), bench_close.rename("b")], axis=1).dropna()
    if len(aligned) < window + 2:
        return None
    sub = aligned.iloc[-window:]
    rs = np.log(sub["s"]).diff().dropna()
    rb = np.log(sub["b"]).diff().dropna()
    common = rs.align(rb, join="inner")
    x = common[0].to_numpy()
    y = common[1].to_numpy()
    if len(x) < 10:
        return None
    cov = np.cov(x, y, ddof=0)[0, 1]
    var = np.var(y)
    if var == 0:
        return None
    return float(cov / var)


async def _shorting_snapshot(ticker: str) -> dict[str, object]:
    """최근 거래일 근처 공매도 현황 스냅샷을 조회합니다."""
    for back in range(1, 10):
        d = date.today() - timedelta(days=back)
        if d.weekday() >= 5:
            continue
        ds = d.strftime("%Y%m%d")
        try:
            df = await asyncio.to_thread(stock.get_shorting_status_by_date, ds, ds, ticker)
        except Exception as exc:
            logger.debug("공매도 조회 예외 무시: %s %s", ds, exc)
            continue
        if df is None or df.empty:
            continue
        return {"basis_date": ds, "rows": df.tail(3).to_dict(orient="records")}
    return {}


class RiskAgent(BaseAgent):
    """리스크 매니저 에이전트."""

    def __init__(self, agent_name: str | None = "리스크") -> None:
        super().__init__(agent_name=agent_name)

    async def analyze(self, ticker: str) -> AgentResponse:
        """가격 기반 리스크 지표와 공매도 스냅샷을 종합합니다."""
        code = self.validate_ticker(ticker)

        # 종목 OHLCV + 코스피 지수 OHLCV를 동시에 조회합니다
        df_s, df_b = await asyncio.gather(
            fetch_equity_ohlcv_async(code),
            fetch_index_ohlcv_async("KS11"),
        )
        close_s, _vol = ti._ensure_close_volume(df_s)
        bench_close = df_b["Close"] if "Close" in df_b.columns else df_b["close"]

        close_s.index = pd.to_datetime(close_s.index).normalize()
        bench_close.index = pd.to_datetime(bench_close.index).normalize()

        vol_ann = ti.realized_volatility(close_s, window=60)
        mdd = ti.max_drawdown(close_s)

        window = min(252, len(close_s))
        recent = close_s.iloc[-window:]
        hi = float(recent.max())
        lo = float(recent.min())
        last = float(close_s.iloc[-1])
        rng_pct = (last - lo) / (hi - lo) if hi != lo else 0.5

        beta = _beta_vs_benchmark(close_s, bench_close, window=120)

        short_info = await _shorting_snapshot(code)

        signals: dict[str, object] = {
            "volatility_ann_60d": vol_ann,
            "max_drawdown_frac": mdd,
            "range_position_52w_proxy": rng_pct,
            "beta_vs_kospi_approx": beta,
            "shorting": short_info,
        }

        score = 0.0
        notes: list[str] = []

        if vol_ann is not None:
            notes.append(f"연율화 변동성 약 {vol_ann*100:.1f}%")
            if vol_ann > 0.35:
                score -= 18
            elif vol_ann > 0.28:
                score -= 10

        if mdd is not None:
            notes.append(f"전 구간 최대낙폭 약 {abs(mdd)*100:.1f}%")
            if abs(mdd) > 0.45:
                score -= 12

        if rng_pct >= 0.85:
            notes.append("52주 고저 대비 상단 근접")
            score -= 8
        elif rng_pct <= 0.15:
            notes.append("52주 고저 대비 하단 근접")
            score += 4

        if beta is not None:
            notes.append(f"베타(KOSPI 대비 근사)≈{beta:.2f}")
            if beta > 1.3:
                score -= 8

        if short_info.get("rows"):
            notes.append("공매도 데이터 확인됨(세부는 시그널 참조)")
            score -= 4

        # 하방 시나리오(약·중·강) 단순 매핑
        severity = "약함"
        if score <= -25:
            severity = "강함"
        elif score <= -12:
            severity = "중간"
        signals["drawdown_scenario_hint"] = severity

        opinion = "중립"
        if score <= -18:
            opinion = "매도"
        elif score >= 15:
            opinion = "매수"

        reasoning = "; ".join(notes) if notes else "상태 정보 부족"

        return self.build_response(
            opinion=opinion,
            confidence=0.57,
            score=float(max(-50.0, min(50.0, score))),
            reasoning=reasoning,
            signals=signals,
        )

"""
기술적 분석 에이전트(RSI·MACD·이평·볼린저·OBV·상대강도).
"""

from __future__ import annotations

import logging

import pandas as pd

from . import technical_indicators as ti
from backend.agents.base_agent import BaseAgent
from backend.agents.io_async import fetch_equity_ohlcv_async, fetch_index_ohlcv_async
from backend.agents.models import AgentResponse

logger = logging.getLogger(__name__)


class TechnicalAgent(BaseAgent):
    """차트·모멘텀 중심 에이전트."""

    def __init__(self, agent_name: str | None = "기술적") -> None:
        super().__init__(agent_name=agent_name)

    async def analyze(self, ticker: str) -> AgentResponse:
        """OHLCV 기반 기술신호를 종합합니다."""
        code = self.validate_ticker(ticker)

        price_task = fetch_equity_ohlcv_async(code)
        bench_task = fetch_index_ohlcv_async("KS11")
        df_stock, df_bench = await price_task, await bench_task

        close_s, vol_s = ti._ensure_close_volume(df_stock)
        bench_close = df_bench["Close"] if "Close" in df_bench.columns else df_bench["close"]

        aligned_close = close_s.copy()
        aligned_close.index = pd.to_datetime(aligned_close.index).normalize()
        bench_close = bench_close.copy()
        bench_close.index = pd.to_datetime(bench_close.index).normalize()

        rsi_v = ti.rsi(aligned_close, 14)
        macd_info = ti.macd_snapshot(aligned_close)
        mas = ti.moving_averages(aligned_close, (20, 60, 120, 200))
        crosses = ti.golden_death_cross_flags(aligned_close)
        bb = ti.bollinger_band_pctb(aligned_close)
        obv_val = ti.obv_last(aligned_close, vol_s)
        rs = ti.relative_strength_vs_benchmark(aligned_close, bench_close, days=60)

        # 최근 거래량 / 20일 평균 — 과열·스크리닝 거래량 급등 판별용
        vol_ratio_ma20: float | None = None
        if len(vol_s) >= 21:
            ma20 = float(vol_s.iloc[-20:].mean())
            last_v = float(vol_s.iloc[-1])
            if ma20 > 0:
                vol_ratio_ma20 = last_v / ma20

        signals: dict[str, object] = {
            "rsi_14": rsi_v,
            "macd": macd_info,
            "moving_averages": mas,
            "ma_cross": crosses,
            "bollinger": bb,
            "obv_last": obv_val,
            "relative_strength_vs_kospi_60d": rs,
            "volume_vs_ma20_ratio": vol_ratio_ma20,
        }

        score = 0.0
        notes: list[str] = []

        if rsi_v is not None:
            if rsi_v >= 70:
                notes.append(f"RSI 과열 구간({rsi_v:.1f})")
                score -= 14
            elif rsi_v <= 30:
                notes.append(f"RSI 과매도 구간({rsi_v:.1f})")
                score += 10

        if macd_info.get("histogram", 0) > 0:
            notes.append("MACD 히스토그램 양수")
            score += 6
        else:
            notes.append("MACD 히스토그램 음수")
            score -= 4

        if macd_info.get("bullish_cross_recent"):
            notes.append("MACD 단기 골든 교차 가능성")
            score += 8

        if crosses.get("golden_cross_recent"):
            notes.append("이평 골든크로스 근접")
            score += 10
        if crosses.get("death_cross_recent"):
            notes.append("이평 데드크로스 근접")
            score -= 10

        if bb:
            pct_b = bb["pct_b"]
            notes.append(f"볼린저 %B≈{pct_b:.2f}")
            if pct_b >= 1.0:
                score -= 6
            elif pct_b <= 0.0:
                score += 6

        if rs is not None:
            notes.append(f"코스피 대비 60일 상대강도 {rs*100:.1f}%p")
            score += max(-12.0, min(12.0, rs * 50))

        opinion = "중립"
        if score >= 15:
            opinion = "매수"
        elif score <= -15:
            opinion = "매도"

        reasoning = "; ".join(notes) if notes else "뚜렷한 기술적 편향 없음"

        return self.build_response(
            opinion=opinion,
            confidence=0.58,
            score=float(max(-50.0, min(50.0, score))),
            reasoning=reasoning,
            signals=signals,
        )

"""
퀀트·팩터 스타일 에이전트(휴리스틱 1차 버전).

펀더멘털 수신 시 간이 품질/가치 신호를 만들고, 가격 데이터로 모멘텀·변동성 페널티를 줍니다.
"""

from __future__ import annotations

import logging

import pandas as pd

from . import technical_indicators as ti
from backend.agents.base_agent import BaseAgent
from backend.agents.financial_agent import _lookup_fundamentals
from backend.agents.io_async import fetch_equity_ohlcv_async
from backend.agents.models import AgentResponse

logger = logging.getLogger(__name__)


class QuantAgent(BaseAgent):
    """퀀트 전략가 에이전트."""

    def __init__(self, agent_name: str | None = "퀀트") -> None:
        super().__init__(agent_name=agent_name)

    async def analyze(self, ticker: str) -> AgentResponse:
        """
        Piotroski/Magic Formula 전체 구현 전, 규칙 기반 중간 점수를 산출합니다.

        ``signals['piotroski_like']`` 에 0~9 근사 점수를 담습니다.
        """
        code = self.validate_ticker(ticker)

        fundamentals, _ = await _lookup_fundamentals(code)
        df = await fetch_equity_ohlcv_async(code)
        close, _vol = ti._ensure_close_volume(df)
        close.index = pd.to_datetime(close.index).normalize()

        roe_proxy: float | None = None
        if fundamentals:
            eps = fundamentals.get("eps")
            bps = fundamentals.get("bps")
            try:
                if eps is not None and bps not in (None, 0):
                    roe_proxy = float(eps) / float(bps) * 100.0
                    fundamentals["roe_proxy_pct"] = roe_proxy
            except (TypeError, ValueError, ZeroDivisionError):
                roe_proxy = None

        mom120 = ti.total_return(close, 120)
        vol_ann = ti.realized_volatility(close, window=60)

        pi_like = 0
        pq_notes: list[str] = []

        if fundamentals:
            roe_proxy = fundamentals.get("roe_proxy_pct")
            if isinstance(roe_proxy, (int, float)) and roe_proxy > 0:
                pi_like += 2
                pq_notes.append("ROE 프록시 양수")
            per = fundamentals.get("per")
            if isinstance(per, (int, float)) and 0 < per < 15:
                pi_like += 2
                pq_notes.append("PER 중저구간")
            pbr = fundamentals.get("pbr")
            if isinstance(pbr, (int, float)) and 0 < pbr < 1.5:
                pi_like += 2
                pq_notes.append("PBR 완만")
            div_y = fundamentals.get("div_yield_pct")
            if isinstance(div_y, (int, float)) and div_y > 2:
                pi_like += 1
                pq_notes.append("배당수익률 플러스")

        if mom120 is not None and mom120 > 0:
            pi_like += 1
            pq_notes.append("120일 모멘텀 양수")
        if vol_ann is not None and vol_ann < 0.28:
            pi_like += 1
            pq_notes.append("변동성 상대적으로 낮음")

        pi_like = int(min(9, pi_like))

        score = (pi_like - 4.5) * 6.0  # 대략 -27~+27 중심
        if mom120 is not None:
            score += max(-12.0, min(12.0, mom120 * 60))
        if vol_ann is not None and vol_ann > 0.33:
            score -= 10

        signals: dict[str, object] = {
            "piotroski_like": pi_like,
            "momentum_120d": mom120,
            "volatility_ann_60d": vol_ann,
            "fundamentals_available": bool(fundamentals),
            "magic_formula_placeholder": "전종목 순위 산출은 배치 파이프라인 예정",
        }

        opinion = "중립"
        if score >= 14:
            opinion = "매수"
        elif score <= -14:
            opinion = "매도"

        reasoning = (
            f"간이 퀀트 스코어(9점 만점 근사)={pi_like}. "
            + ("; ".join(pq_notes) if pq_notes else "세부 팩터 데이터 부족")
        )

        return self.build_response(
            opinion=opinion,
            confidence=0.52 if fundamentals else 0.40,
            score=float(max(-50.0, min(50.0, score))),
            reasoning=reasoning,
            signals=signals,
        )

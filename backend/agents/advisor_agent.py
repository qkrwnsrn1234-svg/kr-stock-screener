"""
포트폴리오 관점 에이전트입니다.

보유 비중 딕셔너리가 비어 있으면 분석 대상 종목을 100% 보유한 것으로 가정합니다.
"""

from __future__ import annotations

import logging

from . import technical_indicators as ti
from backend.agents.base_agent import BaseAgent
from backend.agents.io_async import fetch_equity_ohlcv_async
from backend.agents.models import AgentResponse

logger = logging.getLogger(__name__)


class AdvisorAgent(BaseAgent):
    """포트폴리오 조언 에이전트."""

    def __init__(
        self,
        holdings: dict[str, float] | None = None,
        *,
        agent_name: str | None = "포트폴리오",
    ) -> None:
        """
        Args:
            holdings: 종목코드→비중(0 이상). 비어 있으면 단일 종목 100% 모드.
            agent_name: 표시 이름.
        """
        super().__init__(agent_name=agent_name)
        self._holdings = {k.strip(): float(v) for k, v in (holdings or {}).items() if float(v) > 0}

    async def analyze(self, ticker: str) -> AgentResponse:
        """
        집중도(HHI)와 변동성 가중 프록시를 바탕으로 분산 아이디어를 제시합니다.
        """
        code = self.validate_ticker(ticker)
        weights = dict(self._holdings)
        if not weights:
            weights = {code: 1.0}

        total_w = sum(weights.values())
        norm_weights = {k: v / total_w for k, v in weights.items()}

        hhi = sum(w * w for w in norm_weights.values())
        max_w = max(norm_weights.values()) if norm_weights else 0.0
        eff_n = (1.0 / hhi) if hhi > 0 else 1.0

        vol_map: dict[str, float | None] = {}
        for t in list(norm_weights.keys())[:12]:
            try:
                df = await fetch_equity_ohlcv_async(t, lookback_days=320)
                close, _ = ti._ensure_close_volume(df)
                vol_map[t] = ti.realized_volatility(close, window=60)
            except Exception as exc:
                logger.debug("포트폴리오 변동성 계산 실패(%s): %s", t, exc)
                vol_map[t] = None

        risk_penalty = 0.0
        for t, w in norm_weights.items():
            v = vol_map.get(t)
            if v is None:
                continue
            risk_penalty += w * v

        n = max(1, len(norm_weights))
        equal_w = 1.0 / n
        suggestion = {t: equal_w for t in norm_weights.keys()}

        score = 0.0
        notes: list[str] = []
        if hhi > 0.34:
            notes.append(f"집중도(HHI) 높음({hhi:.2f}) — 분산 필요")
            score -= 18
        elif hhi > 0.25:
            notes.append(f"집중도(HHI) 다소 높음({hhi:.2f})")
            score -= 10
        else:
            notes.append(f"집중도(HHI) 양호({hhi:.2f})")

        notes.append(f"유효 보유 종목 수(1/HHI 근사)≈{eff_n:.1f}개, 최대 비중≈{max_w*100:.1f}%")
        if max_w > 0.45:
            notes.append("단일 종목 비중이 매우 큼 — 리스크 집중")
            score -= 8
        elif max_w > 0.32:
            notes.append("단일 종목 비중이 큼 — 비중 조절 검토")
            score -= 4

        if risk_penalty > 0.28:
            notes.append("가중 변동성 부담 큼 — 리스크 예산 점검")
            score -= 12

        opinion = "중립"
        if score <= -16:
            opinion = "매도"
        elif score >= 12:
            opinion = "매수"

        signals = {
            "herfindahl_index": hhi,
            "weights_normalized": norm_weights,
            "suggested_equal_weights": suggestion,
            "weighted_vol_proxy": risk_penalty,
            "effective_num_holdings_approx": round(eff_n, 2),
            "max_single_weight": round(max_w, 4),
        }

        reasoning = "; ".join(notes)
        return self.build_response(
            opinion=opinion,
            confidence=0.48,
            score=float(max(-50.0, min(50.0, score))),
            reasoning=reasoning,
            signals=signals,
        )

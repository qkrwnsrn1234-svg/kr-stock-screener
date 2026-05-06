"""
재무·밸류에이션 관점 에이전트입니다.

pykrx 펀더멘털(BPS·PER·PBR·EPS·배당)을 우선 사용하고,
미수신 시 데이터 한계를 ``signals`` 에 명시한 채 신뢰도를 낮춥니다.
"""

from __future__ import annotations

import asyncio
import logging
import math
from datetime import date, timedelta
from typing import Any

from pykrx import stock

from backend.agents.base_agent import BaseAgent
from backend.agents.models import AgentResponse

logger = logging.getLogger(__name__)


def _safe_float(x: Any) -> float | None:
    """pandas 스칼라 등을 안전하게 ``float`` 로 변환합니다."""
    try:
        if x is None:
            return None
        v = float(x)
        if math.isnan(v) or math.isinf(v):
            return None
        return v
    except (TypeError, ValueError):
        return None


async def _lookup_fundamentals(ticker: str) -> tuple[dict[str, Any], str | None]:
    """
    최근 영업일 기준 펀더멘털 스냅샷을 조회합니다.

    Returns:
        (signals_dict, market_or_none)
    """
    for back in range(1, 10):
        d = date.today() - timedelta(days=back)
        if d.weekday() >= 5:
            continue
        ds = d.strftime("%Y%m%d")
        for market in ("KOSPI", "KOSDAQ"):
            try:
                df = await asyncio.to_thread(stock.get_market_fundamental_by_ticker, ds, market)
            except Exception as exc:
                logger.debug("펀더멘털 조회 예외 무시: %s %s %s", ds, market, exc)
                continue
            if df is None or df.empty:
                continue
            if ticker not in df.index.astype(str):
                continue
            row = df.loc[ticker]
            signals = {
                "basis_date": ds,
                "market": market,
                "bps": _safe_float(row.get("BPS")),
                "per": _safe_float(row.get("PER")),
                "pbr": _safe_float(row.get("PBR")),
                "eps": _safe_float(row.get("EPS")),
                "div_yield_pct": _safe_float(row.get("DIV")),  # pykrx 정의: 배당수익률(%)
                "dps": _safe_float(row.get("DPS")),
            }
            return signals, market
    return {}, None


class FinancialAgent(BaseAgent):
    """재무제표·밸류 관점 분석 에이전트."""

    def __init__(self, agent_name: str | None = "재무") -> None:
        super().__init__(agent_name=agent_name)

    async def analyze(self, ticker: str) -> AgentResponse:
        """
        펀더멘털 지표를 바탕으로 의견과 스코어를 산출합니다.

        스코어는 대략 -50(비우량·고평가)~+50(우량·저평가) 범위 체감값입니다.
        """
        code = self.validate_ticker(ticker)
        fundamentals, _market = await _lookup_fundamentals(code)

        if not fundamentals:
            return self.build_response(
                opinion="중립",
                confidence=0.35,
                score=0.0,
                reasoning=(
                    "KRX 펀더멘털 데이터를 가져오지 못했습니다. "
                    "네트워크·장 마감 전 시간대 또는 인증 환경을 확인하세요."
                ),
                signals={"fundamentals_available": False},
            )

        per = fundamentals.get("per")
        pbr = fundamentals.get("pbr")
        eps = fundamentals.get("eps")
        bps = fundamentals.get("bps")
        div_y = fundamentals.get("div_yield_pct")

        graham: float | None = None
        if eps and bps and eps > 0 and bps > 0:
            graham = math.sqrt(22.5 * eps * bps)

        score = 0.0
        notes: list[str] = []

        # 단순 휴리스틱 (업종 정교 비교는 Phase 2에서 보강)
        if per is not None:
            if per <= 0:
                notes.append("PER<=0(적자 또는 특수)")
                score -= 5
            elif per < 12:
                notes.append("PER 낮음(저평가 가능)")
                score += 12
            elif per > 25:
                notes.append("PER 높음(성장 기대 또는 고평가)")
                score -= 10

        if pbr is not None:
            if pbr < 1.0:
                notes.append("PBR<1 (순자산 대비 할인)")
                score += 10
            elif pbr > 3.0:
                notes.append("PBR 높음")
                score -= 8

        if div_y is not None and div_y > 2.5:
            notes.append("배당수익률 양호")
            score += 6

        roe_proxy: float | None = None
        if eps and bps and bps != 0:
            roe_proxy = eps / bps * 100
            fundamentals["roe_proxy_pct"] = roe_proxy
            if roe_proxy >= 15:
                notes.append("ROE(근사) 15% 이상")
                score += 8
            elif roe_proxy < 5:
                notes.append("ROE(근사) 낮음")
                score -= 8

        peg_note = None
        # 성장률 데이터 부재 → PEG는 계산 생략
        fundamentals["peg_ratio"] = None

        opinion = "중립"
        if score >= 15:
            opinion = "매수"
        elif score <= -15:
            opinion = "매도"

        reasoning = "; ".join(notes) if notes else "펀더멘털 균형 구간으로 해석"
        if graham:
            fundamentals["graham_number_approx"] = graham
            reasoning += f"; 그레이엄 수(근사)≈{graham:,.0f}"

        confidence = 0.62 if fundamentals else 0.45
        return self.build_response(
            opinion=opinion,
            confidence=min(0.85, confidence),
            score=float(max(-50.0, min(50.0, score))),
            reasoning=reasoning,
            signals=fundamentals,
        )

"""
거시경제(ECOS 등) 관점 에이전트입니다.

환경 변수 ``ECOS_API_KEY`` 가 없거나 호출이 실패하면 신뢰도를 낮춘 중립 의견을 반환합니다.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Any

from backend.agents.base_agent import BaseAgent
from backend.agents.models import AgentResponse
from backend.data import bok_data

logger = logging.getLogger(__name__)


def _extract_recent_observations(payload: dict[str, Any], limit: int = 5) -> list[dict[str, Any]]:
    """ECOS 응답에서 최근 관측값 목록을 추출합니다 (포맷 변동에 관대)."""
    rows: list[dict[str, Any]] = []
    try:
        rowsets = payload["StatisticSearch"]["row"]
        if isinstance(rowsets, dict):
            rowsets = [rowsets]
        for row in rowsets[-limit:]:
            rows.append(dict(row))
    except (KeyError, TypeError) as exc:
        logger.debug("ECOS row 파싱 실패: %s", exc)
    return rows


class MacroAgent(BaseAgent):
    """금리·환율·물가 등 거시 변수 에이전트."""

    def __init__(self, agent_name: str | None = "거시") -> None:
        super().__init__(agent_name=agent_name)

    async def analyze(self, ticker: str) -> AgentResponse:
        """
        원/달러 일간 통계(예시 코드)와 CPI 등 추가 통계는 향후 확장합니다.

        현재는 ECOS 키가 유효할 때만 환율 추세를 요약합니다.
        """
        self.validate_ticker(ticker)

        signals: dict[str, Any] = {"geopolitical_placeholder": "정성 리스크는 추후 뉴스/LLM 연동"}

        try:
            today = date.today()
            start_date = (today - timedelta(days=420)).strftime("%Y%m%d")
            end_date = today.strftime("%Y%m%d")
            raw = bok_data.fetch_usd_krw_daily(
                start_date=start_date,
                end_date=end_date,
                ttl_seconds=3600,
            )
            obs = _extract_recent_observations(raw, limit=8)
            signals["usd_krw_recent"] = obs

            last_vals = []
            for row in obs:
                v = row.get("DATA_VALUE")
                if v is None:
                    continue
                try:
                    last_vals.append(float(str(v).replace(",", "")))
                except ValueError:
                    continue

            trend_note = "환율 추세 정보 부족"
            score = 0.0
            if len(last_vals) >= 3:
                recent_chg = (last_vals[-1] - last_vals[-3]) / last_vals[-3]
                signals["usd_krw_change_3obs"] = recent_chg
                trend_note = f"원/달러 최근 변화율(근사): {recent_chg*100:.2f}%"
                # 원화 약세(환율 상승) → 수출주 우호 가정(단순)
                if recent_chg > 0.02:
                    score += 8
                    trend_note += " — 원화 약세 국면 신호"
                elif recent_chg < -0.02:
                    score -= 6
                    trend_note += " — 원화 강세 국면 신호"

            opinion = "중립"
            if score >= 6:
                opinion = "매수"
            elif score <= -6:
                opinion = "매도"

            return self.build_response(
                opinion=opinion,
                confidence=0.55,
                score=float(max(-50.0, min(50.0, score))),
                reasoning=(
                    "한국은행 ECOS 기반 원/달러 흐름 요약. "
                    "기준금리·CPI·PMI 세부 코드는 ECOS 통계표 확인 후 확장 예정. "
                    + trend_note
                ),
                signals=signals,
            )
        except RuntimeError as exc:
            logger.info("거시 데이터 미사용(ECOS 키/코드 이슈 가능): %s", exc)
            return self.build_response(
                opinion="중립",
                confidence=0.30,
                score=0.0,
                reasoning=(
                    "ECOS 통계를 불러오지 못했습니다. `.env` 의 ECOS_API_KEY 및 통계표 코드를 확인하세요."
                ),
                signals={"ecos_available": False},
            )

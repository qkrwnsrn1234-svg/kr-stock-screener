"""
거시경제(ECOS 등) 관점 에이전트입니다.

환경 변수 ``ECOS_API_KEY`` 가 없거나 호출이 실패하면 신뢰도를 낮춘 중립 의견을 반환합니다.
``ANTHROPIC_API_KEY`` 가 있으면 Claude를 통해 지정학·금리·환율 영향을 자연어로 보강합니다.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import date, timedelta
from functools import partial
from typing import Any, Callable

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


def _observations_to_floats(obs: list[dict[str, Any]]) -> list[float]:
    """관측 행에서 ``DATA_VALUE`` 만 모아 부동소수 리스트로 만듭니다."""
    out: list[float] = []
    for row in obs:
        v = row.get("DATA_VALUE")
        if v is None:
            continue
        try:
            out.append(float(str(v).replace(",", "")))
        except ValueError:
            continue
    return out


def _month_add(d: date, delta_months: int) -> str:
    """날짜 기준으로 월을 더해 ``YYYYMM`` 문자열을 만듭니다."""
    y, m = d.year, d.month
    idx = y * 12 + (m - 1) + delta_months
    ny, rem = divmod(idx, 12)
    nm = rem + 1
    return f"{ny:04d}{nm:02d}"


class MacroAgent(BaseAgent):
    """금리·환율·물가 등 거시 변수 에이전트."""

    def __init__(self, agent_name: str | None = "거시") -> None:
        super().__init__(agent_name=agent_name)

    async def analyze(self, ticker: str) -> AgentResponse:
        """
        ECOS 기준 원/달러·기준금리·CPI·PMI를 요약하고 Claude 코멘터리를 붙입니다.

        개별 통계 호출이 실패해도 나머지 지표는 가능한 채웁니다.
        """
        self.validate_ticker(ticker)

        signals: dict[str, Any] = {}
        score = 0.0
        trend_notes: list[str] = []
        series_ok = 0

        today = date.today()
        start_d = (today - timedelta(days=420)).strftime("%Y%m%d")
        end_d = today.strftime("%Y%m%d")
        rate_start_d = (today - timedelta(days=400)).strftime("%Y%m%d")
        start_m = _month_add(today, -48)
        end_m = today.strftime("%Y%m")

        async def _safe_thread(
            label: str,
            fn: Callable[..., dict[str, Any]],
        ) -> dict[str, Any] | None:
            try:
                raw = await asyncio.to_thread(fn)
                logger.debug("ECOS %s 수신", label)
                return raw
            except RuntimeError as exc:
                logger.info("ECOS %s 실패 — %s", label, exc)
                return None

        raw_usd, raw_rate, raw_cpi, raw_pmi = await asyncio.gather(
            _safe_thread(
                "usd_krw",
                partial(
                    bok_data.fetch_usd_krw_daily,
                    start_date=start_d,
                    end_date=end_d,
                    ttl_seconds=3600,
                ),
            ),
            _safe_thread(
                "base_rate",
                partial(
                    bok_data.fetch_base_rate_daily,
                    rate_start_d,
                    end_d,
                    ttl_seconds=7200,
                ),
            ),
            _safe_thread(
                "cpi_yoy",
                partial(
                    bok_data.fetch_cpi_yoy_monthly,
                    start_m,
                    end_m,
                    ttl_seconds=7200,
                ),
            ),
            _safe_thread(
                "pmi",
                partial(
                    bok_data.fetch_manufacturing_pmi_monthly,
                    start_m,
                    end_m,
                    ttl_seconds=7200,
                ),
            ),
        )

        usd_krw_change: float | None = None
        if raw_usd:
            obs = _extract_recent_observations(raw_usd, limit=8)
            signals["usd_krw_recent"] = obs
            last_vals = _observations_to_floats(obs)
            if len(last_vals) >= 3:
                usd_krw_change = (last_vals[-1] - last_vals[-3]) / last_vals[-3]
                signals["usd_krw_change_3obs"] = usd_krw_change
                trend_notes.append(
                    f"원/달러 최근 변화율(근사): {usd_krw_change * 100:.2f}%"
                )
                if usd_krw_change > 0.02:
                    score += 8
                    trend_notes.append("원화 약세 국면 신호")
                elif usd_krw_change < -0.02:
                    score -= 6
                    trend_notes.append("원화 강세 국면 신호")
            series_ok += 1

        if raw_rate:
            obs_r = _extract_recent_observations(raw_rate, limit=12)
            signals["bok_base_rate_recent"] = obs_r
            vals_r = _observations_to_floats(obs_r)
            if len(vals_r) >= 2:
                signals["bok_base_rate_last_pct"] = vals_r[-1]
                if vals_r[-1] > vals_r[0]:
                    score -= 4
                    trend_notes.append("기준금리 최근 구간 상승 추세")
                elif vals_r[-1] < vals_r[0]:
                    score += 3
                    trend_notes.append("기준금리 최근 구간 하향·완화 추세")
            series_ok += 1

        if raw_cpi:
            obs_c = _extract_recent_observations(raw_cpi, limit=8)
            signals["cpi_yoy_recent"] = obs_c
            vals_c = _observations_to_floats(obs_c)
            if len(vals_c) >= 2:
                signals["cpi_yoy_last_pct"] = vals_c[-1]
                if vals_c[-1] > vals_c[-2] + 0.2:
                    score -= 3
                    trend_notes.append("CPI 전년비 상승률 가속(인플레 압력)")
                elif vals_c[-1] < vals_c[-2] - 0.2:
                    score += 2
                    trend_notes.append("CPI 전년비 상승률 둔화")
            series_ok += 1

        if raw_pmi:
            obs_p = _extract_recent_observations(raw_pmi, limit=6)
            signals["pmi_manufacturing_recent"] = obs_p
            vals_p = _observations_to_floats(obs_p)
            if vals_p:
                last_p = vals_p[-1]
                signals["pmi_manufacturing_last"] = last_p
                if last_p < 50.0:
                    score -= 4
                    trend_notes.append("제조업 PMI 50 미만(수축 우려)")
                elif last_p >= 51.0:
                    score += 4
                    trend_notes.append("제조업 PMI 양호(확장 국면)")
            series_ok += 1

        ecos_partial_or_full = series_ok > 0
        claude_commentary: str | None = None
        try:
            from backend.agents.claude_client import generate_macro_commentary

            claude_commentary = await generate_macro_commentary(
                ticker=ticker,
                usd_krw_change_pct=usd_krw_change,
                ecos_available=ecos_partial_or_full,
                signals=signals,
            )
        except Exception as exc:
            logger.debug("거시 Claude 코멘터리 스킵: %s", exc)

        if claude_commentary:
            signals["claude_macro_commentary"] = claude_commentary

        opinion = "중립"
        if score >= 8:
            opinion = "매수"
        elif score <= -8:
            opinion = "매도"

        if not trend_notes:
            trend_notes.append("거시 시계열 파싱 결과가 비었거나 ECOS 키/코드 이슈일 수 있습니다.")

        reasoning_core = (
            f"ECOS 연계 지표 {series_ok}개 수신. "
            + "; ".join(trend_notes)
        )
        reasoning_parts = [reasoning_core]
        if not ecos_partial_or_full and not claude_commentary:
            reasoning_parts = [
                "ECOS 통계를 불러오지 못했습니다. `.env` 의 ECOS_API_KEY·통계표 코드를 확인하세요."
            ]
            return self.build_response(
                opinion="중립",
                confidence=0.30,
                score=0.0,
                reasoning=reasoning_parts[0],
                signals={"ecos_available": False},
            )

        if claude_commentary:
            reasoning_parts.append(f"[Claude 거시 분석] {claude_commentary}")

        confidence = 0.68 if (ecos_partial_or_full and claude_commentary) else (0.58 if ecos_partial_or_full else 0.42)
        return self.build_response(
            opinion=opinion,
            confidence=confidence,
            score=float(max(-50.0, min(50.0, score))),
            reasoning=" | ".join(reasoning_parts),
            signals=signals,
        )

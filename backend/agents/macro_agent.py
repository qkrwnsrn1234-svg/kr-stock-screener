"""
거시경제(ECOS·미국 시장 프록시) 관점 에이전트입니다.

``ECOS_API_KEY`` 가 없어도 ``yfinance`` 기반 DXY·^IRX(미국 3개월 국채) 스냅샷으로 보조합니다.
``ANTHROPIC_API_KEY`` 가 있으면 Claude 코멘터리를 붙입니다.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import date, timedelta
from functools import partial
from typing import Any, Callable

from backend.agents.base_agent import BaseAgent
from backend.agents.models import AgentResponse
from backend.data import bok_data, finance_data, us_macro_data

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


def _dept_for_ticker_sync(code: str) -> str:
    """상장 목록에서 종목의 ``Dept`` 문자열을 가져옵니다."""
    try:
        df = finance_data.list_krx_symbols(None)
        if df is None or df.empty or "Code" not in df.columns:
            return ""
        codes = df["Code"].astype(str).str.zfill(6)
        rows = df[codes == code.strip().zfill(6)]
        if rows.empty:
            return ""
        dept = str(rows.iloc[0].get("Dept", "") or "").strip()
        return dept if dept.lower() != "nan" else ""
    except Exception as exc:
        logger.debug("거시용 업종 조회 생략: %s", exc)
        return ""


def _sector_rate_pressure(dept: str, bok_rate_rising: bool | None) -> tuple[float, str]:
    """
    한국 기준금리 상승 구간에서 업종별 차입·이자 민감도 휴리스틱(점수 보정).
    """
    if not dept or bok_rate_rising is not True:
        return 0.0, ""
    sens_hi = ("건설", "부동산", "금융", "은행", "보험", "증권", "캐피탈")
    sens_mid = ("유통", "운수", "운송", "화학", "철강", "에너지", "가전")
    if any(k in dept for k in sens_hi):
        return -3.0, f"기준금리 상승 구간 — 업종({dept}) 금리 민감도 높음(휴리스틱)"
    if any(k in dept for k in sens_mid):
        return -1.5, f"기준금리 상승 구간 — 업종({dept}) 다소 민감(휴리스틱)"
    return 0.0, ""


class MacroAgent(BaseAgent):
    """금리·환율·물가 등 거시 변수 에이전트."""

    def __init__(self, agent_name: str | None = "거시") -> None:
        super().__init__(agent_name=agent_name)

    async def analyze(self, ticker: str) -> AgentResponse:
        """
        ECOS 기준 원/달러·기준금리·CPI·전산업 업황 BSI(PMI 대리)를 요약하고 Claude 코멘터리를 붙입니다.

        개별 통계 호출이 실패해도 나머지 지표는 가능한 채웁니다.
        """
        self.validate_ticker(ticker)
        code = ticker.strip()

        signals: dict[str, Any] = {}
        score = 0.0
        trend_notes: list[str] = []
        series_ok = 0
        bok_rate_rising: bool | None = None

        today = date.today()
        start_d = (today - timedelta(days=420)).strftime("%Y%m%d")
        end_d = today.strftime("%Y%m%d")
        rate_start_d = (today - timedelta(days=400)).strftime("%Y%m%d")
        start_m = _month_add(today, -48)
        end_m = today.strftime("%Y%m")

        async def _safe_ecos(label: str, fn: Callable[..., Any]) -> Any:
            # ECOS 호출은 네트워크·통계표 코드 이슈로 자주 단건 실패 → 나머지 지표는 유지
            try:
                raw = await asyncio.to_thread(fn)
                logger.debug("ECOS %s 수신", label)
                return raw
            except RuntimeError as exc:
                logger.info("ECOS %s 실패 — %s", label, exc)
                return None

        raw_usd, raw_rate, raw_cpi, raw_pmi, us_snap, dept_str = await asyncio.gather(
            _safe_ecos(
                "usd_krw",
                partial(
                    bok_data.fetch_usd_krw_daily,
                    start_date=start_d,
                    end_date=end_d,
                    ttl_seconds=3600,
                ),
            ),
            _safe_ecos(
                "base_rate",
                partial(
                    bok_data.fetch_base_rate_daily,
                    rate_start_d,
                    end_d,
                    ttl_seconds=7200,
                ),
            ),
            _safe_ecos(
                "cpi_yoy",
                partial(
                    bok_data.fetch_cpi_yoy_monthly,
                    start_m,
                    end_m,
                    ttl_seconds=7200,
                ),
            ),
            _safe_ecos(
                "industry_bsi",
                partial(
                    bok_data.fetch_manufacturing_pmi_monthly,
                    start_m,
                    end_m,
                    ttl_seconds=7200,
                ),
            ),
            asyncio.to_thread(
                partial(us_macro_data.fetch_us_dollar_rate_snapshot, ttl_seconds=7200),
            ),
            asyncio.to_thread(_dept_for_ticker_sync, code),
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
                bok_rate_rising = vals_r[-1] > vals_r[0]
                if bok_rate_rising:
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
            signals["industry_bsi_recent"] = obs_p
            signals["pmi_manufacturing_recent"] = obs_p
            vals_p = _observations_to_floats(obs_p)
            if vals_p:
                last_p = vals_p[-1]
                signals["industry_bsi_last"] = last_p
                signals["pmi_manufacturing_last"] = last_p
                if last_p < 100.0:
                    score -= 4
                    trend_notes.append("전산업 업황 BSI 100 미만(기준치 대비 위축)")
                elif last_p >= 101.0:
                    score += 4
                    trend_notes.append("전산업 업황 BSI 호조(기준치 100 상회)")
            series_ok += 1

        us_data_ok = False
        if isinstance(us_snap, dict) and us_snap.get("ok"):
            signals["us_macro_yfinance"] = dict(us_snap)
            us_data_ok = True
            irx_pp = us_snap.get("us_tbill_3mo_yield_change_approx_1m_pp")
            if isinstance(irx_pp, (int, float)) and irx_pp > 0.12:
                score -= 3
                trend_notes.append("미국 3개월 국채 수익률 단기 상승(^IRX proxy)")
            dxy_ch = us_snap.get("dxy_change_approx_1m_ratio")
            if isinstance(dxy_ch, (int, float)):
                if dxy_ch > 0.015:
                    score -= 2
                    trend_notes.append("달러 인덱스(DXY) 상승 — 강달러 분위기")
                elif dxy_ch < -0.015:
                    score += 1
                    trend_notes.append("DXY 약세 — 달러 분위기 완화")

        if dept_str:
            signals["listing_dept_proxy"] = dept_str
            sec_adj, sec_note = _sector_rate_pressure(dept_str, bok_rate_rising)
            if sec_note:
                trend_notes.append(sec_note)
                score += sec_adj

        ecos_partial_or_full = series_ok > 0
        claude_commentary: str | None = None
        try:
            from backend.agents.claude_client import generate_macro_commentary

            claude_commentary = await generate_macro_commentary(
                ticker=ticker,
                usd_krw_change_pct=usd_krw_change,
                ecos_available=ecos_partial_or_full or us_data_ok,
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
            trend_notes.append(
                "ECOS·미국 yfinance 데이터가 비었거나 키·네트워크 이슈일 수 있습니다."
            )

        data_any = ecos_partial_or_full or us_data_ok or bool(claude_commentary)
        reasoning_core = (
            f"ECOS 시계열 {series_ok}건"
            + ("; yfinance DXY·^IRX 수신" if us_data_ok else "")
            + ". "
            + "; ".join(trend_notes)
        )
        reasoning_parts = [reasoning_core]
        if not data_any:
            reasoning_parts = [
                "거시 데이터를 가져오지 못했습니다. ECOS_API_KEY·네트워크·yfinance 설치를 확인하세요."
            ]
            return self.build_response(
                opinion="중립",
                confidence=0.28,
                score=0.0,
                reasoning=reasoning_parts[0],
                signals={
                    "ecos_available": False,
                    "us_yfinance_ok": False,
                },
            )

        if claude_commentary:
            reasoning_parts.append(f"[Claude 거시 분석] {claude_commentary}")

        signals["ecos_series_count"] = series_ok
        signals["us_yfinance_ok"] = us_data_ok
        signals["ecos_available"] = ecos_partial_or_full

        if ecos_partial_or_full and claude_commentary:
            confidence = 0.68
        elif ecos_partial_or_full:
            confidence = 0.58
        elif us_data_ok and claude_commentary:
            confidence = 0.55
        elif us_data_ok:
            confidence = 0.50
        elif claude_commentary:
            confidence = 0.48
        else:
            confidence = 0.42
        return self.build_response(
            opinion=opinion,
            confidence=confidence,
            score=float(max(-50.0, min(50.0, score))),
            reasoning=" | ".join(reasoning_parts),
            signals=signals,
        )

"""
퀀트·팩터 스타일 에이전트입니다.

Piotroski F-Score(재무제표 기반 9항목), Greenblatt 매직포뮬러 요소(EBIT/EV·EBIT/투하자본),
가격 기반 모멘텀·변동성 보정을 결합합니다.
"""

from __future__ import annotations

import logging

import pandas as pd

from backend.agents import technical_indicators as ti
from backend.agents.base_agent import BaseAgent
from backend.agents.financial_agent import (
    _lookup_fundamentals,
    _lookup_market_cap_krw,
    fetch_dart_financial_snapshot,
)
from backend.agents.io_async import fetch_equity_ohlcv_async
from backend.agents.models import AgentResponse

logger = logging.getLogger(__name__)


def _piotroski_f_score(d: dict[str, float | None]) -> tuple[int, dict[str, bool]]:
    """
    Piotroski F-Score(0~9)를 DART 스냅샷으로 계산합니다.

    F7(유상증자·신주 없음)는 유통주식수 시계열이 없으므로 **검증 불가 시 0점**(보수적)으로 둡니다.

    Args:
        d: ``_parse_dart_financials`` 형식의 당기·전기 혼합 딕셔너리.

    Returns:
        (총점, 각 기준 충족 여부).
    """
    crit: dict[str, bool] = {}
    ni = d.get("net_income")
    ta = d.get("total_assets")
    ni_p = d.get("net_income_prev")
    ta_p = d.get("total_assets_prev")
    cfo = d.get("operating_cf")
    ca = d.get("current_assets")
    cl = d.get("current_liabilities")
    ca_p = d.get("current_assets_prev")
    cl_p = d.get("current_liabilities_prev")
    debt = d.get("interest_bearing_debt") or 0.0
    debt_p = d.get("interest_bearing_debt_prev")
    rev = d.get("revenue")
    rev_p = d.get("revenue_prev")
    gp = d.get("gross_profit")
    gp_p = d.get("gross_profit_prev")

    roa = (ni / ta) if ni is not None and ta not in (None, 0) else None
    roa_p = (ni_p / ta_p) if ni_p is not None and ta_p not in (None, 0) else None

    crit["f1_roa_positive"] = bool(roa is not None and roa > 0)
    crit["f2_cfo_positive"] = bool(cfo is not None and cfo > 0)
    crit["f3_roa_improved"] = bool(
        roa is not None and roa_p is not None and roa > roa_p
    )
    crit["f4_quality_cfo_vs_ni"] = bool(
        cfo is not None and ni is not None and cfo > ni
    )

    lev = (debt / ta) if ta not in (None, 0) else None
    lev_p = (
        (debt_p / ta_p)
        if debt_p is not None and ta_p not in (None, 0)
        else None
    )
    crit["f5_leverage_down"] = bool(
        lev is not None and lev_p is not None and lev < lev_p
    )

    cr = (ca / cl) if ca is not None and cl not in (None, 0) else None
    cr_p = (ca_p / cl_p) if ca_p is not None and cl_p not in (None, 0) else None
    crit["f6_liquidity_up"] = bool(cr is not None and cr_p is not None and cr > cr_p)

    crit["f7_no_share_dilution_evidence"] = False

    gm = (gp / rev) if gp is not None and rev not in (None, 0) else None
    gm_p = (gp_p / rev_p) if gp_p is not None and rev_p not in (None, 0) else None
    crit["f8_gross_margin_up"] = bool(
        gm is not None and gm_p is not None and gm > gm_p
    )

    at = (rev / ta) if rev is not None and ta not in (None, 0) else None
    at_p = (rev_p / ta_p) if rev_p is not None and ta_p not in (None, 0) else None
    crit["f9_asset_turnover_up"] = bool(
        at is not None and at_p is not None and at > at_p
    )

    total = sum(1 for v in crit.values() if v)
    return int(total), crit


def _magic_formula_metrics(
    d: dict[str, float | None],
    mcap: float | None,
) -> dict[str, float | None]:
    """
    매직포뮬러의 두 요소(수익률·자본수익률)를 **단일 종목** 관점에서 산출합니다.

    전 종목 내 순위 매기기는 배치 파이프라인에서 수행한다고 안내합니다.

    Args:
        d: DART 파싱 결과.
        mcap: 당기 기준 시가총액(원).

    Returns:
        ``earnings_yield`` (EBIT/EV), ``return_on_capital`` (EBIT/(NWC+PPE)) 등.
    """
    ebit = d.get("operating_profit")
    debt_v = float(d.get("interest_bearing_debt") or 0.0)
    cash_v = float(d.get("cash_equiv") or 0.0)
    net_debt = debt_v - cash_v
    ev = (float(mcap) + net_debt) if mcap is not None else None
    ey = (float(ebit) / ev) if ev and ev > 0 and ebit is not None and ebit > 0 else None

    ca = d.get("current_assets")
    cl = d.get("current_liabilities")
    ppe = d.get("ppe_net")
    ta = d.get("total_assets")
    nwc = (float(ca) - float(cl)) if ca is not None and cl is not None else None
    if ppe is None and ta is not None and ca is not None:
        ppe_use = max(0.0, float(ta) - float(ca))
    elif ppe is not None:
        ppe_use = max(0.0, float(ppe))
    else:
        ppe_use = 0.0

    denom = None
    if nwc is not None:
        denom = nwc + ppe_use
    roc = (
        (float(ebit) / denom)
        if denom is not None and denom > 0 and ebit is not None and ebit > 0
        else None
    )
    return {
        "magic_formula_earnings_yield": ey,
        "magic_formula_return_on_capital": roc,
        "magic_formula_ev_krw_approx": float(ev) if ev is not None else None,
    }


class QuantAgent(BaseAgent):
    """퀀트 전략가 에이전트."""

    def __init__(self, agent_name: str | None = "퀀트") -> None:
        super().__init__(agent_name=agent_name)

    async def analyze(self, ticker: str) -> AgentResponse:
        """
        Piotroski·매직포뮬러·모멘텀을 결합한 점수와 근거를 반환합니다.
        """
        code = self.validate_ticker(ticker)

        fundamentals, mkt = await _lookup_fundamentals(code)
        dart_fin, _dart_meta = await fetch_dart_financial_snapshot(code)
        df = await fetch_equity_ohlcv_async(code)
        close, _vol = ti._ensure_close_volume(df)
        close.index = pd.to_datetime(close.index).normalize()

        mom120 = ti.total_return(close, 120)
        vol_ann = ti.realized_volatility(close, window=60)

        basis = str(fundamentals.get("basis_date") or "") if fundamentals else ""
        mkt_s = str(fundamentals.get("market") or mkt or "KOSPI") if fundamentals else (
            mkt or "KOSPI"
        )
        mcap: float | None = None
        if fundamentals and basis:
            fundamentals = dict(fundamentals)
            mcap = await _lookup_market_cap_krw(code, basis, mkt_s)
            if mcap is not None:
                fundamentals["market_cap_krw"] = mcap

        # Piotroski·매직포뮬러(DART 필요)
        pi_total = 0
        pi_crit: dict[str, bool] = {}
        mf: dict[str, float | None] = {}
        dart_ok = bool(dart_fin and any(v not in (None, 0) for v in dart_fin.values()))
        if dart_ok:
            pi_total, pi_crit = _piotroski_f_score(dart_fin)
            mf = _magic_formula_metrics(dart_fin, mcap)

        # 기본 점수: F-Score 중심 + 매직 요소 가중
        score = (pi_total - 4.5) * 5.5
        ey = mf.get("magic_formula_earnings_yield")
        roc = mf.get("magic_formula_return_on_capital")
        if ey is not None and ey > 0.06:
            score += 7.0
        elif ey is not None and ey > 0.03:
            score += 3.0
        if roc is not None and roc > 0.20:
            score += 7.0
        elif roc is not None and roc > 0.12:
            score += 3.5

        if mom120 is not None:
            score += max(-12.0, min(12.0, mom120 * 60))
        if vol_ann is not None and vol_ann > 0.33:
            score -= 10

        pq_notes: list[str] = []
        if dart_ok:
            pq_notes.append(f"Piotroski F-Score={pi_total}/9")
            if ey is not None:
                pq_notes.append(f"EBIT/EV(근사)={ey:.3f}")
            if roc is not None:
                pq_notes.append(f"EBIT/(NWC+PPE)(근사)={roc:.3f}")
        else:
            pq_notes.append("DART 재무 없음 — F-Score·매직포뮬러 제한")

        if fundamentals:
            rpp = fundamentals.get("roe_proxy_pct")
            if isinstance(rpp, (int, float)) and rpp > 0:
                pq_notes.append("ROE 프록시 양수(pykrx)")

        signals: dict[str, object] = {
            "piotroski_f_score": pi_total,
            "piotroski_criteria": pi_crit,
            "magic_formula": mf,
            "magic_formula_note": "전 종목 순위·복합점수는 배치 유니버스가 필요합니다.",
            "momentum_120d": mom120,
            "volatility_ann_60d": vol_ann,
            "fundamentals_available": bool(fundamentals),
            "dart_financials_available": dart_ok,
        }
        if fundamentals:
            signals["pykrx_fundamentals"] = fundamentals

        opinion = "중립"
        if score >= 14:
            opinion = "매수"
        elif score <= -14:
            opinion = "매도"

        reasoning = "; ".join(pq_notes) if pq_notes else "데이터 부족"

        conf = 0.62 if (dart_ok and fundamentals) else (0.55 if fundamentals else 0.40)
        return self.build_response(
            opinion=opinion,
            confidence=conf,
            score=float(max(-50.0, min(50.0, score))),
            reasoning=reasoning,
            signals=signals,
        )

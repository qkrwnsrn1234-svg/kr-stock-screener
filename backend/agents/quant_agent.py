"""
퀀트·팩터 스타일 에이전트입니다.

Piotroski F-Score(재무제표 기반 9항목), Greenblatt 매직포뮬러 요소(EBIT/EV·EBIT/투하자본),
가격 기반 모멘텀·변동성 보정을 결합합니다.

동종 PER/PBR 중앙값 기반 괴리(컨센서스 대용), 연간 당기순이익 YoY 가속도,
DART 공시명 키워드 기반 내부자·자사주 힌트를 보조 시그널로 포함합니다.
"""

from __future__ import annotations

import asyncio
import logging
import re
from datetime import date, timedelta
from typing import Any

import pandas as pd

from backend.agents import technical_indicators as ti
from backend.agents.base_agent import BaseAgent
from backend.agents.financial_agent import (
    _lookup_fundamentals,
    _lookup_market_cap_krw,
    _parse_dart_financials,
    fetch_dart_financial_snapshot,
)
from backend.agents.io_async import fetch_equity_ohlcv_async
from backend.agents.models import AgentResponse
from backend.screener.peer_valuation import fetch_sector_peer_stats

logger = logging.getLogger(__name__)

# 공시명에서 자사주·지배주주 쪽 매수/매도 성격을 짐작할 때 쓰는 키워드 (완전한 NLP 대체 아님)
_DART_TITLE_BUY_HINT = re.compile(
    r"(자기주식\s*취득|자기주식취득|취득\s*결과|소유(?:지분|주식)\s*증가|매수\s*목적의\s*취득)",
    re.I,
)
_DART_TITLE_SELL_HINT = re.compile(
    r"(자기주식\s*처분|자기주식처분|처분\s*결과|소유(?:지분|주식)\s*감소)",
    re.I,
)
_DART_TITLE_MAJOR_HOLDER = re.compile(
    r"(임원[·ㆍ]주요주주|주요주주|특정증권등\s*소유상황|대량보유상황)",
    re.I,
)

# 연간 실적 이력 조회 시 최대 연도 수 (사업보고서 11011)
_ANNUAL_NI_LOOKBACK_YEARS = 5
# 내부자 공시 힌트 조회 기간 및 최대 페이지
_INSIDER_DISCLOSURE_DAYS = 200
_INSIDER_MAX_PAGES = 5


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


def _clamp01(x: float) -> float:
    """0~1 구간으로 잘라냅니다."""
    return max(0.0, min(1.0, x))


def _multifactor_scores(
    *,
    pi_total: int,
    mom120: float | None,
    vol_ann: float | None,
    per: float | None,
    pbr: float | None,
    ey: float | None,
) -> dict[str, float]:
    """
    가치·모멘텀·퀄리티·저변동성 하위 점수(각 0~100)와 복합 점수를 계산합니다.

    전 종목 유니버스 내 z-score·순위는 배치 스크리닝에서 다루고,
    여기서는 **단일 종목** 관점의 해석 가능한 가중 평균만 제공합니다.

    Returns:
        quality, value, momentum, low_volatility 각 0~100 및 composite_0_100.
    """
    quality = (pi_total / 9.0) * 100.0

    value_parts: list[float] = []
    if per is not None and per > 0:
        value_parts.append(100.0 * _clamp01((35.0 - min(per, 35.0)) / 35.0))
    if pbr is not None and pbr > 0:
        value_parts.append(100.0 * _clamp01((4.0 - min(pbr, 4.0)) / 4.0))
    if ey is not None and ey > 0:
        value_parts.append(100.0 * _clamp01(ey / 0.22))
    value = sum(value_parts) / len(value_parts) if value_parts else 50.0

    if mom120 is not None:
        momentum = 100.0 * _clamp01((mom120 + 0.35) / 0.70)
    else:
        momentum = 50.0

    if vol_ann is not None and vol_ann > 0:
        low_vol = 100.0 * _clamp01((0.52 - min(vol_ann, 0.52)) / 0.40)
    else:
        low_vol = 50.0

    w_val, w_mom, w_qual, w_lv = 0.26, 0.24, 0.30, 0.20
    composite = w_val * value + w_mom * momentum + w_qual * quality + w_lv * low_vol
    return {
        "value_0_100": round(value, 2),
        "momentum_0_100": round(momentum, 2),
        "quality_0_100": round(quality, 2),
        "low_volatility_0_100": round(low_vol, 2),
        "composite_0_100": round(composite, 2),
    }


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


async def _resolve_corp_code(ticker: str) -> str | None:
    """DART corp_code를 조회합니다. 키가 없으면 None."""
    try:
        from backend.data import dart_data

        return await asyncio.to_thread(dart_data.find_corp_code, ticker)
    except Exception as exc:
        logger.debug("DART corp_code 조회 불가 %s: %s", ticker, exc)
        return None


def _last_close_price_krw(close: pd.Series) -> float | None:
    """종가 시계열의 최신 유효 가격(원)을 반환합니다."""
    if close is None or close.empty:
        return None
    try:
        v = float(close.iloc[-1])
    except (TypeError, ValueError):
        return None
    if v <= 0 or v != v:  # NaN
        return None
    return v


async def _peer_consensus_gap_proxy(
    code: str,
    fundamentals: dict[str, Any] | None,
    last_price: float | None,
) -> dict[str, Any]:
    """
    컨센서스 목표주가 대신 동종 PER/PBR 중앙값으로 내재가를 근사하고 현재가 대비 괴리율을 냅니다.

    Args:
        code: 6자리 종목코드.
        fundamentals: pykrx 펀더멘털 스냅샷.
        last_price: 최근 종가(원).

    Returns:
        괴리율·동종 통계 메타.
    """
    note = (
        "증권사 목표주가 컨센서스가 아니라, 동일 Dept 동종 PER·PBR 중앙값 기준 근사입니다."
    )
    out: dict[str, Any] = {
        "note": note,
        "median_per_implied_price": None,
        "median_pbr_implied_price": None,
        "current_price_krw": last_price,
        "gap_pct_vs_median_per": None,
        "gap_pct_vs_median_pbr": None,
        "blended_gap_pct": None,
        "peer_sector": None,
        "peer_count": None,
    }
    if not fundamentals or last_price is None or last_price <= 0:
        return out

    peer = await fetch_sector_peer_stats(code)
    out["peer_sector"] = peer.sector_label
    out["peer_count"] = peer.peer_count

    eps = fundamentals.get("eps")
    bps = fundamentals.get("bps")
    gap_values: list[float] = []

    if (
        isinstance(eps, (int, float))
        and float(eps) > 0
        and peer.median_per is not None
        and peer.median_per > 0
    ):
        implied = float(eps) * float(peer.median_per)
        out["median_per_implied_price"] = implied
        gap_p = (implied - last_price) / last_price * 100.0
        out["gap_pct_vs_median_per"] = round(gap_p, 2)
        gap_values.append(gap_p)

    if (
        isinstance(bps, (int, float))
        and float(bps) > 0
        and peer.median_pbr is not None
        and peer.median_pbr > 0
    ):
        implied_b = float(bps) * float(peer.median_pbr)
        out["median_pbr_implied_price"] = implied_b
        gap_b = (implied_b - last_price) / last_price * 100.0
        out["gap_pct_vs_median_pbr"] = round(gap_b, 2)
        gap_values.append(gap_b)

    if gap_values:
        out["blended_gap_pct"] = round(sum(gap_values) / len(gap_values), 2)
    return out


async def _annual_net_income_history_for_surprise_proxy(corp_code: str) -> dict[str, Any]:
    """
    사업보고서(11011)에서 연간 당기순이익과 YoY, 가속도를 만듭니다.

    Args:
        corp_code: DART 법인 고유번호.

    Returns:
        연도별 순이익·YoY·가속도(퍼센트포인트).
    """
    from backend.data import dart_data

    rows_out: list[dict[str, Any]] = []
    y0 = date.today().year
    for offset in range(0, _ANNUAL_NI_LOOKBACK_YEARS):
        ystr = str(y0 - offset)
        picked: dict[str, Any] | None = None
        for fs_div in ("CFS", "OFS"):
            try:
                raw = await asyncio.to_thread(
                    dart_data.fetch_financial_accounts,
                    corp_code,
                    ystr,
                    "11011",
                    fs_div=fs_div,
                )
                dart_rows: list[dict[str, Any]] = raw.get("list") or []
                if not dart_rows:
                    continue
                parsed = _parse_dart_financials(dart_rows)
                ni = parsed.get("net_income")
                if ni is None:
                    continue
                picked = {
                    "year": int(ystr),
                    "net_income_krw": float(ni),
                    "fs_div": fs_div,
                }
                break
            except Exception as exc:
                logger.debug(
                    "연간 순이익 조회 실패 corp=%s year=%s: %s", corp_code, ystr, exc
                )
                continue
        if picked:
            rows_out.append(picked)

    rows_out.sort(key=lambda r: r["year"])
    yoys: list[float] = []
    for i in range(1, len(rows_out)):
        prev = float(rows_out[i - 1]["net_income_krw"])
        cur = float(rows_out[i]["net_income_krw"])
        if prev == 0:
            yoy: float | None = None
        else:
            yoy = (cur - prev) / abs(prev) * 100.0
        rows_out[i]["yoy_pct"] = round(yoy, 2) if yoy is not None else None
        if yoy is not None:
            yoys.append(float(yoy))

    accel: float | None = None
    if len(yoys) >= 2:
        accel = round(yoys[-1] - yoys[-2], 2)

    streak = 0
    for r in reversed(rows_out):
        y = r.get("yoy_pct")
        if y is None:
            break
        if float(y) > 0:
            streak += 1
        else:
            break

    return {
        "annual_net_income": rows_out,
        "yoy_acceleration_pp": accel,
        "positive_yoy_streak_years": streak,
        "interpretation_note": (
            "실제 어닝 서프라이즈(컨센서스 대비)는 별도 데이터가 필요합니다. "
            "여기서는 연간 순이익 YoY와 가속도만 제공합니다."
        ),
    }


def _disclosure_title(item: dict[str, Any]) -> str:
    """DART 공시 목록 행에서 제목 문자열을 꺼냅니다."""
    return str(
        item.get("report_nm")
        or item.get("rcept_nm")
        or item.get("title")
        or ""
    ).strip()


async def _insider_disclosure_hints(corp_code: str) -> dict[str, Any]:
    """
    최근 공시 제목에서 자사주·주요주주 관련 키워드를 세어 휴리스틱 힌트를 반환합니다.

    Args:
        corp_code: DART 법인 고유번호.

    Returns:
        매수/매도 성격으로 보이는 공시 건수 등.
    """
    from backend.data import dart_data

    end = date.today()
    start = end - timedelta(days=_INSIDER_DISCLOSURE_DAYS)
    start_s = start.strftime("%Y%m%d")
    end_s = end.strftime("%Y%m%d")

    buy_like = 0
    sell_like = 0
    major = 0
    samples: list[str] = []

    for page in range(1, _INSIDER_MAX_PAGES + 1):
        try:
            data = await asyncio.to_thread(
                dart_data.fetch_disclosure_list,
                corp_code,
                start_s,
                end_s,
                page_no=page,
                page_count=100,
            )
        except Exception as exc:
            logger.debug("공시 목록 조회 실패 page=%s: %s", page, exc)
            break
        lst = data.get("list") or []
        for it in lst:
            title = _disclosure_title(it)
            if not title:
                continue
            if _DART_TITLE_BUY_HINT.search(title):
                buy_like += 1
            if _DART_TITLE_SELL_HINT.search(title):
                sell_like += 1
            if _DART_TITLE_MAJOR_HOLDER.search(title):
                major += 1
                if len(samples) < 5:
                    samples.append(title[:120])
        if len(lst) < 100:
            break

    bias = "중립"
    if buy_like + sell_like >= 2:
        if buy_like >= sell_like * 1.5:
            bias = "매수성_공시_다소_많음"
        elif sell_like >= buy_like * 1.5:
            bias = "매도성_공시_다소_많음"

    return {
        "window_days": _INSIDER_DISCLOSURE_DAYS,
        "buy_like_disclosure_titles": buy_like,
        "sell_like_disclosure_titles": sell_like,
        "major_holder_related_titles": major,
        "sample_titles": samples,
        "heuristic_bias": bias,
        "note": "공시 제목 패턴 휴리스틱이며 법적 매수·매도 판단이 아닙니다.",
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

        last_px = _last_close_price_krw(close)
        consensus_gap = await _peer_consensus_gap_proxy(
            code, dict(fundamentals) if fundamentals else None, last_px
        )
        corp_code = await _resolve_corp_code(code)
        if corp_code:
            earnings_proxy, insider_hints = await asyncio.gather(
                _annual_net_income_history_for_surprise_proxy(corp_code),
                _insider_disclosure_hints(corp_code),
            )
        else:
            earnings_proxy = {
                "annual_net_income": [],
                "yoy_acceleration_pp": None,
                "positive_yoy_streak_years": 0,
                "interpretation_note": "DART corp_code 없음 또는 API 키 미설정으로 실적 이력을 생략했습니다.",
            }
            insider_hints = {
                "window_days": _INSIDER_DISCLOSURE_DAYS,
                "buy_like_disclosure_titles": 0,
                "sell_like_disclosure_titles": 0,
                "major_holder_related_titles": 0,
                "sample_titles": [],
                "heuristic_bias": "중립",
                "note": "DART corp_code 없음 또는 API 키 미설정",
            }

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

        per_raw = fundamentals.get("per") if fundamentals else None
        pbr_raw = fundamentals.get("pbr") if fundamentals else None
        per_f: float | None = float(per_raw) if isinstance(per_raw, (int, float)) else None
        pbr_f: float | None = float(pbr_raw) if isinstance(pbr_raw, (int, float)) else None
        multifactor = _multifactor_scores(
            pi_total=pi_total,
            mom120=mom120,
            vol_ann=vol_ann,
            per=per_f,
            pbr=pbr_f,
            ey=ey,
        )
        mf_composite = multifactor["composite_0_100"]
        score += (mf_composite - 50.0) * 0.12

        blend_gap = consensus_gap.get("blended_gap_pct")
        if isinstance(blend_gap, (int, float)):
            if blend_gap > 15.0:
                score += 6.0
            elif blend_gap > 8.0:
                score += 3.0
            elif blend_gap < -18.0:
                score -= 5.0
            elif blend_gap < -10.0:
                score -= 2.5

        acc_pp = earnings_proxy.get("yoy_acceleration_pp")
        if isinstance(acc_pp, (int, float)):
            if acc_pp > 5.0:
                score += 5.0
            elif acc_pp > 2.0:
                score += 2.5
            elif acc_pp < -8.0:
                score -= 4.0

        b_dis = int(insider_hints.get("buy_like_disclosure_titles") or 0)
        s_dis = int(insider_hints.get("sell_like_disclosure_titles") or 0)
        if b_dis + s_dis >= 3:
            if b_dis >= s_dis * 1.5:
                score += 3.0
            elif s_dis >= b_dis * 1.5:
                score -= 2.5

        pq_notes: list[str] = []
        if dart_ok:
            pq_notes.append(f"Piotroski F-Score={pi_total}/9")
            if ey is not None:
                pq_notes.append(f"EBIT/EV(근사)={ey:.3f}")
            if roc is not None:
                pq_notes.append(f"EBIT/(NWC+PPE)(근사)={roc:.3f}")
        else:
            pq_notes.append("DART 재무 없음 — F-Score·매직포뮬러 제한")

        pq_notes.append(
            f"멀티팩터(가치·모멘텀·퀄·저변동) 복합≈{multifactor['composite_0_100']:.0f}/100"
        )

        if isinstance(blend_gap, (int, float)):
            pq_notes.append(f"동종밸류괴리(blended)≈{blend_gap:+.1f}% (PER/PBR 중앙값 근사)")
        acc_note = earnings_proxy.get("yoy_acceleration_pp")
        if isinstance(acc_note, (int, float)):
            pq_notes.append(f"순이익 YoY 가속도≈{acc_note:+.1f}pp")
        streak_n = earnings_proxy.get("positive_yoy_streak_years")
        if isinstance(streak_n, int) and streak_n >= 2:
            pq_notes.append(f"순이익 YoY 플러스 연속 {streak_n}년 힌트")
        if b_dis + s_dis >= 2:
            pq_notes.append(
                f"공시 제목 휴리스틱: 매수연계{b_dis} / 매도연계{s_dis} (자사주·주요주주)"
            )

        if fundamentals:
            rpp = fundamentals.get("roe_proxy_pct")
            if isinstance(rpp, (int, float)) and rpp > 0:
                pq_notes.append("ROE 프록시 양수(pykrx)")

        signals: dict[str, object] = {
            "piotroski_f_score": pi_total,
            "piotroski_criteria": pi_crit,
            "magic_formula": mf,
            "magic_formula_note": "전 종목 순위·복합점수는 배치 유니버스가 필요합니다.",
            "multifactor": multifactor,
            "multifactor_note": "단일 종목 가중 복합(0~100). 전종목 통합 순위는 유니버스 배치 시 산출.",
            "momentum_120d": mom120,
            "volatility_ann_60d": vol_ann,
            "fundamentals_available": bool(fundamentals),
            "dart_financials_available": dart_ok,
            "consensus_gap_proxy": consensus_gap,
            "earnings_surprise_proxy": earnings_proxy,
            "insider_disclosure_hints": insider_hints,
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

"""
재무·밸류에이션 관점 에이전트입니다.

1) pykrx 펀더멘털(BPS·PER·PBR·EPS·배당) 스냅샷 우선 사용
2) DART API 키가 있으면 최근 사업보고서에서 연결 재무제표를 추가 로드해
   영업이익률·부채비율·FCF·PEG·EV/EBITDA·ROIC·간이 DCF 등을 보강합니다.
"""

from __future__ import annotations

import asyncio
import logging
import math
from datetime import date, datetime, timedelta
from typing import Any

from backend.agents.base_agent import BaseAgent
from backend.agents.models import AgentResponse
from backend.utils.pykrx_silent import stock

logger = logging.getLogger(__name__)

# 밸류·DCF 휴리스틱 상수 (매직넘버 방지)
DEFAULT_WACC_HEURISTIC_PCT = 8.5
DEFAULT_TAX_RATE = 0.25
DCF_DISCOUNT_RATE = 0.09
DCF_NEAR_TERM_GROWTH = 0.02
DCF_TERMINAL_GROWTH = 0.03
DCF_EXPLICIT_YEARS = 5

# 이자부차입금 계정 매칭 (행 합산)
_DEBT_ACCOUNT_KEYWORDS = (
    "단기차입금",
    "장기차입금",
    "유동성장기부채",
    "유동성장기차입금",
    "사채",
)


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


# DART 재무제표 계정과목명 키워드 (연결·별도 모두 포함, 첫 매칭 행의 당기·전기)
_DART_ACCT_MAP = {
    # Altman Z(상장사 근사) — WC·RE 등
    "current_assets": ["유동자산"],
    "current_liabilities": ["유동부채"],
    "retained_earnings": ["미처분이익잉여금", "이익잉여금"],
    "operating_profit": ["영업이익"],
    "revenue": ["매출액", "수익(매출액)"],
    "operating_cf": ["영업활동으로인한현금흐름", "영업활동 현금흐름"],
    "capex": ["유형자산의취득", "유형자산취득"],
    "total_assets": ["자산총계"],
    "total_liabilities": ["부채총계"],
    "total_equity": ["자본총계"],
    "interest_expense": ["이자비용"],
    "net_income": ["당기순이익", "분기순이익"],
    "depreciation": ["감가상각비"],
    "cash_equiv": ["현금및현금성자산", "현금및예치금"],
    # Piotroski·매직포뮬러용 (퀀트 에이전트)
    "gross_profit": ["매출총이익"],
    "ppe_net": ["유형자산"],
}


def _match_account(label: str, candidates: list[str]) -> bool:
    """계정과목 라벨이 후보 키워드 중 하나와 일치(공백 제거 포함)하는지 확인합니다."""
    clean = label.replace(" ", "")
    return any(kw.replace(" ", "") in clean for kw in candidates)


def _parse_dart_row_amount(row: dict[str, Any], field: str) -> float | None:
    """DART 행에서 금액 필드를 안전하게 파싱합니다."""
    raw = row.get(field)
    if raw is None or raw == "":
        return None
    return _safe_float(str(raw).replace(",", ""))


def _sum_interest_bearing_debt(dart_rows: list[dict[str, Any]]) -> tuple[float | None, float | None]:
    """
    이자부 차입금 계정을 합산합니다 (당기·전기).

    Returns:
        (당기 합계, 전기 합계) — 매칭 행이 없으면 ``(None, None)``.
    """
    c_sum = 0.0
    p_sum = 0.0
    c_hit = False
    p_hit = False
    for row in dart_rows:
        label = str(row.get("account_nm") or "")
        if not any(_match_account(label, [kw]) for kw in _DEBT_ACCOUNT_KEYWORDS):
            continue
        vc = _parse_dart_row_amount(row, "thstrm_amount")
        vp = _parse_dart_row_amount(row, "frmtrm_amount")
        if vc is not None:
            c_sum += vc
            c_hit = True
        if vp is not None:
            p_sum += vp
            p_hit = True
    return (c_sum if c_hit else None, p_sum if p_hit else None)


def _parse_dart_financials(dart_rows: list[dict[str, Any]]) -> dict[str, float | None]:
    """
    DART fnlttSinglAcntAll 응답의 ``list`` 행들에서 핵심 지표를 추출합니다.

    단일 계정은 첫 매칭 행의 당기·전기(frmtrm)를 함께 채웁니다.
    """
    keys = list(_DART_ACCT_MAP.keys())
    result: dict[str, float | None] = {}
    for k in keys:
        result[k] = None
        result[f"{k}_prev"] = None

    for row in dart_rows:
        label = str(row.get("account_nm") or "")
        for key, keywords in _DART_ACCT_MAP.items():
            if result[key] is not None:
                continue
            if not _match_account(label, keywords):
                continue
            result[key] = _parse_dart_row_amount(row, "thstrm_amount")
            result[f"{key}_prev"] = _parse_dart_row_amount(row, "frmtrm_amount")
            break

    debt_c, debt_p = _sum_interest_bearing_debt(dart_rows)
    result["interest_bearing_debt"] = debt_c
    result["interest_bearing_debt_prev"] = debt_p

    return result


def _dcf_enterprise_value_simple(
    base_fcf: float,
    *,
    explicit_years: int = DCF_EXPLICIT_YEARS,
    discount: float = DCF_DISCOUNT_RATE,
    near_growth: float = DCF_NEAR_TERM_GROWTH,
    terminal_g: float = DCF_TERMINAL_GROWTH,
) -> float | None:
    """
    1단계 성장 + 고정 터미널 성장 모형으로 기업가치(근사)를 산출합니다.

    Args:
        base_fcf: 직전 연간 FCF(원). 양수일 때만 의미가 있습니다.
    """
    if base_fcf <= 0:
        return None
    if discount <= terminal_g:
        return None
    pv = 0.0
    fcf_t = base_fcf
    for t in range(1, explicit_years + 1):
        fcf_t = fcf_t * (1 + near_growth)
        pv += fcf_t / (1 + discount) ** t
    fcf_terminal = fcf_t * (1 + terminal_g)
    tv = fcf_terminal / (discount - terminal_g)
    pv += tv / (1 + discount) ** explicit_years
    return float(pv)


async def _lookup_market_cap_krw(ticker: str, basis_yyyymmdd: str, market: str) -> float | None:
    """
    특정 거래일 기준 시가총액(원)을 조회합니다.

    KRX 인증 미설정 등으로 실패하면 ``None`` 을 반환합니다.
    """
    try:
        from backend.data import krx_data
    except ImportError:
        return None
    try:
        d = datetime.strptime(basis_yyyymmdd, "%Y%m%d").date()
        df = await asyncio.to_thread(krx_data.fetch_market_cap_on_date, d, market=market)
    except Exception as exc:
        logger.debug("시가총액 조회 실패 ticker=%s: %s", ticker, exc)
        return None
    if df is None or df.empty:
        return None
    if ticker not in df.index.astype(str):
        return None
    row = df.loc[ticker]
    return _safe_float(row.get("시가총액"))


async def _lookup_dart_financials(ticker: str) -> tuple[dict[str, float | None], dict[str, str]]:
    """
    DART API로 최근 사업보고서(연결 우선 → 별도)에서 재무 데이터를 조회합니다.

    DART_API_KEY가 없거나 오류 발생 시 ``({}, {})`` 를 반환합니다.
    """
    meta: dict[str, str] = {}
    try:
        from backend.data import dart_data
    except ImportError:
        return {}, meta

    try:
        corp_code = await asyncio.to_thread(dart_data.find_corp_code, ticker)
    except Exception as exc:
        logger.debug("DART corp_code 조회 실패: %s %s", ticker, exc)
        return {}, meta

    if not corp_code:
        logger.debug("DART corp_code 없음: %s", ticker)
        return {}, meta

    for year_offset in range(0, 3):
        bsns_year = str(date.today().year - year_offset)
        for fs_div in ("CFS", "OFS"):
            try:
                raw = await asyncio.to_thread(
                    dart_data.fetch_financial_accounts,
                    corp_code,
                    bsns_year,
                    "11011",
                    fs_div=fs_div,
                )
                rows: list[dict[str, Any]] = raw.get("list") or []
                if rows:
                    parsed = _parse_dart_financials(rows)
                    parsed["dart_year"] = float(bsns_year)
                    meta["bsns_year"] = bsns_year
                    meta["fs_div"] = fs_div
                    return parsed, meta
            except Exception as exc:
                logger.debug("DART 재무 조회 실패 %s %s %s: %s", ticker, bsns_year, fs_div, exc)
    return {}, meta


async def fetch_dart_financial_snapshot(
    ticker: str,
) -> tuple[dict[str, float | None], dict[str, str]]:
    """
    DART 재무 스냅샷을 퀀트 등 다른 에이전트에서 재사용할 수 있도록 공개합니다.

    Args:
        ticker: 6자리 종목코드.

    Returns:
        ``_lookup_dart_financials`` 와 동일 형태.
    """
    return await _lookup_dart_financials(ticker)


class FinancialAgent(BaseAgent):
    """재무제표·밸류 관점 분석 에이전트."""

    def __init__(self, agent_name: str | None = "재무") -> None:
        super().__init__(agent_name=agent_name)

    async def analyze(self, ticker: str) -> AgentResponse:
        """
        펀더멘털 지표(pykrx + DART)를 바탕으로 의견과 스코어를 산출합니다.

        스코어는 대략 -50(비우량·고평가)~+50(우량·저평가) 범위 체감값입니다.
        """
        code = self.validate_ticker(ticker)

        fundamentals, _market = await _lookup_fundamentals(code)
        dart_fin, dart_meta = await _lookup_dart_financials(code)

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
        basis = str(fundamentals.get("basis_date") or "")
        mkt = str(fundamentals.get("market") or "KOSPI")

        mcap = await _lookup_market_cap_krw(code, basis, mkt) if basis else None
        if mcap is not None:
            fundamentals["market_cap_krw"] = mcap

        graham: float | None = None
        if eps and bps and eps > 0 and bps > 0:
            graham = math.sqrt(22.5 * eps * bps)

        score = 0.0
        notes: list[str] = []

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

        fundamentals["peg_ratio"] = None

        dart_signals: dict[str, Any] = {}
        if dart_meta.get("fs_div"):
            dart_signals["dart_fs_div"] = dart_meta["fs_div"]

        if dart_fin:
            rev = dart_fin.get("revenue")
            op = dart_fin.get("operating_profit")
            total_liabilities = dart_fin.get("total_liabilities")
            total_equity = dart_fin.get("total_equity")
            op_cf = dart_fin.get("operating_cf")
            capex_raw = dart_fin.get("capex")
            interest_exp = dart_fin.get("interest_expense")
            dart_year = dart_fin.get("dart_year")

            if dart_year:
                dart_signals["dart_bsns_year"] = int(dart_year)

            dep = dart_fin.get("depreciation")
            cash_e = dart_fin.get("cash_equiv")
            debt = dart_fin.get("interest_bearing_debt")
            if dep is not None and op is not None:
                ebitda = op + dep
            elif op is not None:
                ebitda = op
            else:
                ebitda = None
            if ebitda is not None:
                dart_signals["ebitda_approx"] = ebitda

            rev_prev = dart_fin.get("revenue_prev")
            op_prev = dart_fin.get("operating_profit_prev")

            if rev and op is not None and rev != 0:
                opm = op / rev * 100
                dart_signals["operating_margin_pct"] = round(opm, 2)
                if opm >= 10:
                    notes.append(f"영업이익률 {opm:.1f}%(양호)")
                    score += 6
                elif opm < 0:
                    notes.append(f"영업이익 적자({opm:.1f}%)")
                    score -= 8

            if (
                rev_prev
                and op_prev is not None
                and rev_prev != 0
                and rev
                and op is not None
            ):
                opm_prev = op_prev / rev_prev * 100
                dart_signals["operating_margin_prev_pct"] = round(opm_prev, 2)
                opm_curr = op / rev * 100
                delta = opm_curr - opm_prev
                dart_signals["operating_margin_yoy_delta_pctp"] = round(delta, 2)
                if delta >= 1.0:
                    notes.append("영업이익률 전년 대비 개선")
                    score += 4
                elif delta <= -1.0:
                    notes.append("영업이익률 전년 대비 악화")
                    score -= 4

            if total_liabilities is not None and total_equity and total_equity != 0:
                debt_ratio = total_liabilities / total_equity * 100
                dart_signals["debt_to_equity_pct"] = round(debt_ratio, 1)
                if debt_ratio > 200:
                    notes.append(f"부채비율 {debt_ratio:.0f}%(재무 부담)")
                    score -= 10
                elif debt_ratio < 80:
                    notes.append(f"부채비율 {debt_ratio:.0f}%(건전)")
                    score += 5

            fcf: float | None = None
            if op_cf is not None and capex_raw is not None:
                capex = abs(capex_raw)
                fcf = op_cf - capex
                dart_signals["fcf"] = fcf
                if rev and rev > 0:
                    fcf_margin = fcf / rev * 100
                    dart_signals["fcf_margin_pct"] = round(fcf_margin, 2)
                    if fcf_margin >= 5:
                        notes.append(f"FCF 마진 {fcf_margin:.1f}%(양호)")
                        score += 6
                    elif fcf < 0:
                        notes.append("FCF 음수(잉여현금 부재)")
                        score -= 5

            if op is not None and interest_exp and interest_exp > 0:
                icr = op / interest_exp
                dart_signals["interest_coverage_ratio"] = round(icr, 2)
                if icr < 1.5:
                    notes.append(f"이자보상배율 {icr:.1f}(위험)")
                    score -= 8
                elif icr >= 5:
                    notes.append(f"이자보상배율 {icr:.1f}(안정)")
                    score += 4

            ni = dart_fin.get("net_income")
            ni_prev = dart_fin.get("net_income_prev")
            if (
                per is not None
                and per > 0
                and ni is not None
                and ni_prev is not None
                and ni_prev > 0
                and ni > 0
            ):
                ni_growth_pct = (ni / ni_prev - 1.0) * 100.0
                dart_signals["net_income_yoy_growth_pct"] = round(ni_growth_pct, 2)
                if ni_growth_pct > 0.5:
                    peg = per / ni_growth_pct
                    fundamentals["peg_ratio"] = round(peg, 3)
                    if peg < 1.0:
                        notes.append(f"PEG<1 (성장 대비 PER 완만, 근사)")
                        score += 6
                    elif peg > 2.0:
                        notes.append(f"PEG>2 (성장 대비 PER 부담, 근사)")
                        score -= 4

            debt_v = debt if debt is not None else 0.0
            cash_v = cash_e if cash_e is not None else 0.0
            net_debt = debt_v - cash_v
            if mcap and mcap > 0:
                ev = mcap + net_debt
                dart_signals["enterprise_value_approx_krw"] = ev
                if ebitda is not None and ebitda > 0:
                    ev_ebitda = ev / ebitda
                    dart_signals["ev_to_ebitda_approx"] = round(ev_ebitda, 2)
                    if ev_ebitda < 8.0:
                        notes.append(f"EV/EBITDA(근사) {ev_ebitda:.1f}(상대적으로 낮음)")
                        score += 4
                    elif ev_ebitda > 18.0:
                        notes.append(f"EV/EBITDA(근사) {ev_ebitda:.1f}(높음)")
                        score -= 4
                if fcf is not None:
                    fcf_y = fcf / mcap * 100.0
                    dart_signals["fcf_yield_pct"] = round(fcf_y, 2)
                    if fcf > 0 and fcf_y >= 5.0:
                        notes.append(f"FCF Yield(근사) {fcf_y:.1f}%")
                        score += 5

            if op is not None and total_equity is not None:
                nopat = op * (1.0 - DEFAULT_TAX_RATE)
                ic = total_equity + debt_v - cash_v
                if ic > 0:
                    roic_pct = nopat / ic * 100.0
                    dart_signals["roic_approx_pct"] = round(roic_pct, 2)
                    spread = roic_pct - DEFAULT_WACC_HEURISTIC_PCT
                    dart_signals["roic_minus_wacc_heuristic_pctp"] = round(spread, 2)
                    if spread >= 3.0:
                        notes.append(
                            f"ROIC(근사) {roic_pct:.1f}% > WACC 가정 {DEFAULT_WACC_HEURISTIC_PCT}%"
                        )
                        score += 5
                    elif spread <= -3.0:
                        notes.append("ROIC(근사)가 자본비용 가정보다 낮음")
                        score -= 5

            if fcf is not None:
                dcf_ev = _dcf_enterprise_value_simple(fcf)
                if dcf_ev is not None:
                    dart_signals["dcf_enterprise_value_simple_krw"] = round(dcf_ev, 0)
                    ev_for_cmp = dart_signals.get("enterprise_value_approx_krw")
                    if isinstance(ev_for_cmp, (int, float)) and ev_for_cmp > 0:
                        upside = (dcf_ev / float(ev_for_cmp) - 1.0) * 100.0
                        dart_signals["dcf_vs_ev_upside_pct_approx"] = round(upside, 1)
                        if upside >= 10.0:
                            notes.append("간이 DCF 기업가치가 시장 EV(근사) 대비 여유")
                            score += 4
                        elif upside <= -15.0:
                            notes.append("간이 DCF 기업가치가 시장 EV(근사) 대비 낮게 나옴")
                            score -= 3

            fundamentals["dart"] = dart_signals

        opinion = "중립"
        if score >= 15:
            opinion = "매수"
        elif score <= -15:
            opinion = "매도"

        reasoning = "; ".join(notes) if notes else "펀더멘털 균형 구간으로 해석"
        if graham:
            fundamentals["graham_number_approx"] = graham
            reasoning += f"; 그레이엄 수(근사)≈{graham:,.0f}"
        if dart_signals:
            reasoning += " [DART 재무 반영]"

        confidence = 0.72 if dart_signals else (0.62 if fundamentals else 0.45)
        return self.build_response(
            opinion=opinion,
            confidence=min(0.85, confidence),
            score=float(max(-50.0, min(50.0, score))),
            reasoning=reasoning,
            signals=fundamentals,
        )
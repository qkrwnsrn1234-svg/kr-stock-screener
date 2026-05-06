"""
재무·밸류에이션 관점 에이전트입니다.

1) pykrx 펀더멘털(BPS·PER·PBR·EPS·배당) 스냅샷 우선 사용
2) DART API 키가 있으면 최근 사업보고서에서 연결 재무제표를 추가 로드해
   영업이익률·부채비율·FCF를 보강합니다.
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


# DART 재무제표 계정과목명 키워드 (연결·별도 모두 포함)
_DART_ACCT_MAP = {
    "operating_profit": ["영업이익"],
    "revenue": ["매출액", "수익(매출액)"],
    "operating_cf": ["영업활동으로인한현금흐름", "영업활동 현금흐름"],
    "capex": ["유형자산의취득", "유형자산취득"],
    "total_assets": ["자산총계"],
    "total_liabilities": ["부채총계"],
    "total_equity": ["자본총계"],
    "interest_expense": ["이자비용"],
}


def _match_account(label: str, candidates: list[str]) -> bool:
    """계정과목 라벨이 후보 키워드 중 하나와 일치(공백 제거 포함)하는지 확인합니다."""
    clean = label.replace(" ", "")
    return any(kw.replace(" ", "") in clean for kw in candidates)


def _parse_dart_financials(dart_rows: list[dict[str, Any]]) -> dict[str, float | None]:
    """
    DART fnlttSinglAcntAll 응답의 ``list`` 행들에서 핵심 지표를 추출합니다.

    당기(thstrm_amount)를 우선 사용합니다.
    """
    result: dict[str, float | None] = {k: None for k in _DART_ACCT_MAP}
    for row in dart_rows:
        label = str(row.get("account_nm") or "")
        raw_val = row.get("thstrm_amount") or row.get("frmtrm_amount")
        if raw_val is None:
            continue
        val = _safe_float(str(raw_val).replace(",", ""))
        for key, keywords in _DART_ACCT_MAP.items():
            if result[key] is None and _match_account(label, keywords):
                result[key] = val
    return result


async def _lookup_dart_financials(ticker: str) -> dict[str, float | None]:
    """
    DART API로 최근 사업보고서(연결 우선 → 별도)에서 재무 데이터를 조회합니다.

    DART_API_KEY가 없거나 오류 발생 시 빈 딕셔너리를 반환합니다.
    """
    try:
        from backend.data import dart_data
    except ImportError:
        return {}

    try:
        corp_code = await asyncio.to_thread(dart_data.find_corp_code, ticker)
    except Exception as exc:
        logger.debug("DART corp_code 조회 실패: %s %s", ticker, exc)
        return {}

    if not corp_code:
        logger.debug("DART corp_code 없음: %s", ticker)
        return {}

    # 올해 또는 작년 사업보고서(11011) 시도
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
                    parsed["dart_fs_div"] = None  # float 타입 제약을 피해 별도 저장
                    # 문자열 필드는 float 타입 딕셔너리에 넣을 수 없으므로 제외하고
                    # 별도로 반환하지 않습니다 (signals에서 직접 처리)
                    return parsed
            except Exception as exc:
                logger.debug("DART 재무 조회 실패 %s %s %s: %s", ticker, bsns_year, fs_div, exc)
    return {}


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

        # pykrx 펀더멘털과 DART 재무를 병렬로 조회합니다
        fundamentals, _market = await _lookup_fundamentals(code)
        dart_fin = await _lookup_dart_financials(code)

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

        # PEG: 성장률 데이터 미연동 상태에서는 생략
        fundamentals["peg_ratio"] = None

        # ── DART 재무 보강 ──────────────────────────────────────────
        dart_signals: dict[str, Any] = {}
        if dart_fin:
            rev = dart_fin.get("revenue")
            op = dart_fin.get("operating_profit")
            total_assets = dart_fin.get("total_assets")
            total_liabilities = dart_fin.get("total_liabilities")
            total_equity = dart_fin.get("total_equity")
            op_cf = dart_fin.get("operating_cf")
            capex_raw = dart_fin.get("capex")
            interest_exp = dart_fin.get("interest_expense")
            dart_year = dart_fin.get("dart_year")

            if dart_year:
                dart_signals["dart_bsns_year"] = int(dart_year)

            # 영업이익률
            if rev and op is not None and rev != 0:
                opm = op / rev * 100
                dart_signals["operating_margin_pct"] = round(opm, 2)
                if opm >= 10:
                    notes.append(f"영업이익률 {opm:.1f}%(양호)")
                    score += 6
                elif opm < 0:
                    notes.append(f"영업이익 적자({opm:.1f}%)")
                    score -= 8

            # 부채비율
            if total_liabilities is not None and total_equity and total_equity != 0:
                debt_ratio = total_liabilities / total_equity * 100
                dart_signals["debt_to_equity_pct"] = round(debt_ratio, 1)
                if debt_ratio > 200:
                    notes.append(f"부채비율 {debt_ratio:.0f}%(재무 부담)")
                    score -= 10
                elif debt_ratio < 80:
                    notes.append(f"부채비율 {debt_ratio:.0f}%(건전)")
                    score += 5

            # FCF = 영업CF - CAPEX
            if op_cf is not None and capex_raw is not None:
                capex = abs(capex_raw)  # DART는 음수로 기재하는 경우 있음
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

            # 이자보상배율 = 영업이익 / 이자비용
            if op is not None and interest_exp and interest_exp > 0:
                icr = op / interest_exp
                dart_signals["interest_coverage_ratio"] = round(icr, 2)
                if icr < 1.5:
                    notes.append(f"이자보상배율 {icr:.1f}(위험)")
                    score -= 8
                elif icr >= 5:
                    notes.append(f"이자보상배율 {icr:.1f}(안정)")
                    score += 4

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

        # DART 데이터가 있으면 신뢰도를 소폭 상향합니다
        confidence = 0.72 if dart_signals else (0.62 if fundamentals else 0.45)
        return self.build_response(
            opinion=opinion,
            confidence=min(0.85, confidence),
            score=float(max(-50.0, min(50.0, score))),
            reasoning=reasoning,
            signals=fundamentals,
        )

"""
리스크·하방 시나리오·변동성 중심 에이전트입니다.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime, timedelta
from typing import Any

import numpy as np
import pandas as pd
from pykrx import stock

from . import technical_indicators as ti
from backend.agents.base_agent import BaseAgent
from backend.agents.financial_agent import (
    _lookup_dart_financials,
    _lookup_fundamentals,
    _lookup_market_cap_krw,
)
from backend.agents.io_async import fetch_equity_ohlcv_async, fetch_index_ohlcv_async
from backend.agents.models import AgentResponse

logger = logging.getLogger(__name__)

# Altman Z (상장 제조업 기준식 근사) — 계정 단위가 일치한다는 전제 하 비율 항은 무차원
ALTMAN_DISTRESS_MAX = 1.81
ALTMAN_SAFE_MIN = 2.99


def _beta_vs_benchmark(stock_close: pd.Series, bench_close: pd.Series, window: int = 120) -> float | None:
    """단순 회귀 기반 베타 근사값을 계산합니다."""
    aligned = pd.concat([stock_close.rename("s"), bench_close.rename("b")], axis=1).dropna()
    if len(aligned) < window + 2:
        return None
    sub = aligned.iloc[-window:]
    rs = np.log(sub["s"]).diff().dropna()
    rb = np.log(sub["b"]).diff().dropna()
    common = rs.align(rb, join="inner")
    x = common[0].to_numpy()
    y = common[1].to_numpy()
    if len(x) < 10:
        return None
    cov = np.cov(x, y, ddof=0)[0, 1]
    var = np.var(y)
    if var == 0:
        return None
    return float(cov / var)


def _altman_z_public(
    *,
    working_capital: float | None,
    retained_earnings: float | None,
    ebit: float | None,
    total_assets: float | None,
    sales: float | None,
    total_liabilities: float | None,
    market_cap_krw: float | None,
) -> dict[str, Any]:
    """
    Altman Z-Score(상장사용 근사)를 계산합니다.

    Z = 1.2*WC/TA + 1.4*RE/TA + 3.3*EBIT/TA + 0.6*MVE/TL + 1.0*S/TA

    Returns:
        z 값, 구간 레이블, 사용한 입력 요약
    """
    out: dict[str, Any] = {
        "z_score": None,
        "zone": "데이터부족",
        "components_note": "",
    }
    if total_assets is None or total_assets <= 0:
        return out

    wc = working_capital or 0.0
    re = retained_earnings or 0.0
    eb = ebit or 0.0
    s = sales or 0.0
    ta = total_assets

    x1 = 1.2 * (wc / ta)
    x2 = 1.4 * (re / ta)
    x3 = 3.3 * (eb / ta)
    x5 = 1.0 * (s / ta)

    x4 = 0.0
    if total_liabilities is not None and total_liabilities > 0 and market_cap_krw is not None and market_cap_krw > 0:
        x4 = 0.6 * (market_cap_krw / total_liabilities)
    else:
        out["components_note"] = "X4(MVE/TL) 미산출 — 부채·시총 부족"

    z = x1 + x2 + x3 + x4 + x5
    out["z_score"] = round(float(z), 4)
    out["x_parts"] = {
        "x1_wc_ta": round(x1, 4),
        "x2_re_ta": round(x2, 4),
        "x3_ebit_ta": round(x3, 4),
        "x4_mve_tl": round(x4, 4),
        "x5_sales_ta": round(x5, 4),
    }

    if z < ALTMAN_DISTRESS_MAX:
        out["zone"] = "위험"
    elif z < ALTMAN_SAFE_MIN:
        out["zone"] = "주의"
    else:
        out["zone"] = "상대안전"
    return out


def _position_cap_hint(vol_ann: float | None, z_val: float | None) -> str:
    """변동성·Altman Z를 반영한 단일 종목 비중 상한 휴리스틱 문장을 만듭니다."""
    cap = 22.0
    if vol_ann is not None:
        if vol_ann > 0.38:
            cap -= 10
        elif vol_ann > 0.28:
            cap -= 5
    if z_val is not None:
        if z_val < ALTMAN_DISTRESS_MAX:
            cap -= 8
        elif z_val < ALTMAN_SAFE_MIN:
            cap -= 4
    cap = max(4.0, cap)
    return f"휴리스틱 기준 단일 종목 노출은 순자산 대비 약 {cap:.0f}% 미만을 검토(보수적)"


def _drawdown_scenarios_struct(
    *,
    vol_ann: float | None,
    mdd: float | None,
    beta: float | None,
    rng_pct: float,
) -> dict[str, Any]:
    """하방 스트레스를 3단계(경·중·중증)로 수치화해 담습니다."""
    v = float(vol_ann or 0.22)
    b = float(beta or 1.0)
    mild = min(0.12, v * 0.35 * b)
    moderate = min(0.28, v * 0.65 * b)
    severe = min(0.55, abs(float(mdd or -0.25)) * 0.55 + v * 0.5 * b)
    return {
        "mild_frac_drop_hint": round(mild, 4),
        "moderate_frac_drop_hint": round(moderate, 4),
        "severe_frac_drop_hint": round(severe, 4),
        "range_chart_pct": round(rng_pct, 4),
        "summary_ko": (
            f"경미~중증 하방 시나리오(과거 변동성·베타·MDD 휴리스틱): "
            f"약 {mild*100:.1f}% / {moderate*100:.1f}% / {severe*100:.1f}% 수준 참고"
        ),
    }


async def _shorting_snapshot(ticker: str) -> dict[str, object]:
    """최근 거래일 근처 공매도 현황 스냅샷을 조회합니다."""
    for back in range(1, 10):
        d = date.today() - timedelta(days=back)
        if d.weekday() >= 5:
            continue
        ds = d.strftime("%Y%m%d")
        try:
            df = await asyncio.to_thread(stock.get_shorting_status_by_date, ds, ds, ticker)
        except Exception as exc:
            logger.debug("공매도 조회 예외 무시: %s %s", ds, exc)
            continue
        if df is None or df.empty:
            continue
        return {"basis_date": ds, "rows": df.tail(3).to_dict(orient="records")}
    return {}


async def _listed_shares_and_market(
    code: str,
    basis_yyyymmdd: str,
    market_guess: str | None,
) -> tuple[int | None, str | None]:
    """기준일 시총 스냅샷에서 상장주식수·시장을 찾습니다."""
    try:
        from backend.data import krx_data
    except ImportError:
        return None, None
    try:
        d = datetime.strptime(basis_yyyymmdd, "%Y%m%d").date()
    except ValueError:
        return None, None

    order: list[str] = []
    if market_guess in ("KOSPI", "KOSDAQ"):
        order.append(market_guess)
    for m in ("KOSPI", "KOSDAQ"):
        if m not in order:
            order.append(m)

    for mkt in order:
        try:
            df = await asyncio.to_thread(krx_data.fetch_market_cap_on_date, d, market=mkt)
            if code in df.index.astype(str):
                row = df.loc[code]
                sh = row.get("상장주식수")
                if sh is not None and int(sh) > 0:
                    return int(sh), mkt
        except Exception as exc:
            logger.debug("상장주식수 조회 실패 %s %s: %s", code, mkt, exc)
    return None, None


async def _shorting_enriched(
    code: str,
    *,
    market: str | None,
    basis_fund_yyyymmdd: str | None,
    rng_pct: float,
) -> dict[str, Any]:
    """공매도 잔고·상장주식수로 잔고 비율·쇼트 스퀴즈 힌트를 만듭니다."""
    base = await _shorting_snapshot(code)
    out: dict[str, Any] = dict(base)
    out["balance_to_float_ratio"] = None
    out["squeeze_risk_hint"] = "판단불가"

    rows = base.get("rows")
    if not isinstance(rows, list) or not rows:
        return out

    last = rows[-1]
    bal_raw = last.get("잔고수량")
    try:
        bal = int(bal_raw) if bal_raw is not None else 0
    except (TypeError, ValueError):
        bal = 0

    ds = str(base.get("basis_date") or "") or basis_fund_yyyymmdd or ""
    if not ds or bal <= 0:
        return out

    listed, mkt_used = await _listed_shares_and_market(code, ds, market)
    if not listed:
        return out

    ratio = bal / float(listed)
    out["balance_to_float_ratio"] = round(ratio, 6)
    out["listed_shares_basis"] = listed
    out["short_market_used"] = mkt_used

    if ratio >= 0.12:
        out["squeeze_risk_hint"] = "공매도 잔고 비중 높음 — 급등 시 롤업(스퀴즈) 가능성 상대적으로 큼"
        if rng_pct >= 0.75:
            out["squeeze_risk_hint"] += " / 고점 근처·갭 리스크"
    elif ratio >= 0.05:
        out["squeeze_risk_hint"] = "공매도 잔고 존재 — 변동성·뉴스에 민감할 수 있음"
    else:
        out["squeeze_risk_hint"] = "공매도 잔고 비중 상대적으로 낮음"

    return out


class RiskAgent(BaseAgent):
    """리스크 매니저 에이전트."""

    def __init__(self, agent_name: str | None = "리스크") -> None:
        super().__init__(agent_name=agent_name)

    async def analyze(self, ticker: str) -> AgentResponse:
        """가격·펀더멘털·DART·공매도를 종합한 리스크 의견을 냅니다."""
        code = self.validate_ticker(ticker)

        df_s, df_b, fundamentals, dart_fin, dart_meta = await asyncio.gather(
            fetch_equity_ohlcv_async(code),
            fetch_index_ohlcv_async("KS11"),
            _lookup_fundamentals(code),
            _lookup_dart_financials(code),
        )

        close_s, _vol = ti._ensure_close_volume(df_s)
        bench_close = df_b["Close"] if "Close" in df_b.columns else df_b["close"]

        close_s.index = pd.to_datetime(close_s.index).normalize()
        bench_close.index = pd.to_datetime(bench_close.index).normalize()

        vol_ann = ti.realized_volatility(close_s, window=60)
        mdd = ti.max_drawdown(close_s)

        window = min(252, len(close_s))
        recent = close_s.iloc[-window:]
        hi = float(recent.max())
        lo = float(recent.min())
        last = float(close_s.iloc[-1])
        rng_pct = (last - lo) / (hi - lo) if hi != lo else 0.5

        beta = _beta_vs_benchmark(close_s, bench_close, window=120)

        mkt = str(fundamentals.get("market") or "") if fundamentals else ""
        basis = str(fundamentals.get("basis_date") or "") if fundamentals else ""

        mcap: float | None = None
        if fundamentals and basis and mkt in ("KOSPI", "KOSDAQ"):
            mcap = await _lookup_market_cap_krw(code, basis, mkt)

        ca = dart_fin.get("current_assets") if dart_fin else None
        cl = dart_fin.get("current_liabilities") if dart_fin else None
        re = dart_fin.get("retained_earnings") if dart_fin else None
        ebit = dart_fin.get("operating_profit") if dart_fin else None
        ta = dart_fin.get("total_assets") if dart_fin else None
        tl = dart_fin.get("total_liabilities") if dart_fin else None
        sales = dart_fin.get("revenue") if dart_fin else None

        wc: float | None = None
        if ca is not None and cl is not None:
            wc = float(ca) - float(cl)

        altman = _altman_z_public(
            working_capital=wc,
            retained_earnings=float(re) if re is not None else None,
            ebit=float(ebit) if ebit is not None else None,
            total_assets=float(ta) if ta is not None else None,
            sales=float(sales) if sales is not None else None,
            total_liabilities=float(tl) if tl is not None else None,
            market_cap_krw=mcap,
        )

        short_enriched = await _shorting_enriched(
            code,
            market=mkt if mkt else None,
            basis_fund_yyyymmdd=basis if basis else None,
            rng_pct=rng_pct,
        )

        scenarios = _drawdown_scenarios_struct(
            vol_ann=vol_ann,
            mdd=mdd,
            beta=beta,
            rng_pct=rng_pct,
        )

        z_val = altman.get("z_score")
        z_float: float | None = float(z_val) if isinstance(z_val, (int, float)) else None

        signals: dict[str, object] = {
            "volatility_ann_60d": vol_ann,
            "max_drawdown_frac": mdd,
            "range_position_52w_proxy": rng_pct,
            "beta_vs_kospi_approx": beta,
            "shorting": short_enriched,
            "altman_z": altman,
            "drawdown_scenarios": scenarios,
            "position_sizing_hint": _position_cap_hint(vol_ann, z_float),
        }

        if dart_meta.get("bsns_year"):
            signals["dart_bsns_year"] = dart_meta["bsns_year"]
            signals["dart_fs_div"] = dart_meta.get("fs_div")

        score = 0.0
        notes: list[str] = []

        if vol_ann is not None:
            notes.append(f"연율화 변동성 약 {vol_ann*100:.1f}%")
            if vol_ann > 0.35:
                score -= 18
            elif vol_ann > 0.28:
                score -= 10

        if mdd is not None:
            notes.append(f"전 구간 최대낙폭 약 {abs(mdd)*100:.1f}%")
            if abs(mdd) > 0.45:
                score -= 12

        if rng_pct >= 0.85:
            notes.append("52주 고저 대비 상단 근접")
            score -= 8
        elif rng_pct <= 0.15:
            notes.append("52주 고저 대비 하단 근접")
            score += 4

        if beta is not None:
            notes.append(f"베타(KOSPI 대비 근사)≈{beta:.2f}")
            if beta > 1.3:
                score -= 8

        if z_float is not None:
            notes.append(f"Altman Z≈{z_float:.2f}({altman.get('zone')})")
            if z_float < ALTMAN_DISTRESS_MAX:
                score -= 14
            elif z_float < ALTMAN_SAFE_MIN:
                score -= 6
            elif z_float >= ALTMAN_SAFE_MIN:
                score += 5

        ratio = short_enriched.get("balance_to_float_ratio")
        if isinstance(ratio, (int, float)):
            notes.append(f"공매도 잔고/유통주식(상장) 비율≈{float(ratio)*100:.2f}%")
            if ratio >= 0.10:
                score -= 10
            elif ratio >= 0.05:
                score -= 5

        severity = "약함"
        if score <= -28:
            severity = "강함"
        elif score <= -14:
            severity = "중간"
        signals["drawdown_scenario_hint"] = severity

        opinion = "중립"
        if score <= -20:
            opinion = "매도"
        elif score >= 15:
            opinion = "매수"

        reasoning = "; ".join(notes) if notes else "상태 정보 부족"

        return self.build_response(
            opinion=opinion,
            confidence=0.60 if dart_fin else 0.55,
            score=float(max(-50.0, min(50.0, score))),
            reasoning=reasoning,
            signals=signals,
        )

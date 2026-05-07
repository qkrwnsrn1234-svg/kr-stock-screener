"""
상장 목록 업종(Dept) 문자열에 대응하는 대표 ETF의 순매수·거래량 프록시입니다.

KRX 순매수는 환경(``KRX_ID``/``KRX_PW``)에 따라 실패할 수 있으며, 그 경우 거래량만 표시합니다.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import date, timedelta
from typing import Any

import pandas as pd

from backend.agents import technical_indicators as ti
from backend.agents.io_async import fetch_equity_ohlcv_async
from backend.data import krx_data

logger = logging.getLogger(__name__)

# (Dept 부분 일치 키워드, ETF 6자리, 한글 표시명) —_order matters (먼저 매칭 우선)
DEPT_ETF_PROXIES: tuple[tuple[str, str, str], ...] = (
    ("반도체", "091160", "KODEX 반도체"),
    ("전기·전자", "091160", "KODEX 반도체"),
    ("금융업", "091170", "KODEX 은행"),
    ("은행", "091170", "KODEX 은행"),
    ("증권", "225060", "TIGER 200 증권"),
    ("자동차", "091180", "KODEX 자동차"),
    ("운수장비", "091180", "KODEX 자동차"),
    ("바이오", "244580", "KODEX 바이오"),
    ("제약", "244580", "KODEX 바이오"),
    ("건설", "102960", "TIGER 200 건설"),
    ("화학", "117460", "TIGER 200 화학"),
    ("철강", "138520", "KODEX 철강"),
    ("유통", "266370", "KODEX 경기소비재"),
    ("음식료", "266370", "KODEX 경기소비재"),
)


def match_sector_etf(dept: str) -> tuple[str, str] | None:
    """업종 문자열에 맞는 대표 ETF(코드, 라벨)를 돌려줍니다."""
    for key, code, label in DEPT_ETF_PROXIES:
        if key in dept:
            return code, label
    return None


def _row_net_buy_krw(row: pd.Series) -> float | None:
    """순매수 거래대금 성격의 숫자 열을 찾아 합산 근사값을 씁니다."""
    total = 0.0
    found = False
    for col, val in row.items():
        c = str(col)
        if "순매수" not in c:
            continue
        if "거래대금" not in c and "금액" not in c:
            continue
        try:
            total += float(val)
            found = True
        except (TypeError, ValueError):
            continue
    return total if found else None


def _fmt_money_krw(x: float) -> str:
    """표시용 문자열(억/백만 원)."""
    if abs(x) >= 1e8:
        return f"{x / 1e8:+.1f}억 원"
    return f"{x / 1e6:+.0f}백만 원"


async def _sum_foreign_institution_netbuy(etf_code: str, calendar_days: int = 14) -> float | None:
    """외국인·기관 순매수(거래대금) 합계 근사."""
    end = date.today()
    start = end - timedelta(days=calendar_days)
    sym = etf_code.zfill(6)
    grand = 0.0
    any_hit = False
    for investor in ("외국인", "기관합계"):
        try:
            df = await asyncio.to_thread(
                krx_data.fetch_net_purchases_by_ticker,
                start,
                end,
                market="KOSPI",
                investor=investor,
            )
        except Exception as exc:
            logger.debug("섹터 ETF 순매수 조회 생략(%s %s): %s", sym, investor, exc)
            continue
        if df is None or df.empty:
            continue
        idx = df.index.astype(str).str.zfill(6)
        df = df.copy()
        df.index = idx
        if sym not in df.index:
            continue
        v = _row_net_buy_krw(df.loc[sym])
        if v is not None:
            grand += v
            any_hit = True
    return grand if any_hit else None


async def _volume_ratio_ma20(etf_code: str) -> float | None:
    """최근 거래량 / 20일 평균."""
    try:
        df = await fetch_equity_ohlcv_async(etf_code)
        _c, vol = ti._ensure_close_volume(df)
        if len(vol) < 21:
            return None
        ma20 = float(vol.iloc[-20:].mean())
        last = float(vol.iloc[-1])
        return last / ma20 if ma20 > 0 else None
    except Exception as exc:
        logger.debug("ETF 거래량 비율 실패 %s: %s", etf_code, exc)
        return None


async def etf_flow_extras_for_dept(dept: str) -> dict[str, Any]:
    """
    HotSectorItem에 넣을 ETF 관련 필드를 만듭니다.

    Args:
        dept: 상장 목록 ``Dept`` 문자열.

    Returns:
        ``etf_proxy_code``, ``etf_proxy_label``, ``etf_flow_summary`` 키.
    """
    base: dict[str, Any] = {
        "etf_proxy_code": None,
        "etf_proxy_label": None,
        "etf_flow_summary": None,
        "etf_foreign_inst_netbuy_krw_sum": None,
        "etf_volume_ratio_vs_ma20": None,
    }
    matched = match_sector_etf(dept)
    if not matched:
        return base
    code, label = matched
    base["etf_proxy_code"] = code
    base["etf_proxy_label"] = label

    pieces: list[str] = []
    net = await _sum_foreign_institution_netbuy(code)
    base["etf_foreign_inst_netbuy_krw_sum"] = net
    if net is not None:
        pieces.append(f"최근 구간 외국인+기관 순매수 합 {_fmt_money_krw(net)}")
    vr = await _volume_ratio_ma20(code)
    base["etf_volume_ratio_vs_ma20"] = vr
    if vr is not None:
        pieces.append(f"거래량 20일 평균 대비 {vr:.2f}배")

    if pieces:
        base["etf_flow_summary"] = f"{label}({code}): " + "; ".join(pieces)
    else:
        base["etf_flow_summary"] = (
            f"{label}({code}): 순매수·거래량 데이터 없음(KRX 제한·네트워크 등)"
        )
    return base

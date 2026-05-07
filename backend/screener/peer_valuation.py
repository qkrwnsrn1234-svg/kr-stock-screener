"""
같은 상장 목록 업종(Dept) 동종의 PER·PBR 중앙값(스크리닝 상대 밸류용)을 조회합니다.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

import numpy as np
import pandas as pd
from backend.utils.pykrx_silent import stock

from backend.agents.financial_agent import _lookup_fundamentals
from backend.data import finance_data

logger = logging.getLogger(__name__)

# 상대 밸류 신뢰를 위한 동종 최소 표본(미만이면 중앙값 비교 생략)
MIN_PEERS_FOR_RELATIVE = 5


@dataclass(frozen=True)
class SectorPeerStats:
    """업종 동종 펀더멘털 요약입니다."""

    median_per: float | None
    median_pbr: float | None
    peer_count: int
    sector_label: str | None


async def fetch_sector_peer_stats(ticker: str) -> SectorPeerStats:
    """
    종목이 속한 Dept(상장목록) 기준 동종 종목들의 PER/PBR 중앙값을 계산합니다.

    Args:
        ticker: 6자리 종목코드.

    Returns:
        중앙값과 표본 수. 데이터 부족 시 필드는 ``None``/0.
    """
    code = str(ticker).strip().zfill(6)
    fund, market = await _lookup_fundamentals(code)
    if not fund or not market:
        return SectorPeerStats(None, None, 0, None)

    ds = str(fund.get("basis_date") or "")
    if len(ds) != 8:
        return SectorPeerStats(None, None, 0, None)

    try:
        df = await asyncio.to_thread(stock.get_market_fundamental_by_ticker, ds, market)
    except Exception as exc:
        logger.warning("동종 펀더멘털 조회 실패: %s", exc)
        return SectorPeerStats(None, None, 0, None)

    if df is None or df.empty:
        return SectorPeerStats(None, None, 0, None)

    df = df.copy()
    df.index = df.index.astype(str).str.zfill(6)

    try:
        listing = await asyncio.to_thread(finance_data.list_krx_symbols, None)
    except Exception as exc:
        logger.warning("상장 목록 조회 실패: %s", exc)
        return SectorPeerStats(None, None, 0, None)

    if listing is None or listing.empty or "Dept" not in listing.columns or "Code" not in listing.columns:
        return SectorPeerStats(None, None, 0, None)

    lst = listing.copy()
    lst["Code"] = lst["Code"].astype(str).str.zfill(6)
    lst["Dept"] = lst["Dept"].astype(str).str.strip()
    rows = lst[lst["Code"] == code]
    if rows.empty:
        return SectorPeerStats(None, None, 0, None)

    dept = str(rows.iloc[0]["Dept"]).strip()
    if not dept or dept.lower() == "nan":
        return SectorPeerStats(None, None, 0, None)

    peer_codes = lst[lst["Dept"] == dept]["Code"].drop_duplicates().tolist()
    peer_codes = [c for c in peer_codes if c in df.index]

    sub = df.loc[peer_codes]
    pers = pd.to_numeric(sub["PER"], errors="coerce")
    pbrs = pd.to_numeric(sub["PBR"], errors="coerce")
    pers_valid = pers[(pers > 0) & pers.notna()]
    pbrs_valid = pbrs[(pbrs > 0) & pbrs.notna()]

    med_per: float | None
    med_pbr: float | None

    if len(pers_valid) >= MIN_PEERS_FOR_RELATIVE:
        med_per = float(np.median(pers_valid))
    else:
        med_per = None

    if len(pbrs_valid) >= MIN_PEERS_FOR_RELATIVE:
        med_pbr = float(np.median(pbrs_valid))
    else:
        med_pbr = None

    return SectorPeerStats(
        median_per=med_per,
        median_pbr=med_pbr,
        peer_count=len(peer_codes),
        sector_label=dept,
    )

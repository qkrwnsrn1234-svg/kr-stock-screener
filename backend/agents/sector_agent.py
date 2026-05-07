"""
섹터(업종 라벨)·벤치 대비 추세 관점 에이전트입니다.

FinanceDataReader 상장목록의 ``Dept`` 컬럼을 업종 프록시로 사용합니다.
"""

from __future__ import annotations

import asyncio
import logging

import FinanceDataReader as fdr
import pandas as pd

from . import technical_indicators as ti
from backend.agents.base_agent import BaseAgent
from backend.agents.io_async import fetch_equity_ohlcv_async, fetch_index_ohlcv_async
from backend.agents.models import AgentResponse
from backend.screener.sector_etf_flow import etf_flow_extras_for_dept

logger = logging.getLogger(__name__)


def _lookup_listing_row(code: str) -> dict[str, object]:
    """KRX 상장 목록에서 종목 한 줄 메타를 조회합니다."""
    df = fdr.StockListing("KRX")
    rows = df[df["Code"].astype(str) == code]
    if rows.empty:
        return {}
    return rows.iloc[0].to_dict()


class SectorAgent(BaseAgent):
    """섹터 관점 에이전트."""

    def __init__(self, agent_name: str | None = "섹터") -> None:
        super().__init__(agent_name=agent_name)

    async def analyze(self, ticker: str) -> AgentResponse:
        """업종 라벨과 지수 대비 중기 모멘텀을 요약합니다."""
        code = self.validate_ticker(ticker)

        listing_row, df_s, df_b = await asyncio.gather(
            asyncio.to_thread(_lookup_listing_row, code),
            fetch_equity_ohlcv_async(code),
            fetch_index_ohlcv_async("KS11"),
        )

        dept = str(listing_row.get("Dept", "")).strip() if listing_row else ""
        market = str(listing_row.get("Market", "")).strip() if listing_row else ""

        close_s, _ = ti._ensure_close_volume(df_s)
        bench_close = df_b["Close"] if "Close" in df_b.columns else df_b["close"]
        close_s.index = pd.to_datetime(close_s.index).normalize()
        bench_close.index = pd.to_datetime(bench_close.index).normalize()

        tr60_stock = ti.total_return(close_s, 60)
        tr60_bench = ti.total_return(bench_close, 60)

        rel_outperf = None
        if tr60_stock is not None and tr60_bench not in (None, 0):
            rel_outperf = tr60_stock - tr60_bench

        etf_extra: dict[str, object] = {}
        if dept:
            etf_extra = await etf_flow_extras_for_dept(dept)

        signals: dict[str, object] = {
            "sector_proxy": dept or None,
            "listing_market": market or None,
            "total_return_60d": tr60_stock,
            "kospi_total_return_60d": tr60_bench,
            "outperformance_vs_kospi_60d": rel_outperf,
            "etf_proxy_code": etf_extra.get("etf_proxy_code"),
            "etf_proxy_label": etf_extra.get("etf_proxy_label"),
            "etf_flow_summary": etf_extra.get("etf_flow_summary"),
            "etf_foreign_inst_netbuy_krw_sum": etf_extra.get(
                "etf_foreign_inst_netbuy_krw_sum"
            ),
            "etf_volume_ratio_vs_ma20": etf_extra.get("etf_volume_ratio_vs_ma20"),
        }

        score = 0.0
        notes: list[str] = []
        if dept:
            notes.append(f"업종(목록 Dept 프록시): {dept}")
        if rel_outperf is not None:
            notes.append(f"코스피 대비 60일 초과수익 약 {rel_outperf*100:.1f}%p")
            score += float(max(-18.0, min(18.0, rel_outperf * 80)))

        net_etf = etf_extra.get("etf_foreign_inst_netbuy_krw_sum")
        if isinstance(net_etf, (int, float)):
            if net_etf > 0:
                notes.append("대표 업종 ETF 외국인+기관 순매수 합이 양(근사)")
                score += min(8.0, 6.0)
            elif net_etf < 0:
                notes.append("대표 업종 ETF 외국인+기관 순매수 합이 음(근사)")
                score -= min(8.0, 4.0)
        vr = etf_extra.get("etf_volume_ratio_vs_ma20")
        if isinstance(vr, (int, float)) and vr > 1.35:
            notes.append("대표 업종 ETF 거래량이 20일 평균 대비 활발")
            score += 4.0
        opinion = "중립"
        if score >= 10:
            opinion = "매수"
        elif score <= -10:
            opinion = "매도"

        reasoning = "; ".join(notes) if notes else "섹터 라벨을 찾지 못했거나 추세 정보가 부족합니다."

        return self.build_response(
            opinion=opinion,
            confidence=0.50 if dept else 0.38,
            score=float(max(-50.0, min(50.0, score))),
            reasoning=reasoning,
            signals=signals,
        )

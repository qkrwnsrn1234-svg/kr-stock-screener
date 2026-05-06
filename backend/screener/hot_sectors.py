"""
상장 목록 업종(Dept)별 대표 종목 모멘텀으로 주도 섹터 후보를 산출합니다.

전 업종 전수 조회는 비용이 크므로, 종목 수가 많은 업종 상위 일부만 표본으로 삼습니다.
"""

from __future__ import annotations

import asyncio
import logging

import pandas as pd

from backend.agents import technical_indicators as ti
from backend.agents.io_async import fetch_equity_ohlcv_async, fetch_index_ohlcv_async
from backend.agents.models import HotSectorItem, HotSectorsReport
from backend.data import finance_data
from backend.screener.sector_etf_flow import etf_flow_extras_for_dept

logger = logging.getLogger(__name__)

# 로드맵상 어닝 리비전은 외부 피드 연동 전까지 안내 문구만 제공
EARNINGS_REVISION_PLACEHOLDER = "컨센서스·어닝 리비전 데이터 미연동(별도 피드 연동 예정)"


async def _assemble_hot_row(
    dept: str,
    rep_code: str,
    rel: float | None,
    strength: float,
    summary: str,
) -> HotSectorItem:
    """모멘텀 요약 + ETF 프록시 자금 흐름 + 리비전 안내를 한 행으로 만듭니다."""
    ex = await etf_flow_extras_for_dept(dept)
    return HotSectorItem(
        sector_name=dept,
        representative_ticker=rep_code,
        relative_outperformance_60d=float(rel) if rel is not None else None,
        strength_score=strength,
        summary=summary,
        etf_proxy_code=ex.get("etf_proxy_code"),
        etf_proxy_label=ex.get("etf_proxy_label"),
        etf_flow_summary=ex.get("etf_flow_summary"),
        earnings_revision_note=EARNINGS_REVISION_PLACEHOLDER,
    )


async def build_hot_sectors(
    *,
    pool_size: int = 12,
    top_n: int = 5,
) -> HotSectorsReport:
    """
    KRX 상장 목록에서 업종 표본을 뽑고, 코스피 대비 60일 초과수익으로 순위를 매깁니다.

    Args:
        pool_size: 표본으로 볼 업종 개수(종목 수 많은 순).
        top_n: 응답에 포함할 상위 업종 수.

    Returns:
        ``HotSectorsReport`` (데이터 부족 시 ``items`` 는 빈 리스트일 수 있음).
    """
    try:
        listing = await asyncio.to_thread(finance_data.list_krx_symbols, None)
    except Exception as exc:
        logger.exception("상장 목록 조회 실패: %s", exc)
        return HotSectorsReport(items=[])

    if listing is None or listing.empty or "Dept" not in listing.columns or "Code" not in listing.columns:
        logger.warning("상장 목록에 Dept/Code 컬럼이 없거나 비어 있습니다.")
        return HotSectorsReport(items=[])

    df = listing.copy()
    df["Dept"] = df["Dept"].astype(str).str.strip()
    df["Code"] = df["Code"].astype(str).str.strip().str.zfill(6)
    df = df[df["Dept"].ne("") & df["Dept"].ne("nan")]

    if df.empty:
        return HotSectorsReport(items=[])

    dept_counts = df.groupby("Dept").size().sort_values(ascending=False).head(int(pool_size))

    reps: list[tuple[str, str]] = []
    for dept in dept_counts.index:
        row = df[df["Dept"] == dept].iloc[0]
        code = str(row["Code"])
        if len(code) == 6 and code.isdigit():
            reps.append((dept, code))

    if not reps:
        return HotSectorsReport(items=[])

    bench_df = await fetch_index_ohlcv_async("KS11")
    bench_close = bench_df["Close"] if "Close" in bench_df.columns else bench_df["close"]
    bench_close = bench_close.astype(float)
    bench_close.index = pd.to_datetime(bench_close.index).normalize()
    tr_bench = ti.total_return(bench_close, 60)

    async def _momentum_for(dept: str, code: str) -> tuple[str, str, float | None]:
        try:
            df_s = await fetch_equity_ohlcv_async(code)
            close_s, _ = ti._ensure_close_volume(df_s)
            close_s.index = pd.to_datetime(close_s.index).normalize()
            tr_s = ti.total_return(close_s, 60)
            rel: float | None = None
            if tr_s is not None and tr_bench is not None:
                rel = float(tr_s - tr_bench)
            return dept, code, rel
        except Exception as exc:
            logger.warning("섹터 모멘텀 계산 실패 dept=%s code=%s: %s", dept, code, exc)
            return dept, code, None

    rows = await asyncio.gather(*[_momentum_for(d, c) for d, c in reps])
    scored = [(d, c, r) for d, c, r in rows if r is not None]
    scored.sort(key=lambda x: x[2], reverse=True)
    scored = scored[: int(top_n)]

    if not scored:
        return HotSectorsReport(items=[])

    best = scored[0][2] if scored[0][2] is not None else 0.0
    worst = scored[-1][2] if scored[-1][2] is not None else best
    span = abs(best - worst)

    tasks: list[asyncio.Task[HotSectorItem]] = []
    for dept, c, rel in scored:
        if rel is None:
            strength = 0.0
        elif span < 1e-12:
            strength = 85.0
        else:
            strength = max(0.0, min(100.0, (float(rel) - worst) / span * 100.0))
        rel_pct = float(rel) * 100.0 if rel is not None else None
        summ = (
            f"대표종목({c}) 60영업일 수익이 코스피 대비 약 {rel_pct:+.1f}%p"
            if rel_pct is not None
            else "모멘텀 산출 불가"
        )
        tasks.append(asyncio.create_task(_assemble_hot_row(dept, c, rel, strength, summ)))

    items = list(await asyncio.gather(*tasks))

    return HotSectorsReport(items=items)

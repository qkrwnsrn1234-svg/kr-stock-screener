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

logger = logging.getLogger(__name__)


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

    items: list[HotSectorItem] = []
    if not scored:
        return HotSectorsReport(items=[])

    best = scored[0][2] if scored[0][2] is not None else 0.0
    worst = scored[-1][2] if scored[-1][2] is not None else best
    span = abs(best - worst)

    for dept, c, rel in scored:
        # 표본이 하나면 상대 스케일이 없으므로 중간~높은 점수로 표시
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
        items.append(
            HotSectorItem(
                sector_name=dept,
                representative_ticker=c,
                relative_outperformance_60d=float(rel) if rel is not None else None,
                strength_score=strength,
                summary=summ,
            )
        )

    return HotSectorsReport(items=items)

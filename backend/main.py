"""
FastAPI 진입점 — 단일 종목 분석, 스크리닝, 포트폴리오 조언, 주도 섹터 API.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import Body, FastAPI, HTTPException, Query

from backend.agents.advisor_agent import AdvisorAgent
from backend.agents.ceo_agent import CEOOrchestrator
from backend.agents.financial_agent import FinancialAgent
from backend.agents.models import (
    AgentPerformanceSummary,
    AnalysisHistoryItem,
    BacktestSummary,
    CEOReport,
    HotSectorsReport,
    PortfolioAdvice,
    SearchResults,
    ScreeningResult,
    WatchlistAddRequest,
    WatchlistItem,
    WatchlistSummaryItem,
)
from backend.jobs.background_tasks import (
    scheduler_enabled,
    scheduler_interval_seconds,
    scheduler_loop,
)
from backend.notify.alerts import (
    alert_on_overheat,
    alert_on_undervalue,
    alerts_any_channel_configured,
    cooldown_seconds,
    notify_screening_results_sync,
    undervalue_min_score,
    webhook_url,
)
from backend.screener.hot_sectors import build_hot_sectors
from backend.screener.search import search_krx_symbols
from backend.screener.screening import build_screening_result
from backend.screener.watchlist_summary import build_watchlist_summary
from backend.storage.analysis_history import (
    compute_backtest_summary,
    compute_agent_performance,
    list_recent_records,
    list_records_for_ticker,
    save_ceo_report_blocking,
)

logger = logging.getLogger(__name__)

logging.basicConfig(level=logging.INFO)

# 요청 한도 (외부 데이터 조회 부담)
MAX_SCREEN_TICKERS = 8
_TICKER_SPLIT_RE = re.compile(r"[\s,]+")


@asynccontextmanager
async def _lifespan(_app: FastAPI):
    """앱 기동·종료 시 백그라운드 스케줄러를 연결합니다."""
    stop_scheduler = asyncio.Event()
    sched_task: asyncio.Task[None] | None = None
    if scheduler_enabled():
        sched_task = asyncio.create_task(scheduler_loop(stop_scheduler))
    yield
    if sched_task is not None:
        stop_scheduler.set()
        sched_task.cancel()
        try:
            await sched_task
        except asyncio.CancelledError:
            pass


app = FastAPI(
    title="KR Stock Screener API",
    description="AI 멀티에이전트 기반 한국 주식 분석 백엔드",
    version="0.1.0",
    lifespan=_lifespan,
)


def _utc_now_iso() -> str:
    """응답용 UTC ISO 시각 문자열."""
    return datetime.now(timezone.utc).isoformat()


def _parse_holdings(raw: str) -> dict[str, float]:
    """
    holdings 쿼리 문자열을 종목→비중 딕셔너리로 파싱합니다.

    형식: ``005930:0.5,000660:0.5`` (콤마 구분, 콜론으로 비중).
    """
    out: dict[str, float] = {}
    for part in raw.split(","):
        p = part.strip()
        if not p:
            continue
        if ":" not in p:
            raise ValueError(f"비중 형식이 올바르지 않습니다(코드:비중): {p!r}")
        code, w_s = p.split(":", 1)
        code = code.strip().zfill(6)
        FinancialAgent().validate_ticker(code)
        w = float(w_s.strip())
        if w < 0:
            raise ValueError(f"비중은 0 이상이어야 합니다: {code}")
        out[code] = w
    return out


def _normalize_ticker_list(raw: str) -> list[str]:
    """콤마/공백 구분 종목 목록을 6자리 코드 리스트로 정규화합니다."""
    parts = [x for x in _TICKER_SPLIT_RE.split(raw.strip()) if x]
    if not parts:
        raise ValueError("종목이 하나도 없습니다.")
    validator = FinancialAgent()
    codes: list[str] = []
    for p in parts:
        c = p.zfill(6)
        codes.append(validator.validate_ticker(c))
    # 순서 유지 중복 제거
    seen: set[str] = set()
    uniq: list[str] = []
    for c in codes:
        if c not in seen:
            seen.add(c)
            uniq.append(c)
    return uniq


@app.get("/health")
async def health() -> dict[str, str]:
    """서버 동작 확인."""
    return {"status": "ok", "timestamp": _utc_now_iso()}


@app.get("/search", response_model=SearchResults)
async def search_symbols(
    q: str = Query(default="", max_length=40, description="종목명 또는 종목코드 검색어"),
    limit: int = Query(default=8, ge=1, le=20, description="최대 검색 결과 수"),
) -> SearchResults:
    """종목명·종목코드 기반 자동완성 검색 결과를 반환합니다."""
    try:
        items = await asyncio.to_thread(search_krx_symbols, q, limit)
        return SearchResults(items=items)
    except Exception as exc:
        logger.exception("종목 검색 실패 q=%s", q)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/system/scheduler")
async def scheduler_status() -> dict[str, str | bool | int]:
    """백그라운드 데이터 갱신 스케줄러 설정 상태(환경 변수 기준)입니다."""
    return {
        "timestamp": _utc_now_iso(),
        "scheduler_enabled": scheduler_enabled(),
        "interval_seconds": scheduler_interval_seconds(),
    }


@app.get("/system/alerts")
async def alerts_status() -> dict[str, str | bool | float]:
    """과열·저평가 알림 채널 설정 요약(URL·비밀번호 미포함)."""
    smtp_on = bool(os.getenv("ALERT_SMTP_HOST", "").strip() and os.getenv("ALERT_EMAIL_TO", "").strip())
    return {
        "timestamp": _utc_now_iso(),
        "any_channel_configured": alerts_any_channel_configured(),
        "webhook_configured": bool(webhook_url()),
        "smtp_configured": smtp_on,
        "alert_on_overheat": alert_on_overheat(),
        "alert_on_undervalue": alert_on_undervalue(),
        "undervalue_min_score": undervalue_min_score(),
        "cooldown_seconds": cooldown_seconds(),
    }


@app.get("/analyze/{ticker}", response_model=CEOReport)
async def analyze_ticker(
    ticker: str,
    persist: bool = Query(
        True,
        description="true면 분석 결과를 설정된 저장소(DB)에 저장합니다.",
    ),
    use_stats_weights: bool = Query(
        True,
        description=(
            "true면 /agents/stats 성과(이미 채워진 선행수익률)로 에이전트 신뢰도 가중을 적용합니다."
        ),
    ),
    send_alerts: bool = Query(
        True,
        description="false면 과열·저평가 알림(웹훅/메일)을 보내지 않습니다.",
    ),
    use_claude_summary: bool = Query(
        True,
        description="true면 ANTHROPIC_API_KEY가 있을 때 CEO 요약을 Claude로 보강합니다.",
    ),
) -> CEOReport:
    """
    단일 종목에 대해 전 에이전트 병렬 분석 후 CEO 종합 보고서를 반환합니다.
    """
    try:
        orch = CEOOrchestrator()
        report = await orch.run(
            ticker,
            use_stats_weights=use_stats_weights,
            use_claude_summary=use_claude_summary,
        )
        if persist:
            try:
                await asyncio.to_thread(save_ceo_report_blocking, report)
            except Exception as exc:
                logger.warning("분석 이력 저장 실패(응답은 정상): %s", exc)
        if send_alerts and alerts_any_channel_configured():
            try:
                sr = await build_screening_result(report)
                await asyncio.to_thread(notify_screening_results_sync, [sr], "analyze")
            except Exception as exc:
                logger.warning("분석 알림 전송 실패(응답은 정상): %s", exc)
        return report
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("분석 실패 ticker=%s", ticker)
        raise HTTPException(status_code=500, detail=f"분석 중 오류: {exc}") from exc


@app.get("/reports/recent", response_model=list[AnalysisHistoryItem])
async def reports_recent(
    limit: int = Query(50, ge=1, le=200, description="최대 건수"),
) -> list[AnalysisHistoryItem]:
    """최근 저장된 분석 이력(요약) 목록."""
    try:
        rows = await asyncio.to_thread(list_recent_records, limit)
        return [AnalysisHistoryItem(**r) for r in rows]
    except Exception as exc:
        logger.exception("이력 조회 실패")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/reports/ticker/{ticker}", response_model=list[AnalysisHistoryItem])
async def reports_for_ticker(
    ticker: str,
    limit: int = Query(30, ge=1, le=100),
) -> list[AnalysisHistoryItem]:
    """특정 종목의 저장된 분석 이력."""
    try:
        code = FinancialAgent().validate_ticker(ticker.strip().zfill(6))
        rows = await asyncio.to_thread(list_records_for_ticker, code, limit)
        return [AnalysisHistoryItem(**r) for r in rows]
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("종목 이력 조회 실패")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/agents/stats", response_model=AgentPerformanceSummary)
async def agents_stats(
    horizon: int = Query(30, description="평가 거래일 수(30·60·90)", ge=30, le=90),
) -> AgentPerformanceSummary:
    """
    저장된 분석 대비 선행 수익률로 에이전트·CEO 적중 휴리스틱을 요약합니다.

    첫 호출 시 수익률 컬럼이 비어 있으면 OHLCV로 채웁니다(시간 소요 가능).
    """
    if horizon not in (30, 60, 90):
        raise HTTPException(
            status_code=422,
            detail="horizon은 30, 60, 90 중 하나여야 합니다.",
        )
    try:
        raw = await asyncio.to_thread(compute_agent_performance, horizon)
        return AgentPerformanceSummary(**raw)
    except Exception as exc:
        logger.exception("에이전트 통계 산출 실패")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/backtest/summary", response_model=BacktestSummary)
async def backtest_summary(
    horizon: int = Query(30, description="평가 거래일 수(30·60·90)", ge=30, le=90),
    limit: int = Query(100, description="응답에 포함할 최근 평가 레코드 수", ge=10, le=300),
) -> BacktestSummary:
    """저장된 분석 이력 기반 단순 백테스트 요약을 반환합니다."""
    if horizon not in (30, 60, 90):
        raise HTTPException(
            status_code=422,
            detail="horizon은 30, 60, 90 중 하나여야 합니다.",
        )
    try:
        raw = await asyncio.to_thread(compute_backtest_summary, horizon, limit=limit)
        return BacktestSummary(**raw)
    except Exception as exc:
        logger.exception("백테스트 요약 산출 실패")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/screen", response_model=list[ScreeningResult])
async def screen(
    tickers: str = Query(
        ...,
        description="콤마로 구분된 6자리 종목코드 목록 (최대 8개)",
        examples=["005930,000660"],
    ),
    use_stats_weights: bool = Query(
        False,
        description="true면 CEO가 성적표 기반 에이전트 신뢰도 가중을 사용(다종목일 때 부담 증가).",
    ),
    send_alerts: bool = Query(
        True,
        description="false면 과열·저평가 알림(웹훅/메일)을 보내지 않습니다.",
    ),
    use_claude_summary: bool = Query(
        False,
        description="true면 각 종목 CEO 요약을 Claude로 보강합니다(API 비용·시간 증가).",
    ),
) -> list[ScreeningResult]:
    """
    다종목 스크리닝 — 종목별 에이전트 전체 파이프라인·저평가·과열 요약을 반환합니다.
    """
    try:
        codes = _normalize_ticker_list(tickers)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    if len(codes) > MAX_SCREEN_TICKERS:
        raise HTTPException(
            status_code=422,
            detail=f"한 번에 최대 {MAX_SCREEN_TICKERS}개 종목만 조회할 수 있습니다.",
        )

    sem = asyncio.Semaphore(2)

    async def _one(code: str) -> ScreeningResult:
        async with sem:
            report = await CEOOrchestrator().run(
                code,
                use_stats_weights=use_stats_weights,
                use_claude_summary=use_claude_summary,
            )
            return await build_screening_result(report)

    try:
        results = list(await asyncio.gather(*[_one(c) for c in codes]))
        if send_alerts and alerts_any_channel_configured():
            try:
                await asyncio.to_thread(notify_screening_results_sync, results, "screen")
            except Exception as exc:
                logger.warning("스크리닝 알림 전송 실패(응답은 정상): %s", exc)
        return results
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("스크리닝 실패")
        raise HTTPException(status_code=500, detail=f"스크리닝 오류: {exc}") from exc


@app.get("/portfolio/advice", response_model=PortfolioAdvice)
async def portfolio_advice(
    holdings: str = Query(
        ...,
        description="보유 비중(005930:0.6,000660:0.4 형식)",
        examples=["005930:1.0"],
    ),
    focus: str | None = Query(
        default=None,
        description="조언 기준 종목(미지정 시 비중 최대 종목)",
        min_length=6,
        max_length=6,
    ),
) -> PortfolioAdvice:
    """보유 내역을 바탕으로 분산·리스크 관점 조언을 반환합니다."""
    try:
        weights = _parse_holdings(holdings)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    if not weights:
        raise HTTPException(status_code=422, detail="holdings가 비어 있습니다.")

    if focus:
        focus_code = FinancialAgent().validate_ticker(focus.strip().zfill(6))
        if focus_code not in weights:
            raise HTTPException(status_code=422, detail="focus 종목이 holdings에 없습니다.")
    else:
        focus_code = max(weights.keys(), key=lambda k: weights[k])

    agent = AdvisorAgent(holdings=weights)
    try:
        resp = await agent.analyze(focus_code)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("포트폴리오 조언 실패")
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    sig = resp.signals if isinstance(resp.signals, dict) else {}
    suggestion = sig.get("suggested_equal_weights") or {}
    if not isinstance(suggestion, dict):
        suggestion = {}

    hhi = float(sig.get("herfindahl_index", 0.0)) if sig.get("herfindahl_index") is not None else 0.0
    vol = float(sig.get("weighted_vol_proxy", 0.0)) if sig.get("weighted_vol_proxy") is not None else 0.0

    if hhi > 0.34 or vol > 0.32:
        risk_level = "high"
    elif hhi > 0.25 or vol > 0.22:
        risk_level = "medium"
    else:
        risk_level = "low"

    cleaned_weights = {str(k).zfill(6): float(v) for k, v in suggestion.items()}
    text = (resp.reasoning or "").strip() or resp.opinion

    return PortfolioAdvice(
        weight_suggestion=cleaned_weights,
        risk_level=risk_level,
        advice=text,
    )


@app.get("/watchlist", response_model=list[WatchlistItem])
async def watchlist_list() -> list[WatchlistItem]:
    """관심 종목 전체 목록을 반환합니다."""
    try:
        from backend.storage.watchlist import list_tickers

        rows = await asyncio.to_thread(list_tickers)
        return [WatchlistItem(**r) for r in rows]
    except Exception as exc:
        logger.exception("관심 종목 조회 실패")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/watchlist/summary", response_model=list[WatchlistSummaryItem])
async def watchlist_summary() -> list[WatchlistSummaryItem]:
    """관심 종목 목록에 종목명·최근가·등락률을 붙여 반환합니다."""
    try:
        from backend.storage.watchlist import list_tickers

        rows = await asyncio.to_thread(list_tickers)
        summary_rows = await asyncio.to_thread(build_watchlist_summary, rows)
        return [WatchlistSummaryItem(**r) for r in summary_rows]
    except Exception as exc:
        logger.exception("관심 종목 요약 조회 실패")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/watchlist", response_model=WatchlistItem, status_code=201)
async def watchlist_add(body: WatchlistAddRequest = Body(...)) -> WatchlistItem:
    """
    관심 종목을 추가합니다. 이미 있으면 memo만 갱신합니다.
    """
    try:
        from backend.storage.watchlist import add_ticker

        code = FinancialAgent().validate_ticker(body.ticker.strip().zfill(6))
        row = await asyncio.to_thread(add_ticker, code, body.memo)
        return WatchlistItem(**row)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("관심 종목 추가 실패")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.delete("/watchlist/{ticker}", status_code=204)
async def watchlist_remove(ticker: str) -> None:
    """관심 종목을 삭제합니다."""
    try:
        from backend.storage.watchlist import remove_ticker

        code = FinancialAgent().validate_ticker(ticker.strip().zfill(6))
        deleted = await asyncio.to_thread(remove_ticker, code)
        if not deleted:
            raise HTTPException(status_code=404, detail="관심 종목에 없는 종목입니다.")
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("관심 종목 삭제 실패")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/sector/hot", response_model=HotSectorsReport)
async def sector_hot(
    pool: int = Query(default=12, ge=4, le=30, description="표본 업종 수"),
    top: int = Query(default=5, ge=1, le=15, description="응답 상위 개수"),
) -> HotSectorsReport:
    """종목 수가 많은 업종 표본의 코스피 대비 모멘텀 기준 주도 섹터 후보."""
    try:
        return await build_hot_sectors(pool_size=pool, top_n=top)
    except Exception as exc:
        logger.exception("주도 섹터 산출 실패")
        raise HTTPException(status_code=500, detail=str(exc)) from exc

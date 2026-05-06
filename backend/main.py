"""
FastAPI 진입점 — 단일 종목 분석, 스크리닝, 포트폴리오 조언, 주도 섹터 API.
"""

from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException, Query

from backend.agents.advisor_agent import AdvisorAgent
from backend.agents.ceo_agent import CEOOrchestrator
from backend.agents.financial_agent import FinancialAgent
from backend.agents.models import CEOReport, HotSectorsReport, PortfolioAdvice, ScreeningResult
from backend.screener.hot_sectors import build_hot_sectors
from backend.screener.screening import build_screening_result

logger = logging.getLogger(__name__)

logging.basicConfig(level=logging.INFO)

# 요청 한도 (외부 데이터 조회 부담)
MAX_SCREEN_TICKERS = 8
_TICKER_SPLIT_RE = re.compile(r"[\s,]+")

app = FastAPI(
    title="KR Stock Screener API",
    description="AI 멀티에이전트 기반 한국 주식 분석 백엔드",
    version="0.1.0",
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


@app.get("/analyze/{ticker}", response_model=CEOReport)
async def analyze_ticker(ticker: str) -> CEOReport:
    """
    단일 종목에 대해 전 에이전트 병렬 분석 후 CEO 종합 보고서를 반환합니다.
    """
    try:
        orch = CEOOrchestrator()
        return await orch.run(ticker)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("분석 실패 ticker=%s", ticker)
        raise HTTPException(status_code=500, detail=f"분석 중 오류: {exc}") from exc


@app.get("/screen", response_model=list[ScreeningResult])
async def screen(
    tickers: str = Query(
        ...,
        description="콤마로 구분된 6자리 종목코드 목록 (최대 8개)",
        examples=["005930,000660"],
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
            report = await CEOOrchestrator().run(code)
            return await build_screening_result(report)

    try:
        return list(await asyncio.gather(*[_one(c) for c in codes]))
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

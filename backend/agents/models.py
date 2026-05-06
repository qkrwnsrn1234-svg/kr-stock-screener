"""
에이전트·스크리닝·포트폴리오 조언용 공통 데이터 모델입니다.

FastAPI와의 호환을 위해 Pydantic v2 ``BaseModel`` 을 사용합니다.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field, field_validator


def _utc_now() -> datetime:
    """현재 시각(UTC, timezone-aware)을 반환합니다."""
    return datetime.now(timezone.utc)


class AgentResponse(BaseModel):
    """
    단일 에이전트의 분석 결과입니다.

    Attributes:
        opinion: 투자 성향 요약 (예: ``매수``, ``중립``, ``매도`` 또는 자유 서술).
        confidence: 신뢰도 (0.0 ~ 1.0).
        score: 에이전트 고유 스코어 (예: -100 ~ 100 또는 0 ~ 100; 에이전트별 정의).
        reasoning: 판단 근거 서술.
        signals: 정량 신호 딕셔너리 (예: PER, RSI 키-값).
        agent_name: 에이전트 표시 이름.
        timestamp: 응답 생성 시각(UTC).
    """

    opinion: str = Field(..., description="투자 의견 요약")
    confidence: float = Field(..., ge=0.0, le=1.0, description="신뢰도 0~1")
    score: float = Field(..., description="에이전트 스코어")
    reasoning: str = Field(default="", description="판단 근거")
    signals: dict[str, Any] = Field(default_factory=dict, description="정량 신호")
    agent_name: str = Field(default="", description="에이전트 이름")
    timestamp: datetime = Field(default_factory=_utc_now, description="생성 시각(UTC)")

    model_config = {"frozen": False}


class UndervalueBreakdown(BaseModel):
    """
    언더밸류에이션 세부 점수(구성 요소별 0~100, 높을수록 상대적으로 저평가·우량에 가깝게 정의).
    """

    per_score: float = Field(..., ge=0.0, le=100.0, description="PER·업종 중앙값 대비")
    pbr_score: float = Field(..., ge=0.0, le=100.0, description="PBR·업종 중앙값 대비")
    fcf_yield_score: float = Field(
        ...,
        ge=0.0,
        le=100.0,
        description="FCF Yield (미수집 시 중립 50)",
    )
    fscore_score: float = Field(..., ge=0.0, le=100.0, description="Piotroski 근사 점수 반영")
    combined: float = Field(..., ge=0.0, le=100.0, description="가중 합산 최종 언더밸류")
    peer_count: int = Field(default=0, ge=0, description="업종 동종 표본 수")
    sector_label: str | None = Field(default=None, description="업종 라벨(상장목록 Dept)")
    fcf_note: str = Field(default="", description="FCF 관련 데이터 한 줄 메모")


class OverheatAlert(BaseModel):
    """과열(오버히트) 알럿 등급과 근거입니다."""

    level: str = Field(
        default="정상",
        description="정상 | 주의 | 경고 | 위험",
    )
    heat_score: float = Field(default=0.0, ge=0.0, le=100.0, description="과열 강도 0~100")
    reasons: list[str] = Field(default_factory=list, description="트리거 요약")


class ScreeningResult(BaseModel):
    """
    단일 종목 스크리닝 결과입니다.

    Attributes:
        ticker: 종목코드 6자리.
        undervalue_score: 언더밸류 점수 (0~100, 높을수록 저평가 가능성).
        overheat_flag: 과열 여부 (오버히트 알럿용).
        undervalue_breakdown: 구성 요소별 점수(Phase 2).
        overheat_alert: 등급·근거(Phase 2).
        agent_reports: 참여 에이전트별 ``AgentResponse`` 목록.
        timestamp: 산출 시각(UTC).
    """

    ticker: str = Field(..., min_length=6, max_length=6, description="종목코드")
    undervalue_score: float = Field(default=0.0, ge=0.0, le=100.0, description="저평가 스코어")
    overheat_flag: bool = Field(default=False, description="과열 플래그")
    undervalue_breakdown: UndervalueBreakdown | None = Field(
        default=None, description="언더밸류 구성 요소"
    )
    overheat_alert: OverheatAlert | None = Field(default=None, description="과열 알럿 상세")
    agent_reports: list[AgentResponse] = Field(default_factory=list, description="에이전트 결과 목록")
    timestamp: datetime = Field(default_factory=_utc_now, description="생성 시각(UTC)")

    @field_validator("ticker")
    @classmethod
    def _digits_only(cls, v: str) -> str:
        """종목코드는 숫자 6자리만 허용합니다."""
        s = v.strip()
        if not s.isdigit():
            raise ValueError("종목코드는 숫자 6자리여야 합니다.")
        return s


class CEOReport(BaseModel):
    """
    CEO 오케스트레이터의 종합 결과입니다.

    Attributes:
        ticker: 종목코드.
        final_opinion: 최종 의견(매수/중립/매도 등).
        buy_pct: 매수 비중 추정(% , 합계 100).
        neutral_pct: 중립 비중 추정(%).
        sell_pct: 매도 비중 추정(%).
        summary_lines: 핵심 근거(최대 3줄).
        agent_reports: 개별 에이전트 원문 보존.
        risk_rebuttal: 리스크 에이전트 중심 반론 요약.
        timestamp: 생성 시각(UTC).
    """

    ticker: str = Field(..., min_length=6, max_length=6, description="종목코드")
    final_opinion: str = Field(..., description="최종 투자 의견")
    buy_pct: float = Field(..., ge=0.0, le=100.0)
    neutral_pct: float = Field(..., ge=0.0, le=100.0)
    sell_pct: float = Field(..., ge=0.0, le=100.0)
    summary_lines: list[str] = Field(default_factory=list, description="핵심 근거(≤3줄)")
    agent_reports: list[AgentResponse] = Field(default_factory=list)
    risk_rebuttal: str = Field(default="", description="반론/경고 요약")
    timestamp: datetime = Field(default_factory=_utc_now, description="생성 시각(UTC)")
    stats_weights_applied: bool = Field(
        default=False,
        description="성적표 기반 에이전트 신뢰도 가중이 집계에 반영되었는지",
    )
    agent_weight_multipliers: dict[str, float] = Field(
        default_factory=dict,
        description="에이전트명 → 적용된 신뢰도 배수(요청 시에만 채움)",
    )

    @field_validator("ticker")
    @classmethod
    def _ceo_ticker_digits(cls, v: str) -> str:
        s = v.strip()
        if not s.isdigit():
            raise ValueError("종목코드는 숫자 6자리여야 합니다.")
        return s

    @field_validator("summary_lines")
    @classmethod
    def _trim_summary(cls, v: list[str]) -> list[str]:
        """요약은 최대 3줄로 제한합니다."""
        lines = [ln.strip() for ln in v if ln.strip()]
        return lines[:3]


class HotSectorItem(BaseModel):
    """
    주도 섹터 랭킹의 한 행입니다.

    Attributes:
        sector_name: 업종·섹터 라벨(상장목록 Dept 등).
        representative_ticker: 모멘텀 계산에 사용한 대표 종목코드.
        relative_outperformance_60d: 코스피 대비 60영업일 초과수익률(소수, 예: 0.05는 +5%p).
        strength_score: 표시용 상대 강도 점수(0~100, 높을수록 상대적으로 강함).
        summary: 근거 한 줄 요약.
    """

    sector_name: str = Field(..., description="섹터 이름")
    representative_ticker: str = Field(..., min_length=6, max_length=6, description="대표 종목코드")
    relative_outperformance_60d: float | None = Field(
        default=None, description="벤치 대비 60일 초과수익률(소수)"
    )
    strength_score: float = Field(..., ge=0.0, le=100.0, description="상대 강도 점수")
    summary: str = Field(default="", description="요약 문구")
    etf_proxy_code: str | None = Field(default=None, description="섹터 대표 ETF 종목코드")
    etf_proxy_label: str | None = Field(default=None, description="대표 ETF 이름")
    etf_flow_summary: str | None = Field(
        default=None,
        description="ETF 순매수·거래량 기반 자금 흐름 요약",
    )
    earnings_revision_note: str | None = Field(
        default=None,
        description="어닝 리비전·컨센서스 연동 상태 안내",
    )


class HotSectorsReport(BaseModel):
    """시장 전반 관점의 주도 섹터 후보 목록입니다."""

    items: list[HotSectorItem] = Field(default_factory=list, description="섹터 랭킹")
    timestamp: datetime = Field(default_factory=_utc_now, description="생성 시각(UTC)")


class PortfolioAdvice(BaseModel):
    """
    포트폴리오 단위 조언 결과입니다.

    Attributes:
        weight_suggestion: 종목코드(또는 심볼) → 목표 비중(0~1). 합계 1.0 근처를 권장.
        risk_level: 리스크 등급 서술 (예: ``low``, ``medium``, ``high`` 또는 한글).
        advice: 종합 코멘트.
        timestamp: 생성 시각(UTC).
    """

    weight_suggestion: dict[str, float] = Field(default_factory=dict, description="종목별 목표 비중")
    risk_level: str = Field(default="medium", description="포트폴리오 리스크 수준")
    advice: str = Field(default="", description="종합 조언 텍스트")
    timestamp: datetime = Field(default_factory=_utc_now, description="생성 시각(UTC)")

    @field_validator("weight_suggestion")
    @classmethod
    def _weights_non_negative(cls, v: dict[str, float]) -> dict[str, float]:
        """비중은 음수일 수 없습니다 (합계 1.0 맞추기는 호출자 책임)."""
        for k, w in v.items():
            if w < 0:
                raise ValueError(f"비중은 0 이상이어야 합니다: {k}={w}")
        return v


class AnalysisHistoryItem(BaseModel):
    """저장된 분석 이력 목록용 요약 항목입니다."""

    id: int = Field(..., ge=1)
    ticker: str = Field(..., min_length=6, max_length=6)
    analyzed_at: str = Field(..., description="ISO8601 시각 문자열")
    ref_price: float | None = Field(default=None, description="분석 시점 기준가")
    final_opinion: str | None = Field(default=None, description="CEO 최종 의견")
    return_30d: float | None = Field(default=None, description="30거래일 후 수익률(소수)")
    return_60d: float | None = Field(default=None, description="60거래일 후 수익률(소수)")
    return_90d: float | None = Field(default=None, description="90거래일 후 수익률(소수)")


class AgentStatRow(BaseModel):
    """에이전트(또는 CEO) 단위 적중 통계입니다."""

    agent_name: str = Field(..., description="표시 이름")
    samples: int = Field(..., ge=0)
    hits: int = Field(..., ge=0)
    hit_rate: float | None = Field(default=None, description="적중 비율 0~1, 표본 없으면 null")


class AgentPerformanceSummary(BaseModel):
    """에이전트 성적표 요약 API 응답."""

    evaluated_records: int = Field(..., ge=0, description="수익률 계산에 사용된 분석 건수")
    horizon_trading_days: int = Field(default=30, description="평가에 쓴 거래일 수")
    by_agent: list[AgentStatRow] = Field(default_factory=list)
    ceo: AgentStatRow
    timestamp: str = Field(..., description="응답 생성 시각 ISO(UTC)")

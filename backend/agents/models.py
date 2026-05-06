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


class ScreeningResult(BaseModel):
    """
    단일 종목 스크리닝 결과입니다.

    Attributes:
        ticker: 종목코드 6자리.
        undervalue_score: 언더밸류 점수 (0~100, 높을수록 저평가 가능성).
        overheat_flag: 과열 여부 (오버히트 알럿용).
        agent_reports: 참여 에이전트별 ``AgentResponse`` 목록.
        timestamp: 산출 시각(UTC).
    """

    ticker: str = Field(..., min_length=6, max_length=6, description="종목코드")
    undervalue_score: float = Field(default=0.0, ge=0.0, le=100.0, description="저평가 스코어")
    overheat_flag: bool = Field(default=False, description="과열 플래그")
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

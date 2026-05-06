"""
모든 분석 에이전트의 공통 추상 베이스입니다.

CEO 에이전트가 병렬로 ``analyze`` 를 호출할 수 있도록 코루틴 인터페이스를 고정합니다.
"""

from __future__ import annotations

import logging
import re
from abc import ABC, abstractmethod
from typing import Any

from backend.agents.models import AgentResponse

# 한국 상장 일반주·ETF 등 6자리 숫자 종목코드
_TICKER_RE = re.compile(r"^\d{6}$")


class BaseAgent(ABC):
    """
    분석 에이전트 추상 클래스.

    서브클래스는 ``analyze`` 만 구현하면 되며, 공통 로깅·종목 검증·응답 빌더를 사용합니다.

    Attributes:
        agent_name: 에이전트 표시 이름 (미지정 시 클래스 이름).
    """

    def __init__(self, agent_name: str | None = None) -> None:
        """
        베이스 에이전트를 초기화합니다.

        Args:
            agent_name: 로그·응답에 붙일 이름. ``None``이면 클래스 이름을 사용합니다.
        """
        self.agent_name: str = agent_name or self.__class__.__name__
        self.logger: logging.Logger = logging.getLogger(f"agents.{self.agent_name}")

    def validate_ticker(self, ticker: str) -> str:
        """
        종목코드 문자열을 검증하고 정규화(앞뒤 공백 제거)합니다.

        Args:
            ticker: 사용자 입력 종목코드.

        Returns:
            유효한 6자리 숫자 코드.

        Raises:
            ValueError: 형식이 맞지 않을 때.
        """
        normalized = ticker.strip()
        if not _TICKER_RE.fullmatch(normalized):
            raise ValueError(f"종목코드는 숫자 6자리여야 합니다: {ticker!r}")
        return normalized

    @abstractmethod
    async def analyze(self, ticker: str) -> AgentResponse:
        """
        단일 종목을 분석하고 표준 응답을 반환합니다.

        외부 API·파일·LLM 호출이 포함될 수 있으므로 비동기 메서드로 정의합니다.

        Args:
            ticker: 종목코드 6자리.

        Returns:
            ``AgentResponse`` 인스턴스.

        Raises:
            ValueError: 종목코드 등 입력값이 잘못된 경우.
            RuntimeError: 분석 수행 중 치명적 오류가 발생한 경우 (서브클래스 정의).
        """

    def build_response(
        self,
        opinion: str,
        confidence: float,
        score: float,
        reasoning: str,
        *,
        signals: dict[str, Any] | None = None,
    ) -> AgentResponse:
        """
        서브클래스에서 공통 필드를 채운 ``AgentResponse`` 를 생성합니다.

        Args:
            opinion: 투자 의견 요약.
            confidence: 신뢰도 (0~1).
            score: 에이전트 고유 스코어.
            reasoning: 근거 텍스트.
            signals: 정량 신호 (선택).

        Returns:
            ``agent_name`` 과 타임스탬프가 채워진 응답 객체.
        """
        return AgentResponse(
            opinion=opinion,
            confidence=confidence,
            score=score,
            reasoning=reasoning,
            signals=dict(signals or {}),
            agent_name=self.agent_name,
        )

"""
멀티 에이전트 분석 패키지입니다.

환경 변수는 패키지 임포트 시점에 한 번 로드합니다(.env).
"""

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

from backend.agents.base_agent import BaseAgent
from backend.agents.ceo_agent import CEOOrchestrator, default_agents
from backend.agents.models import AgentResponse, CEOReport, PortfolioAdvice, ScreeningResult

__all__ = [
    "AgentResponse",
    "BaseAgent",
    "CEOReport",
    "CEOOrchestrator",
    "PortfolioAdvice",
    "ScreeningResult",
    "default_agents",
]

"""
CEO 오케스트레이터 — 개별 에이전트 병렬 실행과 종합 의견 산출.
"""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict

from backend.agents.advisor_agent import AdvisorAgent
from backend.agents.claude_client import generate_ceo_summary
from backend.agents.financial_agent import FinancialAgent
from backend.agents.macro_agent import MacroAgent
from backend.agents.models import CEOReport, AgentResponse
from backend.agents.quant_agent import QuantAgent
from backend.agents.risk_agent import RiskAgent
from backend.agents.sector_agent import SectorAgent
from backend.agents.technical_agent import TechnicalAgent

logger = logging.getLogger(__name__)


def _bucket(opinion: str) -> str:
    """의견 문자열을 매수/중립/매도 버킷으로 분류합니다."""
    text = opinion.replace(" ", "")
    if "매도" in text:
        return "sell"
    if "매수" in text:
        return "buy"
    return "neutral"


async def _safe_call(agent: object, ticker: str) -> AgentResponse:
    """예외를 표준 응답으로 흡수합니다."""
    try:
        return await agent.analyze(ticker)  # type: ignore[attr-defined]
    except Exception as exc:
        name = getattr(agent, "agent_name", agent.__class__.__name__)
        logger.exception("에이전트 실행 실패: %s", name)
        return AgentResponse(
            opinion="중립",
            confidence=0.25,
            score=0.0,
            reasoning=f"{name} 실행 오류: {exc}",
            signals={"error": True},
            agent_name=str(name),
        )


def default_agents(holdings: dict[str, float] | None = None) -> list[object]:
    """기본 에이전트 구성을 생성합니다."""
    return [
        FinancialAgent(),
        MacroAgent(),
        TechnicalAgent(),
        RiskAgent(),
        SectorAgent(),
        QuantAgent(),
        AdvisorAgent(holdings=holdings),
    ]


class CEOOrchestrator:
    """에이전트 병렬 호출과 간이 반론 라운드를 담당합니다."""

    def __init__(self, agents: list[object] | None = None) -> None:
        """
        Args:
            agents: 사용자 정의 에이전트 목록. ``None``이면 ``default_agents()`` 사용.
        """
        self.agents: list[object] = agents or default_agents()

    async def run(
        self,
        ticker: str,
        *,
        debate_round: bool = True,
        use_stats_weights: bool = False,
        use_claude_summary: bool = True,
    ) -> CEOReport:
        """
        모든 에이전트를 병렬 실행하고 ``CEOReport`` 를 생성합니다.

        Args:
            ticker: 종목코드.
            debate_round: 재무 vs 리스크 반론 요약 생성 여부.
            use_stats_weights: 성적표 DB 기반 에이전트 신뢰도 가중 적용 여부.
            use_claude_summary: Claude API로 CEO 요약 문장을 보강할지 여부.

        Returns:
            집계 결과 및 개별 보고서.
        """
        # agents 목록의 첫 번째 에이전트로 종목코드 검증해 FinancialAgent 중복 생성을 피합니다
        code = self.agents[0].validate_ticker(ticker)

        mult: dict[str, float] = {}
        stats_applied = False
        if use_stats_weights:
            try:
                from backend.storage.agent_weights import get_agent_confidence_multipliers

                mult = await asyncio.to_thread(get_agent_confidence_multipliers)
                stats_applied = len(mult) > 0
            except Exception as exc:
                logger.warning("성적표 가중치 조회 실패: %s", exc)

        tasks = [_safe_call(agent, code) for agent in self.agents]
        reports: list[AgentResponse] = await asyncio.gather(*tasks)

        weights = defaultdict(float)
        for r in reports:
            m = float(mult.get(r.agent_name, 1.0))
            weights[_bucket(r.opinion)] += max(0.05, float(r.confidence)) * m

        total = sum(weights.values()) or 1.0
        buy_pct = weights["buy"] / total * 100.0
        neutral_pct = weights["neutral"] / total * 100.0
        sell_pct = weights["sell"] / total * 100.0

        ranked = sorted(
            reports,
            key=lambda x: abs(float(x.score))
            * float(x.confidence)
            * float(mult.get(x.agent_name, 1.0)),
            reverse=True,
        )
        summary_lines: list[str] = []
        for r in ranked[:3]:
            snippet = (r.reasoning or "").replace("\n", " ")
            if len(snippet) > 140:
                snippet = snippet[:137] + "..."
            summary_lines.append(
                f"[{r.agent_name}] {r.opinion}(신뢰도 {r.confidence:.0%}) — {snippet}"
            )

        final = "중립"
        if buy_pct >= sell_pct and buy_pct >= neutral_pct and buy_pct >= 38.0:
            final = "매수"
        elif sell_pct >= buy_pct and sell_pct >= neutral_pct and sell_pct >= 38.0:
            final = "매도"

        fin = next((r for r in reports if r.agent_name == "재무"), None)
        risk = next((r for r in reports if r.agent_name == "리스크"), None)
        rebuttal = ""
        if debate_round and fin and risk:
            scenario = ""
            if isinstance(risk.signals, dict):
                scenario = str(risk.signals.get("drawdown_scenario_hint", ""))
            if float(fin.score) >= 12.0 and float(risk.score) <= -12.0:
                rebuttal = (
                    "재무 에이전트가 긍정 신호를 제시했지만, 리스크 에이전트는 변동성·가격 위치 등으로 신중할 것을 권고합니다."
                    + (f" 하방 시나리오 강도 힌트: {scenario}" if scenario else "")
                )
            elif float(fin.score) <= -12.0 and float(risk.score) >= 0.0:
                rebuttal = (
                    "재무 지표는 부담스러나 단기 리스크 지표는 완만할 수 있습니다. "
                    "펀더멘털 개선·업종 전환 여부를 추가 확인하는 것이 타당합니다."
                )

        claude_applied = False
        claude_model: str | None = None
        if use_claude_summary:
            claude_result = await generate_ceo_summary(
                ticker=code,
                final_opinion=final,
                buy_pct=buy_pct,
                neutral_pct=neutral_pct,
                sell_pct=sell_pct,
                summary_lines=summary_lines,
                risk_rebuttal=rebuttal,
                agent_reports=reports,
            )
            if claude_result is not None:
                summary_lines = claude_result.summary_lines
                rebuttal = claude_result.risk_rebuttal
                claude_applied = True
                claude_model = claude_result.model

        return CEOReport(
            ticker=code,
            final_opinion=final,
            buy_pct=buy_pct,
            neutral_pct=neutral_pct,
            sell_pct=sell_pct,
            summary_lines=summary_lines,
            agent_reports=reports,
            risk_rebuttal=rebuttal,
            stats_weights_applied=stats_applied,
            agent_weight_multipliers=dict(mult) if use_stats_weights else {},
            claude_summary_applied=claude_applied,
            claude_model=claude_model,
        )

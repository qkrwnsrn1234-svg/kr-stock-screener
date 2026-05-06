"""
Claude API 호출 유틸리티.

룰 기반 에이전트가 만든 정량 신호를 Claude에 전달해 CEO 요약 문장을 보강합니다.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from typing import Any

from backend.agents.models import AgentResponse

logger = logging.getLogger(__name__)

DEFAULT_CLAUDE_MODEL = "claude-sonnet-4-20250514"
MAX_REASONING_CHARS = 700
MAX_SIGNAL_CHARS = 1200


@dataclass(frozen=True)
class ClaudeSummaryResult:
    """Claude가 생성한 CEO 요약 결과입니다."""

    summary_lines: list[str]
    risk_rebuttal: str
    model: str


def _env_bool(name: str, default: bool = True) -> bool:
    """환경변수 문자열을 불리언으로 해석합니다."""
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def claude_summary_enabled() -> bool:
    """CEO 요약용 Claude 호출 가능 여부를 반환합니다."""
    return bool(os.getenv("ANTHROPIC_API_KEY", "").strip()) and _env_bool(
        "CLAUDE_CEO_SUMMARY_ENABLED",
        True,
    )


def _truncate(text: str, limit: int) -> str:
    """긴 문자열을 프롬프트에 넣기 좋은 길이로 줄입니다."""
    clean = " ".join(text.split())
    if len(clean) <= limit:
        return clean
    return clean[: limit - 3] + "..."


def _compact_agent_report(report: AgentResponse) -> dict[str, Any]:
    """Claude에 전달할 에이전트 보고서를 핵심 필드만 남겨 압축합니다."""
    signals_text = json.dumps(report.signals, ensure_ascii=False, default=str)
    return {
        "agent_name": report.agent_name,
        "opinion": report.opinion,
        "confidence": report.confidence,
        "score": report.score,
        "reasoning": _truncate(report.reasoning or "", MAX_REASONING_CHARS),
        "signals": _truncate(signals_text, MAX_SIGNAL_CHARS),
    }


def _extract_text(message: Any) -> str:
    """Anthropic 응답 객체에서 텍스트 블록을 추출합니다."""
    parts: list[str] = []
    for block in getattr(message, "content", []) or []:
        text = getattr(block, "text", None)
        if isinstance(text, str):
            parts.append(text)
    return "\n".join(parts).strip()


def _parse_json_object(text: str) -> dict[str, Any]:
    """응답 텍스트에서 JSON 객체를 파싱합니다."""
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end <= start:
            raise
        return json.loads(text[start : end + 1])


def _clean_summary_lines(raw: Any) -> list[str]:
    """요약 줄 목록을 최대 3개까지 정리합니다."""
    if not isinstance(raw, list):
        return []
    lines: list[str] = []
    for item in raw:
        line = str(item).strip()
        if line:
            lines.append(line)
    return lines[:3]


async def generate_macro_commentary(
    *,
    ticker: str,
    usd_krw_change_pct: float | None,
    ecos_available: bool,
    signals: dict[str, Any],
) -> str | None:
    """
    거시 지표 신호를 Claude에 전달해 지정학·금리·환율 영향을 서술합니다.

    API 키가 없거나 실패 시 ``None`` 을 반환합니다.
    """
    if not claude_summary_enabled():
        return None

    try:
        from anthropic import AsyncAnthropic
    except ImportError:
        return None

    api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    model = os.getenv("CLAUDE_MODEL", DEFAULT_CLAUDE_MODEL).strip() or DEFAULT_CLAUDE_MODEL
    client = AsyncAnthropic(api_key=api_key)

    # 민감 정보 제거 후 간략화한 signals 전달
    safe_signals = {k: v for k, v in signals.items() if k != "usd_krw_recent"}
    if usd_krw_change_pct is not None:
        safe_signals["usd_krw_change_pct_3obs"] = round(usd_krw_change_pct, 4)

    system_prompt = (
        "당신은 한국 주식 AI 분석 시스템의 거시경제 에이전트입니다. "
        "주어진 거시 지표를 근거로 해당 종목 섹터에 미치는 영향을 2~4문장으로 요약하세요. "
        "투자 권유 표현은 쓰지 마세요."
    )
    user_prompt = (
        f"종목코드: {ticker}\n"
        f"ECOS 데이터 조회 가능: {ecos_available}\n"
        f"거시 지표 요약(JSON): {json.dumps(safe_signals, ensure_ascii=False, default=str)}\n\n"
        "위 데이터를 근거로 현재 거시 환경이 이 종목의 업종에 미치는 영향을 "
        "지정학 리스크·금리·환율 관점을 포함해 한국어로 2~4문장 서술하세요. "
        "순수 텍스트로만 반환하세요."
    )

    try:
        message = await client.messages.create(
            model=model,
            max_tokens=400,
            temperature=0.3,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )
        text = _extract_text(message).strip()
        return text if text else None
    except Exception as exc:
        logger.warning("Claude 거시 코멘터리 생성 실패: %s", exc)
        return None


async def generate_ceo_summary(
    *,
    ticker: str,
    final_opinion: str,
    buy_pct: float,
    neutral_pct: float,
    sell_pct: float,
    summary_lines: list[str],
    risk_rebuttal: str,
    agent_reports: list[AgentResponse],
) -> ClaudeSummaryResult | None:
    """
    에이전트 결과를 Claude에 전달해 CEO 요약과 리스크 반론을 생성합니다.

    API 키가 없거나 호출 실패 시 ``None`` 을 반환해 기존 룰 기반 결과를 유지합니다.
    """
    if not claude_summary_enabled():
        return None

    try:
        from anthropic import AsyncAnthropic
    except ImportError as exc:
        logger.warning("anthropic 패키지가 없어 Claude CEO 요약을 건너뜁니다: %s", exc)
        return None

    api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    model = os.getenv("CLAUDE_MODEL", DEFAULT_CLAUDE_MODEL).strip() or DEFAULT_CLAUDE_MODEL
    client = AsyncAnthropic(api_key=api_key)

    payload = {
        "ticker": ticker,
        "rule_based_result": {
            "final_opinion": final_opinion,
            "buy_pct": round(buy_pct, 2),
            "neutral_pct": round(neutral_pct, 2),
            "sell_pct": round(sell_pct, 2),
            "summary_lines": summary_lines,
            "risk_rebuttal": risk_rebuttal,
        },
        "agent_reports": [_compact_agent_report(r) for r in agent_reports],
    }

    system_prompt = (
        "당신은 한국 주식 멀티에이전트 분석 시스템의 CEO 에이전트입니다. "
        "정량 에이전트들의 결과를 종합하되 숫자와 최종 의견은 임의로 바꾸지 마세요. "
        "투자 권유가 아니라 분석 요약 문장만 작성하세요."
    )
    user_prompt = (
        "아래 JSON을 읽고 한국어로 CEO 요약을 작성하세요.\n"
        "반드시 JSON 객체만 반환하세요. 형식: "
        '{"summary_lines":["핵심 근거 1","핵심 근거 2","핵심 근거 3"],"risk_rebuttal":"리스크 반론 또는 빈 문자열"}\n'
        "summary_lines는 정확히 1~3개, 각 줄은 120자 이내로 작성하세요.\n\n"
        f"{json.dumps(payload, ensure_ascii=False, default=str)}"
    )

    try:
        message = await client.messages.create(
            model=model,
            max_tokens=700,
            temperature=0.2,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )
        parsed = _parse_json_object(_extract_text(message))
        lines = _clean_summary_lines(parsed.get("summary_lines"))
        if not lines:
            return None
        return ClaudeSummaryResult(
            summary_lines=lines,
            risk_rebuttal=str(parsed.get("risk_rebuttal") or "").strip(),
            model=model,
        )
    except Exception as exc:
        logger.warning("Claude CEO 요약 생성 실패(룰 기반 결과 유지): %s", exc)
        return None

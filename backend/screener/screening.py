"""
CEO 분석 보고서와 업종 상대 밸류를 결합해 스크리닝 결과를 만듭니다.
"""

from __future__ import annotations

from typing import Any

from backend.agents.models import (
    CEOReport,
    OverheatAlert,
    ScreeningResult,
    UndervalueBreakdown,
)
from backend.screener.peer_valuation import SectorPeerStats, fetch_sector_peer_stats

# 언더밸류 가중치 (합계 1.0)
# FCF가 실측값으로 채워지면 W_FCF를 활성화하고 나머지를 비례 축소합니다
W_PER = 0.32
W_PBR = 0.28
W_FCF = 0.10
W_FSCORE = 0.30
# FCF 미연동 상태에서 PER·PBR·FSCORE만으로 계산할 때 사용하는 정규화 분모
_W_NO_FCF = W_PER + W_PBR + W_FSCORE  # 0.90

# 과열 heat_score 구간 → 등급
THR_NOTICE = 18.0
THR_WARN = 38.0
THR_DANGER = 60.0


def _agent_by_name(reports: list[Any], name: str) -> Any | None:
    """에이전트 이름으로 첫 응답을 찾습니다."""
    for r in reports:
        if getattr(r, "agent_name", "") == name:
            return r
    return None


def _safe_float(v: Any) -> float | None:
    try:
        if v is None:
            return None
        return float(v)
    except (TypeError, ValueError):
        return None


def _ratio_value_score(ratio: float) -> float:
    """
    PER·PBR 공통: 동종 중앙값 대비 비율이 낮을수록(저평가) 점수 높음.
    """
    if ratio <= 0.6:
        return 92.0
    if ratio <= 0.85:
        return 78.0
    if ratio <= 1.0:
        return 62.0
    if ratio <= 1.2:
        return 48.0
    if ratio <= 1.5:
        return 36.0
    return 24.0


def _per_component(stock_per: float | None, peer_med: float | None) -> float:
    if stock_per is None or peer_med is None or peer_med <= 0:
        return 50.0
    if stock_per <= 0:
        return 28.0
    return _ratio_value_score(stock_per / peer_med)


def _pbr_component(stock_pbr: float | None, peer_med: float | None) -> float:
    if stock_pbr is None or peer_med is None or peer_med <= 0:
        return 50.0
    if stock_pbr <= 0:
        return 50.0
    return _ratio_value_score(stock_pbr / peer_med)


def _fscore_component(piotroski_like: int | None) -> float:
    if piotroski_like is None:
        return 50.0
    p = max(0, min(9, int(piotroski_like)))
    return float(p) / 9.0 * 100.0


def _build_undervalue_breakdown(
    fin_sig: dict[str, Any],
    quant_sig: dict[str, Any],
    peer: SectorPeerStats,
) -> UndervalueBreakdown:
    stock_per = _safe_float(fin_sig.get("per"))
    stock_pbr = _safe_float(fin_sig.get("pbr"))
    p_like = quant_sig.get("piotroski_like")
    pi_int: int | None
    try:
        pi_int = int(p_like) if p_like is not None else None
    except (TypeError, ValueError):
        pi_int = None

    per_s = _per_component(stock_per, peer.median_per)
    pbr_s = _pbr_component(stock_pbr, peer.median_pbr)
    fsc_s = _fscore_component(pi_int)

    # FCF Yield가 실측값으로 채워지기 전까지는 해당 가중치를 제외하고
    # 나머지 3개 가중치 합(0.90)으로 정규화합니다
    fcf_s: float | None = None
    fcf_note = "FCF Yield는 DART 현금흐름표 연동 후 반영 예정(현재 계산에서 제외)"
    combined = (W_PER * per_s + W_PBR * pbr_s + W_FSCORE * fsc_s) / _W_NO_FCF

    return UndervalueBreakdown(
        per_score=per_s,
        pbr_score=pbr_s,
        fcf_yield_score=0.0,  # 미연동 상태임을 프론트에 표시
        fscore_score=fsc_s,
        combined=max(0.0, min(100.0, float(combined))),
        peer_count=peer.peer_count,
        sector_label=peer.sector_label,
        fcf_note=fcf_note,
    )


def _build_overheat_alert(
    tech_sig: dict[str, Any],
    stock_per: float | None,
    peer_med_per: float | None,
) -> OverheatAlert:
    heat = 0.0
    reasons: list[str] = []

    rsi = _safe_float(tech_sig.get("rsi_14"))
    if rsi is not None and rsi >= 70.0:
        heat += min(42.0, 16.0 + (rsi - 70.0) * 2.2)
        reasons.append(f"RSI {rsi:.1f} (≥70 과매수 구간)")

    if (
        stock_per is not None
        and peer_med_per is not None
        and peer_med_per > 0
        and stock_per > 0
    ):
        if stock_per >= 2.0 * peer_med_per:
            heat += 34.0
            reasons.append("PER이 업종 중앙값의 2배 초과(밸류 부담)")
        elif stock_per >= 1.5 * peer_med_per:
            heat += 16.0
            reasons.append("PER이 업종 중앙값의 1.5배 이상")

    vol_r = _safe_float(tech_sig.get("volume_vs_ma20_ratio"))
    if vol_r is not None:
        if vol_r >= 3.0:
            heat += 24.0
            reasons.append(f"거래량 20일 평균 대비 {vol_r:.1f}배(급등)")
        elif vol_r >= 2.5:
            heat += 12.0
            reasons.append(f"거래량 20일 평균 대비 {vol_r:.1f}배(다소 급등)")

    heat = max(0.0, min(100.0, heat))

    if heat >= THR_DANGER:
        level = "위험"
    elif heat >= THR_WARN:
        level = "경고"
    elif heat >= THR_NOTICE:
        level = "주의"
    else:
        level = "정상"

    return OverheatAlert(level=level, heat_score=heat, reasons=reasons)


async def build_screening_result(report: CEOReport) -> ScreeningResult:
    """
    CEO 보고서와 업종 상대 밸류를 합쳐 ``ScreeningResult`` 를 생성합니다.

    Args:
        report: ``CEOOrchestrator.run`` 결과.

    Returns:
        언더밸류·과열 상세가 채워진 스크리닝 레코드.
    """
    fin = _agent_by_name(report.agent_reports, "재무")
    quant = _agent_by_name(report.agent_reports, "퀀트")
    tech = _agent_by_name(report.agent_reports, "기술적")

    fin_sig: dict[str, Any] = fin.signals if fin and isinstance(fin.signals, dict) else {}
    quant_sig: dict[str, Any] = quant.signals if quant and isinstance(quant.signals, dict) else {}
    tech_sig: dict[str, Any] = tech.signals if tech and isinstance(tech.signals, dict) else {}

    peer = await fetch_sector_peer_stats(report.ticker)
    breakdown = _build_undervalue_breakdown(fin_sig, quant_sig, peer)
    stock_per = _safe_float(fin_sig.get("per"))
    alert = _build_overheat_alert(tech_sig, stock_per, peer.median_per)

    return ScreeningResult(
        ticker=report.ticker,
        undervalue_score=breakdown.combined,
        overheat_flag=alert.level != "정상",
        undervalue_breakdown=breakdown,
        overheat_alert=alert,
        agent_reports=list(report.agent_reports),
    )

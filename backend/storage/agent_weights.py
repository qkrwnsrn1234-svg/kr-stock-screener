"""
저장된 성과 통계로 에이전트별 신뢰도 가중 배수를 산출합니다.

CEO 집계 시 ``confidence`` 합산에 곱합니다. 표본이 적으면 배수를 적용하지 않습니다.
"""

from __future__ import annotations

import time

from backend.storage.analysis_history import compute_agent_performance

# 배수를 믿을 최소 표본 수
MIN_SAMPLES_FOR_WEIGHT = 8

# 동일 프로세스에서 DB 전체 스캔 반복 방지(초)
_MULTIPLIER_CACHE_TTL_SEC = 300.0
_mult_cache: dict[str, tuple[float, dict[str, float]]] = {}


def _rate_to_multiplier(hit_rate: float) -> float:
    """적중률을 신뢰도 배수(0.88~1.12 근방)로 매핑합니다."""
    if hit_rate >= 0.58:
        return 1.12
    if hit_rate >= 0.52:
        return 1.06
    if hit_rate <= 0.38:
        return 0.88
    if hit_rate <= 0.45:
        return 0.94
    return 1.0


def get_agent_confidence_multipliers(horizon: int = 30) -> dict[str, float]:
    """
    ``/agents/stats`` 와 동일한 DB·규칙으로, 이미 채워진 선행수익률만 사용해 가중치를 계산합니다.

    동일 ``horizon`` 에 대해 짧은 TTL 동안 결과를 재사용합니다(다종목 분석 시 부하 완화).

    Args:
        horizon: 30·60·90 거래일 축.

    Returns:
        에이전트 표시명 → 배수. 기록이 없으면 빈 dict.
    """
    key = str(int(horizon))
    now = time.monotonic()
    hit = _mult_cache.get(key)
    if hit is not None and now - hit[0] < _MULTIPLIER_CACHE_TTL_SEC:
        return dict(hit[1])

    raw = compute_agent_performance(trading_horizon=horizon, fill_missing_returns=False)
    out: dict[str, float] = {}
    for row in raw.get("by_agent", []):
        name = str(row.get("agent_name") or "").strip()
        samples = int(row.get("samples") or 0)
        rate = row.get("hit_rate")
        if not name or samples < MIN_SAMPLES_FOR_WEIGHT or rate is None:
            continue
        out[name] = _rate_to_multiplier(float(rate))
    _mult_cache[key] = (now, out)
    return dict(out)

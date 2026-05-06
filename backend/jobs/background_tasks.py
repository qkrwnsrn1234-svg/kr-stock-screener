"""
앱 수명 주기에 묶인 백그라운드 주기 작업입니다.

외부 API 부하를 줄이기 위해 상장 종목 메타 등 자주 쓰이는 캐시를
일정 간격으로 미리 갱신(워밍)합니다.
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

# 너무 짧은 간격 방지 (초)
_MIN_INTERVAL_SEC = 60
_MAX_INTERVAL_SEC = 86400

_DEFAULT_INTERVAL = 3600


def _env_flag(name: str, default: bool = False) -> bool:
    """환경 변수를 참/거짓으로 해석합니다."""
    raw = os.getenv(name, "")
    if not raw:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def scheduler_interval_seconds() -> int:
    """스케줄러 주기(초)를 환경 변수에서 읽어 클램프합니다."""
    try:
        v = int(os.getenv("SCHEDULER_INTERVAL_SECONDS", str(_DEFAULT_INTERVAL)))
    except ValueError:
        return _DEFAULT_INTERVAL
    return max(_MIN_INTERVAL_SEC, min(_MAX_INTERVAL_SEC, v))


def scheduler_enabled() -> bool:
    """백그라운드 스케줄러 활성 여부."""
    return _env_flag("SCHEDULER_ENABLED", default=False)


def run_refresh_tick() -> dict[str, Any]:
    """
    한 번의 스케줄러 틱에서 수행할 동기 작업입니다.

    Returns:
        로그·모니터링용 요약 dict (예: 워밍한 리소스 이름).
    """
    from backend.data.finance_data import list_krx_symbols

    # TTL 캐시가 있으면 히트, 만료 시에만 FDR 호출
    df = list_krx_symbols("KRX")
    rows = int(len(df))
    logger.info("스케줄러 틱: KRX 상장목록 워밍 완료 rows=%s", rows)
    return {"task": "listing_warm", "market": "KRX", "rows": rows}


async def scheduler_loop(stop: asyncio.Event) -> None:
    """
    주기적으로 ``run_refresh_tick``을 실행하는 비동기 루프입니다.

    Args:
        stop: 종료 신호. 설정 시 루프를 빠져나갑니다.
    """
    interval = scheduler_interval_seconds()
    logger.info(
        "백그라운드 스케줄러 시작 interval_sec=%s (SCHEDULER_ENABLED=true)",
        interval,
    )
    # 기동 직후 한 번 워밍 (요청 전 캐시 프라임)
    try:
        await asyncio.to_thread(run_refresh_tick)
    except Exception:
        logger.exception("초기 스케줄러 틱 실패")
    while not stop.is_set():
        try:
            await asyncio.wait_for(stop.wait(), timeout=float(interval))
            break
        except asyncio.TimeoutError:
            pass
        except asyncio.CancelledError:
            break
        try:
            await asyncio.to_thread(run_refresh_tick)
        except Exception:
            logger.exception("스케줄러 틱 처리 중 오류")

    logger.info("백그라운드 스케줄러 종료")

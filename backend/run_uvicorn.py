"""
uvicorn 진입점 — Phase 5 기본 포트(18000) 및 포트 선점 시 자동 대체 바인드를 지원합니다.

사용법: ``PYTHONPATH=. python -m backend.run_uvicorn`` (저장소 루트에서)
"""

from __future__ import annotations

import logging
import os

import uvicorn
from dotenv import load_dotenv

from backend.utils.server_port import (
    pick_listen_tcp_port,
    read_preferred_http_port,
    server_port_autoscan_enabled,
)

logger = logging.getLogger(__name__)


def _read_bind_host() -> str:
    """컨테이너에서는 0.0.0.0, 로컬 기본값은 127.0.0.1."""
    raw = os.getenv("BIND_HOST") or os.getenv("UVICORN_HOST")
    host = raw.strip() if raw else ""
    if host:
        return host
    return "127.0.0.1"


def _parse_bool_strict(raw: str | None, default: bool = False) -> bool:
    if raw is None or not raw.strip():
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def main() -> None:
    """선호 포트를 결정한 뒤 uvicorn 서버를 띄웁니다."""
    load_dotenv()
    logging.basicConfig(level=logging.INFO)

    bind_host = _read_bind_host()
    preferred = read_preferred_http_port()

    autoscan_default = bind_host.strip() != "0.0.0.0"
    autoscan = server_port_autoscan_enabled(default=autoscan_default)
    autoscan_explicit = os.getenv("SERVER_PORT_AUTOSCAN")

    chosen, used_fallback = pick_listen_tcp_port(
        bind_host, preferred_port=preferred, autoscan=autoscan
    )

    if used_fallback:
        logger.warning(
            "선호 포트 %s 가 사용 중이어서 %s 로 바인드합니다.(SERVER_PORT_AUTOSCAN=%s)",
            preferred,
            chosen,
            autoscan_explicit if autoscan_explicit else ("true" if autoscan else "false"),
        )

    os.environ["KR_STOCK_ACTUAL_HTTP_PORT"] = str(chosen)

    reload_enabled = _parse_bool_strict(os.getenv("SERVER_DEV_RELOAD"))
    logger.info(
        "KR Stock Screener 리스닝: host=%s port=%s (선호 PORT=%s, autoscan=%s)",
        bind_host,
        chosen,
        preferred,
        autoscan,
    )

    uvicorn.run(
        "backend.main:app",
        host=bind_host,
        port=chosen,
        reload=reload_enabled,
        factory=False,
    )


if __name__ == "__main__":
    main()

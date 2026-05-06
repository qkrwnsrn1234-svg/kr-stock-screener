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


def resolve_listen_config(*, load_env: bool = True) -> tuple[str, int, bool]:
    """
    ``BIND_HOST``·``PORT``·``SERVER_PORT_AUTOSCAN`` 에 따라 바인드 주소와 포트를 결정합니다.

    ``KR_STOCK_ACTUAL_HTTP_PORT`` 환경 변수를 설정한 뒤 ``(바인드 주소, 포트, 폴백 여부)``
    튜플을 반환합니다. pywebview 등 별도 스레드에서 uvicorn 을 붙일 때 재사용합니다.

    Args:
        load_env: True면 시작 시 ``load_dotenv()`` 를 한 번 호출합니다.
            이미 불렀거나 ``BIND_HOST`` 를 먼저 덮어쓸 때는 ``False`` 로 호출합니다.
    """
    if load_env:
        load_dotenv()

    bind_host = _read_bind_host()
    preferred = read_preferred_http_port()
    autoscan_default = bind_host.strip() != "0.0.0.0"
    autoscan = server_port_autoscan_enabled(default=autoscan_default)
    autoscan_explicit = os.getenv("SERVER_PORT_AUTOSCAN")

    chosen, used_fallback = pick_listen_tcp_port(
        bind_host, preferred_port=preferred, autoscan=autoscan
    )

    os.environ["KR_STOCK_ACTUAL_HTTP_PORT"] = str(chosen)

    if used_fallback:
        logger.warning(
            "선호 포트 %s 가 사용 중이어서 %s 로 바인드합니다.(SERVER_PORT_AUTOSCAN=%s)",
            preferred,
            chosen,
            autoscan_explicit if autoscan_explicit else ("true" if autoscan else "false"),
        )

    return bind_host, chosen, used_fallback


def main() -> None:
    """선호 포트를 결정한 뒤 uvicorn 서버를 띄웁니다."""
    logging.basicConfig(level=logging.INFO)

    bind_host, chosen, _used_fallback = resolve_listen_config()

    reload_enabled = _parse_bool_strict(os.getenv("SERVER_DEV_RELOAD"))
    autoscan_default = bind_host.strip() != "0.0.0.0"
    autoscan = server_port_autoscan_enabled(default=autoscan_default)

    logger.info(
        "KR Stock Screener 리스닝: host=%s port=%s (선호 PORT=%s, autoscan=%s)",
        bind_host,
        chosen,
        read_preferred_http_port(),
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

"""
HTTP 서버 바인드 포트 결정(기본값·환경변수·선점 시 다음 포트 자동 선택).
"""

from __future__ import annotations

import os
import socket


# Phase 5 단일 실행·데스크톱 기본값 (DOCKER_PORT 등 플랫폼에서는 PORT 로 덮어씁니다.)
DEFAULT_HTTP_PORT = 18000

# 포트 순회 시 최대 탐색 횟수
_MAX_PORT_PROBE = int(os.getenv("SERVER_PORT_SCAN_MAX_ATTEMPTS", "64"))


def _parse_bool(raw: str | None, default: bool) -> bool:
    """환경 문자열을 불린으로 바꿉니다."""
    if raw is None or not raw.strip():
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def server_port_autoscan_enabled(default: bool = True) -> bool:
    """선호 포트가 사용 중일 때 다음 빈 포트를 쓸지 여부입니다."""
    return _parse_bool(os.getenv("SERVER_PORT_AUTOSCAN"), default)


def read_preferred_http_port() -> int:
    """
    사용자·호스팅이 지정한 선호 포트를 읽습니다.

    우선순위: 환경 변수 ``PORT``. 미설정 시 ``DEFAULT_HTTP_PORT``.

    Raises:
        ValueError: 포트 문자열이 잘못되었거나 1~65535 범위를 벗어날 때.
    """
    raw = os.getenv("PORT")
    port_s = raw.strip() if raw else str(DEFAULT_HTTP_PORT)
    try:
        port = int(port_s)
    except ValueError as exc:
        raise ValueError(f"PORT는 정수여야 합니다: {raw!r}") from exc
    if not (1 <= port <= 65535):
        raise ValueError(f"PORT 범위는 1~65535 입니다: {port}")
    return port


def is_tcp_bind_available(bind_host: str, port: int) -> bool:
    """
    지정 호스트에 TCP 바인드를 시험하여 사용 가능하면 True입니다.

    Args:
        bind_host: ``127.0.0.1`` 또는 ``0.0.0.0`` 등 바인드 대상 주소.
        port: 검사할 포트.
    """
    if not (1 <= port <= 65535):
        return False
    # IPv6 주소(콜론 포함)는 AF_INET6, 그 외는 IPv4로 시도
    fam = socket.AF_INET6 if ":" in bind_host.strip() else socket.AF_INET

    sock = socket.socket(fam, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        sock.bind((bind_host, port))
    except OSError:
        sock.close()
        return False
    sock.close()
    return True


def pick_listen_tcp_port(bind_host: str, preferred_port: int, autoscan: bool) -> tuple[int, bool]:
    """
    실제 바인드에 사용할 TCP 포트를 고릅니다.

    Args:
        bind_host: uvicorn 과 동일한 바인드 주소.
        preferred_port: 선호 시작 포트(보통 PORT 환경).
        autoscan: False면 선호 포트만 시도합니다.

    Returns:
        ``(chosen_port, was_fallback)``
        ``was_fallback`` 은 선호 포트 외 다른 포트를 택했을 때 True.

    Raises:
        RuntimeError: 사용 가능한 포트를 찾지 못한 경우.
    """
    attempts = max(1, min(_MAX_PORT_PROBE, 256))
    if not autoscan:
        if not is_tcp_bind_available(bind_host, preferred_port):
            raise RuntimeError(
                f"포트 {preferred_port} 에 바인드할 수 없습니다. "
                f"다른 프로세스를 종료하거나 PORT 를 바꿔 보세요."
            )
        return preferred_port, False

    for delta in range(attempts):
        candidate = preferred_port + delta
        if candidate > 65535:
            break
        if is_tcp_bind_available(bind_host, candidate):
            return candidate, delta != 0

    raise RuntimeError(
        f"{preferred_port} 부터 최대 {attempts}개 포트를 조사했으나 빈 포트가 없습니다. "
        "SERVER_PORT_SCAN_MAX_ATTEMPTS 또는 PORT 설정을 확인하세요."
    )

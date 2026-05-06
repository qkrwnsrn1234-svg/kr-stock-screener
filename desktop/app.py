"""
pywebview 네이티브 창 — FastAPI(uvicorn)를 별도 프로세스로 띄운 뒤 SPA 를 표시합니다.

저장소 루트에서: ``PYTHONPATH=. python -m desktop.app``
(또는 동일 효과로 ``python -m desktop.app`` 실행 전 ``PYTHONPATH``에 루트 경로 포함)
"""

from __future__ import annotations

import logging
import multiprocessing
import os
import sys
import time
import urllib.request
from pathlib import Path

logger = logging.getLogger(__name__)


def _ensure_repo_on_path() -> Path:
    """``backend`` 임포트를 위해 프로젝트 루트(번들이면 ``_MEIPASS``)를 ``sys.path`` 앞에 둡니다."""
    if getattr(sys, "frozen", False) and getattr(sys, "_MEIPASS", None):
        repo = Path(str(sys._MEIPASS))
    else:
        repo = Path(__file__).resolve().parent.parent
    root = str(repo)
    if root not in sys.path:
        sys.path.insert(0, root)
    return repo


def _parse_bool(raw: str | None, default: bool = False) -> bool:
    """환경 문자열을 불린으로 바꿉니다."""
    if raw is None or not raw.strip():
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def _wait_http_ok(url: str, timeout_sec: float, interval_sec: float = 0.25) -> None:
    """
    ``url`` 에 GET 이 200 이 될 때까지 대기합니다(백엔드 기동 대기).

    Raises:
        RuntimeError: ``timeout_sec`` 안에 준비되지 않을 때.
    """
    deadline = time.monotonic() + timeout_sec
    last_exc: BaseException | None = None
    while time.monotonic() < deadline:
        try:
            req = urllib.request.Request(url, headers={"Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=2.0) as resp:
                if getattr(resp, "status", None) == 200 or resp.getcode() == 200:
                    return
        except Exception as exc:
            last_exc = exc
        time.sleep(interval_sec)
    detail = repr(last_exc) if last_exc else "알 수 없음"
    raise RuntimeError(f"헬스체크 타임아웃({timeout_sec:.0f}s): {url} / 마지막 오류: {detail}")


def _shutdown_process(proc: multiprocessing.Process, *, label: str) -> None:
    """uvicorn 자식 프로세스를 종료합니다."""
    if not proc.is_alive():
        return
    logger.info("%s 프로세스 종료 시도(pid=%s)", label, proc.pid)
    proc.terminate()
    proc.join(timeout=30)
    if proc.is_alive():
        logger.warning("%s 프로세스가 살아 있어 kill 합니다.", label)
        proc.kill()
        proc.join(timeout=5)


def _uvicorn_worker(bind_host: str, port: int, log_level: str, access_log: bool) -> None:
    """
    별도 프로세스에서 uvicorn 을 실행합니다.

    ``multiprocessing`` spawn 시 자식 인터프리터가 임포트할 수 있도록
    모듈 최상단에 가깝게 두었습니다.
    """
    import uvicorn

    uvicorn.run(
        "backend.main:app",
        host=bind_host,
        port=port,
        log_level=log_level,
        access_log=access_log,
        factory=False,
        reload=False,
    )


def main() -> None:
    """환경을 읽고 uvicorn 을 띄운 뒤 pywebview 창을 엽니다."""
    from desktop.frozen_env import apply_frozen_runtime, user_data_dir

    apply_frozen_runtime()
    repo = _ensure_repo_on_path()

    from dotenv import load_dotenv

    if getattr(sys, "frozen", False):
        load_dotenv(user_data_dir() / ".env")
    else:
        load_dotenv(repo / ".env")
    load_dotenv()

    # 데스크톱은 로컬 뷰어만 — LAN 바인드 방지
    os.environ["BIND_HOST"] = "127.0.0.1"
    os.environ["PYTHONPATH"] = str(repo)

    from backend.run_uvicorn import resolve_listen_config

    log_level_desktop = os.getenv("DESKTOP_LOG_LEVEL", "INFO").upper()
    logging.basicConfig(level=getattr(logging, log_level_desktop, logging.INFO))

    bind_host, port, _used_fallback = resolve_listen_config(load_env=False)

    uv_log = os.getenv("DESKTOP_UVICORN_LOG_LEVEL", "warning").strip()
    access_log = _parse_bool(os.getenv("DESKTOP_UVICORN_ACCESS_LOG"), False)

    proc = multiprocessing.Process(
        target=_uvicorn_worker,
        args=(bind_host, port, uv_log, access_log),
        name="kr-stock-uvicorn",
        daemon=False,
    )
    proc.start()

    base_url = f"http://127.0.0.1:{port}"
    try:
        startup_timeout = float(os.getenv("DESKTOP_STARTUP_TIMEOUT_SEC", "90"))
    except ValueError:
        startup_timeout = 90.0

    try:
        _wait_http_ok(f"{base_url}/api/health", startup_timeout)
    except Exception:
        _shutdown_process(proc, label="uvicorn")
        raise

    try:
        import webview
    except ImportError as exc:
        _shutdown_process(proc, label="uvicorn")
        raise RuntimeError(
            "pywebview 가 설치되어 있지 않습니다. `pip install pywebview` 또는 requirements.txt 를 설치하세요."
        ) from exc

    title = os.getenv("DESKTOP_WINDOW_TITLE", "KR Stock Screener").strip() or "KR Stock Screener"

    try:
        w = int(os.getenv("DESKTOP_WINDOW_WIDTH", "1400"))
        h = int(os.getenv("DESKTOP_WINDOW_HEIGHT", "880"))
    except ValueError:
        w, h = 1400, 880

    try:
        mw = int(os.getenv("DESKTOP_WINDOW_MIN_WIDTH", "1280"))
        mh = int(os.getenv("DESKTOP_WINDOW_MIN_HEIGHT", "720"))
    except ValueError:
        mw, mh = 1280, 720

    icon_raw = os.getenv("DESKTOP_ICON_PATH", "").strip()
    icon_path: str | None = None
    if icon_raw:
        ip = Path(icon_raw).expanduser()
        if ip.is_file():
            icon_path = str(ip)
        else:
            logger.warning("DESKTOP_ICON_PATH 파일이 없습니다: %s", ip)

    window = webview.create_window(
        title,
        url=f"{base_url}/",
        width=w,
        height=h,
        min_size=(mw, mh),
        resizable=_parse_bool(os.getenv("DESKTOP_WINDOW_RESIZABLE"), True),
    )

    def _on_closed() -> None:
        _shutdown_process(proc, label="uvicorn")

    window.events.closed += _on_closed

    logger.info("데스크톱 창 오픈: %s (백엔드 %s)", base_url, port)
    webview.start(
        debug=_parse_bool(os.getenv("DESKTOP_WEBVIEW_DEBUG")),
        icon=icon_path,
    )

    _shutdown_process(proc, label="uvicorn")


if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()

"""
PyInstaller로 고정(``sys.frozen``) 실행될 때 번들·사용자 데이터 경로를 맞춥니다.
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

_APPLIED = False


def user_data_dir() -> Path:
    """
    SQLite·캐시·``.env`` 를 둘 사용자별 디렉터리입니다.

    Returns:
        OS별 Application Support / AppData Local / XDG 스타일 경로.
    """
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "KRStockScreener"
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA", "").strip()
        if base:
            return Path(base) / "KRStockScreener"
        return Path.home() / "AppData" / "Local" / "KRStockScreener"
    return Path.home() / ".local" / "share" / "KRStockScreener"


def bundle_root() -> Path | None:
    """번들 추출 루트(``_MEIPASS``)입니다. 개발 실행 시에는 ``None``."""
    if not getattr(sys, "frozen", False):
        return None
    raw = getattr(sys, "_MEIPASS", None)
    if not raw:
        return None
    return Path(str(raw))


def apply_frozen_runtime() -> None:
    """
    첫 기동 시 사용자 디렉터리를 만들고, 번들에 동봉된 ``.env.example`` 을
    사용자 ``.env`` 로 복사합니다(이미 있으면 덮어쓰지 않음).

    환경 변수 ``FRONTEND_DIST_DIR`` ``ANALYSIS_DB_PATH`` 등을 설정합니다.
    """
    global _APPLIED
    if _APPLIED:
        return
    _APPLIED = True

    if not getattr(sys, "frozen", False):
        return

    bundle = bundle_root()
    if bundle is None:
        return

    data_root = user_data_dir()
    (data_root / "data").mkdir(parents=True, exist_ok=True)
    (data_root / "data" / "cache").mkdir(parents=True, exist_ok=True)

    env_dst = data_root / ".env"
    example_src = bundle / ".env.example"
    if example_src.is_file() and not env_dst.is_file():
        try:
            shutil.copyfile(example_src, env_dst)
        except OSError:
            pass

    os.environ["PYTHONPATH"] = str(bundle)
    os.environ.setdefault("FRONTEND_DIST_DIR", str(bundle / "frontend" / "dist"))
    os.environ.setdefault("ANALYSIS_DB_PATH", str(data_root / "data" / "analysis_history.db"))
    os.environ.setdefault("WATCHLIST_DB_PATH", str(data_root / "data" / "watchlist.db"))
    os.environ.setdefault("KR_STOCK_CACHE_DIR", str(data_root / "data" / "cache"))

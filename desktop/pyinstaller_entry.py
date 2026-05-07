"""
PyInstaller 부트스트랩 — 진입점은 ``desktop.app:main`` 과 동일합니다.
"""

from __future__ import annotations

import multiprocessing
import sys
import traceback
from pathlib import Path


def _report_frozen_startup_failure() -> None:
    """번들 시작 예외를 파일로 남기고 macOS 에서 사용자에게 알립니다."""
    log_path = Path.home() / "desktop_startup_error.log"
    try:
        from desktop.frozen_env import user_data_dir

        log_path = user_data_dir() / "desktop_startup_error.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    try:
        log_path.write_text(traceback.format_exc(), encoding="utf-8")
    except OSError:
        return

    if sys.platform == "darwin":
        import subprocess

        subprocess.run(["open", "-e", str(log_path)], check=False)
        subprocess.run(
            [
                "osascript",
                "-e",
                'display alert "KR Stock Screener" message "시작에 실패했습니다. 원인은 TextEdit으로 연 로그 파일을 확인하세요."',
            ],
            check=False,
        )


if __name__ == "__main__":
    multiprocessing.freeze_support()
    try:
        from desktop.app import main

        main()
    except BaseException:
        _report_frozen_startup_failure()
        sys.exit(1)

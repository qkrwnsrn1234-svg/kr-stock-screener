"""
PyInstaller 부트스트랩 — 진입점은 ``desktop.app:main`` 과 동일합니다.
"""

from __future__ import annotations

import multiprocessing

if __name__ == "__main__":
    multiprocessing.freeze_support()
    from desktop.app import main

    main()

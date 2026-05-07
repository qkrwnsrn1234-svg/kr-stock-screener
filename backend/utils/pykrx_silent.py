"""
pykrx 패키지는 import 시 KRX 인증 미설정 안내를 ``print()`` 로 내보냅니다.

서버·데스크톱 로그를 오염시키지 않도록 최초 로드 구간에서만 stdout 을 일시 리다이렉트합니다.
"""

from __future__ import annotations

import contextlib
import io

with contextlib.redirect_stdout(io.StringIO()):
    from pykrx import stock

__all__ = ["stock"]

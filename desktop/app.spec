# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller 스펙 — ``./scripts/build_desktop.sh`` 또는 ``pyinstaller desktop/app.spec`` 로 빌드.

사전 조건: ``frontend/dist`` 존재(``npm run build``).
"""

import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_submodules

# PyInstaller 는 spec 실행 시 ``SPECPATH``(spec 파일이 있는 디렉터리)를 주입합니다.
_APP_SPEC_DIR = Path(SPECPATH).resolve()  # type: ignore[name-defined]
_APP_ROOT = _APP_SPEC_DIR.parent

_entry = str(_APP_SPEC_DIR / "pyinstaller_entry.py")

_pathex = [str(_APP_ROOT)]

# 문제가 되기 쉬운 패키지는 collect_all 로 데이터·숨김 임포트 보강
_datas_acc: list = []
_binaries_acc: list = []
_hidden_acc: list = []

for _pkg in (
    "uvicorn",
    "fastapi",
    "starlette",
    "FinanceDataReader",
    "pykrx",
    "webview",
    "watchfiles",
    "anyio",
    "websockets",
):
    try:
        d, b, h = collect_all(_pkg)
        _datas_acc += d
        _binaries_acc += b
        _hidden_acc += h
    except Exception:
        pass

_datas_extra: list = []
_frontend_dist = _APP_ROOT / "frontend" / "dist"
if _frontend_dist.is_dir():
    _datas_extra.append((str(_frontend_dist), "frontend/dist"))
else:
    raise RuntimeError(
        "frontend/dist 가 없습니다. `cd frontend && npm ci && npm run build` 후 다시 빌드하세요."
    )

_env_ex = _APP_ROOT / ".env.example"
if _env_ex.is_file():
    _datas_extra.append((str(_env_ex), "."))

a = Analysis(
    [_entry],
    pathex=_pathex,
    binaries=_binaries_acc,
    datas=_datas_acc + _datas_extra,
    hiddenimports=_hidden_acc
    + collect_submodules("backend")
    + [
        "uvicorn.loops.auto",
        "uvicorn.loops.asyncio",
        "uvicorn.protocols.http.auto",
        "uvicorn.protocols.http.h11_impl",
        "uvicorn.protocols.websockets.auto",
        "uvicorn.lifespan.on",
        "httptools",
        "multipart",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "matplotlib",
        "tkinter",
        "PyQt5",
        "PySide2",
    ],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="KRStockScreener",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="KRStockScreener",
)

# macOS: .app 번들(Windows/Linux 는 COLLECT 출력 폴더만 사용)
if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name="KRStockScreener.app",
        icon=None,
        bundle_identifier="com.krstock.screener",
        info_plist={
            "NSHighResolutionCapable": True,
            "CFBundleDisplayName": "KR Stock Screener",
            "CFBundleName": "KRStockScreener",
        },
    )

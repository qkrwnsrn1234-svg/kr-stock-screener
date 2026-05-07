#!/usr/bin/env bash
# 데스크톱 onedir 번들 빌드 (macOS: dist/KRStockScreener.app)
# 사용법: 저장소 루트에서 ./scripts/build_desktop.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ ! -d "$ROOT/frontend/dist" ]]; then
  echo "[build_desktop] frontend/dist 없음 — frontend 에서 npm run build 를 실행합니다."
  (cd "$ROOT/frontend" && npm ci && npm run build)
fi

# BUG-5 재발 방지: PyInstaller와 동일 인터프리터에 pywebview 등 런타임 의존성 동기화
python3 -m pip install -q -r "$ROOT/requirements.txt"

python3 -m pip install -q -r "$ROOT/requirements-build.txt"
python3 -m PyInstaller --noconfirm "$ROOT/desktop/app.spec"

echo "[build_desktop] 완료. 출력: $ROOT/dist/"
if [[ "$(uname -s)" == "Darwin" ]]; then
  echo "  macOS: open dist/KRStockScreener.app"
else
  echo "  Windows/Linux: dist/KRStockScreener/ 내 실행 파일"
fi

# KR Stock Screener

한국 코스피·코스닥·ETF를 대상으로 한 멀티에이전트 AI 분석 스크리닝 API·프런트엔드 모노레포입니다.

## 문서

- [로드맵 / 현재 진행 위치](./ROADMAP.md)
- [클라우드 배포·CI 안내](./docs/DEPLOYMENT.md)

## 로컬 빠른 시작 (백엔드)

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export PYTHONPATH=.
python -m backend.run_uvicorn
```

선호 포트 `PORT`(기본 **18000**, `.env`에서 변경)가 이미 사용 중이면 같은 머신에서는 이어서 빈 포트를 자동 선택합니다(`SERVER_PORT_AUTOSCAN=false`로 끌 수 있음). 개발 편의로 `SERVER_DEV_RELOAD=true` 로 코드 자동 재로드 가능합니다.

- API 문서: `http://127.0.0.1:18000/docs`(다른 포트로 뜬 경우 `GET /api/health` 의 `listen_port` 확인)
- 같은 서버에서 SPA를 쓰려면 프런트 빌드 후 동일 포트로 접속: `cd frontend && npm ci && npm run build` → 같은 호스트로 직접 접속  
- 개발 시에는 Vite(`npm run dev`, 기본 5173)가 `/api`를 로컬 백엔드(기본 18000)로 프록시합니다.

## 데스크톱 앱 (Phase 5, pywebview)

프런트를 빌드해 두면 내장 브라우저 엔진 창에서 같은 UI 를 띄울 수 있습니다.

```bash
cd frontend && npm ci && npm run build
cd ..
export PYTHONPATH=.
python3 -m desktop.app
```

- 백엔드는 **127.0.0.1** 에만 바인드합니다. 아이콘·창 크기 등은 `.env.example` 의 `DESKTOP_*` 변수를 참고하세요.
- macOS `.icns` / Windows `.ico` 는 `DESKTOP_ICON_PATH` 에 직접 지정하거나, PNG 를 변환한 뒤 경로를 넣으면 됩니다.

### PyInstaller 번들 (`.app` / onedir)

PyInstaller 공식 지원은 **Python 3.12 이하** 권장([ROADMAP](./ROADMAP.md) 참고). 저장소 루트에서:

```bash
./scripts/build_desktop.sh
# 또는: make build-desktop   (동일)
# 응용 프로그램(/Applications)에 넣으려면: make install  (빌드 후 복사)
```

- **macOS** 결과물: `dist/KRStockScreener.app` (onedir + BUNDLE) — **여기만** 생성되며, Dock·Launchpad용으로는 `make install` 로 `/Applications/` 에 복사
- **Windows/Linux** 결과물: `dist/KRStockScreener/` 폴더 내 실행 파일
- 번들된 앱은 첫 실행 시 사용자 데이터 디렉터리에 SQLite·캐시·`.env` 를 둡니다(`desktop/frozen_env.py`).
- `requirements-build.txt` 에 `pyinstaller` 가 있습니다.

### macOS 첫 실행 시 보안 승인 (한 번만)

PyInstaller로 만든 앱은 Apple 개발자 서명이 없으면 **처음 실행할 때** macOS가 “신뢰할 수 없는 개발자” 경고를 띄울 수 있습니다. 카카오톡 등 상용 앱과 달리 로컬에서 빌드한 `.app` 이라 흔한 현상입니다.

1. **Finder**에서 `응용 프로그램`(또는 `/Applications`)을 엽니다.
2. **KRStockScreener.app** 을 **우클릭**(또는 Control+클릭)합니다.
3. 상단 메뉴가 아니라 **바로 뜨는 메뉴**에서 **열기**를 선택합니다.
4. 확인 창에서 다시 **열기**를 누릅니다.

이후에는 Dock·Spotlight·더블클릭으로 평소 앱처럼 실행됩니다. 터미널에서 한 번 열어 승인하고 싶다면 `open /Applications/KRStockScreener.app` 도 같은 효과가 날 수 있으나, 우클릭 → 열기가 가장 확실합니다.

## Docker

```bash
docker compose up --build
```

PostgreSQL까지 쓸 때는 [docs/DEPLOYMENT.md](./docs/DEPLOYMENT.md) 의 Docker Compose 안내를 따르세요.

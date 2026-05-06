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

## Docker

```bash
docker compose up --build
```

PostgreSQL까지 쓸 때는 [docs/DEPLOYMENT.md](./docs/DEPLOYMENT.md) 의 Docker Compose 안내를 따르세요.

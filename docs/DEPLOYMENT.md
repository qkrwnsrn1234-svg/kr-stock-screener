# 클라우드 배포 안내서 (입문용)

이 문서는 **백엔드 API**(Docker 컨테이너)를 인터넷에 올릴 때 무엇을 준비하면 되는지만 짧게 정리합니다.

## 1. 배포 형태 한눈에 보기

- 프로젝트 루트 **Dockerfile**은 Node로 `frontend/` 를 빌드한 뒤, **FastAPI** 가 `frontend/dist` 를 함께 서빙하는 단일 이미지입니다.
- 실행 시 필요한 설정은 거의 모두 **환경 변수**(비밀 API 키 포함)입니다. `.env.example`을 참고하세요.
- **데이터 저장**: 기본은 SQLite 파일(`./data`). 여러 서버 인스턴스나 재시작 시 데이터를 안정적으로 두려면 **PostgreSQL**과 `DATABASE_URL`을 사용하는 편이 좋습니다.

## 2. 꼭 넣어야 하는 환경 변수 (예시)

| 변수 | 설명 |
|------|------|
| `DATABASE_URL` | 비우면 SQLite. 클라우드 DB 쓸 때는 `postgresql://사용자:비밀번호@호스트:5432/DB이름` |
| `ANTHROPIC_API_KEY` | Claude CEO 요약 등 (없어도 룰 기반으로 동작) |
| `DART_API_KEY` | 공시·재무 (선택에 따라 기능 제한) |
| `ECOS_API_KEY` | 한국은행 거시 지표 |
| `PORT` | 많은 호스팅이 자동 설정. Dockerfile은 `PORT`가 없으면 **8000**을 씁니다. |
| `FRONTEND_DIST_DIR` | (선택) PyInstaller 번들 등에서 빌드된 React `dist` 절대 경로 |
| `SERVE_SPA` | 기본 `true`. `dist` 가 없으면 API만 제공. `false` 이면 `dist` 가 있어도 정적 서빙 생략 |

**API 경로:** JSON API는 접두사 **`/api`** 입니다(예: `GET /api/health`, `GET /api/analyze/005930`). 호환용으로 **`GET /health`**(루트)도 동일 헬스 응답을 반환합니다.

알림·스케줄러 등은 운영 정책에 맞게 `.env.example` 나머지를 채우면 됩니다.

## 3. SQLite → PostgreSQL으로 옮길 때

로컬에 모아 둔 `data/analysis_history.db`, `data/watchlist.db`가 있으면, PostgreSQL 준비가 끝난 뒤 **한 번** 아래처럼 실행합니다.

```bash
export DATABASE_URL="postgresql://..."
export PYTHONPATH=.
python backend/scripts/migrate_sqlite_to_postgres.py
```

처음부터 클라우드에만 두면 마이그레이션은 생략하면 됩니다.

## 4. Render.com (Docker) 예시

1. New → **Web Service** → 저장소 연결 또는 Docker 이미지 지정  
2. **Docker** 빌드/시작 선택 (루트 Dockerfile 사용)  
3. **환경 변수**에 위 표와 동일하게 설정 (비밀은 대시보드 Secret으로)  
4. 무료/유료 플랜에 따라 **영속 디스크** 없으면 SQLite는 재배포마다 초기화될 수 있습니다. 장기 저장은 **PostgreSQL 애드온** 권장.

## 5. Fly.io 등 기타 플랫폼

- **Docker 이미지** 배포 패턴은 동일합니다.  
- `fly.toml`에서 `internal_port`를 컨테이너가 듣는 포트와 맞추거나, 플랫폼에 맞게 `PORT`를 전달하면 됩니다.  
- 같은 이미지를 AWS ECS, Google Cloud Run, Railway 등에도 올릴 수 있습니다.

## 6. CI (GitHub Actions)

`.github/workflows/ci.yml`이 **Python compileall**, **마이그레이션 스크립트 dry-run**, **Docker 빌드**를 PR·push마다 돌립니다.  
배포 자동화(예: main 머지 시 이미지 푸시)는 사용하는 호스팅에 맞춰 이 workflow에 한 단계씩 추가하면 됩니다.

## 7. 주의

- `.env`, API 키는 **저장소에 커밋하지 마세요**.  
- 프로덕션에서는 **HTTPS**와 **허용 IP/인증**(리버스 프록시 또는 API 게이트)을 검토하세요.

자세한 로드맵은 저장소 루트의 [ROADMAP.md](../ROADMAP.md)를 보세요.

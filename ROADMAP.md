# KR Stock Screener — 로드맵

## 프로젝트 한 줄 요약
한국 주식/ETF 대상 AI 멀티에이전트 투자 분석 스크리닝 시스템

---

## 📍 현재 작업 위치 (항상 여기를 먼저 확인)

**현재 Phase**: Phase 1-4 에이전트 세부 지표 보강 (재무 완료 → 리스크/퀀트 다음)
**현재 브랜치**: feature/phase4-scheduler-docker
**다음 할 일**: 리스크(Altman Z-Score·공매도 정교화) 또는 퀀트(Magic Formula 랭킹) 중 선택
**최종 배포 목표**: Phase 5 ✅ 구조 완성 — macOS `.app` 더블클릭으로 실행 가능한 상태
**마지막 커밋**: feat(agents): 재무 에이전트 PEG·EV/EBITDA·ROIC·FCF Yield·DCF 등 지표 보강

---

## Phase 0 — 프로젝트 세팅 ✅ 완료

- [x] Git 초기화 및 사용자 설정
- [x] .gitignore 생성
- [x] CLAUDE.md 생성 (Claude Code 컨텍스트)
- [x] .cursorrules 생성 (Cursor AI 규칙)
- [x] feature/ 브랜치 전략 수립
- [x] 전체 폴더 구조 생성
- [x] ROADMAP.md 작성
- [x] AI 자동 컨텍스트 로딩 규칙 추가

---

## Phase 1 — 백엔드 기반 구축 🔄 진행 중

### 1-1. 환경 세팅 ✅ 완료
- [x] Python 가상환경 생성 (.venv)
- [x] requirements.txt 작성 및 패키지 설치
- [x] .env / .env.example 생성 (API 키 관리)

### 1-2. 데이터 수집 모듈 (backend/data/)
- [x] finance_data.py — FinanceDataReader 연동 (주가, ETF)
- [x] krx_data.py — pykrx 연동 (거래량, 시총, 외국인/기관 매매)
- [x] dart_data.py — DART API 연동 (공시, 재무제표)
- [x] bok_data.py — 한국은행 API 연동 (금리, 환율, CPI, PMI)
- [x] cache.py — 데이터 캐싱 로직 (중복 API 호출 방지)

### 1-3. 에이전트 공통 기반 (backend/agents/)
- [x] base_agent.py — BaseAgent 클래스
      - analyze(ticker) → AgentResponse 인터페이스
      - 신뢰도 점수 반환 구조 포함
      - 에이전트 독립 실행 가능 구조
- [x] models.py — 공통 데이터 모델
      - AgentResponse: {opinion, confidence, score, reasoning, signals}
      - ScreeningResult: {ticker, undervalue_score, overheat_flag, agent_reports}
      - PortfolioAdvice: {weight_suggestion, risk_level, advice}

### 1-4. 각 에이전트 구현 (backend/agents/)

**코드 반영(1차):** `financial_agent`, `macro_agent`, `technical_agent`, `risk_agent`, `sector_agent`, `quant_agent`, `advisor_agent`, `ceo_agent`(CEOOrchestrator·CEOReport) 규칙 기반 구현 완료. OHLCV·가능 시 pykrx·ECOS 사용. **재무 에이전트 2차:** DART 당·전기 확장, 이자부차입·현금, PEG·EV/EBITDA·ROIC·FCF Yield·영업이익률 추세·간이 DCF(`financial_agent.py`). 아래 나머지 에이전트 세부 지표는 단계적으로 진행합니다.

#### 재무제표 분석가 (financial_agent.py)
담당 지표:
- [x] PER (주가수익비율) — 저평가 핵심 (`pykrx` 펀더멘털)
- [x] PBR (주가순자산비율) — 자산 대비 저평가
- [x] PEG Ratio — 성장 감안 밸류에이션 (DART 당기순이익 YoY + PER 근사)
- [x] EV/EBITDA — 자본구조 제거한 순수 비교 (시총+순차입 근사, EBITDA=영업이익+감가상각비)
- [x] ROE — 자기자본 수익성 (15% 이상 선호) (`EPS/BPS` 프록시)
- [x] ROIC vs WACC — 가치 창출 여부 (`NOPAT/투하자본` 근사 vs WACC 휴리스틱 8.5%)
- [x] FCF Yield — 실질 현금창출력 (FCF/시총, DART+`pykrx` 시총)
- [x] 부채비율 — 재무 안전성 (DART)
- [x] 이자보상배율 — 금리 상승기 생존력
- [x] 영업이익률 추세 — 본업 경쟁력 (사업보고서 당·전기 매출·영업이익)
- [x] DCF 적정주가 산출 (5년 명시 + 터미널 기업가치 근사, 시장 EV 대비 괴리율 시그널)
- [x] 그레이엄 수식 (Graham Number)
- [x] 배당수익률 (`pykrx` DIV%)

#### 거시경제 분석가 (macro_agent.py)
담당 지표:
- [ ] 기준금리 동향 (Fed + 한국은행)
- [ ] CPI/인플레이션 — 금리 방향 예측
- [ ] PMI — 경기 확장/수축 판단
- [ ] 환율 (원/달러, DXY) — 수출기업 영향
- [ ] 국제 정세/지정학 리스크 — 방산/에너지 수혜
- [ ] 섹터별 금리 민감도 분석

#### 기술적 분석가 (technical_agent.py)
담당 지표:
- [x] RSI — 과매수(70+)/과매도(30-) 판단 (`ti.rsi`, 14일)
- [x] MACD + 시그널선 교차 (`ti.macd_snapshot`, 히스토그램·골든교차 플래그)
- [x] 이동평균선 (20/60/120/200일) (`ti.moving_averages`)
- [x] 골든크로스 / 데드크로스 (`ti.golden_death_cross_flags`)
- [x] 볼린저 밴드 위치 (`ti.bollinger_band_pctb`, %B 기준)
- [x] 거래량 분석 (OBV) (`ti.obv_last`)
- [x] 상대강도 (개별주 vs 코스피/코스닥) (`ti.relative_strength_vs_benchmark`, 60일)

#### 리스크 매니저 (risk_agent.py)
담당 지표:
- [ ] Altman Z-Score — 파산 위험도
- [ ] 공매도 비율 / 쇼트 스퀴즈 가능성
- [ ] 변동성 (베타, 52주 고저 범위)
- [ ] 하락 시나리오 3단계 (약세/중립/강세)
- [ ] 최대낙폭 (MDD)
- [ ] 포지션 사이징 조언

#### 섹터 전문가 (sector_agent.py)
담당 지표:
- [ ] 섹터 모멘텀 — 현재 주도 섹터 판단
- [ ] ETF 자금흐름 — 기관 관심 섹터 추적
- [ ] 어닝 리비전 방향성 — 섹터 선행 신호
- [ ] 경쟁사 대비 상대강도
- [ ] 업종 평균 PER/PBR 비교

#### 퀀트 전략가 (quant_agent.py)
담당 지표:
- [ ] Piotroski F-Score (0~9점, 7+ 우량)
- [ ] Magic Formula (Greenblatt) — ROIC + EV/EBIT 순위
- [ ] 멀티팩터 스코어 (가치+모멘텀+퀄리티+저변동성)
- [ ] 컨센서스 괴리율 — 목표주가 대비 현재가
- [ ] 어닝 서프라이즈 이력
- [ ] 내부자 거래 신호 (대주주 매입/매도)

#### 포트폴리오 조언자 (advisor_agent.py)
담당 역할:
- [ ] 현재 보유 종목 전체 리스크 진단
- [ ] 섹터 쏠림 경고
- [ ] 종목별 비중 조절 제안
- [ ] 매수/매도/홀딩 우선순위 조언
- [ ] 시장 국면별 방어 전략 제시

#### CEO 오케스트레이터 (ceo_agent.py)
- [x] 전체 에이전트 병렬 호출 (`asyncio.gather`)
- [x] 반론 라운드: 리스크 매니저가 낙관론에 반박 (`risk_rebuttal` 생성)
- [x] 신뢰도 퍼센트 집계 (`buy_pct` / `neutral_pct` / `sell_pct`)
- [x] 최종 투자 의견 + 핵심 근거 3줄 요약 (`summary_lines`, Claude 보강 포함)
- [x] 에이전트별 발언 전문 보존 (`agent_reports` 전체 포함)

### 1-5. FastAPI 서버 (backend/)
- [x] main.py 기본 설정
- [x] GET /analyze/{ticker} — 단일 종목 분석
- [x] GET /screen — 다종목 스크리닝 (사용자가 직접 종목코드 입력, 최대 8개)
- [x] GET /portfolio/advice — 포트폴리오 조언
- [x] GET /sector/hot — 현재 주도 섹터
- [x] GET /search?q= — 종목명·코드 검색 API (예: "삼성전자" → 005930 자동완성용)

---

## Phase 2 — 스크리닝 고급 기능 🔄 진행 중

### 언더밸류에이션 스코어 (0~100점)
- [x] PER 점수 (업종 중앙값 대비 정규화)
- [x] PBR 점수
- [x] FCF Yield 점수 (현재 중립 50점·연동 예정)
- [x] F-Score 반영 (퀀트 에이전트 `piotroski_like`)
- [x] 종합 가중 합산 로직 (`/screen` 응답 `undervalue_breakdown`)

### 오버히트 알럿 시스템
- [x] RSI 70+ 감지
- [x] PER 업종 중앙값 2배 초과 감지
- [x] 거래량 급등 이상 감지 (20일 평균 대비)
- [x] 알럿 등급 (주의/경고/위험 — `overheat_alert.level`)

### 주도 섹터 자동 감지
- [x] 섹터별 ETF 자금흐름 분석 (업종→대표 ETF, pykrx 외국인·기관 순매수 + 거래량 비율)
- [x] 어닝 리비전 상향 섹터 추적 (컨센서스 피드 미연동 — `earnings_revision_note` 안내)
- [x] 상대강도 상위 섹터 추출 (Phase 1-5 `/sector/hot` 모멘텀 랭킹)
- [x] 근거 텍스트 자동 생성 (`HotSectorItem.summary`)

### 에이전트 성적표
- [x] 분석 의견 DB 저장 (날짜, 종목, CEO·전체 에이전트 JSON, 기준가)
- [x] 30/60/90거래일 후 수익률 대조 (OHLCV 기반, `/agents/stats` 호출 시 채움)
- [x] 에이전트별 적중률 통계 (단순 방향 적중 휴리스틱)
- [x] 가장 신뢰도 높은 에이전트 자동 가중치 조정 (`/analyze` 기본 on, `CEOReport.stats_weights_applied`)

### 스크리닝 방식 확정
> 사용자가 종목코드를 직접 입력하는 방식으로 확정 (최대 8개 동시 분석)
> 전 종목 자동 스크리닝은 pykrx rate limiting·API 비용 문제로 미채택

### 품질 개선 — 버그 수정

#### [BUG-1] 비동기 OHLCV 로딩이 순차 실행으로 동작 (TechnicalAgent·RiskAgent)
- [x] `await price_task, await bench_task` → `await asyncio.gather(price_task, bench_task)` 로 교체
      — 파일: `backend/agents/technical_agent.py`, `backend/agents/risk_agent.py`

#### [BUG-2] CEOOrchestrator가 validate_ticker 하나 때문에 FinancialAgent 중복 생성
- [x] `validator = FinancialAgent()` 제거 → `self.agents[0].validate_ticker(ticker)` 로 교체
      — 파일: `backend/agents/ceo_agent.py`

#### [BUG-3] FCF Yield가 언더밸류 스코어에서 항상 50점(중립) 고정
- [x] `fcf_s = 50.0` 상수 제거 → FCF 가중치 제외 후 PER·PBR·FSCORE 3가중치 합(0.90)으로 정규화
      — 파일: `backend/screener/screening.py`

#### [BUG-5] pywebview 미설치로 데스크톱 앱 실행 불가 ← 앱이 켜지지 않는 직접 원인
- [x] 원인 파악: `requirements.txt`에 `pywebview>=5.4.0` 선언되어 있으나 `.venv`에 미설치
      — 증상: `ModuleNotFoundError: No module named 'webview'` → 앱 즉시 종료
      — 해결: `.venv/bin/pip install pywebview` 로 수동 설치 완료 (6.2.1 설치됨)
- [x] 재발 방지: `scripts/build_desktop.sh` 에 PyInstaller 실행 전 `requirements.txt` 동기화 추가, `Makefile` `build-desktop` 에서 `.venv` 있을 때 선행 `pip install` (BUG-5)
      ```bash
      python3 -m pip install -q -r requirements.txt
      ```

#### [BUG-4] pykrx 라이브러리 내부 `print()` 경고 출력
- [ ] 앱/서버 시작 시 `"KRX 로그인 실패: KRX_ID 또는 KRX_PW 환경 변수가 설정되지 않았습니다."` 출력
      — 원인: pykrx 라이브러리 내부 코드(`pykrx/website/comm/auth.py:185`)의 `print()` 직접 호출
      — 해결: pykrx 최초 임포트 시 `contextlib.redirect_stdout` 로 stdout 일시 억제
      — 예시: `backend/__init__.py` 또는 `backend/main.py` 상단에서 처리
      ```python
      import contextlib, io
      with contextlib.redirect_stdout(io.StringIO()):
          import pykrx  # 내부 print() 흡수
      ```

### 품질 개선 — 기획-구현 갭

#### [GAP-1] Claude API 연동 시작 ← 가장 중요
- [x] CEO 종합 의견 생성부터 Claude 선택 연동
      — `ANTHROPIC_API_KEY`가 있으면 CEO 단계에서 Claude 호출, 없거나 실패하면 기존 룰 기반 요약 유지
- [x] **설계 결정 완료**: ① CEO 종합 의견 생성부터 적용 → ② 거시(뉴스·지정학 해석) → ③ 재무(자연어 분석) 순서로 확대
- [x] `ANTHROPIC_API_KEY` 환경변수 연동 확인 (패키지는 이미 설치됨)
      — `.env.example`에 `CLAUDE_MODEL`, `CLAUDE_CEO_SUMMARY_ENABLED` 추가
- [x] 에이전트 내부에서 룰 기반 signals 딕셔너리 → Claude에 컨텍스트로 전달 → 자연어 reasoning 생성 구조
      — 파일: `backend/agents/claude_client.py`, `backend/agents/ceo_agent.py`
- [x] 거시 에이전트 지정학·환율 영향 reasoning에 Claude 확대
      — `generate_macro_commentary()` 추가, `macro_agent.py` 연동
- [ ] 재무 에이전트 정량 지표 자연어 분석에 Claude 확대 (선택)

#### [GAP-2] DART 재무데이터가 financial_agent에 연동되지 않음
- [x] `dart_data.py`의 `fetch_financial_accounts()` → financial_agent에서 호출
      — 연결 재무제표(CFS)에서 영업이익률·부채비율·FCF·이자보상배율 추출 반영
      — 파일: `backend/agents/financial_agent.py`

#### [GAP-3] macro_agent의 지정학 리스크가 플레이스홀더
- [x] `signals["geopolitical_placeholder"]` 제거
- [x] Claude를 통한 지정학·금리·환율 영향 자연어 코멘터리 생성 연동
      — `generate_macro_commentary()` → `macro_agent.py`

#### [GAP-4] 관심 종목이 프론트 LocalStorage에만 저장
- [x] 백엔드 SQLite에 watchlist 테이블 추가 → `GET/POST/DELETE /watchlist` 엔드포인트
      — 파일: `backend/storage/watchlist.py` (신규), `backend/main.py` 라우터 추가
- [x] 프론트 Watchlist 탭에서 백엔드 API 연동 (Phase 3-2 선행 작업)

---

## Phase 3 — 디자인 시스템 & 프론트엔드 대시보드

### 3-0. 디자인 시스템 정의 (코딩 전 먼저 결정할 것)

#### 전체 테마
- **컨셉**: 다크 블룸버그 터미널 느낌 — 전문적이고 밀도 높은 정보 표시
- **배경**: `#0d1117` (현재 적용됨), 카드: `#161b22`, 보더: `#30363d`
- **폰트**: Pretendard (현재 적용됨), 숫자는 고정폭(`monospace`) 처리

#### 색상 시멘틱 (의미별 색상 규칙)
- [x] 매수(BUY): `#22c55e` (초록)
- [x] 매도(SELL): `#ef4444` (빨강)
- [x] 중립(HOLD): `#f59e0b` (앰버)
- [x] 상승: `#22c55e` / 하락: `#ef4444` (주식 앱 표준)
- [x] 경고/과열: `#f97316` (오렌지) / 위험: `#ef4444`
- [x] 포인트 컬러: `#3b82f6` (파란색) — 버튼, 링크, 활성 탭

#### 레이아웃 구조
- [x] 좌측 사이드바 네비게이션 (탭 전환) — 너비 220px 고정
- [x] 우측 메인 콘텐츠 영역
- [x] 상단 글로벌 검색바 (항상 노출)
- [x] 반응형 없음 (데스크톱 전용, 최소 너비 1280px)

#### 공통 컴포넌트 규칙
- [x] 카드 컴포넌트 — `border-radius: 8px`, 보더 `#30363d`
- [x] 배지 컴포넌트 — 과열 등급 색상 표시
- [x] 스켈레톤 로딩 — AI 분석 중 표시용
- [x] 숫자 색상 — 양수 초록, 음수 빨강 (수익률, 등락률 등)

### 3-1. 글로벌 검색 & 종목 탐색
- [x] React + TypeScript 초기 세팅 (Vite, `/api` 프록시 → 백엔드 기본 **18000**)
- [x] **글로벌 검색바** — 종목명 또는 6자리 코드 입력 → 자동완성
      — 백엔드 `GET /search?q=` 엔드포인트 연동 (Phase 1-5 신규 항목)
      — 입력 디바운스(300ms) 적용
- [x] **최근 검색 히스토리** — LocalStorage 저장, 최대 10개
- [x] **검색 → 분석 페이지 이동** — 결과 클릭 시 `/analyze/{ticker}` 페이지로 라우팅

### 3-2. 관심 종목 탭 (Watchlist)
- [x] **관심 종목 저장** — 백엔드 SQLite 저장 (Phase 2 [GAP-4] 선행 필요)
      — 데스크톱 앱 재설치 후에도 유지
- [x] **관심 종목 목록 화면** — 종목명, 현재가, 등락률, 언더밸류 스코어, 과열 배지 한눈에 표시
- [x] **빠른 분석 버튼** — 관심 종목에서 바로 AI 분석 실행
- [ ] **그룹 기능** (선택) — "성장주", "배당주" 등 사용자 태그 분류

### 3-3. 기존 화면 디자인 시스템 적용
- [x] 에이전트 토론 결과 화면 (구현됨 → 디자인 통일 필요)
- [x] 신뢰도 퍼센트 시각화 (파이차트/게이지)
- [x] 언더밸류에이션 스코어 미터
- [x] 오버히트 알럿 배지
- [x] 섹터 히트맵
- [x] 에이전트 성적표 대시보드
- [x] 포트폴리오 조언 화면

---

## Phase 4 — 고도화 및 배포 ✅ 완료

- [x] 실시간 데이터 업데이트 — 백그라운드 스케줄러(`SCHEDULER_ENABLED`, `SCHEDULER_INTERVAL_SECONDS`), KRX 상장목록 캐시 워밍, `GET /system/scheduler`
- [x] 과열/저평가 감지 시 알림 — Slack 호환 `ALERT_WEBHOOK_URL`, 선택 `SMTP` (`/analyze`·`/screen`의 `send_alerts`, `GET /system/alerts`)
- [x] 백테스트 결과 대시보드
- [x] PostgreSQL 이관
  - [x] PostgreSQL 이관 검토 및 SQLite 저장소 추상화 — `backend/storage/db.py`, `DATABASE_URL`, `psycopg`
  - [x] 기존 SQLite 데이터 → PostgreSQL 마이그레이션 스크립트 — `backend/scripts/migrate_sqlite_to_postgres.py`
  - [x] Docker Compose PostgreSQL 서비스 분리 — `docker compose --profile postgres` 의 `db` 서비스, `.env.example` 변수 안내
- [x] Docker — `Dockerfile` + `docker-compose.yml` (`./data` 볼륨, API + 선택 `db` 프로필)
- [x] 클라우드 배포 (CI/CD, 호스팅)
  - [x] GitHub Actions CI — `.github/workflows/ci.yml` (`compileall`, 마이그레이션 `--dry-run`, Docker 빌드)
  - [x] 배포 가이드 — `docs/DEPLOYMENT.md`(Render/Fly 등), `README.md` 요약
  - [x] Dockerfile `PORT` 환경변수 지원 (호스팅 기본 포트 대응)

---

## Phase 5 — 데스크톱 앱 패키징 (pywebview + PyInstaller)

> 목표: 아이콘 더블클릭 → 앱 실행. macOS `.app` + Windows `.exe` 배포.
> 기술 선택: pywebview (Python 네이티브 창) + PyInstaller (단일 실행 파일 번들)

### 5-1. 빌드 통합 구조 정비
- [x] React 정적 빌드 결과물(`dist/`)을 FastAPI가 서빙하도록 통합
      — `GET /` → `dist/index.html`, `/assets` 마운트·클라 라우트 SPA 폴백, REST는 `/api/*`
- [x] 서버 포트 고정 (기본 **18000**, `PORT`/`.env`로 변경 가능, `backend/run_uvicorn`)
- [x] 앱 실행 시 사용 가능한 포트 자동 탐색 (`SERVER_PORT_AUTOSCAN`, `GET /api/health`에 `listen_port`)

### 5-2. pywebview 데스크톱 래퍼
- [x] `desktop/app.py` 생성
      — FastAPI(uvicorn)를 **별도 프로세스**로 실행(스레드보다 종료 정리가 명확)
      — `webview.create_window()` 로 네이티브 창 띄우기
      — 서버 준비 완료 후 창 오픈 (`GET /api/health` 폴링)
- [x] 앱 아이콘: `DESKTOP_ICON_PATH` + `webview.start(icon=...)` (`.icns`/`.ico` 경로 직접 지정, 변환은 문서/README)
- [x] 창 타이틀·최소 크기·리사이즈: `DESKTOP_WINDOW_*` 환경 변수
- [x] 앱 종료 시 uvicorn 자식 프로세스 `terminate`/`kill` (`window.events.closed` + `webview.start` 이후 정리)

### 5-3. PyInstaller 번들링
- [x] `desktop/app.spec` 작성 (`desktop/pyinstaller_entry.py`, `collect_all`·`collect_submodules(backend)`·`frontend/dist`·`.env.example` 동봉)
- [x] macOS **onedir** + `BUNDLE` → `dist/KRStockScreener.app` (Windows/Linux 는 `dist/KRStockScreener/` 폴더)
- [ ] Windows: `.exe` NSIS 인스톨러 생성 (선택)
- [x] 번들 크기 일부 절감: `excludes`(matplotlib·tkinter·PyQt5 등), `upx=False`
- [x] 런타임: ``desktop/frozen_env.py`` 로 사용자 영역 DB·캐시·`.env` 복사, ``KR_STOCK_CACHE_DIR`` (`backend/data/cache.py`)

### 5-4. 빌드 자동화
- [x] `scripts/build_desktop.sh` + `Makefile` (`build-desktop`, `build-mac` / `build-win` → 동일 스크립트)
- [ ] `make install` — 빌드 후 `/Applications/KRStockScreener.app` 자동 복사
      ```makefile
      install: build-desktop
          cp -r dist/KRStockScreener.app /Applications/
          @echo "✅ 설치 완료: /Applications/KRStockScreener.app"
      ```
      — 설치 후 Launchpad · Spotlight · Dock 어디서나 실행 가능
- [ ] macOS 첫 실행 보안 경고 우회 문서화 (`README.md` 또는 `docs/` 추가)
      — 서명되지 않은 앱은 최초 1회만: Finder에서 우클릭 → "열기" → "열기" 확인
      — 이후부터는 더블클릭만으로 실행
- [ ] GitHub Actions CI: 태그 푸시 시 자동 빌드 + Releases 업로드 (선택)

### 5-5. 최종 실행 방법 (완성 후 사용자 흐름)

> **목표: 카카오톡처럼 아이콘 하나로 실행**

#### 최초 설치 (딱 한 번만)
```bash
# 1. 저장소 루트에서 실행
make build-desktop   # PyInstaller로 .app 빌드 (~수 분 소요)
make install         # /Applications/KRStockScreener.app 복사

# 2. macOS 보안 승인 (처음 한 번만)
# Finder → /Applications → KRStockScreener.app
# 우클릭 → "열기" → "열기" 클릭
```

#### 이후 매번 실행
- **방법 1**: Finder → `/Applications/KRStockScreener.app` 더블클릭
- **방법 2**: Spotlight(`⌘+Space`) → "KRStockScreener" 검색 → Enter
- **방법 3**: Dock에 고정 후 클릭

#### 앱 업데이트 시 (코드 변경 후)
```bash
make build-desktop   # 재빌드
make install         # /Applications 덮어쓰기
```

---

## 주요 기술 결정 사항
- AI 모델: claude-sonnet-4-20250514
- DB: SQLite (Phase 1~3) → PostgreSQL (Phase 4)
- 한국 주식/ETF 위주, 미국 지수는 참고용
- 에이전트 호출: CEO가 병렬 호출 후 반론 라운드 진행
- Python: 배포용 데스크톱 빌드는 **3.11~3.12** 권장(PyInstaller·휠 호환). 3.14 등 최신 버전은 로컬에서 빌드될 수 있으나 공식 지원 밖일 수 있음.

---

## AI 자동 업데이트 규칙
작업 항목 완료 시 AI가 직접 수행할 것:
1. 완료 항목: [ ] → [x] 로 변경
2. "📍 현재 작업 위치" 섹션 업데이트
3. 아래 명령어로 자동 커밋:
   git add ROADMAP.md && git commit -m "docs: ROADMAP 진행상황 업데이트"

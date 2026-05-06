# KR Stock Screener — 로드맵

## 프로젝트 한 줄 요약
한국 주식/ETF 대상 AI 멀티에이전트 투자 분석 스크리닝 시스템

---

## 📍 현재 작업 위치 (항상 여기를 먼저 확인)

**현재 Phase**: Phase 3 — 디자인 시스템 반영 완료 · Phase 4 병행
**현재 브랜치**: feature/phase4-scheduler-docker
**다음 할 일**: Phase 3-1 글로벌 검색 자동완성·히스토리, Phase 4 백테스트·PostgreSQL·CI
**최종 배포 목표**: Phase 5 — pywebview + PyInstaller로 macOS .app / Windows .exe 패키징
**마지막 커밋**: Phase 3-0 디자인 토큰·글로벌 검색바 레이아웃·컴포넌트 색상 통일

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

**코드 반영(1차):** `financial_agent`, `macro_agent`, `technical_agent`, `risk_agent`, `sector_agent`, `quant_agent`, `advisor_agent`, `ceo_agent`(CEOOrchestrator·CEOReport) 규칙 기반 구현 완료. OHLCV·가능 시 pykrx·ECOS 사용. 아래 세부 지표 체크는 데이터 보강과 함께 단계적으로 진행합니다.

#### 재무제표 분석가 (financial_agent.py)
담당 지표:
- [ ] PER (주가수익비율) — 저평가 핵심
- [ ] PBR (주가순자산비율) — 자산 대비 저평가
- [ ] PEG Ratio — 성장 감안 밸류에이션
- [ ] EV/EBITDA — 자본구조 제거한 순수 비교
- [ ] ROE — 자기자본 수익성 (15% 이상 선호)
- [ ] ROIC vs WACC — 가치 창출 여부
- [ ] FCF Yield — 실질 현금창출력
- [ ] 부채비율 — 재무 안전성
- [ ] 이자보상배율 — 금리 상승기 생존력
- [ ] 영업이익률 추세 — 본업 경쟁력
- [ ] DCF 적정주가 산출
- [ ] 그레이엄 수식 (Graham Number)
- [ ] 배당수익률

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
- [ ] RSI — 과매수(70+)/과매도(30-) 판단
- [ ] MACD + 시그널선 교차
- [ ] 이동평균선 (20/60/120/200일)
- [ ] 골든크로스 / 데드크로스
- [ ] 볼린저 밴드 위치
- [ ] 거래량 분석 (OBV)
- [ ] 상대강도 (개별주 vs 코스피/코스닥)

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
- [ ] 전체 에이전트 병렬 호출
- [ ] 반론 라운드: 리스크 매니저가 낙관론에 반박
- [ ] 신뢰도 퍼센트 집계
      예) 매수 68% / 중립 22% / 매도 10%
- [ ] 최종 투자 의견 + 핵심 근거 3줄 요약
- [ ] 에이전트별 발언 전문 보존

### 1-5. FastAPI 서버 (backend/)
- [x] main.py 기본 설정
- [x] GET /analyze/{ticker} — 단일 종목 분석
- [x] GET /screen — 다종목 스크리닝
- [x] GET /portfolio/advice — 포트폴리오 조언
- [x] GET /sector/hot — 현재 주도 섹터

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

### 자동 스크리닝 파이프라인 (C안 — 룰 기반 필터 → AI 분석)
> 전 종목을 AI로 돌리면 비용·시간 폭발 → 1차 필터로 후보를 좁힌 뒤 AI 분석

- [ ] **1차 필터 (pykrx 기반, AI 호출 없음)**
      — 시가총액 하한 필터 (예: 500억 이상)
      — 거래량 하한 필터 (20일 평균 대비 0.5배 이상)
      — PER 범위 필터 (0 초과 ~ 업종 중앙값 3배 이하)
      — 상장폐지·관리종목 제외
      — `GET /screen/candidates?market=KOSPI|KOSDAQ&limit=100` 엔드포인트
- [ ] **2차 AI 분석** — 필터 통과 종목 상위 N개에만 에이전트 파이프라인 실행
- [ ] **필터 조건 사용자 설정** — `.env` 또는 프론트 설정 화면에서 변경 가능
- [ ] **결과 정렬** — 언더밸류에이션 스코어 내림차순 기본, 사용자 정렬 변경 가능

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
- [x] React + TypeScript 초기 세팅 (Vite, `/api` 프록시 → 백엔드 8000)
- [ ] **글로벌 검색바** — 종목명 또는 6자리 코드 입력 → 자동완성 (KRX 전종목 리스트 기반)
- [ ] **최근 검색 히스토리** — LocalStorage 저장, 최대 10개

### 3-2. 관심 종목 탭 (Watchlist)
- [ ] **관심 종목 저장** — LocalStorage 기반 (로그인 없이 사용)
- [ ] **관심 종목 목록 화면** — 종목명, 현재가, 등락률, 언더밸류 스코어, 과열 배지 한눈에 표시
- [ ] **빠른 분석 버튼** — 관심 종목에서 바로 AI 분석 실행
- [ ] **그룹 기능** (선택) — "성장주", "배당주" 등 사용자 태그 분류

### 3-3. 자동 스크리닝 결과 탭
- [ ] **필터 조건 설정 패널** — 시장(KOSPI/KOSDAQ/전체), 시총 범위, PER 범위 등
- [ ] **후보 종목 테이블** — 1차 필터 결과 표시 (AI 분석 전 단계)
- [ ] **AI 분석 실행 버튼** — 선택 종목 또는 상위 N개에만 실행
- [ ] **결과 정렬/필터** — 스코어, 시총, 섹터별 정렬

### 3-4. 기존 화면 디자인 시스템 적용
- [x] 에이전트 토론 결과 화면 (구현됨 → 디자인 통일 필요)
- [x] 신뢰도 퍼센트 시각화 (파이차트/게이지)
- [x] 언더밸류에이션 스코어 미터
- [x] 오버히트 알럿 배지
- [x] 섹터 히트맵
- [x] 에이전트 성적표 대시보드
- [x] 포트폴리오 조언 화면

---

## Phase 4 — 고도화 및 배포

- [x] 실시간 데이터 업데이트 — 백그라운드 스케줄러(`SCHEDULER_ENABLED`, `SCHEDULER_INTERVAL_SECONDS`), KRX 상장목록 캐시 워밍, `GET /system/scheduler`
- [x] 과열/저평가 감지 시 알림 — Slack 호환 `ALERT_WEBHOOK_URL`, 선택 `SMTP` (`/analyze`·`/screen`의 `send_alerts`, `GET /system/alerts`)
- [ ] 백테스트 결과 대시보드
- [ ] PostgreSQL 이관
- [x] Docker — `Dockerfile` + `docker-compose.yml` (`./data` 볼륨, API 단일 서비스)
- [ ] 클라우드 배포 (CI/CD, 호스팅)

---

## Phase 5 — 데스크톱 앱 패키징 (pywebview + PyInstaller)

> 목표: 아이콘 더블클릭 → 앱 실행. macOS `.app` + Windows `.exe` 배포.
> 기술 선택: pywebview (Python 네이티브 창) + PyInstaller (단일 실행 파일 번들)

### 5-1. 빌드 통합 구조 정비
- [ ] React 정적 빌드 결과물(`dist/`)을 FastAPI가 서빙하도록 통합
      — `GET /` → `dist/index.html` 반환, 정적 파일 마운트
- [ ] 서버 포트 고정 (기본 18000, `.env`로 변경 가능)
- [ ] 앱 실행 시 사용 가능한 포트 자동 탐색 로직 추가 (포트 충돌 방지)

### 5-2. pywebview 데스크톱 래퍼
- [ ] `desktop/app.py` 생성
      — FastAPI 서버를 백그라운드 스레드로 실행
      — `webview.create_window()` 로 네이티브 창 띄우기
      — 서버 준비 완료 후 창 오픈 (헬스체크 폴링)
- [ ] 앱 아이콘 설정 (512×512 PNG → `.icns` / `.ico` 변환)
- [ ] 창 타이틀, 최소 크기, 리사이즈 옵션 설정
- [ ] 앱 종료 시 FastAPI 서버 프로세스 정리

### 5-3. PyInstaller 번들링
- [ ] `desktop/app.spec` 작성
      — `backend/`, `frontend/dist/` 정적 파일 포함
      — `.env` 및 데이터 파일 동봉
      — 숨겨진 import 명시 (pykrx, dart_fss 등)
- [ ] macOS: `--onefile` 또는 `--onedir` 선택 후 `.app` 번들 생성
- [ ] Windows: `.exe` + NSIS 인스톨러 생성 (선택)
- [ ] 번들 크기 최적화 (불필요한 패키지 제외)

### 5-4. 빌드 자동화
- [ ] `Makefile` 또는 `build.sh` 작성
      — `make build-mac` → macOS `.app` 생성
      — `make build-win` → Windows `.exe` 생성
- [ ] GitHub Actions CI: 태그 푸시 시 자동 빌드 + Releases 업로드 (선택)

---

## 주요 기술 결정 사항
- AI 모델: claude-sonnet-4-20250514
- DB: SQLite (Phase 1~3) → PostgreSQL (Phase 4)
- 한국 주식/ETF 위주, 미국 지수는 참고용
- 에이전트 호출: CEO가 병렬 호출 후 반론 라운드 진행
- Python: 3.14 (현재 맥 환경), 배포 시 pyenv로 3.11 고정 예정

---

## AI 자동 업데이트 규칙
작업 항목 완료 시 AI가 직접 수행할 것:
1. 완료 항목: [ ] → [x] 로 변경
2. "📍 현재 작업 위치" 섹션 업데이트
3. 아래 명령어로 자동 커밋:
   git add ROADMAP.md && git commit -m "docs: ROADMAP 진행상황 업데이트"

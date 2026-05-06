# KR Stock Screener — 로드맵

## 프로젝트 한 줄 요약
한국 주식/ETF 대상 AI 멀티에이전트 투자 분석 스크리닝 시스템

---

## 📍 현재 작업 위치 (항상 여기를 먼저 확인)

**현재 Phase**: Phase 1 — 백엔드 기반 구축
**현재 브랜치**: main
**다음 할 일**: Phase 1-3: 에이전트 공통 기반 (base_agent.py, models.py)
**마지막 커밋**: Phase 1-2 데이터 모듈(backend/data) 추가

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
- [ ] base_agent.py — BaseAgent 클래스
      - analyze(ticker) → AgentResponse 인터페이스
      - 신뢰도 점수 반환 구조 포함
      - 에이전트 독립 실행 가능 구조
- [ ] models.py — 공통 데이터 모델
      - AgentResponse: {opinion, confidence, score, reasoning, signals}
      - ScreeningResult: {ticker, undervalue_score, overheat_flag, agent_reports}
      - PortfolioAdvice: {weight_suggestion, risk_level, advice}

### 1-4. 각 에이전트 구현 (backend/agents/)

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
- [ ] main.py 기본 설정
- [ ] GET /analyze/{ticker} — 단일 종목 분석
- [ ] GET /screen — 다종목 스크리닝
- [ ] GET /portfolio/advice — 포트폴리오 조언
- [ ] GET /sector/hot — 현재 주도 섹터

---

## Phase 2 — 스크리닝 고급 기능

### 언더밸류에이션 스코어 (0~100점)
- [ ] PER 점수 (업종 평균 대비 정규화)
- [ ] PBR 점수
- [ ] FCF Yield 점수
- [ ] F-Score 반영
- [ ] 종합 가중 합산 로직

### 오버히트 알럿 시스템
- [ ] RSI 70+ 감지
- [ ] PER 업종 평균 2배 초과 감지
- [ ] 거래량 급등 이상 감지
- [ ] 알럿 등급 (주의/경고/위험)

### 주도 섹터 자동 감지
- [ ] 섹터별 ETF 자금흐름 분석
- [ ] 어닝 리비전 상향 섹터 추적
- [ ] 상대강도 상위 섹터 추출
- [ ] 근거 텍스트 자동 생성
      예) "방산 섹터: 지정학 리스크 + 방산 ETF 자금 유입 3주 연속"

### 에이전트 성적표
- [ ] 분석 의견 DB 저장 (날짜, 종목, 의견, 신뢰도)
- [ ] 30/60/90일 후 실제 수익률 대조
- [ ] 에이전트별 적중률 통계
- [ ] 가장 신뢰도 높은 에이전트 자동 가중치 조정

---

## Phase 3 — 프론트엔드 대시보드

- [ ] React + TypeScript 초기 세팅
- [ ] 종목 검색 + 에이전트 토론 결과 화면
- [ ] 신뢰도 퍼센트 시각화 (파이차트/게이지)
- [ ] 언더밸류에이션 스코어 미터
- [ ] 오버히트 알럿 배지
- [ ] 섹터 히트맵
- [ ] 에이전트 성적표 대시보드
- [ ] 포트폴리오 조언 화면

---

## Phase 4 — 고도화 및 배포

- [ ] 실시간 데이터 업데이트 (스케줄러)
- [ ] 과열/저평가 감지 시 알림 (이메일/슬랙)
- [ ] 백테스트 결과 대시보드
- [ ] PostgreSQL 이관
- [ ] Docker + 클라우드 배포

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

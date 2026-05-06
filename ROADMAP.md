# KR Stock Screener — 로드맵

## 프로젝트 한 줄 요약
한국 주식/ETF 대상 AI 멀티에이전트 투자 분석 스크리닝 시스템

---

## 📍 현재 작업 위치 (항상 여기를 먼저 확인)

**현재 Phase**: Phase 1 — 백엔드 기반 구축
**현재 브랜치**: main
**다음 할 일**: 데이터 수집 모듈 — FinanceDataReader 연동 (backend/data/)
**마지막 커밋**: Phase 1-1 환경 세팅(requirements, .env 예시, venv)

---

## Phase 0 — 프로젝트 세팅 ✅ 완료

- [x] Git 초기화 및 사용자 설정
- [x] .gitignore 생성
- [x] CLAUDE.md 생성 (Claude Code 컨텍스트)
- [x] .cursorrules 생성 (Cursor AI 규칙)
- [x] feature/ 브랜치 전략 수립
- [x] 전체 폴더 구조 생성

---

## Phase 1 — 백엔드 기반 구축 🔄 진행 중

### 1-1. 환경 세팅
- [x] Python 가상환경 생성 (venv)
- [x] requirements.txt 작성
- [x] 필수 패키지 설치
      (fastapi, uvicorn, anthropic, FinanceDataReader,
       pykrx, python-dotenv, pandas, requests)
- [x] .env 파일 생성 (API 키 관리) — 저장소에는 `.env.example` 제공, 로컬에서 `.env` 복사 후 값 입력

### 1-2. 데이터 수집 모듈 (backend/data/)
- [ ] FinanceDataReader 연동 (주가 데이터)
- [ ] pykrx 연동 (거래량, 외국인/기관 매매)
- [ ] DART API 연동 (공시, 재무제표)
- [ ] 한국은행 API 연동 (금리, 환율)
- [ ] 데이터 캐싱 로직

### 1-3. 에이전트 기반 구조 (backend/agents/)
- [ ] base_agent.py — 모든 에이전트의 공통 베이스
- [ ] AgentResponse 데이터 모델 정의

### 1-4. 각 에이전트 구현
- [ ] financial_agent.py (PER, PBR, ROE, ROIC, FCF, 부채비율)
- [ ] macro_agent.py (금리, 환율, CPI, PMI, 지정학)
- [ ] technical_agent.py (RSI, MACD, 이평선, 거래량)
- [ ] risk_agent.py (공매도비율, Altman Z, 변동성)
- [ ] sector_agent.py (섹터 모멘텀, 상대강도, ETF 자금흐름)
- [ ] quant_agent.py (F-Score, Magic Formula, 팩터)
- [ ] advisor_agent.py (포트폴리오 비중/리스크 조언)
- [ ] ceo_agent.py (전체 종합 + 반론 라운드 오케스트레이션)

### 1-5. FastAPI 서버 (backend/)
- [ ] main.py 기본 설정
- [ ] /analyze/{ticker} 엔드포인트
- [ ] /screen 엔드포인트 (다종목 스크리닝)
- [ ] /portfolio/advice 엔드포인트

---

## Phase 2 — 스크리닝 고급 기능

- [ ] 언더밸류에이션 스코어 (0~100점 산출)
- [ ] 오버히트 알럿 (RSI 70+ & PER 업종평균 2배 초과)
- [ ] 주도 섹터 자동 감지
- [ ] 에이전트 반론 라운드 구현
- [ ] 에이전트 성적표 (과거 분석 vs 실제 수익률)

---

## Phase 3 — 프론트엔드 대시보드

- [ ] React + TypeScript 초기 세팅
- [ ] 종목 검색 + 분석 결과 화면
- [ ] 에이전트 토론 내용 시각화
- [ ] 언더밸류에이션 스코어 차트
- [ ] 섹터 히트맵
- [ ] 포트폴리오 조언 화면

---

## Phase 4 — 고도화 및 배포

- [ ] 실시간 데이터 업데이트
- [ ] 알림 기능 (과열/저평가 감지 시)
- [ ] 백테스트 결과 대시보드
- [ ] 배포 (Docker + 클라우드)

---

## 주요 기술 결정 사항 (ADR)
- AI 모델: claude-sonnet-4-20250514
- DB: SQLite (Phase 1) → PostgreSQL (Phase 4에서 이관)
- 한국 주식/ETF 위주, 미국 지수는 참고용만
- 에이전트 호출 방식: CEO가 병렬 호출 후 취합

## 새 세션 시작 시 AI에게 전달할 템플릿
---
ROADMAP.md를 읽고 현재 작업 위치를 파악한 뒤
"📍 현재 작업 위치"의 다음 할 일부터 이어서 진행해줘.
기술 스택과 규칙은 CLAUDE.md와 .cursorrules를 따를 것.
---

---
## AI 자동 업데이트 규칙
작업 항목 완료 시 AI가 직접 수행할 것:
1. 완료 항목: [ ] → [x] 로 변경
2. "📍 현재 작업 위치" 섹션 업데이트
3. 아래 명령어로 자동 커밋:
   git add ROADMAP.md && git commit -m "docs: ROADMAP 진행상황 업데이트"

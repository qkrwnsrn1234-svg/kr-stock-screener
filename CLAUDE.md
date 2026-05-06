# ⚠️ 세션 시작 시 필수 확인
이 프로젝트 작업을 시작할 때 반드시 ROADMAP.md를 읽을 것.
"📍 현재 작업 위치" 섹션에서 다음 할 일을 파악하고 시작.
작업 완료 시 ROADMAP.md 자동 업데이트 후 git commit 할 것.

---

# KR Stock Screener — 프로젝트 컨텍스트

## 프로젝트 개요
한국 주식(코스피/코스닥) 및 ETF 대상의 AI 기반 기업 분석 스크리닝 시스템.
여러 AI 에이전트가 각자의 전문 관점에서 종목을 분석하고
CEO 에이전트가 최종 투자 의견을 종합하는 "AI 투자 회사" 구조.

## 핵심 목표
- 저평가 종목 자동 발굴 (언더밸류에이션 스코어)
- 과열 종목 경고 (오버히트 알럿)
- 현재 주도 섹터 자동 감지
- 포트폴리오 비중/리스크 조언

## 폴더 구조
kr-stock-screener/
├── CLAUDE.md
├── ROADMAP.md
├── .cursorrules
├── .gitignore
├── README.md
├── backend/
│   ├── main.py
│   ├── api/
│   ├── agents/
│   │   ├── base_agent.py
│   │   ├── ceo_agent.py
│   │   ├── financial_agent.py
│   │   ├── macro_agent.py
│   │   ├── technical_agent.py
│   │   ├── risk_agent.py
│   │   ├── sector_agent.py
│   │   ├── quant_agent.py
│   │   └── advisor_agent.py
│   ├── screener/
│   ├── data/
│   └── utils/
├── frontend/
│   └── src/
├── desktop/
│   ├── app.py              # Phase 5 pywebview 데스크톱 래퍼
│   ├── app.spec            # PyInstaller
│   ├── frozen_env.py       # 번들 런타임 경로
│   └── pyinstaller_entry.py
├── scripts/
│   └── build_desktop.sh    # 데스크톱 번들 빌드
├── Makefile                # make build-desktop 등
└── data/

## AI 에이전트 구성
| 에이전트 | 역할 | 주요 지표 |
|---|---|---|
| CEO | 토론 종합, 최종 매수/중립/매도 결정 | 전체 종합 |
| 재무제표 분석가 | 기업 재무 심층 분석 | PER, PBR, ROE, ROIC, FCF, 부채비율 |
| 거시경제 분석가 | 금리/환율/정세 → 섹터 수혜 판단 | 금리, CPI, PMI, 환율, 지정학 |
| 기술적 분석가 | 차트 패턴, 진입 타이밍 | RSI, MACD, 이평선, 거래량 |
| 리스크 매니저 | 하락 시나리오, 리스크 수치화 | 공매도비율, Altman Z, 변동성 |
| 섹터 전문가 | 업종 트렌드, 경쟁사 비교 | 섹터 모멘텀, 상대강도 |
| 퀀트 전략가 | 팩터 스코어, 통계 저평가 신호 | F-Score, Magic Formula, 팩터 |
| 포트폴리오 조언자 | 비중/리스크 조절 전반 조언 | 포트폴리오 전체 관점 |

## 데이터 소스
- FinanceDataReader: 한국 주식/ETF 가격 데이터
- pykrx: KRX 공식 데이터 (거래량, 시총, 외국인/기관 매매)
- DART API: 공시 데이터, 재무제표
- 한국은행 API: 금리, 환율, 경제지표
- yfinance: 미국 지수 참고용

## 기술 스택
- Backend: Python 3.11, FastAPI, SQLite
- Frontend: React 18, TypeScript, Recharts
- AI: Anthropic Claude API (claude-sonnet-4-20250514)

## 코딩 규칙 요약
- 모든 함수: 한국어 docstring 필수
- 타입 힌트 필수
- 에러: try/except + logging
- 주석: 한국어
- 상세 규칙은 .cursorrules 참조

## 작업 시 주의사항
- API 키는 절대 코드에 하드코딩 금지, .env 파일 사용
- 각 에이전트는 base_agent.py를 상속해서 구현
- 새 기능은 반드시 feature/ 브랜치에서 작업

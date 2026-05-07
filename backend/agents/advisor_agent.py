"""
포트폴리오 관점 에이전트입니다.

보유 비중 딕셔너리가 비어 있으면 분석 대상 종목을 100% 보유한 것으로 가정합니다.
"""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict

import pandas as pd

from . import technical_indicators as ti
from backend.agents.base_agent import BaseAgent
from backend.agents.io_async import fetch_equity_ohlcv_async, fetch_index_ohlcv_async
from backend.agents.models import AgentResponse
from backend.data import finance_data

logger = logging.getLogger(__name__)


def _build_action_priorities(
    norm_weights: dict[str, float],
    vol_map: dict[str, float | None],
    equal_w: float,
) -> list[dict[str, object]]:
    """
    매도(축소)·홀드·비중확대 후보를 우선순위로 정렬합니다.

    Args:
        norm_weights: 정규화된 보유 비중.
        vol_map: 종목별 연율화 변동성(없으면 None).
        equal_w: 동일가중 목표 비중.

    Returns:
        ``priority`` 오름차순(1이 가장 먼저 검토) 리스트.
    """
    rows: list[tuple[float, str, str, str]] = []
    max_w_all = max(norm_weights.values()) if norm_weights else 0.0
    for tic, w in norm_weights.items():
        v = vol_map.get(tic)
        vp = float(v) if isinstance(v, (int, float)) else 0.28
        dev = w - equal_w
        if w > equal_w + 0.035 and (w >= max_w_all * 0.92 or w > 0.22):
            urgency = dev * (1.0 + vp * 2.2)
            rows.append((urgency, tic, "trim", f"과대비중(목표 대비 +{dev*100:.1f}%p), 변동성 가중"))
        elif w < equal_w - 0.025 and vp < 0.36:
            urgency = (-dev) * (1.2 + (0.35 - vp))
            rows.append((urgency, tic, "add", f"저비중·상대적 저변동 — 비중 확대 후보"))
        else:
            rows.append((0.0, tic, "hold", "동일가중 근처 — 유지·미세 조정"))

    trim = [(u, t, a, n) for u, t, a, n in rows if a == "trim"]
    add = [(u, t, a, n) for u, t, a, n in rows if a == "add"]
    hold = [(u, t, a, n) for u, t, a, n in rows if a == "hold"]
    trim.sort(key=lambda x: -x[0])
    add.sort(key=lambda x: -x[0])
    ordered = trim + hold + add
    out: list[dict[str, object]] = []
    for i, (_u, t, act, note) in enumerate(ordered, start=1):
        out.append(
            {
                "priority": i,
                "ticker": t,
                "action": act,
                "note": note,
            }
        )
    return out


class AdvisorAgent(BaseAgent):
    """포트폴리오 조언 에이전트."""

    def __init__(
        self,
        holdings: dict[str, float] | None = None,
        *,
        agent_name: str | None = "포트폴리오",
    ) -> None:
        """
        Args:
            holdings: 종목코드→비중(0 이상). 비어 있으면 단일 종목 100% 모드.
            agent_name: 표시 이름.
        """
        super().__init__(agent_name=agent_name)
        self._holdings = {k.strip(): float(v) for k, v in (holdings or {}).items() if float(v) > 0}

    async def analyze(self, ticker: str) -> AgentResponse:
        """
        집중도(HHI)와 변동성 가중 프록시를 바탕으로 분산 아이디어를 제시합니다.
        """
        code = self.validate_ticker(ticker)
        weights = dict(self._holdings)
        if not weights:
            weights = {code: 1.0}

        total_w = sum(weights.values())
        norm_weights = {k: v / total_w for k, v in weights.items()}

        hhi = sum(w * w for w in norm_weights.values())
        max_w = max(norm_weights.values()) if norm_weights else 0.0
        eff_n = (1.0 / hhi) if hhi > 0 else 1.0

        sector_hhi: float | None = None
        max_sector_w: float | None = None
        sector_weights_norm: dict[str, float] = {}
        try:
            lst = await asyncio.to_thread(finance_data.list_krx_symbols, None)
            if lst is not None and not lst.empty and "Code" in lst.columns and "Dept" in lst.columns:
                code_to_dept: dict[str, str] = {}
                for _, row in lst.iterrows():
                    c = str(row.get("Code", "")).strip().zfill(6)
                    d = str(row.get("Dept", "") or "").strip() or "미분류"
                    if len(c) == 6:
                        code_to_dept[c] = d
                agg: defaultdict[str, float] = defaultdict(float)
                for c, w in norm_weights.items():
                    ck = c.strip().zfill(6)
                    agg[code_to_dept.get(ck, "미분류")] += w
                sector_weights_norm = dict(agg)
                if sector_weights_norm:
                    sector_hhi = sum(s * s for s in agg.values())
                    max_sector_w = max(agg.values())
        except Exception as exc:
            logger.debug("포트폴리오 업종 쏠림 계산 생략: %s", exc)

        vol_map: dict[str, float | None] = {}
        for t in list(norm_weights.keys())[:12]:
            try:
                df = await fetch_equity_ohlcv_async(t, lookback_days=320)
                close, _ = ti._ensure_close_volume(df)
                vol_map[t] = ti.realized_volatility(close, window=60)
            except Exception as exc:
                logger.debug("포트폴리오 변동성 계산 실패(%s): %s", t, exc)
                vol_map[t] = None

        risk_penalty = 0.0
        for t, w in norm_weights.items():
            v = vol_map.get(t)
            if v is None:
                continue
            risk_penalty += w * v

        n = max(1, len(norm_weights))
        equal_w = 1.0 / n
        suggestion = {t: equal_w for t in norm_weights.keys()}

        action_priorities = _build_action_priorities(norm_weights, vol_map, equal_w)

        market_regime_hint = "neutral"
        kospi_tr60: float | None = None
        try:
            df_idx = await fetch_index_ohlcv_async("KS11")
            bench = df_idx["Close"] if "Close" in df_idx.columns else df_idx["close"]
            bench = bench.copy()
            bench.index = pd.to_datetime(bench.index).normalize()
            kospi_tr60 = ti.total_return(bench, 60)
            if kospi_tr60 is not None:
                if kospi_tr60 < -0.08:
                    market_regime_hint = "defensive"
                elif kospi_tr60 > 0.08:
                    market_regime_hint = "risk_on"
        except Exception as exc:
            logger.debug("코스피 국면 계산 생략: %s", exc)

        score = 0.0
        notes: list[str] = []
        if hhi > 0.34:
            notes.append(f"집중도(HHI) 높음({hhi:.2f}) — 분산 필요")
            score -= 18
        elif hhi > 0.25:
            notes.append(f"집중도(HHI) 다소 높음({hhi:.2f})")
            score -= 10
        else:
            notes.append(f"집중도(HHI) 양호({hhi:.2f})")

        notes.append(f"유효 보유 종목 수(1/HHI 근사)≈{eff_n:.1f}개, 최대 비중≈{max_w*100:.1f}%")
        if max_w > 0.45:
            notes.append("단일 종목 비중이 매우 큼 — 리스크 집중")
            score -= 8
        elif max_w > 0.32:
            notes.append("단일 종목 비중이 큼 — 비중 조절 검토")
            score -= 4

        if max_sector_w is not None and max_sector_w > 0.55:
            notes.append(f"업종 쏠림: 최대 업종 비중≈{max_sector_w*100:.0f}% (상장 Dept 기준)")
            score -= 10
        elif max_sector_w is not None and max_sector_w > 0.42:
            notes.append(f"업종 비중이 한쪽으로 치우침(최대≈{max_sector_w*100:.0f}%)")
            score -= 5
        if sector_hhi is not None and sector_hhi > 0.38:
            notes.append(f"업종 분산 HHI={sector_hhi:.2f} — 섹터 집중")
            score -= 6

        if risk_penalty > 0.28:
            notes.append("가중 변동성 부담 큼 — 리스크 예산 점검")
            score -= 12

        if market_regime_hint == "defensive":
            notes.append("시장 국면(코스피 60일) 약세 — 방어·현금·퀄리티 비중 휴리스틱")
            score -= 6
        elif market_regime_hint == "risk_on":
            notes.append("시장 국면(코스피 60일) 강세 — 분산 유지하되 추세 리스크 관리")

        opinion = "중립"
        if score <= -16:
            opinion = "매도"
        elif score >= 12:
            opinion = "매수"

        signals = {
            "herfindahl_index": hhi,
            "weights_normalized": norm_weights,
            "suggested_equal_weights": suggestion,
            "weighted_vol_proxy": risk_penalty,
            "effective_num_holdings_approx": round(eff_n, 2),
            "max_single_weight": round(max_w, 4),
            "sector_herfindahl_index": round(sector_hhi, 4) if sector_hhi is not None else None,
            "max_sector_weight": round(max_sector_w, 4) if max_sector_w is not None else None,
            "sector_weights_by_listing_dept": sector_weights_norm or None,
            "action_priorities": action_priorities,
            "market_regime_hint": market_regime_hint,
            "kospi_total_return_60d": kospi_tr60,
        }

        reasoning = "; ".join(notes)
        return self.build_response(
            opinion=opinion,
            confidence=0.48,
            score=float(max(-50.0, min(50.0, score))),
            reasoning=reasoning,
            signals=signals,
        )

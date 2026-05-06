"""
분석 이력(CEO·에이전트 의견) SQLite 저장 및 성과 요약.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from backend.agents.models import CEOReport
from backend.data import finance_data

logger = logging.getLogger(__name__)


def _default_db_path() -> Path:
    """프로젝트 루트 ``data/analysis_history.db`` 경로."""
    root = Path(__file__).resolve().parents[2]
    return root / "data" / "analysis_history.db"


def get_db_path() -> Path:
    """환경변수 ``ANALYSIS_DB_PATH`` 가 있으면 우선, 없으면 기본 경로."""
    import os

    raw = os.getenv("ANALYSIS_DB_PATH", "").strip()
    return Path(raw) if raw else _default_db_path()


def _connect() -> sqlite3.Connection:
    path = get_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_analysis_db() -> None:
    """분석 이력 테이블을 생성합니다 (멱등)."""
    conn = _connect()
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS analysis_record (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              ticker TEXT NOT NULL,
              analyzed_at TEXT NOT NULL,
              ref_price REAL,
              final_opinion TEXT,
              buy_pct REAL,
              neutral_pct REAL,
              sell_pct REAL,
              report_json TEXT NOT NULL,
              return_30d REAL,
              return_60d REAL,
              return_90d REAL
            );
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_analysis_ticker_time
            ON analysis_record (ticker, analyzed_at DESC);
            """
        )
        conn.commit()
    finally:
        conn.close()


def _last_close_price(ticker: str) -> float | None:
    """최근 구간 종가(분석 시점 기준가)를 조회합니다."""
    try:
        end = date.today()
        start = end - timedelta(days=40)
        df = finance_data.fetch_ohlcv(ticker, start, end)
        if df is None or df.empty:
            return None
        col = "Close" if "Close" in df.columns else "close"
        return float(df[col].iloc[-1])
    except Exception as exc:
        logger.warning("기준가 조회 실패 %s: %s", ticker, exc)
        return None


def _forward_trading_return(ticker: str, as_of_utc: datetime, trading_days: int) -> float | None:
    """
    ``as_of_utc`` 일자에 가까운 종가 대비, ``trading_days`` 거래일 뒤 종가 수익률을 계산합니다.
    """
    try:
        as_of_date = as_of_utc.astimezone(timezone.utc).date()
        start = as_of_date - timedelta(days=15)
        end = as_of_date + timedelta(days=400)
        df = finance_data.fetch_ohlcv(ticker, start, end)
        if df is None or df.empty or len(df) < trading_days + 2:
            return None
        col = "Close" if "Close" in df.columns else "close"
        close = df[col].astype(float)
        idx = pd.to_datetime(close.index).normalize()
        close = pd.Series(close.values, index=idx)
        # as_of 이전 마지막 봉부터 시작
        pos = int(close.index.searchsorted(pd.Timestamp(as_of_date), side="right") - 1)
        if pos < 0:
            pos = 0
        if pos + trading_days >= len(close):
            return None
        p0 = float(close.iloc[pos])
        p1 = float(close.iloc[pos + trading_days])
        if p0 <= 0:
            return None
        return (p1 - p0) / p0
    except Exception as exc:
        logger.debug("선행 수익률 계산 실패 %s: %s", ticker, exc)
        return None


def insert_analysis_record(report: CEOReport, ref_price: float | None = None) -> int:
    """
    CEO 보고서 한 건을 저장합니다.

    Args:
        report: 분석 결과.
        ref_price: 기준가(미지정 시 ``None``).

    Returns:
        새 행 ``id``.
    """
    init_analysis_db()
    payload = report.model_dump(mode="json")
    analyzed_at = report.timestamp.isoformat()
    conn = _connect()
    try:
        cur = conn.execute(
            """
            INSERT INTO analysis_record (
              ticker, analyzed_at, ref_price, final_opinion,
              buy_pct, neutral_pct, sell_pct, report_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                report.ticker,
                analyzed_at,
                ref_price,
                report.final_opinion,
                report.buy_pct,
                report.neutral_pct,
                report.sell_pct,
                json.dumps(payload, ensure_ascii=False),
            ),
        )
        conn.commit()
        return int(cur.lastrowid or 0)
    finally:
        conn.close()


def save_ceo_report_blocking(report: CEOReport) -> int:
    """동기 컨텍스트에서 기준가를 조회한 뒤 저장합니다."""
    ref = _last_close_price(report.ticker)
    return insert_analysis_record(report, ref)


def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {k: row[k] for k in row.keys()}


def list_recent_records(limit: int = 50) -> list[dict[str, Any]]:
    """최신 분석 이력 요약 목록."""
    init_analysis_db()
    conn = _connect()
    try:
        cur = conn.execute(
            """
            SELECT id, ticker, analyzed_at, ref_price, final_opinion,
                   return_30d, return_60d, return_90d
            FROM analysis_record
            ORDER BY analyzed_at DESC
            LIMIT ?
            """,
            (limit,),
        )
        return [_row_to_dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


def list_records_for_ticker(ticker: str, limit: int = 30) -> list[dict[str, Any]]:
    """특정 종목 이력."""
    init_analysis_db()
    conn = _connect()
    try:
        cur = conn.execute(
            """
            SELECT id, ticker, analyzed_at, ref_price, final_opinion,
                   return_30d, return_60d, return_90d
            FROM analysis_record
            WHERE ticker = ?
            ORDER BY analyzed_at DESC
            LIMIT ?
            """,
            (ticker, limit),
        )
        return [_row_to_dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


def _maybe_fill_forward_returns(row: sqlite3.Row) -> sqlite3.Row:
    """선행 수익률 컬럼이 비어 있으면 채웁니다."""
    need = (
        row["return_30d"] is None
        or row["return_60d"] is None
        or row["return_90d"] is None
    )
    if not need:
        return row

    as_of = datetime.fromisoformat(str(row["analyzed_at"]).replace("Z", "+00:00"))
    if datetime.now(timezone.utc) - as_of.replace(tzinfo=timezone.utc) < timedelta(days=25):
        return row

    ticker = str(row["ticker"])
    r30 = row["return_30d"]
    r60 = row["return_60d"]
    r90 = row["return_90d"]
    if r30 is None:
        r30 = _forward_trading_return(ticker, as_of, 30)
    if r60 is None:
        r60 = _forward_trading_return(ticker, as_of, 60)
    if r90 is None:
        r90 = _forward_trading_return(ticker, as_of, 90)

    conn = _connect()
    try:
        conn.execute(
            """
            UPDATE analysis_record
            SET return_30d = COALESCE(?, return_30d),
                return_60d = COALESCE(?, return_60d),
                return_90d = COALESCE(?, return_90d)
            WHERE id = ?
            """,
            (r30, r60, r90, row["id"]),
        )
        conn.commit()
        cur = conn.execute("SELECT * FROM analysis_record WHERE id = ?", (row["id"],))
        updated = cur.fetchone()
        return updated or row
    finally:
        conn.close()


def _ceo_hit(opinion: str, ret: float | None) -> bool | None:
    """CEO·에이전트 의견과 수익률로 단순 적중 여부."""
    if ret is None:
        return None
    o = opinion.replace(" ", "")
    if "매수" in o:
        return ret > 0
    if "매도" in o:
        return ret < 0
    return abs(ret) < 0.04


@dataclass
class AgentStatAccum:
    hits: int = 0
    total: int = 0


def compute_agent_performance(trading_horizon: int = 30) -> dict[str, Any]:
    """
    저장된 분석 중 충분히 경과한 건에 대해 에이전트별 적중률을 계산합니다.

    Args:
        trading_horizon: 30 / 60 / 90 등 ``analysis_record`` 의 ``return_*d`` 컬럼과 매칭.

    Returns:
        API 응답용 딕셔너리.
    """
    init_analysis_db()
    col = {30: "return_30d", 60: "return_60d", 90: "return_90d"}.get(trading_horizon, "return_30d")

    conn = _connect()
    try:
        rows = conn.execute("SELECT * FROM analysis_record ORDER BY analyzed_at ASC").fetchall()
    finally:
        conn.close()

    min_age = {30: 28, 60: 55, 90: 85}.get(trading_horizon, 28)
    now = datetime.now(timezone.utc)
    by_agent: dict[str, AgentStatAccum] = {}
    ceo_acc = AgentStatAccum()
    evaluated = 0

    for raw in rows:
        row = _maybe_fill_forward_returns(raw)
        as_of = datetime.fromisoformat(str(row["analyzed_at"]).replace("Z", "+00:00"))
        if now - as_of.replace(tzinfo=timezone.utc) < timedelta(days=min_age):
            continue

        ret = row[col]
        if ret is None:
            continue

        evaluated += 1
        try:
            report = CEOReport.model_validate_json(row["report_json"])
        except Exception:
            continue

        ch = _ceo_hit(report.final_opinion, float(ret))
        if ch is not None:
            ceo_acc.total += 1
            if ch:
                ceo_acc.hits += 1

        for ar in report.agent_reports:
            h = _ceo_hit(ar.opinion, float(ret))
            if h is None:
                continue
            acc = by_agent.setdefault(ar.agent_name or "unknown", AgentStatAccum())
            acc.total += 1
            if h:
                acc.hits += 1

    def pack(acc: AgentStatAccum, name: str) -> dict[str, Any]:
        rate = (acc.hits / acc.total) if acc.total else None
        return {
            "agent_name": name,
            "samples": acc.total,
            "hits": acc.hits,
            "hit_rate": round(rate, 4) if rate is not None else None,
        }

    by_list = sorted(
        (pack(v, k) for k, v in by_agent.items()),
        key=lambda x: x["samples"],
        reverse=True,
    )

    return {
        "evaluated_records": evaluated,
        "horizon_trading_days": trading_horizon,
        "by_agent": by_list,
        "ceo": pack(ceo_acc, "CEO"),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

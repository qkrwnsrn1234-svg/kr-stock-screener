"""
관심 종목(Watchlist) 저장소.

테이블: watchlist
  - id         자동 증가 기본키
  - ticker     TEXT NOT NULL (6자리)
  - added_at   TEXT NOT NULL (ISO8601 UTC)
  - memo       TEXT DEFAULT ''
  - UNIQUE(ticker)
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from backend.storage.db import connect, execute, primary_key_sql, row_to_dict

logger = logging.getLogger(__name__)


def _connect() -> Any:
    """저장소 연결을 생성하고 테이블을 초기화합니다."""
    conn = connect("watchlist.db", sqlite_env_var="WATCHLIST_DB_PATH")
    _init_table(conn)
    return conn


def _init_table(conn: Any) -> None:
    """watchlist 테이블이 없으면 생성합니다."""
    pk_sql = primary_key_sql()
    execute(
        conn,
        f"""
        CREATE TABLE IF NOT EXISTS watchlist (
            id       {pk_sql},
            ticker   TEXT    NOT NULL,
            added_at TEXT    NOT NULL,
            memo     TEXT    DEFAULT '',
            UNIQUE(ticker)
        )
        """
    )
    conn.commit()


def init_watchlist_db() -> None:
    """watchlist 테이블만 생성합니다 (마이그레이션·배포 초기화용, 멱등)."""
    conn = connect("watchlist.db", sqlite_env_var="WATCHLIST_DB_PATH")
    try:
        _init_table(conn)
    finally:
        conn.close()


def _utc_now_iso() -> str:
    """현재 UTC 시각 ISO8601 문자열을 반환합니다."""
    return datetime.now(timezone.utc).isoformat()


def add_ticker(ticker: str, memo: str = "") -> dict[str, Any]:
    """
    관심 종목을 추가하거나 이미 있으면 memo만 갱신합니다.

    Args:
        ticker: 6자리 종목코드.
        memo: 사용자 메모(선택).

    Returns:
        저장된 행 딕셔너리.
    """
    ticker = ticker.strip().zfill(6)
    if len(ticker) != 6 or not ticker.isdigit():
        raise ValueError(f"종목코드는 숫자 6자리여야 합니다: {ticker!r}")

    conn = _connect()
    try:
        now = _utc_now_iso()
        execute(
            conn,
            """
            INSERT INTO watchlist (ticker, added_at, memo)
            VALUES (?, ?, ?)
            ON CONFLICT(ticker) DO UPDATE SET memo = excluded.memo
            """,
            (ticker, now, memo),
        )
        conn.commit()
        row = execute(
            conn,
            "SELECT id, ticker, added_at, memo FROM watchlist WHERE ticker = ?",
            (ticker,),
        ).fetchone()
        return row_to_dict(row)
    finally:
        conn.close()


def remove_ticker(ticker: str) -> bool:
    """
    관심 종목을 삭제합니다.

    Args:
        ticker: 6자리 종목코드.

    Returns:
        삭제 성공 여부(존재하지 않으면 False).
    """
    ticker = ticker.strip().zfill(6)
    conn = _connect()
    try:
        cur = execute(conn, "DELETE FROM watchlist WHERE ticker = ?", (ticker,))
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def list_tickers() -> list[dict[str, Any]]:
    """
    전체 관심 종목 목록을 최근 추가 순서로 반환합니다.

    Returns:
        [{id, ticker, added_at, memo}, ...] 목록.
    """
    conn = _connect()
    try:
        rows = execute(
            conn,
            "SELECT id, ticker, added_at, memo FROM watchlist ORDER BY added_at DESC"
        ).fetchall()
        return [row_to_dict(r) for r in rows]
    finally:
        conn.close()


def get_ticker(ticker: str) -> dict[str, Any] | None:
    """
    단일 관심 종목을 조회합니다.

    Returns:
        행 딕셔너리 또는 None.
    """
    ticker = ticker.strip().zfill(6)
    conn = _connect()
    try:
        row = execute(
            conn,
            "SELECT id, ticker, added_at, memo FROM watchlist WHERE ticker = ?",
            (ticker,),
        ).fetchone()
        return row_to_dict(row) if row else None
    finally:
        conn.close()

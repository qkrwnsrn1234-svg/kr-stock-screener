#!/usr/bin/env python3
"""
로컬 SQLite 저장소(`analysis_history`, `watchlist`)를 PostgreSQL로 복사합니다.

사용 전 ``DATABASE_URL`` 또는 ``--database-url`` 로 대상 PostgreSQL 연결 문자열을 지정하세요.

예 (프로젝트 루트에서):

``PYTHONPATH=. python3 backend/scripts/migrate_sqlite_to_postgres.py --dry-run``

``PYTHONPATH=. python3 backend/scripts/migrate_sqlite_to_postgres.py``
"""

from __future__ import annotations

import argparse
import logging
import os
import sqlite3
import sys
from pathlib import Path

# 패키지 로딩용 (backend.*)
_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

logger = logging.getLogger(__name__)


def _analysis_sqlite_path() -> Path:
    """분석 이력 SQLite 파일 경로."""
    from backend.storage.db import default_sqlite_path

    raw = os.getenv("ANALYSIS_DB_PATH", "").strip()
    return Path(raw) if raw else default_sqlite_path("analysis_history.db")


def _watchlist_sqlite_path() -> Path:
    """관심 종목 SQLite 파일 경로."""
    from backend.storage.db import default_sqlite_path

    raw = os.getenv("WATCHLIST_DB_PATH", "").strip()
    return Path(raw) if raw else default_sqlite_path("watchlist.db")


def _migrate_analysis(sqlite_path: Path, dry_run: bool) -> tuple[int, int]:
    """
    analysis_record 행을 SQLite에서 읽어 PostgreSQL에 삽입합니다.

    Returns:
        (소스 행 수, 실제 삽입 행 수).
    """
    if not sqlite_path.is_file():
        logger.info("SQLite 없음 — 건너뜀: %s", sqlite_path)
        return 0, 0

    sl = sqlite3.connect(sqlite_path)
    sl.row_factory = sqlite3.Row
    try:
        rows = sl.execute("SELECT * FROM analysis_record ORDER BY id").fetchall()
    finally:
        sl.close()

    n_src = len(rows)
    if dry_run:
        logger.info("[dry-run] analysis_record 소스 %d행 (대상 PostgreSQL 미기록)", n_src)
        return n_src, 0

    import psycopg

    pg_url = os.environ["DATABASE_URL"]
    inserted = 0
    with psycopg.connect(pg_url) as pg:
        with pg.cursor() as cur:
            for r in rows:
                cur.execute(
                    """
                    INSERT INTO analysis_record (
                        id, ticker, analyzed_at, ref_price, final_opinion,
                        buy_pct, neutral_pct, sell_pct, report_json,
                        return_30d, return_60d, return_90d
                    ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT (id) DO NOTHING
                    """,
                    (
                        r["id"],
                        r["ticker"],
                        r["analyzed_at"],
                        r["ref_price"],
                        r["final_opinion"],
                        r["buy_pct"],
                        r["neutral_pct"],
                        r["sell_pct"],
                        r["report_json"],
                        r["return_30d"],
                        r["return_60d"],
                        r["return_90d"],
                    ),
                )
                inserted += cur.rowcount
        pg.commit()

        with pg.cursor() as cur:
            cur.execute("SELECT COALESCE(MAX(id), 0) FROM analysis_record")
            mx = cur.fetchone()[0]
            if mx and int(mx) > 0:
                cur.execute(
                    "SELECT setval(pg_get_serial_sequence('analysis_record', 'id'), %s)",
                    (int(mx),),
                )
        pg.commit()

    logger.info("analysis_record: 소스 %d행, 새로 삽입 %d행", n_src, inserted)
    return n_src, inserted


def _migrate_watchlist(sqlite_path: Path, dry_run: bool) -> tuple[int, int]:
    """watchlist 행을 복사합니다."""
    if not sqlite_path.is_file():
        logger.info("SQLite 없음 — 건너뜀: %s", sqlite_path)
        return 0, 0

    sl = sqlite3.connect(sqlite_path)
    sl.row_factory = sqlite3.Row
    try:
        rows = sl.execute("SELECT * FROM watchlist ORDER BY id").fetchall()
    finally:
        sl.close()

    n_src = len(rows)
    if dry_run:
        logger.info("[dry-run] watchlist 소스 %d행 (대상 PostgreSQL 미기록)", n_src)
        return n_src, 0

    import psycopg

    pg_url = os.environ["DATABASE_URL"]
    inserted = 0
    with psycopg.connect(pg_url) as pg:
        with pg.cursor() as cur:
            for r in rows:
                cur.execute(
                    """
                    INSERT INTO watchlist (id, ticker, added_at, memo)
                    VALUES (%s,%s,%s,%s)
                    ON CONFLICT (ticker) DO UPDATE SET
                        added_at = EXCLUDED.added_at,
                        memo = EXCLUDED.memo
                    """,
                    (r["id"], r["ticker"], r["added_at"], r["memo"] or ""),
                )
                inserted += cur.rowcount
        pg.commit()

        with pg.cursor() as cur:
            cur.execute("SELECT COALESCE(MAX(id), 0) FROM watchlist")
            mx = cur.fetchone()[0]
            if mx and int(mx) > 0:
                cur.execute(
                    "SELECT setval(pg_get_serial_sequence('watchlist', 'id'), %s)",
                    (int(mx),),
                )
        pg.commit()

    logger.info("watchlist: 소스 %d행, 처리(삽입/갱신) %d행", n_src, inserted)
    return n_src, inserted


def main() -> int:
    """CLI 진입점."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description="SQLite → PostgreSQL 데이터 마이그레이션")
    parser.add_argument(
        "--database-url",
        default="",
        help="postgresql://... (미지정 시 환경변수 DATABASE_URL 사용)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="PostgreSQL에 쓰지 않고 SQLite 행 수만 출력",
    )
    args = parser.parse_args()

    pg_url = (args.database_url or os.getenv("DATABASE_URL", "")).strip()
    if not args.dry_run and not pg_url.lower().startswith(("postgresql://", "postgres://")):
        logger.error("DATABASE_URL 또는 --database-url 에 PostgreSQL 연결 문자열이 필요합니다.")
        return 1

    if not args.dry_run:
        os.environ["DATABASE_URL"] = pg_url
        from backend.storage.analysis_history import init_analysis_db
        from backend.storage.watchlist import init_watchlist_db

        init_analysis_db()
        init_watchlist_db()
        logger.info("PostgreSQL 스키마 준비 완료")

    ap = _analysis_sqlite_path()
    wl = _watchlist_sqlite_path()
    _migrate_analysis(ap, args.dry_run)
    _migrate_watchlist(wl, args.dry_run)

    if args.dry_run:
        logger.info("[dry-run] 완료. 실제 이관은 --dry-run 없이 동일 명령으로 실행하세요.")
    else:
        logger.info("마이그레이션 완료")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

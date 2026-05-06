"""
SQLite 기본 저장소와 PostgreSQL 전환을 위한 공통 DB 유틸리티.
"""

from __future__ import annotations

import logging
import os
import sqlite3
from pathlib import Path
from typing import Any, Literal, Sequence

logger = logging.getLogger(__name__)

StorageBackend = Literal["sqlite", "postgresql"]


def project_root() -> Path:
    """프로젝트 루트 디렉터리 경로를 반환합니다."""
    return Path(__file__).resolve().parents[2]


def default_sqlite_path(filename: str) -> Path:
    """프로젝트 data/ 디렉터리 아래 SQLite 파일 경로를 반환합니다."""
    return project_root() / "data" / filename


def database_url() -> str:
    """PostgreSQL 연결 문자열 환경변수를 반환합니다."""
    return os.getenv("DATABASE_URL", "").strip()


def storage_backend() -> StorageBackend:
    """
    현재 저장소 백엔드를 판별합니다.

    DATABASE_URL이 postgres/postgresql 스킴이면 PostgreSQL, 그 외에는 SQLite를 사용합니다.
    """
    url = database_url().lower()
    if url.startswith(("postgres://", "postgresql://")):
        return "postgresql"
    return "sqlite"


def is_postgresql() -> bool:
    """현재 저장소 백엔드가 PostgreSQL인지 여부를 반환합니다."""
    return storage_backend() == "postgresql"


def primary_key_sql() -> str:
    """DB 종류에 맞는 자동 증가 기본키 SQL 조각을 반환합니다."""
    if is_postgresql():
        return "BIGSERIAL PRIMARY KEY"
    return "INTEGER PRIMARY KEY AUTOINCREMENT"


def connect_sqlite(filename: str, *, env_var: str | None = None) -> sqlite3.Connection:
    """SQLite 연결을 생성합니다."""
    raw_path = os.getenv(env_var, "").strip() if env_var else ""
    path = Path(raw_path) if raw_path else default_sqlite_path(filename)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def connect_postgresql() -> Any:
    """PostgreSQL 연결을 생성합니다."""
    try:
        import psycopg
        from psycopg.rows import dict_row
    except ImportError as exc:
        raise RuntimeError(
            "PostgreSQL을 사용하려면 requirements.txt의 psycopg 패키지를 설치해야 합니다."
        ) from exc

    return psycopg.connect(database_url(), row_factory=dict_row)


def connect(filename: str, *, sqlite_env_var: str | None = None) -> Any:
    """현재 저장소 설정에 맞는 DB 연결을 생성합니다."""
    if is_postgresql():
        return connect_postgresql()
    return connect_sqlite(filename, env_var=sqlite_env_var)


def sql(sql_text: str) -> str:
    """
    공통 SQL의 qmark 플레이스홀더(?)를 현재 DB 드라이버 형식으로 변환합니다.

    저장소 모듈의 SQL에는 문자열 리터럴 안에 물음표를 쓰지 않는다는 전제를 둡니다.
    """
    if is_postgresql():
        return sql_text.replace("?", "%s")
    return sql_text


def execute(conn: Any, sql_text: str, params: Sequence[Any] = ()) -> Any:
    """DB 종류에 맞게 SQL을 실행하고 커서를 반환합니다."""
    return conn.execute(sql(sql_text), params)


def row_to_dict(row: Any) -> dict[str, Any]:
    """SQLite Row 또는 PostgreSQL dict row를 일반 딕셔너리로 변환합니다."""
    if isinstance(row, dict):
        return dict(row)
    return {key: row[key] for key in row.keys()}


def inserted_id(cursor: Any, row: Any | None = None) -> int:
    """INSERT 결과에서 새 기본키 값을 추출합니다."""
    if row is not None:
        return int(row["id"] if isinstance(row, dict) else row["id"])
    return int(getattr(cursor, "lastrowid", 0) or 0)

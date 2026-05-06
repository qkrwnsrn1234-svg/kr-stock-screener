"""
디스크 기반 TTL 캐시 모듈입니다.

기본 저장 위치는 프로젝트 루트의 ``data/cache`` 입니다.
PyInstaller 데스크톱 번들 등에서는 ``KR_STOCK_CACHE_DIR`` 로 쓰기 가능한 경로를 지정할 수 있습니다.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import pickle
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")

# 캐시 기본 TTL (초) — 단순 조회 API 부하 완화용
DEFAULT_TTL_SECONDS = 3600

# 프로젝트 루트 (backend/data 기준 상위 두 단계)
_PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _cache_root_dir() -> Path:
    """
    디스크 캐시 루트 디렉터리입니다.

    PyInstaller 번들 등 쓰기 가능한 경로가 필요하면 ``KR_STOCK_CACHE_DIR`` 을 설정합니다.
    """
    raw = os.getenv("KR_STOCK_CACHE_DIR", "").strip()
    if raw:
        return Path(raw).resolve()
    return _PROJECT_ROOT / "data" / "cache"


# 런타임에 환경 변수로 재지정 가능(``desktop.app`` 번들 기동 시 설정)
CACHE_ROOT = _cache_root_dir()


def build_cache_key(*parts: str) -> str:
    """
    캐시 키 문자열을 안전하게 결합합니다.

    Args:
        *parts: 키를 구성하는 문자열 조각들.

    Returns:
        ``'|'`` 로 연결된 단일 키 문자열.
    """
    return "|".join(parts)


def _digest(key: str) -> str:
    """키 문자열의 SHA-256 해시(파일명용)를 반환합니다."""
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def _paths(namespace: str, key: str) -> tuple[Path, Path]:
    """네임스페이스와 키에 해당하는 (페이로드 경로, 메타 경로)를 반환합니다."""
    folder = CACHE_ROOT / namespace
    folder.mkdir(parents=True, exist_ok=True)
    name = _digest(key)
    return folder / f"{name}.pkl", folder / f"{name}.meta.json"


def _utc_now() -> datetime:
    """현재 시각(UTC)을 반환합니다."""
    return datetime.now(timezone.utc)


def load_cached(
    namespace: str,
    cache_key: str,
    fetcher: Callable[[], T],
    ttl_seconds: int = DEFAULT_TTL_SECONDS,
) -> T:
    """
    TTL이 유효하면 디스크 캐시를 반환하고, 만료 시 ``fetcher``를 실행해 갱신합니다.

    Args:
        namespace: 캐시 상위 폴더명 (예: ``fdr``, ``pykrx``, ``dart``).
        cache_key: ``build_cache_key`` 등으로 만든 논리 키.
        fetcher: 캐시 미스 시 호출되는 무인수 팩토리.
        ttl_seconds: TTL(초).

    Returns:
        캐시된 값 또는 ``fetcher()`` 결과.

    Raises:
        pickle.UnpicklingError: 손상된 캐시 파일이 있을 때 (삭제 후 재시도 권장).
    """
    payload_path, meta_path = _paths(namespace, cache_key)

    try:
        if meta_path.is_file() and payload_path.is_file():
            meta_raw = meta_path.read_text(encoding="utf-8")
            meta = json.loads(meta_raw)
            expires_at = datetime.fromisoformat(meta["expires_at"])
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)
            if _utc_now() < expires_at:
                with payload_path.open("rb") as f:
                    logger.debug("캐시 히트: namespace=%s digest=%s", namespace, _digest(cache_key))
                    return pickle.load(f)
    except (json.JSONDecodeError, KeyError, OSError, pickle.UnpicklingError) as exc:
        logger.warning("캐시 읽기 실패 — 무시 후 재조회합니다: %s", exc)

    logger.debug("캐시 미스: namespace=%s key_digest=%s", namespace, _digest(cache_key))
    value = fetcher()
    expires_at = _utc_now() + timedelta(seconds=ttl_seconds)

    try:
        with payload_path.open("wb") as f:
            pickle.dump(value, f, protocol=pickle.HIGHEST_PROTOCOL)
        meta_path.write_text(
            json.dumps({"expires_at": expires_at.isoformat()}),
            encoding="utf-8",
        )
    except OSError as exc:
        logger.warning("캐시 저장 실패 — 결과만 반환합니다: %s", exc)

    return value


def clear_namespace(namespace: str) -> int:
    """
    지정한 네임스페이스 폴더의 캐시 파일을 모두 삭제합니다.

    Args:
        namespace: 삭제할 상위 폴더명.

    Returns:
        삭제한 파일 개수.
    """
    folder = CACHE_ROOT / namespace
    if not folder.is_dir():
        return 0
    removed = 0
    for path in folder.iterdir():
        try:
            path.unlink()
            removed += 1
        except OSError as exc:
            logger.warning("캐시 파일 삭제 실패: %s (%s)", path, exc)
    return removed


def cache_root() -> Path:
    """캐시 루트 경로를 반환합니다."""
    return CACHE_ROOT

"""
한국은행 ECOS(Open API) 통계 조회 모듈입니다.

통계표 코드·항목 코드·주기 값은 [ECOS 통계표 메타](https://ecos.bok.or.kr/)
에서 확인해야 하며, 여기서는 범용 ``statistic_search`` 와 자주 쓰일 만한 **예시** 상수만 제공합니다.

환경 변수 ``ECOS_API_KEY`` (또는 ``BOK_API_KEY``) 가 필요합니다.
"""

from __future__ import annotations

import hashlib
import logging
import os
from typing import Any
from urllib.parse import quote

import requests

from backend.data.cache import DEFAULT_TTL_SECONDS, build_cache_key, load_cached

logger = logging.getLogger(__name__)

ECOS_API_BASE = "https://ecos.bok.or.kr/api"

# 아래 코드들은 ECOS 포털에서 재확인 후 사용하는 것을 권장합니다 (변경 가능).
# 원/달러 매매기준율 일련 — 통계표·항목 코드는 환경에 따라 다를 수 있습니다.
DEFAULT_STAT_USD_KRW = ("731Y001", "D", "0000001")

# 정책금리(기준금리) 일간 — ``722B001`` 는 API에서 데이터 미제공(INFO-200)이며 ``722Y001`` 이 실데이터로 검증됨.
DEFAULT_STAT_BASE_RATE = ("722Y001", "D", "0101000")

# 소비자물가 전년동월비 등 월간 지표 — 항목 코드가 필요한 통계표는 ECOS 항목 목록으로 확인합니다.
DEFAULT_STAT_CPI_YOY = ("901Y010", "M", "")

# 제조업 PMI 대체: ECOS ``812Y001`` 는 실조회 시 데이터 없음(INFO-200).
# 한국은행 「업종별 기업경기실사지수」 전산업·업황실적 BSI(항목 AA·99988)를 거시 선행 분위기 지표로 사용합니다.
DEFAULT_STAT_INDUSTRY_BSI = ("512Y007", "M", "AA", "99988")


def _api_key_fingerprint(api_key: str) -> str:
    """캐시 키용 인증키 지문(비가역)을 생성합니다."""
    return hashlib.sha256(api_key.encode("utf-8")).hexdigest()[:16]


def _resolve_api_key(api_key: str | None) -> str:
    """ECOS 인증키를 환경 변수 또는 인수에서 가져옵니다."""
    key = api_key or os.getenv("ECOS_API_KEY") or os.getenv("BOK_API_KEY") or ""
    key = key.strip()
    if not key:
        raise RuntimeError("ECOS API 키가 비어 있습니다. .env 의 ECOS_API_KEY 를 설정하세요.")
    return key


def statistic_search(
    stat_code: str,
    cycle: str,
    start_date: str,
    end_date: str,
    item_code: str = "",
    *,
    item_code2: str = "",
    item_code3: str = "",
    item_code4: str = "",
    api_key: str | None = None,
    start_index: int = 1,
    end_index: int = 10000,
    lang: str = "kr",
    fmt: str = "json",
    ttl_seconds: int = DEFAULT_TTL_SECONDS,
) -> dict[str, Any]:
    """
    ECOS ``StatisticSearch`` API를 호출합니다.

    Args:
        stat_code: 통계표 코드 (예: ``731Y001``).
        cycle: 주기 코드 (``D`` 일, ``M`` 월 등 ECOS 규약).
        start_date: 조회 시작 일자 (통계표 주기에 맞는 문자열).
        end_date: 조회 종료 일자.
        item_code: 통계항목 코드 1(불필요 시 빈 문자열).
        item_code2: 통계항목 코드 2(다단 항목 통계표용).
        item_code3: 통계항목 코드 3.
        item_code4: 통계항목 코드 4.
        api_key: ECOS 인증키.
        start_index: 시작 건수(페이지 시작).
        end_index: 종료 건수(페이지 끝).
        lang: 언어 코드.
        fmt: 응답 포맷 (``json`` 권장).
        ttl_seconds: 캐시 TTL.

    Returns:
        ECOS JSON 응답 파싱 결과.

    Raises:
        RuntimeError: HTTP 오류 또는 ECOS 결과 코드가 비정상인 경우.
    """
    resolved = _resolve_api_key(api_key)

    def _fetch() -> dict[str, Any]:
        # 경로 세그먼트 인코딩 — 특수문자가 있는 항목 코드 대비
        segments = [
            "StatisticSearch",
            quote(resolved, safe=""),
            fmt,
            lang,
            str(start_index),
            str(end_index),
            quote(stat_code, safe=""),
            quote(cycle, safe=""),
            quote(start_date, safe=""),
            quote(end_date, safe=""),
        ]
        for raw_item in (item_code, item_code2, item_code3, item_code4):
            part = raw_item.strip()
            if part:
                segments.append(quote(part, safe=""))
        url = f"{ECOS_API_BASE}/{'/'.join(segments)}"
        try:
            resp = requests.get(url, timeout=60)
            resp.raise_for_status()
            data = resp.json()
        except (requests.RequestException, ValueError) as exc:
            logger.exception("ECOS StatisticSearch 호출 실패 stat=%s", stat_code)
            raise RuntimeError(f"ECOS StatisticSearch 호출 실패: {stat_code}") from exc

        # ECOS 응답: RESULT 코드 확인
        try:
            code = data["RESULT"]["CODE"]
            msg = data["RESULT"]["MESSAGE"]
            if str(code).strip() != "INFO-000":
                logger.warning("ECOS 비정상 RESULT code=%s message=%s", code, msg)
                raise RuntimeError(f"ECOS 오류: {code} - {msg}")
        except (KeyError, TypeError):
            logger.warning("ECOS 응답에 RESULT 필드가 없습니다 — 원문을 반환합니다.")
        return data

    kid = _api_key_fingerprint(resolved)
    key = build_cache_key(
        "ecos",
        kid,
        stat_code,
        cycle,
        start_date,
        end_date,
        item_code,
        item_code2,
        item_code3,
        item_code4,
        str(start_index),
        str(end_index),
    )
    return load_cached("bok_ecos", key, _fetch, ttl_seconds=ttl_seconds)


def fetch_base_rate_daily(
    start_date: str,
    end_date: str,
    *,
    api_key: str | None = None,
    ttl_seconds: int = DEFAULT_TTL_SECONDS,
) -> dict[str, Any]:
    """
    한국은행 기준금리(정책금리) 일간 시계열을 조회합니다.

    Args:
        start_date: 시작일 ``YYYYMMDD``.
        end_date: 종료일 ``YYYYMMDD``.
        api_key: ECOS 인증키.
        ttl_seconds: 캐시 TTL.

    Returns:
        ECOS JSON 응답.
    """
    stat_code, cycle, item_code = DEFAULT_STAT_BASE_RATE
    return statistic_search(
        stat_code,
        cycle,
        start_date,
        end_date,
        item_code=item_code,
        api_key=api_key,
        ttl_seconds=ttl_seconds,
    )


def fetch_cpi_yoy_monthly(
    start_month: str,
    end_month: str,
    *,
    api_key: str | None = None,
    ttl_seconds: int = DEFAULT_TTL_SECONDS,
) -> dict[str, Any]:
    """
    소비자물가 상승률(전년동월비 등) 월간 시계열을 조회합니다.

    Args:
        start_month: 시작 월 ``YYYYMM``.
        end_month: 종료 월 ``YYYYMM``.
        api_key: ECOS 인증키.
        ttl_seconds: 캐시 TTL.

    Returns:
        ECOS JSON 응답.
    """
    stat_code, cycle, item_code = DEFAULT_STAT_CPI_YOY
    return statistic_search(
        stat_code,
        cycle,
        start_month,
        end_month,
        item_code=item_code,
        api_key=api_key,
        ttl_seconds=ttl_seconds,
    )


def fetch_manufacturing_pmi_monthly(
    start_month: str,
    end_month: str,
    *,
    api_key: str | None = None,
    ttl_seconds: int = DEFAULT_TTL_SECONDS,
) -> dict[str, Any]:
    """
    제조업 PMI 대신 전산업 「업황실적BSI」 월간 시계열을 조회합니다.

    과거 PMI 전용 통계표(예: ``812Y001``)가 ECOS에서 비어 있는 경우가 있어,
    기업경기실사지수(512Y007, 항목 AA·전산업 99988)로 거시 분위기를 봅니다.
    민감도 해석은 기준치 **100**(초과·호전, 미만·위축)입니다.

    Args:
        start_month: 시작 월 ``YYYYMM``.
        end_month: 종료 월 ``YYYYMM``.
        api_key: ECOS 인증키.
        ttl_seconds: 캐시 TTL.

    Returns:
        ECOS JSON 응답.
    """
    stat_code, cycle, it1, it2 = DEFAULT_STAT_INDUSTRY_BSI
    return statistic_search(
        stat_code,
        cycle,
        start_month,
        end_month,
        item_code=it1,
        item_code2=it2,
        api_key=api_key,
        ttl_seconds=ttl_seconds,
    )


def fetch_usd_krw_daily(
    start_date: str,
    end_date: str,
    *,
    api_key: str | None = None,
    ttl_seconds: int = DEFAULT_TTL_SECONDS,
) -> dict[str, Any]:
    """
    (예시) 원/달러 관련 일간 통계를 조회합니다.

    실패하면 통계표·항목 코드가 현재 ECOS 메타와 맞지 않을 가능성이 큽니다.
    이 경우 ``statistic_search`` 에 올바른 코드를 직접 넘기세요.

    Args:
        start_date: 시작일 (일간 주기 형식).
        end_date: 종료일.
        api_key: ECOS 인증키.
        ttl_seconds: 캐시 TTL.

    Returns:
        ECOS JSON 응답.
    """
    stat_code, cycle, item_code = DEFAULT_STAT_USD_KRW
    return statistic_search(
        stat_code,
        cycle,
        start_date,
        end_date,
        item_code=item_code,
        api_key=api_key,
        ttl_seconds=ttl_seconds,
    )

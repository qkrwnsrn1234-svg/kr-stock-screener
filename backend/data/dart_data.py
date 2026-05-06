"""
금융감독원 전자공시 Open DART API 연동 모듈입니다.

공시 목록·회사 개황 등 조회 전에 ``corp_code`` 가 필요하므로,
상장법인 고유번호(zip/XML) 목록을 내려받아 종목코드와 매핑합니다.

환경 변수 ``DART_API_KEY`` (또는 ``CRTFC_KEY``) 가 필요합니다.
"""

from __future__ import annotations

import io
import json
import logging
import hashlib
import os
import zipfile
import xml.etree.ElementTree as ET
from typing import Any

import requests

from backend.data.cache import DEFAULT_TTL_SECONDS, build_cache_key, load_cached

logger = logging.getLogger(__name__)

OPENDART_API_BASE = "https://opendart.fss.or.kr/api"
CORPCODE_URL = f"{OPENDART_API_BASE}/corpCode.xml"


def _api_key_fingerprint(api_key: str) -> str:
    """캐시 키용 인증키 지문(비가역)을 생성합니다."""
    return hashlib.sha256(api_key.encode("utf-8")).hexdigest()[:16]


def _resolve_api_key(api_key: str | None) -> str:
    """환경 변수 또는 인수에서 인증키를 가져옵니다."""
    key = api_key or os.getenv("DART_API_KEY") or os.getenv("CRTFC_KEY") or ""
    key = key.strip()
    if not key:
        raise RuntimeError("DART API 키가 비어 있습니다. .env 의 DART_API_KEY 를 설정하세요.")
    return key


def _fetch_corpcode_zip_bytes(api_key: str) -> bytes:
    """corpCode.xml ZIP 원본을 내려받습니다."""
    try:
        resp = requests.get(CORPCODE_URL, params={"crtfc_key": api_key}, timeout=60)
        resp.raise_for_status()
    except requests.RequestException as exc:
        logger.exception("DART corpCode 다운로드 실패")
        raise RuntimeError("DART corpCode 다운로드 실패") from exc
    return resp.content


def _parse_corpcode_zip(zip_bytes: bytes) -> dict[str, str]:
    """
    corpCode ZIP 안의 XML을 파싱해 ``종목코드(stock_code) → 고유번호(corp_code)`` 맵을 만듭니다.

    비상장 등으로 ``stock_code`` 가 비어 있는 행은 무시합니다.
    """
    mapping: dict[str, str] = {}
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        names = zf.namelist()
        xml_name = next((n for n in names if n.lower().endswith(".xml")), names[0])
        with zf.open(xml_name) as xml_file:
            tree = ET.parse(xml_file)
    root = tree.getroot()
    for row in root.findall(".//list"):
        stock = (row.findtext("stock_code") or "").strip()
        corp = (row.findtext("corp_code") or "").strip()
        if len(stock) == 6 and corp:
            mapping[stock] = corp
    if not mapping:
        raise RuntimeError("DART corpCode XML 파싱 결과가 비어 있습니다.")
    return mapping


def load_stock_to_corp_map(
    api_key: str | None = None,
    *,
    ttl_seconds: int = 24 * DEFAULT_TTL_SECONDS,
) -> dict[str, str]:
    """
    상장 종목코드 → DART ``corp_code`` 매핑을 로드합니다 (디스크 캐시).

    Args:
        api_key: DART 인증키. ``None``이면 환경 변수 사용.
        ttl_seconds: 캐시 TTL.

    Returns:
        ``{"005930": "00126380", ...}`` 형태의 딕셔너리.
    """
    resolved = _resolve_api_key(api_key)

    def _fetch() -> dict[str, str]:
        blob = _fetch_corpcode_zip_bytes(resolved)
        return _parse_corpcode_zip(blob)

    key = build_cache_key("corp_map", _api_key_fingerprint(resolved))
    return load_cached("dart_corp", key, _fetch, ttl_seconds=ttl_seconds)


def find_corp_code(ticker: str, api_key: str | None = None) -> str | None:
    """
    6자리 종목코드로 ``corp_code`` 를 조회합니다.

    Args:
        ticker: 종목코드.
        api_key: DART 인증키.

    Returns:
        매칭되는 ``corp_code`` 또는 ``None``.
    """
    ticker = ticker.strip()
    if len(ticker) != 6 or not ticker.isdigit():
        logger.warning("비정상 종목코드 형식: %s", ticker)
        return None
    mapping = load_stock_to_corp_map(api_key=api_key)
    return mapping.get(ticker)


def dart_request_json(path: str, params: dict[str, Any], *, timeout: int = 30) -> dict[str, Any]:
    """
    Open DART ``*.json`` 엔드포인트를 호출하고 JSON 본문을 반환합니다.

    Args:
        path: ``list.json`` 등 API 상대 경로.
        params: 쿼리 파라미터(``crtfc_key`` 포함 필수).
        timeout: 요청 타임아웃(초).

    Returns:
        파싱된 JSON 객체.

    Raises:
        RuntimeError: HTTP 오류 또는 DART ``status != '000'`` 인 경우.
    """
    url = f"{OPENDART_API_BASE}/{path.lstrip('/')}"
    try:
        resp = requests.get(url, params=params, timeout=timeout)
        resp.raise_for_status()
        data = resp.json()
    except (requests.RequestException, json.JSONDecodeError) as exc:
        logger.exception("DART JSON 요청 실패 path=%s", path)
        raise RuntimeError(f"DART 요청 실패: {path}") from exc

    status = str(data.get("status", ""))
    if status != "000":
        msg = data.get("message") or data.get("msg") or "unknown error"
        logger.warning("DART 비정상 응답 status=%s message=%s", status, msg)
        raise RuntimeError(f"DART 오류 응답: {status} - {msg}")
    return data


def fetch_disclosure_list(
    corp_code: str,
    start_yyyymmdd: str,
    end_yyyymmdd: str,
    *,
    api_key: str | None = None,
    page_no: int = 1,
    page_count: int = 100,
    ttl_seconds: int = DEFAULT_TTL_SECONDS // 6,
) -> dict[str, Any]:
    """
    특정 법인의 공시 목록을 조회합니다 (``list.json``).

    Args:
        corp_code: DART 고유번호.
        start_yyyymmdd: 시작일 ``YYYYMMDD``.
        end_yyyymmdd: 종료일 ``YYYYMMDD``.
        api_key: DART 인증키.
        page_no: 페이지 번호.
        page_count: 페이지당 건수 (최대 100).
        ttl_seconds: 캐시 TTL.

    Returns:
        DART 표준 JSON 응답 (``list`` 필드 등).
    """
    resolved = _resolve_api_key(api_key)

    def _fetch() -> dict[str, Any]:
        params = {
            "crtfc_key": resolved,
            "corp_code": corp_code,
            "bgn_de": start_yyyymmdd,
            "end_de": end_yyyymmdd,
            "page_no": str(page_no),
            "page_count": str(page_count),
        }
        return dart_request_json("list.json", params)

    kid = _api_key_fingerprint(resolved)
    key = build_cache_key(
        "disclosures",
        kid,
        corp_code,
        start_yyyymmdd,
        end_yyyymmdd,
        str(page_no),
        str(page_count),
    )
    return load_cached("dart_list", key, _fetch, ttl_seconds=ttl_seconds)


def fetch_company_outline(
    corp_code: str,
    *,
    api_key: str | None = None,
    ttl_seconds: int = 24 * DEFAULT_TTL_SECONDS,
) -> dict[str, Any]:
    """
    법인 개황을 조회합니다 (``company.json``).

    Args:
        corp_code: DART 고유번호.
        api_key: DART 인증키.
        ttl_seconds: 캐시 TTL.

    Returns:
        DART JSON 응답.
    """
    resolved = _resolve_api_key(api_key)

    def _fetch() -> dict[str, Any]:
        params = {"crtfc_key": resolved, "corp_code": corp_code}
        return dart_request_json("company.json", params)

    kid = _api_key_fingerprint(resolved)
    key = build_cache_key("company", kid, corp_code)
    return load_cached("dart_company", key, _fetch, ttl_seconds=ttl_seconds)


def fetch_financial_accounts(
    corp_code: str,
    business_year: str,
    report_code: str,
    *,
    fs_div: str = "CFS",
    api_key: str | None = None,
    ttl_seconds: int = 24 * DEFAULT_TTL_SECONDS,
) -> dict[str, Any]:
    """
    재무제표 주요 계정과 목록을 조회합니다 (``fnlttSinglAcntAll.json``).

    ``report_code`` 예시(공시 유형 코드):

    - ``11011``: 사업보고서
    - ``11012``: 반기보고서
    - ``11013``: 1분기보고서
    - ``11014``: 3분기보고서

    Args:
        corp_code: DART 고유번호.
        business_year: 사업 연도(문자열 4자리, 예: ``2024``).
        report_code: 공시유형 코드.
        fs_div: ``CFS``(연결) 또는 ``OFS``(별도).
        api_key: DART 인증키.
        ttl_seconds: 캐시 TTL.

    Returns:
        DART JSON 응답(``list`` 등).
    """
    resolved = _resolve_api_key(api_key)

    def _fetch() -> dict[str, Any]:
        params = {
            "crtfc_key": resolved,
            "corp_code": corp_code,
            "bsns_year": business_year,
            "reprt_code": report_code,
            "fs_div": fs_div,
        }
        return dart_request_json("fnlttSinglAcntAll.json", params)

    kid = _api_key_fingerprint(resolved)
    key = build_cache_key("fnltt", kid, corp_code, business_year, report_code, fs_div)
    return load_cached("dart_fnltt", key, _fetch, ttl_seconds=ttl_seconds)

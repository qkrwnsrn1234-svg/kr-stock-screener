"""
KRX 상장 목록 기반 종목 검색 로직입니다.
"""

from __future__ import annotations

import logging
from typing import Any

import pandas as pd

from backend.data.finance_data import list_krx_symbols

logger = logging.getLogger(__name__)

DEFAULT_SEARCH_LIMIT = 8


def _clean_text(value: Any) -> str:
    """검색 비교용 문자열을 안전하게 정리합니다."""
    if value is None or pd.isna(value):
        return ""
    return str(value).strip()


def _row_to_item(row: pd.Series) -> dict[str, str | None]:
    """상장 목록 한 행을 검색 응답 항목으로 변환합니다."""
    ticker = _clean_text(row.get("Code")).zfill(6)
    name = _clean_text(row.get("Name"))
    market = _clean_text(row.get("Market")) or None
    sector = _clean_text(row.get("Dept")) or None
    return {
        "ticker": ticker,
        "name": name,
        "market": market,
        "sector": sector,
    }


def search_krx_symbols(query: str, limit: int = DEFAULT_SEARCH_LIMIT) -> list[dict[str, str | None]]:
    """
    종목명 또는 6자리 종목코드로 KRX 상장 종목을 검색합니다.

    Args:
        query: 사용자가 입력한 검색어.
        limit: 최대 응답 개수.

    Returns:
        검색 우선순위로 정렬된 종목 목록.
    """
    q = query.strip()
    if not q:
        return []

    normalized_limit = max(1, min(int(limit), 20))

    try:
        listing = list_krx_symbols(None)
    except Exception as exc:
        logger.exception("KRX 상장 목록 검색 실패 query=%s", q)
        raise RuntimeError("KRX 상장 목록을 조회하지 못했습니다.") from exc

    if listing is None or listing.empty or "Code" not in listing.columns or "Name" not in listing.columns:
        return []

    df = listing.copy()
    df["Code"] = df["Code"].astype(str).str.zfill(6)
    df["Name"] = df["Name"].astype(str).str.strip()

    q_lower = q.lower()
    q_digits = "".join(ch for ch in q if ch.isdigit())

    def _rank(row: pd.Series) -> int | None:
        """일치 유형별 검색 우선순위를 계산합니다."""
        code = _clean_text(row.get("Code"))
        name = _clean_text(row.get("Name"))
        name_lower = name.lower()

        if q_digits and code == q_digits.zfill(6):
            return 0
        if name == q:
            return 1
        if q_digits and code.startswith(q_digits):
            return 2
        if name_lower.startswith(q_lower):
            return 3
        if q_digits and q_digits in code:
            return 4
        if q_lower in name_lower:
            return 5
        return None

    ranked: list[tuple[int, dict[str, str | None]]] = []
    for _, row in df.iterrows():
        rank = _rank(row)
        if rank is None:
            continue
        item = _row_to_item(row)
        if item["ticker"].isdigit() and item["name"]:
            ranked.append((rank, item))

    ranked.sort(key=lambda pair: (pair[0], pair[1]["ticker"] or ""))
    return [item for _, item in ranked[:normalized_limit]]

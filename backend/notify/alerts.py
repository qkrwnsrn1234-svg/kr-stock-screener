"""
스크리닝 결과 기반 알림 전송(Slack 호환 Incoming Webhook, 선택적 SMTP).

환경 변수로 채널을 켜고, 동일 종목·유형별 쿨다운으로 스팸을 줄입니다.
"""

from __future__ import annotations

import logging
import os
import smtplib
import threading
import time
from email.mime.text import MIMEText

import requests

from backend.agents.models import ScreeningResult

logger = logging.getLogger(__name__)

_COOLDOWN_LOCK = threading.Lock()
# (종목코드, 알림 유형) → 마지막 전송 시각(monotonic)
_LAST_SEND_MONO: dict[str, float] = {}


def _env_flag(name: str, default: bool = False) -> bool:
    """환경 변수를 참/거짓으로 해석합니다."""
    raw = os.getenv(name, "")
    if not raw:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def webhook_url() -> str:
    """Slack·호환 Incoming Webhook URL."""
    return (os.getenv("ALERT_WEBHOOK_URL") or "").strip()


def alerts_any_channel_configured() -> bool:
    """웹훅 또는 메일 중 하나라도 설정되었는지."""
    if webhook_url():
        return True
    if (os.getenv("ALERT_SMTP_HOST") or "").strip() and (os.getenv("ALERT_EMAIL_TO") or "").strip():
        return True
    return False


def alert_on_overheat() -> bool:
    """과열 알림 전송 여부."""
    return _env_flag("ALERT_ON_OVERHEAT", default=True)


def alert_on_undervalue() -> bool:
    """저평가(스코어 임계 이상) 알림 전송 여부."""
    return _env_flag("ALERT_ON_UNDERVALUE", default=True)


def undervalue_min_score() -> float:
    """언더밸류 종합 점수가 이 값 이상이면 저평가 후보로 알림합니다."""
    try:
        return float(os.getenv("ALERT_UNDERVALUE_MIN_SCORE", "72"))
    except ValueError:
        return 72.0


def cooldown_seconds() -> float:
    """동일 종목·유형 알림 최소 간격(초)."""
    try:
        return max(60.0, float(os.getenv("ALERT_COOLDOWN_SECONDS", "3600")))
    except ValueError:
        return 3600.0


def _cooldown_key(ticker: str, kind: str) -> str:
    return f"{ticker.strip()}:{kind}"


def _can_send_after_cooldown(ticker: str, kind: str) -> bool:
    """쿨다운이 지났으면 True (전송 전 검사만)."""
    key = _cooldown_key(ticker, kind)
    now = time.monotonic()
    cd = cooldown_seconds()
    with _COOLDOWN_LOCK:
        prev = _LAST_SEND_MONO.get(key, 0.0)
        return now - prev >= cd


def _commit_cooldown(ticker: str, kind: str) -> None:
    """전송 성공 후 쿨다운 시각을 갱신합니다."""
    key = _cooldown_key(ticker, kind)
    with _COOLDOWN_LOCK:
        _LAST_SEND_MONO[key] = time.monotonic()


def _is_overheat(sr: ScreeningResult) -> bool:
    if sr.overheat_flag:
        return True
    if sr.overheat_alert and (sr.overheat_alert.level or "").strip() not in ("", "정상"):
        return True
    return False


def _is_undervalue(sr: ScreeningResult) -> bool:
    score = float(sr.undervalue_score or 0.0)
    return score >= undervalue_min_score()


def _format_lines(results: list[ScreeningResult], source: str) -> tuple[str, list[tuple[str, str]]]:
    """
    알림 본문과 전송 시 쿨다운을 갱신할 (종목, 유형) 목록을 만듭니다.

    Returns:
        (본문 문자열, [(ticker, kind), ...]) — 본문이 비면 전송 생략.
    """
    lines: list[str] = [f"*KR Stock Screener 알림* (`source={source}`)"]
    marks: list[tuple[str, str]] = []
    oh_on = alert_on_overheat()
    uv_on = alert_on_undervalue()

    for sr in results:
        ticker = sr.ticker
        row_bits: list[str] = []

        if oh_on and _is_overheat(sr) and _can_send_after_cooldown(ticker, "overheat"):
            lvl = sr.overheat_alert.level if sr.overheat_alert else "과열"
            heat = sr.overheat_alert.heat_score if sr.overheat_alert else 0.0
            rs = sr.overheat_alert.reasons if sr.overheat_alert else []
            reason_txt = "; ".join(rs) if rs else ""
            row_bits.append(f"과열 `{lvl}` (강도 {heat:.0f}) {reason_txt}".strip())
            marks.append((ticker, "overheat"))

        if uv_on and _is_undervalue(sr) and _can_send_after_cooldown(ticker, "undervalue"):
            sc = float(sr.undervalue_score or 0.0)
            row_bits.append(f"저평가 후보 언더밸류 {sc:.1f}점 (임계 {undervalue_min_score():.0f})")
            marks.append((ticker, "undervalue"))

        if row_bits:
            lines.append(f"• `{ticker}`: " + " | ".join(row_bits))

    if len(lines) <= 1:
        return "", []

    body = "\n".join(lines)
    return body, marks


def _post_webhook(text: str) -> bool:
    """Slack Incoming Webhook 형식(`text` 필드)으로 POST합니다."""
    url = webhook_url()
    if not url:
        return False
    try:
        resp = requests.post(url, json={"text": text}, timeout=20)
        resp.raise_for_status()
        logger.info("알림 웹훅 전송 완료")
        return True
    except Exception as exc:
        logger.warning("알림 웹훅 전송 실패: %s", exc)
        return False


def _send_smtp_email(subject: str, body: str) -> bool:
    """환경 변수 기준 SMTP로 단문 메일을 보냅니다."""
    host = (os.getenv("ALERT_SMTP_HOST") or "").strip()
    to_raw = (os.getenv("ALERT_EMAIL_TO") or "").strip()
    from_addr = (os.getenv("ALERT_EMAIL_FROM") or "").strip()
    if not host or not to_raw or not from_addr:
        return False

    port = int(os.getenv("ALERT_SMTP_PORT", "587"))
    user = (os.getenv("ALERT_SMTP_USER") or "").strip()
    password = (os.getenv("ALERT_SMTP_PASSWORD") or "").strip()
    use_tls = _env_flag("ALERT_SMTP_USE_TLS", default=True)

    recipients = [x.strip() for x in to_raw.split(",") if x.strip()]
    if not recipients:
        return False

    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = ", ".join(recipients)

    try:
        if use_tls:
            with smtplib.SMTP(host, port, timeout=30) as smtp:
                smtp.starttls()
                if user and password:
                    smtp.login(user, password)
                smtp.sendmail(from_addr, recipients, msg.as_string())
        else:
            with smtplib.SMTP_SSL(host, port, timeout=30) as smtp:
                if user and password:
                    smtp.login(user, password)
                smtp.sendmail(from_addr, recipients, msg.as_string())
        logger.info("알림 메일 전송 완료 receivers=%s", len(recipients))
        return True
    except Exception as exc:
        logger.warning("알림 메일 전송 실패: %s", exc)
        return False


def notify_screening_results_sync(results: list[ScreeningResult], source: str) -> None:
    """
    스크리닝 결과에 대해 조건을 만족하면 웹훅·메일을 보냅니다.

    블로킹 IO 포함 — ``asyncio.to_thread``에서 호출하세요.

    Args:
        results: 스크리닝 레코드 목록.
        source: 호출 출처 라벨(예: ``screen``, ``analyze``).
    """
    if not results or not alerts_any_channel_configured():
        return

    body, marks = _format_lines(results, source)
    if not body or not marks:
        return

    subject = f"[KR Stock Screener] 알림 ({source})"
    want_webhook = bool(webhook_url())
    want_mail = bool((os.getenv("ALERT_SMTP_HOST") or "").strip())

    webhook_ok = _post_webhook(body) if want_webhook else True
    mail_ok = _send_smtp_email(subject, body) if want_mail else True

    if webhook_ok or mail_ok:
        for t, k in marks:
            _commit_cooldown(t, k)
    else:
        logger.debug("알림 채널 전송 실패로 쿨다운 미적용 source=%s", source)

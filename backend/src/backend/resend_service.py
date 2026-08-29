"""Resend transport for transactional email.

A provider module: it knows how to put a message on the wire, and nothing about
which message. Template selection and provider choice live in
:mod:`backend.email_service`, which is the only module that should import this one.

Note: Resend only sends from a *verified* domain — verify ``vicoa.ai`` (or the
sending subdomain) in the Resend dashboard and add its DNS records before these
sends will succeed.
"""

from __future__ import annotations

import logging

import httpx

from shared.config import settings

logger = logging.getLogger(__name__)

RESEND_ENDPOINT = "https://api.resend.com/emails"


def resend_is_configured() -> bool:
    """Return True when required Resend settings are available.

    Resend is a dormant fallback now: :mod:`backend.email_service` only reaches
    for it when Mailgun is left unconfigured, so setting these no longer diverts
    sending away from Mailgun on its own.
    """
    return bool(settings.resend_api_key and settings.resend_from_email)


async def send_email(
    to_email: str,
    subject: str,
    body_html: str,
    *,
    bcc_email: str | None = None,
    reply_to: str | None = None,
) -> bool:
    """Send one email through Resend. Returns True on success, False on any failure."""
    if not resend_is_configured():
        logger.warning("Resend is not configured; skipping email '%s'", subject)
        return False

    payload: dict[str, object] = {
        "from": settings.resend_from_email,
        "to": [to_email],
        "subject": subject,
        "html": body_html,
    }
    if bcc_email:
        payload["bcc"] = [bcc_email]
    if reply_to:
        payload["reply_to"] = reply_to

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                RESEND_ENDPOINT,
                json=payload,
                headers={"Authorization": f"Bearer {settings.resend_api_key}"},
            )
        if response.status_code >= 400:
            logger.error(
                "Resend email send failed: subject='%s' status=%s body=%s",
                subject,
                response.status_code,
                response.text,
            )
            return False
        return True
    except Exception as exc:
        logger.error("Resend email send error for '%s': %s", subject, exc)
        return False

"""Mailgun transport for transactional email.

A provider module: it knows how to put a message on the wire, and nothing about
which message. Template selection and provider choice live in
:mod:`backend.email_service`, which is the only module that should import this one.

This is the primary transport: :mod:`backend.email_service` sends over Mailgun
whenever it is configured, which is the case in production. Resend is kept as a
dormant fallback for when Mailgun is unconfigured.
"""

from __future__ import annotations

import logging

import httpx

from shared.config import settings

logger = logging.getLogger(__name__)


def mailgun_is_configured() -> bool:
    """Return True when required Mailgun settings are available."""
    return bool(
        settings.mailgun_api_key
        and settings.mailgun_domain
        and settings.mailgun_from_email
    )


async def send_email(
    to_email: str,
    subject: str,
    body_html: str,
    *,
    bcc_email: str | None = None,
    reply_to: str | None = None,
) -> bool:
    """Send one email through Mailgun. Returns True on success, False on any failure."""
    if not mailgun_is_configured():
        logger.warning("Mailgun is not configured; skipping email '%s'", subject)
        return False

    endpoint = f"https://api.mailgun.net/v3/{settings.mailgun_domain}/messages"
    data: dict[str, object] = {
        "from": settings.mailgun_from_email,
        "to": [to_email],
        "subject": subject,
        "html": body_html,
    }
    if bcc_email:
        data["bcc"] = [bcc_email]
    if reply_to:
        data["h:Reply-To"] = reply_to

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                endpoint,
                data=data,
                auth=("api", settings.mailgun_api_key),
            )
        if response.status_code >= 400:
            logger.error(
                "Mailgun email send failed: subject='%s' status=%s body=%s",
                subject,
                response.status_code,
                response.text,
            )
            return False
        return True
    except Exception as exc:
        logger.error("Mailgun email send error for '%s': %s", subject, exc)
        return False

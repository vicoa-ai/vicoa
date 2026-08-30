"""Transactional email: provider plumbing + the unbranded support forward.

The provider modules (:mod:`backend.resend_service`, :mod:`backend.mailgun_service`)
only know how to put a message on the wire. :func:`_send` picks the provider;
call sites import from here, never from a provider module directly.

Mailgun is the primary sender: whenever it is configured (``MAILGUN_API_KEY``,
``MAILGUN_DOMAIN`` and ``MAILGUN_FROM_EMAIL``) everything goes out over Mailgun.
Resend stays wired up as a dormant fallback and only sends when Mailgun is left
unconfigured. Production runs on Mailgun.
"""

from __future__ import annotations

import logging

from backend import mailgun_service, resend_service

logger = logging.getLogger(__name__)


async def _send(
    to_email: str,
    subject: str,
    body_html: str,
    *,
    bcc_email: str | None = None,
    reply_to: str | None = None,
) -> bool:
    """Deliver one email through whichever provider is configured."""
    if mailgun_service.mailgun_is_configured():
        return await mailgun_service.send_email(
            to_email, subject, body_html, bcc_email=bcc_email, reply_to=reply_to
        )
    return await resend_service.send_email(
        to_email, subject, body_html, bcc_email=bcc_email, reply_to=reply_to
    )


async def send_support_issue_email(
    to_email: str,
    from_user_email: str,
    from_user_name: str,
    message: str,
) -> bool:
    """Send a user-submitted issue report to the support inbox."""
    display_name = from_user_name.strip() if from_user_name.strip() else from_user_email
    subject = f"Issue report from {display_name}"
    body_html = (
        "<div style=\"font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;\">"
        f"<p><strong>From:</strong> {display_name} ({from_user_email})</p>"
        "<p><strong>Message:</strong></p>"
        f'<p style="white-space: pre-wrap;">{message}</p>'
        "</div>"
    )
    return await _send(to_email, subject, body_html, reply_to=from_user_email)


def email_is_configured() -> bool:
    """Whether any transport is wired up. False -> callers must degrade, not fail."""
    return (
        mailgun_service.mailgun_is_configured() or resend_service.resend_is_configured()
    )


async def send_auth_code_email(to_email: str, code: str, purpose: str) -> bool:
    """Send a one-time code for the built-in auth provider.

    Deliberately unbranded: this is open-core code that any self-hosted
    deployment sends from its own domain.
    """
    action = (
        "confirm your email address"
        if purpose == "verify_email"
        else "reset your password"
    )
    subject = f"Your verification code: {code}"
    body_html = (
        "<div style=\"font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;\">"
        f"<p>Use this code to {action}:</p>"
        f'<p style="font-size: 28px; letter-spacing: 4px;"><strong>{code}</strong></p>'
        "<p>It expires in 15 minutes. If you did not request it, you can ignore this email.</p>"
        "</div>"
    )
    return await _send(to_email, subject, body_html)

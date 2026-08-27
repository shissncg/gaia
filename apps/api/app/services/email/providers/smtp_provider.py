"""SMTP adapter — stdlib smtplib, no third-party dependency for one adapter.

Self-host escape hatch: EMAIL_PROVIDER=smtp lets an operator point at any
STARTTLS-capable relay (a corporate SMTP server, a local Postfix/Mailhog,
etc.) without a Resend account.
"""

import asyncio
from email.mime.text import MIMEText
import smtplib

from app.config.settings import settings
from app.services.email.models import EmailMessage


class SMTPEmailProvider:
    """EmailProvider backed by a plain SMTP relay.

    Does not implement MarketingContactsProvider — audience/contact
    management is a Resend-specific capability. Senders isinstance-check for
    that capability and skip it silently when absent, so audience opt-in is
    a no-op on this provider by design (not a bug to fix here).
    """

    async def send(self, message: EmailMessage) -> None:
        """Deliver one message via SMTP. Raises on failure."""
        if not settings.SMTP_HOST:
            raise ValueError(
                "SMTP_HOST is not set — configure SMTP_HOST/PORT/USERNAME/PASSWORD/FROM "
                "in your environment, or switch EMAIL_PROVIDER away from 'smtp'."
            )

        sender = message.sender or settings.SMTP_FROM
        if not sender:
            raise ValueError(
                "No sender address: EmailMessage.sender is empty and SMTP_FROM is not set."
            )

        msg = MIMEText(message.html, "html")
        msg["From"] = sender
        msg["To"] = ", ".join(message.to)
        msg["Subject"] = message.subject
        if message.reply_to:
            msg["Reply-To"] = message.reply_to
        if message.headers:
            for key, value in message.headers.items():
                msg[key] = value

        # smtplib is synchronous — run it in a thread to keep the event loop
        # free, mirroring the Resend adapter's sync-through-thread pattern.
        await asyncio.to_thread(self._send_sync, msg, message.to, sender)

    def _send_sync(self, msg: MIMEText, recipients: list[str], sender: str) -> None:
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=30) as client:
            if settings.SMTP_STARTTLS:
                client.starttls()
            if settings.SMTP_USERNAME:
                client.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD or "")
            client.sendmail(sender, recipients, msg.as_string())

"""Unit tests for the SMTP email provider (EMAIL_PROVIDER=smtp).

Boundary mocked: smtplib.SMTP (the network client). Everything else — MIME
construction, header population, the provider-registry resolution, and the
fail-loud guards — is the real production code.
"""

from unittest.mock import MagicMock, patch

import pytest

from app.services.email.models import EmailMessage
from app.services.email.providers import get_email_provider
from app.services.email.providers.smtp_provider import SMTPEmailProvider

PROVIDER_MOD = "app.services.email.providers.smtp_provider"


@pytest.fixture(autouse=True)
def _clear_provider_cache():
    """get_email_provider is @lru_cache(maxsize=1) — never leak across tests."""
    get_email_provider.cache_clear()
    yield
    get_email_provider.cache_clear()


class TestProviderRegistry:
    def test_smtp_setting_resolves_to_the_smtp_provider(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr("app.services.email.providers.settings.EMAIL_PROVIDER", "smtp")
        provider = get_email_provider()
        assert isinstance(provider, SMTPEmailProvider)


@pytest.fixture
def smtp_settings(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(f"{PROVIDER_MOD}.settings.SMTP_HOST", "smtp.example.com")
    monkeypatch.setattr(f"{PROVIDER_MOD}.settings.SMTP_PORT", 587)
    monkeypatch.setattr(f"{PROVIDER_MOD}.settings.SMTP_USERNAME", "gaia")
    monkeypatch.setattr(f"{PROVIDER_MOD}.settings.SMTP_PASSWORD", "s3cr3t")
    monkeypatch.setattr(f"{PROVIDER_MOD}.settings.SMTP_FROM", "GAIA <no-reply@example.com>")
    monkeypatch.setattr(f"{PROVIDER_MOD}.settings.SMTP_STARTTLS", True)


class TestSMTPProviderSend:
    async def test_composes_and_sends_correct_mime(self, smtp_settings) -> None:
        with patch(f"{PROVIDER_MOD}.smtplib.SMTP") as m_smtp_cls:
            m_client = MagicMock()
            m_smtp_cls.return_value.__enter__.return_value = m_client
            provider = SMTPEmailProvider()

            await provider.send(
                EmailMessage(
                    sender="GAIA <no-reply@heygaia.io>",
                    to=["alice@example.com", "bob@example.com"],
                    subject="Hello",
                    html="<p>hi</p>",
                    reply_to="support@heygaia.io",
                    headers={"X-Custom": "yes"},
                )
            )

        m_smtp_cls.assert_called_once_with("smtp.example.com", 587, timeout=30)
        m_client.starttls.assert_called_once()
        m_client.login.assert_called_once_with("gaia", "s3cr3t")
        sender, recipients, raw_message = m_client.sendmail.call_args[0]
        assert sender == "GAIA <no-reply@heygaia.io>"
        assert recipients == ["alice@example.com", "bob@example.com"]
        assert "Subject: Hello" in raw_message
        assert "Reply-To: support@heygaia.io" in raw_message
        # The composed MIME must be an html part carrying the real body, with
        # the sender and comma-joined recipients in the headers (the envelope
        # sender/recipients above are separate), and custom headers applied.
        assert "Content-Type: text/html" in raw_message
        assert "<p>hi</p>" in raw_message
        assert "From: GAIA <no-reply@heygaia.io>" in raw_message
        assert "To: alice@example.com, bob@example.com" in raw_message
        assert "X-Custom: yes" in raw_message

    async def test_skips_starttls_when_disabled(
        self, smtp_settings, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(f"{PROVIDER_MOD}.settings.SMTP_STARTTLS", False)
        with patch(f"{PROVIDER_MOD}.smtplib.SMTP") as m_smtp_cls:
            m_client = MagicMock()
            m_smtp_cls.return_value.__enter__.return_value = m_client
            provider = SMTPEmailProvider()
            await provider.send(
                EmailMessage(sender="s", to=["a@example.com"], subject="t", html="h")
            )

        m_client.starttls.assert_not_called()

    async def test_skips_login_when_no_username(
        self, smtp_settings, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(f"{PROVIDER_MOD}.settings.SMTP_USERNAME", None)
        with patch(f"{PROVIDER_MOD}.smtplib.SMTP") as m_smtp_cls:
            m_client = MagicMock()
            m_smtp_cls.return_value.__enter__.return_value = m_client
            provider = SMTPEmailProvider()
            await provider.send(
                EmailMessage(sender="s", to=["a@example.com"], subject="t", html="h")
            )

        m_client.login.assert_not_called()

    async def test_username_without_password_logs_in_with_empty_password(
        self, smtp_settings, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Some relays authenticate by username alone; the password must be
        exactly the empty string then, not a placeholder."""
        monkeypatch.setattr(f"{PROVIDER_MOD}.settings.SMTP_PASSWORD", None)
        with patch(f"{PROVIDER_MOD}.smtplib.SMTP") as m_smtp_cls:
            m_client = MagicMock()
            m_smtp_cls.return_value.__enter__.return_value = m_client
            provider = SMTPEmailProvider()
            await provider.send(
                EmailMessage(sender="s", to=["a@example.com"], subject="t", html="h")
            )

        m_client.login.assert_called_once_with("gaia", "")

    async def test_falls_back_to_smtp_from_when_sender_blank(self, smtp_settings) -> None:
        with patch(f"{PROVIDER_MOD}.smtplib.SMTP") as m_smtp_cls:
            m_client = MagicMock()
            m_smtp_cls.return_value.__enter__.return_value = m_client
            provider = SMTPEmailProvider()
            await provider.send(
                EmailMessage(sender="", to=["a@example.com"], subject="t", html="h")
            )

        sender, _recipients, _raw = m_client.sendmail.call_args[0]
        assert sender == "GAIA <no-reply@example.com>"

    async def test_missing_smtp_host_raises_with_an_actionable_message(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(f"{PROVIDER_MOD}.settings.SMTP_HOST", None)
        provider = SMTPEmailProvider()

        with pytest.raises(ValueError) as exc_info:
            await provider.send(
                EmailMessage(sender="s", to=["a@example.com"], subject="t", html="h")
            )
        # Exact equality, not substring: this message is the operator's whole
        # remediation path, so any corruption of it must fail here.
        assert str(exc_info.value) == (
            "SMTP_HOST is not set — configure SMTP_HOST/PORT/USERNAME/PASSWORD/FROM "
            "in your environment, or switch EMAIL_PROVIDER away from 'smtp'."
        )

    async def test_missing_sender_and_smtp_from_raises(
        self, smtp_settings, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(f"{PROVIDER_MOD}.settings.SMTP_FROM", None)
        provider = SMTPEmailProvider()

        with pytest.raises(ValueError) as exc_info:
            await provider.send(
                EmailMessage(sender="", to=["a@example.com"], subject="t", html="h")
            )
        assert str(exc_info.value) == (
            "No sender address: EmailMessage.sender is empty and SMTP_FROM is not set."
        )

    async def test_failure_propagates(self, smtp_settings) -> None:
        with patch(f"{PROVIDER_MOD}.smtplib.SMTP") as m_smtp_cls:
            m_smtp_cls.return_value.__enter__.side_effect = OSError("connection refused")
            provider = SMTPEmailProvider()

            with pytest.raises(OSError, match="connection refused"):
                await provider.send(
                    EmailMessage(sender="s", to=["a@example.com"], subject="t", html="h")
                )

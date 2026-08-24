"""Slack OAuth redirect URI — must derive from HOST everywhere.

Regression: DevelopmentSettings used to hardcode a redirectmeto.com/localhost
proxy override, breaking Slack account linking on every self-hosted
(ENV=development) deploy that isn't running on localhost.
"""

import pytest


@pytest.fixture(autouse=True)
def _fresh_settings():
    from app.config.settings import get_settings

    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_slack_redirect_derives_from_host_in_development(monkeypatch):
    """Regression: DevelopmentSettings used to hardcode a redirectmeto.com/localhost
    proxy, breaking Slack linking on every self-hosted (ENV=development) deploy."""
    from app.config.settings import get_settings

    monkeypatch.setenv("ENV", "development")
    monkeypatch.setenv("HOST", "https://api.gaia.example.com")
    monkeypatch.delenv("SLACK_OAUTH_REDIRECT_URI_OVERRIDE", raising=False)
    s = get_settings()
    assert s.SLACK_OAUTH_REDIRECT_URI == (
        "https://api.gaia.example.com/api/v1/platform-auth/slack/callback"
    )


def test_slack_redirect_override_wins(monkeypatch):
    """The override remains available as an explicit opt-in (vendor-local dev
    behind Slack's https-only rule), just never a shipped default."""
    from app.config.settings import get_settings

    monkeypatch.setenv("ENV", "development")
    monkeypatch.setenv("HOST", "https://api.gaia.example.com")
    monkeypatch.setenv(
        "SLACK_OAUTH_REDIRECT_URI_OVERRIDE",
        "https://redirectmeto.com/http://localhost:8000/api/v1/platform-auth/slack/callback",
    )
    s = get_settings()
    assert s.SLACK_OAUTH_REDIRECT_URI == (
        "https://redirectmeto.com/http://localhost:8000/api/v1/platform-auth/slack/callback"
    )

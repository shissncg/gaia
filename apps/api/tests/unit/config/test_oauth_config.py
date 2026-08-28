"""Unit tests for the Composio auth-config override map (COMPOSIO_AUTH_CONFIGS).

A self-hoster's Composio project has its own auth config ids per toolkit —
the vendor's hardcoded ids in OAUTH_INTEGRATIONS 404 against it. These tests
cover the override parsing/substitution in get_composio_social_configs(),
not the OAUTH_INTEGRATIONS catalog itself.
"""

from __future__ import annotations

import pytest

from app.config.oauth_config import get_composio_social_configs, get_integration_by_config

# Vendor defaults (OAUTH_INTEGRATIONS) as of this test's writing — pinned so a
# behavior change in the catalog itself surfaces as a clear failure here.
GMAIL_DEFAULT_AUTH_CONFIG_ID = "ac_svLPDmjcTVMX"
GOOGLECALENDAR_DEFAULT_AUTH_CONFIG_ID = "ac_exqcpnLvCzGJ"


@pytest.fixture(autouse=True)
def _clear_composio_config_cache():
    """Both lookups are @cache'd — never leak overrides across tests."""
    get_composio_social_configs.cache_clear()
    get_integration_by_config.cache_clear()
    yield
    get_composio_social_configs.cache_clear()
    get_integration_by_config.cache_clear()


def test_an_override_for_gmail_replaces_only_gmails_auth_config_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.config.oauth_config.settings.COMPOSIO_AUTH_CONFIGS",
        '{"gmail": "ac_yourGmailCfg"}',
    )

    configs = get_composio_social_configs()

    # gmail's provider key is "gmail" (id == provider for this integration).
    assert configs["gmail"].auth_config_id == "ac_yourGmailCfg"
    # googlecalendar's provider key is "google" — untouched, still the default.
    assert configs["google"].auth_config_id == GOOGLECALENDAR_DEFAULT_AUTH_CONFIG_ID


def test_overrides_key_on_integration_id_not_on_the_output_providers_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # "google" is the output dict's key for googlecalendar, but the override
    # map is keyed by OAuthIntegration.id ("googlecalendar") — a self-hoster
    # typing the provider key instead must not silently match anything.
    monkeypatch.setattr(
        "app.config.oauth_config.settings.COMPOSIO_AUTH_CONFIGS",
        '{"google": "ac_shouldNotApply"}',
    )

    configs = get_composio_social_configs()

    assert configs["google"].auth_config_id == GOOGLECALENDAR_DEFAULT_AUTH_CONFIG_ID


def test_overriding_googlecalendar_by_its_integration_id_works(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.config.oauth_config.settings.COMPOSIO_AUTH_CONFIGS",
        '{"googlecalendar": "ac_yourCalendarCfg"}',
    )

    configs = get_composio_social_configs()

    assert configs["google"].auth_config_id == "ac_yourCalendarCfg"
    assert configs["gmail"].auth_config_id == GMAIL_DEFAULT_AUTH_CONFIG_ID


def test_empty_setting_is_a_quiet_noop(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.config.oauth_config.settings.COMPOSIO_AUTH_CONFIGS", "")

    configs = get_composio_social_configs()

    assert configs["gmail"].auth_config_id == GMAIL_DEFAULT_AUTH_CONFIG_ID
    assert configs["google"].auth_config_id == GOOGLECALENDAR_DEFAULT_AUTH_CONFIG_ID


def test_malformed_json_fails_loud_naming_the_setting(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.config.oauth_config.settings.COMPOSIO_AUTH_CONFIGS", "{not valid json")

    with pytest.raises(ValueError, match="COMPOSIO_AUTH_CONFIGS is not valid JSON"):
        get_composio_social_configs()


@pytest.mark.regression
def test_reverse_lookup_resolves_an_overridden_auth_config_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression: the OAuth callback and Composio webhook map a connected
    account back to an integration via get_integration_by_config. On a live
    self-hosted deploy the Google consent completed and the callback then
    failed with "Integration config not found" — the reverse lookup compared
    against the vendor's hardcoded ids only, never the self-hoster's
    COMPOSIO_AUTH_CONFIGS overrides that the connect path had just used.
    """
    monkeypatch.setattr(
        "app.config.oauth_config.settings.COMPOSIO_AUTH_CONFIGS",
        '{"gmail": "ac_yourGmailCfg"}',
    )

    integration = get_integration_by_config("ac_yourGmailCfg")

    assert integration is not None, (
        "overridden auth config id did not resolve — a self-hoster's OAuth "
        "callback fails with 'Integration config not found' after a "
        "successful Google consent"
    )
    assert integration.id == "gmail"


def test_reverse_lookup_ignores_a_vendor_id_that_was_overridden(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Once gmail is overridden, the vendor's default id no longer identifies
    # gmail on this deployment — matching it would resurrect the split-brain.
    monkeypatch.setattr(
        "app.config.oauth_config.settings.COMPOSIO_AUTH_CONFIGS",
        '{"gmail": "ac_yourGmailCfg"}',
    )

    assert get_integration_by_config(GMAIL_DEFAULT_AUTH_CONFIG_ID) is None


def test_reverse_lookup_still_resolves_vendor_defaults_without_overrides(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.config.oauth_config.settings.COMPOSIO_AUTH_CONFIGS", "")

    integration = get_integration_by_config(GMAIL_DEFAULT_AUTH_CONFIG_ID)

    assert integration is not None
    assert integration.id == "gmail"


def test_a_non_object_json_value_fails_loud(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.config.oauth_config.settings.COMPOSIO_AUTH_CONFIGS", '["gmail", "ac_x"]'
    )

    with pytest.raises(ValueError) as exc_info:
        get_composio_social_configs()
    # Exact equality — a substring match cannot notice message corruption.
    assert str(exc_info.value) == (
        "COMPOSIO_AUTH_CONFIGS must be a JSON object mapping integration id -> auth config id"
    )

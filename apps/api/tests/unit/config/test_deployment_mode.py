"""DEPLOYMENT_MODE — the single cloud-vs-self-host switch (see .agents/plans/selfhost)."""

import pytest

from app.config.settings import get_settings


@pytest.fixture(autouse=True)
def _fresh_settings():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_deployment_mode_defaults_to_self_hosted(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DEPLOYMENT_MODE", raising=False)
    assert get_settings().DEPLOYMENT_MODE == "self_hosted"


def test_deployment_mode_cloud_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEPLOYMENT_MODE", "cloud")
    assert get_settings().DEPLOYMENT_MODE == "cloud"

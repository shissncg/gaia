"""``session_cookie_kwargs`` — the single source for the three ``wos_session``
set/delete sites (middleware refresh, OAuth callback, logout) so their
security attributes (Secure, SameSite, Domain) can never drift apart.
"""

import pytest


def test_secure_derived_from_https_host(monkeypatch) -> None:
    from app.utils import auth_utils

    monkeypatch.setattr(auth_utils.settings, "COOKIE_SECURE", None)
    monkeypatch.setattr(auth_utils.settings, "HOST", "https://api.gaia.example.com")
    monkeypatch.setattr(auth_utils.settings, "COOKIE_SAMESITE", "lax")
    monkeypatch.setattr(auth_utils.settings, "COOKIE_DOMAIN", None)

    kwargs = auth_utils.session_cookie_kwargs()

    assert kwargs["secure"] is True


def test_secure_derived_from_http_host(monkeypatch) -> None:
    from app.utils import auth_utils

    monkeypatch.setattr(auth_utils.settings, "COOKIE_SECURE", None)
    monkeypatch.setattr(auth_utils.settings, "HOST", "http://localhost:8000")
    monkeypatch.setattr(auth_utils.settings, "COOKIE_SAMESITE", "lax")
    monkeypatch.setattr(auth_utils.settings, "COOKIE_DOMAIN", None)

    kwargs = auth_utils.session_cookie_kwargs()

    assert kwargs["secure"] is False


def test_explicit_cookie_secure_wins(monkeypatch) -> None:
    from app.utils import auth_utils

    monkeypatch.setattr(auth_utils.settings, "COOKIE_SECURE", False)
    monkeypatch.setattr(auth_utils.settings, "HOST", "https://api.gaia.example.com")
    monkeypatch.setattr(auth_utils.settings, "COOKIE_SAMESITE", "lax")
    monkeypatch.setattr(auth_utils.settings, "COOKIE_DOMAIN", None)

    kwargs = auth_utils.session_cookie_kwargs()

    assert kwargs["secure"] is False


def test_samesite_none_without_secure_raises(monkeypatch) -> None:
    from app.utils import auth_utils

    monkeypatch.setattr(auth_utils.settings, "COOKIE_SECURE", False)
    monkeypatch.setattr(auth_utils.settings, "HOST", "http://localhost:8000")
    monkeypatch.setattr(auth_utils.settings, "COOKIE_SAMESITE", "none")
    monkeypatch.setattr(auth_utils.settings, "COOKIE_DOMAIN", None)

    with pytest.raises(ValueError, match="SameSite=None"):
        auth_utils.session_cookie_kwargs()


def test_cookie_domain_included_only_when_set(monkeypatch) -> None:
    from app.utils import auth_utils

    monkeypatch.setattr(auth_utils.settings, "COOKIE_SECURE", True)
    monkeypatch.setattr(auth_utils.settings, "HOST", "https://api.gaia.example.com")
    monkeypatch.setattr(auth_utils.settings, "COOKIE_SAMESITE", "lax")
    monkeypatch.setattr(auth_utils.settings, "COOKIE_DOMAIN", None)

    assert "domain" not in auth_utils.session_cookie_kwargs()

    monkeypatch.setattr(auth_utils.settings, "COOKIE_DOMAIN", ".gaia.example.com")

    assert auth_utils.session_cookie_kwargs()["domain"] == ".gaia.example.com"

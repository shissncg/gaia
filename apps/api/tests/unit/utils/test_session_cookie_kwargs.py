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


def test_returns_full_cookie_policy_shape(monkeypatch) -> None:
    """Every kwarg Response.set_cookie(**kwargs) needs must be present under
    its exact key, with the exact value — a renamed or flipped key would pass
    silently through the dict spread and break the cookie at the browser.
    """
    from app.utils import auth_utils

    monkeypatch.setattr(auth_utils.settings, "COOKIE_SECURE", True)
    monkeypatch.setattr(auth_utils.settings, "HOST", "https://api.gaia.example.com")
    monkeypatch.setattr(auth_utils.settings, "COOKIE_SAMESITE", "lax")
    monkeypatch.setattr(auth_utils.settings, "COOKIE_DOMAIN", None)

    kwargs = auth_utils.session_cookie_kwargs()

    assert kwargs == {"httponly": True, "secure": True, "samesite": "lax"}


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

    with pytest.raises(ValueError) as exc_info:
        auth_utils.session_cookie_kwargs()

    assert str(exc_info.value) == (
        "COOKIE_SAMESITE=none requires Secure cookies (COOKIE_SECURE=true "
        "or an https HOST) — browsers reject SameSite=None without Secure."
    )


def test_cookie_domain_included_only_when_set(monkeypatch) -> None:
    from app.utils import auth_utils

    monkeypatch.setattr(auth_utils.settings, "COOKIE_SECURE", True)
    monkeypatch.setattr(auth_utils.settings, "HOST", "https://api.gaia.example.com")
    monkeypatch.setattr(auth_utils.settings, "COOKIE_SAMESITE", "lax")
    monkeypatch.setattr(auth_utils.settings, "COOKIE_DOMAIN", None)

    assert "domain" not in auth_utils.session_cookie_kwargs()

    monkeypatch.setattr(auth_utils.settings, "COOKIE_DOMAIN", ".gaia.example.com")

    assert auth_utils.session_cookie_kwargs()["domain"] == ".gaia.example.com"

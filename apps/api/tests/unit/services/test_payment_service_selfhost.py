"""Self-hosted deployments have no Dodo account; every user is PRO by fiat.
See .agents/plans/selfhost/04-billing.md."""

import pytest

from app.models.payment_models import PlanType, SubscriptionStatus


@pytest.mark.asyncio
async def test_cached_plan_type_is_pro_without_touching_redis(monkeypatch):
    from app.services.payments import payment_service as ps_module

    monkeypatch.setattr(ps_module.settings, "DEPLOYMENT_MODE", "self_hosted")

    async def _explode(*a, **k):  # Redis must not be consulted at all
        raise AssertionError("redis_cache must not be touched in self_hosted mode")

    monkeypatch.setattr(ps_module.redis_cache, "get", _explode)
    monkeypatch.setattr(ps_module.redis_cache, "set", _explode)

    plan = await ps_module.payment_service.get_cached_plan_type("any-user")
    assert plan is PlanType.PRO


@pytest.mark.asyncio
async def test_subscription_status_reports_pro_without_mongo(monkeypatch):
    from app.services.payments import payment_service as ps_module
    from app.services.payments.payment_service import DodoPaymentService

    monkeypatch.setattr(ps_module.settings, "DEPLOYMENT_MODE", "self_hosted")

    async def _explode(*a, **k):
        raise AssertionError("subscription_repository must not be queried")

    monkeypatch.setattr(ps_module.subscription_repository, "get_active_for_user", _explode)

    # Call through the class: the conftest patches the singleton's bound method.
    status = await DodoPaymentService.get_user_subscription_status(
        ps_module.payment_service, "any-user"
    )
    assert status.plan_type is PlanType.PRO
    assert status.is_subscribed is True  # existing UI logic keys on this
    assert status.has_subscription is False  # there is no subscription row
    assert status.can_upgrade is False
    assert status.can_downgrade is False  # model default is True; must be set
    assert status.status == SubscriptionStatus.ACTIVE
    assert status.current_plan is None
    assert status.subscription is None
    assert status.days_remaining is None

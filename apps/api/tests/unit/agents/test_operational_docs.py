"""GAIA_CORE — the always-on core injected into every executor turn.

Self-hosted deployments register no billing tools (see
tests/unit/tools/test_registry.py::TestBillingCategory), so the core must not
instruct the executor to route pricing/upgrade questions to them.
"""

from unittest.mock import patch

from app.agents.workspace import operational_docs as docs_module
from app.agents.workspace.operational_docs import GAIA_CORE, get_core


class TestSelfHostedCore:
    def test_cloud_core_still_routes_billing_questions(self) -> None:
        """Sanity check: the cloud core has the routing this test suite removes."""
        assert "get_subscription_details" in GAIA_CORE
        assert "create_upgrade_link" in GAIA_CORE
        assert "`billing`" in GAIA_CORE

    def test_self_hosted_core_has_no_billing_routing(self) -> None:
        with patch.object(docs_module.settings, "DEPLOYMENT_MODE", "self_hosted"):
            core = get_core()

        assert "get_subscription_details" not in core
        assert "create_upgrade_link" not in core
        assert "billing" not in core.lower()

    def test_cloud_mode_still_gets_the_full_core(self) -> None:
        with patch.object(docs_module.settings, "DEPLOYMENT_MODE", "cloud"):
            core = get_core()

        assert core == GAIA_CORE

    def test_stripping_only_removes_billing_leaving_everything_else_intact(self) -> None:
        """The strip must be surgical: every other topic/row stays byte-identical."""
        with patch.object(docs_module.settings, "DEPLOYMENT_MODE", "self_hosted"):
            core = get_core()

        assert "`workflows`" in core
        assert "`memory`" in core
        assert "create_workflow" in core
        # The topic list sentence loses only ", billing" — the rest is intact.
        assert (
            "sessions/artifacts, notifications, workflows, memory), read that topic's doc" in core
        )

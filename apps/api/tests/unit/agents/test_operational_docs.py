"""GAIA_CORE — the always-on core injected into every executor turn.

Self-hosted deployments register no billing tools (see
tests/unit/tools/test_registry.py::TestBillingCategory), so the core must not
instruct the executor to route pricing/upgrade questions to them.
"""

from unittest.mock import patch

import pytest

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


class TestStripBillingReferences:
    """Direct tests of ``_strip_billing_references``.

    ``get_core()`` only ever reads the module-level ``_GAIA_CORE_SELF_HOSTED``
    constant, which is computed exactly once at import time (see its comment:
    precomputed so the bytes stay stable for the provider's prompt cache).
    Calling ``get_core()`` therefore never re-runs the stripping logic, so the
    only way to exercise its branches — including the safety net that aborts
    the whole strip when a fragment has drifted out of ``GAIA_CORE`` — is to
    call it directly, as these tests do.
    """

    def test_strips_all_three_fragments_leaving_everything_else_byte_identical(
        self,
    ) -> None:
        core = (
            "before\n"
            + docs_module._BILLING_ROUTING_ROWS
            + "middle-one\n"
            + docs_module._BILLING_TOPIC_LIST_MENTION
            + "middle-two\n"
            + docs_module._BILLING_MANUAL_BULLET
            + "after"
        )
        expected = (
            "before\n"
            "middle-one\n"
            + docs_module._BILLING_TOPIC_LIST_MENTION_STRIPPED
            + "middle-two\n"
            + "after"
        )

        assert docs_module._strip_billing_references(core) == expected

    @pytest.mark.parametrize(
        "omit_fragment,expected_label",
        [
            ("routing_rows", "routing table rows"),
            ("topic_list_mention", "topic list mention"),
            ("manual_bullet", "manual bullet"),
        ],
    )
    def test_missing_single_fragment_aborts_stripping_entirely_and_names_it(
        self, omit_fragment: str, expected_label: str
    ) -> None:
        """A future GAIA_CORE edit that drops one known fragment must not
        leave the self-hosted core partially stripped — the whole input comes
        back untouched and the drift is logged by name."""
        fragments = {
            "routing_rows": docs_module._BILLING_ROUTING_ROWS,
            "topic_list_mention": docs_module._BILLING_TOPIC_LIST_MENTION,
            "manual_bullet": docs_module._BILLING_MANUAL_BULLET,
        }
        present = [value for key, value in fragments.items() if key != omit_fragment]
        core = "before\n" + "\nmiddle\n".join(present) + "\nafter"
        expected_message = (
            f"{docs_module.LogTag.AGENT} operational_docs: billing references not found in GAIA_CORE "
            "— the self-hosted core may still route billing questions. "
            "Update _strip_billing_references to match GAIA_CORE."
        )

        with patch.object(docs_module.log, "warning") as mock_warning:
            result = docs_module._strip_billing_references(core)

        assert result == core
        mock_warning.assert_called_once_with(expected_message, missing_fragments=[expected_label])

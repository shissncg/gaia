"""``_strip_billing_section`` — removes the Rate Limits & Subscription block.

Self-hosted deployments register no billing tools (see
tests/unit/tools/test_registry.py::TestBillingCategory), so the comms agent
must not be told to delegate pricing/upgrade questions to them. Wired into
the per-channel static prompt in ``agent_template.py`` (verified end-to-end
via the ``driving-gaia`` manual chat check, not here — that constant is
precomputed once at import for prompt-cache stability, same as the existing
``_strip_openui_section`` wiring it sits beside)."""

from app.agents.prompts.comms_prompts import COMMS_AGENT_PROMPT, _strip_billing_section


class TestStripBillingSection:
    def test_removes_the_billing_section_from_the_real_prompt(self) -> None:
        stripped = _strip_billing_section(COMMS_AGENT_PROMPT)

        assert "—Rate Limits & Subscription—" not in stripped
        assert "get_subscription_details" not in stripped
        assert "create_upgrade_link" not in stripped

    def test_leaves_the_surrounding_sections_intact(self) -> None:
        stripped = _strip_billing_section(COMMS_AGENT_PROMPT)

        assert "—Memory & Getting To Know The User—" in stripped
        assert "Never reproduce the literal tags" in stripped

    def test_missing_start_marker_warns_and_returns_unchanged(self) -> None:
        prompt = "no billing section here at all"

        assert _strip_billing_section(prompt) == prompt

    def test_missing_end_marker_warns_and_returns_unchanged(self) -> None:
        prompt = "—Rate Limits & Subscription—\nsome text with no next section header"

        assert _strip_billing_section(prompt) == prompt

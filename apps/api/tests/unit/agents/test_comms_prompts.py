"""``_strip_billing_section`` — removes the Rate Limits & Subscription block.

Self-hosted deployments register no billing tools (see
tests/unit/tools/test_registry.py::TestBillingCategory), so the comms agent
must not be told to delegate pricing/upgrade questions to them. Wired into
the per-channel static prompt in ``agent_template.py`` (verified end-to-end
via the ``driving-gaia`` manual chat check, not here — that constant is
precomputed once at import for prompt-cache stability, same as the existing
``_strip_openui_section`` wiring it sits beside)."""

from app.agents.prompts.comms_prompts import COMMS_AGENT_PROMPT, _strip_billing_section
from app.constants.log_tags import LogTag
from tests.helpers import captured_wide_event


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

    async def test_missing_start_marker_warns_and_returns_unchanged(self) -> None:
        prompt = "no billing section here at all"

        async with captured_wide_event() as event:
            result = _strip_billing_section(prompt)

        assert result == prompt
        assert event["warnings"] == [
            {
                "msg": (
                    f"{LogTag.AGENT} comms_prompts: billing section start marker not found in "
                    "COMMS_AGENT_PROMPT — self-hosted variant will still route pricing "
                    "questions to the (nonexistent) billing tools. Update "
                    "_BILLING_SECTION_START_MARKER to match the prompt."
                )
            }
        ]

    async def test_missing_end_marker_warns_and_returns_unchanged(self) -> None:
        prompt = "—Rate Limits & Subscription—\nsome text with no next section header"

        async with captured_wide_event() as event:
            result = _strip_billing_section(prompt)

        assert result == prompt
        assert event["warnings"] == [
            {
                "msg": (
                    f"{LogTag.AGENT} comms_prompts: billing section end marker not found after "
                    "the start marker — self-hosted strip aborted. Update "
                    "_BILLING_SECTION_END_MARKER to match the prompt."
                )
            }
        ]

    def test_uses_the_first_occurrence_of_the_start_marker(self) -> None:
        """A duplicated start marker must not shift the strip to the later one:
        find semantics, not rfind. Also pins the exact rstrip + separator join
        (a lstrip, or an altered separator, produces a different result here)."""
        prompt = (
            "before one\n"
            "—Rate Limits & Subscription—\n"
            "unexpected duplicate marker text\n"
            "—Rate Limits & Subscription—\n"
            "billing details\n"
            "—Memory & Getting To Know The User—\n"
            "after"
        )

        stripped = _strip_billing_section(prompt)

        assert stripped == "before one\n\n—Memory & Getting To Know The User—\nafter"

    def test_searches_for_the_end_marker_only_after_the_start_marker(self) -> None:
        """An end-marker lookalike appearing before the start marker must be
        ignored: the end-marker search has to begin at start, not at index 0."""
        prompt = (
            "decoy —Memory & Getting To Know The User— body\n"
            "—Rate Limits & Subscription—\n"
            "billing stuff\n"
            "—Memory & Getting To Know The User—\n"
            "after"
        )

        stripped = _strip_billing_section(prompt)

        assert stripped == (
            "decoy —Memory & Getting To Know The User— body\n\n"
            "—Memory & Getting To Know The User—\n"
            "after"
        )

    def test_uses_the_first_occurrence_of_the_end_marker_after_start(self) -> None:
        """Two end-marker occurrences after start must resolve to the nearer
        one: find semantics, not rfind."""
        prompt = (
            "before\n"
            "—Rate Limits & Subscription—\n"
            "billing section content\n"
            "—Memory & Getting To Know The User—\n"
            "middle text between two memory headers\n"
            "—Memory & Getting To Know The User—\n"
            "after"
        )

        stripped = _strip_billing_section(prompt)

        assert stripped == (
            "before\n\n"
            "—Memory & Getting To Know The User—\n"
            "middle text between two memory headers\n"
            "—Memory & Getting To Know The User—\n"
            "after"
        )

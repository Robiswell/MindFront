from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from mindfront.gui import (
    POLICY_PATH,
    GuiInputError,
    _bootstrap_payload,
    _build_assistance_request,
    _build_message_brief,
    run_server,
)
from mindfront.validation import validate_brief_file
from mindfront.workplace_assistance import (
    load_workplace_assistance_policy,
    validate_workplace_assistance_request,
)


class MindfrontGuiRequestTests(unittest.TestCase):
    def setUp(self) -> None:
        self.policy = load_workplace_assistance_policy(POLICY_PATH)

    def assert_valid_assistance(self, payload: dict[str, object]) -> dict[str, object]:
        request = _build_assistance_request(payload)
        errors = validate_workplace_assistance_request(request, policy=self.policy)
        self.assertEqual([], errors)
        return request

    def test_builds_valid_preflight_request(self) -> None:
        request = self.assert_valid_assistance(
            {
                "mode": "preflight",
                "summary": "Prepare an ownership update.",
                "intendedAsk": "Can we confirm the owner and approval path?",
                "draftText": "I propose that I coordinate delivery while the director approves.",
                "knownFacts": "The pilot has a documented workstream structure.",
            }
        )
        self.assertEqual("preflight", request["mode"])
        self.assertFalse(request["authorization"]["automaticSendingAllowed"])

    def test_builds_valid_interpret_request(self) -> None:
        request = self.assert_valid_assistance(
            {
                "mode": "interpret",
                "summary": "Interpret an ambiguous ownership question.",
                "incomingText": "Who owns this and when do you need approval?",
            }
        )
        self.assertEqual(["interpret_ambiguity"], request["requestedActions"])

    def test_builds_valid_debrief_request(self) -> None:
        request = self.assert_valid_assistance(
            {
                "mode": "debrief",
                "summary": "Debrief a pilot handoff.",
                "knownFacts": "The group discussed a security review before release.",
                "decisions": "Security review should happen before release.",
                "unresolvedItems": "Confirm the final participant list.",
            }
        )
        self.assertEqual("proposed", request["decisions"][0]["status"])

    def test_builds_valid_career_review_request(self) -> None:
        request = self.assert_valid_assistance(
            {
                "mode": "career_review",
                "summary": "Review evidence for a larger AI enablement scope.",
                "careerEvidence": "Delivered a reusable intake workflow adopted by two teams.",
                "careerCategory": "adoption_or_reuse",
            }
        )
        self.assertEqual("user_asserted", request["careerEvidence"][0]["evidenceState"])

    def test_simple_form_builds_valid_requests_for_every_mode(self) -> None:
        examples = {
            "preflight": "I want to ask who owns the final decision.",
            "interpret": "Can you take another pass at this?",
            "debrief": "We discussed the security review and did not name an owner.",
            "career_review": "I built a workflow that two teams reused.",
        }
        for mode, primary_text in examples.items():
            with self.subTest(mode=mode):
                request = self.assert_valid_assistance(
                    {
                        "mode": mode,
                        "primaryText": primary_text,
                        "desiredOutcome": "Choose the safest next action.",
                    }
                )
                self.assertEqual(mode, request["mode"])

    def test_confirmed_authority_requires_inspectable_source(self) -> None:
        with self.assertRaises(GuiInputError) as context:
            _build_assistance_request(
                {
                    "mode": "preflight",
                    "summary": "Prepare an ownership update.",
                    "intendedAsk": "Can we confirm the owner?",
                    "authorityState": "explicitly_delegated",
                }
            )
        self.assertEqual("authoritySource", context.exception.field)

    def test_authority_source_creates_qualified_fact(self) -> None:
        request = self.assert_valid_assistance(
            {
                "mode": "preflight",
                "summary": "Prepare an ownership update.",
                "intendedAsk": "Can we confirm the owner?",
                "authorityState": "explicitly_delegated",
                "authorityEvidence": "The director delegated pilot coordination.",
                "authoritySource": "Decision record dated July 25",
            }
        )
        self.assertEqual(
            ["fact-authority-evidence-01"],
            request["authority"]["evidenceFactIds"],
        )


class MindfrontGuiArtifactTests(unittest.TestCase):
    def test_simple_audit_form_builds_strictly_valid_message_brief(self) -> None:
        brief = _build_message_brief(
            {"primaryText": "The pilot needs a confirmed owner and approval path."}
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "message-brief.json"
            path.write_text(json.dumps(brief), encoding="utf-8")
            result = validate_brief_file(path, strict=True)
        self.assertTrue(result.ok, [error.to_dict() for error in result.errors])

    def test_builds_strictly_valid_message_brief(self) -> None:
        brief = _build_message_brief(
            {
                "projectName": "AI pilot update",
                "messageGoal": "Help leaders confirm the next decision.",
                "targetAudience": "Technology leadership",
                "sourceText": "The pilot needs a confirmed owner and approval path.",
                "artifactChannel": "document",
                "communicationIntent": "request_decision",
                "documentArchetype": "internal_operational_brief",
                "dataClassification": "internal",
                "proofAvailable": "A decision record exists.",
            }
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "message-brief.json"
            path.write_text(json.dumps(brief), encoding="utf-8")
            result = validate_brief_file(path, strict=True)
        self.assertTrue(result.ok, [error.to_dict() for error in result.errors])
        self.assertFalse(brief["llmProcessingAllowed"])

    def test_bootstrap_does_not_expose_profile_content(self) -> None:
        payload = _bootstrap_payload("token")
        self.assertIn("profileAvailable", payload)
        self.assertNotIn("profile", payload)
        self.assertFalse(payload["privacy"]["browserStorageUsed"])
        self.assertFalse(payload["privacy"]["automaticSendingAllowed"])

    def test_server_rejects_non_loopback_bind(self) -> None:
        with self.assertRaises(ValueError):
            run_server("0.0.0.0", 8765)


if __name__ == "__main__":
    unittest.main()

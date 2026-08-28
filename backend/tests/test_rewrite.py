from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT.parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from mindfront.rewrite import (
    RewriteBlockedError,
    _profile_distinctness_check,
    evaluate_copy_gates,
    rewrite_message_brief,
)


class RewriteTests(unittest.TestCase):
    def test_rewrite_sample_brief_generates_gated_variants(self) -> None:
        bundle = rewrite_message_brief(
            PROJECT / "examples" / "briefs" / "sample-message-brief.json",
            config_root=PROJECT / "config",
        )

        self.assertEqual("copy_variant_bundle", bundle["artifactType"])
        self.assertEqual("passed", bundle["claimGateSummary"]["status"])
        self.assertEqual(4, len(bundle["variants"]))
        self.assertTrue(all(variant["claimGateStatus"] == "passed" for variant in bundle["variants"]))
        self.assertTrue(all(variant["requiresProofBeforePublishing"] for variant in bundle["variants"]))
        self.assertNotIn("validated_for_exact_context", json.dumps(bundle))

    def test_qualified_profile_creates_distinct_sanitized_multi_dimension_variant(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            brief_path = Path(temp_dir) / "profiled-executive-brief.json"
            brief_path.write_text(json.dumps(_profiled_executive_brief()), encoding="utf-8")
            bundle = rewrite_message_brief(
                brief_path,
                config_root=PROJECT / "config",
                interaction_profile=_qualified_interaction_profile(),
                interaction_profile_context="executive_update",
            )

        profile_variants = [
            variant
            for variant in bundle["variants"]
            if variant["strategyId"] == "profile_guided"
        ]
        self.assertEqual(1, len(profile_variants))
        variant = profile_variants[0]
        self.assertNotEqual(_profiled_executive_brief()["sourceText"], variant["copy"])
        self.assertTrue(variant["distinctnessCheck"]["passed"])
        self.assertTrue(variant["distinctnessCheck"]["semanticDistinctFromSource"])
        self.assertTrue(variant["distinctnessCheck"]["distinctFromOtherVariants"])
        self.assertEqual(
            [
                "action_clarity",
                "information_density",
                "opening",
                "private_terminology",
                "question_patterns",
                "response_hypotheses",
                "structure",
                "tone_register",
            ],
            variant["interactionTransformation"]["appliedDimensions"],
        )
        self.assertIn("Quick update:", variant["copy"])
        self.assertIn("Supporting facts:", variant["copy"])
        self.assertIn("Next step:", variant["copy"])
        self.assertIn("Azure Government Foundry", variant["copy"])
        self.assertEqual("passed", variant["claimGateStatus"])
        self.assertEqual("passed", variant["contentGateStatus"])
        self.assertEqual(1.0, variant["sourceCoverage"])
        self.assertTrue(bundle["interactionAssistance"]["applied"])
        self.assertFalse(bundle["interactionAssistance"]["transformationSummary"]["privateContentIncluded"])
        self.assertFalse(bundle["interactionAssistance"]["transformationSummary"]["claimEvidenceChanged"])
        self.assertFalse(bundle["interactionAssistance"]["transformationSummary"]["privateTerminologyIntroduced"])

        serialized = json.dumps(bundle)
        for canary in (
            "PRIVATE RECIPIENT CANARY",
            "PRIVATE LEXICON CANARY",
            "PRIVATE EXAMPLE CANARY",
            "PRIVATE RESPONSE CANARY",
        ):
            self.assertNotIn(canary, serialized)

    def test_no_op_profile_does_not_emit_or_count_profile_variant(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            brief_path = Path(temp_dir) / "profiled-executive-brief.json"
            brief_path.write_text(json.dumps(_profiled_executive_brief()), encoding="utf-8")
            baseline = rewrite_message_brief(brief_path, config_root=PROJECT / "config")
            bundle = rewrite_message_brief(
                brief_path,
                config_root=PROJECT / "config",
                interaction_profile=_no_op_interaction_profile(),
                interaction_profile_context="executive_update",
            )

        self.assertFalse(bundle["interactionAssistance"]["applied"])
        self.assertTrue(bundle["interactionAssistance"]["contextMatched"])
        self.assertEqual(
            "no_qualified_actionable_guidance",
            bundle["interactionAssistance"]["reason"],
        )
        self.assertFalse(any(
            variant["strategyId"] == "profile_guided"
            for variant in bundle["variants"]
        ))
        self.assertEqual(
            [variant["strategyId"] for variant in baseline["variants"]],
            [variant["strategyId"] for variant in bundle["variants"]],
        )
        self.assertNotIn("PRIVATE NOOP EXAMPLE CANARY", json.dumps(bundle))

    def test_profile_distinctness_rejects_semantic_source_and_variant_duplicates(self) -> None:
        normalized_source_duplicate = _profile_distinctness_check(
            {
                "strategyId": "profile_guided",
                "copy": "Status: Pilot ready.",
                "transformationSummary": {},
            },
            source_text="status pilot ready",
            other_results=[],
        )
        other_variant_duplicate = _profile_distinctness_check(
            {
                "strategyId": "profile_guided",
                "copy": "Bottom line: start the governed pilot.",
                "transformationSummary": {},
            },
            source_text="Start the governed pilot after review.",
            other_results=[
                {
                    "strategyId": "proof_first",
                    "copy": "BOTTOM LINE - start the governed pilot",
                }
            ],
        )

        self.assertFalse(normalized_source_duplicate["passed"])
        self.assertFalse(normalized_source_duplicate["semanticDistinctFromSource"])
        self.assertFalse(other_variant_duplicate["passed"])
        self.assertEqual(["proof_first"], other_variant_duplicate["duplicateStrategyIds"])

    def test_rewrite_blocks_blocked_source_analysis(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            brief_path = Path(temp_dir) / "guarantee-brief.json"
            brief = valid_message_brief()
            brief["sourceText"] = "Mindfront is guaranteed to double every team's productivity in one week."
            brief["proofAvailable"] = []
            brief_path.write_text(json.dumps(brief, indent=2), encoding="utf-8")

            with self.assertRaises(RewriteBlockedError) as raised:
                rewrite_message_brief(brief_path, config_root=PROJECT / "config")

        self.assertEqual("analysis_report_blocked", raised.exception.reasons[0]["code"])

    def test_rewrite_rejects_unknown_strategy(self) -> None:
        with self.assertRaises(RewriteBlockedError) as raised:
            rewrite_message_brief(
                PROJECT / "examples" / "briefs" / "sample-message-brief.json",
                config_root=PROJECT / "config",
                strategies=["market_magic"],
            )

        self.assertEqual("unknown_strategy", raised.exception.reasons[0]["code"])

    def test_internal_executive_digest_preserves_subject_terms_and_numbers(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            brief_path = Path(temp_dir) / "executive-digest.json"
            brief = valid_message_brief()
            brief.update(
                {
                    "briefId": "brief-chatgpt-enterprise-executive-digest",
                    "sourceText": (
                        "The ChatGPT Enterprise export labeled June 25-July 24 contains 243 users, "
                        "including 227 with a nonzero estimated-cost field. The top 39 users account "
                        "for 80% of that estimated-cost field. These values are activity indicators, "
                        "not evidence of productivity, quality, business value, or actual spend."
                    ),
                    "targetAudience": "Senior IT operator",
                    "channel": "internal_executive_brief",
                    "desiredAction": "read_update",
                    "dataClassification": "internal",
                    "documentArchetype": "internal_executive_digest",
                    "communicationIntent": "inform",
                    "decisionRequired": False,
                    "readerTimeBudgetSeconds": 30,
                    "requiredTerms": ["ChatGPT Enterprise", "estimated-cost field"],
                    "prohibitedTerms": ["Mindfront", "approval required"],
                    "sourceContainsPersonalData": True,
                    "sourceDataSanitized": True,
                    "sourceFactManifestHash": f"sha256:{'0' * 64}",
                    "verifiedFactStatements": [
                        (
                            "The ChatGPT Enterprise export labeled June 25-July 24 contains 243 users, "
                            "including 227 with a nonzero estimated-cost field."
                        ),
                        "The top 39 users account for 80% of that estimated-cost field.",
                    ],
                    "proofAvailable": [
                        {
                            "type": "real_user_data",
                            "label": "De-identified aggregate manifest",
                            "summary": "Aggregate values recomputed from the source export.",
                            "sourceId": "source-001",
                        }
                    ],
                }
            )
            brief_path.write_text(json.dumps(brief, indent=2), encoding="utf-8")
            bundle = rewrite_message_brief(brief_path, config_root=PROJECT / "config")

        self.assertEqual("passed", bundle["contentGateSummary"]["status"])
        self.assertEqual("inform", bundle["communicationIntent"])
        for variant in bundle["variants"]:
            self.assertEqual("passed", variant["contentGateStatus"])
            self.assertEqual(1.0, variant["numericFidelity"])
            self.assertEqual(1.0, variant["sourceCoverage"])
            self.assertIn("ChatGPT Enterprise", variant["copy"])
            self.assertIn("estimated-cost field", variant["copy"])
            self.assertNotIn("Mindfront", variant["copy"])

    def test_required_ai_term_does_not_match_inside_paid(self) -> None:
        evaluation = evaluate_copy_gates(
            "The team uses paid tools.",
            source_text="The team uses paid tools.",
            required_terms=["AI"],
        )

        self.assertEqual("blocked_source_fidelity", evaluation["contentGateStatus"])
        self.assertEqual(["AI"], evaluation["missingRequiredTerms"])
        self.assertEqual(0.0, evaluation["requiredTermCoverage"])

    def test_prohibited_ai_term_does_not_match_inside_paid(self) -> None:
        evaluation = evaluate_copy_gates(
            "The team uses paid tools.",
            source_text="The team uses paid tools.",
            prohibited_terms=["AI"],
        )

        self.assertEqual("passed", evaluation["contentGateStatus"])
        self.assertEqual([], evaluation["presentProhibitedTerms"])

    def test_multiword_required_term_matches_case_and_punctuation_variants(self) -> None:
        evaluation = evaluate_copy_gates(
            "AI-governance is part of the operating model.",
            source_text="AI-governance is part of the operating model.",
            required_terms=["ai GOVERNANCE"],
        )

        self.assertEqual("passed", evaluation["contentGateStatus"])
        self.assertEqual([], evaluation["missingRequiredTerms"])
        self.assertEqual(1.0, evaluation["requiredTermCoverage"])

    def test_multiword_prohibited_term_matches_case_and_punctuation_variants(self) -> None:
        evaluation = evaluate_copy_gates(
            "The brief says APPROVAL, required.",
            source_text="The brief says APPROVAL, required.",
            prohibited_terms=["approval required"],
        )

        self.assertEqual("blocked_source_fidelity", evaluation["contentGateStatus"])
        self.assertEqual(["approval required"], evaluation["presentProhibitedTerms"])

    def test_cli_rewrite_writes_json_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "variants.json"
            env = dict(os.environ)
            env["PYTHONPATH"] = str(SRC)
            completed = subprocess.run(
                [
                    sys.executable,
                    "-B",
                    "-m",
                    "mindfront.cli",
                    "rewrite",
                    "--brief",
                    str(PROJECT / "examples" / "briefs" / "sample-message-brief.json"),
                    "--config-root",
                    str(PROJECT / "config"),
                    "--output",
                    str(output_path),
                ],
                check=False,
                env=env,
                capture_output=True,
                text=True,
            )

            self.assertEqual(0, completed.returncode, completed.stderr)
            payload = json.loads(output_path.read_text(encoding="utf-8"))

        self.assertEqual("copy_variant_bundle", payload["artifactType"])
        self.assertTrue(payload["outputHash"].startswith("sha256:"))


def valid_message_brief() -> dict:
    return {
        "briefId": "brief-rewrite-blocked",
        "artifactType": "message_brief",
        "schemaVersion": 1,
        "createdAt": "2026-05-09",
        "sourceText": "Mindfront helps teams make early product copy clearer before research is available.",
        "targetAudience": "Product and marketing leads",
        "channel": "landing_page",
        "desiredAction": "request_demo",
        "dataClassification": "public",
        "containsPersonalData": False,
        "containsCustomerConfidentialData": False,
        "llmProcessingAllowed": False,
        "retentionPolicy": "project_local_until_deleted",
        "domainContext": "general_b2b",
        "sensitiveDomainFlags": [],
        "expertReviewRequired": False,
        "expertReviewStatus": "not_required",
        "blockedClaimTypes": [],
        "publishReadiness": "not_assessed",
    }


def _profiled_executive_brief() -> dict[str, object]:
    brief = valid_message_brief()
    brief.update(
        {
            "briefId": "brief-profile-assistance-rewrite",
            "sourceText": (
                "The current issue is fragmented AI tooling across departments. "
                "The recommendation is to start with one governed pilot. "
                "Implementation will use Azure Government Foundry for the secure path. "
                "The IT lead owns the pilot and will consult Infrastructure on security. "
                "The next milestone is a 30-day review."
            ),
            "targetAudience": "Executive IT leadership",
            "channel": "internal_executive_brief",
            "desiredAction": "read_update",
            "dataClassification": "internal",
            "documentArchetype": "internal_operational_brief",
            "communicationIntent": "inform",
            "decisionRequired": False,
            "readerTimeBudgetSeconds": 30,
        }
    )
    return brief


def _qualified_interaction_profile() -> dict[str, object]:
    context = "executive_update"
    return {
        "profileId": "profile-sanitized-001",
        "displayName": "PRIVATE RECIPIENT CANARY",
        "profileHash": f"sha256:{'1' * 64}",
        "status": "active",
        "eligibleForAutomaticUse": True,
        "expiresAt": "2099-01-01T00:00:00+00:00",
        "evidenceBoundary": "Directional exact-context assistance only.",
        "observedCommunicationPatterns": [
            _profile_observation("opening_preference", "bottom_line_first", context),
            _profile_observation("information_density", "layered_detail", context),
            _profile_observation("structure_preference", "decision_action_sections", context),
            _profile_observation("tone_register", "informal_direct", context),
            _profile_observation("action_clarity", "owner_and_timing", context),
            _profile_observation("question_pattern", "implementation", context),
        ],
        "likelyResponsePatterns": [
            {
                "triggerClass": context,
                "responseClass": "request_risk_controls",
                "likelyResponsePattern": "PRIVATE RESPONSE CANARY",
                "confidence": "context_supported",
                "contexts": [context],
            }
        ],
        "privateLexicon": [
            {
                "term": "Azure Government Foundry",
                "category": "preferred_term",
                "supportCount": 25,
                "contexts": [context],
            },
            {
                "term": "PRIVATE LEXICON CANARY",
                "category": "preferred_term",
                "supportCount": 25,
                "contexts": [context],
            },
        ],
        "privateExamples": [
            {
                "exampleText": "PRIVATE EXAMPLE CANARY",
                "exampleKind": "preferred_wording",
                "outcomeClass": "advanced_work",
                "similarExample Organizationunt": 25,
                "contexts": [context],
            }
        ],
    }


def _no_op_interaction_profile() -> dict[str, object]:
    profile = _qualified_interaction_profile()
    profile["observedCommunicationPatterns"] = []
    profile["likelyResponsePatterns"] = []
    profile["privateLexicon"] = []
    profile["privateExamples"] = [
        {
            "exampleText": "PRIVATE NOOP EXAMPLE CANARY",
            "exampleKind": "preferred_wording",
            "outcomeClass": "advanced_work",
            "similarExample Organizationunt": 25,
            "contexts": ["executive_update"],
        }
    ]
    return profile


def _profile_observation(dimension: str, tendency_code: str, context: str) -> dict[str, object]:
    return {
        "dimension": dimension,
        "tendencyCode": tendency_code,
        "confidence": "context_supported",
        "supportCount": 25,
        "contradictionCount": 2,
        "contexts": [context],
        "suggestedAdjustment": "Use the qualified adjustment.",
    }


if __name__ == "__main__":
    unittest.main()

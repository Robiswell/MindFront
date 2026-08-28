from __future__ import annotations

import hashlib
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

from mindfront.analysis import AnalysisBlockedError, analyze_message_brief


class AnalysisTests(unittest.TestCase):
    def test_analyze_sample_brief_emits_conservative_report(self) -> None:
        report = analyze_message_brief(
            PROJECT / "examples" / "briefs" / "sample-message-brief.json",
            config_root=PROJECT / "config",
        )

        self.assertEqual("message_analysis_report", report["artifactType"])
        self.assertEqual("brief-mindfront-sample-message", report["briefId"])
        self.assertEqual(["clarity", "cognitive_load", "concreteness", "trust_proof", "ethical_risk"], [
            score["dimensionId"] for score in report["scores"]
        ])
        self.assertTrue(report["unsupportedClaimsVisible"])
        self.assertFalse(report["evidenceBasisSummary"]["marketEvidenceAvailable"])
        self.assertFalse(report["evidenceBasisSummary"]["realUserDataAvailable"])
        self.assertEqual("motivation_friction_report", report["motivationFriction"]["artifactType"])
        self.assertNotIn("validated_for_exact_context", json.dumps(report))

    def test_profile_assistance_adds_sanitized_material_recommendation_without_changing_claims(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            brief_path = Path(temp_dir) / "profiled-executive-brief.json"
            brief_path.write_text(json.dumps(_profiled_executive_brief()), encoding="utf-8")
            baseline = analyze_message_brief(brief_path, config_root=PROJECT / "config")
            profiled = analyze_message_brief(
                brief_path,
                config_root=PROJECT / "config",
                interaction_profile=_qualified_interaction_profile(),
                interaction_profile_context="executive_update",
            )

        assistance = profiled["interactionAssistance"]
        self.assertTrue(assistance["applied"])
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
            assistance["transformationSummary"]["appliedDimensions"],
        )
        self.assertTrue(assistance["transformationSummary"]["privateTerminologyMatchedSource"])
        self.assertFalse(assistance["transformationSummary"]["privateContentIncluded"])
        self.assertFalse(assistance["transformationSummary"]["claimEvidenceChanged"])
        self.assertEqual(baseline["claims"], profiled["claims"])
        self.assertEqual(len(baseline["recommendations"]) + 1, len(profiled["recommendations"]))
        tailored = profiled["recommendations"][-1]
        self.assertEqual("directional_interaction_observation", tailored["evidenceBasis"])
        self.assertIn("qualified, context-matched", tailored["summary"])
        self.assertTrue(tailored["recommendedAction"])
        self.assertFalse(tailored["privateContentIncluded"])

        serialized = json.dumps(profiled)
        for canary in (
            "PRIVATE RECIPIENT CANARY",
            "PRIVATE LEXICON CANARY",
            "PRIVATE EXAMPLE CANARY",
            "PRIVATE RESPONSE CANARY",
        ):
            self.assertNotIn(canary, serialized)

    def test_context_matched_but_no_op_profile_is_not_marked_applied(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            brief_path = Path(temp_dir) / "profiled-executive-brief.json"
            brief_path.write_text(json.dumps(_profiled_executive_brief()), encoding="utf-8")
            baseline = analyze_message_brief(brief_path, config_root=PROJECT / "config")
            profiled = analyze_message_brief(
                brief_path,
                config_root=PROJECT / "config",
                interaction_profile=_no_op_interaction_profile(),
                interaction_profile_context="executive_update",
            )

        assistance = profiled["interactionAssistance"]
        self.assertFalse(assistance["applied"])
        self.assertTrue(assistance["contextMatched"])
        self.assertEqual("no_qualified_actionable_guidance", assistance["reason"])
        self.assertEqual(baseline["recommendations"], profiled["recommendations"])
        self.assertEqual(baseline["claims"], profiled["claims"])
        self.assertNotIn("PRIVATE NOOP EXAMPLE CANARY", json.dumps(profiled))

    def test_unmatched_private_terminology_does_not_mark_assistance_applied(
        self,
    ) -> None:
        profile = _no_op_interaction_profile()
        profile["privateLexicon"] = [
            {
                "term": "PRIVATE ABSENT TERM CANARY",
                "category": "preferred_term",
                "supportCount": 25,
                "contexts": ["executive_update"],
            }
        ]
        with tempfile.TemporaryDirectory() as temp_dir:
            brief_path = Path(temp_dir) / "profiled-executive-brief.json"
            brief_path.write_text(
                json.dumps(_profiled_executive_brief()),
                encoding="utf-8",
            )
            profiled = analyze_message_brief(
                brief_path,
                config_root=PROJECT / "config",
                interaction_profile=profile,
                interaction_profile_context="executive_update",
            )

        self.assertFalse(profiled["interactionAssistance"]["applied"])
        self.assertEqual(
            "no_qualified_actionable_guidance",
            profiled["interactionAssistance"]["reason"],
        )
        self.assertNotIn("PRIVATE ABSENT TERM CANARY", json.dumps(profiled))

    def test_profile_context_mismatch_preserves_strict_non_application(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            brief_path = Path(temp_dir) / "profiled-executive-brief.json"
            brief_path.write_text(json.dumps(_profiled_executive_brief()), encoding="utf-8")
            profiled = analyze_message_brief(
                brief_path,
                config_root=PROJECT / "config",
                interaction_profile=_qualified_interaction_profile(),
                interaction_profile_context="support_request",
            )

        self.assertFalse(profiled["interactionAssistance"]["applied"])
        self.assertFalse(profiled["interactionAssistance"]["contextMatched"])
        self.assertEqual(
            "no_context_supported_profile_observation",
            profiled["interactionAssistance"]["reason"],
        )
        self.assertFalse(any(
            recommendation["evidenceBasis"] == "directional_interaction_observation"
            for recommendation in profiled["recommendations"]
        ))

    def test_analyze_includes_phase_5_motivation_friction_outputs(self) -> None:
        report = analyze_message_brief(
            PROJECT / "examples" / "briefs" / "sample-message-brief.json",
            config_root=PROJECT / "config",
        )
        motivation = report["motivationFriction"]

        self.assertIn("score", motivation["motivationScore"])
        self.assertIn("calibrationAnchor", motivation["motivationScore"])
        categories = {item["categoryId"] for item in motivation["frictionCategories"]}
        self.assertIn("no_proof", categories)
        self.assertIn("premature_cta", categories)
        self.assertTrue(motivation["objectionMap"])
        self.assertTrue(all(item["categoryId"] in categories for item in motivation["objectionMap"]))
        self.assertEqual("trust_gap_detected", motivation["trustGapReport"]["state"])
        self.assertTrue(motivation["trustGapReport"]["separatedFromClarityGap"])

    def test_analyze_specialist_documentation_emits_specialist_quality_signal(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            brief_path = Path(temp_dir) / "specialist-doc-brief.json"
            brief_path.write_text(json.dumps(_specialist_documentation_brief()), encoding="utf-8")
            report = analyze_message_brief(brief_path, config_root=PROJECT / "config")

        quality = report["documentationQuality"]
        self.assertTrue(quality["detected"])
        self.assertTrue(quality["notMarketEvidence"])
        self.assertFalse(quality["marketEvidenceCreated"])
        self.assertEqual(["lens-specialist-bandwidth"], quality["appliedLensIds"])
        self.assertFalse(quality["signals"]["fastPathVisible"])
        self.assertTrue(quality["signals"]["learningTaxRisk"])
        self.assertFalse(quality["signals"]["evidenceBoundaryVisible"])
        self.assertTrue(quality["signals"]["expertAgencyRisk"])
        self.assertTrue(quality["signals"]["coerciveGravityRisk"])
        self.assertTrue(any(
            finding["findingId"] in quality["findingIds"] and "evidence boundary" in finding["issue"].lower()
            for finding in report["findings"]
        ))

        issues = " ".join(finding["issue"].lower() for finding in report["findings"])
        self.assertIn("fast path", issues)
        self.assertIn("learning tax", issues)
        self.assertIn("evidence boundary", issues)
        self.assertIn("expert agency", issues)
        self.assertIn("dependency or addiction", issues)
        friction_categories = {
            item["categoryId"] for item in report["motivationFriction"]["frictionCategories"]
        }
        self.assertIn("coercive_momentum_risk", friction_categories)
        self.assertNotIn("validated_for_exact_context", json.dumps(report))

    def test_documentation_evidence_boundary_requires_explicit_status(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            weak_boundary_brief = _specialist_documentation_brief()
            weak_boundary_brief["sourceText"] = (
                "This specialist documentation includes proof and sources for a framework "
                "that everyone must learn before using the report."
            )
            weak_path = Path(temp_dir) / "weak-boundary.json"
            weak_path.write_text(json.dumps(weak_boundary_brief), encoding="utf-8")
            weak_report = analyze_message_brief(weak_path, config_root=PROJECT / "config")

            explicit_boundary_brief = _specialist_documentation_brief()
            explicit_boundary_brief["sourceText"] = (
                "Evidence boundary: this guidance is heuristic and not validated employee research. "
                "Sources are listed separately. Start here: use the checklist to decide the next action."
            )
            explicit_path = Path(temp_dir) / "explicit-boundary.json"
            explicit_path.write_text(json.dumps(explicit_boundary_brief), encoding="utf-8")
            explicit_report = analyze_message_brief(explicit_path, config_root=PROJECT / "config")

        self.assertFalse(weak_report["documentationQuality"]["signals"]["evidenceBoundaryVisible"])
        self.assertTrue(any(
            "does not make the evidence boundary" in finding["issue"].lower()
            for finding in weak_report["findings"]
        ))
        self.assertTrue(explicit_report["documentationQuality"]["signals"]["evidenceBoundaryVisible"])
        self.assertFalse(any(
            "does not make the evidence boundary" in finding["issue"].lower()
            for finding in explicit_report["findings"]
        ))

    def test_analyze_rejects_invalid_brief(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            bad_brief = Path(temp_dir) / "bad-brief.json"
            bad_brief.write_text(
                json.dumps(
                    {
                        "briefId": "brief-bad",
                        "artifactType": "message_brief",
                        "schemaVersion": 1,
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaises(AnalysisBlockedError) as raised:
                analyze_message_brief(bad_brief, config_root=PROJECT / "config")

        self.assertTrue(any(error.code == "missing_required_field" for error in raised.exception.errors))

    def test_executive_digest_downgrades_placeholder_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            verified = "The export contains 243 users."
            brief = _executive_digest_brief(
                source_text=verified,
                verified_statements=[verified],
                source_fact_manifest_hash=f"sha256:{'0' * 64}",
                source_id="source-001",
            )
            path = Path(temp_dir) / "executive-digest.json"
            path.write_text(json.dumps(brief), encoding="utf-8")
            report = analyze_message_brief(path, config_root=PROJECT / "config")

        claims = {claim["claimText"]: claim for claim in report["claims"]}
        self.assertEqual("support_candidate", claims[verified]["supportStatus"])
        self.assertEqual("user_provided_unverified", claims[verified]["evidenceBasis"])
        self.assertFalse(report["evidenceBasisSummary"]["sourceFactManifestResolved"])
        self.assertFalse(report["evidenceBasisSummary"]["realUserDataAvailable"])

    def test_executive_digest_downgrades_unresolved_proof_source(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            inputs = root / "inputs"
            inputs.mkdir()
            manifest_hash = _write_fact_manifest(root / "evidence" / "facts.json")
            verified = "The export contains 243 users."
            brief = _executive_digest_brief(
                source_text=verified,
                verified_statements=[verified],
                source_fact_manifest_hash=manifest_hash,
                source_id="source-999",
            )
            path = inputs / "executive-digest.json"
            path.write_text(json.dumps(brief), encoding="utf-8")
            report = analyze_message_brief(path, config_root=PROJECT / "config")

        claim = report["claims"][0]
        self.assertEqual("support_candidate", claim["supportStatus"])
        self.assertEqual("user_provided_unverified", claim["evidenceBasis"])
        self.assertEqual(["source-999"], report["evidenceBasisSummary"]["unresolvedProofSourceIds"])
        self.assertTrue(report["evidenceBasisSummary"]["sourceFactManifestResolved"])
        self.assertFalse(report["evidenceBasisSummary"]["realUserDataAvailable"])

    def test_executive_digest_supports_only_resolved_manifest_facts(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            inputs = root / "inputs"
            inputs.mkdir()
            manifest_hash = _write_fact_manifest(root / "evidence" / "facts.json")
            verified = "The export contains 243 users."
            planned = "The operating plan runs for 30 days."
            commitment = "I will validate the billing source."
            brief = _executive_digest_brief(
                source_text=f"{verified} {planned} {commitment}",
                verified_statements=[verified],
                source_fact_manifest_hash=manifest_hash,
                source_id="source-001",
            )
            path = inputs / "executive-digest.json"
            path.write_text(json.dumps(brief), encoding="utf-8")
            report = analyze_message_brief(path, config_root=PROJECT / "config")

        claims = {claim["claimText"]: claim for claim in report["claims"]}
        self.assertEqual("supported", claims[verified]["supportStatus"])
        self.assertEqual("real_user_data", claims[verified]["evidenceBasis"])
        self.assertNotEqual("supported", claims[planned]["supportStatus"])
        self.assertNotIn(commitment, claims)
        self.assertTrue(report["evidenceBasisSummary"]["sourceFactManifestResolved"])
        self.assertTrue(report["evidenceBasisSummary"]["realUserDataAvailable"])
        self.assertEqual(["source-001"], report["evidenceBasisSummary"]["resolvedProofSourceIds"])

    def test_cli_analyze_writes_json_report(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "report.json"
            env = dict(os.environ)
            env["PYTHONPATH"] = str(SRC)
            completed = subprocess.run(
                [
                    sys.executable,
                    "-B",
                    "-m",
                    "mindfront.cli",
                    "analyze",
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

        self.assertEqual("message_analysis_report", payload["artifactType"])
        self.assertTrue(payload["outputHash"].startswith("sha256:"))


def _specialist_documentation_brief() -> dict[str, object]:
    return {
        "schemaVersion": 1,
        "briefId": "brief-specialist-doc-specialist-bandwidth",
        "artifactType": "message_brief",
        "createdAt": "2026-06-01",
        "projectName": "Specialist Documentation",
        "messageGoal": "Improve internal documentation for specialized technical readers.",
        "targetAudience": "technical specialists and technical solutions consultants",
        "audienceFamiliarity": "high",
        "channel": "internal_documentation",
        "desiredAction": "use_documentation_for_task",
        "sourceText": (
            "This specialist documentation introduces a specialist enablement framework and onboarding model "
            "that everyone must learn before using the report. The basic process is simple enough for resistant "
            "readers, and the guide should be addicting to read so employees cannot live without it."
        ),
        "proofAvailable": [],
        "constraints": [
            "Do not claim employee research.",
            "Preserve expert autonomy.",
        ],
        "unknowns": [
            "No specialists have completed task validation for this document."
        ],
        "dataClassification": "internal",
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


def _executive_digest_brief(
    *,
    source_text: str,
    verified_statements: list[str],
    source_fact_manifest_hash: str,
    source_id: str,
) -> dict[str, object]:
    brief = _specialist_documentation_brief()
    brief.update(
        {
            "briefId": "brief-executive-digest-evidence-resolution",
            "sourceText": source_text,
            "documentArchetype": "internal_executive_digest",
            "communicationIntent": "inform",
            "decisionRequired": False,
            "readerTimeBudgetSeconds": 30,
            "sourceContainsPersonalData": True,
            "sourceDataSanitized": True,
            "sourceFactManifestHash": source_fact_manifest_hash,
            "verifiedFactStatements": verified_statements,
            "proofAvailable": [
                {
                    "type": "real_user_data",
                    "label": "Aggregate manifest",
                    "summary": "De-identified aggregate source.",
                    "sourceId": source_id,
                }
            ],
        }
    )
    return brief


def _write_fact_manifest(path: Path) -> str:
    manifest = {
        "artifactType": "deidentified_usage_fact_manifest",
        "schemaVersion": 1,
        "facts": {"userCount": 243},
        "privacy": {"deidentified": True},
        "validation": {"status": "passed"},
        "outputHash": "sha256:pending-until-written",
    }
    canonical = json.dumps(manifest, sort_keys=True, separators=(",", ":"))
    manifest_hash = f"sha256:{hashlib.sha256(canonical.encode('utf-8')).hexdigest()}"
    manifest["outputHash"] = manifest_hash
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    return manifest_hash


def _profiled_executive_brief() -> dict[str, object]:
    brief = _specialist_documentation_brief()
    brief.update(
        {
            "briefId": "brief-profile-assistance-analysis",
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
            "documentArchetype": "internal_operational_brief",
            "communicationIntent": "inform",
            "decisionRequired": False,
            "readerTimeBudgetSeconds": 30,
        }
    )
    return brief


def _qualified_interaction_profile() -> dict[str, object]:
    context = "executive_update"
    observations = [
        _profile_observation("opening_preference", "bottom_line_first", context),
        _profile_observation("information_density", "layered_detail", context),
        _profile_observation("structure_preference", "decision_action_sections", context),
        _profile_observation("tone_register", "informal_direct", context),
        _profile_observation("action_clarity", "owner_and_timing", context),
        _profile_observation("question_pattern", "implementation", context),
    ]
    return {
        "profileId": "profile-sanitized-001",
        "displayName": "PRIVATE RECIPIENT CANARY",
        "profileHash": f"sha256:{'1' * 64}",
        "status": "active",
        "eligibleForAutomaticUse": True,
        "expiresAt": "2099-01-01T00:00:00+00:00",
        "evidenceBoundary": "Directional exact-context assistance only.",
        "observedCommunicationPatterns": observations,
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

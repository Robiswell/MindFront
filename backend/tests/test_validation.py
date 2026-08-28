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
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from mindfront.schemas import CANONICAL_CONFIDENCE_ENUMS, REQUIRED_RUBRIC_DIMENSIONS
from mindfront.validation import validate_config_root, validate_workspace


class ValidationTests(unittest.TestCase):
    def test_valid_config_passes_strict(self) -> None:
        with temp_config_root() as config_root:
            result = validate_config_root(config_root, strict=True)

        self.assertEqual([], result.errors)
        self.assertTrue(result.ok)

    def test_missing_required_file_fails(self) -> None:
        with temp_config_root() as config_root:
            (config_root / "evidence-sources.json").unlink()
            result = validate_config_root(config_root, strict=True)

        self.assert_error_code(result, "missing_config_file")

    def test_duplicate_principle_ids_fail(self) -> None:
        with temp_config_root() as config_root:
            principles_path = config_root / "psychology-principles.json"
            data = json.loads(principles_path.read_text(encoding="utf-8"))
            duplicate = dict(data["principles"][0])
            data["principles"].append(duplicate)
            write_json(principles_path, data)

            result = validate_config_root(config_root, strict=True)

        self.assert_error_code(result, "duplicate_id")

    def test_invalid_confidence_enum_fails(self) -> None:
        with temp_config_root() as config_root:
            labels_path = config_root / "confidence-labels.json"
            data = json.loads(labels_path.read_text(encoding="utf-8"))
            data["concepts"]["recommendationState"].append({"id": "heuristic_high_confidence"})
            write_json(labels_path, data)

            result = validate_config_root(config_root, strict=True)

        self.assert_error_code(result, "invalid_confidence_enum")

    def test_dangling_rubric_principle_ref_fails(self) -> None:
        with temp_config_root() as config_root:
            rubric_path = config_root / "message-quality-rubric.json"
            data = json.loads(rubric_path.read_text(encoding="utf-8"))
            data["dimensions"][0]["principleIds"] = ["missing-principle"]
            write_json(rubric_path, data)

            result = validate_config_root(config_root, strict=True)

        self.assert_error_code(result, "unknown_principle_ref")

    def test_lens_required_fields_fail(self) -> None:
        with temp_config_root() as config_root:
            lenses_path = config_root / "audience-lenses.json"
            data = json.loads(lenses_path.read_text(encoding="utf-8"))
            del data["lenses"][0]["reviewQuestions"]
            write_json(lenses_path, data)

            result = validate_config_root(config_root, strict=True)

        self.assert_error_code(result, "missing_required_field")

    def test_principle_required_fields_fail(self) -> None:
        with temp_config_root() as config_root:
            principles_path = config_root / "psychology-principles.json"
            data = json.loads(principles_path.read_text(encoding="utf-8"))
            del data["principles"][0]["definition"]
            write_json(principles_path, data)

            result = validate_config_root(config_root, strict=True)

        self.assert_error_code(result, "missing_required_field")

    def test_evidence_source_required_fields_fail(self) -> None:
        with temp_config_root() as config_root:
            sources_path = config_root / "evidence-sources.json"
            data = json.loads(sources_path.read_text(encoding="utf-8"))
            del data["sources"][0]["supportTier"]
            write_json(sources_path, data)

            result = validate_config_root(config_root, strict=True)

        self.assert_error_code(result, "missing_required_field")

    def test_workplace_assistance_policy_boundary_fails_closed(self) -> None:
        with temp_config_root() as config_root:
            policy_path = config_root / "workplace-assistance-policy.json"
            data = json.loads(policy_path.read_text(encoding="utf-8"))
            data["requiredBoundaries"]["automaticSendingAllowed"] = True
            write_json(policy_path, data)

            result = validate_config_root(config_root, strict=True)

        self.assert_error_code(result, "unsafe_policy_boundary")

    def test_workspace_validate_checks_message_briefs(self) -> None:
        with temp_config_root() as config_root:
            brief_root = config_root / "briefs"
            brief_root.mkdir()
            brief = valid_message_brief()
            del brief["sourceText"]
            write_json(brief_root / "bad-brief.json", brief)

            result = validate_workspace(config_root, strict=True, brief_root=brief_root)

        self.assert_error_code(result, "missing_required_field")

    def test_internal_executive_digest_requires_source_contract(self) -> None:
        with temp_config_root() as config_root:
            brief_root = config_root / "briefs"
            brief_root.mkdir()
            brief = valid_message_brief()
            brief["documentArchetype"] = "internal_executive_digest"
            write_json(brief_root / "digest.json", brief)

            result = validate_workspace(config_root, strict=True, brief_root=brief_root)

        self.assert_error_code(result, "missing_required_field")

    def test_sanitized_source_declaration_and_pii_detection_fail_closed(self) -> None:
        with temp_config_root() as config_root:
            brief_root = config_root / "briefs"
            brief_root.mkdir()
            brief = valid_message_brief()
            brief.update(
                {
                    "documentArchetype": "internal_executive_digest",
                    "communicationIntent": "inform",
                    "decisionRequired": False,
                    "readerTimeBudgetSeconds": 30,
                    "sourceFactManifestHash": f"sha256:{'0' * 64}",
                    "sourceContainsPersonalData": True,
                    "sourceDataSanitized": False,
                    "sourceText": "Aggregate includes test.user@example.com and 243 users.",
                }
            )
            write_json(brief_root / "unsafe-digest.json", brief)

            result = validate_workspace(config_root, strict=True, brief_root=brief_root)

        self.assert_error_code(result, "source_data_not_sanitized")
        self.assert_error_code(result, "undeclared_personal_data")
        self.assert_error_code(result, "placeholder_evidence_manifest_hash")

    def test_strict_workspace_accepts_resolved_manifest_and_registered_source(self) -> None:
        with temp_config_root() as config_root:
            brief_root = config_root / "inputs"
            brief_root.mkdir()
            manifest_hash = write_fact_manifest(config_root / "evidence" / "facts.json")
            write_json(
                brief_root / "digest.json",
                valid_executive_digest(
                    source_fact_manifest_hash=manifest_hash,
                    source_id="source-001",
                ),
            )

            result = validate_workspace(config_root, strict=True, brief_root=brief_root)

        self.assertEqual([], result.errors)
        self.assertTrue(result.ok)

    def test_strict_workspace_rejects_unresolved_proof_source(self) -> None:
        with temp_config_root() as config_root:
            brief_root = config_root / "inputs"
            brief_root.mkdir()
            manifest_hash = write_fact_manifest(config_root / "evidence" / "facts.json")
            write_json(
                brief_root / "digest.json",
                valid_executive_digest(
                    source_fact_manifest_hash=manifest_hash,
                    source_id="source-999",
                ),
            )

            result = validate_workspace(config_root, strict=True, brief_root=brief_root)

        self.assert_error_code(result, "unknown_evidence_source_ref")

    def test_strict_workspace_rejects_missing_fact_manifest(self) -> None:
        with temp_config_root() as config_root:
            brief_root = config_root / "inputs"
            brief_root.mkdir()
            write_json(
                brief_root / "digest.json",
                valid_executive_digest(
                    source_fact_manifest_hash=(
                        f"sha256:{hashlib.sha256(b'missing-manifest').hexdigest()}"
                    ),
                    source_id="source-001",
                ),
            )

            result = validate_workspace(config_root, strict=True, brief_root=brief_root)

        self.assert_error_code(result, "unresolved_evidence_manifest")

    def test_phone_number_is_detected_as_undeclared_personal_data(self) -> None:
        with temp_config_root() as config_root:
            brief_root = config_root / "briefs"
            brief_root.mkdir()
            brief = valid_message_brief()
            brief["sourceText"] = "Call the owner at +1 (303) 555-0123 before publishing."
            write_json(brief_root / "phone.json", brief)

            result = validate_workspace(config_root, strict=True, brief_root=brief_root)

        self.assertTrue(any(
            error.code == "undeclared_personal_data" and "phone number" in error.message
            for error in result.errors
        ))

    def test_ssn_style_value_is_detected_as_undeclared_personal_data(self) -> None:
        with temp_config_root() as config_root:
            brief_root = config_root / "briefs"
            brief_root.mkdir()
            brief = valid_message_brief()
            brief["sourceText"] = "The submitted identifier was 123-45-6789."
            write_json(brief_root / "ssn.json", brief)

            result = validate_workspace(config_root, strict=True, brief_root=brief_root)

        self.assertTrue(any(
            error.code == "undeclared_personal_data" and "SSN-style" in error.message
            for error in result.errors
        ))

    def test_dates_and_aggregate_values_do_not_trigger_phone_or_ssn_detection(self) -> None:
        with temp_config_root() as config_root:
            brief_root = config_root / "briefs"
            brief_root.mkdir()
            brief = valid_message_brief()
            brief["sourceText"] = (
                "Export date 2026-07-24; 55,489,730,522 tokens; $147,875.04 estimated."
            )
            write_json(brief_root / "aggregates.json", brief)

            result = validate_workspace(config_root, strict=True, brief_root=brief_root)

        self.assertFalse(any(error.code == "undeclared_personal_data" for error in result.errors))

    def test_cli_validate_json_errors(self) -> None:
        with temp_config_root() as config_root:
            (config_root / "audience-lenses.json").unlink()
            env = dict(os.environ)
            env["PYTHONPATH"] = str(SRC)
            completed = subprocess.run(
                [
                    sys.executable,
                    "-B",
                    "-m",
                    "mindfront.cli",
                    "validate",
                    "--strict",
                    "--json-errors",
                    "--config-root",
                    str(config_root),
                ],
                check=False,
                env=env,
                capture_output=True,
                text=True,
            )

        self.assertEqual(1, completed.returncode)
        payload = json.loads(completed.stdout)
        self.assertEqual("failed", payload["status"])
        self.assertEqual(1, payload["exitCode"])
        self.assertTrue(any(error["code"] == "missing_config_file" for error in payload["errors"]))

    def test_cli_validate_writes_output_and_accepts_common_flags(self) -> None:
        with temp_config_root() as config_root, tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir) / "validation"
            env = dict(os.environ)
            env["PYTHONPATH"] = str(SRC)
            completed = subprocess.run(
                [
                    sys.executable,
                    "-B",
                    "-m",
                    "mindfront.cli",
                    "validate",
                    "--strict",
                    "--no-external-llm",
                    "--overwrite",
                    "fail",
                    "--config-root",
                    str(config_root),
                    "--output",
                    str(output_dir),
                ],
                check=False,
                env=env,
                capture_output=True,
                text=True,
            )
            payload = json.loads((output_dir / "validation-report.json").read_text(encoding="utf-8"))

        self.assertEqual(0, completed.returncode, completed.stderr)
        self.assertEqual("ok", payload["status"])
        self.assertIn("validation report written", completed.stdout)

    def test_cli_validate_dry_run_does_not_write_output(self) -> None:
        with temp_config_root() as config_root, tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir) / "validation"
            env = dict(os.environ)
            env["PYTHONPATH"] = str(SRC)
            completed = subprocess.run(
                [
                    sys.executable,
                    "-B",
                    "-m",
                    "mindfront.cli",
                    "validate",
                    "--strict",
                    "--dry-run",
                    "--config-root",
                    str(config_root),
                    "--output",
                    str(output_dir),
                ],
                check=False,
                env=env,
                capture_output=True,
                text=True,
            )
            payload = json.loads(completed.stdout)

        self.assertEqual(0, completed.returncode, completed.stderr)
        self.assertEqual("dry_run", payload["status"])
        self.assertFalse(output_dir.exists())

    def assert_error_code(self, result, code: str) -> None:
        self.assertFalse(result.ok)
        self.assertTrue(
            any(error.code == code for error in result.errors),
            f"Expected {code}, got {[error.code for error in result.errors]}",
        )


class temp_config_root:
    def __enter__(self) -> Path:
        self._temporary_directory = tempfile.TemporaryDirectory()
        self.path = Path(self._temporary_directory.name)
        write_valid_config(self.path)
        return self.path

    def __exit__(self, exc_type, exc, traceback) -> None:
        self._temporary_directory.cleanup()


def write_valid_config(config_root: Path) -> None:
    config_root.mkdir(parents=True, exist_ok=True)
    policy_source = ROOT.parent / "config" / "workplace-assistance-policy.json"
    write_json(
        config_root / "workplace-assistance-policy.json",
        json.loads(policy_source.read_text(encoding="utf-8")),
    )

    write_json(
        config_root / "confidence-labels.json",
        {
            "concepts": {
                key: [{"id": value, "definition": f"{value} definition"} for value in values]
                for key, values in CANONICAL_CONFIDENCE_ENUMS.items()
            }
        },
    )
    write_json(
        config_root / "psychology-principles.json",
        {
            "principles": [
                {
                    "principleId": "processing-fluency",
                    "label": "Processing Fluency",
                    "status": "active",
                    "evidenceBasis": "heuristic_inference",
                    "sourceIds": ["source-002"],
                    "definition": "Readers understand and continue through copy that is easy to process.",
                    "appliesToDimensions": ["clarity", "cognitive_load"],
                    "allowedUses": ["identify avoidable comprehension friction"],
                    "misuseRisks": ["Oversimplification can remove necessary nuance."],
                    "prohibitedUses": ["claiming market preference without user evidence"],
                    "requiredCaveat": "This is a heuristic, not market validation.",
                    "reviewedAt": "2026-05-09",
                }
            ]
        },
    )
    write_json(
        config_root / "audience-lenses.json",
        {
            "lenses": [
                {
                    "lensId": "lens-target-user-comprehension",
                    "label": "Target User Comprehension Lens",
                    "status": "active",
                    "roleFit": "target_user",
                    "defaultEvidenceBasis": "synthetic_reader_stress_test",
                    "notMarketEvidence": True,
                    "purpose": "Stress-test whether a reader can understand the offer after one pass.",
                    "assumptions": ["The reader has the job context named in the brief."],
                    "reviewQuestions": ["Can I summarize this in one sentence?"],
                    "frictionSignals": ["unclear category"],
                    "safetyRules": ["Do not infer market preference."],
                    "blockedUses": ["validated market evidence"],
                    "recommendedValidation": "Run a small comprehension test with target users.",
                    "principleIds": ["processing-fluency"],
                }
            ]
        },
    )
    write_json(
        config_root / "evidence-sources.json",
        {
            "sources": [
                {
                    "sourceId": "source-001",
                    "label": "Internal pilot interview notes",
                    "sourceType": "user_provided_internal",
                    "supportTier": "unverified_user_provided",
                    "allowedUses": ["claim_support_candidate", "research_context"],
                    "llmProcessingAllowed": False,
                    "retentionDays": 30,
                    "excerptPolicy": "short_excerpt_only",
                    "sensitiveDataAllowed": False,
                    "owner": "Maintainer",
                    "reviewedAt": "2026-05-09",
                    "status": "active",
                    "limitations": ["No sample details supplied"],
                },
                {
                    "sourceId": "source-002",
                    "label": "Mindfront Phase 0 hardening documents",
                    "sourceType": "project_plan",
                    "supportTier": "heuristic_reference",
                    "allowedUses": ["principle_support", "rubric_support", "config_policy"],
                    "llmProcessingAllowed": False,
                    "retentionDays": 3650,
                    "excerptPolicy": "reference_only",
                    "sensitiveDataAllowed": False,
                    "owner": "Maintainer",
                    "reviewedAt": "2026-05-09",
                    "status": "active",
                    "limitations": ["Planning source, not user validation"],
                }
            ]
        },
    )
    write_json(
        config_root / "message-quality-rubric.json",
        {
            "dimensions": [
                {
                    "dimensionId": dimension,
                    "label": dimension.replace("_", " ").title(),
                    "scoreScale": "0_to_5",
                    "higherIsBetter": True,
                    "definition": "A required Phase 0 rubric dimension.",
                    "principleIds": ["processing-fluency"],
                    "deterministicSignals": ["unclear or unsupported message behavior"],
                    "scoreAnchors": {str(score): f"Anchor {score}" for score in range(6)},
                    "goldenExampleAnchors": {
                        "1": "Weak example",
                        "3": "Usable example",
                        "5": "Strong example",
                    },
                }
                for dimension in REQUIRED_RUBRIC_DIMENSIONS
            ]
        },
    )


def valid_message_brief() -> dict:
    return {
        "briefId": "brief-test-message",
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


def valid_executive_digest(*, source_fact_manifest_hash: str, source_id: str) -> dict:
    brief = valid_message_brief()
    verified_statement = "The export contains 243 users."
    brief.update(
        {
            "briefId": "brief-valid-executive-digest",
            "sourceText": verified_statement,
            "documentArchetype": "internal_executive_digest",
            "communicationIntent": "inform",
            "decisionRequired": False,
            "readerTimeBudgetSeconds": 30,
            "sourceContainsPersonalData": True,
            "sourceDataSanitized": True,
            "sourceFactManifestHash": source_fact_manifest_hash,
            "verifiedFactStatements": [verified_statement],
            "proofAvailable": [
                {
                    "type": "real_user_data",
                    "label": "De-identified aggregate manifest",
                    "summary": "Aggregate values recomputed from the source export.",
                    "sourceId": source_id,
                }
            ],
        }
    )
    return brief


def write_fact_manifest(path: Path) -> str:
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
    write_json(path, manifest)
    return manifest_hash


def write_json(path: Path, data) -> None:
    path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")


if __name__ == "__main__":
    unittest.main()

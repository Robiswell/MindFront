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

from mindfront.compare import CompareBlockedError, compare_variant_bundle
from mindfront.rewrite import rewrite_message_brief, write_rewrite_bundle


class CompareTests(unittest.TestCase):
    def test_compare_rewrite_bundle_ranks_test_candidates(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            bundle = rewrite_message_brief(
                PROJECT / "examples" / "briefs" / "sample-message-brief.json",
                config_root=PROJECT / "config",
            )
            bundle_path = write_rewrite_bundle(bundle, Path(temp_dir) / "copy-variants.json")
            report = compare_variant_bundle(bundle_path)

        self.assertEqual("variant_comparison_report", report["artifactType"])
        self.assertEqual("hypothesis_to_test", report["recommendationState"])
        self.assertFalse(report["marketEvidenceCreated"])
        self.assertGreaterEqual(len(report["recommendedVariantIds"]), 1)
        self.assertEqual([1, 2, 3, 4], [item["rank"] for item in report["rankedVariants"]])
        self.assertNotIn("validated_for_exact_context", json.dumps(report))

    def test_compare_rejects_invalid_artifact_type(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "bad.json"
            path.write_text(
                json.dumps(
                    {
                        "artifactType": "message_analysis_report",
                        "bundleId": "variant-bundle-bad",
                        "briefId": "brief-bad",
                        "variants": [],
                        "sourceBriefHash": "sha256:bad",
                        "sourceTextHash": "sha256:bad",
                        "configSetHash": "sha256:bad",
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaises(CompareBlockedError) as raised:
                compare_variant_bundle(path)

        self.assertTrue(any(reason["code"] == "invalid_artifact_type" for reason in raised.exception.reasons))

    def test_compare_recomputes_stale_blocked_metadata_and_does_not_require_cta_for_inform(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            bundle = rewrite_message_brief(
                PROJECT / "examples" / "briefs" / "sample-message-brief.json",
                config_root=PROJECT / "config",
            )
            bundle["communicationIntent"] = "inform"
            bundle["decisionRequired"] = False
            bundle["documentArchetype"] = "internal_executive_digest"
            bundle["variants"][0]["contentGateStatus"] = "blocked_source_fidelity"
            bundle["variants"][0]["sourceCoverage"] = 0.5
            bundle["variants"][0]["numericFidelity"] = 0.0
            bundle_path = write_rewrite_bundle(bundle, temp_path / "copy-variants.json")
            report = compare_variant_bundle(bundle_path)

        reevaluated = next(
            item
            for item in report["rankedVariants"]
            if item["variantId"] == bundle["variants"][0]["variantId"]
        )
        self.assertEqual("passed", reevaluated["contentGateStatus"])
        self.assertEqual(1.0, reevaluated["sourceCoverage"])
        self.assertEqual(1.0, reevaluated["numericFidelity"])
        self.assertFalse(reevaluated["serializedGateMetadataMatched"])
        eligible = [item for item in report["rankedVariants"] if item["contentGateStatus"] == "passed"]
        self.assertTrue(eligible)
        self.assertTrue(all(item["dimensionScores"]["action_clarity"] == 5 for item in eligible))
        self.assertTrue(all(item["dimensionScores"]["intent_fit"] >= 3 for item in eligible))

    def test_compare_blocks_all_variants_when_copy_is_tampered_but_pass_metadata_is_retained(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            bundle = rewrite_message_brief(
                PROJECT / "examples" / "briefs" / "sample-message-brief.json",
                config_root=PROJECT / "config",
            )
            self.assertTrue(all(item["claimGateStatus"] == "passed" for item in bundle["variants"]))
            self.assertTrue(all(item["contentGateStatus"] == "passed" for item in bundle["variants"]))
            for variant in bundle["variants"]:
                variant["copy"] = "Guaranteed results."

            bundle_path = write_rewrite_bundle(bundle, Path(temp_dir) / "copy-variants.json")
            report = compare_variant_bundle(bundle_path)

        self.assertEqual([], report["recommendedVariantIds"])
        self.assertEqual("blocked_unsupported", report["recommendationState"])
        self.assertEqual("blocked", report["claimGateSummary"]["status"])
        self.assertEqual("blocked", report["contentGateSummary"]["status"])
        self.assertTrue(
            all(item["claimGateStatus"] == "blocked_new_unsupported_claim" for item in report["rankedVariants"])
        )
        self.assertTrue(
            all(item["contentGateStatus"] == "blocked_source_fidelity" for item in report["rankedVariants"])
        )
        self.assertTrue(all(not item["serializedGateMetadataMatched"] for item in report["rankedVariants"]))
        self.assertTrue(all(not item["recommendedForTesting"] for item in report["rankedVariants"]))

    def test_cli_compare_writes_json_report(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            bundle = rewrite_message_brief(
                PROJECT / "examples" / "briefs" / "sample-message-brief.json",
                config_root=PROJECT / "config",
            )
            bundle_path = write_rewrite_bundle(bundle, temp_path / "copy-variants.json")
            output_path = temp_path / "comparison.json"
            env = dict(os.environ)
            env["PYTHONPATH"] = str(SRC)
            completed = subprocess.run(
                [
                    sys.executable,
                    "-B",
                    "-m",
                    "mindfront.cli",
                    "compare",
                    "--variants",
                    str(bundle_path),
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

        self.assertEqual("variant_comparison_report", payload["artifactType"])
        self.assertTrue(payload["outputHash"].startswith("sha256:"))


if __name__ == "__main__":
    unittest.main()

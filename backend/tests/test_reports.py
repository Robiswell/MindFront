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
TESTS = Path(__file__).resolve().parent
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
if str(TESTS) not in sys.path:
    sys.path.insert(0, str(TESTS))

from mindfront.analysis import analyze_message_brief, write_analysis_report
from mindfront.compare import compare_variant_bundle, write_comparison_report
from mindfront.impact import build_task_validation_result, write_task_validation_result
from mindfront.protocol import build_task_observation_protocol, write_task_observation_protocol
from mindfront.reports import ReportBundleBlockedError, build_report_bundle, write_report_bundle
from mindfront.research import build_research_plan, write_research_plan
from mindfront.rewrite import rewrite_message_brief, write_rewrite_bundle
from mindfront.stress import run_reader_stress_test, write_stress_report
from test_analysis import _specialist_documentation_brief


class ReportBundleTests(unittest.TestCase):
    def test_report_bundle_preserves_boundaries_and_required_sections(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            paths = _sample_artifact_paths(Path(temp_dir))
            bundle = build_report_bundle(
                paths["analysis"],
                config_root=PROJECT / "config",
                variants_path=paths["variants"],
                comparison_path=paths["comparison"],
                stress_path=paths["stress"],
                research_plan_path=paths["research"],
            )

        self.assertEqual("audit_report_bundle", bundle["artifactType"])
        self.assertFalse(bundle["marketEvidenceCreated"])
        self.assertTrue(bundle["notMarketEvidence"])
        self.assertIn("does not create market evidence", bundle["evidenceBoundary"])
        self.assertIn("confidenceLabels", bundle["sections"])
        self.assertIn("limitations", bundle["sections"])
        self.assertIn("whatToTestNext", bundle["sections"])
        self.assertTrue(bundle["sections"]["confidenceLabels"]["labels"])
        self.assertTrue(bundle["sections"]["whatToTestNext"]["items"])
        self.assertTrue(bundle["sections"]["limitations"]["items"])
        payload = json.dumps(bundle)
        self.assertNotIn("small_user_test_supported", payload)
        self.assertNotIn("validated_for_exact_context", payload)

    def test_write_report_bundle_directory_outputs_source_and_manifest_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            paths = _sample_artifact_paths(temp_path)
            bundle = build_report_bundle(
                paths["analysis"],
                config_root=PROJECT / "config",
                variants_path=paths["variants"],
                comparison_path=paths["comparison"],
                stress_path=paths["stress"],
                research_plan_path=paths["research"],
            )
            output_paths = write_report_bundle(bundle, temp_path / "report")
            payload = json.loads((temp_path / "report" / "mindfront-audit-report.json").read_text(encoding="utf-8"))
            markdown = (temp_path / "report" / "mindfront-audit-report.md").read_text(encoding="utf-8")
            html = (temp_path / "report" / "source.html").read_text(encoding="utf-8")
            named_html = (temp_path / "report" / "mindfront-audit-report.html").read_text(encoding="utf-8")
            csv_text = (temp_path / "report" / "mindfront-audit-scorecard.csv").read_text(encoding="utf-8")
            handoff = (temp_path / "report" / "mindfront-document-workflow-handoff.md").read_text(encoding="utf-8")

        self.assertEqual(6, len(output_paths))
        manifest = payload["reportOutputManifest"]
        self.assertTrue(manifest["editableSourcePath"].endswith("source.html"))
        self.assertTrue(manifest["auditReportHtmlPath"].endswith("mindfront-audit-report.html"))
        self.assertEqual(manifest["editableSourcePath"], manifest["finalOutputPath"])
        self.assertEqual("not_generated_by_cli", manifest["pdfStatus"])
        self.assertIsNone(manifest["pdfFinalOutputPath"])
        self.assertTrue(manifest["documentationHandoffPath"].endswith("mindfront-document-workflow-handoff.md"))
        self.assertTrue(manifest["pdfPlannedOutputPath"].endswith("mindfront-audit-report.pdf"))
        self.assertIn("## What To Test Next", markdown)
        self.assertIn("<h2>What To Test Next</h2>", html)
        self.assertEqual(html, named_html)
        self.assertIn("section,id,dimension,score_or_severity,summary,evidence_basis", csv_text)
        self.assertIn("render-mindfront-report-pdf.ps1", handoff)

    def test_report_bundle_surfaces_documentation_quality_section(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            analysis = analyze_message_brief(
                PROJECT / "examples" / "briefs" / "specialist-documentation-brief.json",
                config_root=PROJECT / "config",
            )
            analysis_path = write_analysis_report(analysis, temp_path / "analysis.json")
            bundle = build_report_bundle(analysis_path, config_root=PROJECT / "config")
            output_paths = write_report_bundle(bundle, temp_path / "report")

            payload = json.loads((temp_path / "report" / "mindfront-audit-report.json").read_text(encoding="utf-8"))
            markdown = (temp_path / "report" / "mindfront-audit-report.md").read_text(encoding="utf-8")
            html = (temp_path / "report" / "source.html").read_text(encoding="utf-8")

        self.assertTrue(payload["sections"]["documentationQuality"]["detected"])
        self.assertIn("Documentation Quality", markdown)
        self.assertIn("specialist-bandwidth", markdown)
        self.assertIn("Documentation Quality", html)
        self.assertTrue(output_paths)

    def test_report_bundle_surfaces_task_validation_without_confidence_upgrade(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            analysis = analyze_message_brief(
                PROJECT / "examples" / "briefs" / "specialist-documentation-brief.json",
                config_root=PROJECT / "config",
            )
            analysis_path = write_analysis_report(analysis, temp_path / "analysis.json")
            validation = build_task_validation_result(
                PROJECT / "examples" / "task-validation" / "specialist-documentation-task-validation.json",
                analysis_path=analysis_path,
            )
            validation_path = write_task_validation_result(validation, temp_path / "task-validation")
            bundle = build_report_bundle(
                analysis_path,
                config_root=PROJECT / "config",
                task_validation_path=validation_path,
            )
            write_report_bundle(bundle, temp_path / "report")

            payload = json.loads((temp_path / "report" / "mindfront-audit-report.json").read_text(encoding="utf-8"))
            markdown = (temp_path / "report" / "mindfront-audit-report.md").read_text(encoding="utf-8")
            html = (temp_path / "report" / "source.html").read_text(encoding="utf-8")

        self.assertTrue(payload["sections"]["taskValidation"]["included"])
        self.assertEqual("synthetic_fixture", payload["sections"]["taskValidation"]["observationSource"])
        self.assertEqual("synthetic_task_fixture", payload["sections"]["taskValidation"]["evidenceBasis"])
        self.assertEqual("synthetic_fixture_only", payload["sections"]["taskValidation"]["evidenceGrade"])
        self.assertFalse(payload["sections"]["taskValidation"]["realTaskEvidenceCreated"])
        self.assertFalse(payload["sections"]["taskValidation"]["marketEvidenceCreated"])
        self.assertIn("Task Validation Evidence", markdown)
        self.assertIn("Task Validation Evidence", html)
        self.assertIn("workflow behavior", markdown)
        self.assertNotIn("validated_for_exact_context", json.dumps(payload))

    def test_report_bundle_surfaces_task_protocol_as_handoff_not_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            analysis = analyze_message_brief(
                PROJECT / "examples" / "briefs" / "specialist-documentation-brief.json",
                config_root=PROJECT / "config",
            )
            analysis_path = write_analysis_report(analysis, temp_path / "analysis.json")
            research = build_research_plan(analysis_path)
            research_path = write_research_plan(research, temp_path / "research")[0]
            protocol = build_task_observation_protocol(analysis_path, research_plan_path=research_path)
            protocol_path = write_task_observation_protocol(protocol, temp_path / "protocol")[0]
            bundle = build_report_bundle(
                analysis_path,
                config_root=PROJECT / "config",
                research_plan_path=research_path,
                task_protocol_path=protocol_path,
            )
            write_report_bundle(bundle, temp_path / "report")

            payload = json.loads((temp_path / "report" / "mindfront-audit-report.json").read_text(encoding="utf-8"))
            markdown = (temp_path / "report" / "mindfront-audit-report.md").read_text(encoding="utf-8")
            html = (temp_path / "report" / "source.html").read_text(encoding="utf-8")

        self.assertTrue(payload["sections"]["taskProtocol"]["included"])
        self.assertEqual(protocol["protocolId"], payload["sections"]["taskProtocol"]["protocolId"])
        self.assertIn(protocol["protocolId"], payload["includedArtifactIds"])
        self.assertFalse(payload["sections"]["taskProtocol"]["marketEvidenceCreated"])
        self.assertTrue(payload["sections"]["taskProtocol"]["notMarketEvidence"])
        self.assertIn("Protocols are evidence-collection handoffs only", payload["evidenceBoundary"])
        self.assertIn("Task Observation Protocol", markdown)
        self.assertIn("Intended observation source", markdown)
        self.assertIn("Evidence status: `not_collected`", markdown)
        self.assertIn("Task Observation Protocol", html)
        self.assertIn("not_collected", html)
        self.assertNotIn("validated_for_exact_context", json.dumps(payload))

    def test_report_bundle_rejects_protocol_marked_as_market_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            analysis = analyze_message_brief(
                PROJECT / "examples" / "briefs" / "specialist-documentation-brief.json",
                config_root=PROJECT / "config",
            )
            analysis_path = write_analysis_report(analysis, temp_path / "analysis.json")
            protocol = build_task_observation_protocol(analysis_path)
            protocol["notMarketEvidence"] = False
            protocol_path = temp_path / "bad-protocol.json"
            protocol_path.write_text(json.dumps(protocol), encoding="utf-8")

            with self.assertRaises(ReportBundleBlockedError) as raised:
                build_report_bundle(
                    analysis_path,
                    config_root=PROJECT / "config",
                    task_protocol_path=protocol_path,
                )

        self.assertIn("evidence_boundary_violation", {reason["code"] for reason in raised.exception.reasons})

    def test_report_bundle_rejects_malformed_task_validation_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            analysis = analyze_message_brief(
                PROJECT / "examples" / "briefs" / "specialist-documentation-brief.json",
                config_root=PROJECT / "config",
            )
            analysis_path = write_analysis_report(analysis, temp_path / "analysis.json")
            validation = build_task_validation_result(
                PROJECT / "examples" / "task-validation" / "specialist-documentation-task-validation.json",
                analysis_path=analysis_path,
            )
            validation["marketEvidenceCreated"] = True
            validation["evidenceBasis"] = "small_user_test"
            validation_path = temp_path / "bad-task-validation.json"
            validation_path.write_text(json.dumps(validation), encoding="utf-8")

            with self.assertRaises(ReportBundleBlockedError) as raised:
                build_report_bundle(
                    analysis_path,
                    config_root=PROJECT / "config",
                    task_validation_path=validation_path,
                )

        reason_codes = {reason["code"] for reason in raised.exception.reasons}
        self.assertIn("evidence_boundary_violation", reason_codes)
        self.assertIn("evidence_basis_mismatch", reason_codes)

    def test_report_bundle_rejects_mismatched_optional_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            paths = _sample_artifact_paths(temp_path)
            research = json.loads(paths["research"].read_text(encoding="utf-8"))
            research["sourceAnalysisReportId"] = "report-other"
            bad_research_path = temp_path / "bad-research.json"
            bad_research_path.write_text(json.dumps(research), encoding="utf-8")

            with self.assertRaises(ReportBundleBlockedError) as raised:
                build_report_bundle(
                    paths["analysis"],
                    config_root=PROJECT / "config",
                    research_plan_path=bad_research_path,
                )

        self.assertEqual("source_mismatch", raised.exception.reasons[0]["code"])

    def test_cli_report_writes_directory_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            paths = _sample_artifact_paths(temp_path)
            output_dir = temp_path / "report-output"
            env = dict(os.environ)
            env["PYTHONPATH"] = str(SRC)
            completed = subprocess.run(
                [
                    sys.executable,
                    "-B",
                    "-m",
                    "mindfront.cli",
                    "report",
                    "--analysis",
                    str(paths["analysis"]),
                    "--variants",
                    str(paths["variants"]),
                    "--comparison",
                    str(paths["comparison"]),
                    "--stress",
                    str(paths["stress"]),
                    "--research-plan",
                    str(paths["research"]),
                    "--config-root",
                    str(PROJECT / "config"),
                    "--output",
                    str(output_dir),
                ],
                check=False,
                env=env,
                capture_output=True,
                text=True,
            )

            self.assertEqual(0, completed.returncode, completed.stderr)
            payload = json.loads((output_dir / "mindfront-audit-report.json").read_text(encoding="utf-8"))

        self.assertEqual("audit_report_bundle", payload["artifactType"])
        self.assertIn("source.html", completed.stdout)
        self.assertIn("mindfront-audit-report.html", completed.stdout)


def _sample_artifact_paths(root: Path) -> dict[str, Path]:
    analysis = analyze_message_brief(
        PROJECT / "examples" / "briefs" / "sample-message-brief.json",
        config_root=PROJECT / "config",
    )
    analysis_path = write_analysis_report(analysis, root / "analysis.json")
    variants = rewrite_message_brief(
        PROJECT / "examples" / "briefs" / "sample-message-brief.json",
        config_root=PROJECT / "config",
    )
    variants_path = write_rewrite_bundle(variants, root / "variants.json")
    comparison = compare_variant_bundle(variants_path)
    comparison_path = write_comparison_report(comparison, root / "comparison.json")
    stress = run_reader_stress_test(analysis_path, config_root=PROJECT / "config")
    stress_path = write_stress_report(stress, root / "stress.json")
    research = build_research_plan(analysis_path)
    research_paths = write_research_plan(research, root / "research")
    return {
        "analysis": analysis_path,
        "variants": variants_path,
        "comparison": comparison_path,
        "stress": stress_path,
        "research": research_paths[0],
    }


if __name__ == "__main__":
    unittest.main()

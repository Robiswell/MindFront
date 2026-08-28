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
from mindfront.research import ResearchPlanBlockedError, build_research_plan, write_research_plan
from test_analysis import _specialist_documentation_brief


REQUIRED_RESEARCH_QUESTION_FIELDS = {
    "questionId",
    "uncertainty",
    "method",
    "evidenceGradeTarget",
    "sampleSource",
    "sampleSize",
    "screenerCriteria",
    "roleFit",
    "protocolVersion",
    "biasRisks",
    "consentScript",
    "sensitiveDataAvoidance",
    "deceptionUsed",
    "minorOrVulnerableParticipantRule",
    "stopConditions",
    "decisionThreshold",
    "relatedFindingIds",
    "relatedClaimIds",
}


class ResearchPlanTests(unittest.TestCase):
    def test_research_plan_generates_schema_complete_questions(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            analysis = analyze_message_brief(
                PROJECT / "examples" / "briefs" / "sample-message-brief.json",
                config_root=PROJECT / "config",
            )
            analysis_path = write_analysis_report(analysis, Path(temp_dir) / "analysis.json")
            plan = build_research_plan(analysis_path)

        self.assertEqual("research_plan", plan["artifactType"])
        self.assertTrue(plan["questions"])
        self.assertFalse(plan["marketEvidenceCreated"])
        self.assertTrue(plan["notMarketEvidence"])
        self.assertEqual("heuristic_inference", plan["evidenceBasis"])
        for question in plan["questions"]:
            self.assertTrue(REQUIRED_RESEARCH_QUESTION_FIELDS.issubset(question))
            self.assertEqual("research_question", question["artifactType"])
            self.assertFalse(question["deceptionUsed"])
            self.assertIn("Do not collect personal health", question["sensitiveDataAvoidance"])
            self.assertNotEqual("small_user_test", question["evidenceGradeTarget"])
            self.assertNotIn("statistically", question["decisionThreshold"].lower())
        self.assertEqual("comprehension_test", plan["questions"][0]["method"])

    def test_research_plan_covers_major_findings(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            analysis = analyze_message_brief(
                PROJECT / "examples" / "briefs" / "sample-message-brief.json",
                config_root=PROJECT / "config",
            )
            analysis_path = write_analysis_report(analysis, Path(temp_dir) / "analysis.json")
            plan = build_research_plan(analysis_path)

        major_finding_ids = {
            finding["findingId"]
            for finding in analysis["findings"]
            if finding["severity"] in {"medium", "high", "blocked"}
        }
        covered_finding_ids = {
            finding_id
            for question in plan["questions"]
            for finding_id in question["relatedFindingIds"]
        }
        self.assertTrue(major_finding_ids.issubset(covered_finding_ids))
        self.assertTrue(all(item["coverageState"] == "covered" for item in plan["uncertaintyCoverage"]))
        self.assertTrue(plan["interviewScript"]["items"])
        self.assertTrue(plan["surveyQuestions"])
        self.assertTrue(plan["usabilityTasks"])
        self.assertTrue(plan["abHypotheses"])
        self.assertIn("sample size", plan["abHypotheses"][0]["sampleSizeCaveat"])
        self.assertTrue(all(item["coverageState"] == "covered" for item in plan["motivationFrictionCoverage"]))
        self.assertTrue(all(item["coverageState"] == "covered" for item in plan["trustGapCoverage"]))

    def test_research_plan_routes_documentation_findings_to_task_validation(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            brief_path = temp_path / "specialist-doc-brief.json"
            brief_path.write_text(json.dumps(_specialist_documentation_brief()), encoding="utf-8")
            analysis = analyze_message_brief(brief_path, config_root=PROJECT / "config")
            analysis_path = write_analysis_report(analysis, temp_path / "analysis.json")
            plan = build_research_plan(analysis_path)

        usability_uncertainties = [
            question["uncertainty"].lower()
            for question in plan["questions"]
            if question["method"] == "usability_task"
        ]
        evidence_boundary_uncertainties = [
            question["uncertainty"].lower()
            for question in plan["questions"]
            if any("evidence boundary" in finding["issue"].lower() for finding in analysis["findings"] if finding["findingId"] in question["relatedFindingIds"])
        ]
        self.assertTrue(any("learning tax" in uncertainty for uncertainty in usability_uncertainties))
        self.assertTrue(any("sourced, assumed, heuristic, or unvalidated" in uncertainty for uncertainty in evidence_boundary_uncertainties))
        self.assertTrue(plan["usabilityTasks"])
        self.assertFalse(plan["marketEvidenceCreated"])

    def test_research_plan_rejects_invalid_artifact_type(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "invalid.json"
            path.write_text(json.dumps({"artifactType": "copy_variant_bundle"}), encoding="utf-8")

            with self.assertRaises(ResearchPlanBlockedError) as raised:
                build_research_plan(path)

        self.assertEqual("invalid_artifact_type", raised.exception.reasons[0]["code"])

    def test_write_research_plan_directory_outputs_json_and_markdown(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            analysis = analyze_message_brief(
                PROJECT / "examples" / "briefs" / "sample-message-brief.json",
                config_root=PROJECT / "config",
            )
            analysis_path = write_analysis_report(analysis, temp_path / "analysis.json")
            plan = build_research_plan(analysis_path)
            paths = write_research_plan(plan, temp_path / "research-output")

            json_path = temp_path / "research-output" / "research-plan.json"
            markdown_path = temp_path / "research-output" / "research-plan.md"

            self.assertEqual([json_path, markdown_path], paths)
            payload = json.loads(json_path.read_text(encoding="utf-8"))
            markdown = markdown_path.read_text(encoding="utf-8")

        self.assertEqual("research_plan", payload["artifactType"])
        self.assertTrue(payload["outputHash"].startswith("sha256:"))
        self.assertIn("# Mindfront Research Plan", markdown)
        self.assertIn("Market evidence created: `false`", markdown)

    def test_cli_research_plan_writes_directory_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            analysis = analyze_message_brief(
                PROJECT / "examples" / "briefs" / "sample-message-brief.json",
                config_root=PROJECT / "config",
            )
            analysis_path = write_analysis_report(analysis, temp_path / "analysis.json")
            output_dir = temp_path / "research"
            env = dict(os.environ)
            env["PYTHONPATH"] = str(SRC)
            completed = subprocess.run(
                [
                    sys.executable,
                    "-B",
                    "-m",
                    "mindfront.cli",
                    "research-plan",
                    "--analysis",
                    str(analysis_path),
                    "--output",
                    str(output_dir),
                ],
                check=False,
                env=env,
                capture_output=True,
                text=True,
            )

            self.assertEqual(0, completed.returncode, completed.stderr)
            payload = json.loads((output_dir / "research-plan.json").read_text(encoding="utf-8"))
            markdown = (output_dir / "research-plan.md").read_text(encoding="utf-8")

        self.assertEqual("research_plan", payload["artifactType"])
        self.assertIn("research-plan.md", completed.stdout)
        self.assertIn("## A/B Hypotheses", markdown)


if __name__ == "__main__":
    unittest.main()

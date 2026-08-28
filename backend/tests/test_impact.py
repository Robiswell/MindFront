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

from mindfront.analysis import analyze_message_brief, write_analysis_report
from mindfront.impact import (
    TaskValidationBlockedError,
    build_task_validation_result,
    write_task_validation_result,
)


class TaskValidationTests(unittest.TestCase):
    def test_task_validation_summarizes_synthetic_fixture_without_evidence_upgrade(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            analysis_path = _specialist_analysis_path(Path(temp_dir))
            result = build_task_validation_result(
                PROJECT / "examples" / "task-validation" / "specialist-documentation-task-validation.json",
                analysis_path=analysis_path,
            )
            output_path = write_task_validation_result(result, Path(temp_dir) / "task-validation")
            payload = json.loads(output_path.read_text(encoding="utf-8"))

        self.assertEqual("documentation_task_validation_result", payload["artifactType"])
        self.assertEqual("synthetic_fixture", payload["observationSource"])
        self.assertEqual("synthetic_task_fixture", payload["evidenceBasis"])
        self.assertEqual("synthetic_fixture_only", payload["evidenceGrade"])
        self.assertFalse(payload["marketEvidenceCreated"])
        self.assertTrue(payload["notMarketEvidence"])
        self.assertFalse(payload["realTaskEvidenceCreated"])
        self.assertFalse(payload["rawParticipantDataStored"])
        self.assertEqual(5, payload["sample"]["participantCount"])
        self.assertEqual(5, payload["sample"]["sessionCount"])
        self.assertEqual(0.8, payload["aggregateMetrics"]["completionRate"])
        self.assertLess(payload["aggregateMetrics"]["medianSkimToAnswerSeconds"], 90)
        self.assertTrue(payload["beforeAfterDeltas"]["medianSkimToAnswerSeconds"]["improved"])
        self.assertIn("task_completion_rate", {item["signalId"] for item in payload["executiveSignals"]})
        self.assertIn("owner_field_missing", {item["value"] for item in payload["aggregateMetrics"]["topTrustObjectionCodes"]})
        self.assertNotIn("validated_for_exact_context", json.dumps(payload))
        self.assertIn("fixture", payload["recommendedNextStep"].lower())

    def test_task_validation_summarizes_real_observations_as_exact_context_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            analysis_path = _specialist_analysis_path(temp_path)
            source = _task_validation_fixture()
            source["observationSource"] = "real_task_observation"
            path = temp_path / "real-validation.json"
            path.write_text(json.dumps(source), encoding="utf-8")
            result = build_task_validation_result(path, analysis_path=analysis_path)
            output_path = write_task_validation_result(result, temp_path / "real-result")
            payload = json.loads(output_path.read_text(encoding="utf-8"))

        self.assertEqual("small_user_test", payload["evidenceBasis"])
        self.assertEqual("exact_context_directional", payload["evidenceGrade"])
        self.assertTrue(payload["realTaskEvidenceCreated"])
        self.assertEqual("directional_task_evidence_positive", payload["decisionState"])
        self.assertTrue(all(item["realTaskEvidenceCreated"] for item in payload["executiveSignals"]))

    def test_task_validation_rejects_personal_data(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            source = _task_validation_fixture()
            source["containsPersonalData"] = True
            path = Path(temp_dir) / "bad-validation.json"
            path.write_text(json.dumps(source), encoding="utf-8")

            with self.assertRaises(TaskValidationBlockedError) as raised:
                build_task_validation_result(path)

        self.assertEqual("personal_data_not_allowed", raised.exception.reasons[0]["code"])

    def test_task_validation_rejects_string_boolean_completion(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            source = _task_validation_fixture()
            source["sessions"][0]["completed"] = "false"
            path = Path(temp_dir) / "bad-validation.json"
            path.write_text(json.dumps(source), encoding="utf-8")

            with self.assertRaises(TaskValidationBlockedError) as raised:
                build_task_validation_result(path)

        self.assertIn("invalid_boolean_field", {reason["code"] for reason in raised.exception.reasons})

    def test_task_validation_rejects_fractional_counts_and_raw_objections(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            source = _task_validation_fixture()
            source["sessions"][0]["followUpQuestionCount"] = 1.5
            source["sessions"][0]["trustObjections"] = ["raw text should not be stored"]
            path = Path(temp_dir) / "bad-validation.json"
            path.write_text(json.dumps(source), encoding="utf-8")

            with self.assertRaises(TaskValidationBlockedError) as raised:
                build_task_validation_result(path)

        codes = {reason["code"] for reason in raised.exception.reasons}
        self.assertIn("invalid_integer_field", codes)
        self.assertIn("raw_trust_objections_not_allowed", codes)

    def test_cli_task_validation_writes_result(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            analysis_path = _specialist_analysis_path(temp_path)
            output_dir = temp_path / "task-validation-result"
            env = dict(os.environ)
            env["PYTHONPATH"] = str(SRC)
            completed = subprocess.run(
                [
                    sys.executable,
                    "-B",
                    "-m",
                    "mindfront.cli",
                    "task-validation",
                    "--input",
                    str(PROJECT / "examples" / "task-validation" / "specialist-documentation-task-validation.json"),
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
            output_path = output_dir / "documentation-task-validation-result.json"
            output_exists = output_path.exists()

        self.assertEqual(0, completed.returncode, completed.stderr)
        self.assertTrue(output_exists)
        self.assertIn("documentation-task-validation-result.json", completed.stdout)


def _specialist_analysis_path(root: Path) -> Path:
    analysis = analyze_message_brief(
        PROJECT / "examples" / "briefs" / "specialist-documentation-brief.json",
        config_root=PROJECT / "config",
    )
    return write_analysis_report(analysis, root / "specialist-analysis.json")


def _task_validation_fixture() -> dict[str, object]:
    return json.loads(
        (PROJECT / "examples" / "task-validation" / "specialist-documentation-task-validation.json").read_text(
            encoding="utf-8"
        )
    )


if __name__ == "__main__":
    unittest.main()

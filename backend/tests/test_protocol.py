from __future__ import annotations

import csv
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
from mindfront.impact import build_task_validation_result
from mindfront.protocol import (
    SESSION_TEMPLATE_COLUMNS,
    TaskInputBlockedError,
    build_task_observation_protocol,
    build_task_validation_input_from_protocol,
    write_task_observation_protocol,
    write_task_validation_input,
)
from mindfront.research import build_research_plan, write_research_plan


class TaskObservationProtocolTests(unittest.TestCase):
    def test_protocol_writes_json_markdown_and_session_template(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            paths = _specialist_analysis_and_research(temp_path)
            protocol = build_task_observation_protocol(
                paths["analysis"],
                research_plan_path=paths["research"],
                document_id="specialist-doc-001",
            )
            output_paths = write_task_observation_protocol(protocol, temp_path / "protocol")
            payload = json.loads((temp_path / "protocol" / "documentation-task-observation-protocol.json").read_text(encoding="utf-8"))
            markdown = (temp_path / "protocol" / "documentation-task-observation-protocol.md").read_text(encoding="utf-8")
            with (temp_path / "protocol" / "documentation-task-session-template.csv").open("r", encoding="utf-8", newline="") as handle:
                rows = list(csv.DictReader(handle))

        self.assertEqual(3, len(output_paths))
        self.assertEqual("documentation_task_observation_protocol", payload["artifactType"])
        self.assertEqual("real_task_observation", payload["observationSource"])
        self.assertFalse(payload["marketEvidenceCreated"])
        self.assertTrue(payload["notMarketEvidence"])
        self.assertEqual("specialist-doc-001", payload["documentId"])
        self.assertEqual(SESSION_TEMPLATE_COLUMNS, payload["sessionTemplateColumns"])
        self.assertTrue(payload["tasks"])
        self.assertEqual(payload["tasks"][0]["taskId"], rows[0]["taskId"])
        self.assertIn("not as proof by itself", json.dumps(payload["limitations"]))
        self.assertIn("Evidence Boundary", markdown)
        self.assertIn("Intended observation source", markdown)
        self.assertIn("Evidence status: `not_collected`", markdown)
        self.assertNotIn("email", ",".join(payload["sessionTemplateColumns"]).lower())

    def test_task_input_requires_explicit_real_observation_source(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            paths = _specialist_analysis_and_research(temp_path)
            protocol = build_task_observation_protocol(paths["analysis"], research_plan_path=paths["research"])
            protocol_path = write_task_observation_protocol(protocol, temp_path / "protocol")[0]
            sessions_path = _write_sessions_csv(temp_path / "sessions.csv", protocol)
            task_input = build_task_validation_input_from_protocol(protocol_path, sessions_path)
            input_path = write_task_validation_input(task_input, temp_path / "task-input")
            validation = build_task_validation_result(input_path, analysis_path=paths["analysis"])

        self.assertEqual("synthetic_fixture", task_input["observationSource"])
        self.assertEqual("synthetic_workflow_fixture", task_input["evidenceCollectionMethod"])
        self.assertEqual("synthetic_fixture", validation["observationSource"])
        self.assertFalse(validation["realTaskEvidenceCreated"])
        self.assertEqual("synthetic_task_fixture", validation["evidenceBasis"])

    def test_task_input_from_real_filled_csv_carries_lineage_into_validation_result(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            paths = _specialist_analysis_and_research(temp_path)
            protocol = build_task_observation_protocol(paths["analysis"], research_plan_path=paths["research"])
            protocol_path = write_task_observation_protocol(protocol, temp_path / "protocol")[0]
            sessions_path = _write_sessions_csv(temp_path / "sessions.csv", protocol)
            task_input = build_task_validation_input_from_protocol(
                protocol_path,
                sessions_path,
                observation_source="real_task_observation",
            )
            input_path = write_task_validation_input(task_input, temp_path / "task-input")
            validation = build_task_validation_result(input_path, analysis_path=paths["analysis"])

        self.assertEqual("documentation_task_validation_input", task_input["artifactType"])
        self.assertEqual(protocol["protocolId"], task_input["sourceProtocolId"])
        self.assertEqual("real_task_observation", task_input["observationSource"])
        self.assertFalse(task_input["containsPersonalData"])
        self.assertFalse(task_input["containsCustomerConfidentialData"])
        self.assertEqual(protocol["protocolId"], validation["sourceProtocolId"])
        self.assertEqual(task_input["sourceSessionsHash"], validation["sourceSessionsHash"])
        self.assertTrue(validation["realTaskEvidenceCreated"])
        self.assertEqual("small_user_test", validation["evidenceBasis"])
        self.assertFalse(validation["marketEvidenceCreated"])

    def test_task_input_rejects_case_varied_prohibited_columns(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            paths = _specialist_analysis_and_research(temp_path)
            protocol = build_task_observation_protocol(paths["analysis"], research_plan_path=paths["research"])
            protocol_path = write_task_observation_protocol(protocol, temp_path / "protocol")[0]
            sessions_path = temp_path / "bad-sessions.csv"
            with sessions_path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=[*SESSION_TEMPLATE_COLUMNS, "Email", "RawComments"])
                writer.writeheader()
                row = _session_row(protocol["tasks"][0]["taskId"], index=1)
                row["Email"] = "person@example.com"
                row["RawComments"] = "raw note"
                writer.writerow(row)

            with self.assertRaises(TaskInputBlockedError) as raised:
                build_task_validation_input_from_protocol(protocol_path, sessions_path)

        self.assertIn("prohibited_session_column", {reason["code"] for reason in raised.exception.reasons})

    def test_cli_task_protocol_and_task_input_write_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            paths = _specialist_analysis_and_research(temp_path)
            protocol_dir = temp_path / "cli-protocol"
            input_dir = temp_path / "cli-input"
            real_input_dir = temp_path / "cli-input-real"
            env = dict(os.environ)
            env["PYTHONPATH"] = str(SRC)
            protocol_run = subprocess.run(
                [
                    sys.executable,
                    "-B",
                    "-m",
                    "mindfront.cli",
                    "task-protocol",
                    "--analysis",
                    str(paths["analysis"]),
                    "--research-plan",
                    str(paths["research"]),
                    "--output",
                    str(protocol_dir),
                ],
                check=False,
                env=env,
                capture_output=True,
                text=True,
            )
            protocol_path = protocol_dir / "documentation-task-observation-protocol.json"
            protocol = json.loads(protocol_path.read_text(encoding="utf-8"))
            sessions_path = _write_sessions_csv(temp_path / "sessions.csv", protocol)
            input_run = subprocess.run(
                [
                    sys.executable,
                    "-B",
                    "-m",
                    "mindfront.cli",
                    "task-input",
                    "--protocol",
                    str(protocol_path),
                    "--sessions-csv",
                    str(sessions_path),
                    "--output",
                    str(input_dir),
                ],
                check=False,
                env=env,
                capture_output=True,
                text=True,
            )
            real_input_run = subprocess.run(
                [
                    sys.executable,
                    "-B",
                    "-m",
                    "mindfront.cli",
                    "task-input",
                    "--protocol",
                    str(protocol_path),
                    "--sessions-csv",
                    str(sessions_path),
                    "--observation-source",
                    "real_task_observation",
                    "--output",
                    str(real_input_dir),
                ],
                check=False,
                env=env,
                capture_output=True,
                text=True,
            )
            input_exists = (input_dir / "documentation-task-validation-input.json").exists()
            input_payload = json.loads((input_dir / "documentation-task-validation-input.json").read_text(encoding="utf-8"))
            real_input_payload = json.loads(
                (real_input_dir / "documentation-task-validation-input.json").read_text(encoding="utf-8")
            )

        self.assertEqual(0, protocol_run.returncode, protocol_run.stderr)
        self.assertEqual(0, input_run.returncode, input_run.stderr)
        self.assertEqual(0, real_input_run.returncode, real_input_run.stderr)
        self.assertIn("documentation-task-observation-protocol.json", protocol_run.stdout)
        self.assertTrue(input_exists)
        self.assertIn("documentation-task-validation-input.json", input_run.stdout)
        self.assertEqual("synthetic_fixture", input_payload["observationSource"])
        self.assertIn("workflow fixture", input_payload["provenanceBoundary"])
        self.assertEqual("real_task_observation", real_input_payload["observationSource"])
        self.assertIn("caller explicitly declared", real_input_payload["provenanceBoundary"])


def _specialist_analysis_and_research(root: Path) -> dict[str, Path]:
    analysis = analyze_message_brief(
        PROJECT / "examples" / "briefs" / "specialist-documentation-brief.json",
        config_root=PROJECT / "config",
    )
    analysis_path = write_analysis_report(analysis, root / "analysis.json")
    research = build_research_plan(analysis_path)
    research_path = write_research_plan(research, root / "research")[0]
    return {"analysis": analysis_path, "research": research_path}


def _write_sessions_csv(path: Path, protocol: dict[str, object]) -> Path:
    tasks = protocol["tasks"]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=SESSION_TEMPLATE_COLUMNS)
        writer.writeheader()
        for index in range(1, 6):
            task = tasks[(index - 1) % len(tasks)]
            writer.writerow(_session_row(task["taskId"], index=index))
    return path


def _session_row(task_id: str, *, index: int) -> dict[str, object]:
    return {
        "sessionId": f"session_{index:03d}",
        "participantToken": f"participant_{index:03d}",
        "roleSegment": "target_reader",
        "taskId": task_id,
        "completed": "true" if index != 5 else "false",
        "skimToAnswerSeconds": str(45 + index),
        "followUpQuestionCount": "0" if index < 4 else "1",
        "skippedSectionCount": "0" if index < 5 else "2",
        "expertRespectRating": "4",
        "reuseIntentRating": "4",
        "trustObjectionCodes": "" if index < 5 else "owner_field_missing",
    }


if __name__ == "__main__":
    unittest.main()

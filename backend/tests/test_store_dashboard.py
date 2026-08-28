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
from mindfront.compare import compare_variant_bundle, write_comparison_report
from mindfront.dashboard import build_static_dashboard
from mindfront.db import (
    StoreBlockedError,
    compare_analysis_history,
    delete_run,
    export_store,
    initialize_store_path,
    list_analysis_history,
    refresh_stale_state,
    store_artifact_set,
)
from mindfront.impact import build_task_validation_result, write_task_validation_result
from mindfront.improvement import build_improvement_plan, write_improvement_plan
from mindfront.protocol import build_task_observation_protocol, write_task_observation_protocol
from mindfront.reports import build_report_bundle, write_report_bundle
from mindfront.research import build_research_plan, write_research_plan
from mindfront.rewrite import rewrite_message_brief, write_rewrite_bundle
from mindfront.stress import run_reader_stress_test, write_stress_report


class StoreDashboardTests(unittest.TestCase):
    def test_store_ingest_lists_and_compares_history(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            paths = _sample_artifact_paths(temp_path)
            db_path = temp_path / "mindfront.sqlite"
            init = initialize_store_path(db_path)
            result = store_artifact_set(
                db_path,
                analysis_path=paths["analysis"],
                variants_path=paths["variants"],
                comparison_path=paths["comparison"],
                stress_path=paths["stress"],
                research_plan_path=paths["research"],
                report_path=paths["report"],
            )
            history = list_analysis_history(db_path)
            comparison = compare_analysis_history(db_path)

        self.assertEqual("history_store_init_result", init["artifactType"])
        self.assertEqual("history_store_result", result["artifactType"])
        self.assertFalse(result["marketEvidenceCreated"])
        self.assertFalse(result["rawSourceTextStored"])
        self.assertEqual(1, history["runCount"])
        self.assertEqual("current_at_ingest", history["runs"][0]["staleState"])
        self.assertGreater(history["runs"][0]["simulatedResultCount"], 0)
        self.assertEqual(0, history["runs"][0]["validatedSignalCount"])
        self.assertTrue(comparison["scoreChanges"])
        self.assertEqual([], comparison["repeatedFindings"])
        self.assertIn("not counted as validated", comparison["simulatedVsValidated"]["interpretation"])

    def test_dashboard_build_separates_simulated_from_validated(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            paths = _sample_artifact_paths(temp_path)
            db_path = temp_path / "mindfront.sqlite"
            store_artifact_set(
                db_path,
                analysis_path=paths["analysis"],
                variants_path=paths["variants"],
                comparison_path=paths["comparison"],
                stress_path=paths["stress"],
                research_plan_path=paths["research"],
                report_path=paths["report"],
            )
            output_paths = build_static_dashboard(db_path, temp_path / "dashboard")
            payload = json.loads((temp_path / "dashboard" / "mindfront-dashboard.json").read_text(encoding="utf-8"))
            html = (temp_path / "dashboard" / "index.html").read_text(encoding="utf-8")

        self.assertEqual(2, len(output_paths))
        self.assertEqual("static_dashboard_bundle", payload["artifactType"])
        self.assertFalse(payload["marketEvidenceCreated"])
        self.assertGreater(payload["summary"]["simulatedResultCount"], 0)
        self.assertEqual(0, payload["summary"]["validatedSignalCount"])
        self.assertIn("Simulated Versus Validated", html)
        self.assertIn("dashboard display never upgrades confidence", payload["evidenceBoundary"])
        self.assertNotIn("validated_for_exact_context", json.dumps(payload))
        self.assertTrue(payload["improvementPlan"]["planId"].startswith("improvement-plan-"))
        self.assertIn(
            "mindfront_improvement_plan",
            {item["label"] for item in payload["evidenceSeparation"]},
        )

    def test_improvement_plan_prioritizes_protocol_handoff_without_market_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            paths = _specialist_protocol_artifact_paths(temp_path)
            db_path = temp_path / "mindfront.sqlite"
            store_artifact_set(
                db_path,
                analysis_path=paths["analysis"],
                task_protocol_path=paths["task_protocol"],
            )
            plan = build_improvement_plan(db_path)
            output_paths = write_improvement_plan(plan, temp_path / "improvement")
            written = json.loads((temp_path / "improvement" / "mindfront-improvement-plan.json").read_text(encoding="utf-8"))

        action_types = {action["actionType"] for action in plan["priorityActions"]}
        self.assertEqual(2, len(output_paths))
        self.assertEqual("mindfront_improvement_plan", plan["artifactType"])
        self.assertFalse(plan["marketEvidenceCreated"])
        self.assertTrue(plan["notMarketEvidence"])
        self.assertIn("collect_task_sessions_from_protocol", action_types)
        self.assertIn("no_real_task_validation", plan["loopReadiness"]["blockingGaps"])
        self.assertEqual(plan["planId"], written["planId"])

    def test_improvement_plan_keeps_synthetic_fixture_out_of_real_task_actions(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            paths = _specialist_artifact_paths(temp_path)
            db_path = temp_path / "mindfront.sqlite"
            store_artifact_set(
                db_path,
                analysis_path=paths["analysis"],
                task_validation_path=paths["task_validation"],
            )
            plan = build_improvement_plan(db_path)

        action_types = {action["actionType"] for action in plan["priorityActions"]}
        self.assertNotIn("reduce_documentation_task_friction", action_types)
        self.assertIn("no_real_task_validation", plan["loopReadiness"]["blockingGaps"])

    def test_improvement_plan_surfaces_real_task_friction(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            paths = _specialist_artifact_paths(temp_path, observation_source="real_task_observation")
            db_path = temp_path / "mindfront.sqlite"
            store_artifact_set(
                db_path,
                analysis_path=paths["analysis"],
                task_validation_path=paths["task_validation"],
            )
            plan = build_improvement_plan(db_path)

        friction_actions = [
            action
            for action in plan["priorityActions"]
            if action["actionType"] == "reduce_documentation_task_friction"
        ]
        self.assertTrue(friction_actions)
        self.assertIn("exact-context", plan["evidenceBoundary"])
        self.assertGreater(len(friction_actions[0]["details"]["frictionSignals"]), 0)

    def test_store_and_dashboard_surface_synthetic_task_fixture_without_signal_upgrade(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            paths = _specialist_artifact_paths(temp_path)
            db_path = temp_path / "mindfront.sqlite"
            result = store_artifact_set(
                db_path,
                analysis_path=paths["analysis"],
                task_validation_path=paths["task_validation"],
            )
            history = list_analysis_history(db_path)
            comparison = compare_analysis_history(db_path)
            build_static_dashboard(db_path, temp_path / "dashboard")
            payload = json.loads((temp_path / "dashboard" / "mindfront-dashboard.json").read_text(encoding="utf-8"))
            html = (temp_path / "dashboard" / "index.html").read_text(encoding="utf-8")

        self.assertIn("task_validation", result["storedArtifactTypes"])
        self.assertEqual(0, history["runs"][0]["validatedSignalCount"])
        self.assertEqual(0, history["runs"][0]["taskValidationSignalCount"])
        self.assertEqual(1, history["runs"][0]["taskValidationCount"])
        self.assertEqual(1, comparison["taskValidationSummary"]["validationRunCount"])
        self.assertEqual(0, comparison["taskValidationSummary"]["realTaskEvidenceRunCount"])
        self.assertEqual(1, comparison["taskValidationSummary"]["syntheticFixtureRunCount"])
        self.assertEqual(1, payload["summary"]["taskValidationRunCount"])
        self.assertEqual(0, payload["summary"]["taskValidationSignalCount"])
        self.assertTrue(payload["taskValidations"])
        self.assertEqual("synthetic_fixture", payload["taskValidations"][0]["observationSource"])
        self.assertEqual("synthetic_task_fixture", payload["taskValidations"][0]["evidenceBasis"])
        self.assertEqual("synthetic_fixture_only", payload["taskValidations"][0]["evidenceGrade"])
        self.assertFalse(payload["taskValidations"][0]["realTaskEvidenceCreated"])
        self.assertIn("Task Validation Evidence", html)
        self.assertNotIn("validated_for_exact_context", json.dumps(payload))

    def test_store_and_dashboard_surface_task_protocol_as_handoff(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            paths = _specialist_protocol_artifact_paths(temp_path)
            db_path = temp_path / "mindfront.sqlite"
            result = store_artifact_set(
                db_path,
                analysis_path=paths["analysis"],
                task_protocol_path=paths["task_protocol"],
            )
            build_static_dashboard(db_path, temp_path / "dashboard")
            payload = json.loads((temp_path / "dashboard" / "mindfront-dashboard.json").read_text(encoding="utf-8"))
            html = (temp_path / "dashboard" / "index.html").read_text(encoding="utf-8")

        self.assertIn("task_protocol", result["storedArtifactTypes"])
        self.assertEqual(1, payload["summary"]["taskProtocolCount"])
        self.assertEqual(paths["protocol_id"], payload["taskProtocols"][0]["protocolId"])
        self.assertGreater(payload["taskProtocols"][0]["taskCount"], 0)
        self.assertFalse(payload["taskProtocols"][0]["marketEvidenceCreated"])
        self.assertTrue(payload["taskProtocols"][0]["notMarketEvidence"])
        self.assertEqual("read", payload["taskProtocols"][0]["readStatus"])
        self.assertIn("Task Observation Protocols", html)
        self.assertIn(
            "documentation_task_observation_protocol",
            {item["label"] for item in payload["evidenceSeparation"]},
        )
        self.assertEqual(0, payload["summary"]["taskValidationSignalCount"])

    def test_store_rejects_protocol_marked_as_market_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            paths = _specialist_protocol_artifact_paths(temp_path)
            protocol = json.loads(paths["task_protocol"].read_text(encoding="utf-8"))
            protocol["notMarketEvidence"] = False
            bad_path = temp_path / "bad-protocol.json"
            bad_path.write_text(json.dumps(protocol), encoding="utf-8")

            with self.assertRaises(StoreBlockedError) as raised:
                store_artifact_set(
                    temp_path / "mindfront.sqlite",
                    analysis_path=paths["analysis"],
                    task_protocol_path=bad_path,
                )

        self.assertIn("evidence_boundary_violation", {reason["code"] for reason in raised.exception.reasons})

    def test_store_and_dashboard_count_real_task_observation_signals_separately(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            paths = _specialist_artifact_paths(temp_path, observation_source="real_task_observation")
            db_path = temp_path / "mindfront.sqlite"
            store_artifact_set(
                db_path,
                analysis_path=paths["analysis"],
                task_validation_path=paths["task_validation"],
            )
            history = list_analysis_history(db_path)
            comparison = compare_analysis_history(db_path)
            build_static_dashboard(db_path, temp_path / "dashboard")
            payload = json.loads((temp_path / "dashboard" / "mindfront-dashboard.json").read_text(encoding="utf-8"))

        self.assertEqual(0, history["runs"][0]["validatedSignalCount"])
        self.assertGreater(history["runs"][0]["taskValidationSignalCount"], 0)
        self.assertEqual(1, comparison["taskValidationSummary"]["realTaskEvidenceRunCount"])
        self.assertEqual(0, comparison["taskValidationSummary"]["syntheticFixtureRunCount"])
        self.assertGreater(payload["summary"]["taskValidationSignalCount"], 0)
        self.assertEqual("real_task_observation", payload["taskValidations"][0]["observationSource"])
        self.assertEqual("small_user_test", payload["taskValidations"][0]["evidenceBasis"])
        self.assertEqual("exact_context_directional", payload["taskValidations"][0]["evidenceGrade"])
        self.assertTrue(payload["taskValidations"][0]["realTaskEvidenceCreated"])

    def test_store_rejects_malformed_task_validation_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            paths = _specialist_artifact_paths(temp_path)
            validation = json.loads(paths["task_validation"].read_text(encoding="utf-8"))
            validation["realTaskEvidenceCreated"] = True
            validation["evidenceBasis"] = "small_user_test"
            bad_path = temp_path / "bad-task-validation.json"
            bad_path.write_text(json.dumps(validation), encoding="utf-8")

            with self.assertRaises(StoreBlockedError) as raised:
                store_artifact_set(
                    temp_path / "mindfront.sqlite",
                    analysis_path=paths["analysis"],
                    task_validation_path=bad_path,
                )

        reason_codes = {reason["code"] for reason in raised.exception.reasons}
        self.assertIn("real_task_evidence_mismatch", reason_codes)
        self.assertIn("evidence_basis_mismatch", reason_codes)

    def test_store_export_and_delete_run(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            paths = _sample_artifact_paths(temp_path)
            db_path = temp_path / "mindfront.sqlite"
            result = store_artifact_set(db_path, analysis_path=paths["analysis"], stress_path=paths["stress"])
            export_path = export_store(db_path, temp_path / "export")
            export_payload = json.loads(export_path.read_text(encoding="utf-8"))
            delete_result = delete_run(db_path, result["storedRunId"])
            history = list_analysis_history(db_path)

        self.assertEqual("history_store_export", export_payload["artifactType"])
        self.assertIn("not full raw source text", export_payload["dataBoundary"])
        self.assertNotIn("sourceText", json.dumps(export_payload))
        self.assertEqual(0, delete_result["remainingRunCount"])
        self.assertEqual(0, history["runCount"])

    def test_stale_state_check_detects_changed_artifact_hashes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            paths = _sample_artifact_paths(temp_path)
            db_path = temp_path / "mindfront.sqlite"
            store_artifact_set(db_path, analysis_path=paths["analysis"], stress_path=paths["stress"])
            before = refresh_stale_state(db_path)
            paths["analysis"].write_text(paths["analysis"].read_text(encoding="utf-8") + "\n", encoding="utf-8")
            after = refresh_stale_state(db_path)
            history = list_analysis_history(db_path)

        self.assertEqual(0, before["staleRunCount"])
        self.assertEqual(1, after["staleRunCount"])
        self.assertEqual("stale", history["runs"][0]["staleState"])
        self.assertEqual("artifact_hash_changed", after["runs"][0]["reasons"][0]["code"])

    def test_cli_store_and_dashboard_flow(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            paths = _sample_artifact_paths(temp_path)
            db_path = temp_path / "mindfront.sqlite"
            dashboard_dir = temp_path / "dashboard"
            env = dict(os.environ)
            env["PYTHONPATH"] = str(SRC)

            init = _run_cli(env, ["store", "init", "--db", str(db_path)])
            ingest = _run_cli(
                env,
                [
                    "store",
                    "ingest",
                    "--db",
                    str(db_path),
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
                    "--report",
                    str(paths["report"]),
                ],
            )
            listed = _run_cli(env, ["store", "list-analyses", "--db", str(db_path)])
            compared = _run_cli(env, ["store", "compare", "--db", str(db_path)])
            stale = _run_cli(env, ["store", "check-stale", "--db", str(db_path)])
            dashboard = _run_cli(env, ["dashboard", "build", "--db", str(db_path), "--output", str(dashboard_dir)])
            improvement = _run_cli(
                env,
                [
                    "improvement-plan",
                    "--db",
                    str(db_path),
                    "--output",
                    str(temp_path / "improvement"),
                ],
            )
            dashboard_exists = (dashboard_dir / "index.html").exists()
            improvement_exists = (temp_path / "improvement" / "mindfront-improvement-plan.json").exists()

        self.assertEqual(0, init.returncode, init.stderr)
        self.assertEqual(0, ingest.returncode, ingest.stderr)
        self.assertEqual(0, listed.returncode, listed.stderr)
        self.assertEqual(0, compared.returncode, compared.stderr)
        self.assertEqual(0, stale.returncode, stale.stderr)
        self.assertEqual(0, dashboard.returncode, dashboard.stderr)
        self.assertEqual(0, improvement.returncode, improvement.stderr)
        self.assertIn("history_analysis_list", listed.stdout)
        self.assertIn("history_comparison_report", compared.stdout)
        self.assertIn("history_stale_state_check", stale.stdout)
        self.assertIn("Mindfront improvement plan written", improvement.stdout)
        self.assertTrue(dashboard_exists)
        self.assertTrue(improvement_exists)


def _run_cli(env: dict[str, str], args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-B", "-m", "mindfront.cli", *args],
        check=False,
        env=env,
        capture_output=True,
        text=True,
    )


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
    research_path = write_research_plan(research, root / "research")[0]
    report = build_report_bundle(
        analysis_path,
        config_root=PROJECT / "config",
        variants_path=variants_path,
        comparison_path=comparison_path,
        stress_path=stress_path,
        research_plan_path=research_path,
    )
    report_path = write_report_bundle(report, root / "report")[0]
    return {
        "analysis": analysis_path,
        "variants": variants_path,
        "comparison": comparison_path,
        "stress": stress_path,
        "research": research_path,
        "report": report_path,
    }


def _specialist_artifact_paths(root: Path, *, observation_source: str = "synthetic_fixture") -> dict[str, Path]:
    analysis = analyze_message_brief(
        PROJECT / "examples" / "briefs" / "specialist-documentation-brief.json",
        config_root=PROJECT / "config",
    )
    analysis_path = write_analysis_report(analysis, root / "specialist-analysis.json")
    task_input = json.loads(
        (PROJECT / "examples" / "task-validation" / "specialist-documentation-task-validation.json").read_text(
            encoding="utf-8"
        )
    )
    task_input["observationSource"] = observation_source
    task_input_path = root / f"specialist-task-validation-{observation_source}.json"
    task_input_path.write_text(json.dumps(task_input), encoding="utf-8")
    task_validation = build_task_validation_result(
        task_input_path,
        analysis_path=analysis_path,
    )
    task_validation_path = write_task_validation_result(task_validation, root / "task-validation")
    return {
        "analysis": analysis_path,
        "task_validation": task_validation_path,
    }


def _specialist_protocol_artifact_paths(root: Path) -> dict[str, Path | str]:
    analysis = analyze_message_brief(
        PROJECT / "examples" / "briefs" / "specialist-documentation-brief.json",
        config_root=PROJECT / "config",
    )
    analysis_path = write_analysis_report(analysis, root / "specialist-analysis.json")
    research = build_research_plan(analysis_path)
    research_path = write_research_plan(research, root / "research")[0]
    protocol = build_task_observation_protocol(analysis_path, research_plan_path=research_path)
    protocol_path = write_task_observation_protocol(protocol, root / "task-protocol")[0]
    return {
        "analysis": analysis_path,
        "research": research_path,
        "task_protocol": protocol_path,
        "protocol_id": protocol["protocolId"],
    }


if __name__ == "__main__":
    unittest.main()

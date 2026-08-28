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
from mindfront.stress import StressTestBlockedError, run_reader_stress_test, write_stress_report
from test_analysis import _specialist_documentation_brief


class StressTests(unittest.TestCase):
    def test_reader_stress_test_marks_everything_simulated(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            analysis = analyze_message_brief(
                PROJECT / "examples" / "briefs" / "sample-message-brief.json",
                config_root=PROJECT / "config",
            )
            analysis_path = write_analysis_report(analysis, Path(temp_dir) / "analysis.json")
            report = run_reader_stress_test(analysis_path, config_root=PROJECT / "config")

        self.assertEqual("reader_stress_test_report", report["artifactType"])
        self.assertTrue(report["notMarketEvidence"])
        self.assertFalse(report["marketEvidenceCreated"])
        self.assertEqual("synthetic_reader_stress_test", report["evidenceBasis"])
        self.assertTrue(report["results"])
        self.assertTrue(all(result["notMarketEvidence"] for result in report["results"]))
        self.assertTrue(all(result["evidenceBasis"] == "synthetic_reader_stress_test" for result in report["results"]))
        self.assertNotIn("real_user_data", json.dumps(report))
        self.assertNotIn("validated_for_exact_context", json.dumps(report))

    def test_reader_stress_test_filters_lenses(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            analysis = analyze_message_brief(
                PROJECT / "examples" / "briefs" / "sample-message-brief.json",
                config_root=PROJECT / "config",
            )
            analysis_path = write_analysis_report(analysis, Path(temp_dir) / "analysis.json")
            report = run_reader_stress_test(
                analysis_path,
                config_root=PROJECT / "config",
                lens_ids=["lens-technical-evaluator-proof"],
        )

        self.assertEqual(["lens-technical-evaluator-proof"], [result["lensId"] for result in report["results"]])

    def test_specialist_specialist_lens_observes_documentation_friction(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            brief_path = temp_path / "specialist-doc-brief.json"
            brief_path.write_text(json.dumps(_specialist_documentation_brief()), encoding="utf-8")
            analysis = analyze_message_brief(brief_path, config_root=PROJECT / "config")
            analysis_path = write_analysis_report(analysis, temp_path / "analysis.json")
            report = run_reader_stress_test(
                analysis_path,
                config_root=PROJECT / "config",
                lens_ids=["lens-specialist-bandwidth"],
            )

        self.assertEqual(["lens-specialist-bandwidth"], [result["lensId"] for result in report["results"]])
        observed_signals = {item["signal"] for item in report["results"][0]["observedFriction"]}
        self.assertIn("hidden learning tax", observed_signals)
        self.assertIn("missing fast path", observed_signals)
        self.assertIn("missing evidence boundary", observed_signals)
        self.assertTrue(report["results"][0]["notMarketEvidence"])

    def test_reader_stress_test_rejects_unknown_lens(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            analysis = analyze_message_brief(
                PROJECT / "examples" / "briefs" / "sample-message-brief.json",
                config_root=PROJECT / "config",
            )
            analysis_path = write_analysis_report(analysis, Path(temp_dir) / "analysis.json")
            with self.assertRaises(StressTestBlockedError) as raised:
                run_reader_stress_test(analysis_path, config_root=PROJECT / "config", lens_ids=["missing-lens"])

        self.assertEqual("unknown_lens", raised.exception.reasons[0]["code"])

    def test_cli_reader_stress_test_writes_json_report(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            analysis = analyze_message_brief(
                PROJECT / "examples" / "briefs" / "sample-message-brief.json",
                config_root=PROJECT / "config",
            )
            analysis_path = write_analysis_report(analysis, temp_path / "analysis.json")
            output_path = temp_path / "stress.json"
            env = dict(os.environ)
            env["PYTHONPATH"] = str(SRC)
            completed = subprocess.run(
                [
                    sys.executable,
                    "-B",
                    "-m",
                    "mindfront.cli",
                    "reader-stress-test",
                    "--analysis",
                    str(analysis_path),
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

        self.assertEqual("reader_stress_test_report", payload["artifactType"])
        self.assertTrue(payload["outputHash"].startswith("sha256:"))


if __name__ == "__main__":
    unittest.main()

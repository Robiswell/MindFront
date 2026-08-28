from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SRC = REPO_ROOT / "backend" / "src"
EXAMPLES = REPO_ROOT / "examples" / "workplace-assistance"
POLICY = REPO_ROOT / "config" / "workplace-assistance-policy.json"


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(SRC)
    return subprocess.run(
        [sys.executable, "-B", "-m", "mindfront.cli", *args],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


@unittest.skipUnless(os.name == "nt", "Current-user DPAPI is Windows-only.")
class WorkplaceAssistanceCliTests(unittest.TestCase):
    def test_profile_upsert_and_each_mode_use_the_private_fast_path(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "runtime-data"
            store = root / "self-profile.vault"
            created = _run(
                "assist",
                "profile",
                "upsert",
                "--input",
                str(EXAMPLES / "synthetic-self-profile.json"),
                "--store",
                str(store),
            )
            self.assertEqual(0, created.returncode, created.stderr)
            self.assertTrue(store.is_file())
            context = _run(
                "assist",
                "profile",
                "context",
                "--store",
                str(store),
            )
            self.assertEqual(0, context.returncode, context.stderr)
            context_payload = json.loads(context.stdout)
            self.assertEqual(
                "self_workplace_assistance_context",
                context_payload["artifactType"],
            )
            self.assertTrue(context_payload["privateArtifact"])
            self.assertFalse(context_payload["automaticSendingAllowed"])

            for command, fixture in (
                ("preflight", "synthetic-preflight.json"),
                ("interpret", "synthetic-interpret.json"),
                ("debrief", "synthetic-debrief.json"),
                ("career-review", "synthetic-career-review.json"),
            ):
                output = root / command
                completed = _run(
                    "assist",
                    command,
                    "--input",
                    str(EXAMPLES / fixture),
                    "--self-store",
                    str(store),
                    "--policy",
                    str(POLICY),
                    "--output",
                    str(output),
                )
                self.assertEqual(0, completed.returncode, completed.stderr)
                payload = json.loads(
                    (output / "workplace-assistance-result.json").read_text(
                        encoding="utf-8"
                    )
                )
                self.assertTrue(payload["privateArtifact"])
                self.assertTrue(payload["humanReviewRequired"])
                self.assertFalse(payload["automaticSendingAllowed"])
                self.assertFalse(payload["coworkerEvaluationAllowed"])
                self.assertFalse(payload["promotionPredictionCreated"])

    def test_mode_mismatch_fails_before_private_store_lookup(self) -> None:
        completed = _run(
            "assist",
            "interpret",
            "--input",
            str(EXAMPLES / "synthetic-preflight.json"),
            "--json-errors",
        )

        self.assertEqual(1, completed.returncode)
        payload = json.loads(completed.stdout)
        self.assertEqual("assistance_mode_mismatch", payload["errors"][0]["code"])

    def test_assistance_dry_run_does_not_write_output(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "runtime-data"
            store = root / "self-profile.vault"
            created = _run(
                "assist",
                "profile",
                "upsert",
                "--input",
                str(EXAMPLES / "synthetic-self-profile.json"),
                "--store",
                str(store),
            )
            self.assertEqual(0, created.returncode, created.stderr)
            output = root / "planned"

            completed = _run(
                "assist",
                "preflight",
                "--input",
                str(EXAMPLES / "synthetic-preflight.json"),
                "--self-store",
                str(store),
                "--policy",
                str(POLICY),
                "--output",
                str(output),
                "--dry-run",
            )

            self.assertEqual(0, completed.returncode, completed.stderr)
            self.assertFalse(output.exists())
            payload = json.loads(completed.stdout)
            self.assertEqual("dry_run", payload["status"])
            self.assertTrue(payload["details"]["humanReviewRequired"])
            self.assertFalse(payload["details"]["automaticSendingAllowed"])

    def test_cli_rejects_private_store_and_output_outside_runtime_data(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            unsafe_store = root / "self-profile.vault"
            blocked_store = _run(
                "assist",
                "profile",
                "upsert",
                "--input",
                str(EXAMPLES / "synthetic-self-profile.json"),
                "--store",
                str(unsafe_store),
                "--json-errors",
            )
            self.assertEqual(1, blocked_store.returncode)
            self.assertEqual(
                "private_runtime_path_required",
                json.loads(blocked_store.stdout)["errors"][0]["code"],
            )

            private_root = root / "runtime-data"
            store = private_root / "self-profile.vault"
            created = _run(
                "assist",
                "profile",
                "upsert",
                "--input",
                str(EXAMPLES / "synthetic-self-profile.json"),
                "--store",
                str(store),
            )
            self.assertEqual(0, created.returncode, created.stderr)
            unsafe_output = root / "outside-private-root"
            blocked_output = _run(
                "assist",
                "preflight",
                "--input",
                str(EXAMPLES / "synthetic-preflight.json"),
                "--self-store",
                str(store),
                "--policy",
                str(POLICY),
                "--output",
                str(unsafe_output),
                "--json-errors",
            )
            self.assertEqual(1, blocked_output.returncode)
            self.assertEqual(
                "private_runtime_path_required",
                json.loads(blocked_output.stdout)["errors"][0]["code"],
            )
            self.assertFalse(unsafe_output.exists())


if __name__ == "__main__":
    unittest.main()

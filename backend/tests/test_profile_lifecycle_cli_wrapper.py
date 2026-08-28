from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from mindfront import cli
from mindfront.interaction_profiles import InteractionProfileBlockedError


def test_profile_context_maps_unverifiable_vault_to_source_mismatch(
    monkeypatch,
    capsys,
) -> None:
    def fail_current_bundle(_vault: Path, _name: str) -> dict:
        raise InteractionProfileBlockedError(
            [
                {
                    "code": "corpus_person_not_found",
                    "path": "recipient",
                    "message": "No current source messages remain.",
                }
            ]
        )

    monkeypatch.setattr(cli, "derive_observation_bundle", fail_current_bundle)

    exit_code = cli.main(
        [
            "profile",
            "context",
            "--store",
            "profiles.vault",
            "--vault",
            "communications.vault",
            "--name",
            "Exact Name",
            "--json-errors",
        ]
    )
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 1
    assert payload["errors"][0]["code"] == "source_mismatch"
    assert "No current source messages remain" not in json.dumps(payload)


def test_profile_context_checks_current_source_bundle_before_guidance(
    monkeypatch,
    capsys,
) -> None:
    current_bundle = {
        "bundleId": "comms-bundle-current-source-001",
        "subject": {"identityFingerprint": "sha256:" + "a" * 64},
    }
    received: dict[str, object] = {}

    monkeypatch.setattr(
        cli,
        "derive_observation_bundle",
        lambda _vault, _name: current_bundle,
    )

    def fake_get_profile(
        _store: Path,
        display_name: str,
        *,
        include_collecting: bool = False,
        expected_source_bundle: dict | None = None,
    ) -> dict:
        received["display_name"] = display_name
        received["include_collecting"] = include_collecting
        received["source_bundle"] = expected_source_bundle
        return {"profileId": "profile-1"}

    monkeypatch.setattr(cli, "get_interaction_profile", fake_get_profile)
    monkeypatch.setattr(
        cli,
        "profile_guidance",
        lambda _profile, context=None: {
            "artifactType": "interaction_assistance_guidance",
            "contextMatched": True,
            "matchedContext": context,
        },
    )

    exit_code = cli.main(
        [
            "profile",
            "context",
            "--store",
            "profiles.vault",
            "--vault",
            "communications.vault",
            "--name",
            "Exact Name",
            "--context",
            "executive_update",
        ]
    )
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["contextMatched"] is True
    assert received["display_name"] == "Exact Name"
    assert received["source_bundle"] is current_bundle


def test_wrapper_refreshes_once_then_has_bounded_unprofiled_fallback() -> None:
    wrapper = Path(
        "skills/mindfront/scripts/run_mindfront_workflow.ps1"
    ).read_text(encoding="utf-8")

    assert "[string]$CommunicationVaultPath" in wrapper
    assert (
        'Join-Path $repoRoot "runtime-data\\interaction-communications.vault"'
        in wrapper
    )
    assert '"--vault", $VaultPath' in wrapper
    assert "mindfront.cli corpus refresh-profile" in wrapper
    assert wrapper.count("Invoke-ProfileCliCheck `") == 2
    assert "continuing unprofiled; source coverage remains bounded" in wrapper
    assert "The profile preflight for" not in wrapper
    assert "throw" not in wrapper.split(
        "Mindfront named-recipient profile fallback:", 1
    )[1].split("}", 1)[0]


def test_wrapper_keeps_exact_name_pairing_and_private_output_boundary() -> None:
    wrapper = Path(
        "skills/mindfront/scripts/run_mindfront_workflow.ps1"
    ).read_text(encoding="utf-8")

    assert '$hasRecipientName -ne $hasProfileStorePath' in wrapper
    assert '$hasCommunicationVaultPath -and -not $hasRecipientName' in wrapper
    assert '"--name",' in wrapper
    assert "$RecipientName" not in wrapper.split(
        "Mindfront named-recipient profile fallback:", 1
    )[1].split(")", 1)[0]


@pytest.mark.skipif(shutil.which("powershell") is None, reason="PowerShell is required.")
@pytest.mark.parametrize(
    ("refresh_succeeds", "vault_available"),
    [(True, True), (False, True), (True, False)],
)
def test_wrapper_refresh_recheck_and_bounded_fallback_behavior(
    tmp_path: Path,
    refresh_succeeds: bool,
    vault_available: bool,
) -> None:
    fake_cli = tmp_path / "fake_mindfront.py"
    invocation_log = tmp_path / "invocations.jsonl"
    fake_python = tmp_path / "fake-python.cmd"
    profile_store = tmp_path / "profiles.vault"
    communication_vault = tmp_path / "communications.vault"
    output_root = tmp_path / "workflow-output"
    profile_store.write_text("placeholder", encoding="utf-8")
    if vault_available:
        communication_vault.write_text("placeholder", encoding="utf-8")
    fake_cli.write_text(
        """
import json
import sys
from pathlib import Path

log_path = Path(sys.argv[1])
refresh_succeeds = sys.argv[2] == "true"
args = sys.argv[3:]
existing = []
if log_path.exists():
    existing = [
        json.loads(line)
        for line in log_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
with log_path.open("a", encoding="utf-8") as stream:
    stream.write(json.dumps(args) + "\\n")

is_profile_check = "profile" in args and "context" in args
is_refresh = "corpus" in args and "refresh-profile" in args
prior_checks = sum(
    "profile" in item and "context" in item
    for item in existing
)
if is_profile_check and (not refresh_succeeds or prior_checks == 0):
    print(json.dumps({
        "status": "failed",
        "errors": [{"code": "profile_not_ready", "path": "profile", "message": "bounded"}],
    }))
    raise SystemExit(1)
if is_refresh and not refresh_succeeds:
    print(json.dumps({
        "status": "failed",
        "errors": [{"code": "refresh_failed", "path": "profile", "message": "bounded"}],
    }))
    raise SystemExit(1)
print(json.dumps({"status": "passed"}))
""".strip()
        + "\n",
        encoding="utf-8",
    )
    fake_python.write_text(
        "@echo off\r\n"
        f'"{sys.executable}" "{fake_cli}" "{invocation_log}" '
        f'{"true" if refresh_succeeds else "false"} %*\r\n'
        "exit /b %errorlevel%\r\n",
        encoding="ascii",
    )

    completed = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            "skills/mindfront/scripts/run_mindfront_workflow.ps1",
            "-BriefPath",
            "examples/briefs/sample-message-brief.json",
            "-OutputRoot",
            str(output_root),
            "-Python",
            str(fake_python),
            "-RecipientName",
            "Exact Name",
            "-ProfileStorePath",
            str(profile_store),
            "-CommunicationVaultPath",
            str(communication_vault),
            "-RecipientContext",
            "executive_update",
        ],
        cwd=Path(__file__).resolve().parents[2],
        check=False,
        capture_output=True,
        text=True,
    )
    invocations = [
        json.loads(line)
        for line in invocation_log.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    profile_checks = [
        item for item in invocations if "profile" in item and "context" in item
    ]
    refreshes = [
        item for item in invocations if "corpus" in item and "refresh-profile" in item
    ]
    analyze = next(item for item in invocations if "analyze" in item)

    assert completed.returncode == 0, completed.stderr
    if not vault_available:
        assert profile_checks == []
        assert refreshes == []
        assert "--profile-store" not in analyze
        assert "communication_vault_unavailable" in completed.stdout
        assert "continuing unprofiled; source coverage remains bounded" in completed.stdout
    else:
        assert len(profile_checks) == 2
        assert len(refreshes) == 1
        assert all("--vault" in item for item in profile_checks)
    if refresh_succeeds and vault_available:
        assert "--profile-store" in analyze
        assert "profile fallback" not in completed.stdout
    elif vault_available:
        assert "--profile-store" not in analyze
        assert "continuing unprofiled; source coverage remains bounded" in completed.stdout

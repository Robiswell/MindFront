from __future__ import annotations

import base64
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from mindfront.cli import main
from mindfront.vault_crypto import (
    CURRENT_ENCRYPTION,
    LEGACY_DPAPI_ENCRYPTION,
    VaultEncryptionError,
    decrypt_envelope,
    dpapi_protect,
    encrypt_payload,
    initialize_vault_key,
    inspect_vault,
    migrate_vault,
    vault_key_status,
)


ARTIFACT_TYPE = "mindfront_encrypted_profile_store"


def test_key_initialization_and_authenticated_round_trip(tmp_path: Path, monkeypatch) -> None:
    key_path = tmp_path / "shared.key"
    monkeypatch.setenv("MINDFRONT_VAULT_KEY_FILE", str(key_path))

    initialized = initialize_vault_key()
    envelope = encrypt_payload(b"private-value", artifact_type=ARTIFACT_TYPE)

    assert initialized["status"] == "ready"
    assert initialized["keyMaterialExposed"] is False
    assert envelope["encryption"] == CURRENT_ENCRYPTION
    assert "plaintextHash" not in envelope
    assert decrypt_envelope(envelope, expected_artifact_type=ARTIFACT_TYPE) == b"private-value"
    assert vault_key_status()["keyId"] == envelope["keyId"]


def test_wrong_local_key_fails_closed(tmp_path: Path, monkeypatch) -> None:
    first = tmp_path / "first.key"
    second = tmp_path / "second.key"
    monkeypatch.setenv("MINDFRONT_VAULT_KEY_FILE", str(first))
    initialize_vault_key()
    envelope = encrypt_payload(b"private-value", artifact_type=ARTIFACT_TYPE)

    monkeypatch.setenv("MINDFRONT_VAULT_KEY_FILE", str(second))
    initialize_vault_key()
    with pytest.raises(VaultEncryptionError) as exc:
        decrypt_envelope(envelope, expected_artifact_type=ARTIFACT_TYPE)

    assert exc.value.reasons[0]["code"] == "vault_key_mismatch"


def test_current_vault_is_readable_in_a_separate_process(tmp_path: Path, monkeypatch) -> None:
    key_path = tmp_path / "shared.key"
    envelope_path = tmp_path / "profile.vault"
    monkeypatch.setenv("MINDFRONT_VAULT_KEY_FILE", str(key_path))
    initialize_vault_key()
    envelope_path.write_text(
        json.dumps(encrypt_payload(b"cross-task", artifact_type=ARTIFACT_TYPE)),
        encoding="utf-8",
    )
    environment = os.environ.copy()
    environment["MINDFRONT_VAULT_KEY_FILE"] = str(key_path)
    environment["PYTHONPATH"] = str(Path(__file__).resolve().parents[1] / "src")
    code = (
        "import json; from pathlib import Path; "
        "from mindfront.vault_crypto import decrypt_envelope; "
        f"e=json.loads(Path(r'{envelope_path}').read_text(encoding='utf-8')); "
        f"print(decrypt_envelope(e, expected_artifact_type='{ARTIFACT_TYPE}').decode())"
    )
    completed = subprocess.run(
        [sys.executable, "-c", code],
        check=True,
        capture_output=True,
        text=True,
        env=environment,
    )

    assert completed.stdout.strip() == "cross-task"


def test_vault_cli_initializes_inspects_and_reopens_current_vault(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    key_path = tmp_path / "shared.key"
    vault_path = tmp_path / "profile.vault"
    monkeypatch.setenv("MINDFRONT_VAULT_KEY_FILE", str(key_path))

    assert main(["vault", "init-key", "--key-file", str(key_path)]) == 0
    initialized = json.loads(capsys.readouterr().out)
    assert initialized["keyMaterialExposed"] is False

    vault_path.write_text(
        json.dumps(encrypt_payload(b"cli-private-value", artifact_type=ARTIFACT_TYPE)),
        encoding="utf-8",
    )
    assert main(["vault", "inspect", "--path", str(vault_path)]) == 0
    inspected = json.loads(capsys.readouterr().out)
    assert inspected["current"] is True
    assert inspected["payloadExposed"] is False

    assert main(["vault", "migrate", "--path", str(vault_path)]) == 0
    migrated = json.loads(capsys.readouterr().out)
    assert migrated["status"] == "already_current"
    assert migrated["payloadExposed"] is False


def test_vault_cli_fails_closed_without_key(tmp_path: Path, capsys) -> None:
    missing = tmp_path / "missing.key"

    assert main(["vault", "key-status", "--key-file", str(missing), "--json-errors"]) == 1
    blocked = json.loads(capsys.readouterr().out)
    assert blocked["status"] == "blocked"
    assert blocked["payloadExposed"] is False
    assert blocked["reasons"][0]["code"] == "vault_key_missing"


@pytest.mark.skipif(os.name != "nt", reason="Legacy DPAPI migration is Windows-only.")
def test_legacy_dpapi_vault_migrates_with_backup(tmp_path: Path, monkeypatch) -> None:
    key_path = tmp_path / "shared.key"
    vault_path = tmp_path / "legacy.vault"
    monkeypatch.setenv("MINDFRONT_VAULT_KEY_FILE", str(key_path))
    initialize_vault_key()
    payload = b'{"artifactType":"mindfront_private_interaction_profile_store"}'
    encrypted = dpapi_protect(payload)
    vault_path.write_text(
        json.dumps(
            {
                "artifactType": ARTIFACT_TYPE,
                "schemaVersion": 1,
                "encryption": LEGACY_DPAPI_ENCRYPTION,
                "ciphertextHash": "sha256:" + __import__("hashlib").sha256(encrypted).hexdigest(),
                "plaintextHash": "sha256:" + __import__("hashlib").sha256(payload).hexdigest(),
                "payloadBase64": base64.b64encode(encrypted).decode("ascii"),
            }
        ),
        encoding="utf-8",
    )

    result = migrate_vault(vault_path)
    status = inspect_vault(vault_path)

    assert result["status"] == "migrated"
    assert result["legacyBackup"]
    assert Path(result["legacyBackup"]).exists()
    assert status["encryption"] == CURRENT_ENCRYPTION
    assert decrypt_envelope(
        json.loads(vault_path.read_text(encoding="utf-8")),
        expected_artifact_type=ARTIFACT_TYPE,
    ) == payload

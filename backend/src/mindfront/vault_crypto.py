"""Cross-task encryption for Mindfront private vaults.

The original stores used Windows current-user DPAPI directly on every vault.
Codex desktop tasks can execute under different sandbox logon contexts, which
made a vault created by one task unreadable to another task.  The current
format uses one installation-local AES-256-GCM key kept outside the repository.
The key file is protected by filesystem permissions and is shared with the
local Codex sandbox group when that group exists.

Legacy DPAPI envelopes remain decryptable in the Windows context that created
them so they can be migrated without exporting plaintext.
"""

from __future__ import annotations

import base64
import csv
import ctypes
import hashlib
import json
import os
import secrets
import shutil
import subprocess
import tempfile
from ctypes import wintypes
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


CURRENT_ENCRYPTION = "aes_256_gcm_local_key_v1"
LEGACY_DPAPI_ENCRYPTION = "windows_dpapi_current_user"
KEY_ARTIFACT_TYPE = "mindfront_private_vault_key"
KEY_ALGORITHM = "AES-256-GCM"
KEY_ENVIRONMENT_VARIABLE = "MINDFRONT_VAULT_KEY_FILE"
KNOWN_ENCRYPTED_ARTIFACT_TYPES = {
    "mindfront_encrypted_communication_vault",
    "mindfront_encrypted_profile_store",
    "mindfront_encrypted_self_assistance_profile_store",
}


class VaultEncryptionError(Exception):
    """Raised when a private key or encrypted envelope cannot be used safely."""

    def __init__(self, reasons: list[dict[str, str]]):
        self.reasons = reasons
        super().__init__("Mindfront private vault encryption operation blocked.")


def default_vault_key_path() -> Path:
    """Return the stable key path shared by local Codex tasks."""

    configured = os.environ.get(KEY_ENVIRONMENT_VARIABLE, "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    codex_home = os.environ.get("CODEX_HOME", "").strip()
    if codex_home:
        root = Path(codex_home).expanduser()
    else:
        user_profile = os.environ.get("USERPROFILE", "").strip()
        root = Path(user_profile) / ".codex" if user_profile else Path.home() / ".codex"
    return (root / "mindfront" / "private-vault.key").resolve()


def initialize_vault_key(key_path: str | Path | None = None) -> dict[str, Any]:
    """Create or validate the installation-local key without returning it."""

    path = Path(key_path).expanduser().resolve() if key_path else default_vault_key_path()
    if path.exists():
        key_document, _ = _load_key_document(path)
        return _key_status_payload(path, key_document, created=False)

    path.parent.mkdir(parents=True, exist_ok=True)
    key = secrets.token_bytes(32)
    document = {
        "artifactType": KEY_ARTIFACT_TYPE,
        "schemaVersion": 1,
        "algorithm": KEY_ALGORITHM,
        "keyId": _key_id(key),
        "keyBase64": base64.b64encode(key).decode("ascii"),
        "createdAt": _now(),
        "dataBoundary": (
            "Installation-local Mindfront encryption key. Keep outside repositories, backups, "
            "messages, reports, and shareable artifacts."
        ),
    }
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "x",
            encoding="utf-8",
            newline="\n",
            delete=False,
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
        ) as handle:
            json.dump(document, handle, indent=2, sort_keys=True)
            handle.write("\n")
            temporary = Path(handle.name)
        os.replace(temporary, path)
        _restrict_key_permissions(path)
    except Exception as exc:
        if temporary is not None and temporary.exists():
            temporary.unlink(missing_ok=True)
        if path.exists():
            path.unlink(missing_ok=True)
        if isinstance(exc, VaultEncryptionError):
            raise
        raise VaultEncryptionError(
            [_reason("vault_key_initialization_failed", str(path), str(exc))]
        ) from exc
    return _key_status_payload(path, document, created=True)


def vault_key_status(key_path: str | Path | None = None) -> dict[str, Any]:
    """Validate the configured key and return only non-secret metadata."""

    path = Path(key_path).expanduser().resolve() if key_path else default_vault_key_path()
    document, _ = _load_key_document(path)
    return _key_status_payload(path, document, created=False)


def encrypt_payload(
    payload: bytes,
    *,
    artifact_type: str,
    schema_version: int = 1,
    key_path: str | Path | None = None,
) -> dict[str, Any]:
    """Build an authenticated encrypted envelope for one private payload."""

    if artifact_type not in KNOWN_ENCRYPTED_ARTIFACT_TYPES:
        raise VaultEncryptionError(
            [_reason("unsupported_vault_artifact", artifact_type, "Encrypted artifact type is not allowed.")]
        )
    path = Path(key_path).expanduser().resolve() if key_path else default_vault_key_path()
    if not path.exists():
        initialize_vault_key(path)
    key_document, key = _load_key_document(path)
    nonce = secrets.token_bytes(12)
    aad = _associated_data(artifact_type, schema_version)
    ciphertext = AESGCM(key).encrypt(nonce, payload, aad)
    return {
        "artifactType": artifact_type,
        "schemaVersion": schema_version,
        "encryption": CURRENT_ENCRYPTION,
        "keyId": key_document["keyId"],
        "nonceBase64": base64.b64encode(nonce).decode("ascii"),
        "ciphertextHash": _sha256_bytes(ciphertext),
        "payloadBase64": base64.b64encode(ciphertext).decode("ascii"),
    }


def decrypt_envelope(
    envelope: dict[str, Any],
    *,
    expected_artifact_type: str,
    key_path: str | Path | None = None,
) -> bytes:
    """Decrypt a current envelope or a legacy current-user DPAPI envelope."""

    if envelope.get("artifactType") != expected_artifact_type:
        raise VaultEncryptionError(
            [_reason("unexpected_vault_artifact", "artifactType", "Encrypted artifact type does not match.")]
        )
    encryption = envelope.get("encryption")
    try:
        ciphertext = base64.b64decode(envelope["payloadBase64"], validate=True)
    except (KeyError, TypeError, ValueError) as exc:
        raise VaultEncryptionError(
            [_reason("invalid_vault_envelope", "payloadBase64", "Encrypted payload is missing or invalid.")]
        ) from exc

    ciphertext_hash = envelope.get("ciphertextHash")
    if ciphertext_hash and ciphertext_hash != _sha256_bytes(ciphertext):
        raise VaultEncryptionError(
            [_reason("vault_ciphertext_hash_mismatch", "ciphertextHash", "Encrypted payload hash mismatch.")]
        )

    if encryption == LEGACY_DPAPI_ENCRYPTION:
        payload = dpapi_unprotect(ciphertext)
    elif encryption == CURRENT_ENCRYPTION:
        path = Path(key_path).expanduser().resolve() if key_path else default_vault_key_path()
        key_document, key = _load_key_document(path)
        if envelope.get("keyId") != key_document["keyId"]:
            raise VaultEncryptionError(
                [
                    _reason(
                        "vault_key_mismatch",
                        str(path),
                        "The configured local key does not match this encrypted vault.",
                    )
                ]
            )
        try:
            nonce = base64.b64decode(envelope["nonceBase64"], validate=True)
        except (KeyError, TypeError, ValueError) as exc:
            raise VaultEncryptionError(
                [_reason("invalid_vault_envelope", "nonceBase64", "AES-GCM nonce is missing or invalid.")]
            ) from exc
        if len(nonce) != 12:
            raise VaultEncryptionError(
                [_reason("invalid_vault_nonce", "nonceBase64", "AES-GCM nonce must be 12 bytes.")]
            )
        try:
            payload = AESGCM(key).decrypt(
                nonce,
                ciphertext,
                _associated_data(expected_artifact_type, int(envelope.get("schemaVersion", 1))),
            )
        except InvalidTag as exc:
            raise VaultEncryptionError(
                [_reason("vault_authentication_failed", str(path), "Encrypted vault authentication failed.")]
            ) from exc
    else:
        raise VaultEncryptionError(
            [_reason("unsupported_vault_encryption", "encryption", f"Unsupported mode: {encryption!r}.")]
        )

    plaintext_hash = envelope.get("plaintextHash")
    if plaintext_hash and plaintext_hash != _sha256_bytes(payload):
        raise VaultEncryptionError(
            [_reason("vault_plaintext_hash_mismatch", "plaintextHash", "Decrypted payload hash mismatch.")]
        )
    return payload


def write_encrypted_payload(
    path: str | Path,
    payload: bytes,
    *,
    artifact_type: str,
    schema_version: int = 1,
    preserve_legacy_backup: bool = True,
) -> dict[str, Any]:
    """Atomically write a current envelope and preserve a legacy backup once."""

    destination = Path(path)
    envelope = encrypt_payload(
        payload,
        artifact_type=artifact_type,
        schema_version=schema_version,
    )
    backup_path: Path | None = None
    if destination.exists() and preserve_legacy_backup:
        try:
            existing = json.loads(destination.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            existing = {}
        if existing.get("encryption") == LEGACY_DPAPI_ENCRYPTION:
            backup_path = _legacy_backup_path(destination)
            shutil.copy2(destination, backup_path)

    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        newline="\n",
        delete=False,
        dir=destination.parent,
        prefix=f".{destination.name}.",
        suffix=".tmp",
    ) as handle:
        json.dump(envelope, handle, indent=2, sort_keys=True)
        handle.write("\n")
        temporary = Path(handle.name)
    os.replace(temporary, destination)
    return {
        "envelope": envelope,
        "legacyBackup": str(backup_path) if backup_path else None,
    }


def inspect_vault(path: str | Path) -> dict[str, Any]:
    """Return non-secret envelope metadata without decrypting the payload."""

    source = Path(path)
    try:
        envelope = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise VaultEncryptionError(
            [_reason("vault_envelope_unreadable", str(source), str(exc))]
        ) from exc
    return {
        "artifactType": "mindfront_vault_encryption_status",
        "schemaVersion": 1,
        "path": str(source),
        "encryptedArtifactType": envelope.get("artifactType"),
        "encryption": envelope.get("encryption"),
        "keyId": envelope.get("keyId"),
        "current": envelope.get("encryption") == CURRENT_ENCRYPTION,
        "payloadExposed": False,
    }


def migrate_vault(path: str | Path) -> dict[str, Any]:
    """Re-encrypt one known legacy envelope without exposing its plaintext."""

    source = Path(path)
    try:
        envelope = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise VaultEncryptionError(
            [_reason("vault_envelope_unreadable", str(source), str(exc))]
        ) from exc
    artifact_type = envelope.get("artifactType")
    if artifact_type not in KNOWN_ENCRYPTED_ARTIFACT_TYPES:
        raise VaultEncryptionError(
            [_reason("unsupported_vault_artifact", str(source), "Vault artifact type is not migratable.")]
        )
    previous_encryption = envelope.get("encryption")
    payload = decrypt_envelope(envelope, expected_artifact_type=artifact_type)
    if previous_encryption == CURRENT_ENCRYPTION:
        return {
            "artifactType": "mindfront_vault_migration_result",
            "schemaVersion": 1,
            "status": "already_current",
            "path": str(source),
            "previousEncryption": previous_encryption,
            "currentEncryption": CURRENT_ENCRYPTION,
            "legacyBackup": None,
            "payloadExposed": False,
        }
    write_result = write_encrypted_payload(
        source,
        payload,
        artifact_type=artifact_type,
        schema_version=int(envelope.get("schemaVersion", 1)),
    )
    return {
        "artifactType": "mindfront_vault_migration_result",
        "schemaVersion": 1,
        "status": "migrated",
        "path": str(source),
        "previousEncryption": previous_encryption,
        "currentEncryption": CURRENT_ENCRYPTION,
        "legacyBackup": write_result["legacyBackup"],
        "payloadExposed": False,
    }


class _DataBlob(ctypes.Structure):
    _fields_ = [
        ("cbData", wintypes.DWORD),
        ("pbData", ctypes.POINTER(ctypes.c_ubyte)),
    ]


def dpapi_protect(payload: bytes) -> bytes:
    """Protect a payload with legacy current-user DPAPI for migration tests."""

    if os.name != "nt":
        raise VaultEncryptionError(
            [_reason("legacy_dpapi_unavailable", "vault", "Legacy DPAPI is available only on Windows.")]
        )
    buffer = ctypes.create_string_buffer(payload)
    source = _DataBlob(len(payload), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
    destination = _DataBlob()
    if not ctypes.windll.crypt32.CryptProtectData(
        ctypes.byref(source),
        "Mindfront legacy private vault",
        None,
        None,
        None,
        0x1,
        ctypes.byref(destination),
    ):
        error = ctypes.WinError()
        raise VaultEncryptionError(
            [_reason("legacy_dpapi_encryption_failed", "vault", str(error))]
        ) from error
    try:
        return ctypes.string_at(destination.pbData, destination.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(destination.pbData)


def dpapi_unprotect(payload: bytes) -> bytes:
    """Decrypt a legacy current-user DPAPI payload."""

    if os.name != "nt":
        raise VaultEncryptionError(
            [_reason("legacy_dpapi_unavailable", "vault", "Legacy DPAPI is available only on Windows.")]
        )
    buffer = ctypes.create_string_buffer(payload)
    source = _DataBlob(len(payload), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
    destination = _DataBlob()
    if not ctypes.windll.crypt32.CryptUnprotectData(
        ctypes.byref(source),
        None,
        None,
        None,
        None,
        0x1,
        ctypes.byref(destination),
    ):
        error = ctypes.WinError()
        raise VaultEncryptionError(
            [
                _reason(
                    "legacy_dpapi_unreadable",
                    "vault",
                    "The legacy vault cannot be decrypted in this Windows logon context: " + str(error),
                )
            ]
        ) from error
    try:
        return ctypes.string_at(destination.pbData, destination.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(destination.pbData)


def _load_key_document(path: Path) -> tuple[dict[str, Any], bytes]:
    if not path.exists():
        raise VaultEncryptionError(
            [
                _reason(
                    "vault_key_missing",
                    str(path),
                    "Initialize the local Mindfront vault key before reading encrypted stores.",
                )
            ]
        )
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
        if document.get("artifactType") != KEY_ARTIFACT_TYPE:
            raise ValueError("unexpected key artifact type")
        if document.get("algorithm") != KEY_ALGORITHM:
            raise ValueError("unexpected key algorithm")
        key = base64.b64decode(document["keyBase64"], validate=True)
        if len(key) != 32:
            raise ValueError("AES-256-GCM key must be 32 bytes")
        if document.get("keyId") != _key_id(key):
            raise ValueError("key id mismatch")
        return document, key
    except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        raise VaultEncryptionError(
            [_reason("vault_key_unreadable", str(path), str(exc))]
        ) from exc


def _restrict_key_permissions(path: Path) -> None:
    if os.name != "nt":
        path.chmod(0o600)
        return
    try:
        identity_result = subprocess.run(
            ["whoami", "/user", "/fo", "csv", "/nh"],
            check=True,
            capture_output=True,
            text=True,
        )
        row = next(csv.reader([identity_result.stdout.strip()]))
        user_sid = row[1].strip()
        grants = [
            f"*{user_sid}:(F)",
            "*S-1-5-18:(F)",
            "*S-1-5-32-544:(F)",
        ]
        computer = os.environ.get("COMPUTERNAME", "").strip()
        if computer:
            sandbox_group = f"{computer}\\CodexSandboxUsers"
            group_check = subprocess.run(
                ["net", "localgroup", "CodexSandboxUsers"],
                capture_output=True,
                text=True,
            )
            if group_check.returncode == 0:
                grants.append(f"{sandbox_group}:(R)")
        subprocess.run(
            ["icacls.exe", str(path), "/inheritance:r", "/grant:r", *grants],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError, IndexError) as exc:
        raise VaultEncryptionError(
            [
                _reason(
                    "vault_key_permissions_failed",
                    str(path),
                    "Could not restrict the local vault key permissions: " + str(exc),
                )
            ]
        ) from exc


def _key_status_payload(path: Path, document: dict[str, Any], *, created: bool) -> dict[str, Any]:
    return {
        "artifactType": "mindfront_vault_key_status",
        "schemaVersion": 1,
        "status": "ready",
        "created": created,
        "path": str(path),
        "algorithm": document["algorithm"],
        "keyId": document["keyId"],
        "crossTaskReadable": True,
        "keyMaterialExposed": False,
    }


def _legacy_backup_path(path: Path) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    candidate = path.with_name(f"{path.name}.legacy-dpapi-{stamp}.bak")
    suffix = 1
    while candidate.exists():
        candidate = path.with_name(f"{path.name}.legacy-dpapi-{stamp}-{suffix}.bak")
        suffix += 1
    return candidate


def _associated_data(artifact_type: str, schema_version: int) -> bytes:
    return f"mindfront|{artifact_type}|{schema_version}|{CURRENT_ENCRYPTION}".encode("utf-8")


def _key_id(key: bytes) -> str:
    return _sha256_bytes(key)


def _sha256_bytes(value: bytes) -> str:
    return f"sha256:{hashlib.sha256(value).hexdigest()}"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _reason(code: str, path: str, message: str) -> dict[str, str]:
    return {"code": code, "path": path, "message": message}

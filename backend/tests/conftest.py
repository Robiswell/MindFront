from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def isolated_mindfront_vault_key(tmp_path, monkeypatch):
    """Keep unit-test encryption keys out of the user's real Codex home."""

    monkeypatch.setenv(
        "MINDFRONT_VAULT_KEY_FILE",
        str(tmp_path / "mindfront-test-private-vault.key"),
    )

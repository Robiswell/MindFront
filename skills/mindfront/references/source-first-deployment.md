# Source-First Deployment

Keep this repo as the source of truth.

## Repo-Local Use

Use `skills/mindfront` directly while the workflow is evolving. Do not copy partial skill edits into the global Codex skills directory.

The current operating surface includes project-local hooks, the repo-local skill, deterministic CLI workflows, the localhost GUI, first-party workplace assistance, and connected-source orchestration performed by Codex. The offline CLI and GUI do not call Teams or Outlook connectors themselves.

## Private Runtime Boundary

Never distribute `runtime-data`, encrypted profile or communication vaults, plaintext profile inputs, the installation-local key, local history databases, connector payloads, or generated private artifacts. Current vaults use AES-256-GCM with a key outside the repository at `%USERPROFILE%\.codex\mindfront\private-vault.key`; its restricted NTFS ACL makes the same vault readable across local Codex tasks. The vault and key remain personal installation artifacts and are not portable to another employee or device. Legacy DPAPI vaults may be migrated only from a Windows context that can decrypt them.

If a live connector succeeds but vault ingestion or decryption is unavailable, the retrieved context may guide only the current response and must remain transient. Do not represent it as persisted corpus coverage.

## Department Pilot

There is no one-click departmental installer yet. For an internal pilot:

1. Publish a sanitized internal Git repository from the verified source state.
2. Include `.codex`, `AGENTS.md`, `backend`, `config`, `docs`, `examples`, `frontend`, `project-tools`, `skills`, `.gitignore`, and `README.md`.
3. Exclude `runtime-data`, `test-output`, `docs-deliverables`, `generated-memes`, `.venv`, build output, local planning history, and personal task artifacts.
4. Replace user-specific absolute paths with `$env:USERPROFILE`-relative or repository-relative paths.
5. Have each employee create their own encrypted self profile from the synthetic template and connect only sources they are authorized to use.
6. Validate under a different Windows user account before calling the package portable.

A ZIP may be used for a bounded pilot, but an internal versioned Git repository is the maintained distribution path.

## Installing Later

Only install to the global Codex runtime after:

- CLI workflow passes verification.
- Artifact schemas are stable.
- Confidence labels and ethical boundaries are stable.
- The skill passes `quick_validate.py`.
- A source-to-runtime copy plan exists.

## Config Deployment

Do not hand-edit runtime config as the source of truth. If this moves into a configuration repo, deploy source-owned config files and wrappers through that repo's normal validation/deployment flow.

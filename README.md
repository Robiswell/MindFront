# Mindfront

Mindfront is a local-first toolkit for workplace communication support and evidence-bounded message review. It helps a person prepare, interpret, and debrief workplace interactions, improve drafts without losing their own voice, and review messages or documentation through a deterministic quality workflow.

Mindfront is designed as an assistive tool. It does not diagnose people, infer hidden motives as facts, evaluate coworkers, predict career outcomes, or send messages automatically.

## What it includes

- A simple local web interface for communication preparation, interpretation, debriefing, and message review.
- A deterministic Python CLI for validation, analysis, rewriting, comparison, reader stress testing, research planning, reports, and local history.
- Optional encrypted local vaults for self profiles and authorized communication context.
- A Codex skill and project hooks that route Mindfront requests while preserving human review and privacy boundaries.
- Synthetic examples and tests that contain no real workplace communications.

## Privacy model

Mindfront is local-first. Private runtime data is excluded from this repository and ignored by Git.

Never commit or distribute:

- `runtime-data/`
- encrypted profile or communication vaults
- local encryption keys
- connector exports or staging payloads
- generated private reports
- real workplace messages, names, email addresses, or identifiers

The offline CLI and GUI do not connect to Microsoft Teams, Outlook, or other cloud services. Any connector orchestration must be implemented separately and used only when the operator is authorized to process the source material under applicable law and organizational policy.

For internal email adapters, set the organization domain before importing data:

```powershell
$env:MINDFRONT_INTERNAL_EMAIL_DOMAIN = "example.org"
```

The default is `corp.example` so the included synthetic tests work without local configuration.

## Requirements

- Windows PowerShell or PowerShell 7
- Python 3.11 or later
- PyYAML 6.0.3
- cryptography 49.0.0

Codex Desktop users can also use the bundled Python runtime when available.

## Start the local GUI

From the repository root:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\project-tools\start-mindfront-gui.ps1
```

Mindfront binds to `127.0.0.1` by default and opens the local interface at port 8765.

To start it without opening a browser:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\project-tools\start-mindfront-gui.ps1 -NoBrowser
```

## Use the CLI

Set the source path for the current PowerShell session:

```powershell
$env:PYTHONPATH = ".\backend\src"
python -m mindfront.cli --help
```

Run the deterministic message workflow with the synthetic sample brief:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\skills\mindfront\scripts\run_mindfront_workflow.ps1 `
  -BriefPath .\examples\briefs\sample-message-brief.json `
  -OutputRoot .\test-output\sample-run
```

The workflow runs validation, analysis, rewrite generation, comparison, a synthetic reader stress test, a research plan, and report assembly. Synthetic and heuristic outputs are not market evidence, employee research, or proof of real-world performance.

## Run verification

Backend tests:

```powershell
$env:PYTHONPATH = ".\backend\src"
python -m pytest .\backend\tests
```

Skill validation:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\project-tools\validate-mindfront-skill.ps1
```

Hook routing tests:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\project-tools\test-mindfront-automation.ps1
```

Full workflow verification:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\project-tools\test-mindfront-skill.ps1
```

## Codex project integration

The `.codex/hooks.json` configuration is project-local. Open the repository as a trusted Codex project and ensure the Codex hooks feature is enabled before expecting automatic routing. The runtime audit is read-only and reports any missing prerequisite:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\project-tools\test-mindfront-runtime-pickup.ps1
```

A fresh clone is expected to require local trust and hook approval before that audit passes.
## Repository layout

- `.codex/`: project-local hook configuration and routing scripts.
- `backend/`: Python package and tests.
- `config/`: evidence labels, audience lenses, quality rules, and policy configuration.
- `docs/`: architecture, privacy, evidence, schemas, and workflow documentation.
- `examples/`: synthetic briefs, validation fixtures, and workplace-assistance inputs.
- `frontend/`: local GUI files.
- `project-tools/`: launch, validation, rendering, and test scripts.
- `skills/mindfront/`: Codex skill instructions and workflow wrapper.

## Safety boundaries

- Human review is required before using any suggested message.
- Mindfront must not auto-send, post, publish, approve, or impersonate.
- Recipient profiles are communication aids, not psychological truth or employee-evaluation evidence.
- Claims about preference, adoption, conversion, or performance require real evidence mapped to the exact claim and context.
- Sensitive or prohibited material must not be imported merely because the software can technically process it.

See `docs/data-boundaries.md`, `docs/ethical-boundaries.md`, and `docs/evidence-policy.md` for the complete rules.

## License

Copyright 2026 Robert Ganey.

This repository is source-available under the [PolyForm Noncommercial License 1.0.0](LICENSE.md). Commercial use is not permitted by that license. This is not an OSI-approved open-source license.

If you want to use Mindfront commercially, you need a separate written license from the copyright holder.

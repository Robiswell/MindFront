# MindFront

MindFront is a private, local-first workplace communication assistant. It helps you turn a complicated situation, rough draft, or confusing message into a clearer view of what is known, what is uncertain, what to say, and what to do next.

In plain English, you choose the kind of help you need, paste the relevant message or describe the situation, and add the outcome you want. MindFront separates facts from interpretations, checks for communication risks, and returns useful structure such as a clearer ask, a shorter version, alternative interpretations, unresolved questions, or the next action to take.

MindFront was designed to reduce the extra interpretation and drafting work that workplace communication can require, including for autistic professionals. It supports the user without trying to erase their personality, ambition, directness, or technical knowledge.

The project has two parts:

- The local application provides deterministic, offline communication support and message-quality checks. It does not need an AI model.
- The included Codex skill applies the same evidence, privacy, and human-review rules when MindFront is used through Codex for more flexible drafting and analysis.

MindFront does not read minds, diagnose people, score coworkers, predict career outcomes, or send messages. The user always reviews the result and decides what to use.

This public release contains only synthetic examples and test data. It contains no private workplace communications, personal profiles, connector exports, or employer data.

This project is source-available for noncommercial use. Commercial use is prohibited unless Robert Ganey provides a separate written license. See [License](#license).

## What problem it solves

Workplace communication often requires more than correcting grammar. A person may need to determine:

- what the other person is actually asking for
- which interpretation is supported and which is only possible
- how to make a request direct without sounding dismissive or pushy
- whether ownership, credit, authority, timing, or the next step is unclear
- how to preserve their natural voice while reducing avoidable reception risk
- what was decided and what remains unresolved
- which career claims are supported and which still need confirmation

MindFront turns those questions into a repeatable review process instead of relying on guesswork alone.

## What a MindFront session looks like

1. Choose **Prepare**, **Understand**, **Debrief**, **Career evidence**, or **Review a message or document**.
2. Paste a draft, an incoming message, or a description of the situation.
3. Add the outcome, audience, channel, and other context when they matter.
4. MindFront separates facts, inferences, unknowns, and unsupported claims before producing guidance.
5. Review the result, make any needed changes, and decide whether to use it.

For example, if the situation is "I need my manager to make a decision without making the request sound pushy," MindFront can identify the exact ask, place the strongest facts first, flag unclear authority or ownership, produce a short version, and identify the smallest useful next action.

Nothing is sent, posted, approved, or changed automatically.

## Assistance modes

| Mode | What you provide | What MindFront returns |
| --- | --- | --- |
| Prepare | A draft or upcoming conversation | The exact ask, leading facts, authority and credit checks, a short version, an interruption-safe sentence, and the next action |
| Understand | A message you received | Multiple plausible interpretations, known facts, unknowns, the risk of assuming incorrectly, and one clarifying question |
| Debrief | Notes from a meeting or conversation | Decisions, commitments, owners, dates, unresolved items, and possible interpretations kept separate from facts |
| Career evidence | Evidence about your own work | Supported impact, proof gaps, scope signals, and the next evidence needed without predicting a promotion |
| Message or document review | Draft content and its intended outcome | Clarity, credibility, evidence, audience, actionability, and reception-risk findings |

## What it includes

- A simple local web interface for communication preparation, interpretation, debriefing, and message review.
- A deterministic Python CLI for validation, analysis, rewriting, comparison, reader stress testing, research planning, reports, and local history.
- Optional encrypted local vaults for self profiles and authorized communication context.
- A Codex skill and project hooks that route MindFront requests while preserving human review and privacy boundaries.
- Synthetic examples and tests that contain no real workplace communications.

The local engine uses rules, schemas, and templates. External LLM calls are disabled by default and are not required for the GUI or deterministic CLI workflow. Read [LLM boundary](docs/llm-boundary.md) for the exact separation.

## Privacy model

MindFront is local-first. Private runtime data is excluded from this repository and ignored by Git.

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
python -m pip install -e .\backend
powershell -NoProfile -ExecutionPolicy Bypass -File .\project-tools\start-mindfront-gui.ps1
```

MindFront binds to `127.0.0.1` by default and opens the private local interface at `http://127.0.0.1:8765`.

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
python -m pip install pytest
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

## Architecture at a glance

- Local browser to loopback GUI and API to deterministic assistance engine.
- Codex request to MindFront skill to evidence and privacy rules to human review.
- CLI workflow to validated artifacts and reports.
- Optional private vaults to encrypted local context only.

Every path ends with human review. No adapter may auto-send, auto-approve, impersonate a user, or convert an inference into a fact.

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
- MindFront must not auto-send, post, publish, approve, or impersonate.
- Recipient profiles are communication aids, not psychological truth or employee-evaluation evidence.
- Claims about preference, adoption, conversion, or performance require real evidence mapped to the exact claim and context.
- Sensitive or prohibited material must not be imported merely because the software can technically process it.

See `docs/data-boundaries.md`, `docs/ethical-boundaries.md`, and `docs/evidence-policy.md` for the complete rules.

## License

Copyright 2026 Robert Ganey.

This repository is source-available under the [PolyForm Noncommercial License 1.0.0](LICENSE.md). Commercial use is not permitted by that license. This is not an OSI-approved open-source license.

If you want to use MindFront commercially, you need a separate written license from the copyright holder.

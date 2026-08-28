# Mindfront CLI Contract

This contract defines the current Mindfront command surface. The implementation validates local inputs, runs deterministic message analysis and rewrites, compares variants, runs simulated reader stress tests, produces research and documentation-task handoffs, assembles audit reports, persists sanitized artifact history, renders a static dashboard, emits an improvement backlog, and hands editable report HTML to the document-workflow PDF renderer.

Mindfront also provides two private assistance subsystems. `assist` uses a first-party, self-declared installation-local encrypted profile for the current user's workplace communication and career-evidence support. `corpus` and `profile` manage authorized recipient context and thresholded named-recipient guidance. None of these private stores are part of normal Mindfront history, dashboards, or shareable reports.

Normal deterministic commands remain offline by default. Private communication intake separately requires recorded Codex-processing authorization and an `externalModelProcessingUsed` disclosure.

## Invocation

```powershell
python -m mindfront.cli <command> [options]
```

The canonical private-store paths are:

```text
runtime-data/interaction-communications.vault
runtime-data/interaction-profiles.vault
runtime-data/self-workplace-assistance.vault
```

The shared key defaults to `%USERPROFILE%\.codex\mindfront\private-vault.key` and remains outside the repository. Vault maintenance never prints decrypted payloads:

```powershell
python -m mindfront.cli vault init-key
python -m mindfront.cli vault key-status
python -m mindfront.cli vault inspect --path <vault>
python -m mindfront.cli vault migrate --path <legacy-vault>
```

A successful legacy migration preserves a timestamped encrypted backup. A failed legacy DPAPI decryption leaves the source vault unchanged.

Private connector staging files and private command outputs must remain below `runtime-data` until deleted or sanitized.

The first private workplace-assistance commands are:

```powershell
python -m mindfront.cli assist profile upsert --input <self-profile.json>
python -m mindfront.cli assist preflight --input <request.json>
python -m mindfront.cli assist interpret --input <request.json>
python -m mindfront.cli assist debrief --input <request.json>
python -m mindfront.cli assist career-review --input <request.json>
```

The default self-profile store is `runtime-data/self-workplace-assistance.vault`; the default policy is `config/workplace-assistance-policy.json`.

The first validation command is:

```powershell
$env:PYTHONPATH='backend/src'
python -m mindfront.cli validate --strict --json-errors --config-root config --brief-root examples/briefs --task-validation-root examples/task-validation
```

The first analysis command is:

```powershell
$env:PYTHONPATH='backend/src'
python -m mindfront.cli analyze --brief examples/briefs/sample-message-brief.json --config-root config --output test-output/sample-analysis
```

The first rewrite command is:

```powershell
$env:PYTHONPATH='backend/src'
python -m mindfront.cli rewrite --brief examples/briefs/sample-message-brief.json --config-root config --output test-output/sample-rewrite
```

The first compare command is:

```powershell
$env:PYTHONPATH='backend/src'
python -m mindfront.cli compare --variants test-output/sample-rewrite/copy-variants.json --output test-output/sample-compare
```

The first reader stress-test command is:

```powershell
$env:PYTHONPATH='backend/src'
python -m mindfront.cli reader-stress-test --analysis test-output/sample-analysis/message-analysis-report.json --config-root config --output test-output/sample-stress
```

The first research-plan command is:

```powershell
$env:PYTHONPATH='backend/src'
python -m mindfront.cli research-plan --analysis test-output/sample-analysis/message-analysis-report.json --output test-output/sample-research-plan
```

The first task-validation command is:

```powershell
$env:PYTHONPATH='backend/src'
python -m mindfront.cli task-validation --input examples/task-validation/specialist-documentation-task-validation.json --analysis test-output/specialist-doc-analysis/message-analysis-report.json --output test-output/specialist-doc-task-validation
```

The first task-observation protocol command is:

```powershell
$env:PYTHONPATH='backend/src'
python -m mindfront.cli task-protocol --analysis test-output/specialist-doc-analysis/message-analysis-report.json --research-plan test-output/specialist-doc-research/research-plan.json --output test-output/specialist-doc-task-protocol
```

The first filled-session conversion command is:

```powershell
$env:PYTHONPATH='backend/src'
python -m mindfront.cli task-input --protocol test-output/specialist-doc-task-protocol/documentation-task-observation-protocol.json --sessions-csv path/to/filled-session-template.csv --observation-source real_task_observation --output test-output/specialist-doc-task-input
```

The first report command is:

```powershell
$env:PYTHONPATH='backend/src'
python -m mindfront.cli report --analysis test-output/sample-analysis/message-analysis-report.json --variants test-output/sample-rewrite/copy-variants.json --comparison test-output/sample-compare/variant-comparison.json --stress test-output/sample-stress/reader-stress-test.json --research-plan test-output/sample-research-plan/research-plan.json --config-root config --output test-output/sample-report
```

The first store, dashboard, and improvement-loop commands are:

```powershell
$env:PYTHONPATH='backend/src'
python -m mindfront.cli store ingest --db test-output/mindfront.sqlite --analysis test-output/sample-analysis/message-analysis-report.json --variants test-output/sample-rewrite/copy-variants.json --comparison test-output/sample-compare/variant-comparison.json --stress test-output/sample-stress/reader-stress-test.json --research-plan test-output/sample-research-plan/research-plan.json --report test-output/sample-report/mindfront-audit-report.json
python -m mindfront.cli store check-stale --db test-output/mindfront.sqlite
python -m mindfront.cli dashboard build --db test-output/mindfront.sqlite --output test-output/dashboard
python -m mindfront.cli improvement-plan --db test-output/mindfront.sqlite --output test-output/improvement-plan
```

## Global Flags

| Flag | Required | Meaning |
| --- | --- | --- |
| `--config-root <path>` | No | Config directory to validate. Defaults to `config`. |
| `--brief-root <path>` | No | Message brief directory to validate when present. Defaults to `examples/briefs`. |
| `--task-validation-root <path>` | No | Documentation task-validation input directory to validate when present. Defaults to `examples/task-validation`. |
| `--output <path>` | No | Write the validation report to a file or directory instead of stdout. |
| `--strict` | No | Treat warnings, deprecated aliases, missing optional-but-required-for-MVP contracts, and unknown enum values as failures. |
| `--json-errors` | No | Emit machine-readable error output using the error envelope below. |
| `--dry-run` | No | Resolve inputs and planned outputs without writing artifacts. Available on concrete commands and store/dashboard subcommands. |
| `--overwrite fail|replace|rename` | No | Output conflict behavior for file or directory outputs. Defaults to `fail`; repeatable wrappers use `replace`. |
| `--no-external-llm` | No | Accepted for deterministic offline runs. Phase 0/1 does not call external LLMs. |

## Profile-Assisted Flags

These optional flags are available on `analyze` and `rewrite`:

| Flag | Required | Meaning |
| --- | --- | --- |
| `--profile-store <path>` | Paired | Path to the installation-local encrypted named-profile store. |
| `--profile-name <displayName>` | Paired | Exact named recipient profile to apply. Requires `--profile-store`. |
| `--profile-context <context>` | No | Override deterministic context inference with one controlled communication context. |

The two paired flags must be supplied together. The CLI performs an exact normalized display-name lookup; it does not infer a recipient from prose. The calling Codex workflow may automatically detect a recipient named in the task and pass these flags, but it must not use fuzzy matching, title-based guessing, or a nearest-name fallback. After lookup, the CLI infers the task context from the validated brief, filters the profile to observations from that context, and declines to tailor when no matching observations exist.

## Exit Codes

| Code | Meaning |
| --- | --- |
| `0` | Success. |
| `1` | Validation failure. |
| `2` | Blocked by safety or evidence gate. |
| `3` | Missing input. |
| `4` | Output conflict. |
| `5` | Internal error. |

## Machine-Readable Error Shape

```json
{
  "status": "failed",
  "exitCode": 1,
  "errors": [
    {
      "code": "invalid_confidence_label",
      "message": "Unknown recommendationState.",
      "path": "recommendations[0].recommendationState"
    }
  ]
}
```

Rules:

- `status` is `ok`, `failed`, `blocked`, or `dry_run`, depending on command and outcome.
- `exitCode` must match the process exit code.
- `errors` is empty on success.
- `code` is stable snake_case for tests and automation.
- `message` is human-readable and must not be the only machine signal.
- `path` points to the offending field, reference, flag, or input path when available.

## `validate`

Purpose:

Validate that the Phase 0/1 local contracts are present, internally consistent, and safe to use before any analysis logic runs.

Required inputs:

- Config root, defaulting to `config`.
- Local contract files when present.
- Example briefs under `examples/briefs`.
- Example task-validation inputs under `examples/task-validation`.

Required gates:

- Schema shape checks for known contracts.
- Required field checks for message briefs.
- Enum validation for data classification, sensitive-domain context, expert-review state, publish readiness, confidence labels, evidence basis, and recommendation state.
- Cross-reference checks for config IDs and brief references.
- Deprecated alias rejection in strict mode, including `panel`; the contract name is `reader-stress-test`.
- Data-boundary checks: sample fixtures and task-validation inputs must not contain real customer, employee, patient, student, applicant, or participant data.
- Safety checks: sensitive-domain briefs cannot be treated as publish-ready without required expert review.
- Offline operation: validation must work with `--no-external-llm`.

Outputs:

- Validation report to stdout when `--output` is omitted.
- Validation report at `--output` when provided.
- Machine-readable error envelope when `--json-errors` is set or when validation fails in an automation context.

Minimal report fields:

```json
{
  "status": "ok",
  "command": "validate",
  "configRoot": "config",
  "strict": true,
  "checkedAt": "2026-05-09T17:00:00-06:00",
  "checks": [
    {
      "id": "message_brief_required_fields",
      "status": "passed",
      "path": "examples/briefs/sample-message-brief.json"
    }
  ],
  "errors": [],
  "warnings": []
}
```

## `analyze`

Purpose:

Analyze one validated message brief with deterministic checks and emit a conservative JSON report.

Required inputs:

- `--brief <path>` pointing to a valid `message_brief`.
- Config root, defaulting to `config`.

Optional private inputs:

- `--profile-store <path>` pointing to the encrypted interaction-profile store.
- `--profile-name <displayName>` identifying the exact intended recipient. Both profile flags are required together.
- `--profile-context <context>` overriding deterministic context inference when the caller has more precise task context.

Required gates:

- Config validation must pass.
- Message brief validation must pass.
- Analysis must run offline and cannot use external LLM processing.
- Claims with only free-text proof remain `user_provided_unverified`.
- Unsupported strong claims remain visible and blocked or marked for validation.
- Sensitive domains remain blocked until required expert review is recorded.
- A supplied profile must resolve to one exact confirmed identity.
- A supplied profile must be `active`, `eligibleForAutomaticUse`, and non-expired.
- Only observations and response hypotheses matching the inferred or explicitly supplied communication context may influence the result.
- Profile guidance may affect structure and anticipated question coverage only; it must not change claim support.
- Automatic sending remains disabled and human review remains required.

Outputs:

- JSON report to stdout when `--output` is omitted.
- `message-analysis-report.json` when `--output` points to a directory.
- The exact file when `--output` points to a `.json` path.
- Profile-assisted output includes sanitized application state and lineage. It records only profile id/hash and context-match state, never the recipient's name or private guidance.

Current output bundle:

- rubric scores
- deterministic findings
- motivation/friction report
- extracted claims
- recommendations
- research handoff question
- lineage hashes
- optional profile id/hash, application state, human-review state, and evidence boundary

Non-goals:

- No copy rewrite.
- No conversion prediction.
- No market preference claim.
- No synthetic reader simulation.
- No PDF/report polish.
- No exact response prediction, diagnosis, employee evaluation, or market-evidence upgrade.

## `rewrite`

Purpose:

Generate deterministic copy variants from one valid message brief and its source analysis.

Required inputs:

- `--brief <path>` pointing to a valid `message_brief`.
- Config root, defaulting to `config`.

Optional inputs:

- `--strategy <strategyId>`, repeatable. Without a profile, defaults to `plain_english_clarity`, `proof_first`, `problem_first`, and `cta_clarity`. When an active profile is supplied and no explicit strategy is selected, `profile_guided` is added before the normal strategy set.
- `--profile-store <path>` and `--profile-name <displayName>`, supplied together for an exact named recipient.

Required gates:

- Config validation must pass.
- Message brief validation must pass.
- Source analysis must not be blocked.
- Variants must run through the claim gate before output.
- Variants must not claim market evidence, conversion prediction, or validated user preference.
- Variants with unverified source claims must keep `requiresProofBeforePublishing: true`.
- A supplied profile must be active, eligible, non-expired, and uniquely matched.
- Profile guidance may reorder or frame supported source content but may not invent proof, commitments, dates, owners, risks, costs, or decisions.
- Profile-guided output requires human review and cannot be sent automatically.

Outputs:

- JSON copy variant bundle to stdout when `--output` is omitted.
- `copy-variants.json` when `--output` points to a directory.
- The exact file when `--output` points to a `.json` path.

Current output bundle:

- copy variants
- strategy ids
- claim-gate status
- preserved source claim references
- recommendation state
- lineage hashes
- optional sanitized profile-application state and profile hash

Non-goals:

- No freeform LLM copywriting.
- No proof invention.
- No publish-ready claim upgrade.
- No market validation.
- No impersonation, employee evaluation, diagnosis, or exact response prediction.

## `compare`

Purpose:

Compare gated rewrite variants and rank them as candidates for user testing.

Required inputs:

- `--variants <path>` pointing to a valid `copy_variant_bundle`.

Required gates:

- Input must be a copy variant bundle.
- Variants must include stable ids, strategy ids, copy, claim-gate status, and recommendation state.
- Rankings must not hide claim-gate failures.
- Rankings must not claim market preference, conversion prediction, comprehension proof, or validated persuasion.

Outputs:

- JSON comparison report to stdout when `--output` is omitted.
- `variant-comparison.json` when `--output` points to a directory.
- The exact file when `--output` points to a `.json` path.

Current output bundle:

- ranked variants
- deterministic dimension scores
- recommended test candidates
- claim-gate summary
- limitations and lineage hashes

Non-goals:

- No winner claim.
- No statistical result.
- No preference inference.
- No publish-ready upgrade.

## `reader-stress-test`

Purpose:

Run configured audience lenses against a message analysis report and emit explicitly simulated reader stress-test notes.

Required inputs:

- `--analysis <path>` pointing to a valid `message_analysis_report`.
- Config root containing `audience-lenses.json`.

Optional inputs:

- `--lens <lensId>`, repeatable. Defaults to all active lenses.

Required gates:

- Input must be a message analysis report.
- Every output result must include `simulationNotice`.
- Every output result must include `notMarketEvidence: true`.
- Every output result must use `evidenceBasis: synthetic_reader_stress_test`.
- Output must not produce `real_user_data`, `small_user_test`, `small_user_test_supported`, or `validated_for_exact_context`.

Outputs:

- JSON stress-test report to stdout when `--output` is omitted.
- `reader-stress-test.json` when `--output` points to a directory.
- The exact file when `--output` points to a `.json` path.

Current output bundle:

- one result per selected lens
- observed simulated friction
- referenced finding ids
- review questions
- recommended real-world validation
- limitations and lineage hashes

Non-goals:

- No persona roleplay.
- No real user quote.
- No market validation.
- No preference or conversion prediction.

## `research-plan`

Purpose:

Convert a message analysis report into a runnable research handoff with method, sample, consent, bias, stop-condition, and decision-threshold fields.

Required inputs:

- `--analysis <path>` pointing to a valid `message_analysis_report`.

Required gates:

- Input must be a message analysis report.
- Every major medium, high, or blocked finding must be covered by at least one research question.
- Every research question must include the required research-method policy fields.
- Comprehension validation must appear before preference, persuasion, or live-channel testing.
- A/B hypotheses must include sample-size and exact-context caveats.
- Output must not produce `real_user_data`, `small_user_test_supported`, or `validated_for_exact_context`.

Outputs:

- JSON research plan to stdout when `--output` is omitted.
- `research-plan.json` and `research-plan.md` when `--output` points to a directory.
- The exact file when `--output` points to a `.json` or `.md` path.

Current output bundle:

- normalized `research_question` records
- uncertainty coverage map
- motivation-friction and trust-gap coverage maps
- interview script
- survey questions
- usability tasks
- A/B hypotheses with caveats
- decision summary
- limitations and lineage hashes

Non-goals:

- No user evidence.
- No statistical claim.
- No market validation.
- No publish-ready upgrade.

## `task-validation`

Purpose:

Summarize documentation task observations as aggregate evidence. This command exists to support the Executive Impact Loop without pretending that a small task check or synthetic fixture is market research.

Required inputs:

- `--input <path>` pointing to a `documentation_task_validation_input` JSON file.

Optional inputs:

- `--analysis <path>` pointing to the source `message_analysis_report`, used to verify `sourceAnalysisReportId` and `briefId`.

Required gates:

- Input must be a `documentation_task_validation_input`.
- Input must declare `observationSource: real_task_observation` or `observationSource: synthetic_fixture`.
- Input must declare `containsPersonalData: false`.
- Input must declare `containsCustomerConfidentialData: false`.
- Input must declare `llmProcessingAllowed: false`.
- Sessions must reference known task ids and include required numeric task metrics.
- Sessions must use non-identifying `participantToken` values and coded `trustObjectionCodes`; raw trust-objection text is rejected.
- Real observation output must use `evidenceBasis: small_user_test`, `evidenceGrade: exact_context_directional`, and `realTaskEvidenceCreated: true`.
- Synthetic fixture output must use `evidenceBasis: synthetic_task_fixture`, `evidenceGrade: synthetic_fixture_only`, and `realTaskEvidenceCreated: false`.
- Output must include `marketEvidenceCreated: false`, `notMarketEvidence: true`, and `rawParticipantDataStored: false`.
- Output must not produce `validated_for_exact_context`, market preference, company-wide adoption proof, productivity lift proof, conversion prediction, or publish-ready upgrade.

Outputs:

- JSON result to stdout when `--output` is omitted.
- `documentation-task-validation-result.json` when `--output` points to a directory.
- The exact file when `--output` points to a `.json` path.

Current output bundle:

- aggregate task metrics
- before/after deltas when baseline metrics are supplied
- executive signals for completion, skim-to-answer speed, follow-up load, expert respect, reuse intent, and coded trust objections
- observation source, evidence basis, evidence grade, and real-task-evidence flag
- decision state
- recommended next step
- limitations and lineage hashes

Non-goals:

- No raw participant transcript, name, email, or identifying token storage.
- No personal data processing.
- No market validation.
- No company-wide performance or adoption proof.
- No confidence upgrade from dashboard or report inclusion.

## `task-protocol`

Purpose:

Generate a no-PII documentation task-observation protocol from a source analysis and optional research plan. This command creates a collection handoff and session template; it does not create evidence by itself.

Required inputs:

- `--analysis <path>` pointing to a `message_analysis_report`.

Optional inputs:

- `--research-plan <path>` pointing to a matching `research_plan`.
- `--document-id <id>` for the document under test.
- `--document-type <type>`, defaulting to `internal_documentation`.

Required gates:

- Analysis input must be a `message_analysis_report`.
- Research plan, when supplied, must reference the same analysis and brief.
- Research plan must not create market evidence.
- Protocol output must include `marketEvidenceCreated: false` and `notMarketEvidence: true`.
- Protocol must instruct observers to avoid names, emails, raw comments, transcripts, customer-confidential details, and personal data.

Outputs:

- JSON protocol to stdout when `--output` is omitted.
- `documentation-task-observation-protocol.json`, `documentation-task-observation-protocol.md`, and `documentation-task-session-template.csv` when `--output` points to a directory.
- The exact file when `--output` points to a `.json` or `.md` path.

Current output bundle:

- protocol id and source lineage
- target audience and document identifiers
- evidence and data boundaries
- consent script and stop conditions
- observer instructions
- task prompts and success/failure signals
- session CSV template columns
- task-validation input defaults
- limitations and hashes

Non-goals:

- No participant data collection inside the CLI.
- No market evidence.
- No adoption or performance proof.
- No task-validation result until sessions are filled and converted.

## `task-input`

Purpose:

Convert a filled no-PII task-observation CSV into a `documentation_task_validation_input` JSON artifact.

Required inputs:

- `--protocol <path>` pointing to `documentation-task-observation-protocol.json`.
- `--sessions-csv <path>` pointing to a filled session CSV using the published template columns.

Optional inputs:

- `--validation-id <id>` for deterministic downstream naming.
- `--observation-source synthetic_fixture|real_task_observation`; defaults to `synthetic_fixture`. Use `real_task_observation` only for real no-PII observations collected from the protocol.

Required gates:

- Protocol input must be a `documentation_task_observation_protocol`.
- Session CSV must include all required template columns.
- Session CSV must not include prohibited identifying or raw-comment columns, including case-varied names, emails, comments, notes, transcripts, quotes, or free-text fields.
- Session ids, participant tokens, role segments, and trust-objection codes must be short non-identifying codes.
- Session metrics must be typed and in range.
- Session task ids must exist in the protocol.
- Generated or test-filled CSV rows must remain `synthetic_fixture`; real task evidence requires explicit `--observation-source real_task_observation`.

Outputs:

- JSON task-validation input to stdout when `--output` is omitted.
- `documentation-task-validation-input.json` when `--output` points to a directory.
- The exact file when `--output` points to a `.json` path.
- Lineage and provenance fields: `sourceProtocolId`, `sourceProtocolHash`, `sourceSessionsHash`, `sourceSessionsProvenance`, and `provenanceBoundary`.

Non-goals:

- No raw participant comments or transcripts.
- No personal data processing.
- No evidence summary; use `task-validation` for aggregate results.
- No real task evidence unless the caller explicitly declares `real_task_observation`.

## `corpus`

Purpose:

Manage the installation-local encrypted vault that retains complete authorized internal messages for private assistive drafting. This vault is separate from normal Mindfront history and the named-profile store.

Subcommands:

- `corpus validate --input <communication-corpus-batch.json>`
- `corpus ingest --input <communication-corpus-batch.json> --vault <vaultPath>`
- `corpus ingest-outlook-export --input <connector-export.json> --vault <vaultPath> --batch-id <corpus-batch-id>`
- `corpus ingest-teams-export --input <connector-export.json> --vault <vaultPath> --batch-id <corpus-batch-id>`
- `corpus ingest-freshservice-jsonl --input <freshservice-agent-cases.jsonl> --cleaning-manifest <cleaning-manifest.json> --export-manifest <export-manifest.json> [--identity-map <identity-map.json>] --vault <vaultPath> --batch-id <corpus-batch-id>`
- `corpus list-people --vault <vaultPath>`
- `corpus context --vault <vaultPath> --name <displayName> [--context <context>] [--limit 1-100] [--include-thread-context] [--thread-limit 1-20]`
- `corpus derive-profile --vault <vaultPath> --name <displayName>`
- `corpus refresh-profile --vault <vaultPath> --profile-store <profileStorePath> --name <displayName>`
- `corpus delete-person --vault <vaultPath> --name <displayName>`
- `corpus invalidate-batch --vault <vaultPath> --batch-id <corpus-batch-id>`

Canonical vault:

```text
runtime-data/interaction-communications.vault
```

Supported sources:

- `microsoft_outlook`
- `microsoft_teams`
- `resolved_support_ticket`

Outlook, Teams, and the normalized Freshservice JSONL source pack have dedicated adapter commands. Other resolved-ticket sources may use a normalized `communication_corpus_batch` with `corpus validate` and `corpus ingest`.

The Freshservice adapter:

- requires `freshservice-agent-cases.jsonl`, `cleaning-manifest.json`, and `export-manifest.json`
- requires a read-only export manifest
- requires private notes to be included, duplicate messages to be preserved, and secret-like values to have always-on redaction
- verifies ticket and conversation counts across the source pack and manifests
- accepts only terminal status codes `4` and `5`
- accepts only internal authors resolved from an existing vault identity or an optional `freshservice_identity_map`
- preserves source order, complete accepted bodies, resolution outcome, and SHA-256 source-artifact hashes
- quarantines unresolved, non-internal, automated, malformed, missing-body, non-terminal, credential-bearing, and controlled-content rows through exclusion counts or validation errors

Required corpus gates:

- Purpose must be `autistic_communication_assistance`.
- The batch must record legitimate access, company-system authorization, Codex-processing authorization, assistive-only use, no employment-decision use, human review, and `governanceBasis: user_asserted_company_policy`.
- Private one-to-one content requires the corresponding approval flag.
- Coverage must remain partial.
- Attachments must not be processed.
- Credential/secret scanning must pass.
- Messages with detected credentials/secrets or explicit CUI/export-control markers must be excluded.
- Full-message encrypted retention must be disclosed.
- `externalModelProcessingUsed` must be a boolean.
- Authors must resolve to confirmed directory or ticket identities.
- Display-name identity collisions are blocked.

Ingestion behavior:

- Source-system record ids provide deterministic event identity.
- Re-ingesting an unchanged batch is idempotent.
- Changed source content replaces the prior version for that event.
- Replacing a batch removes missing records when no other batch references them.
- The vault retains complete accepted message bodies and source lineage under installation-local AES-256-GCM encryption.
- Normal Mindfront history is not updated by corpus ingestion.

Private context behavior:

- `corpus context` returns up to 100 complete authored messages for the exact named person.
- An optional context filter ranks exact-context messages before fallback context.
- `--include-thread-context` returns every ingested message, with actual author names and complete bodies, from up to `--thread-limit` selected conversations.
- A returned thread is complete only within the encrypted vault. The command does not claim that connector retrieval covered every source-system message.
- Complete context is private and may guide drafting; it must not be sent to `report`, `store`, `dashboard`, or `improvement-plan`.

Profile derivation behavior:

- Derivation uses subject-authored content after removing quoted Outlook history and common signatures.
- The original complete message remains in the communication vault.
- The derived bundle contains controlled observations, response hypotheses, private terminology, bounded representative examples, source coverage, counts, and authorization metadata.
- `corpus refresh-profile` derives and upserts the named profile into the separate profile store.
- The profile stores a digest of the exact source bundle used to derive it. `profile context --vault` compares that digest with the current named-person corpus and fails closed with `source_mismatch` after replacement, invalidation, or deletion changes the source.

Deletion behavior:

- `corpus invalidate-batch` removes the batch and deletes messages not referenced by another batch.
- `corpus delete-person` removes every full message authored by the confirmed named person and removes empty batch references.
- Neither operation automatically deletes an existing derived profile.

Outputs:

- Validation, ingest, people-index, context, derivation, refresh, invalidation, and deletion results are JSON.
- Private outputs containing names or messages must remain below `runtime-data`.
- Ingest results disclose the current vault encryption mode, retained message count, exclusion count, and that normal history was not updated.

Non-goals:

- No attachment ingestion.
- No normal-history or dashboard ingestion.
- No psychological diagnosis, employee evaluation, market evidence, or exact response prediction.
- No automatic sending or impersonation.

## `assist`

Purpose:

Run private, first-party workplace communication accommodation without forcing the message-audit/report pipeline.

Commands:

- `assist profile validate --input <self-profile.json>`
- `assist profile upsert --input <self-profile.json> [--store <path>]`
- `assist profile show [--store <path>]`
- `assist profile context [--store <path>]`
- `assist profile delete [--store <path>]`
- `assist preflight --input <request.json> [--self-store <path>] [--policy <path>]`
- `assist interpret --input <request.json> [--self-store <path>] [--policy <path>]`
- `assist debrief --input <request.json> [--self-store <path>] [--policy <path>]`
- `assist career-review --input <request.json> [--self-store <path>] [--policy <path>]`

Each mode also accepts optional `--recipient-guidance <interaction-assistance-guidance.json>` after the normal exact-name recipient checks have produced an active, current, context-matched private guidance artifact.

Required behavior:

- The self profile is explicitly user-declared and stored separately under installation-local AES-256-GCM encryption.
- `assist profile context` returns the bounded private personalization fields used by inline assistance. The prompt hook validates that the encrypted profile is available but never serializes decrypted values into hook output; the assistant loads them privately on demand for the current response.
- `preflight` returns the exact ask, authority-safe role line, explicit leading facts, separately labeled unverified claims, complete leading-evidence records, recommendation, visible credit, short version, interruption-safe sentence, gates, and next action.
- `interpret` returns facts, bounded inferences, at least two plausible interpretations, unknowns, one clarifying question, and the risk of acting on an unverified interpretation.
- `debrief` separates decisions, commitments, owners, dates, unresolved items, and follow-up.
- `career-review` classifies only the user's own evidence and missing proof, authority, sponsor, adoption, owner, or date. Its strongest supportable case includes only source-supported, stakeholder-confirmed, or formally decided records; user assertions remain visible only as candidates to verify. It does not predict promotion.
- Confirmed authority states require `authority.evidenceFactIds` that link to sourced, explicit `authority_evidence` facts in the same request. Missing, nonexistent, duplicate, or unqualified links fail closed.
- Language gates are review aids. They preserve the user's intent and direct voice while flagging motive attribution, unsupported authority, sole-source/territorial framing, disparagement, compliance certainty, contradictory certainty, message stacking, executive-altitude mismatch, and an explicitly rushed or fatigued state.
- Every result keeps `privateArtifact: true`, `humanReviewRequired: true`, `automaticSendingAllowed: false`, `coworkerEvaluationAllowed: false`, `promotionPredictionCreated: false`, and `normalHistoryEligible: false`.
- `--dry-run` never writes the encrypted store or result artifact.
- The self-profile store and every persisted `assist` output must resolve below a directory named `runtime-data`; the API and CLI reject other destinations.

The default store contains personal accommodation and career context. Do not copy it or an `assist` result into `report`, `store`, `dashboard`, or `improvement-plan`.

## `profile`

Purpose:

Manage the separate installation-local encrypted store containing named interaction-assistance profiles. Profiles use actual names for exact private lookup and contain derived communication guidance rather than the full message corpus.

Subcommands:

- `profile validate --input <observation-bundle.json>`
- `profile build --input <observation-bundle.json>`
- `profile upsert --input <observation-bundle.json> --store <profileStorePath>`
- `profile show --store <profileStorePath> --name <displayName> [--include-collecting]`
- `profile context --store <profileStorePath> --name <displayName> [--vault <communicationVaultPath>] [--context <controlledContext>]`
- `profile list --store <profileStorePath>`
- `profile delete --store <profileStorePath> --name <displayName>`
- `profile invalidate-batch --store <profileStorePath> --bundle-id <communication-bundle-id>`

Canonical store:

```text
runtime-data/interaction-profiles.vault
```

Required profile gates:

- Purpose must be `autistic_communication_assistance`.
- The display name must resolve to one confirmed directory or ticket identity and one SHA-256 identity fingerprint.
- Authorization must use the same private-assistance fields required by `corpus`.
- Derived profile governance records `basis: user_asserted_company_policy` and `independentlyVerified: false`.
- Feature bundles reject raw message bodies, subjects, transcripts, message ids, sender/recipient fields, attachments, and other raw-content keys.
- Required exclusions are `credentials_and_secrets` and `cui_and_export_controlled`.
- Connector coverage must remain partial.

Automatic-use readiness:

| Requirement | Minimum |
| --- | --- |
| Subject-authored messages | 50 |
| Conversations | 5 |
| Contexts | 2 |
| Active days | 30 |
| Collection-window span | 45 days |

At least one observation must also be either:

- a subject-confirmed explicit preference, or
- a behavioral pattern with at least 20 supporting instances and at least 65 percent consistency within one matching context.

A context-scoped response hypothesis requires at least 20 supporting instances and at least 65 percent consistency to become `context_supported`. Evidence from one context cannot qualify or guide a different context. The overall profile still requires at least two distinct contexts. Below-threshold observations remain tentative, and the profile remains `collecting` when automatic-use readiness is not met.

Freshness:

- `expiresAt` is 90 days after the end of the newest observation window.
- An expired profile is marked `stale`.
- Only an `active`, non-expired profile with `eligibleForAutomaticUse: true` may produce `profile context` guidance or guide `analyze`/`rewrite`.
- Refreshing the profile recalculates readiness, confidence, expiry, guidance, and profile hash.

Automatic recipient matching:

- The Codex orchestration layer may identify a recipient named in the task and pass the exact display name to `analyze` or `rewrite`.
- Matching is exact after case-insensitive name normalization.
- The matched profile must represent one confirmed identity and be active, eligible, non-expired, and relevant to the current context.
- Missing, ambiguous, collecting, stale, or context-mismatched profiles are not applied.
- The CLI does not parse prose to infer a recipient.
- The CLI enforces exact lookup, identity uniqueness, readiness, staleness, deterministic context inference, and context-filtered application. The calling orchestration is responsible only for semantic recipient extraction and may use `--profile-context` when the task supplies a more precise controlled context.
- `skills/mindfront/scripts/run_mindfront_workflow.ps1` defaults named-recipient runs to `runtime-data/interaction-communications.vault`, verifies the stored source digest, refreshes once when the profile is missing or ineligible, and rechecks before applying guidance. If the vault is unavailable or no active source-matched profile exists, it continues unprofiled and emits an explicit bounded-coverage notice.

Profile guidance may include:

- qualified drafting adjustments
- likely question or response classes
- preferred terminology and terms to avoid
- bounded representative examples
- context and use rules

Every guidance output includes:

- `humanReviewRequired: true`
- `automaticSendingAllowed: false`
- `marketEvidenceCreated: false`
- a boundary stating that the profile is not a diagnosis, personality truth, employee evaluation, or exact behavior prediction

Deletion behavior:

- `profile invalidate-batch` removes one derived bundle, recomputes affected profiles, and deletes profiles with no remaining bundles.
- `profile delete` removes the named profile and all of its encrypted derived batches.
- Neither operation automatically deletes source messages in the communication vault.

Non-goals:

- No storage of the full communication corpus in the profile store.
- No fuzzy identity matching.
- No comparison or ranking of people.
- No employee decision support.
- No diagnosis, market evidence, exact future-word prediction, sending, or impersonation.

## `report`

Purpose:

Assemble validated Mindfront artifacts into local JSON, Markdown, editable HTML, and CSV audit report outputs.

Required inputs:

- `--analysis <path>` pointing to a valid `message_analysis_report`.
- Config root containing `confidence-labels.json`.

Optional inputs:

- `--variants <path>` pointing to a `copy_variant_bundle`.
- `--comparison <path>` pointing to a `variant_comparison_report`.
- `--stress <path>` pointing to a `reader_stress_test_report`.
- `--research-plan <path>` pointing to a `research_plan`.
- `--task-protocol <path>` pointing to a `documentation_task_observation_protocol`.
- `--task-validation <path>` pointing to a `documentation_task_validation_result`.

Required gates:

- Input artifacts must match their expected artifact types.
- Optional artifacts must reference the supplied source analysis or variant bundle.
- Reader stress-test and research-plan artifacts must not create market evidence.
- Task-observation protocol artifacts must not create market evidence and must keep `notMarketEvidence: true`.
- Task-validation artifacts must not create market evidence. Real observation artifacts remain exact-context directional evidence; synthetic fixture artifacts remain workflow checks only.
- Report output must preserve unsupported claims, limitations, confidence labels, and what to test next.
- Report output must not introduce `small_user_test_supported`, `validated_for_exact_context`, or other confidence upgrades.
- PDF status must stay `not_generated_by_cli` unless a separate document workflow renders and verifies a PDF.
- Directory output must include a document-workflow handoff with editable source path, planned PDF path, and verification rule.
- Full messages, names, identity fingerprints, private examples, private terminology, and named response-pattern details must not enter report output.
- Profile-assisted inputs may preserve only sanitized application state, non-identifying lineage such as a profile hash, human-review state, and the evidence boundary.

Outputs:

- JSON report bundle to stdout when `--output` is omitted.
- `mindfront-audit-report.json`, `mindfront-audit-report.md`, editable `source.html`, compatibility copy `mindfront-audit-report.html`, and `mindfront-audit-scorecard.csv` when `--output` points to a directory.
- `mindfront-document-workflow-handoff.md` when `--output` points to a directory.
- The exact file when `--output` points to a `.json`, `.md`, `.html`, or `.csv` path.

Current output bundle:

- short-version summary
- confidence labels
- scorecard
- message diagnosis
- claim/proof map
- motivation and friction
- copy variant summary
- synthetic audience review
- task-observation protocol handoff when provided
- task-validation evidence when provided
- what to test next
- limitations
- report output manifest

Non-goals:

- No PDF rendering inside the CLI.
- No deck rendering inside the CLI.
- No new claims beyond source artifact summaries.
- No evidence or publish-readiness upgrade.
- No disclosure of private named-profile content.

## `store`

Purpose:

Persist validated artifact summaries in a local SQLite history store and support export/delete flows before dashboard use.

Subcommands:

- `store init --db <path>`
- `store ingest --db <path> --analysis <path> [--variants <path>] [--comparison <path>] [--stress <path>] [--research-plan <path>] [--report <path>] [--task-protocol <path>] [--task-validation <path>]`
- `store list-analyses --db <path> [--output <path>]`
- `store compare --db <path> [--brief-id <id>] [--output <path>]`
- `store export --db <path> --output <path>`
- `store check-stale --db <path> [--output <path>]`
- `store delete-run --db <path> --run-id <id>`

Required gates:

- Required analysis input must be a `message_analysis_report`.
- Optional artifacts must match their expected artifact types and source ids.
- Stress, research, and report artifacts must not create market evidence.
- Task-observation protocols must not create market evidence and must keep `notMarketEvidence: true`.
- Task-validation artifacts must not create market evidence.
- Store must keep full raw source text out of the database by default.
- Store must keep interaction-profile names, identity fingerprints, private examples, private terminology, private guidance, and complete communication context out of the database.
- Stored dashboard rows must include validation state, sensitive-domain state, simulated result count, validated signal count, task-validation signal count, source/config hashes, and stale state.
- Stored task-validation rows must include aggregate metrics only, not raw participant identity or raw transcripts.
- `store check-stale` must mark a run stale when a stored artifact path is missing or its current hash differs from the stored hash.

Outputs:

- SQLite database at `--db`.
- JSON results on stdout for init, ingest, list, compare, and delete-run.
- JSON export file for `store export`.
- JSON stale-state check for `store check-stale`.

Non-goals:

- No remote database.
- No real-time syncing.
- No confidence upgrade from historical presence alone.

## `dashboard`

Purpose:

Build a static local dashboard from the SQLite store.

Subcommands:

- `dashboard build --db <path> --output <directory>`

Required gates:

- Store must exist and be readable.
- Dashboard must distinguish simulated reader-stress results from validated signals.
- Dashboard must distinguish real exact-context task-validation signals, synthetic task-validation fixtures, heuristic outputs, and simulated reader-stress outputs.
- Dashboard must surface task-observation protocols as collection handoffs, not evidence.
- Dashboard must show prior analyses, score changes, repeated message failures, validation state, sensitive-domain state, and stale state.
- Dashboard must not store or render full raw source text by default.
- Dashboard must not store or render named-profile identities, actual recipient names, identity fingerprints, private examples, private terminology, or named response-pattern detail.
- Dashboard must not upgrade any evidence, confidence, recommendation, or claim status.

Outputs:

- `mindfront-dashboard.json`
- `index.html`

Non-goals:

- No web server.
- No authenticated dashboard.
- No live telemetry.
- No publish-ready or market-validation claim.

## `improvement-plan`

Purpose:

Build a ranked next-action backlog from stored Mindfront history so the next Codex documentation pass can act on prior findings, stale-state checks, protocol handoffs, and real task-validation friction.

Command:

- `improvement-plan --db <path> [--brief-id <id>] [--max-actions <n>] [--output <path>]`

Required gates:

- Store must exist and be readable.
- Improvement actions must use stored summaries, hashes, scores, status fields, task metrics, and artifact paths only.
- Improvement actions must not use or expose named-profile identities, full communications, private examples, private terminology, or named response-pattern details.
- Synthetic task-validation fixtures must not create real task-friction improvement actions.
- Real task-validation actions must remain exact-context and must not become market evidence, preference proof, adoption proof, or company-wide performance proof.
- Output must include `marketEvidenceCreated: false`, `notMarketEvidence: true`, and an explicit evidence boundary.

Outputs:

- `mindfront-improvement-plan.json`
- `mindfront-improvement-plan.md`

Non-goals:

- No autonomous editing.
- No market research claim.
- No company-wide performance claim.
- No raw source text, participant identity, raw comments, or transcripts.

## Command Contract Table

`validate`, `analyze`, `rewrite`, `compare`, `reader-stress-test`, `research-plan`, `task-protocol`, `task-input`, `task-validation`, `assist`, `corpus`, `profile`, `report`, `store`, `dashboard`, and `improvement-plan` are in the current implementation. PDF rendering is available through the separate document-workflow renderer and must preserve the evidence boundary. The private `assist`, `corpus`, and `profile` stores and results are operational inputs, not report/history stores.

| Command | Required Inputs | Outputs | Required Gates |
| --- | --- | --- | --- |
| `validate` | config root | validation report | schema, refs, enums |
| `analyze` | message brief | JSON analysis report | config, brief, data boundary, claims |
| `rewrite` | message brief | JSON copy variant bundle | source analysis valid, claim gate |
| `compare` | copy variant bundle | JSON comparison report | variant schema, claim gate visibility |
| `reader-stress-test` | analysis report, lenses | stress-test report | simulation boundary, lens schema |
| `research-plan` | analysis report | research plan | uncertainty mapping, research ethics |
| `task-protocol` | analysis report, optional research plan | protocol JSON, Markdown, CSV template | no-PII protocol boundary |
| `task-input` | protocol, filled session CSV | task-validation input JSON | no PII, typed session metrics, explicit observation source |
| `task-validation` | task-validation input, optional analysis report | aggregate task-validation result | data boundary, exact-context evidence boundary |
| `corpus` | authorized communication batch/export, encrypted vault | encrypted full-message vault and private operation results | authorization, identity, secret/control scan, private output boundary |
| `profile` | feature-only observation bundle, encrypted store | encrypted named profile store and private guidance | thresholds, freshness, exact identity, no raw corpus |
| `report` | analysis report, optional artifacts | JSON, Markdown, editable HTML, CSV | confidence labels, limitations, report manifest |
| `store` | artifact set | SQLite store, JSON results | source refs, data boundary, export/delete |
| `dashboard` | SQLite store | static JSON/HTML dashboard | simulated vs validated separation |
| `improvement-plan` | SQLite store | improvement-plan JSON/Markdown | operational backlog, evidence boundary |

## Naming Rule

The synthetic review command is `reader-stress-test`, not `panel`. This reduces pseudo-persona and fake-research risk. Strict validation must reject `panel` as a deprecated alias after Phase 1.

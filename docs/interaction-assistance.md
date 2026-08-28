# Mindfront Private Interaction Assistance

Status: Implemented operating contract.

## Purpose

Private interaction assistance helps Codex prepare clearer documentation and messages for a known colleague. It uses authorized internal communication history to reduce the interpretation and drafting load placed on an autistic writer.

The system is designed to answer bounded drafting questions:

- How much context has usually been useful in exchanges like this?
- Which terminology has reduced clarification loops?
- What question classes commonly followed similar requests?
- Should the recommendation, evidence, risk, owner, timing, or next step appear earlier?
- Which prior wording and resolved-ticket outcomes provide useful context?

It is not designed to answer:

- What is this person's psychological type?
- What is the person thinking or feeling?
- What exact words will the person use?
- Will the person approve the request?
- How should the person be evaluated as an employee?

## First-Party Assistance

Mindfront also has a separate encrypted self profile at:

`runtime-data/self-workplace-assistance.vault`

This profile contains only information the current user explicitly declares about their own accommodation context, career goal, strengths, known communication risks, support preferences, authenticity constraints, and energy protection. It is not derived from colleague messages and it is not stored in the named-recipient profile store.

The `assist` fast path supports:

- `preflight`: prepare the exact ask, authority-safe role framing backed by linked source evidence when authority is confirmed, up to three explicit leading facts, separately labeled unverified claims, recommendation, teammate credit, short version, and interruption-safe sentence
- `interpret`: separate facts from inferences, provide multiple plausible interpretations, state unknowns, and offer one clarifying question
- `debrief`: separate decisions, commitments, owners, dates, interpretations, and unresolved items
- `career_review`: organize the user's own evidence and formalization gaps without predicting promotion; user assertions remain verification candidates and do not enter the strongest supportable case

Confirmed authority states must reference explicit, sourced `authority_evidence` facts in the same request. An authority evidence-state label alone is not proof.

The goal is reduced interpretation and drafting load while preserving the user's directness, ambition, technical precision, initiative, and team advocacy. The system flags reception risk and proposes minimal changes; it does not enforce masking or suppress personality.

The leadership framing is one accountable coordinator with distributed specialist and approval ownership. For example, a domain specialist may own security research and validation while the user coordinates architecture and integration. This is not shadow management when scope, credit, partnership, and final approval are explicit.

## Private Architecture

| Component | Default Path | Function |
| --- | --- | --- |
| Communication vault | `runtime-data/interaction-communications.vault` | Stores complete authorized Outlook, Teams, and resolved-ticket messages under installation-local AES-256-GCM authenticated encryption. |
| Profile store | `runtime-data/interaction-profiles.vault` | Stores actual names, confirmed identity fingerprints, derived observations, response hypotheses, terminology, and bounded representative examples under separate installation-local AES-256-GCM encryption. |
| Normal Mindfront workflow | Existing analysis, rewrite, compare, report, history, dashboard, and improvement-plan paths | Uses only sanitized assistance state and lineage. It does not receive names, full messages, or private profile detail. |

The stores are deliberately separate. Deleting or invalidating one does not silently mutate the other.

## Source Boundary

Supported source systems are:

- `microsoft_outlook`
- `microsoft_teams`
- `resolved_support_ticket`

Full messages are valuable because an isolated sentence loses conversational sequence, terminology, follow-up questions, and ticket outcome. The vault therefore retains the complete authorized message body. Profile derivation separately removes quoted Outlook history and common signatures from the current author's analytical text so another person's words are not attributed to the named subject.

For named-recipient documentation, Codex should attempt a live connected-source refresh before it treats the encrypted corpus as current. Teams and Outlook search results are discovery records; fetch the complete message or thread bodies for relevant exact-person and task-topic matches before adapter ingestion. Prefer native author, message, conversation, and timestamp identifiers. Connector pagination, result limits, throttling, and empty searches must remain explicit coverage limits. The deterministic PowerShell wrapper has no cloud-connector capability and operates only on the encrypted vault supplied to it.

The system does not ingest attachments. It excludes messages containing credential/secret patterns or explicit CUI/export-control markers before storage. Ordinary authorized internal messages are not excluded merely because they contain names, internal plans, technical details, private one-to-one discussion, or complete conversation history.

## Authorization Record

Every source batch must record:

```json
{
  "requesterHasLegitimateAccess": true,
  "companySystemContentAuthorized": true,
  "codexProcessingAuthorized": true,
  "assistiveUseOnly": true,
  "noEmploymentDecisionUse": true,
  "humanReviewRequired": true,
  "governanceBasis": "user_asserted_company_policy"
}
```

The governance record means the user has asserted that company-system content is authorized for this internal assistive purpose. The derived profile records `independentlyVerified: false`; Mindfront does not present the assertion as an independent policy audit.

## Identity Resolution

Actual names are permitted inside the two private stores and private command outputs.

Each person must resolve through:

1. a confirmed directory or ticket identity
2. the actual display name
3. a SHA-256 identity fingerprint derived from the connector-local identity

The system does not infer a person from writing style, signature text, role, title, or similarity. A display-name collision between different fingerprints blocks profile storage and automatic use.

## Collection And Derivation

The implemented flow is:

1. Retrieve an authorized Outlook page, Teams transcript, or normalized resolved-ticket batch.
2. Convert the source into a versioned `communication_corpus_batch`.
3. Scan every message for excluded credentials/secrets and explicit CUI/export-control markers.
4. Ingest accepted full messages into the installation-local encrypted communication vault.
5. Select one confirmed author by actual display name.
6. Remove quoted history and common signatures from that author's analytical copy while preserving the full source message in the vault.
7. Derive controlled observations, response hypotheses, terminology, and representative examples.
8. Build or refresh the named profile in the separate installation-local encrypted profile store.
9. Mark the profile `collecting`, `active`, or `stale`.
10. Apply an active profile only to a matching recipient and context, then require human review.

Connector coverage is always recorded as partial. A profile summarizes observed samples; it is not a complete record of the person.

## Readiness Thresholds

Automatic use requires all of the following:

| Requirement | Minimum |
| --- | --- |
| Subject-authored messages | 50 |
| Distinct conversations | 5 |
| Distinct contexts | 2 |
| Active days | 30 |
| Collection-window span | 45 days |

It also requires at least one qualified observation:

- Subject-confirmed explicit preferences are `subject_confirmed`.
- A behavioral pattern becomes `context_supported` within one matching context when that context has at least 20 supporting instances and at least 65 percent consistency. Evidence observed in one context cannot qualify or guide another context.
- Response hypotheses require at least 20 supporting instances and at least 65 percent consistency within the trigger context to become `context_supported`.

Everything else remains `tentative`. A profile that has not met the collection and observation requirements remains `collecting`.

## Automatic Recipient Matching

the user does not need to ask Codex to use the profile system each time.

When a documentation or message request names one recipient, the Codex workflow may:

1. normalize the stated recipient name
2. look for one exact named profile
3. verify that its confirmed identity is unique
4. verify `status: active`
5. verify `eligibleForAutomaticUse: true`
6. verify the profile has not expired
7. apply only observations that match the current communication context
8. pass the exact match to `analyze` or `rewrite`

The CLI does not extract a recipient from prose. The orchestration layer must pass both:

```powershell
--profile-store runtime-data/interaction-profiles.vault
--profile-name "<exact display name>"
```

`analyze` and `rewrite` infer a controlled communication context from the validated brief. The caller may override that inference with `--profile-context` when it has more precise task context.

No fuzzy or nearest-name fallback is allowed. If the profile is missing, ambiguous, collecting, stale, or context-mismatched, Mindfront proceeds without profile guidance. The output records the evaluated context and whether matching profile observations existed.

### Current Enforcement Boundary

The CLI enforces paired profile flags, exact named lookup, identity uniqueness, readiness, staleness, current-corpus source matching, deterministic context inference, and context-filtered guidance. It does not independently:

- extract a recipient name from the user's prose
- refresh connector data before every draft

Those steps belong to the Codex orchestration layer. Automatic recipient-aware use therefore occurs only when Codex recognizes the named recipient and passes the exact profile flags. The deterministic wrapper defaults named-recipient runs to `runtime-data/interaction-communications.vault`, checks the stored source digest against that current vault, refreshes the exact profile once when needed, and rechecks it. If the vault is unavailable or the profile remains ineligible, the wrapper records a bounded unprofiled fallback and runs the normal workflow. It cannot call Microsoft cloud connectors itself; live retrieval remains an orchestration step. The CLI then selects only evidence observed in the inferred or explicitly supplied task context; if none matches, it records a context mismatch and does not tailor the copy.

```powershell
skills/mindfront/scripts/run_mindfront_workflow.ps1 `
  -BriefPath path/to/message-brief.json `
  -RecipientName "<exact display name>" `
  -ProfileStorePath runtime-data/interaction-profiles.vault
```

Use `-CommunicationVaultPath <path>` only to override the canonical encrypted vault.

## Drafting Behavior

An active profile may guide:

- order of information
- amount of context
- recommendation and decision framing
- evidence placement
- action, owner, and timing clarity
- terminology
- likely question classes to answer proactively
- respectful tone and reading density

It may not:

- invent claims, proof, commitments, owners, dates, costs, risks, or decisions
- strengthen unsupported claims
- authorize sending
- imitate the recipient
- claim certainty about a response
- override the normal Mindfront claim and evidence gates

The current rewrite implementation can use the `profile_guided` strategy to reorder supported source content. Profile guidance changes presentation, not factual support.

## Private CLI Workflow

Use the normal bundled runtime and set `PYTHONPATH=backend/src`.

### Ingest Outlook or Teams connector exports

```powershell
python -m mindfront.cli corpus ingest-outlook-export `
  --input runtime-data/staging/outlook-page.json `
  --vault runtime-data/interaction-communications.vault `
  --batch-id corpus-batch-outlook-2026-07-24

python -m mindfront.cli corpus ingest-teams-export `
  --input runtime-data/staging/teams-threads.json `
  --vault runtime-data/interaction-communications.vault `
  --batch-id corpus-batch-teams-2026-07-24
```

Delete each staging export after the ingest result is confirmed.

### Ingest the normalized Freshservice source pack

The implemented Freshservice adapter validates the source pack before ingesting terminal resolved-ticket messages:

```powershell
python -m mindfront.cli corpus ingest-freshservice-jsonl `
  --input path/to/freshservice-agent-cases.jsonl `
  --cleaning-manifest path/to/cleaning-manifest.json `
  --export-manifest path/to/export-manifest.json `
  --identity-map runtime-data/freshservice-identity-map.json `
  --vault runtime-data/interaction-communications.vault `
  --batch-id corpus-batch-freshservice-2026-07-24
```

`--identity-map` is optional when the encrypted vault already maps the same internal email fingerprint to an exact display name. The adapter requires a read-only export manifest, private notes, preserved duplicate rows, always-on secret-like-value redaction, and matching ticket/conversation counts. It accepts terminal status codes `4` and `5`, retains complete accepted bodies, preserves source order and resolution outcome, and records source-artifact hashes.

Other normalized resolved-ticket sources may still use `corpus validate` followed by generic `corpus ingest`. They must use `sourceSystem: resolved_support_ticket` and confirm known resolution outcomes.

### Inspect private coverage and context

```powershell
python -m mindfront.cli corpus list-people `
  --vault runtime-data/interaction-communications.vault

python -m mindfront.cli corpus context `
  --vault runtime-data/interaction-communications.vault `
  --name "<exact display name>" `
  --context decision_request `
  --limit 30 `
  --include-thread-context `
  --thread-limit 5
```

`corpus context` returns complete private messages authored by the exact person. With `--include-thread-context`, it also returns every ingested message from the selected conversations in source order, with actual author names and complete bodies. `--thread-limit` limits how many relevant conversations are selected; it does not truncate messages inside a selected ingested conversation. The result states `complete_within_ingested_vault` because connector coverage may still be partial. Use the response as private working context and do not direct it to a normal report, dashboard, history, improvement plan, or shareable handoff path.

### Derive and refresh a named profile

```powershell
python -m mindfront.cli corpus derive-profile `
  --vault runtime-data/interaction-communications.vault `
  --name "<exact display name>" `
  --output runtime-data/profile-observation.json

python -m mindfront.cli corpus refresh-profile `
  --vault runtime-data/interaction-communications.vault `
  --profile-store runtime-data/interaction-profiles.vault `
  --name "<exact display name>"
```

`derive-profile` creates a private feature bundle. `refresh-profile` derives and upserts it directly.

### Apply a profile

```powershell
python -m mindfront.cli analyze `
  --brief path/to/message-brief.json `
  --config-root config `
  --profile-store runtime-data/interaction-profiles.vault `
  --profile-name "<exact display name>" `
  --output runtime-data/private-analysis

python -m mindfront.cli rewrite `
  --brief path/to/message-brief.json `
  --config-root config `
  --profile-store runtime-data/interaction-profiles.vault `
  --profile-name "<exact display name>" `
  --output runtime-data/private-rewrite
```

The private analysis and rewrite must be sanitized before any artifact enters `report`, `store`, `dashboard`, or a shareable handoff.

## Lifecycle

### Ingestion

- Stable source record ids make re-ingestion idempotent.
- Changed source content updates the stored message version.
- Replacing a batch removes no-longer-present records when another batch does not reference them.

### Profile refresh

- A new derived bundle is merged into the existing profile for the same identity.
- Reusing the same bundle id is unchanged rather than duplicated.
- Counts, confidence, guidance, status, expiry, and hash are recomputed after a valid change.

### Staleness

- `expiresAt` is 90 days after the latest observation-window end.
- An expired profile becomes `stale`.
- `stale` and `collecting` profiles cannot guide analysis or rewriting.
- Refresh from current source content is required before automatic reuse.

### Invalidation

```powershell
python -m mindfront.cli corpus invalidate-batch `
  --vault runtime-data/interaction-communications.vault `
  --batch-id corpus-batch-outlook-2026-07-24

python -m mindfront.cli profile invalidate-batch `
  --store runtime-data/interaction-profiles.vault `
  --bundle-id comms-bundle-example
```

Corpus invalidation removes unreferenced full messages. Profile invalidation removes the derived source bundle, recomputes affected profiles, and removes a profile if no derived bundle remains.

### Person-level deletion

```powershell
python -m mindfront.cli corpus delete-person `
  --vault runtime-data/interaction-communications.vault `
  --name "<exact display name>"

python -m mindfront.cli profile delete `
  --store runtime-data/interaction-profiles.vault `
  --name "<exact display name>"
```

Run both commands for complete person-level deletion. Deleting one store does not implicitly delete the other.

## Output Boundary

Private artifacts may use actual names so the user can verify the correct match. Normal Mindfront artifacts may not.

Before a shareable output is complete, verify that it contains none of the following:

- employee or recipient names from the private system
- email addresses
- identity fingerprints
- full messages or transcripts
- private examples
- private lexicon
- named response-pattern details

A shareable output may retain:

- whether bounded assistance was applied
- a non-identifying profile hash for lineage
- `humanReviewRequired: true`
- `automaticSendingAllowed: false`
- `marketEvidenceCreated: false`
- the general evidence boundary

## Evidence Boundary

The system produces context-specific communication hypotheses. It does not produce:

- a diagnosis
- a personality truth
- a prediction of exact words or behavior
- an employee evaluation
- market research
- preference, conversion, adoption, or performance evidence

Full messages improve contextual drafting. More messages can improve coverage and confidence within observed contexts, but volume does not remove these boundaries.

## Operator Completion Check

Before treating a profile-assisted draft as complete:

- confirm the intended recipient matched exactly
- confirm the profile is active and non-expired
- confirm the current context matches the supporting observations
- confirm the source claims remain supported
- confirm no private wording was copied unnecessarily
- confirm the output sounds like the user
- confirm human review occurred
- confirm any shareable artifact contains no names or private communication content

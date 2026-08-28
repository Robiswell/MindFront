# Mindfront Evidence Policy

Status: Canonical evidence policy.

## Purpose

Mindfront can make a message easier to understand and easier to test. It cannot know what the market wants without real evidence.

The private interaction-assistance system adds a different kind of input: observed communication from a known colleague. Complete messages can improve contextual drafting because they preserve actual wording, sequence, terminology, question classes, and resolved-ticket outcomes. They do not reveal psychological truth and do not validate market preference, conversion, adoption, employee value, or exact future behavior.

## Evidence Ladder

| Evidence Basis | Meaning | May Support |
| --- | --- | --- |
| `unsupported` | No usable support is attached. | Blocked claim or rewrite review. |
| `user_provided_unverified` | The user supplied a proof note or assertion, but method, sample, source, and limits are incomplete. | Support candidate only. |
| `source_evidence` | A supplied source supports a narrow statement, subject to its limitations. | Bounded claim support. |
| `heuristic_inference` | The finding comes from observable text and configured principles. | Message improvement hypothesis. |
| `synthetic_reader_stress_test` | A configured lens found likely reader friction. | Stress-test hypothesis only. |
| `synthetic_task_fixture` | Synthetic documentation-task observations verify the task-validation workflow shape. | Pipeline check only. |
| `local_validation` | Local manual review or checklist evidence exists. | Internal readiness signal. |
| `small_user_test` | A small real-user test supports a specific comprehension or usability question. | Exact-context directional evidence. |
| `real_user_data` | Real user behavior or research data is mapped to the claim and context. | Exact-context evidence, with limits. |
| `expert_review` | A qualified reviewer approved a domain-specific interpretation. | Domain review support, not market preference by itself. |

Named interaction assistance does not add a market-evidence rung. Its observations and hypotheses remain private assistance signals governed by the separate table below.

First-party workplace assistance also does not add a market-evidence rung. The user's declared goals, strengths, communication risks, and accommodation preferences may guide support immediately because they describe the user, but they do not prove formal authority, coworker intent, sponsor commitment, promotion readiness, or a future career outcome.

## Interaction-Assistance Signal Classes

| Signal | Meaning | Permitted Use | Not Permitted |
| --- | --- | --- | --- |
| Complete authorized message context | Prior message wording and sequence from Outlook, Teams, or resolved tickets, retained in the installation-local encrypted vault. | Understand context, terminology, question flow, and prior outcomes while drafting. | Quoting into a shareable report, claiming complete coverage, or treating the message as a permanent trait. |
| `behavioral_pattern` observation | A controlled communication feature derived from subject-authored messages, with support, contradiction, contexts, and sources. | Adjust draft structure when the current context matches. | Diagnosis, motive inference, employee evaluation, or market claim. |
| `explicit_preference` observation | A preference the subject directly confirmed and that the bundle records as subject-confirmed. | Strongest private drafting preference within its stated context. | Generalization beyond the context or evidence of market preference. |
| Response-pattern hypothesis | A recurring response class following a defined trigger, such as asking for evidence, ownership, scope, risk, timing, or implementation detail. | Anticipate information that may be useful to include. | Predict exact words, approval, action, emotion, or intent. |
| Private lexicon or representative example | Repeated terminology or bounded prior wording retained only in the profile store. | Match established vocabulary and avoid needless translation friction. | Imitation, impersonation, or copying private wording into a shareable artifact without a separate reason. |

## First-Party Assistance Signal Classes

| Signal | Meaning | Permitted Use | Not Permitted |
| --- | --- | --- | --- |
| `explicit_fact` | Directly present in a supplied source or record. | Ground the current interaction plan within the source's limits. | Inferring broader authority, intent, or outcome. |
| `user_provided_unverified` | Supplied by the user but not independently confirmed in the current run. | Organize a support candidate and identify missing proof. | Presenting it as documented fact. |
| `bounded_inference` | A reasonable but uncertain reading. | Prepare possible responses and questions. | Presenting motive, emotion, or future behavior as fact. |
| `plausible_alternative` | Another explanation consistent with the known facts. | Reduce premature certainty and interpretation load. | Treating the list as exhaustive. |
| `stakeholder_confirmed` | The relevant stakeholder explicitly confirmed the exact scope or statement. | Support that exact scope. | Generalizing to title, compensation, conversion, or unrelated decision rights. |
| `formally_decided` | The authorized decision owner recorded a decision. | Treat the exact recorded decision as formal evidence. | Predicting later approval or promotion. |

Career review organizes the user's evidence only. It may distinguish measurable results, delegated scope, decision rights, adoption, teammate enablement, sponsor confirmation, executive exposure, title/conversion signals, and learning evidence. It may not compare coworker value or produce a promotion probability.

`user_asserted` career records may identify what to verify, but they never enter `strongestSupportableCase` until their evidence state is upgraded from an inspectable source, stakeholder confirmation, or formal decision. Likewise, a confirmed authority state must link directly to one or more explicit `authority_evidence` facts with inspectable source references; an unrelated fact or an evidence-state label alone is insufficient.

## Automatic-Use Thresholds

A named profile may guide analysis or rewriting automatically only when all collection thresholds are met:

| Requirement | Minimum |
| --- | --- |
| Subject-authored messages | 50 |
| Distinct conversations | 5 |
| Distinct communication contexts | 2 |
| Active days | 30 |
| Observation-window span | 45 days |

The profile must also contain at least one qualified observation:

- A subject-confirmed explicit preference qualifies as `subject_confirmed`.
- A behavioral observation qualifies as `context_supported` only with at least 20 supporting instances, at least 65 percent consistency, and observations in at least two contexts.
- A response-pattern hypothesis qualifies as `context_supported` only with at least 20 supporting instances and at least 65 percent consistency within its trigger context.

Below-threshold patterns remain `tentative`. A below-threshold profile remains `collecting`. Neither may guide a draft automatically.

## Freshness And Context

- A profile expires 90 days after the end of its newest observation window.
- An expired profile is `stale` and cannot guide analysis or rewriting.
- Profile use is valid only when the current communication context matches the contexts recorded for the relevant observation.
- Connector coverage always remains partial.
- Contradictions lower confidence and must not be discarded to make a pattern appear stronger.
- Refreshing a profile recalculates counts, confidence, status, expiry, and the profile hash.

## Identity And Matching Evidence

Actual names are lookup keys, not evidence. Automatic recipient matching requires:

- an exact normalized display-name match
- one confirmed directory or ticket identity
- a matching identity fingerprint
- one active, non-expired profile
- no display-name collision

The workflow may record a private recipient name while confirming the match. Shareable artifacts may retain only a profile id/hash and the fact that bounded assistance was applied. A profile hash proves which private profile version guided the run; it does not prove that the guidance was correct or that the recipient preferred the result.

## Non-Negotiable Rules

- Heuristic findings do not become market facts.
- Synthetic reader stress tests do not become user research.
- Synthetic task-validation fixtures do not become real task evidence.
- Rewrite rankings do not become preference evidence.
- Dashboard history does not become validation.
- PDF generation does not upgrade confidence.
- Full-message access does not become psychological truth.
- Repeated communication does not become a diagnosis or employee evaluation.
- A response-pattern hypothesis does not become an exact prediction.
- A named profile does not support comparison, ranking, promotion, discipline, hiring, or any other employment decision.
- A self profile does not turn operating scope into formal title, compensation, conversion, or decision-right evidence.
- User-asserted company policy is provenance, not independently verified authorization evidence.
- Claims must remain `support_candidate`, `unsupported`, or otherwise limited until mapped evidence supports the exact claim, audience, channel, and context.

## Promotion Requirements

Before a normal message recommendation can be treated as validated, the artifact must record:

- the exact claim or recommendation being supported
- audience and channel context
- method and sample
- source or participant basis
- decision threshold
- limitations
- reviewer or owner
- date and lineage hash

For MVP use, comprehension testing should precede preference, persuasion, conversion, or live-channel testing.

Interaction-profile confidence is not promoted through this market-evidence process. It remains an assistance-only status even when the communication threshold is met.

## Report And Dashboard Language

Reports and dashboards must use visible boundary language:

- `marketEvidenceCreated: false`
- `notMarketEvidence: true`
- a limitation section
- a what-to-test-next section
- simulated result counts separate from validated signal counts

Normal reports, SQLite history, dashboards, and improvement plans must not contain:

- recipient or author names
- full message bodies
- private examples or lexicon
- identity fingerprints
- response-pattern details tied to a named person

A shareable report may say that private interaction assistance was applied and may retain a non-identifying profile hash for lineage. It must not reveal who the profile represents or reproduce the private evidence behind it.

Any output that omits these boundaries or crosses the private-to-normal data boundary is incomplete.

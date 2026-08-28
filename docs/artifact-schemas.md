# Mindfront Artifact Schemas

Version: 0.1.0
Status: Phase 0 schema contract
Sources:

- `docs/ethical-boundaries.md`
- `docs/evidence-policy.md`

This file defines the first validator target for Mindfront artifacts. These are contracts, not implementation classes. The validator should reject unknown enum values, missing required fields, dangling references, unsupported confidence aliases, and outputs that upgrade hypotheses into validated recommendations without mapped evidence.

## Shared Conventions

### Required Artifact Envelope

Every generated artifact must include an envelope with these fields:

| Field | Required | Rule |
| --- | --- | --- |
| `artifactId` | yes | Matches the artifact id pattern for the artifact type. |
| `artifactType` | yes | One of the artifact types in this document. |
| `schemaVersion` | yes | Integer, currently `1`. |
| `runId` | yes | `run-[a-z0-9-]+`. |
| `parentArtifactIds` | yes | Array, empty only for root inputs. |
| `generatedAt` | yes | ISO-8601 timestamp with timezone. |
| `toolVersion` | yes | Semantic version string. |
| `command` | yes | CLI command that generated or validated the artifact. |
| `commandArgs` | yes | Object. |
| `sourceBriefHash` | yes | `sha256:` plus lowercase hex digest, when a brief is involved. |
| `configSetHash` | yes | `sha256:` plus lowercase hex digest. |
| `principleSetHash` | yes | `sha256:` plus lowercase hex digest. |
| `rubricHash` | yes | `sha256:` plus lowercase hex digest. |
| `audienceLensHash` | yes | `sha256:` plus lowercase hex digest. |
| `evidenceHash` | yes | `sha256:` plus lowercase hex digest. |
| `templateHash` | yes | `sha256:` plus lowercase hex digest, or `sha256:not-used` for deterministic outputs with no template. |
| `outputHash` | yes | `sha256:` plus lowercase hex digest for the emitted artifact. |

Invalid example:

```json
{
  "artifactId": "report-001",
  "artifactType": "message_analysis_report",
  "sourceTextHash": "sha256..."
}
```

Reason: missing run id, config hashes, lineage, command, and output hash.

### Canonical Enums

Use only the canonical values from `config/confidence-labels.json`.

`evidenceBasis`:

```text
unsupported
user_provided_unverified
source_evidence
heuristic_inference
synthetic_reader_stress_test
synthetic_task_fixture
local_validation
small_user_test
real_user_data
expert_review
```

`findingConfidence`:

```text
low
medium
high_observable_text_issue
high_source_supported
blocked_sensitive_domain
```

`recommendationState`:

```text
blocked_unsupported
blocked_sensitive_domain
needs_domain_evidence
needs_user_research
needs_expert_review
hypothesis_to_test
ready_for_small_test
locally_checked
small_user_test_supported
validated_for_exact_context
```

Deprecated aliases such as `heuristic_high_confidence`, `psychology_supported_hypothesis`, `requires_user_research`, `requires_domain_evidence`, `unsupported_overclaim`, and `validated_by_real_data` must fail validation after Phase 1.

### Global Cross-Reference Rules

- `sourceIds` must exist in `config/evidence-sources.json`.
- `principleIds` must exist in `config/psychology-principles.json`.
- `dimensionId` must exist in `config/message-quality-rubric.json`.
- `lensId` must exist in `config/audience-lenses.json`.
- `findingIds`, `claimIds`, `recommendationIds`, `variantIds`, and `questionIds` must reference records in the same report bundle.
- Free-text proof without `method`, `sample`, `sourceId`, and `limitations` defaults to `evidenceBasis: user_provided_unverified`.
- Synthetic reader stress tests must include `simulationNotice` and `notMarketEvidence: true`.
- Synthetic reader stress tests cannot produce `small_user_test_supported` or `validated_for_exact_context`.
- Documentation task-observation protocols must use `marketEvidenceCreated: false` and `notMarketEvidence: true`; they are collection handoffs, not evidence.
- Synthetic task-validation fixtures must use `evidenceBasis: synthetic_task_fixture`, `realTaskEvidenceCreated: false`, and cannot produce real-user evidence.
- Mindfront improvement plans must use `marketEvidenceCreated: false` and `notMarketEvidence: true`; they are operational next-action backlogs, not proof of user preference, adoption, conversion, or company-wide performance.
- Sensitive domains cannot move beyond `needs_expert_review` until `expertReviewStatus: completed`.
- Real user data must map the exact claim, audience, channel, and context.

### Score Bounds

All score records use integer scores from `0` through `5`.

- `0` is worst or blocked.
- `5` is strongest or safest.
- Higher is better for every Phase 0 dimension, including `ethical_risk`.
- Every score requires a `calibrationAnchor` from `config/message-quality-rubric.json`.

## Message Brief

Purpose: the root input describing the copy, audience, evidence notes, data boundary, and sensitive-domain context.

Artifact type: `message_brief`

ID pattern: `^brief-[a-z0-9][a-z0-9-]*$`

Required fields:

- `briefId`
- `artifactType`
- `schemaVersion`
- `createdAt`
- `sourceText`
- `targetAudience`
- `channel`
- `desiredAction`
- `dataClassification`
- `containsPersonalData`
- `containsCustomerConfidentialData`
- `llmProcessingAllowed`
- `retentionPolicy`
- `domainContext`
- `sensitiveDomainFlags`
- `expertReviewRequired`
- `expertReviewStatus`
- `blockedClaimTypes`
- `publishReadiness`

Allowed enums:

- `dataClassification`: `public`, `internal`, `confidential`, `sensitive`
- `domainContext`: `general_b2b`, `health`, `finance`, `legal`, `employment`, `housing`, `insurance`, `education`, `security`, `minors`, `crisis`, `political_civic`, `public_benefits`
- `expertReviewStatus`: `not_required`, `required_not_started`, `completed`
- `publishReadiness`: `not_assessed`, `blocked_until_review`, `not_ready`, `ready_for_small_test`

Score bounds: none.

Cross-reference rules:

- Any `evidenceIds` must reference evidence records in the same bundle.
- `llmProcessingAllowed` must be `false` for `confidential` or `sensitive` inputs unless explicit approval is recorded.
- If `domainContext` is not `general_b2b`, `expertReviewRequired` must be true unless the validator has a narrower allow rule.

Lineage fields:

- `sourceBriefHash`
- `sourceTextHash`
- `configSetHash`

Invalid example:

```json
{
  "briefId": "brief-001",
  "sourceText": "This tool helps patients avoid anxiety without therapy.",
  "domainContext": "health",
  "expertReviewRequired": false
}
```

Reason: health context requires expert review gating and data boundary fields.

## Evidence Source

Purpose: registered source metadata that governs whether evidence can support claims, research context, principles, or rubric rules.

Artifact type: `evidence_source`

ID pattern: `^source-[0-9]{3}$`

Required fields:

- `sourceId`
- `label`
- `sourceType`
- `supportTier`
- `allowedUses`
- `llmProcessingAllowed`
- `retentionDays`
- `excerptPolicy`
- `sensitiveDataAllowed`
- `owner`
- `reviewedAt`
- `status`
- `limitations`

Allowed enums:

- Use the enums in `config/evidence-sources.json`.

Score bounds: none.

Cross-reference rules:

- A source used by an evidence record must have `status: active`.
- Sources with `supportTier: unverified_user_provided` cannot create validated claims.
- Sources with `sensitiveDataAllowed: true` must not allow external LLM processing by default.

Lineage fields:

- `reviewedAt`
- `owner`
- `sourceDocuments` when the source is a project policy or plan source.

Invalid example:

```json
{
  "sourceId": "source-notes",
  "label": "Customer quote",
  "supportTier": "real_user_data",
  "limitations": []
}
```

Reason: source id pattern is invalid, required fields are missing, and real user data requires method and exact-context mapping.

## Evidence Record

Purpose: claim-level or research-level evidence tied to a registered source.

Artifact type: `evidence_record`

ID pattern: `^evidence-[a-z0-9][a-z0-9-]*$`

Required fields:

- `evidenceId`
- `sourceId`
- `evidenceType`
- `method`
- `sample`
- `summary`
- `limitations`
- `capturedAt`
- `evidenceBasis`
- `allowedClaimIds`

Allowed enums:

- `evidenceBasis`: canonical enum.
- `evidenceType`: `proof_note`, `interview_note`, `comprehension_test`, `usability_task`, `survey`, `ab_test`, `expert_review`, `metric`, `public_source`, `synthetic_reader_stress_test`

Score bounds: none.

Cross-reference rules:

- `sourceId` must exist and be active.
- `allowedClaimIds` must reference claim records or be empty when the evidence is context only.
- `real_user_data` requires exact `claimId`, `audience`, `channel`, and `context` mapping.
- Free text proof with no method, sample, or limitations must be downgraded to `user_provided_unverified`.

Lineage fields:

- `sourceId`
- `capturedAt`
- `sourceExcerptHash`

Invalid example:

```json
{
  "evidenceId": "evidence-001",
  "sourceId": "source-001",
  "summary": "Customers love it",
  "evidenceBasis": "real_user_data"
}
```

Reason: lacks method, sample, limitations, and exact context mapping.

## Psychology Principle

Purpose: source-owned principle used to justify findings, scores, rewrites, research handoffs, or ethical gates.

Artifact type: `psychology_principle`

ID pattern: `^[a-z][a-z0-9-]*$`

Required fields:

- `principleId`
- `label`
- `status`
- `evidenceBasis`
- `sourceIds`
- `definition`
- `appliesToDimensions`
- `allowedUses`
- `misuseRisks`
- `prohibitedUses`
- `requiredCaveat`
- `reviewedAt`

Allowed enums:

- `status`: `draft`, `accepted_for_phase_0`, `needs_review`, `deprecated`, `blocked`
- `allowedUses`: `finding_rationale`, `rubric_support`, `rewrite_rationale`, `research_handoff`, `ethical_gate`
- `evidenceBasis`: canonical enum.

Score bounds: none.

Cross-reference rules:

- `sourceIds` must exist in the evidence source registry.
- `appliesToDimensions` must reference rubric dimensions.
- Only `accepted_for_phase_0` principles may be used by the analyzer.

Lineage fields:

- `sourceIds`
- `reviewedAt`
- `version`

Invalid example:

```json
{
  "principleId": "pain-first",
  "status": "accepted_for_phase_0",
  "misuseRisks": []
}
```

Reason: banned language, missing source references, and missing misuse risks.

## Audience Lens

Purpose: bounded synthetic stress-test lens that can expose likely comprehension or safety friction without pretending to be research.

Artifact type: `audience_lens`

ID pattern: `^lens-[a-z0-9][a-z0-9-]*$`

Required fields:

- `lensId`
- `label`
- `status`
- `roleFit`
- `defaultEvidenceBasis`
- `notMarketEvidence`
- `purpose`
- `assumptions`
- `reviewQuestions`
- `frictionSignals`
- `safetyRules`
- `blockedUses`
- `recommendedValidation`
- `principleIds`

Allowed enums:

- `status`: `active`, `draft`, `deprecated`, `blocked`
- `roleFit`: `target_user`, `buyer`, `evaluator`, `accessibility_review`, `non_target`
- `defaultEvidenceBasis`: `synthetic_reader_stress_test`, `heuristic_inference`

Score bounds: none.

Cross-reference rules:

- `principleIds` must exist.
- Synthetic outputs from a lens cannot use `real_user_data`.
- A lens must not be named or framed as a real persona panel.

Lineage fields:

- `sourceDocuments`
- `principleIds`
- `reviewedAt` if promoted beyond Phase 0.

Invalid example:

```json
{
  "lensId": "lens-001",
  "label": "Anxious first-time user",
  "notMarketEvidence": false
}
```

Reason: replaced by anxiety-reduction accessibility lens, missing review questions, and not marked as simulated.

## Rubric Dimension

Purpose: scoreable quality dimension with explicit anchors and calibration examples.

Artifact type: `rubric_dimension`

ID pattern: `^[a-z][a-z0-9_]*$`

Required fields:

- `dimensionId`
- `label`
- `scoreScale`
- `higherIsBetter`
- `definition`
- `principleIds`
- `deterministicSignals`
- `scoreAnchors`
- `goldenExampleAnchors`

Allowed enums:

- `scoreScale`: `0_to_5`

Score bounds:

- `0` through `5`, integer only.
- `scoreAnchors` must define all values from `0` through `5`.
- `goldenExampleAnchors` should define at least `1`, `3`, and `5`.

Cross-reference rules:

- `principleIds` must exist.
- Score records using a dimension must cite one score anchor.

Lineage fields:

- `sourceDocuments`
- `version`

Invalid example:

```json
{
  "dimensionId": "clarity",
  "scoreScale": "1_to_10"
}
```

Reason: unsupported scale and missing anchors.

## Claim

Purpose: an explicit or implied claim extracted from the brief, report prose, rewrite, or variant.

Artifact type: `claim`

ID pattern: `^claim-[a-z0-9][a-z0-9-]*$`

Required fields:

- `claimId`
- `claimText`
- `claimType`
- `claimStrength`
- `sourceArtifactId`
- `sourceExcerpt`
- `evidenceBasis`
- `evidenceIds`
- `supportStatus`
- `limitations`
- `sensitiveDomainFlags`

Allowed enums:

- `claimType`: `category`, `feature`, `outcome`, `performance`, `social_proof`, `security`, `compliance`, `health`, `financial`, `legal`, `employment`, `eligibility`, `preference`, `other`
- `claimStrength`: `low`, `moderate`, `strong`, `guaranteed`
- `supportStatus`: `unsupported`, `support_candidate`, `supported_with_limits`, `blocked`, `validated_for_exact_context`
- `evidenceBasis`: canonical enum.

Score bounds: none.

Cross-reference rules:

- `evidenceIds` must exist.
- `claimStrength: guaranteed` requires expert review or real user data, and is blocked in restricted domains unless explicitly allowed by review.
- `supportStatus: validated_for_exact_context` requires exact real-user data or expert review mapping.

Lineage fields:

- `sourceArtifactId`
- `sourceExcerpt`
- `sourceExcerptHash`

Invalid example:

```json
{
  "claimId": "claim-001",
  "claimText": "Users will double productivity in one week.",
  "claimStrength": "guaranteed",
  "supportStatus": "validated_for_exact_context",
  "evidenceIds": []
}
```

Reason: guaranteed quantified claim has no evidence.

## Finding

Purpose: a structured issue or observation produced by the analyzer.

Artifact type: `finding`

ID pattern: `^finding-[a-z0-9][a-z0-9-]*$`

Required fields:

- `findingId`
- `dimensionId`
- `severity`
- `findingConfidence`
- `evidenceBasis`
- `inputExcerpt`
- `issue`
- `whyItMatters`
- `principleIds`
- `rubricDimensionIds`
- `claimIds`
- `recommendedFix`
- `limitation`
- `recommendedValidation`

Allowed enums:

- `severity`: `low`, `medium`, `high`, `blocked`
- `findingConfidence`: canonical enum.
- `evidenceBasis`: canonical enum.

Score bounds: none.

Cross-reference rules:

- `dimensionId` and `rubricDimensionIds` must exist in the rubric.
- `principleIds` must exist.
- `claimIds` must reference claim records when the finding is claim-related.
- `high_observable_text_issue` requires an observable text property.

Lineage fields:

- `sourceBriefId`
- `sourceTextHash`
- `generatedAt`
- `toolVersion`
- `configVersion`

Invalid example:

```json
{
  "findingId": "finding-001",
  "dimensionId": "clarity",
  "confidenceLabel": "heuristic_high_confidence"
}
```

Reason: deprecated overloaded confidence label and missing evidence basis, issue, rationale, and references.

## Motivation Friction Report

Purpose: a deterministic map of likely reader motivation, friction, objections, and trust gaps.

Artifact type: `motivation_friction_report`

Required fields:

- `motivationScore`
- `frictionCategories`
- `objectionMap`
- `trustGapReport`
- `limitations`

Friction categories:

- `unclear_value`
- `unclear_category`
- `unclear_time_relevance`
- `no_proof`
- `high_perceived_effort`
- `high_perceived_risk`
- `wrong_audience`
- `premature_cta`
- `jargon_barrier`

Score bounds:

- `motivationScore.score` uses integer values from `0` through `5`.
- Every score must include `calibrationAnchor`.

Cross-reference rules:

- `objectionMap[].categoryId` must reference a friction category in the same report.
- `objectionMap[].sourceFindingIds` must reference findings when the objection came from a finding.
- `trustGapReport.separatedFromClarityGap` must be true.
- Trust gaps must stay separate from clarity gaps.

Invalid example:

```json
{
  "artifactType": "motivation_friction_report",
  "motivationScore": {"score": 5},
  "trustGapReport": {"separatedFromClarityGap": false}
}
```

Reason: missing score anchor and trust gaps are not separated from clarity.

## Score

Purpose: dimension-level score with rationale and traceability to findings.

Artifact type: `score`

ID pattern: `^score-[a-z0-9][a-z0-9-]*$`

Required fields:

- `scoreId`
- `dimensionId`
- `score`
- `scoreScale`
- `scoreReason`
- `findingIds`
- `calibrationAnchor`
- `evidenceBasis`
- `findingConfidence`

Allowed enums:

- `scoreScale`: `0_to_5`
- `evidenceBasis`: canonical enum.
- `findingConfidence`: canonical enum.

Score bounds:

- `score` must be an integer from `0` through `5`.

Cross-reference rules:

- `dimensionId` must exist.
- `findingIds` must reference findings in the same report.
- `calibrationAnchor` must match the selected dimension's anchors.

Lineage fields:

- `sourceBriefId`
- `sourceTextHash`
- `configVersion`
- `rubricHash`

Invalid example:

```json
{
  "scoreId": "score-001",
  "dimensionId": "clarity",
  "score": 7
}
```

Reason: score exceeds the 0 to 5 scale and lacks rationale.

## Recommendation

Purpose: an action recommendation tied to findings, claims, evidence, and validation needs.

Artifact type: `recommendation`

ID pattern: `^recommendation-[a-z0-9][a-z0-9-]*$`

Required fields:

- `recommendationId`
- `summary`
- `recommendationState`
- `evidenceBasis`
- `findingIds`
- `claimIds`
- `principleIds`
- `recommendedAction`
- `limitation`
- `recommendedValidation`
- `blockedReasons`

Allowed enums:

- `recommendationState`: canonical enum.
- `evidenceBasis`: canonical enum.

Score bounds: none.

Cross-reference rules:

- `findingIds`, `claimIds`, and `principleIds` must exist.
- `blockedReasons` must be non-empty for `blocked_unsupported` or `blocked_sensitive_domain`.
- `validated_for_exact_context` requires real-user data or expert review mapped to exact claim, audience, channel, and context.

Lineage fields:

- `sourceBriefId`
- `sourceTextHash`
- `configSetHash`
- `evidenceHash`

Invalid example:

```json
{
  "recommendationId": "recommendation-001",
  "recommendationState": "validated_by_real_data",
  "evidenceBasis": "synthetic_reader_stress_test"
}
```

Reason: deprecated state and synthetic output cannot validate a recommendation.

## Copy Variant

Purpose: a rewrite or message variant with strategy, tradeoffs, and claim-diff result.

Artifact type: `copy_variant`

ID pattern: `^variant-[a-z0-9][a-z0-9-]*$`

Required fields:

- `variantId`
- `strategyId`
- `copy`
- `intendedEffect`
- `tradeoffs`
- `introducedClaimIds`
- `preservedClaimIds`
- `removedClaimIds`
- `recommendationState`
- `evidenceBasis`
- `requiresProofBeforePublishing`
- `claimGateStatus`
- `recommendedValidation`

Allowed enums:

- `strategyId`: `plain_english_clarity`, `proof_first`, `problem_first`, `risk_reduction`, `technical_precision`, `cta_clarity`
- `claimGateStatus`: `not_run`, `passed`, `blocked_new_unsupported_claim`, `needs_review`
- `recommendationState`: canonical enum.
- `evidenceBasis`: canonical enum.

Score bounds: none.

Cross-reference rules:

- Introduced, preserved, and removed claim ids must reference claim records.
- Variant cannot be `ready_for_small_test` if `claimGateStatus` is not `passed`.
- Variant must not introduce unsupported quantified claims.

Lineage fields:

- `parentArtifactIds`
- `sourceBriefHash`
- `templateHash`
- `outputHash`

Invalid example:

```json
{
  "variantId": "variant-001",
  "copy": "Guaranteed to double productivity.",
  "claimGateStatus": "not_run",
  "recommendationState": "ready_for_small_test"
}
```

Reason: variant contains a strong claim and cannot be ready before claim gate passes.

## Variant Comparison Report

Purpose: a deterministic ranking of gated copy variants for choosing candidates to test.

Artifact type: `variant_comparison_report`

ID pattern: `^comparison-[a-z0-9][a-z0-9-]*$`

Required fields:

- `comparisonId`
- `sourceVariantBundleId`
- `briefId`
- `summary`
- `rankedVariants`
- `recommendedVariantIds`
- `recommendationState`
- `evidenceBasis`
- `claimGateSummary`
- `marketEvidenceCreated`
- `recommendedValidation`
- `limitations`
- `sourceBriefHash`
- `sourceTextHash`
- `sourceVariantBundleHash`
- `configSetHash`
- `outputHash`

Allowed enums:

- `recommendationState`: canonical enum.
- `evidenceBasis`: canonical enum.
- ranked variant `claimGateStatus`: `passed`, `blocked_new_unsupported_claim`, `needs_review`

Score bounds:

- Deterministic dimension scores use integers from `0` through `5`.
- Higher scores mean a stronger local text-quality signal for the named dimension.

Cross-reference rules:

- Every `variantId` in `recommendedVariantIds` must exist in `rankedVariants`.
- Blocked variants cannot be recommended for testing.
- `marketEvidenceCreated` must be false.
- Top-ranked variants are test candidates only, not winners.

Lineage fields:

- `sourceVariantBundleId`
- `sourceVariantBundleHash`
- `sourceBriefHash`
- `sourceTextHash`
- `configSetHash`

Invalid example:

```json
{
  "comparisonId": "comparison-001",
  "summary": "Variant 2 will convert best.",
  "marketEvidenceCreated": true,
  "recommendedVariantIds": ["variant-blocked"]
}
```

Reason: deterministic comparison cannot create market evidence, conversion claims, or recommend blocked variants.

## Reader Stress Test Result

Purpose: optional synthetic reader stress-test output, explicitly marked as simulated and not market evidence.

Artifact type: `reader_stress_test_result`

ID pattern: `^stress-[a-z0-9][a-z0-9-]*$`

Required fields:

- `stressTestId`
- `lensId`
- `simulationNotice`
- `notMarketEvidence`
- `sourceArtifactId`
- `observedFriction`
- `findingIds`
- `recommendationState`
- `evidenceBasis`
- `recommendedValidation`
- `limitations`

Allowed enums:

- `evidenceBasis`: `synthetic_reader_stress_test`
- `recommendationState`: `blocked_unsupported`, `needs_user_research`, `hypothesis_to_test`

Score bounds: none.

Cross-reference rules:

- `lensId` must exist.
- `notMarketEvidence` must be true.
- Must not generate `validated_for_exact_context`, `small_user_test_supported`, or `real_user_data`.

Lineage fields:

- `sourceArtifactId`
- `parentArtifactIds`
- `audienceLensHash`
- `templateHash`

Invalid example:

```json
{
  "stressTestId": "stress-001",
  "lensId": "lens-target-user-comprehension",
  "notMarketEvidence": false,
  "recommendationState": "validated_for_exact_context"
}
```

Reason: synthetic result is not market evidence and cannot validate a recommendation.

## Reader Stress Test Report

Purpose: a bundle of configured audience-lens stress-test results for one analysis report.

Artifact type: `reader_stress_test_report`

Required fields:

- `stressReportId`
- `sourceAnalysisReportId`
- `simulationNotice`
- `notMarketEvidence`
- `marketEvidenceCreated`
- `evidenceBasis`
- `results`
- `recommendedValidation`
- `limitations`
- `sourceAnalysisHash`
- `audienceLensHash`
- `sourceBriefHash`
- `sourceTextHash`
- `configSetHash`
- `outputHash`

Cross-reference rules:

- `results[].lensId` must exist in `config/audience-lenses.json`.
- `results[].findingIds` must reference findings in the source analysis report.
- `marketEvidenceCreated` must be false.
- Every embedded result must satisfy the Reader Stress Test Result rules.

Invalid example:

```json
{
  "artifactType": "reader_stress_test_report",
  "notMarketEvidence": false,
  "marketEvidenceCreated": true,
  "evidenceBasis": "real_user_data"
}
```

Reason: stress-test reports are simulated and cannot create real user evidence.

## Research Question

Purpose: runnable user-validation or research handoff question tied to uncertainty and decision threshold.

Artifact type: `research_question`

ID pattern: `^research-[a-z0-9][a-z0-9-]*$`

Required fields:

- `questionId`
- `uncertainty`
- `method`
- `evidenceGradeTarget`
- `sampleSource`
- `sampleSize`
- `screenerCriteria`
- `roleFit`
- `protocolVersion`
- `biasRisks`
- `consentScript`
- `sensitiveDataAvoidance`
- `deceptionUsed`
- `minorOrVulnerableParticipantRule`
- `stopConditions`
- `decisionThreshold`
- `relatedFindingIds`
- `relatedClaimIds`

Allowed enums:

- `method`: `user_interview`, `comprehension_test`, `usability_task`, `preference_test`, `survey`, `ab_test`
- `evidenceGradeTarget`: `exploratory`, `directional`, `statistically_supported`
- `roleFit`: `target_user`, `buyer`, `evaluator`, `non_target`

Score bounds: none.

Cross-reference rules:

- `relatedFindingIds` must reference findings.
- Preference tests must not be treated as behavior proof.
- Exploratory thresholds must not be described as statistically meaningful.
- A/B test recommendations must include sample-size caveat.
- Phase 1 should prefer comprehension tests before persuasion or motivation tests.

Lineage fields:

- `sourceBriefId`
- `sourceTextHash`
- `relatedFindingIds`
- `relatedClaimIds`

Invalid example:

```json
{
  "questionId": "research-001",
  "method": "preference_test",
  "evidenceGradeTarget": "statistically_supported",
  "sampleSize": 5,
  "decisionThreshold": "Whichever version people like is proven better."
}
```

Reason: small preference test cannot be treated as statistically supported behavior proof.

## Research Plan

Purpose: runnable research handoff that converts analysis uncertainty into real-world validation work.

Artifact type: `research_plan`

ID pattern: `^research-plan-[a-z0-9][a-z0-9-]*$`

Required fields:

- `artifactType`
- `researchPlanId`
- `sourceAnalysisReportId`
- `briefId`
- `summary`
- `evidenceBasis`
- `marketEvidenceCreated`
- `notMarketEvidence`
- `recommendedSequence`
- `questions`
- `uncertaintyCoverage`
- `motivationFrictionCoverage`
- `trustGapCoverage`
- `interviewScript`
- `surveyQuestions`
- `usabilityTasks`
- `abHypotheses`
- `decisionSummary`
- `limitations`
- `sourceAnalysisHash`
- `sourceBriefHash`
- `sourceTextHash`
- `configSetHash`
- `outputHash`

Cross-reference rules:

- `questions[]` must satisfy the Research Question rules.
- Every medium, high, or blocked source finding must appear in `uncertaintyCoverage`.
- Covered findings must reference at least one `questions[].questionId`.
- Motivation objections from the source analysis must appear in `motivationFrictionCoverage`.
- Trust gaps from the source analysis must appear in `trustGapCoverage`.
- `interviewScript.items[].questionId`, `surveyQuestions[].questionId`, and `usabilityTasks[].questionId` must reference generated questions.
- `abHypotheses[]` must include sample-size and exact-context caveats.
- `marketEvidenceCreated` must be false.
- `notMarketEvidence` must be true.
- `evidenceBasis` must not be `real_user_data`.
- Comprehension validation must appear before preference or live-channel testing.

Required generated sections:

- normalized research questions
- interview script
- survey questions
- usability tasks
- A/B hypotheses
- decision summary

Invalid example:

```json
{
  "artifactType": "research_plan",
  "marketEvidenceCreated": true,
  "questions": [
    {
      "questionId": "research-001",
      "method": "ab_test",
      "decisionThreshold": "Pick whichever one wins."
    }
  ]
}
```

Reason: a research plan creates a validation handoff, not market evidence, and A/B plans need sample-size and context caveats.

## Documentation Task Observation Protocol

Purpose: a no-PII handoff for collecting exact-context documentation task observations.

Artifact type: `documentation_task_observation_protocol`

Required fields:

- `artifactType`
- `protocolId`
- `sourceAnalysisReportId`
- `sourceResearchPlanId`
- `briefId`
- `documentId`
- `documentType`
- `targetAudience`
- `observationSource`
- `evidenceCollectionMethod`
- `marketEvidenceCreated`
- `notMarketEvidence`
- `dataBoundary`
- `evidenceBoundary`
- `consentScript`
- `stopConditions`
- `participantTokenRule`
- `observerInstructions`
- `tasks`
- `sessionTemplateColumns`
- `taskValidationInputDefaults`
- `limitations`
- `sourceAnalysisHash`
- `sourceResearchPlanHash`
- `sourceBriefHash`
- `sourceTextHash`
- `configSetHash`
- `outputHash`

Required CSV columns:

- `sessionId`
- `participantToken`
- `roleSegment`
- `taskId`
- `completed`
- `skimToAnswerSeconds`
- `followUpQuestionCount`
- `skippedSectionCount`
- `expertRespectRating`
- `reuseIntentRating`
- `trustObjectionCodes`

Cross-reference rules:

- `sourceAnalysisReportId` must reference the supplied analysis report.
- `sourceResearchPlanId`, when present, must reference a matching research plan.
- `tasks[].taskId` must be stable and must match the session CSV `taskId` values used later.
- `sessionTemplateColumns` must not include names, emails, raw comments, transcripts, quotes, notes, or free-text fields.
- `taskValidationInputDefaults` must declare no personal data, no customer-confidential data, and no LLM processing.
- `marketEvidenceCreated` must be false.
- `notMarketEvidence` must be true.
- The protocol must not include raw participant observations.

Invalid example:

```json
{
  "artifactType": "documentation_task_observation_protocol",
  "marketEvidenceCreated": false,
  "notMarketEvidence": false,
  "sessionTemplateColumns": ["participantEmail", "rawComments"]
}
```

Reason: protocols are not market evidence, and session templates cannot collect identifying or raw-comment fields.

## Documentation Task Validation Input

Purpose: a local input artifact for no-PII documentation task observations or synthetic workflow fixtures.

Artifact type: `documentation_task_validation_input`

Required fields:

- `artifactType`
- `validationId`
- `observationSource`
- `sourceAnalysisReportId`
- `briefId`
- `documentId`
- `documentType`
- `targetAudience`
- `evidenceCollectionMethod`
- `containsPersonalData`
- `containsCustomerConfidentialData`
- `llmProcessingAllowed`
- `tasks`
- `sessions`

Optional lineage fields:

- `sourceProtocolId`
- `sourceProtocolHash`
- `sourceSessionsHash`
- `sourceSessionsProvenance`
- `provenanceBoundary`

Allowed enums:

- `observationSource`: `real_task_observation`, `synthetic_fixture`

Provenance rules:

- `task-input` defaults to `observationSource: synthetic_fixture`.
- `real_task_observation` is valid only when the caller explicitly declares the filled CSV contains real no-PII task observations collected from the source protocol.
- Generated, sample, or test-filled CSV rows must stay `synthetic_fixture`.
- Generated `task-input` artifacts must include `sourceSessionsProvenance` and `provenanceBoundary` explaining whether rows were caller-declared real observations or synthetic/test rows.

Session required fields:

- `sessionId`
- `participantToken`
- `roleSegment`
- `taskId`
- `completed`
- `skimToAnswerSeconds`
- `followUpQuestionCount`
- `skippedSectionCount`
- `expertRespectRating`
- `reuseIntentRating`
- `trustObjectionCodes`

Cross-reference rules:

- `tasks[].taskId` must exist for every `sessions[].taskId`.
- `completed` must be a JSON boolean, not a string.
- Count fields must be non-negative integers.
- `participantToken` and `sessionId` must be short non-identifying tokens.
- `trustObjectionCodes` must be coded categories, not raw participant comments.
- `containsPersonalData`, `containsCustomerConfidentialData`, and `llmProcessingAllowed` must all be false.
- If source protocol fields are present, they must be strings and point to the protocol/session files used to generate the input.

Invalid example:

```json
{
  "artifactType": "documentation_task_validation_input",
  "observationSource": "real_task_observation",
  "containsPersonalData": false,
  "sessions": [
    {
      "sessionId": "alice@example.com",
      "completed": "false",
      "trustObjections": ["I do not trust the source table."]
    }
  ]
}
```

Reason: the session id is identifying, `completed` is a string, and raw trust-objection text is not allowed.

## Documentation Task Validation Result

Purpose: aggregate task-validation output for the Executive Impact Loop.

Artifact type: `documentation_task_validation_result`

Required fields:

- `artifactType`
- `validationResultId`
- `sourceValidationId`
- `observationSource`
- `sourceAnalysisReportId`
- `briefId`
- `documentId`
- `documentType`
- `targetAudience`
- `evidenceBasis`
- `evidenceGrade`
- `marketEvidenceCreated`
- `notMarketEvidence`
- `realTaskEvidenceCreated`
- `rawParticipantDataStored`
- `dataBoundary`
- `sample`
- `tasks`
- `aggregateMetrics`
- `baselineMetrics`
- `beforeAfterDeltas`
- `executiveSignals`
- `decisionState`
- `recommendedNextStep`
- `limitations`
- `sourceInputHash`
- optional `sourceProtocolId`
- optional `sourceProtocolHash`
- optional `sourceSessionsHash`
- `sourceAnalysisHash`
- `outputHash`

Cross-reference rules:

- `observationSource: real_task_observation` must use `evidenceBasis: small_user_test`, `evidenceGrade: exact_context_directional`, and `realTaskEvidenceCreated: true`.
- `observationSource: synthetic_fixture` must use `evidenceBasis: synthetic_task_fixture`, `evidenceGrade: synthetic_fixture_only`, `realTaskEvidenceCreated: false`, and `decisionState: synthetic_fixture_only`.
- `marketEvidenceCreated` must be false.
- `notMarketEvidence` must be true.
- `rawParticipantDataStored` must be false.
- `sample.taskAttemptCount` must equal `aggregateMetrics.taskAttemptCount`.
- `sample.participantCount` cannot exceed `sample.sessionCount`.
- Executive signals must use the evidence basis derived from `observationSource` and keep `notMarketEvidence: true`.
- Result payloads must not contain `small_user_test_supported` or `validated_for_exact_context`.

Invalid example:

```json
{
  "artifactType": "documentation_task_validation_result",
  "observationSource": "synthetic_fixture",
  "evidenceBasis": "small_user_test",
  "evidenceGrade": "exact_context_directional",
  "realTaskEvidenceCreated": true,
  "marketEvidenceCreated": false
}
```

Reason: synthetic fixtures cannot be promoted into real task evidence.

## Mindfront Improvement Plan

Purpose: ranked operational backlog for the next Codex documentation pass, derived from stored Mindfront history.

Artifact type: `mindfront_improvement_plan`

Required fields:

- `planId`
- `dbPath`
- `briefId`
- `runCount`
- `actionCount`
- `priorityActions`
- `loopReadiness`
- `sourceHistoryComparison`
- `evidenceBoundary`
- `dataBoundary`
- `marketEvidenceCreated`
- `notMarketEvidence`
- `generatedAt`
- `toolVersion`
- `outputHash`

Required gates:

- `marketEvidenceCreated` must be `false`.
- `notMarketEvidence` must be `true`.
- `priorityActions[*].evidenceBoundary` must state that the action is operational planning only.
- Synthetic task-validation fixtures cannot create `reduce_documentation_task_friction` actions.
- Real task-validation actions must remain exact-context directional and cannot become market, adoption, or company-wide impact proof.
- The plan must not include raw source text, participant names, emails, raw comments, transcripts, or other personal data.

Invalid example:

```json
{
  "artifactType": "mindfront_improvement_plan",
  "marketEvidenceCreated": true,
  "priorityActions": [
    {
      "actionType": "publish_company_wide_claim",
      "recommendedAction": "Claim documentation performance is proven."
    }
  ]
}
```

Reason: an improvement plan is a backlog, not proof.

## Audit Report Bundle

Purpose: local report-ready bundle that packages validated Mindfront artifacts into JSON, Markdown, editable HTML, and CSV report outputs.

Artifact type: `audit_report_bundle`

ID pattern: `^audit-report-[a-z0-9][a-z0-9-]*$`

Required fields:

- `artifactType`
- `reportBundleId`
- `sourceAnalysisReportId`
- `briefId`
- `summary`
- `marketEvidenceCreated`
- `notMarketEvidence`
- `evidenceBoundary`
- `includedArtifactIds`
- `missingOptionalArtifacts`
- `sections`
- `reportOutputManifest`
- `sourceHashes`
- `sourceBriefHash`
- `sourceTextHash`
- `configSetHash`
- `confidenceLabelHash`
- `templateHash`
- `outputHash`

Required sections:

- `shortVersion`
- `confidenceLabels`
- `scorecard`
- `messageDiagnosis`
- `documentationQuality`
- `taskProtocol`
- `taskValidation`
- `claimProofMap`
- `motivationAndFriction`
- `copyVariants`
- `syntheticAudienceReview`
- `whatToTestNext`
- `limitations`

Required manifest fields:

- `jsonPath`
- `markdownPath`
- `editableSourcePath`
- `spreadsheetPath`
- `documentationHandoffPath`
- `finalOutputPath`
- `pdfStatus`
- `pdfSourceEditablePath`
- `pdfFinalOutputPath`
- `pdfPlannedOutputPath`
- `pdfVerificationStatus`
- `pdfInstruction`

Cross-reference rules:

- `sourceAnalysisReportId` must reference the supplied analysis report.
- Optional variants must reference the supplied analysis report.
- Optional comparison must reference the supplied variant bundle.
- Optional stress-test and research-plan artifacts must reference the supplied analysis report.
- Optional task-observation protocol artifacts must reference the supplied analysis report and keep `notMarketEvidence: true`.
- `confidenceLabels.labels[]` must use ids from `config/confidence-labels.json` when available.
- `claimProofMap.claims[]` must preserve unsupported, support-candidate, blocked, or validated claim status from the source analysis.
- `whatToTestNext.items[]` must come from the research plan when supplied, otherwise from analysis recommendations.
- `taskProtocol` must preserve the protocol evidence boundary when supplied.
- `limitations.items[]` must include source limitations and a report-packaging limitation.
- `marketEvidenceCreated` must be false.
- `notMarketEvidence` must be true.
- `pdfStatus` must be `not_generated_by_cli` unless a separate document workflow records a rendered and verified PDF.
- `documentationHandoffPath` must point to instructions for rendering the editable HTML through the document workflow.
- `pdfPlannedOutputPath` must point to the intended PDF path when directory output is used.
- `pdfVerificationStatus` must stay `not_run` until render and QA evidence exists.
- Visual polish must not upgrade `evidenceBasis`, `findingConfidence`, `recommendationState`, or claim support status.

Invalid example:

```json
{
  "artifactType": "audit_report_bundle",
  "marketEvidenceCreated": true,
  "sections": {
    "confidenceLabels": {
      "labels": [
        {
          "id": "validated_for_exact_context"
        }
      ]
    }
  }
}
```

Reason: a report is a packaging layer. It cannot create evidence or upgrade confidence.

## History Store And Dashboard Artifacts

Purpose: local persistence and static dashboard artifacts for comparing Mindfront runs over time.

Artifact types:

- `history_store_init_result`
- `history_store_result`
- `history_analysis_list`
- `history_comparison_report`
- `history_store_export`
- `history_stale_state_check`
- `history_store_delete_result`
- `static_dashboard_bundle`

SQLite tables:

- `schema_meta`
- `runs`
- `scores`
- `findings`
- `claims`
- `variants`
- `stale_state`
- `task_validations`

Required run fields:

- `run_id`
- `brief_id`
- `summary`
- `validation_state`
- `sensitive_domain_state`
- `data_classification`
- `source_text_hash`
- `source_brief_hash`
- `config_set_hash`
- `generated_at`
- `stored_at`
- `artifact_paths_json`
- `artifact_hashes_json`
- `market_evidence_created`
- `simulated_result_count`
- `validated_signal_count`
- `task_validation_signal_count`

Dashboard required fields:

- `artifactType`
- `dashboardId`
- `dbPath`
- `schemaVersion`
- `summary`
- `runs`
- `scoreChanges`
- `repeatedFailures`
- `taskProtocols`
- `taskValidations`
- `evidenceSeparation`
- `evidenceBoundary`
- `marketEvidenceCreated`
- `notMarketEvidence`
- `generatedAt`

Cross-reference rules:

- Store ingest must reject optional artifacts that do not reference the supplied source analysis or variant bundle.
- Stored runs must include source text, source brief, config set, and artifact output hashes.
- Store rows must keep simulated result counts separate from validated signal counts.
- Store rows must keep exact-context task-validation signal counts separate from validated analysis signal counts.
- Store and dashboard rows must keep task-observation protocols separate from task-validation evidence.
- Synthetic task-validation fixture rows must not increment `validated_signal_count` or `task_validation_signal_count`.
- `validated_signal_count` must not include synthetic reader stress-test results.
- Dashboard rows must include validation state, sensitive-domain state, stale state, simulated result count, validated signal count, and task-validation signal count.
- Dashboard protocol rows must include protocol id, task count, artifact path, `marketEvidenceCreated`, `notMarketEvidence`, and a collection-handoff interpretation.
- Stale-state checks must compare stored artifact paths and hashes against current files and mark changed or missing artifacts as stale.
- Export must include summaries, hashes, excerpts, and status fields rather than full raw source text by default.
- Delete-run must remove dependent score, finding, claim, variant, and stale-state rows.
- `marketEvidenceCreated` must be false for store and dashboard artifacts.

Invalid example:

```json
{
  "artifactType": "static_dashboard_bundle",
  "summary": {
    "simulatedResultCount": 5,
    "validatedSignalCount": 5,
    "taskValidationSignalCount": 5
  },
  "evidenceBoundary": "The simulated panel validated the message."
}
```

Reason: simulated stress-test output cannot be counted as validated evidence.

## Analysis Report

Purpose: validated bundle containing the scorecard, findings, claim/proof map, recommendations, rewrite, research handoff, limitations, and envelope.

Artifact type: `message_analysis_report`

ID pattern: `^report-[a-z0-9][a-z0-9-]*$`

Required fields:

- artifact envelope fields
- `reportId`
- `briefId`
- `summary`
- `dataClassification`
- `evidenceBasisSummary`
- `scores`
- `claims`
- `findings`
- `recommendations`
- `copyVariants`
- `researchQuestions`
- `limitations`
- `unsupportedClaimsVisible`
- `sensitiveDomainState`
- `validationState`

Allowed enums:

- `dataClassification`: same as message brief.
- `validationState`: `not_validated`, `valid`, `failed`, `blocked`
- `sensitiveDomainState`: `not_sensitive`, `restricted_needs_review`, `disallowed_blocked`, `review_completed`

Score bounds:

- All embedded scores must follow the 0 to 5 rule.

Cross-reference rules:

- All embedded references must resolve within the report bundle or config registries.
- Report prose cannot introduce new claims that are absent from `claims`.
- Unsupported claims must remain visible.
- Report polish cannot upgrade confidence.

Lineage fields:

- Full artifact envelope.
- `runManifestId`.

Invalid example:

```json
{
  "reportId": "report-001",
  "summary": "The market will prefer the rewrite.",
  "unsupportedClaimsVisible": false,
  "scores": []
}
```

Reason: market preference claim is unsupported, unsupported claims are hidden, and score records are missing.

## Run Manifest

Purpose: record exact inputs, config hashes, command args, generated artifacts, and stale-state determinants.

Artifact type: `run_manifest`

ID pattern: `^run-[a-z0-9][a-z0-9-]*$`

Required fields:

- `runId`
- `schemaVersion`
- `startedAt`
- `finishedAt`
- `toolVersion`
- `command`
- `commandArgs`
- `inputArtifacts`
- `generatedArtifacts`
- `sourceBriefHash`
- `configSetHash`
- `principleSetHash`
- `rubricHash`
- `audienceLensHash`
- `evidenceHash`
- `templateHash`
- `validationState`
- `staleIfChanged`

Allowed enums:

- `validationState`: `not_validated`, `valid`, `failed`, `blocked`
- `staleIfChanged`: `source_text`, `evidence_record`, `principle`, `rubric`, `audience_lens`, `prompt_template`, `command_option`

Score bounds: none.

Cross-reference rules:

- `generatedArtifacts` must include the emitted artifact ids and hashes.
- Any changed source text, evidence record, principle, rubric, audience lens, prompt/template, or command option invalidates prior publish-ready, dashboard-ready, or validated states until rerun.

Lineage fields:

- The manifest is the lineage root for one run.

Invalid example:

```json
{
  "runId": "run-001",
  "command": "mindfront analyze",
  "generatedArtifacts": [
    "message-analysis-report.json"
  ]
}
```

Reason: missing hashes, command args, validation state, and stale-state rules.

## Private First-Party Workplace Assistance

These private artifacts use a separate compact envelope because they are not normal report/history artifacts.

### Self-declared profile

Artifact type: `self_declared_workplace_assistance_profile`

Required controls:

- `selfDeclared: true`
- `purpose: autistic_workplace_communication_accommodation`
- user-declared career goals, strengths, communication risks, support preferences, authenticity constraints, and energy protections
- `careerAccountabilityModel: single_point_of_accountability_with_distributed_ownership`
- `authorization.humanReviewRequired: true`
- `authorization.automaticSendingAllowed: false`
- `authorization.coworkerEvaluationAllowed: false`
- `authorization.profileBelongsToCurrentUser: true`

The encrypted envelope is `mindfront_encrypted_self_assistance_profile_store` with `encryption: aes_256_gcm_local_key_v1`. The profile is excluded from normal history.

### Workplace assistance request

Artifact type: `workplace_assistance_request`

Modes:

- `preflight`
- `interpret`
- `debrief`
- `career_review`

Inputs keep fact status, authority state, contributor ownership, decisions, commitments, unresolved items, energy state, and career-evidence state explicit. Confirmed authority states require `authority.evidenceFactIds` that resolve to explicit `authority_evidence` facts with inspectable `sourceReference` values. Unknown fields, missing or unqualified authority links, auto-send, coworker evaluation, motive-as-fact, promotion prediction, secrets, and controlled-content markers fail closed.

### Workplace assistance result

Artifact type: `workplace_assistance_result`

Required boundaries:

- facts and unverified claims remain separate from bounded inferences
- preflight `leadingFacts` contains only explicit facts; `leadingUnverifiedClaims` and `leadingEvidence` preserve user-asserted content and its status without relabeling it
- `authorityBasis` preserves the authority state, evidence state, and exact linked fact IDs
- `strongestSupportableCase` excludes `user_asserted` career records while listing those records separately as candidates to verify
- interpretation includes multiple plausible alternatives
- `humanReviewRequired: true`
- `automaticSendingAllowed: false`
- `coworkerEvaluationAllowed: false`
- `promotionPredictionCreated: false`
- `diagnosisCreated: false`
- `marketEvidenceCreated: false`
- `privateArtifact: true`
- `normalHistoryEligible: false`

## First Validator Minimum

The first validator should implement these checks before analysis logic exists:

1. JSON is parseable.
2. Required config files are present.
3. IDs match patterns.
4. Enums use canonical values.
5. Deprecated confidence aliases are rejected or flagged by phase.
6. Config cross-references resolve.
7. Rubric score anchors cover 0 through 5.
8. Audience lenses include simulation boundaries.
9. Sensitive domains require expert-review gating.
10. Synthetic evidence cannot be treated as real validation.

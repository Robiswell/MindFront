# Mindfront Research Method Policy

Status: Phase 0 policy.
The public repository policies in `docs/ethical-boundaries.md` and `docs/evidence-policy.md` are authoritative.

## Purpose

Mindfront research handoffs must be runnable and honest about evidence quality. A research question is not valid just because it sounds specific. It must name the uncertainty, method, participants, bias risks, stop conditions, and the decision threshold that would change the recommendation.

## Required Research Question Contract

Every research question must include:

```json
{
  "questionId": "research-001",
  "uncertainty": "What is unknown?",
  "method": "user_interview | comprehension_test | usability_task | preference_test | survey | ab_test",
  "evidenceGradeTarget": "exploratory | directional | statistically_supported",
  "sampleSource": "where participants come from",
  "sampleSize": 5,
  "screenerCriteria": ["role match", "channel familiarity"],
  "roleFit": "target_user | buyer | evaluator | non_target",
  "protocolVersion": "0.1",
  "biasRisks": ["leading question risk"],
  "consentScript": "Short consent language",
  "sensitiveDataAvoidance": "Do not collect personal health, financial, legal, or protected-class details.",
  "deceptionUsed": false,
  "minorOrVulnerableParticipantRule": "Do not recruit minors or vulnerable participants for MVP tests.",
  "stopConditions": ["participant distress", "request to stop", "sensitive disclosure"],
  "decisionThreshold": "What result changes the recommendation?"
}
```

Recommended additional fields:

```json
{
  "relatedFindingIds": ["finding-001"],
  "relatedClaimIds": ["claim-001"],
  "channelContext": "landing_page",
  "artifactUnderTestIds": ["variant-001"],
  "analysisLimitation": "No real target-user data has been collected yet."
}
```

## Method Selection

| Method | Use When | Do Not Claim |
| --- | --- | --- |
| `comprehension_test` | Need to know whether target readers understand the category, user, value, or next action. | Preference, purchase intent, or conversion lift. |
| `user_interview` | Need to explore why copy is confusing, credible, or relevant. | Statistical prevalence. |
| `usability_task` | Need to test whether a reader can complete a message-driven action. | Broad market demand. |
| `preference_test` | Need directional preference between two wordings. | Actual behavior, conversion, or durable preference. |
| `survey` | Need directional evidence from a defined sample. | Statistical support unless sample, design, and analysis support it. |
| `ab_test` | Need behavioral comparison in a live channel. | General truth beyond the exact audience, channel, and test setup. |

Comprehension tests should lead Phase 1 validation before persuasion, motivation, or preference testing.

## Evidence Grades

| Grade | Meaning | Minimum Standard |
| --- | --- | --- |
| `exploratory` | Helps discover likely issues or hypotheses. | Clear target, method, protocol, and limitations. |
| `directional` | Suggests a likely direction for a specific context. | Role-fit sample, consistent protocol, clear decision threshold. |
| `statistically_supported` | Supports a measured claim for a defined context. | Adequate sample, design, analysis, and caveats. |

Exploratory thresholds must not be described as statistically meaningful.

## Decision Threshold Rules

Every question must state what result changes the recommendation.

Valid examples:

- "If fewer than 4 of 5 target users can name the product category after reading the first sentence, keep iterating on category clarity."
- "If 4 of 5 target users mention proof concerns before price concerns, prioritize evidence language before value framing."
- "If a live A/B test has insufficient sample size, record the result as exploratory or inconclusive."

Invalid examples:

- "Test this with users."
- "See if people like it."
- "Run an A/B test and pick the winner."

## Bias And Consent Rules

Research handoffs must:

- avoid leading questions
- disclose that the message is being tested
- avoid collecting unnecessary personal or sensitive information
- include consent language
- avoid deception by default
- include stop conditions
- avoid recruiting minors or vulnerable participants for MVP tests
- separate comprehension findings from preference or behavior claims

If deception is proposed, it must be explicitly marked and blocked until reviewed. The MVP should not use deception.

## Sensitive Data Avoidance

The default research script must state:

```text
Do not collect personal health, financial, legal, protected-class, employment eligibility, housing, insurance, education, crisis, or minor-related details. If a participant discloses sensitive information, stop the test, do not record the details, and mark the session for exclusion or expert review.
```

## Research Gates

| Gate | Blocks When | Required Result |
| --- | --- | --- |
| Missing uncertainty | The question does not say what is unknown. | Fail validation. |
| Weak method match | Method does not answer the uncertainty. | Revise method. |
| Missing sample | Sample source, size, screener, or role fit is missing. | Fail validation. |
| Missing threshold | No decision threshold is defined. | Fail validation. |
| Inflated evidence | Exploratory or preference data is treated as behavior proof or statistical support. | Downgrade or block. |
| Sensitive collection | The protocol invites personal, regulated, crisis, or protected-class data. | Block until revised or reviewed. |
| Vulnerable participants | The plan recruits minors or vulnerable participants for MVP tests. | Block. |
| A/B caveat missing | A/B recommendation lacks sample-size and context caveats. | Fail validation. |

## Phase 0 And MVP Priority

The first research handoff should be a comprehension test, not a persuasion test.

Minimum MVP handoff:

- one linked uncertainty
- one target-user sample
- one exact comprehension task
- one decision threshold
- one consent line
- one limitation
- no sensitive-data collection

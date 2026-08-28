# Mindfront Ethical Boundaries

Status: Canonical use policy.

## Purpose

Mindfront may improve clarity, proof alignment, reading momentum, and communication accessibility. It must not help users manipulate, deceive, pressure, shame, exploit, diagnose, or evaluate an audience.

The private named interaction-assistance system has one allowed purpose:

```text
autistic_communication_assistance
```

It helps the user understand how a known colleague has communicated in prior work contexts so Codex can prepare clearer drafts and anticipate likely questions. It is an accessibility aid for the writer. It is not a psychological dossier, a clinical assessment, or an employee-management system.

The separate first-party system uses:

```text
autistic_workplace_communication_accommodation
```

It uses only a self-declared encrypted profile to reduce interpretation, preparation, debriefing, and career-evidence workload. It may help the current user communicate their own value and pursue their own role. It may not predict promotion, fabricate authority, evaluate coworkers, intensify status competition, or turn the accommodation into forced masking.

## Purpose Gate

| Use Type | Decision | Required Handling |
| --- | --- | --- |
| Clear general B2B product messaging | Allowed | Continue with normal evidence, claim, and data gates. |
| Private recipient-aware drafting for communication accessibility | Allowed with bounded use | Use only authorized communications, an active exact-match profile, contextual hypotheses, and human review. |
| Private first-party interaction or career-evidence assistance | Allowed with bounded use | Use the self-declared encrypted profile, preserve voice, separate fact from inference, credit collaborators, and require human review. |
| Health, mental health, financial, legal, employment, housing, insurance, education admissions, public benefits, security, crisis, minors, or vulnerable populations | Restricted | Require expert review and block publish-readiness. |
| Deceptive, coercive, exploitative, sensitive-trait targeting, diagnosis, or employee-evaluation workflows | Disallowed | Reject or block the workflow. |

## Allowed Interaction Assistance

The private system may:

- retain authorized internal Outlook, Teams, and resolved-ticket messages in the encrypted communication vault
- use actual names to retrieve the correct private profile
- observe communication features such as information density, structure, terminology, decision framing, evidence expectations, question patterns, and tone register
- use complete prior messages as private context for a draft
- identify recurring response classes, such as requests for evidence, scope, ownership, risk, cost, timing, or implementation detail
- adapt ordering, framing, level of context, next-step clarity, and terminology when the current situation matches the observed context
- show the user which observations shaped a draft

These capabilities are meant to reduce interpretation effort for an autistic writer, not to create leverage over the recipient.

The first-party system may additionally:

- prepare short, layered workplace communication
- provide multiple plausible readings of ambiguous interactions
- distinguish assigned, delegated, nominated, approved-workstream, partnership, self-initiated, and unknown authority
- surface motive attribution, territorial framing, disparagement, unsupported compliance certainty, message stacking, and fatigue risk
- organize the user's own measurable results, delegated scope, adoption, teammate enablement, sponsor confirmation, executive exposure, and formalization gaps
- recommend one accountable coordinator within distributed ownership

It must preserve ambition, directness, technical precision, initiative, and team advocacy. Review flags should explain reception risk and suggest the smallest useful change.

## Prohibited Interaction Uses

The private system must not be used for:

- diagnosis, mental-health labeling, or claims about a person's internal mental state
- inference of protected, sensitive, medical, disability, political, religious, or family traits
- employee ranking, performance evaluation, promotion, compensation, discipline, hiring, firing, succession, or eligibility decisions
- comparing one person's profile with another person's profile
- claims that a person will use exact words, take an exact action, approve a request, or react with certainty
- impersonation, automatic sending, automatic posting, or undisclosed message generation
- manipulation based on vulnerability, fear, status, shame, pressure, private stressors, or inferred motives
- copying private messages, examples, names, or profile details into a shareable report
- presenting observed workplace communication as a complete or permanent personality

## Response-Pattern Boundary

A response pattern is a bounded drafting hypothesis:

> In observed contexts of this type, this person often asked for or responded to this class of information.

It is not:

> This person thinks this way, has this personality, or will say these words.

Every response-pattern output must preserve:

- the observed contexts
- support and contradiction counts
- source-system coverage
- confidence state
- the 90-day freshness boundary
- the statement that exact words and behavior are not predicted

Contradictions are uncertainty, not noise. A context mismatch is a reason not to apply a pattern.

## Automatic Recipient Matching

When a documentation request identifies a recipient, Codex may automatically attempt private profile lookup so the user does not have to ask for the tool by name.

Automatic use is allowed only when:

- the task names one recipient
- the name resolves by exact normalized display-name match to one confirmed identity
- no identity collision exists
- the profile status is `active`
- `eligibleForAutomaticUse` is `true`
- the profile has not passed its `expiresAt` time
- the current communication context matches at least one recorded context

No fuzzy name matching, signature-based identity inference, title-based guessing, or nearest-person fallback is allowed. Missing, collecting, ambiguous, stale, or context-mismatched profiles are skipped. The draft remains usable without profile assistance.

The CLI does not infer a recipient from prose by itself. The Codex workflow identifies the named recipient and passes the exact name through `--profile-name` with `--profile-store`.

## Human Review And Agency

Profile-guided output always requires the user's review. The system may prepare or revise a draft, but it may not send, post, publish, or impersonate automatically.

Review must confirm:

- the profile matched the intended person
- the current context resembles the observed contexts
- the draft remains factually supported
- private examples were used for guidance rather than copied unnecessarily
- the draft sounds like the user, not like an imitation of the recipient
- the wording preserves the recipient's agency and does not pressure them

## Company-Policy Boundary

The system records the governance basis as `user_asserted_company_policy`. This means the user has stated that company-system content is authorized for this internal assistive purpose.

Ordinary company-system content is therefore eligible source material even when it contains actual names, internal plans, one-to-one discussion, or technical detail. The word `private` in this workflow describes where full source content is retained and which outputs may expose it; it is not a reason to omit authorized internal content.

The system does not independently verify that policy and must retain:

```json
{
  "basis": "user_asserted_company_policy",
  "independentlyVerified": false,
  "scope": "private internal assistive drafting"
}
```

This metadata is a provenance statement, not a legal opinion, compliance certification, or permission for unrelated use.

## Disallowed General Uses

Reject or block workflows for:

- scams or deceptive commercial claims
- political or civic persuasion targeting behavior or belief
- harassment, intimidation, shame, or social pressure
- gambling, addiction, or compulsive-use promotion
- self-harm, eating-disorder, or crisis exploitation
- targeting based on protected or inferred sensitive traits
- manipulative persuasion aimed at minors or vulnerable people
- regulated eligibility decisions for housing, insurance, employment, education, credit, or public benefits
- medical, legal, financial, or mental-health claims presented as advice or guaranteed outcomes

## Restricted Uses

These are allowed only for analysis or cautious drafting with expert review required. They cannot become publish-ready from Mindfront alone.

| Restricted Area | Gate |
| --- | --- |
| Health or mental-health product messaging | Require domain expert review. Block advice, guarantee, diagnosis, treatment, or outcome claims. |
| Financial product messaging | Require expert review. Block guaranteed returns, debt-relief promises, or suitability claims. |
| Legal service messaging | Require expert review. Block legal advice or outcome guarantees. |
| Employment, hiring, or performance messaging | Require expert review. Block eligibility, evaluation, or protected-class targeting claims. Accessibility-focused drafting does not permit employee evaluation. |
| Housing, insurance, education admissions, or public-benefits messaging | Require expert review. Block eligibility decisions or behavioral targeting. |
| Security claims | Require expert review or evidence. Block absolute safety claims. |
| Crisis or safety communications | Require expert review. Block persuasion tactics that pressure distressed users. |
| Minors or vulnerable populations | Require expert review. Block manipulative persuasion and high-pressure framing. |

## Language Rules

Use these replacements everywhere:

| Do Not Use | Use Instead |
| --- | --- |
| `pain-first` | `problem-first` |
| `low urgency` | `unclear time relevance` |
| `anxious first-time user` | `anxiety-reduction accessibility lens` |
| `personality prediction` | `context-specific communication hypothesis` |
| `will ask` | `may ask, based on observed contexts` |
| `knows how this person thinks` | `uses observed communication patterns to reduce drafting friction` |

The system may name a user's problem only when grounded in the brief or evidence. It must not intensify fear, shame, status anxiety, loss aversion, or urgency beyond what the evidence supports. It must preserve user agency.

## Allowed Persuasion

Recommendations may improve:

- category clarity
- concrete benefits
- proof alignment
- direct and respectful language
- next-action clarity
- helpful contrast
- honest caveats
- useful reading rhythm
- recipient-appropriate structure when an active profile supports it

Recommendations must not add:

- fake urgency
- fake scarcity
- unsupported authority
- unsupported superiority
- hidden tradeoffs
- fear pressure without evidence
- social pressure or shame
- targeting based on vulnerability
- certainty about a named person's future response

## Required Output Language

Reports and recommendations should use bounded wording:

- "likely to reduce comprehension friction"
- "hypothesis to test"
- "may improve first-pass understanding"
- "should be validated with users"
- "supported by heuristic analysis"
- "may match the recipient's observed communication pattern in this context"
- "likely question class, not predicted wording"

Do not say:

- "users will understand"
- "the market wants"
- "this will convert"
- "this is proven"
- "customers prefer"
- "this person will approve"
- "this person will say"
- "this profile reveals how the person thinks"

unless the statement is independently supported by the exact evidence it claims. A named interaction profile can never support diagnosis, employee evaluation, exact prediction, or market preference.

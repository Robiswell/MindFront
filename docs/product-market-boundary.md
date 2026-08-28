# Mindfront Product And Market Boundary

Status: Phase 0 policy.
The public repository policies in `docs/ethical-boundaries.md` and `docs/evidence-policy.md` are authoritative.

## Purpose

Mindfront is a local-first pre-research message intelligence workflow. It helps teams improve rough product or offer messaging before real user research is available. It must not claim to know market preference, conversion impact, or user behavior unless real evidence is supplied and mapped to the exact claim, audience, channel, and context.

## First Wedge

| Field | Boundary |
| --- | --- |
| Primary user | Product, marketing, sales enablement, technical solutions, or founder/operator users who need to clarify product messaging before formal research. |
| Buyer or sponsor | A product, marketing, revenue, or technical leadership sponsor who wants clearer messaging and a runnable validation step. |
| First use case | Audit and improve one landing page, internal pitch, product explainer, sales narrative, or launch-message draft. |
| First trigger | "We need to explain this clearly, but we do not have time or access for proper market research yet." |
| First channel | Single-message artifacts: landing-page section, one-pager copy, internal pitch, sales narrative, launch message, or product explainer. |
| First desired action | Make the message understandable, credible, and testable. Do not optimize for high-volume conversion. |

## Excluded Users

- Users seeking medical, legal, financial, mental-health, housing, insurance, employment, education, credit, public-benefits, political, or crisis advice.
- Users trying to target minors, vulnerable people, protected classes, or inferred sensitive traits.
- Users seeking manipulative persuasion, deceptive urgency, shame, intimidation, addictive engagement, or hidden tradeoff framing.
- Users seeking campaign-scale targeting, ad optimization, or publish-ready claims without evidence.

## Excluded First Use Cases

- Regulated medical, legal, financial, or mental-health advice campaigns.
- Political or civic persuasion targeting behavior or belief.
- Crisis messaging, safety-critical messaging, or support situations where harm can result from weak wording.
- Targeted ads to vulnerable groups or people selected by protected or inferred sensitive traits.
- Gambling, addiction, compulsive-use promotion, or high-pressure conversion flows.
- High-volume conversion optimization.
- Any workflow claiming validated market preference without mapped real evidence.

## Current Alternatives

- Generic LLM copy prompts.
- Manual copy review.
- Product-marketing critique by a colleague.
- UX writing review.
- Lightweight user interviews or comprehension tests.
- Existing document workflow without Mindfront-specific gates.

## Why This Is Not A Generic Copywriting Prompt Pack

Mindfront must produce structured, inspectable records rather than only polished prose. Every recommendation needs:

- a detected issue
- a linked rubric dimension or principle
- evidence basis
- finding confidence
- recommendation state
- limitation
- recommended validation
- claim/proof impact, when relevant

The tool may improve wording, but the core product is the gate-controlled workflow: boundary check, analysis, claim/proof review, safe rewrite, rewrite claim-diff, and research handoff.

## Required Brief Fields

The first implementation brief must include or derive these fields before analysis:

```json
{
  "messageBriefId": "brief-001",
  "projectName": "Example Product",
  "primaryUser": "Product marketer",
  "buyerOrSponsor": "Product leadership",
  "targetAudience": "Busy operations manager",
  "audienceFamiliarity": "low | medium | high",
  "channel": "landing_page | pitch | explainer | sales_narrative | launch_message",
  "desiredAction": "request_demo",
  "sourceText": "Paste copy here",
  "firstUseCase": "single_message_audit",
  "domainContext": "general_b2b",
  "proofAvailable": [],
  "unknowns": [],
  "constraints": []
}
```

## First Useful Workflow

The first useful workflow must prove that Mindfront can:

1. Load one structured brief.
2. Validate product, data, evidence, and ethical boundaries.
3. Find concrete clarity, proof, friction, and ethical-risk issues.
4. Produce one safer plain-English rewrite.
5. Block or flag unsupported claims introduced by the rewrite.
6. Create one runnable user-validation step.
7. State limitations without implying market truth.

## Boundary Gates

| Gate | Blocks When | Required Result |
| --- | --- | --- |
| Product fit | The request is outside the first wedge or missing target audience, channel, or desired action. | Stop with validation failure and request missing context. |
| Excluded use | The workflow matches any excluded user or use case. | Block analysis or rewrite. |
| Sensitive domain | The workflow touches restricted domains or vulnerable audiences. | Require expert review and block publish-readiness. |
| Evidence | Strong claims have no source, method, sample, or limitation record. | Mark as unsupported or user-provided unverified. |
| Rewrite | The rewrite adds new material claims. | Run claim-diff and block unsupported additions. |
| Research handoff | No uncertainty can be turned into a runnable test. | Stop before report-ready state. |
| Output maturity | JSON/Markdown artifacts are invalid or missing limitations. | Do not create polished reports, dashboards, or skill outputs. |

## First Success Proof

Mindfront is useful enough for Phase 1 only if a user can compare it against a generic LLM prompt or manual review and see that it:

- catches specific clarity, proof, friction, and ethical-risk problems
- avoids unsupported market claims
- improves wording without adding unsupported claims
- produces a validation step that a real target user workflow could run
- finishes faster than an unstructured manual review

Minimum later promotion evidence:

- 3 to 5 real target-user workflows
- at least 70 percent of high-priority findings accepted as useful
- zero unsupported claims marked publish-ready
- zero synthetic outputs treated as real evidence
- at least 3 research handoffs judged runnable

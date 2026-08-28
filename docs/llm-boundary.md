# Mindfront LLM Boundary

Status: Phase 0 policy.
The public repository policies in `docs/ethical-boundaries.md` and `docs/evidence-policy.md` are authoritative.

## Purpose

Mindfront must work without external LLM calls in the MVP. LLMs may later assist with structured judgment or creative drafting, but they cannot replace evidence, validation, schemas, claim/proof gates, or expert review.

## MVP Rule

- External LLM use is disabled by default.
- Deterministic checks must work offline.
- `--no-external-llm` must be supported for CLI workflows.
- LLM output is never accepted directly as a final artifact. It must be normalized into schema-validated records.

## Processing Stages

| Stage | MVP Status | Examples | Output Requirement |
| --- | --- | --- | --- |
| Deterministic checks | Required offline | sentence length, CTA presence, quantified claim detection, superlatives, vague phrases, manipulation patterns, required fields | Structured findings with observable text evidence. |
| Structured judgment | Optional later | likely confusion, trust gap, implied audience, emotional frame, objection hypothesis | Schema-validated records with confidence and limitations. |
| Creative generation | Optional later | plain-English rewrite, copy variants, interview questions, survey questions | Must pass claim/proof, ethical, data, and research-method gates. |

## Required LLM Stage Record

If LLM use is enabled later, every stage must record:

```json
{
  "llmStageId": "llm-stage-001",
  "stageType": "structured_judgment | creative_generation",
  "provider": "provider-name",
  "model": "model-name",
  "promptTemplateId": "template-001",
  "promptTemplateHash": "sha256...",
  "inputArtifactIds": ["artifact-001"],
  "inputFields": ["sourceText", "targetAudience", "constraints"],
  "outputSchema": "finding-record-v1",
  "generatedArtifactIds": ["artifact-002"],
  "llmProcessingAllowed": true,
  "dataClassification": "public | internal | confidential | sensitive",
  "redactionStatus": "not_needed | redacted | required",
  "createdAt": "2026-05-09T00:00:00-06:00"
}
```

## Allowed Inputs

External LLM inputs are allowed only when all are true:

- the source artifact has `llmProcessingAllowed: true`
- data is redacted when needed
- data classification permits the stage
- source artifact ids are recorded
- input fields are limited to the minimum useful set
- the output schema is known before the call

## Blocked Inputs

Do not send these externally unless a specific exception is recorded and redaction is complete:

- PII
- PHI
- private customer quotes
- customer-confidential details
- participant names or raw notes
- account identifiers
- confidential strategy
- regulated-domain case details
- minor or vulnerable participant data
- crisis or safety-sensitive content

## LLM Output Rules

LLM-generated or LLM-assisted output must:

- be parsed into known artifact schemas
- include source artifact ids
- include evidence basis
- include finding confidence or recommendation state when action is recommended
- include limitations
- pass claim/proof gate
- pass ethical boundary gate
- pass data-boundary gate
- pass rewrite claim-diff when it creates new wording

LLM output must not:

- create publish-ready claims from unsupported inputs
- turn simulated agreement into validation
- remove limitations
- infer sensitive traits for targeting
- strengthen high-stakes claims without mapped evidence and expert review

## Validation Boundary

Repeated LLM agreement is not real user validation. It can support `heuristic_inference` or `synthetic_reader_stress_test` only when labeled and schema-valid. It cannot produce `validated_for_exact_context`.

Synthetic reader stress tests cannot:

- be described as market research
- use real-user evidence labels
- exceed hypothesis or locally checked states without external evidence
- omit simulation notices

## Gate Table

| Gate | Blocks When | Required Result |
| --- | --- | --- |
| External LLM default | A workflow requests external LLM use without explicit allowance. | Fail or rerun with local deterministic path. |
| Data classification | The input is confidential or sensitive without approved exception and redaction. | Block external processing. |
| Missing stage record | Provider, model, prompt hash, input fields, schema, or source artifacts are missing. | Reject generated artifact. |
| Schema failure | LLM output cannot be normalized into the expected schema. | Reject output. |
| Claim/proof failure | Generated prose adds unsupported material claims. | Block variant or mark proof required. |
| Ethical failure | Generated prose uses manipulation, sensitive targeting, or restricted-domain overclaiming. | Reject output. |
| Validation inflation | LLM output is marked as real user data or exact-context validation. | Fail validation. |

## CLI Implications

- `validate` must not require LLM access.
- `analyze` must run under `--no-external-llm`.
- `rewrite` may later use LLM generation, but the MVP rewrite path should be deterministic or locally generated from templates.
- `reader-stress-test` is optional and must carry simulation fields.
- `report` must not introduce new LLM-written claims unless the report prose is claim-gated.

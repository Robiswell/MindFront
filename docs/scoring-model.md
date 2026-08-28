# Mindfront Scoring Model

Status: Phase 0 canonical scoring model.

## Purpose

Mindfront scores the message as a testable artifact, not as a prediction of market performance. Scores summarize observable clarity, proof, friction, and readiness signals so a user can decide what to fix before research.

## Score Inputs

The current deterministic scorer uses:

- the message brief
- configured psychology principles
- configured rubric dimensions
- evidence-source policy
- confidence-label policy
- sensitive-domain and publish-readiness fields
- observable source-text signals

It does not use external market data, hidden audience profiles, behavioral prediction, or live conversion data.

## Required Dimensions

The canonical rubric is defined in `config/message-quality-rubric.json`. Required Phase 0 dimensions include:

- clarity
- cognitive load
- proof
- trust
- motivation
- friction
- action readiness
- evidence readiness
- ethical risk

Each score must include the score value, scale, reason, evidence basis, finding confidence, related findings, and lineage hashes where applicable.

## Motivation And Friction

Motivation and friction are treated as separate but connected outputs:

- Motivation score explains whether the message makes the intended action feel understandable and worthwhile.
- Friction categories identify likely obstacles such as unclear category, unsupported claim, vague next step, cognitive overload, or trust gap.
- Objection mapping records likely reader objections as hypotheses.
- Trust-gap reporting separates missing proof from wording preference.

These outputs are useful for prioritization, not validation.

## Interpretation Rules

| Score Pattern | Interpretation | Required Next Step |
| --- | --- | --- |
| High clarity, weak proof | Readers may understand the offer but not believe it. | Add bounded proof or mark claims unsupported. |
| Strong proof, weak clarity | Evidence may exist, but the message is hard to parse. | Rewrite before research. |
| High friction | The user may hesitate or misunderstand before action. | Fix friction and run comprehension validation. |
| Sensitive-domain risk | Expert review may be required. | Block publish-readiness until reviewed. |
| Evidence-readiness gap | The claim cannot be responsibly promoted. | Attach mapped evidence or downgrade the claim. |

## Completion Rule

A score is complete only when the output states why the score was assigned, what evidence basis was used, what limitation applies, and what validation would change the recommendation.

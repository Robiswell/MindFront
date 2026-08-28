# Confidence Policy

Mindfront outputs are useful only when evidence state remains visible.

## Allowed Interpretation

- `heuristic_inference`: structured local inference from text properties, rubric anchors, and configured principles.
- `synthetic_reader_stress_test`: simulated lens output for planning real validation only.
- `synthetic_task_fixture`: synthetic documentation-task observations used to verify workflow behavior only.
- `user_provided_unverified`: a proof note exists, but method, sample, source id, or limitations are incomplete.
- `small_user_test`, `real_user_data`, and `expert_review`: only count as validated signals when the source artifact explicitly uses those evidence bases.

## Private Workplace Assistance

These labels organize an assistive interpretation; they do not create market evidence or psychological truth:

- `explicit_fact`: directly present in the supplied artifact or source.
- `user_provided_unverified`: asserted by the user but not independently confirmed in the current run.
- `source_supported_workplace_evidence`: supported by an authorized communication or system record available in the current run.
- `bounded_inference`: a reasonable interpretation that remains uncertain.
- `plausible_alternative`: another explanation consistent with the known facts.
- `unknown`: information the available context cannot establish.
- `stakeholder_confirmed`: explicitly confirmed by the relevant stakeholder.

Profile-derived observations remain context-specific drafting guidance even when their readiness threshold is met. They do not confirm intent, emotion, personality, employee value, formal authority, or future behavior.

## Forbidden Upgrades

- Do not say the market prefers a variant because `compare` ranked it first.
- Do not say users understood the copy because `reader-stress-test` found fewer issues.
- Do not say real users completed tasks because a task-validation artifact has `observationSource: synthetic_fixture`.
- Do not say a report or dashboard validates a message.
- Do not hide `unsupported`, `support_candidate`, or `blocked` claim status.
- Do not use `validated_for_exact_context` unless mapped real-user data or applicable expert review exists in the source artifact.
- Do not present an inferred motive, emotion, personality, or exact future response as fact.
- Do not infer formal authority, decision rights, title, compensation, or conversion from operating scope alone.
- Do not turn career evidence into a promotion probability or guarantee.
- Do not use workplace assistance to rank or evaluate another person for hiring, promotion, compensation, discipline, or performance.

## Safe Language

Use:

- "hypothesis to test"
- "message issue to validate"
- "simulated stress-test finding"
- "synthetic workflow fixture"
- "exact-context task observation"
- "support candidate"
- "recommended next validation"
- "explicit fact"
- "bounded inference"
- "plausible alternative"
- "unknown from the available context"
- "operating-scope evidence, not a formal employment fact"

Avoid:

- "proven"
- "validated by psychology"
- "market-backed"
- "users will prefer"
- "conversion lift"
- "this person definitely thinks"
- "this guarantees promotion"

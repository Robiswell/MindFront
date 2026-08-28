# Mindfront Architecture Plan

Status: Phase 0 canonical architecture.

## Purpose

Mindfront is a local-first workplace communication accommodation and message-intelligence workflow. It has a private first-party path for interaction preparation, interpretation, debriefing, and the user's own career evidence, plus the existing inspectable artifact path for message quality and research readiness.

The architecture must stay source-first and evidence-safe. Every stage emits structured JSON, plain-language report material, lineage hashes, confidence labels, and limitations. No stage may convert heuristic analysis, rewrite ranking, simulated reader review, dashboard history, improvement planning, or PDF generation into market evidence.

## System Shape

| Layer | Responsibility | Current Source |
| --- | --- | --- |
| Brief input | Capture the exact message, audience, channel, data classification, domain context, and publish-readiness state. | `examples/briefs`, `backend/src/mindfront/validation.py` |
| Policy config | Define psychology principles, audience lenses, evidence sources, confidence labels, and scoring dimensions. | `config/*.json` |
| Deterministic analysis | Score observable message issues and produce findings, claims, recommendations, motivation/friction, and validation questions. | `backend/src/mindfront/analysis.py`, `backend/src/mindfront/motivation.py` |
| Safe rewrite | Generate copy variants while blocking unsupported claim expansion. | `backend/src/mindfront/rewrite.py` |
| Variant comparison | Rank variants as test candidates without claiming validated preference. | `backend/src/mindfront/compare.py` |
| Reader stress test | Simulate comprehension-friction checks through configured lenses, labeled as not market evidence. | `backend/src/mindfront/stress.py` |
| Research handoff | Turn uncertainties into runnable real-world research tasks with consent, sample, method, and threshold fields. | `backend/src/mindfront/research.py` |
| Task-observation protocol | Generate no-PII documentation task protocols, observer instructions, session CSV templates, and filled-CSV conversion. | `backend/src/mindfront/protocol.py` |
| Task validation | Summarize real no-PII documentation task observations or synthetic workflow fixtures without storing raw participant data or claiming market proof. | `backend/src/mindfront/impact.py` |
| Report package | Assemble JSON, Markdown, editable HTML, CSV, and document-workflow handoff artifacts. | `backend/src/mindfront/reports.py` |
| History and dashboard | Store artifact summaries, hashes, scores, claims, variants, stale state, and dashboard views without raw source text. | `backend/src/mindfront/db.py`, `backend/src/mindfront/dashboard.py` |
| Improvement planning | Rank operational next actions from stored history, task protocols, task-validation summaries, stale state, and history comparison without upgrading evidence. | `backend/src/mindfront/improvement.py` |
| First-party self profile | Retain user-declared goals, strengths, communication risks, support preferences, authenticity constraints, and energy protections in a separate installation-local AES-256-GCM store. | `backend/src/mindfront/workplace_assistance.py`, `runtime-data/self-workplace-assistance.vault` |
| Workplace assistance | Produce private `preflight`, `interpret`, `debrief`, and `career_review` results with fact/inference separation, authority and credit gates, and no outcome prediction. | `backend/src/mindfront/workplace_assistance.py`, `config/workplace-assistance-policy.json` |
| Codex integration | Provide a repo-local skill and wrapper scripts for repeatable normal use. | `skills/mindfront`, `project-tools` |

## First-Party Accommodation Plane

The self profile is not a recipient profile. It contains only information the current user explicitly declares and may guide assistance immediately. Recipient profiles remain third-party, observation-derived, thresholded, expiring, exact-identity, and context-specific.

The workplace-assistance result is a private working artifact. It separates explicit facts, unverified user claims, bounded inferences, plausible alternatives, and unknowns. It can help the user advocate for their own role and organize their own career evidence, but it cannot evaluate coworkers, infer motives as facts, predict promotion, grant authority, or send a message.

The leadership model is one accountable coordinator within distributed security, engineering, business, and approval ownership. The system flags sole-source and territorial framing because organizational capability and visible collaborator ownership are stronger leadership evidence than dependence on one person.

## Specialist Documentation Layer

Mindfront now includes a general specialist-bandwidth layer for documentation requests. It is designed for Codex-assisted internal documentation where the likely reader may be a highly specialized technical employee with limited spare attention for learning another workflow.

The layer is intentionally heuristic. It can flag likely learning tax, vague process language, weak fast paths, loss of agency, missing proof, coercive "addictive" framing, and documentation that feels remedial or bureaucratic. It cannot prove employee preference, adoption, comprehension, or performance improvement.

When a brief is detected as documentation, analysis emits a `documentationQuality` signal and adds findings tied to `lens-specialist-bandwidth`. Reports surface the signal, the evidence boundary remains explicit, and the research plan turns the findings into task-based validation prompts rather than preference claims.

Normal use should translate rough statements such as "make this addictive to read" into safer quality goals: reading momentum, skim-to-answer speed, obvious next action, respectful precision, and no coercive pressure.

## Executive Impact Loop

Mindfront now includes a task-observation, task-validation, and improvement-planning loop for documentation that can first generate a no-PII collection protocol, then process real no-PII task observations or explicitly synthetic workflow fixtures, then rank the next Codex actions from the stored evidence boundary. This loop is meant to give leadership-facing work a measurable spine: task completion, skim-to-answer speed, follow-up load, expert-respect rating, reuse-intent rating, coded trust objections, and an operational backlog for the next documentation pass.

The loop is deliberately narrow. A `documentation_task_observation_protocol` is a collection handoff only: it creates observer instructions and a session CSV template, not evidence. A filled no-PII CSV can be converted into `documentation_task_validation_input`; that artifact is accepted only when it declares no personal data, no customer-confidential data, no LLM processing permission, clear provenance, and a clear `observationSource`. `task-input` defaults to `observationSource: synthetic_fixture` so generated or test-filled CSV rows cannot become real evidence by accident. Inputs with explicitly declared `observationSource: real_task_observation` produce aggregate `documentation_task_validation_result` evidence with `evidenceBasis: small_user_test`, `evidenceGrade: exact_context_directional`, `realTaskEvidenceCreated: true`, `marketEvidenceCreated: false`, and `rawParticipantDataStored: false`. Inputs with `observationSource: synthetic_fixture` produce `evidenceBasis: synthetic_task_fixture`, `evidenceGrade: synthetic_fixture_only`, and `realTaskEvidenceCreated: false`.

Real task observations may support a narrow statement such as, "participants in this protocol completed these tasks at the observed rate and time." Synthetic fixtures only prove that the workflow can process and report the shape of the data. Improvement plans only prioritize the next operational actions, such as collecting filled no-PII sessions, refreshing stale runs, fixing repeated message failures, or reducing task friction seen in real observations. None of these paths allow claims that the market prefers the copy, the company will adopt it, productivity increased company-wide, C-suite attention is proven, or a conversion outcome was proven. Those claims require repeated task validation, representative sampling, operational telemetry, or a separate research program.

## Normal Workflow

1. Validate config and briefs.
2. Analyze the message brief.
3. Generate gated rewrite variants.
4. Compare variants.
5. Run the reader stress test.
6. Generate the real-world research plan.
7. Generate a task-observation protocol when documentation task evidence may be needed.
8. Convert filled no-PII session CSVs with `task-input` when available; pass `--observation-source real_task_observation` only for real no-PII sessions collected from the protocol.
9. Optionally summarize exact-context task-validation observations.
10. Assemble the report bundle.
11. Ingest artifacts into the local store.
12. Check stale state.
13. Build the dashboard.
14. Build the improvement plan when a DB path is available.
15. Render a PDF only through the document workflow when a polished deliverable is needed.

## Hard Boundaries

- The CLI must work without external LLM calls.
- The self profile must remain installation-local AES-256-GCM encrypted, user-declared, editable, deletable, and outside normal Mindfront history.
- Workplace assistance must preserve voice and reduce interpretation load without enforcing masking.
- Workplace assistance must require human review, disable automatic sending and coworker evaluation, and never predict promotion.
- Synthetic and heuristic outputs must remain visibly separate from validated signals.
- Task-observation protocols are collection handoffs, not evidence.
- Real task-validation evidence must remain exact-context directional evidence unless a later research program supplies broader proof; synthetic task-validation fixtures are workflow checks only.
- Improvement plans are operational backlogs for the next Codex pass, not evidence that a reader preference, adoption, conversion, performance lift, or executive impact has been proven.
- The report pipeline must record editable source, final output, planned PDF output, and document-workflow handoff path.
- The dashboard must not store full raw source text.
- The dashboard may surface task-observation protocol metadata, task-validation metrics, and improvement-plan actions, but dashboard display must not upgrade market evidence, confidence, or publish readiness.
- A run becomes stale when stored artifact paths are missing or stored hashes no longer match current files.

## Verification Standard

A phase is not complete until strict validation, unit tests, compile checks, skill validation, and end-to-end wrapper smoke tests pass. Report outputs must include limitations and what-to-test-next guidance. PDF output is complete only after render, non-empty file verification, and visual QA.

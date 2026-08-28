# Workflow Contract

Mindfront is local-first and deterministic by default. Select one route, preserve its evidence boundary, and verify before calling the work complete.

## Route Selection

Use `mindfront_reference` when the user explicitly names Mindfront but asks only for an explanation, maintenance, hooks, tests, repository work, configuration, implementation, or no substantive workflow. Point to the canonical repository, `AGENTS.md`, `skills/mindfront/SKILL.md`. Do not load `runtime-data`, retrieve company communications, create artifacts, or apply Stop enforcement merely because the name appears. Reclassify only when the actual request substantively requires one of the routes below.

Use `workplace_assistance` for:

- ambiguous workplace-message or interaction interpretation
- meeting preparation or debriefing
- executive or stakeholder communication
- authority, ownership, or credit calibration
- the user's own career evidence
- user-declared autistic communication accommodation

Read `workplace-assistance.md`, choose `preflight`, `interpret`, `debrief`, or `career_review`, and use the deterministic `assist` command described in `docs/cli-contract.md` when structured private input is available. Keep the answer inline unless the user requests a saved artifact. Do not require audit, report, dashboard, or PDF files for an inline assistive answer.

Use `artifact_workflow` for message and copy audits, reader stress tests, research planning, task-observation work, reports, dashboards, and repeated improvement loops. Follow the command order below.

## Artifact Workflow Command Order

1. `validate`
2. `analyze`
3. `rewrite`
4. `compare`
5. `reader-stress-test`
6. `research-plan`
7. `task-protocol` when documentation task evidence may be needed
8. `task-input` when a filled no-PII session CSV exists; use `--observation-source real_task_observation` only for real no-PII observations
9. `task-validation` when task-validation input exists
10. `report`
11. optional PDF render through `project-tools/render-mindfront-report-pdf.ps1`
12. `store ingest` when a DB path is available or history output is requested
13. `store check-stale` when a DB path is available or history output is requested
14. `dashboard build` when a DB path is available or dashboard output is requested
15. `improvement-plan` when a DB path is available or a next-action backlog is requested

## Artifact Workflow Required Outputs

- `message-analysis-report.json`
- `copy-variants.json`
- `variant-comparison.json`
- `reader-stress-test.json`
- `research-plan.json`
- `research-plan.md`
- optional `documentation-task-observation-protocol.json`
- optional `documentation-task-observation-protocol.md`
- optional `documentation-task-session-template.csv`
- optional `documentation-task-validation-input.json`
- optional `documentation-task-validation-result.json`
- `mindfront-audit-report.json`
- `mindfront-audit-report.md`
- `source.html`
- `mindfront-audit-report.html`
- `mindfront-audit-scorecard.csv`
- `mindfront-document-workflow-handoff.md`
- optional `mindfront.sqlite`
- optional `mindfront-dashboard.json`
- optional `index.html`
- optional `mindfront-improvement-plan.json`
- optional `mindfront-improvement-plan.md`
- optional `mindfront-audit-report.pdf`
- optional `mindfront-documentation-flow-result.json`

## Verification

Before calling an artifact-workflow run complete:

- Run strict validation.
- Run unit tests.
- Run compile checks.
- Run the sample command path for the phase being changed.
- Inspect generated JSON for evidence-boundary fields.
- If a task-observation protocol was generated, verify it is marked `marketEvidenceCreated: false`, `notMarketEvidence: true`, and includes the CSV template.
- If task-validation was generated, verify synthetic fixtures and real observations keep their distinct evidence grades.
- If `task-input` was generated from a CSV, verify generated/test rows remain `synthetic_fixture` unless the caller explicitly declared real no-PII observations.
- If an improvement plan was generated, verify it is marked `marketEvidenceCreated: false`, `notMarketEvidence: true`, and does not treat backlog actions as proof.
- Inspect Markdown or HTML outputs for limitations and what to test next.
- If a PDF was requested, render from the editable HTML and inspect the PDF before presenting it as final.

Before calling workplace assistance complete:

- Verify the selected mode matches the user's need.
- Keep facts, user-provided claims, bounded inferences, plausible alternatives, and unknowns distinct.
- For `interpret`, include at least two plausible interpretations, the risk of being wrong, and one useful clarifying question.
- For `preflight`, include the desired outcome, exact ask, authority state, visible credit, a short version, and an interruption-safe sentence.
- For `debrief`, separate decisions, commitments, owners, dates, interpretations, and unresolved items.
- For `career_review`, distinguish operating-scope evidence from formal employment facts and do not create a promotion prediction.
- Confirm private context stayed under `runtime-data` and did not enter normal history or shareable artifacts.
- For a paste-ready draft, confirm the final response contains only the intended message and no Mindfront, profile, source-coverage, tool-status, or review meta-commentary.
- Confirm human review remains structural and automatic sending, coworker evaluation, and promotion prediction remain disabled.

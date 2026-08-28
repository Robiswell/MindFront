# Mindfront Skill Integration

Status: repo-local source package.

## Purpose

`skills/mindfront` turns the Mindfront CLI workflow into reusable Codex behavior for message audits, positioning reviews, copy testing, pre-research plans, no-PII documentation task-observation protocols, report packaging, local dashboard history, and next-action improvement planning.

For specialist documentation work, the skill also applies a specialist-bandwidth lens by default. The lens checks whether documentation minimizes learning tax, preserves expert autonomy, gives specialists a fast path to the useful answer, and keeps evidence boundaries explicit. This remains synthetic review, not employee research.

## Source-First Rule

This repository is the source of truth. Do not manually patch the global Codex skills directory as the canonical copy. If the skill is installed later, copy from this repo and keep a source-to-runtime validation step.

Project-local automation lives in `.codex/hooks.json`, `.codex/hooks/mindfront-common.ps1`, `.codex/hooks/mindfront-prompt.ps1`, `.codex/hooks/mindfront-stop.ps1`, `AGENTS.md`, and `config/automation-manifest.json`. These files make Mindfront the default workflow for matching requests inside this repo even when the global skill inventory does not list `mindfront`. A lightweight `mindfront_reference` route also activates on every standalone explicit Mindfront mention, links to this skill and the origin context task, and deliberately avoids private-context loading, artifact requirements, and Stop enforcement.

## Skill Package

```text
skills/mindfront/
  SKILL.md
  agents/openai.yaml
  references/
    confidence-policy.md
    workflow-contract.md
    source-first-deployment.md
  scripts/
    run_mindfront_workflow.ps1
  assets/
    report-output-checklist.md
```

## Validation

Use:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\project-tools\test-mindfront-skill.ps1 -Python $env:USERPROFILE\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe
```

The wrapper validates skill structure, runs the full sample Mindfront workflow, writes a report, ingests the run into SQLite, builds a static dashboard, and emits a `mindfront-improvement-plan.json`/`.md` backlog when `-DbPath` is used. It also runs the specialist documentation fixture through task-observation protocol generation, synthetic task-validation fixture handling, report integration, store ingest, dashboard evidence separation, and improvement-plan evidence-boundary checks. When `-TaskSessionsCsv` is used, the wrapper defaults `-TaskSessionsObservationSource` to `synthetic_fixture`; set it to `real_task_observation` only for real no-PII sessions collected from the generated protocol.

For PDF deliverables, run the wrapper with `-RenderPdf` or run `project-tools/render-mindfront-report-pdf.ps1` against the report directory. The PDF step uses the document workflow converter, writes `mindfront-documentation-flow-result.json`, and still requires visual QA before the PDF is treated as final.

Use `project-tools/test-mindfront-automation.ps1` after changing project-local hooks or activation language. The test verifies all three routes, requires standalone and technical Mindfront mentions to receive reference context, keeps embedded substrings and unrelated coding/file-operation/error-message requests quiet, proves the reference route does not load private context or invoke Stop enforcement, verifies transcript-only assistant responses are read by the Stop hook, and blocks weak artifact completion messages until they mention concrete Mindfront artifacts or evidence boundaries.

Improvement-plan requests are treated as Mindfront requests. The Stop hook should block completion claims for improvement loops unless the final response mentions `mindfront-improvement-plan.json` and clearly states that the plan is an operational backlog, not market evidence or proof of performance.

Use `project-tools/test-mindfront-runtime-pickup.ps1` to audit machine-level prerequisites that cannot live entirely inside the repo: `[features] hooks = true`, this repo trusted by Codex, and trusted hook state for the project-local UserPromptSubmit and Stop commands. This is runtime pickup evidence, not a replacement for the hook-script smoke test.

The runtime pickup audit verifies that trusted hook-state entries exist and that normal verification is running from the repo root. Codex owns the exact current-command trust hash calculation, so this audit does not claim to recompute that hash.

Use `project-tools/invoke-phase-verification.ps1 -RequirePlan -PlanPath plans/explicit-mindfront-reference-activation.md -Passes 3` after this automation change. It runs the activation smoke test, runtime pickup audit, skill validation, backend unit tests, compile checks, and full sample Mindfront workflow three times, then writes a source-owned phase verification result under `test-output/phase-verification`.

The upstream skill-creator `quick_validate.py` imports `PyYAML`. If the local Python environment lacks that module, use `project-tools/validate-mindfront-skill.ps1`; it checks the same required frontmatter fields, naming rule, TODO absence, and required Mindfront resources without installing dependencies.

## Trigger Fixtures

Positive trigger examples:

- "Audit this landing page message and tell me what users may misunderstand before we do research."
- "Generate safer copy variants and a research plan for this positioning draft."
- "Package the message analysis into a report and dashboard without claiming market validation."
- "Make this headline and tagline clearer."
- "Improve this product messaging."
- "Run a reader-stress-test on this value-prop."
- "Edit this landing page for clarity."
- "Polish the homepage hero."
- "Improve this error message copy so users understand what to do."
- "Review this specialist documentation for specialist bandwidth and learning tax."
- "Check whether this documentation preserves expert autonomy for technical specialists."
- "Evaluate the documentation gravity of this report."
- "Rewrite this Example Organization guide so it has a fast path for specialists."
- "Generate a task-observation protocol and session template for this documentation."
- "Convert this filled no-PII session template into task-validation input."
- "Build the next-action backlog from the Mindfront history DB."
- "Create a documentation improvement loop from the stored Mindfront runs."

Reference-route examples:

- "Mindfront"
- "Tell me what Mindfront is."
- "Review the Mindfront runtime pickup hook implementation."
- "Review the Mindfront specialist bandwidth hook implementation."
- "Review specialist bandwidth trigger coverage in mindfront-common.ps1."

Negative trigger examples:

- "Analyze this spreadsheet formula."
- "Check my calendar availability."
- "Look up current stock prices."
- "Copy files from docs to test-output."
- "Fix this error message in Python."
- "Tell me what files changed in this Example Organization repo."
- "Fix the Python error in the specialist documentation renderer."
- "Copy the specialist documentation folder to test-output."
- "Mindfrontier should remain an unrelated substring."

## Runtime Deployment Gate

Project-local automatic activation is expected only when work happens from this repo root in a Codex session that has hooks enabled and has trusted this project's hook commands. Outside this workspace, the separate source-owned global Mindfront link hook provides the canonical repo, skill, and origin-task pointers; the full substantive workflow still runs from this source package.

Install or deploy the skill outside this repo only after:

- strict validation passes
- unit tests pass
- skill validation passes
- sample wrapper run passes
- confidence policy remains source-owned
- config deployment has a source-first copy plan

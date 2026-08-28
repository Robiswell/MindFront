# Mindfront Project Instructions

Use Mindfront automatically for two substantive request classes plus one lightweight reference route:

1. `workplace_assistance`: ambiguous workplace interactions, meeting preparation or debriefing, executive or stakeholder communication, authority/ownership/credit calibration, the user's own career or FTE evidence, and user-declared autistic communication accommodation.
2. `artifact_workflow`: product messaging, message-quality review, positioning, homepage or landing-page copy, headline/tagline clarity, sales narrative copy, launch copy, comprehension, motivation/friction, pre-research validation, copy variants, audit reports, local history dashboards, next-action backlogs, and repeated documentation improvement loops.
3. `mindfront_reference`: every standalone explicit mention of Mindfront that is name-only or concerns explanation, maintenance, hooks, tests, repository work, configuration, or implementation without requesting either substantive workflow.

Classify the route before acting. For `mindfront_reference`, link to `skills/mindfront/SKILL.md` and let the current request control scope. Do not load private profiles, retrieve company communications, force a report or dashboard, create an artifact, or apply Stop enforcement merely because the name appears. For `workplace_assistance`, read `skills/mindfront/references/workplace-assistance.md`, privately load and apply the bounded context from `runtime-data/self-workplace-assistance.vault` when it exists (the prompt hook validates availability but never serializes decrypted values), choose `preflight`, `interpret`, `debrief`, or `career_review`, and keep the answer inline unless the user requests an artifact. Separate facts, user assertions, bounded inferences, plausible alternatives, and unknowns. Preserve the user's direct voice and reduce interpretation load without forcing masking. Never infer motives as facts, evaluate coworkers, predict promotion, or auto-send.

For a rewording, composition, or reply-ready request, the final response must contain only the intended paste-ready message unless the user asks for analysis or alternatives. Do not append Mindfront notes, profile or source-coverage notices, tool status, human-review reminders, or other meta-commentary that could be pasted accidentally. Human review remains a structural delivery boundary: never auto-send.

Use plain ASCII characters in all user-facing prose and paste-ready communication by default. Use straight apostrophes and quotation marks, regular hyphens, three periods instead of a typographic ellipsis, and unaccented common English spellings such as "resume." Do not use smart quotes, em dashes, en dashes, nonbreaking spaces, decorative bullets, emoji, or other typographic Unicode unless the user explicitly requests them or the exact character is required in a proper name, quotation, code, path, URL, identifier, or technical data.

For `artifact_workflow`, do not wait for the user to say "use Mindfront." Read `skills/mindfront/SKILL.md` if the skill is not listed in the active skill inventory, then follow the workflow order:

1. validate
2. analyze
3. rewrite
4. compare
5. reader-stress-test
6. research-plan
7. task-observation protocol when documentation task evidence may be needed
8. task-input only when a filled no-PII session CSV exists
9. task-validation only when a task-validation input exists
10. report
11. optional PDF render only when requested
12. optional store, stale check, dashboard, and improvement-plan

When a documentation or message request names an intended recipient, use connected Microsoft Teams or Outlook context only when the user has explicitly authorized that source use and the operator has legitimate access under applicable law and organizational policy. If authorized, search the exact person and task topic, fetch complete relevant messages or threads, convert them through the repo adapters, and ingest accepted content into `runtime-data/interaction-communications.vault`. Reuse native message, conversation, author, and timestamp identifiers whenever available. Keep retrieval bounded and record partial coverage honestly; an empty or throttled search is an access gap, not proof that no communication exists. Never write connector payloads or full bodies outside `runtime-data`, and remove temporary staging after successful ingestion. The deterministic local wrapper cannot call cloud connectors itself.

After the live-source attempt, automatically check the exact name with `mindfront.cli profile context` against `runtime-data/interaction-profiles.vault` and the communication vault. Pass `--profile-store` and `--profile-name` to both `analyze` and `rewrite` only when that check confirms the profile is active, non-stale, and still matches the current corpus. The CLI deterministically infers the current communication context from the brief and applies only matching observations; use `--profile-context` only when the task provides a more precise controlled context. If the profile is missing, collecting, stale, source-mismatched, or unreadable, refresh it once when safe, then continue unprofiled if it still cannot qualify. Successfully retrieved live connector context may guide only the current response and must remain transient when ingestion fails. Put any useful bounded-coverage notice outside paste-ready copy.

Before drafting or revising content for a named recipient, also retrieve private complete-message context for that exact name from `runtime-data/interaction-communications.vault` with `mindfront.cli corpus context --include-thread-context`. Use the inferred or explicit communication context and a small relevant thread limit. Do this even when the derived profile is still collecting: complete message bodies and the surrounding ingested thread may improve terminology, continuity, open-question handling, and tone without lowering the profile evidence thresholds. Treat the response as private working context only. Keep it in memory or under `runtime-data`, never copy it into normal Mindfront artifacts, and describe thread coverage only as complete within the encrypted vault rather than complete source-system coverage.

Profile derivation may use complete Teams messages, Outlook emails, and resolved-ticket communications only after the authorization gate above is satisfied. Exclude prohibited, unnecessary, or unapproved content. Treat all resulting guidance as exact-context, directional communication assistance only: it is not psychological truth, a diagnosis, an exact response prediction, market evidence, or an employee-evaluation signal. Keep private profile details, examples, and source-message content out of reports, normal history, dashboards, and improvement plans. Require human review and never auto-send.

When documentation task validation is involved, run `task-protocol` after `research-plan`, pass `--task-protocol` into `report` and `store ingest`, and treat the protocol as a no-PII collection handoff, not evidence. When a filled no-PII session CSV exists, run `task-input` before `task-validation`; pass `--observation-source real_task_observation` only when the CSV contains real no-PII observations collected from the protocol. Generated or test-filled CSV rows must stay `synthetic_fixture`. Then pass `--task-validation` into `report` and `store ingest`. Keep synthetic fixtures separate from real task observations. When `-DbPath` is available, run `improvement-plan` after `store check-stale` and `dashboard build` so the next Codex pass has a ranked backlog.

Keep the evidence boundary explicit. Heuristic analysis, rewrite ranking, synthetic reader stress tests, task-observation protocols, synthetic task-validation fixtures, dashboards, improvement plans, and PDF rendering are not market evidence and do not validate user preference, conversion, adoption, or company-wide performance.

Use the bundled Python runtime if plain `python` fails in this Windows environment:

`$env:USERPROFILE\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe`

Before finalizing substantive changes, run the relevant targeted test plus the normal Mindfront verification flow:

- `project-tools/test-mindfront-automation.ps1` for hook or trigger changes.
- `project-tools/test-mindfront-runtime-pickup.ps1` for runtime pickup or Codex hook prerequisite changes.
- backend unit tests with `PYTHONPATH=backend/src`.
- `project-tools/test-mindfront-skill.ps1` for workflow/report/dashboard output quality.
- `project-tools/invoke-phase-verification.ps1 -RequirePlan -PlanPath <phase-plan> -Passes 3` before closing an automation phase.

For polished PDF deliverables, run `project-tools/render-mindfront-report-pdf.ps1` or `project-tools/test-mindfront-skill.ps1 -RenderPdf`, then inspect the rendered PDF before treating it as final.

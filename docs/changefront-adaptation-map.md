# Mindfront Changefront Adaptation Map

Status: Phase 0 policy.
The public repository policies in `docs/ethical-boundaries.md` and `docs/evidence-policy.md` are authoritative.

## Purpose

Mindfront should adapt Changefront's evidence discipline and local-first operating pattern without merging the projects. Changefront tracks external product changes. Mindfront evaluates messaging, claims, and research handoffs. The architecture lessons transfer, but the domain model must stay separate until Mindfront stabilizes.

## Adaptation Map

| Changefront Area | Mindfront Use | Action |
| --- | --- | --- |
| `registry.py` | source/evidence registry pattern | adapt |
| `policy.py` | evidence/no-go gates | adapt |
| `recommendations.py` | recommendation records | adapt |
| `db.py` | SQLite later | defer |
| `dashboard.py` | static dashboard later | defer |
| `delivery.py` | local digest later | defer |
| CLI command shape | command organization | adapt |
| Reddit/community policy | weak-signal separation analogy | reference only |

## Adapted Concepts

### Source And Evidence Registry

Mindfront needs a registry for:

- evidence sources
- proof records
- research notes
- principle support sources
- claim-support candidates
- validation results

Every source/evidence record should include owner, allowed uses, support tier, retention, excerpt policy, sensitive-data flag, status, limitations, and review timestamp.

### No-Go Gates

Mindfront should adapt no-go gates for:

- unsupported claims marked publish-ready
- sensitive domains without expert review
- synthetic outputs treated as real evidence
- external LLM use on blocked data
- missing artifact envelope
- stale outputs after input/config/evidence changes
- polished reports generated from invalid JSON/Markdown

### Recommendation Records

Mindfront recommendations should be structured records with:

- recommendation id
- source finding id
- claim ids affected
- principle or rubric references
- evidence basis
- finding confidence
- recommendation state
- limitation
- recommended validation
- blocked or publish-readiness state

### Weak-Signal Separation

Changefront separates weak community signals from official evidence. Mindfront should use the same discipline by separating:

- heuristic inference
- source evidence
- user-provided unverified proof
- synthetic reader stress tests
- local validation
- small user tests
- real user data
- expert review

Synthetic or heuristic agreement is not market proof.

## Deferred Concepts

Do not implement these until Mindfront has stable schemas, five local analysis examples, and at least three successful target-user workflows:

- SQLite history
- dashboard cards
- digest delivery
- local archive comparison
- source/runtime skill deployment

Dashboard rows must eventually include artifact id, source brief hash, config set hash, maturity state, evidence basis, finding confidence, recommendation state, validation state, sensitive-domain state, last run timestamp, and stale state.

## Separation Rules

- Do not merge Mindfront into Changefront during Phase 0 or MVP.
- Do not copy Changefront database schema without a Mindfront schema review.
- Do not use Changefront confidence labels directly if Mindfront's canonical confidence registry differs.
- Do not import community-signal behavior into Mindfront as evidence of market preference.
- Keep Mindfront source files, configs, examples, and artifacts project-local until the domain model is stable.

## Implementation Gates Borrowed From Changefront

| Gate | Mindfront Adaptation |
| --- | --- |
| Source registry required | Claims, proof, research evidence, and principles reference source/evidence ids where applicable. |
| Policy-first evaluation | Evidence, ethical, data, and LLM boundaries run before publish-ready or report-ready states. |
| Confidence is explicit | Separate evidence basis, finding confidence, and recommendation state. |
| Staleness matters | Source text, evidence, principles, rubrics, audience lenses, templates, or command options changing invalidates prior ready states. |
| Local-first output | Write JSON/Markdown and run manifests locally before dashboards, PDFs, or skill promotion. |

## Phase 0 Outcome

For Phase 0, the only required Changefront action is conceptual adaptation. The next implementation slice should create Mindfront-specific docs and config contracts first, then build the validator. Code reuse can be considered after Mindfront's schemas, gates, and artifacts are stable.

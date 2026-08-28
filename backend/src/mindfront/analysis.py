"""Deterministic Mindfront message analysis.

The first analyzer is intentionally conservative. It detects observable text
properties, maps them to configured dimensions, and keeps every recommendation
as a hypothesis or blocked state. It does not infer market preference.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import __version__
from .interaction_profiles import infer_interaction_context, profile_guidance
from .motivation import build_motivation_friction_report
from .schemas import REQUIRED_RUBRIC_DIMENSIONS, SENSITIVE_DOMAIN_CONTEXTS
from .validation import (
    BriefEvidenceResolution,
    ValidationError,
    resolve_brief_evidence,
    validate_brief_file,
    validate_config_root,
)


class AnalysisBlockedError(Exception):
    """Raised when validation prevents analysis."""

    def __init__(self, errors: list[ValidationError]):
        self.errors = errors
        super().__init__("Analysis blocked by validation errors.")


ABSTRACT_TERMS = {
    "accelerate",
    "best-in-class",
    "disrupt",
    "empower",
    "frictionless",
    "game-changing",
    "innovative",
    "next-generation",
    "optimize",
    "seamless",
    "synergy",
    "transform",
    "unlock",
    "world-class",
}

CATEGORY_TERMS = {
    "app",
    "platform",
    "product",
    "service",
    "software",
    "system",
    "tool",
    "toolkit",
    "workflow",
}

CTA_TERMS = {
    "book",
    "contact",
    "demo",
    "request",
    "schedule",
    "start",
    "test",
    "try",
}

CLAIM_TRIGGERS = {
    "automate",
    "boost",
    "cut",
    "double",
    "flag",
    "guarantee",
    "help",
    "improve",
    "increase",
    "prevent",
    "reduce",
    "save",
    "suggest",
    "validate",
}

JARGON_TERMS = {
    "cross-functional",
    "enablement",
    "go-to-market",
    "leverage",
    "operationalize",
    "paradigm",
    "stakeholder",
    "value stream",
}

DOCUMENT_CONTEXT_TERMS = {
    "documentation",
    "document",
    "docs",
    "guide",
    "handbook",
    "runbook",
    "report",
    "briefing",
    "playbook",
    "standard operating procedure",
    "sop",
}

FAST_PATH_TERMS = {
    "fast path",
    "quick start",
    "start here",
    "summary",
    "plain english",
    "practical rule",
    "checklist",
    "steps",
    "what to do",
    "decision",
    "owner",
    "input",
    "output",
    "example",
}

PRACTICAL_ACTION_TERMS = {
    "checklist",
    "command",
    "copy",
    "decision",
    "example",
    "input",
    "output",
    "owner",
    "path",
    "rule",
    "step",
    "verify",
}

LEARNING_TAX_TERMS = {
    "framework",
    "methodology",
    "training",
    "onboarding",
    "learn",
    "learning",
    "model",
    "program",
    "enablement",
    "change management",
}

EVIDENCE_BOUNDARY_PHRASES = {
    "evidence boundary",
    "evidence basis",
    "evidence status",
    "heuristic",
    "known limitation",
    "known limitations",
    "not market evidence",
    "not user research",
    "not validated",
    "sourced fact",
    "sourced facts",
    "synthetic",
    "validation status",
    "what is assumed",
    "what is sourced",
    "what remains unproven",
}

EVIDENCE_BOUNDARY_ANCHORS = {
    "claim",
    "claims",
    "evidence",
    "proof",
    "source",
    "sources",
    "sourced",
}

EVIDENCE_BOUNDARY_STATUS_TERMS = {
    "assumed",
    "assumption",
    "assumptions",
    "caveat",
    "caveats",
    "confidence",
    "heuristic",
    "limitation",
    "limitations",
    "pending",
    "sourced",
    "synthetic",
    "unproven",
    "unvalidated",
    "validated",
    "validation",
}

EVIDENCE_BOUNDARY_SEPARATORS = {
    "boundary",
    "distinguish",
    "label",
    "mark",
    "separate",
    "separates",
    "status",
}

EXPERT_AGENCY_RISK_TERMS = {
    "basic",
    "difficult",
    "entitled",
    "hand-holding",
    "lazy",
    "obvious",
    "obviously",
    "remedial",
    "resistant",
    "simple enough",
}

COERCIVE_GRAVITY_TERMS = {
    "addictive",
    "addicting",
    "cannot live without",
    "can't live without",
    "compulsive",
    "hooked",
    "irresistible",
}

PRESSURE_TERMS = {
    "act now",
    "before it is too late",
    "before they fall behind",
    "do not miss",
    "limited time",
    "only today",
}

SHAME_TERMS = {
    "fall behind",
    "only smart",
    "serious teams",
    "stupid",
}

SUPERLATIVE_TERMS = {
    "best",
    "best-in-class",
    "every",
    "guarantee",
    "guaranteed",
    "leading",
    "only",
    "proven",
}

PROFILE_ASSISTIVE_DIMENSIONS = {
    "opening_preference": ("opening", "opening_order"),
    "information_density": ("information_density", "density_adjustment"),
    "structure_preference": ("structure", "structure_adjustment"),
    "tone_register": ("tone_register", "tone_register_adjustment"),
    "action_clarity": ("action_clarity", "action_ownership_clarity"),
    "question_pattern": ("question_patterns", "anticipated_question_coverage"),
}

PROFILE_DIMENSION_ACTIONS = {
    "opening": "Put the most relevant result, issue, or context first.",
    "information_density": "Layer the content so the first pass is complete and supporting detail remains easy to scan.",
    "structure": "Use qualified signposting to separate the main point, supporting facts, and action.",
    "tone_register": "Use the qualified professional register without imitating personal slang or profanity.",
    "action_clarity": "Make the next step, ownership, or default choice explicit only where the source supplies it.",
    "question_patterns": "Move source-backed answers to recurrent question classes into easier-to-find positions.",
    "response_hypotheses": "Surface source-backed details relevant to qualified response hypotheses without predicting exact behavior.",
    "private_terminology": "Align terminology only when the current source already contains a qualified term; do not introduce private vocabulary.",
}


def analyze_message_brief(
    brief_path: str | Path,
    *,
    config_root: str | Path = "config",
    interaction_profile: dict[str, Any] | None = None,
    interaction_profile_context: str | None = None,
) -> dict[str, Any]:
    """Create a deterministic analysis report for one validated message brief."""

    config_path = Path(config_root)
    brief_file = Path(brief_path)
    validation_errors = [
        *validate_config_root(config_path, strict=True).errors,
        *validate_brief_file(brief_file, strict=True).errors,
    ]
    if validation_errors:
        raise AnalysisBlockedError(validation_errors)

    brief = _read_json(brief_file)
    config = _load_analysis_config(config_path)
    evidence_resolution = resolve_brief_evidence(
        brief_file,
        config_path,
        brief=brief,
    )
    source_text = brief["sourceText"]
    source_hash = _hash_text(source_text)
    brief_hash = _hash_file(brief_file)
    config_hash = _hash_config_files(config_path)
    interaction_candidate = None
    if interaction_profile is not None:
        inferred_context = infer_interaction_context(
            brief,
            explicit_context=interaction_profile_context,
        )
        interaction_candidate = profile_guidance(
            interaction_profile,
            context=inferred_context,
        )
    interaction_context = (
        interaction_candidate
        if interaction_candidate is not None and interaction_candidate["contextMatched"] is True
        else None
    )
    assistance_plan = _build_profile_assistance_plan(interaction_context, source_text)
    profile_hash = interaction_context["profileHash"] if assistance_plan["applied"] else ""
    report_id = f"report-{_hash_text(brief['briefId'] + source_hash + profile_hash)[:12]}"
    generated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")

    claims = _extract_claims(brief, evidence_resolution=evidence_resolution)
    findings = _build_findings(brief, claims)
    documentation_quality = _build_documentation_quality(brief, findings)
    scores = _build_scores(findings, config["rubric"], source_hash)
    motivation_friction = build_motivation_friction_report(brief, findings, claims)
    recommendations = _build_recommendations(findings, claims)
    if assistance_plan["applied"]:
        recommendations.append(
            _build_profile_assistance_recommendation(
                assistance_plan,
                recommendation_index=len(recommendations) + 1,
            )
        )
    research_questions = _build_research_questions(brief, findings, claims)

    has_blocked = any(recommendation["recommendationState"].startswith("blocked_") for recommendation in recommendations)
    sensitive_domain_state = _sensitive_domain_state(brief)
    real_user_data_available = any(
        claim["evidenceBasis"] == "real_user_data" and claim["supportStatus"] == "supported"
        for claim in claims
    )

    return {
        "artifactType": "message_analysis_report",
        "reportId": report_id,
        "briefId": brief["briefId"],
        "summary": _build_summary(findings, claims),
        "dataClassification": brief["dataClassification"],
        "evidenceBasisSummary": {
            "dominantBasis": "heuristic_inference",
            "marketEvidenceAvailable": False,
            "realUserDataAvailable": real_user_data_available,
            "sourceFactManifestResolved": evidence_resolution.source_fact_manifest_resolved,
            "resolvedProofSourceIds": sorted(evidence_resolution.resolved_proof_source_ids),
            "unresolvedProofSourceIds": sorted(evidence_resolution.unresolved_proof_source_ids),
            "notes": [
                "This report is based on deterministic text checks and user-provided context.",
                "It must not be treated as market research, conversion prediction, or validated user preference.",
            ],
        },
        "scores": scores,
        "claims": claims,
        "findings": findings,
        "documentationQuality": documentation_quality,
        "motivationFriction": motivation_friction,
        "recommendations": recommendations,
        "copyVariants": [],
        "researchQuestions": research_questions,
        "interactionAssistance": _interaction_assistance_summary(
            interaction_candidate,
            assistance_plan=assistance_plan,
        ),
        "limitations": [
            "No external market research was used.",
            "No synthetic reader output is treated as user evidence.",
            "Scores reflect observable text properties and configured heuristics only.",
            (
                "A named interaction profile may guide structure and anticipated questions, but it does not "
                "change claim support, prove preference, or predict exact behavior."
            ),
        ],
        "unsupportedClaimsVisible": True,
        "sensitiveDomainState": sensitive_domain_state,
        "validationState": "blocked" if has_blocked or sensitive_domain_state == "restricted_needs_review" else "valid",
        "sourceBriefHash": brief_hash,
        "sourceTextHash": f"sha256:{source_hash}",
        "configSetHash": config_hash,
        "principleSetHash": _hash_file(config_path / "psychology-principles.json"),
        "rubricHash": _hash_file(config_path / "message-quality-rubric.json"),
        "audienceLensHash": _hash_file(config_path / "audience-lenses.json"),
        "evidenceHash": _hash_file(config_path / "evidence-sources.json"),
        "templateHash": "sha256:not-used",
        "outputHash": "sha256:pending-until-written",
        "generatedAt": generated_at,
        "toolVersion": __version__,
        "configVersion": config["configVersion"],
    }


def _build_profile_assistance_plan(
    context: dict[str, Any] | None,
    source_text: str,
) -> dict[str, Any]:
    if context is None or context.get("contextMatched") is not True:
        return {
            "applied": False,
            "appliedDimensions": [],
            "transformationCodes": [],
            "privateTerminologyMatchedSource": False,
        }

    dimensions: set[str] = set()
    transformation_codes: set[str] = set()
    for observation in context.get("observedCommunicationPatterns", []):
        if observation.get("confidence") not in {"subject_confirmed", "context_supported"}:
            continue
        mapped = PROFILE_ASSISTIVE_DIMENSIONS.get(str(observation.get("dimension")))
        if mapped is None:
            continue
        dimension, transformation_code = mapped
        dimensions.add(dimension)
        transformation_codes.add(transformation_code)

    qualified_hypotheses = [
        item
        for item in context.get("likelyResponsePatterns", [])
        if item.get("confidence") == "context_supported"
    ]
    if qualified_hypotheses:
        dimensions.add("response_hypotheses")
        transformation_codes.add("response_hypothesis_coverage")

    guidance = context.get("guidance") or {}
    preferred_terms = [
        str(term).strip()
        for term in guidance.get("preferredTerminology", [])
        if str(term).strip()
    ]
    terms_to_avoid = [
        str(term).strip()
        for term in guidance.get("terminologyToAvoid", [])
        if str(term).strip()
    ]
    private_terminology_matched = any(
        _contains_semantic_phrase(source_text, term)
        for term in preferred_terms
    )
    terminology_to_avoid_matched = any(
        _contains_semantic_phrase(source_text, term)
        for term in terms_to_avoid
    )
    if private_terminology_matched or terminology_to_avoid_matched:
        dimensions.add("private_terminology")
        transformation_codes.add("private_terminology_alignment")

    return {
        "applied": bool(dimensions),
        "appliedDimensions": sorted(dimensions),
        "transformationCodes": sorted(transformation_codes),
        "privateTerminologyMatchedSource": private_terminology_matched,
    }


def _build_profile_assistance_recommendation(
    plan: dict[str, Any],
    *,
    recommendation_index: int,
) -> dict[str, Any]:
    dimensions = list(plan["appliedDimensions"])
    actions = [PROFILE_DIMENSION_ACTIONS[dimension] for dimension in dimensions]
    return {
        "recommendationId": f"recommendation-{recommendation_index:03d}",
        "summary": "Apply qualified, context-matched communication assistance to this draft.",
        "recommendationState": "hypothesis_to_test",
        "evidenceBasis": "directional_interaction_observation",
        "findingIds": [],
        "claimIds": [],
        "principleIds": ["processing-fluency", "validation-before-certainty"],
        "recommendedAction": " ".join(actions),
        "limitation": (
            "This adjustment is exact-context communication assistance, not psychological truth, "
            "diagnosis, employee evaluation, or evidence of recipient preference."
        ),
        "recommendedValidation": "Require human review and confirm the revised draft preserves every source claim.",
        "blockedReasons": [],
        "assistanceDimensions": dimensions,
        "privateContentIncluded": False,
    }


def _interaction_assistance_summary(
    context: dict[str, Any] | None,
    *,
    assistance_plan: dict[str, Any],
) -> dict[str, Any]:
    if context is None:
        return {
            "applied": False,
            "profileId": None,
            "profileHash": None,
            "recipientNameIncluded": False,
            "matchedContext": None,
            "contextMatched": False,
            "marketEvidenceCreated": False,
        }
    if context.get("contextMatched") is not True:
        return {
            "applied": False,
            "profileId": context["profileId"],
            "profileHash": context["profileHash"],
            "recipientNameIncluded": False,
            "matchedContext": context.get("matchedContext"),
            "contextMatched": False,
            "reason": "no_context_supported_profile_observation",
            "marketEvidenceCreated": False,
        }
    if not assistance_plan["applied"]:
        return {
            "applied": False,
            "profileId": context["profileId"],
            "profileHash": context["profileHash"],
            "recipientNameIncluded": False,
            "matchedContext": context.get("matchedContext"),
            "contextMatched": True,
            "reason": "no_qualified_actionable_guidance",
            "transformationSummary": {
                "status": "not_applied",
                "appliedDimensions": [],
                "transformationCodes": [],
                "privateContentIncluded": False,
                "claimEvidenceChanged": False,
            },
            "marketEvidenceCreated": False,
        }
    return {
        "applied": True,
        "profileId": context["profileId"],
        "profileHash": context["profileHash"],
        "recipientNameIncluded": False,
        "matchedContext": context.get("matchedContext"),
        "contextMatched": True,
        "expiresAt": context["expiresAt"],
        "humanReviewRequired": True,
        "automaticSendingAllowed": False,
        "privateGuidanceIncludedInReport": False,
        "transformationSummary": {
            "status": "recommendation_added",
            "appliedDimensions": list(assistance_plan["appliedDimensions"]),
            "transformationCodes": list(assistance_plan["transformationCodes"]),
            "privateTerminologyMatchedSource": assistance_plan["privateTerminologyMatchedSource"],
            "privateContentIncluded": False,
            "claimEvidenceChanged": False,
        },
        "evidenceBoundary": context["evidenceBoundary"],
        "marketEvidenceCreated": False,
    }


def write_analysis_report(report: dict[str, Any], output_path: str | Path) -> Path:
    """Write a report, filling its output hash with the final payload hash."""

    destination = Path(output_path)
    if destination.suffix.lower() != ".json":
        destination.mkdir(parents=True, exist_ok=True)
        destination = destination / "message-analysis-report.json"
    else:
        destination.parent.mkdir(parents=True, exist_ok=True)

    payload = finalize_analysis_report(report)
    destination.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return destination


def finalize_analysis_report(report: dict[str, Any]) -> dict[str, Any]:
    """Return a report with a stable hash for the emitted JSON payload."""

    payload = dict(report)
    payload["outputHash"] = "sha256:pending-until-written"
    provisional = json.dumps(payload, indent=2, sort_keys=True)
    payload["outputHash"] = f"sha256:{_hash_text(provisional)}"
    return payload


def _load_analysis_config(config_root: Path) -> dict[str, Any]:
    rubric = _read_json(config_root / "message-quality-rubric.json")
    config_versions = []
    for name in (
        "confidence-labels.json",
        "evidence-sources.json",
        "psychology-principles.json",
        "audience-lenses.json",
        "message-quality-rubric.json",
    ):
        data = _read_json(config_root / name)
        config_versions.append(str(data.get("version", "unknown")))

    return {
        "rubric": {dimension["dimensionId"]: dimension for dimension in rubric["dimensions"]},
        "configVersion": "+".join(config_versions),
    }


def _extract_claims(
    brief: dict[str, Any],
    *,
    evidence_resolution: BriefEvidenceResolution,
) -> list[dict[str, Any]]:
    sentences = _sentences(brief["sourceText"])
    proof_items = brief.get("proofAvailable") or []
    has_proof_notes = bool(proof_items)
    claims: list[dict[str, Any]] = []

    for sentence in sentences:
        lower = sentence.lower()
        if (
            brief.get("documentArchetype") in {"internal_executive_digest", "internal_operational_brief"}
            and _is_document_action_or_heading(sentence)
        ):
            continue
        if not _contains_any(lower, CLAIM_TRIGGERS) and not _has_quantified_claim(lower):
            continue

        claim_id = f"claim-{len(claims) + 1:03d}"
        strength = _claim_strength(lower)
        verified_fact_statements = {
            " ".join(str(statement).split()).lower()
            for statement in brief.get("verifiedFactStatements") or []
        }
        is_source_grounded_metric = (
            brief.get("documentArchetype") == "internal_executive_digest"
            and evidence_resolution.source_fact_manifest_resolved
            and bool(evidence_resolution.resolved_real_user_source_ids)
            and _has_quantified_claim(lower)
            and " ".join(sentence.split()).lower() in verified_fact_statements
        )
        if is_source_grounded_metric:
            evidence_basis = "real_user_data"
            support_status = "supported"
            evidence_ids = sorted(evidence_resolution.resolved_real_user_source_ids)
        else:
            evidence_basis = "user_provided_unverified" if has_proof_notes else "unsupported"
            support_status = "support_candidate" if has_proof_notes else "unsupported"
            evidence_ids = []
        if strength == "guaranteed" and evidence_basis != "real_user_data":
            support_status = "blocked"

        claims.append(
            {
                "claimId": claim_id,
                "claimText": sentence,
                "claimType": _claim_type(lower, brief),
                "claimStrength": strength,
                "sourceArtifactId": brief["briefId"],
                "sourceExcerpt": sentence,
                "sourceExcerptHash": f"sha256:{_hash_text(sentence)}",
                "evidenceBasis": evidence_basis,
                "evidenceIds": evidence_ids,
                "supportStatus": support_status,
                "limitations": _claim_limitations(evidence_basis, strength),
                "sensitiveDomainFlags": list(brief.get("sensitiveDomainFlags") or []),
            }
        )

    if not claims:
        claims.append(
            {
                "claimId": "claim-001",
                "claimText": brief["sourceText"][:240],
                "claimType": "other",
                "claimStrength": "low",
                "sourceArtifactId": brief["briefId"],
                "sourceExcerpt": brief["sourceText"][:240],
                "sourceExcerptHash": f"sha256:{_hash_text(brief['sourceText'][:240])}",
                "evidenceBasis": "unsupported",
                "evidenceIds": [],
                "supportStatus": "unsupported",
                "limitations": ["No explicit inspectable claim trigger was detected; review manually before publishing."],
                "sensitiveDomainFlags": list(brief.get("sensitiveDomainFlags") or []),
            }
        )

    return claims


def _build_findings(brief: dict[str, Any], claims: list[dict[str, Any]]) -> list[dict[str, Any]]:
    text = brief["sourceText"]
    lower = text.lower()
    sentences = _sentences(text)
    findings: list[dict[str, Any]] = []

    is_document = brief.get("documentArchetype") in {"internal_executive_digest", "internal_operational_brief"}
    is_informational = brief.get("communicationIntent") == "inform" or brief.get("decisionRequired") is False

    if not is_document and not _contains_any(lower, CATEGORY_TERMS):
        findings.append(
            _finding(
                findings,
                brief,
                dimension="clarity",
                severity="medium",
                issue="The copy does not clearly name a product category.",
                why="Readers need a fast category label before they can understand value or relevance.",
                excerpt=text[:180],
                principles=["category-clarity", "processing-fluency"],
                fix="Name the product category early, such as tool, workflow, platform, or service.",
                validation="Ask target users to name what the product is after reading the first sentence.",
            )
        )

    if not is_informational and not _contains_any(lower, CTA_TERMS):
        findings.append(
            _finding(
                findings,
                brief,
                dimension="clarity",
                severity="medium",
                issue="The copy does not state an explicit next action.",
                why="A reader may understand the concept but still not know what to do next.",
                excerpt=text[:180],
                principles=["processing-fluency"],
                fix=f"State the desired action directly: {brief['desiredAction'].replace('_', ' ')}.",
                validation="Ask readers what action they think the message is asking them to take.",
            )
        )

    for sentence in sentences:
        if len(_words(sentence)) > 32:
            findings.append(
                _finding(
                    findings,
                    brief,
                    dimension="cognitive_load",
                    severity="high",
                    issue="A sentence is long enough to create parsing friction.",
                    why="Long sentences make readers hold too many ideas in memory at once.",
                    excerpt=sentence,
                    principles=["cognitive-load-limits", "processing-fluency"],
                    fix="Split the sentence into one main idea and one supporting detail.",
                    validation="Have a target reader paraphrase the sentence without rereading.",
                )
            )

    jargon_hits = sorted(term for term in JARGON_TERMS if term in lower)
    if jargon_hits:
        findings.append(
            _finding(
                findings,
                brief,
                dimension="cognitive_load",
                severity="medium",
                issue=f"Potential jargon appears: {', '.join(jargon_hits)}.",
                why="Specialized terms can be useful, but unexplained jargon slows first-pass understanding.",
                excerpt=text[:220],
                principles=["cognitive-load-limits"],
                fix="Keep necessary domain terms, but replace generic jargon with concrete nouns and actions.",
                validation="Ask a target reader which terms need explanation.",
            )
        )

    abstract_hits = sorted(term for term in ABSTRACT_TERMS if term in lower)
    if abstract_hits:
        findings.append(
            _finding(
                findings,
                brief,
                dimension="concreteness",
                severity="medium",
                issue=f"Abstract persuasion terms appear: {', '.join(abstract_hits)}.",
                why="Abstract terms can sound attractive while leaving the actual object, action, or proof unclear.",
                excerpt=text[:220],
                principles=["concreteness-and-specificity", "category-clarity"],
                fix="Replace abstract value language with the specific action the tool performs and the proof available.",
                validation="Ask readers to identify the concrete action, output, and limit of the offer.",
            )
        )

    unverified_claims = [claim for claim in claims if claim["evidenceBasis"] == "user_provided_unverified"]
    blocked_claims = [claim for claim in claims if claim["supportStatus"] == "blocked"]
    if unverified_claims:
        findings.append(
            _finding(
                findings,
                brief,
                dimension="trust_proof",
                severity="medium",
                issue="The available proof is user-provided and unverified.",
                why="Unverified proof can support a hypothesis, but it cannot validate a claim for the exact market context.",
                excerpt=unverified_claims[0]["sourceExcerpt"],
                principles=["claim-proof-alignment", "validation-before-certainty"],
                fix="Keep the claim caveated and attach a method, sample, source id, and limitations before upgrading confidence.",
                validation="Record an evidence item or run a small target-user comprehension test.",
                claim_ids=[claim["claimId"] for claim in unverified_claims],
                evidence_basis="user_provided_unverified",
            )
        )

    if blocked_claims:
        findings.append(
            _finding(
                findings,
                brief,
                dimension="trust_proof",
                severity="blocked",
                issue="A guaranteed or high-certainty claim lacks qualifying evidence.",
                why="Strong claims need exact evidence or expert review before they can be used safely.",
                excerpt=blocked_claims[0]["sourceExcerpt"],
                principles=["claim-proof-alignment", "validation-before-certainty"],
                fix="Remove the guarantee or replace it with a qualified, testable claim.",
                validation="Provide exact real-user evidence or qualified expert review before publishing.",
                claim_ids=[claim["claimId"] for claim in blocked_claims],
                evidence_basis="unsupported",
            )
        )

    pressure_hits = sorted(term for term in PRESSURE_TERMS | SHAME_TERMS if term in lower)
    if pressure_hits:
        findings.append(
            _finding(
                findings,
                brief,
                dimension="ethical_risk",
                severity="high",
                issue=f"Pressure or shame language appears: {', '.join(pressure_hits)}.",
                why="Pressure language can reduce reader agency and create manipulative urgency.",
                excerpt=text[:220],
                principles=["user-agency-and-autonomy"],
                fix="Replace pressure with clear value, proof, limits, and a low-pressure next step.",
                validation="Ask readers whether the message clarifies the choice without making them feel pressured.",
            )
        )

    if brief["domainContext"] in SENSITIVE_DOMAIN_CONTEXTS or brief.get("sensitiveDomainFlags"):
        findings.append(
            _finding(
                findings,
                brief,
                dimension="ethical_risk",
                severity="blocked" if brief["expertReviewStatus"] != "completed" else "medium",
                issue="The brief touches a sensitive or restricted domain.",
                why="Sensitive domains require expert review before copy quality can be treated as safe enough for use.",
                excerpt=text[:220],
                principles=["sensitive-domain-gating", "user-agency-and-autonomy"],
                fix="Keep recommendations blocked until the required expert review is recorded.",
                validation="Complete expert review for the exact claim, audience, channel, and context.",
            )
        )

    _add_documentation_findings(brief, findings)
    return findings


def _add_documentation_findings(brief: dict[str, Any], findings: list[dict[str, Any]]) -> None:
    signals = _documentation_signals(brief)
    if not signals["detected"]:
        return

    text = brief["sourceText"]

    if not signals["fastPathVisible"]:
        findings.append(
            _finding(
                findings,
                brief,
                dimension="clarity",
                severity="medium",
                issue="Documentation is missing a fast path for specialist readers.",
                why="Specialists with scarce attention need the usable answer, decision path, or next action before extra context.",
                excerpt=text[:220],
                principles=["specialist-bandwidth-and-autonomy", "processing-fluency"],
                fix="Add a Start Here, Plain English, Practical Rule, or checklist block before background explanation.",
                validation="Ask specialists to find the answer for a real task and measure skim-to-answer time.",
            )
        )

    if signals["learningTaxRisk"]:
        findings.append(
            _finding(
                findings,
                brief,
                dimension="cognitive_load",
                severity="high",
                issue="The document creates a hidden learning tax before practical value.",
                why="A specialist may reject documentation that asks them to learn a framework before it helps them act.",
                excerpt=text[:220],
                principles=["specialist-bandwidth-and-autonomy", "cognitive-load-limits"],
                fix="Move framework or onboarding language after the task path, concrete example, and minimum viable action.",
                validation="Ask specialists where they first get enough information to act, and note where they stop reading.",
            )
        )

    if not signals["evidenceBoundaryVisible"]:
        findings.append(
            _finding(
                findings,
                brief,
                dimension="trust_proof",
                severity="medium",
                issue="Documentation does not make the evidence boundary visible.",
                why="Technical readers need to distinguish sourced fact, heuristic guidance, assumption, and validation status.",
                excerpt=text[:220],
                principles=["claim-proof-alignment", "validation-before-certainty", "specialist-bandwidth-and-autonomy"],
                fix="Add a short evidence boundary that names what is sourced, assumed, heuristic, synthetic, or unvalidated.",
                validation="Ask a technical reviewer to mark which claims are proven, assumed, or still need validation.",
            )
        )

    if signals["expertAgencyRisk"]:
        findings.append(
            _finding(
                findings,
                brief,
                dimension="ethical_risk",
                severity="high",
                issue=f"Language may reduce expert agency: {', '.join(signals['expertAgencyTerms'])}.",
                why="Status-sensitive readers may resist documentation that sounds remedial, dismissive, or controlling.",
                excerpt=text[:220],
                principles=["specialist-bandwidth-and-autonomy", "user-agency-and-autonomy"],
                fix="Replace remedial or judgmental phrasing with respectful precision, options, and clear tradeoffs.",
                validation="Ask specialists whether the document feels respectful, useful, and optional where choice exists.",
            )
        )

    if signals["coerciveGravityRisk"]:
        findings.append(
            _finding(
                findings,
                brief,
                dimension="ethical_risk",
                severity="high",
                issue=f"Reader momentum is framed as dependency or addiction: {', '.join(signals['coerciveGravityTerms'])}.",
                why="Documentation should create useful reading momentum without coercive, dependency, or dark-pattern framing.",
                excerpt=text[:220],
                principles=["documentation-gravity-without-coercion", "user-agency-and-autonomy"],
                fix="Reframe the goal as skim-to-answer speed, task completion, repeated usefulness, and respectful precision.",
                validation="Measure whether readers voluntarily reuse the document for real tasks; do not ask whether it feels addictive.",
            )
        )


def _build_documentation_quality(brief: dict[str, Any], findings: list[dict[str, Any]]) -> dict[str, Any]:
    signals = _documentation_signals(brief)
    documentation_principles = {
        "specialist-bandwidth-and-autonomy",
        "documentation-gravity-without-coercion",
    }
    linked_findings = [
        finding["findingId"]
        for finding in findings
        if documentation_principles.intersection(set(finding.get("principleIds", [])))
    ]
    return {
        "artifactType": "documentation_quality_signal",
        "detected": signals["detected"],
        "evidenceBasis": "heuristic_inference",
        "notMarketEvidence": True,
        "marketEvidenceCreated": False,
        "appliedLensIds": ["lens-specialist-bandwidth"] if signals["detected"] else [],
        "principleIds": sorted(documentation_principles) if signals["detected"] else [],
        "signals": {
            "fastPathVisible": signals["fastPathVisible"],
            "practicalActionVisible": signals["practicalActionVisible"],
            "learningTaxRisk": signals["learningTaxRisk"],
            "evidenceBoundaryVisible": signals["evidenceBoundaryVisible"],
            "expertAgencyRisk": signals["expertAgencyRisk"],
            "coerciveGravityRisk": signals["coerciveGravityRisk"],
        },
        "findingIds": linked_findings,
        "recommendedValidation": (
            "Ask specialists to use the documentation for a real task. Track skim-to-answer time, "
            "task completion, follow-up questions, skipped sections, coded trust-objection categories, and whether the document felt respectful."
            if signals["detected"]
            else "No documentation-specific validation plan was generated because the brief was not detected as documentation."
        ),
        "limitations": [
            "Documentation-quality signals are deterministic heuristics, not employee research.",
            "They cannot prove adoption, preference, productivity improvement, or C-suite impact.",
            "Task-based validation is required before making performance or adoption claims.",
        ],
    }


def _documentation_signals(brief: dict[str, Any]) -> dict[str, Any]:
    source_text = brief["sourceText"]
    lower = source_text.lower()
    context = " ".join(
        str(brief.get(field_name, ""))
        for field_name in ("projectName", "messageGoal", "targetAudience", "channel", "desiredAction")
    ).lower()
    combined = f"{context} {lower}"
    detected = _contains_any(combined, DOCUMENT_CONTEXT_TERMS)
    fast_path_visible = _contains_any(lower, FAST_PATH_TERMS)
    practical_action_visible = _contains_any(lower, PRACTICAL_ACTION_TERMS)
    learning_tax_terms = sorted(term for term in LEARNING_TAX_TERMS if term in lower)
    expert_agency_terms = sorted(term for term in EXPERT_AGENCY_RISK_TERMS if term in lower)
    coercive_gravity_terms = sorted(term for term in COERCIVE_GRAVITY_TERMS if term in lower)
    evidence_boundary_visible = _has_evidence_boundary(lower)
    learning_tax_risk = bool(learning_tax_terms) and not (fast_path_visible or practical_action_visible)

    return {
        "detected": detected,
        "fastPathVisible": fast_path_visible,
        "practicalActionVisible": practical_action_visible,
        "learningTaxRisk": detected and learning_tax_risk,
        "evidenceBoundaryVisible": evidence_boundary_visible,
        "expertAgencyRisk": detected and bool(expert_agency_terms),
        "expertAgencyTerms": expert_agency_terms,
        "coerciveGravityRisk": detected and bool(coercive_gravity_terms),
        "coerciveGravityTerms": coercive_gravity_terms,
    }


def _build_scores(
    findings: list[dict[str, Any]],
    rubric: dict[str, dict[str, Any]],
    source_text_hash: str,
) -> list[dict[str, Any]]:
    scores: list[dict[str, Any]] = []
    for dimension in REQUIRED_RUBRIC_DIMENSIONS:
        dimension_findings = [finding for finding in findings if finding["dimensionId"] == dimension]
        severity_points = {"low": 1, "medium": 2, "high": 3, "blocked": 5}
        penalty = max((severity_points[finding["severity"]] for finding in dimension_findings), default=0)
        score = max(0, 5 - penalty)
        if dimension == "trust_proof" and not dimension_findings:
            score = 4

        anchors = rubric[dimension]["scoreAnchors"]
        score_text = str(score)
        scores.append(
            {
                "scoreId": f"score-{dimension.replace('_', '-')}",
                "dimensionId": dimension,
                "score": score,
                "scoreScale": "0_to_5",
                "scoreReason": _score_reason(dimension, score, dimension_findings),
                "findingIds": [finding["findingId"] for finding in dimension_findings],
                "calibrationAnchor": anchors[score_text],
                "evidenceBasis": "heuristic_inference",
                "findingConfidence": "high_observable_text_issue" if dimension_findings else "medium",
                "sourceTextHash": f"sha256:{source_text_hash}",
                "configVersion": "rubric-v1",
            }
        )
    return scores


def _build_recommendations(
    findings: list[dict[str, Any]],
    claims: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    recommendations: list[dict[str, Any]] = []
    for finding in findings:
        if finding["severity"] == "blocked" and finding["dimensionId"] == "ethical_risk":
            state = "blocked_sensitive_domain"
        elif finding["severity"] == "blocked":
            state = "blocked_unsupported"
        else:
            state = "hypothesis_to_test"

        recommendations.append(
            {
                "recommendationId": f"recommendation-{len(recommendations) + 1:03d}",
                "summary": finding["issue"],
                "recommendationState": state,
                "evidenceBasis": finding["evidenceBasis"],
                "findingIds": [finding["findingId"]],
                "claimIds": finding["claimIds"],
                "principleIds": finding["principleIds"],
                "recommendedAction": finding["recommendedFix"],
                "limitation": finding["limitation"],
                "recommendedValidation": finding["recommendedValidation"],
                "blockedReasons": [finding["issue"]] if state.startswith("blocked_") else [],
            }
        )

    if not recommendations:
        recommendations.append(
            {
                "recommendationId": "recommendation-001",
                "summary": "The copy has no blocked deterministic issues in the Phase 0 checks.",
                "recommendationState": "ready_for_small_test",
                "evidenceBasis": "heuristic_inference",
                "findingIds": [],
                "claimIds": [claim["claimId"] for claim in claims],
                "principleIds": ["processing-fluency", "validation-before-certainty"],
                "recommendedAction": "Run a small target-user comprehension test before treating the copy as validated.",
                "limitation": "A clean deterministic pass is not market evidence.",
                "recommendedValidation": "Ask target users to explain the offer, proof, and next step in their own words.",
                "blockedReasons": [],
            }
        )

    return recommendations


def _build_research_questions(
    brief: dict[str, Any],
    findings: list[dict[str, Any]],
    claims: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    high_priority_findings = [
        finding["findingId"] for finding in findings if finding["severity"] in {"medium", "high", "blocked"}
    ]
    return [
        {
            "questionId": "research-001",
            "question": "Can target users explain what the offer is, who it is for, what proof is available, and what action to take after one pass?",
            "method": "comprehension_test",
            "audience": brief["targetAudience"],
            "evidenceGradeTarget": "small_user_test",
            "sampleSize": 5,
            "decisionThreshold": "At least four of five target users can accurately describe the offer, proof limits, and next step without interviewer explanation.",
            "relatedFindingIds": high_priority_findings,
            "relatedClaimIds": [claim["claimId"] for claim in claims],
        }
    ]


def _finding(
    existing: list[dict[str, Any]],
    brief: dict[str, Any],
    *,
    dimension: str,
    severity: str,
    issue: str,
    why: str,
    excerpt: str,
    principles: list[str],
    fix: str,
    validation: str,
    claim_ids: list[str] | None = None,
    evidence_basis: str = "heuristic_inference",
) -> dict[str, Any]:
    return {
        "findingId": f"finding-{len(existing) + 1:03d}",
        "dimensionId": dimension,
        "severity": severity,
        "findingConfidence": "high_observable_text_issue" if severity in {"high", "blocked"} else "medium",
        "evidenceBasis": evidence_basis,
        "inputExcerpt": excerpt,
        "issue": issue,
        "whyItMatters": why,
        "principleIds": principles,
        "rubricDimensionIds": [dimension],
        "claimIds": claim_ids or [],
        "recommendedFix": fix,
        "limitation": "This is a deterministic text finding, not evidence of market preference.",
        "recommendedValidation": validation,
        "sourceBriefId": brief["briefId"],
        "sourceTextHash": f"sha256:{_hash_text(brief['sourceText'])}",
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "toolVersion": __version__,
        "configVersion": "phase-0",
    }


def _score_reason(dimension: str, score: int, findings: list[dict[str, Any]]) -> str:
    if not findings:
        return f"{dimension} passed the current deterministic checks; user validation is still required."
    issues = "; ".join(finding["issue"] for finding in findings)
    return f"{dimension} scored {score}/5 because: {issues}"


def _build_summary(findings: list[dict[str, Any]], claims: list[dict[str, Any]]) -> str:
    blocked = [finding for finding in findings if finding["severity"] == "blocked"]
    if blocked:
        return "Deterministic analysis found blocked issues that must be resolved before treating the message as ready for testing."
    if findings:
        return "Deterministic analysis found message issues to fix or test; results are hypotheses, not market research."
    unsupported = [claim for claim in claims if claim["supportStatus"] in {"unsupported", "support_candidate"}]
    if unsupported:
        return "Deterministic analysis found no blocked text issues, but claims still require user validation or evidence before publish-ready status."
    return "Deterministic analysis found no blocked Phase 0 issues; run target-user validation before relying on the message."


def _sensitive_domain_state(brief: dict[str, Any]) -> str:
    if brief["domainContext"] == "general_b2b" and not brief.get("sensitiveDomainFlags"):
        return "not_sensitive"
    if brief["expertReviewStatus"] == "completed":
        return "review_completed"
    return "restricted_needs_review"


def _claim_strength(text: str) -> str:
    if "guarantee" in text or "guaranteed" in text or re.search(r"\b100\s*%", text):
        return "guaranteed"
    if _has_quantified_claim(text) or _contains_any(text, SUPERLATIVE_TERMS):
        return "strong"
    if _contains_any(text, CLAIM_TRIGGERS):
        return "moderate"
    return "low"


def _claim_type(text: str, brief: dict[str, Any] | None = None) -> str:
    if (
        brief
        and brief.get("documentArchetype") in {"internal_executive_digest", "internal_operational_brief"}
        and _has_quantified_claim(text)
    ):
        return "descriptive_metric"
    if "security" in text or "secure" in text or "compliance" in text:
        return "security"
    if _has_quantified_claim(text) or any(term in text for term in ("increase", "reduce", "save", "double")):
        return "performance"
    if any(term in text for term in ("prefer", "love", "want")):
        return "preference"
    if any(term in text for term in ("help", "suggest", "flag", "automate")):
        return "feature"
    return "other"


def _claim_limitations(evidence_basis: str, strength: str) -> list[str]:
    limitations = []
    if evidence_basis == "unsupported":
        limitations.append("No registered evidence or proof note supports this claim.")
    elif evidence_basis == "user_provided_unverified":
        limitations.append("Proof is user-provided and lacks complete method, sample, source id, and limitations.")
    elif evidence_basis == "real_user_data":
        limitations.append(
            "The source supports the descriptive metric only; it does not prove value, productivity, quality, or causation."
        )
    if strength in {"strong", "guaranteed"}:
        limitations.append("Strong claims require exact-context evidence or expert review before publishing.")
    return limitations or ["Claim requires target-context validation before publish-ready status."]


def _sentences(text: str) -> list[str]:
    return [part.strip() for part in re.split(r"(?<=[.!?])\s+", text) if part.strip()]


def _words(text: str) -> list[str]:
    return re.findall(r"[A-Za-z0-9]+(?:[-'][A-Za-z0-9]+)?", text)


def _has_quantified_claim(text: str) -> bool:
    return bool(re.search(r"\b\d+(?:\.\d+)?\s*(?:%|percent|x|times|days?|weeks?|hours?)?\b", text))


def _is_document_action_or_heading(text: str) -> bool:
    normalized = text.strip()
    lower = normalized.lower()
    if len(_words(normalized)) <= 6 and not _has_quantified_claim(lower):
        return True
    return lower.startswith(("i will ", "we will ", "i plan to ", "we plan to "))


def _contains_semantic_phrase(text: str, phrase: str) -> bool:
    text_tokens = re.findall(r"[A-Za-z0-9]+", text.casefold())
    phrase_tokens = re.findall(r"[A-Za-z0-9]+", phrase.casefold())
    if not phrase_tokens or len(phrase_tokens) > len(text_tokens):
        return False
    width = len(phrase_tokens)
    return any(text_tokens[index : index + width] == phrase_tokens for index in range(len(text_tokens) - width + 1))


def _contains_any(text: str, terms: set[str]) -> bool:
    return any(term in text for term in terms)


def _has_evidence_boundary(text: str) -> bool:
    if _contains_any(text, EVIDENCE_BOUNDARY_PHRASES):
        return True

    has_anchor = _contains_any(text, EVIDENCE_BOUNDARY_ANCHORS)
    has_status = _contains_any(text, EVIDENCE_BOUNDARY_STATUS_TERMS)
    has_separator = _contains_any(text, EVIDENCE_BOUNDARY_SEPARATORS)
    return has_anchor and has_status and has_separator


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _hash_file(path: Path) -> str:
    return f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"


def _hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _hash_config_files(config_root: Path) -> str:
    digest = hashlib.sha256()
    for name in sorted(path.name for path in config_root.glob("*.json")):
        digest.update(name.encode("utf-8"))
        digest.update((config_root / name).read_bytes())
    return f"sha256:{digest.hexdigest()}"

"""Deterministic rewrite generation with a conservative claim gate."""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import __version__
from .analysis import AnalysisBlockedError, analyze_message_brief
from .interaction_profiles import infer_interaction_context, profile_guidance


class RewriteBlockedError(Exception):
    """Raised when the source analysis is not safe to rewrite."""

    def __init__(self, reasons: list[dict[str, str]]):
        self.reasons = reasons
        super().__init__("Rewrite blocked by analysis or claim-gate rules.")


DEFAULT_STRATEGIES = (
    "plain_english_clarity",
    "proof_first",
    "problem_first",
    "cta_clarity",
)

SUPPORTED_STRATEGIES = {
    "plain_english_clarity",
    "proof_first",
    "problem_first",
    "risk_reduction",
    "technical_precision",
    "cta_clarity",
    "profile_guided",
}

HIGH_RISK_CLAIM_PATTERNS = (
    r"\bguarantee(?:d|s)?\b",
    r"\bproven\b",
    r"\bbest(?:-in-class)?\b",
    r"\bdouble\b",
    r"\b100\s*%",
    r"\b\d+(?:\.\d+)?\s*(?:%|percent|x|times)\b",
)

QUALIFIED_PROFILE_CONFIDENCE = {"subject_confirmed", "context_supported"}
PROFILE_DIMENSION_LABELS = {
    "opening_preference": "opening",
    "information_density": "information_density",
    "structure_preference": "structure",
    "tone_register": "tone_register",
    "action_clarity": "action_clarity",
    "question_pattern": "question_patterns",
}
QUESTION_TERMS = {
    "ownership": ("owner", "owns", "owned", "responsible"),
    "next_step": ("next step", "next action", "milestone"),
    "scope": ("scope", "boundary", "included", "excluded"),
    "risk": ("risk", "security", "control", "governance"),
    "evidence": ("evidence", "source", "data", "proof"),
    "implementation": ("implement", "implementation", "path", "build", "deploy"),
    "cost_or_effort": ("cost", "effort", "resource", "support"),
    "timeline": ("timeline", "date", "milestone", "when", "day", "week"),
}
RESPONSE_CLASS_TERMS = {
    "request_ownership": QUESTION_TERMS["ownership"],
    "request_next_step": QUESTION_TERMS["next_step"],
    "request_scope_clarification": QUESTION_TERMS["scope"],
    "request_risk_controls": QUESTION_TERMS["risk"],
    "request_evidence": QUESTION_TERMS["evidence"],
    "request_implementation_detail": QUESTION_TERMS["implementation"],
    "request_cost_or_effort": QUESTION_TERMS["cost_or_effort"],
    "request_timeline": QUESTION_TERMS["timeline"],
}


def rewrite_message_brief(
    brief_path: str | Path,
    *,
    config_root: str | Path = "config",
    strategies: list[str] | None = None,
    interaction_profile: dict[str, Any] | None = None,
    interaction_profile_context: str | None = None,
) -> dict[str, Any]:
    """Analyze a message brief and emit deterministic rewrite variants."""

    report = analyze_message_brief(
        brief_path,
        config_root=config_root,
        interaction_profile=interaction_profile,
        interaction_profile_context=interaction_profile_context,
    )
    brief = _read_json(Path(brief_path))
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
    return build_rewrite_bundle(
        brief,
        report,
        strategies=strategies,
        interaction_context=interaction_context,
        interaction_assistance=interaction_candidate,
    )


def build_rewrite_bundle(
    brief: dict[str, Any],
    analysis_report: dict[str, Any],
    *,
    strategies: list[str] | None = None,
    interaction_context: dict[str, Any] | None = None,
    interaction_assistance: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a copy variant bundle from a validated brief and analysis report."""

    _ensure_rewrite_allowed(analysis_report)
    generated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    source_text = brief["sourceText"]
    gate_context = _build_gate_context(brief, analysis_report)
    profile_plan = _build_profile_guidance_plan(interaction_context, source_text)
    selected_strategies = _resolve_strategies(
        strategies,
        brief,
        interaction_context if profile_plan["actionable"] else None,
    )
    rendered_candidates = [
        _render_strategy_result(
            strategy_id,
            brief,
            analysis_report,
            interaction_context,
            profile_plan=profile_plan,
        )
        for strategy_id in selected_strategies
    ]
    profile_result = next(
        (result for result in rendered_candidates if result["strategyId"] == "profile_guided"),
        None,
    )
    profile_distinctness = _profile_distinctness_check(
        profile_result,
        source_text=source_text,
        other_results=[
            result
            for result in rendered_candidates
            if result["strategyId"] != "profile_guided"
        ],
    )
    emitted_results = [
        result
        for result in rendered_candidates
        if result["strategyId"] != "profile_guided" or profile_distinctness["passed"]
    ]
    variants = []
    for index, result in enumerate(emitted_results, start=1):
        variant = _build_variant(
            index=index,
            strategy_id=result["strategyId"],
            copy=result["copy"],
            brief=brief,
            analysis_report=analysis_report,
        )
        if result["strategyId"] == "profile_guided":
            variant["interactionTransformation"] = dict(result["transformationSummary"])
            variant["distinctnessCheck"] = dict(profile_distinctness)
            variant["outputHash"] = f"sha256:{_hash_text(json.dumps(variant, sort_keys=True))}"
        variants.append(variant)

    profile_applied = bool(profile_result is not None and profile_distinctness["passed"])

    bundle = {
        "artifactType": "copy_variant_bundle",
        "bundleId": f"variant-bundle-{_hash_text(brief['briefId'] + analysis_report['reportId'])[:12]}",
        "briefId": brief["briefId"],
        "sourceAnalysisReportId": analysis_report["reportId"],
        "variants": variants,
        "claimGateSummary": _claim_gate_summary(variants),
        "contentGateSummary": _content_gate_summary(variants),
        "documentArchetype": brief.get("documentArchetype", "product_message"),
        "communicationIntent": brief.get("communicationIntent", "persuade"),
        "decisionRequired": brief.get("decisionRequired"),
        "readerTimeBudgetSeconds": brief.get("readerTimeBudgetSeconds"),
        "requiredTerms": list(brief.get("requiredTerms") or []),
        "prohibitedTerms": list(brief.get("prohibitedTerms") or []),
        "gateContext": gate_context,
        "gateContextHash": hash_gate_context(gate_context),
        "sourceNumericTokens": _numeric_tokens(source_text),
        "sourceWordCount": len(_words(source_text)),
        "sourceFactManifestHash": brief.get("sourceFactManifestHash"),
        "interactionAssistance": _interaction_assistance_summary(
            interaction_assistance if interaction_assistance is not None else interaction_context,
            applied=profile_applied,
            transformation_summary=(
                profile_result["transformationSummary"]
                if profile_result is not None
                else _empty_profile_transformation_summary()
            ),
            distinctness_check=profile_distinctness,
        ),
        "limitations": [
            "Variants are deterministic rewrites, not market-tested copy.",
            "Variants preserve unsupported or unverified claims as hypotheses; proof is still required before publishing.",
            "Content gates check source terms and numeric fidelity but do not prove that the source data is complete or correct.",
            "The claim and content gates do not replace human review.",
            (
                "Named communication profiles guide ordering and anticipated questions only; they do not "
                "change evidence status or predict exact responses."
            ),
        ],
        "sourceBriefHash": analysis_report["sourceBriefHash"],
        "sourceTextHash": analysis_report["sourceTextHash"],
        "configSetHash": analysis_report["configSetHash"],
        "templateHash": "sha256:not-used",
        "outputHash": "sha256:pending-until-written",
        "generatedAt": generated_at,
        "toolVersion": __version__,
        "sourceTextPreviewHash": f"sha256:{_hash_text(source_text[:240])}",
    }
    return bundle


def write_rewrite_bundle(bundle: dict[str, Any], output_path: str | Path) -> Path:
    """Write a rewrite bundle, filling its output hash."""

    destination = Path(output_path)
    if destination.suffix.lower() != ".json":
        destination.mkdir(parents=True, exist_ok=True)
        destination = destination / "copy-variants.json"
    else:
        destination.parent.mkdir(parents=True, exist_ok=True)

    payload = finalize_rewrite_bundle(bundle)
    destination.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return destination


def finalize_rewrite_bundle(bundle: dict[str, Any]) -> dict[str, Any]:
    """Return a bundle with a stable hash for the emitted payload."""

    payload = dict(bundle)
    payload["outputHash"] = "sha256:pending-until-written"
    provisional = json.dumps(payload, indent=2, sort_keys=True)
    payload["outputHash"] = f"sha256:{_hash_text(provisional)}"
    return payload


def _ensure_rewrite_allowed(analysis_report: dict[str, Any]) -> None:
    if analysis_report.get("validationState") == "blocked":
        raise RewriteBlockedError(
            [
                {
                    "code": "analysis_report_blocked",
                    "message": "Rewrite is blocked until source analysis blocking issues are resolved.",
                    "path": "validationState",
                }
            ]
        )


def _resolve_strategies(
    strategies: list[str] | None,
    brief: dict[str, Any],
    interaction_context: dict[str, Any] | None,
) -> tuple[str, ...]:
    if not strategies:
        if interaction_context is not None:
            return (
                "profile_guided",
                "proof_first",
                "problem_first",
                "technical_precision",
            )
        if brief.get("communicationIntent") == "inform" or brief.get("decisionRequired") is False:
            return (
                "plain_english_clarity",
                "proof_first",
                "problem_first",
                "technical_precision",
            )
        return DEFAULT_STRATEGIES
    unknown = [strategy for strategy in strategies if strategy not in SUPPORTED_STRATEGIES]
    if unknown:
        raise RewriteBlockedError(
            [
                {
                    "code": "unknown_strategy",
                    "message": f"Unknown rewrite strategy: {strategy}.",
                    "path": "strategy",
                }
                for strategy in unknown
            ]
        )
    return tuple(dict.fromkeys(strategies))


def _render_strategy_result(
    strategy_id: str,
    brief: dict[str, Any],
    analysis_report: dict[str, Any],
    interaction_context: dict[str, Any] | None,
    *,
    profile_plan: dict[str, Any],
) -> dict[str, Any]:
    if strategy_id == "profile_guided":
        if interaction_context is None:
            raise RewriteBlockedError(
                [
                    {
                        "code": "profile_guided_without_profile",
                        "message": "profile_guided requires active, qualified, context-matched guidance.",
                        "path": "strategy",
                    }
                ]
            )
        rendered = _render_profile_guided(brief, interaction_context, profile_plan=profile_plan)
        return {
            "strategyId": strategy_id,
            "copy": rendered["copy"],
            "transformationSummary": rendered["transformationSummary"],
        }
    return {
        "strategyId": strategy_id,
        "copy": _render_strategy(strategy_id, brief, analysis_report, interaction_context),
        "transformationSummary": _empty_profile_transformation_summary(),
    }


def _render_strategy(
    strategy_id: str,
    brief: dict[str, Any],
    analysis_report: dict[str, Any],
    interaction_context: dict[str, Any] | None = None,
) -> str:
    del analysis_report
    source = _normalize_text(brief["sourceText"])
    sentences = _sentences(source)
    is_informational = brief.get("communicationIntent") == "inform" or brief.get("decisionRequired") is False

    if strategy_id == "plain_english_clarity":
        return source

    if strategy_id == "profile_guided":
        if interaction_context is None:
            raise RewriteBlockedError(
                [
                    {
                        "code": "profile_guided_without_profile",
                        "message": "profile_guided requires an active named interaction profile.",
                        "path": "strategy",
                    }
                ]
            )
        return _render_profile_guided(
            brief,
            interaction_context,
            profile_plan=_build_profile_guidance_plan(interaction_context, source),
        )["copy"]

    if strategy_id == "proof_first":
        return _join_sentences(
            _prioritize_sentences(
                sentences,
                (
                    "estimated",
                    "source",
                    "does not",
                    "doesn't",
                    "not ",
                    "limitation",
                    "evidence",
                    "unverified",
                    "activity indicator",
                ),
            )
        )

    if strategy_id == "problem_first":
        return _join_sentences(
            _prioritize_sentences(
                sentences,
                (
                    "issue",
                    "request",
                    "activity",
                    "concentration",
                    "demand",
                    "risk",
                    "gap",
                    "without",
                ),
            )
        )

    if strategy_id == "risk_reduction":
        return _render_strategy("proof_first", brief, {}, interaction_context)

    if strategy_id == "technical_precision":
        return source

    if strategy_id == "cta_clarity":
        if is_informational:
            return source
        action = _action_phrase(brief["desiredAction"])
        if action.lower() in source.lower():
            return source
        return f"{source} Next step: {action}."

    raise RewriteBlockedError(
        [
            {
                "code": "unknown_strategy",
                "message": f"Unknown rewrite strategy: {strategy_id}.",
                "path": "strategy",
            }
        ]
    )


def _render_profile_guided(
    brief: dict[str, Any],
    interaction_context: dict[str, Any],
    *,
    profile_plan: dict[str, Any],
) -> dict[str, Any]:
    del interaction_context
    source = _normalize_text(brief["sourceText"])
    sentences = _sentences(source)
    dimensions: set[str] = set()
    transformation_codes: set[str] = set()
    priority_terms: list[str] = []

    opening_codes = profile_plan["observationCodes"].get("opening_preference", set())
    if opening_codes & {"bottom_line_first", "recommendation_first", "decision_request_first"}:
        priority_terms.extend(("recommend", "decision", "result", "status", "next step", "request", "action"))
        dimensions.add("opening")
        transformation_codes.add("opening_priority_applied")
    elif "problem_first" in opening_codes:
        priority_terms.extend(("issue", "problem", "risk", "gap", "without", "blocked"))
        dimensions.add("opening")
        transformation_codes.add("opening_priority_applied")
    elif "context_first" in opening_codes:
        priority_terms.extend(("context", "because", "constraint", "currently", "background"))
        dimensions.add("opening")
        transformation_codes.add("opening_priority_applied")

    question_terms = [
        term
        for code in profile_plan["observationCodes"].get("question_pattern", set())
        for term in QUESTION_TERMS.get(code, ())
    ]
    if question_terms and _first_matching_sentence(sentences, tuple(question_terms)) is not None:
        priority_terms.extend(question_terms)
        dimensions.add("question_patterns")
        transformation_codes.add("anticipated_question_coverage")

    response_terms = [
        term
        for response_class in profile_plan["responseClasses"]
        for term in RESPONSE_CLASS_TERMS.get(response_class, ())
    ]
    if response_terms and _first_matching_sentence(sentences, tuple(response_terms)) is not None:
        priority_terms.extend(response_terms)
        dimensions.add("response_hypotheses")
        transformation_codes.add("response_hypothesis_coverage")

    matched_private_terms = [
        term
        for term in profile_plan["preferredTerms"]
        if _contains_semantic_term(source, term)
    ]
    if matched_private_terms:
        priority_terms.extend(matched_private_terms)
        dimensions.add("private_terminology")
        transformation_codes.add("source_present_private_terminology_prioritized")

    ordered = _prioritize_sentences(sentences, tuple(dict.fromkeys(priority_terms))) if priority_terms else sentences

    action_codes = profile_plan["observationCodes"].get("action_clarity", set())
    action_sentence = _first_matching_sentence(
        ordered,
        ("next step", "next action", "owner", "owns", "responsible", "milestone", "recommend", "default"),
    )
    if action_codes and action_sentence is not None:
        ordered = [sentence for sentence in ordered if sentence != action_sentence] + [action_sentence]
        dimensions.add("action_clarity")
        transformation_codes.add("source_backed_action_isolated")

    opening_label = _profile_opening_label(opening_codes)
    tone_codes = profile_plan["observationCodes"].get("tone_register", set())
    tone_label = _profile_tone_label(tone_codes)
    if tone_label:
        dimensions.add("tone_register")
        transformation_codes.add("tone_register_signposted")
    top_label = tone_label or opening_label

    density_codes = profile_plan["observationCodes"].get("information_density", set())
    structure_codes = profile_plan["observationCodes"].get("structure_preference", set())
    copy = _format_profile_copy(
        ordered,
        top_label=top_label,
        action_sentence=action_sentence,
        density_codes=density_codes,
        structure_codes=structure_codes,
    )
    if density_codes:
        dimensions.add("information_density")
        transformation_codes.add("density_layering_applied")
    if structure_codes:
        dimensions.add("structure")
        transformation_codes.add("structure_signposting_applied")

    if not dimensions:
        copy = source

    return {
        "copy": copy,
        "transformationSummary": {
            "status": "candidate",
            "appliedDimensions": sorted(dimensions),
            "transformationCodes": sorted(transformation_codes),
            "qualifiedDimensionCount": len(profile_plan["qualifiedDimensions"]),
            "privateTerminologyMatchedSource": bool(matched_private_terms),
            "privateTerminologyIntroduced": False,
            "privateContentIncluded": False,
            "claimEvidenceChanged": False,
        },
    }


def _build_profile_guidance_plan(
    context: dict[str, Any] | None,
    source_text: str,
) -> dict[str, Any]:
    observation_codes: dict[str, set[str]] = {}
    if context is not None and context.get("contextMatched") is True:
        for observation in context.get("observedCommunicationPatterns", []):
            dimension = str(observation.get("dimension") or "")
            if (
                observation.get("confidence") in QUALIFIED_PROFILE_CONFIDENCE
                and dimension in PROFILE_DIMENSION_LABELS
            ):
                observation_codes.setdefault(dimension, set()).add(str(observation.get("tendencyCode") or ""))

    response_classes = {
        str(item.get("responseClass") or "")
        for item in (context or {}).get("likelyResponsePatterns", [])
        if item.get("confidence") == "context_supported"
        and str(item.get("responseClass") or "") in RESPONSE_CLASS_TERMS
    }
    guidance = (context or {}).get("guidance") or {}
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
    qualified_dimensions = {
        PROFILE_DIMENSION_LABELS[dimension]
        for dimension in observation_codes
    }
    if response_classes:
        qualified_dimensions.add("response_hypotheses")
    private_terminology_matched = any(
        _contains_semantic_term(source_text, term)
        for term in preferred_terms
    )
    if private_terminology_matched:
        qualified_dimensions.add("private_terminology")

    return {
        "actionable": bool(qualified_dimensions),
        "qualifiedDimensions": sorted(qualified_dimensions),
        "observationCodes": observation_codes,
        "responseClasses": response_classes,
        "preferredTerms": preferred_terms,
        "termsToAvoid": terms_to_avoid,
        "privateTerminologyMatchedSource": private_terminology_matched,
    }


def _format_profile_copy(
    sentences: list[str],
    *,
    top_label: str | None,
    action_sentence: str | None,
    density_codes: set[str],
    structure_codes: set[str],
) -> str:
    body_sentences = [
        sentence
        for sentence in sentences
        if sentence != action_sentence
    ]
    sections: list[str] = []
    if top_label and body_sentences:
        sections.append(f"{top_label} {body_sentences.pop(0)}")

    if "bullets" in structure_codes and body_sentences:
        sections.append("Key points:\n" + "\n".join(f"- {sentence}" for sentence in body_sentences))
    elif "decision_action_sections" in structure_codes and body_sentences:
        sections.append("Supporting facts:\n" + _join_sentences(body_sentences))
    elif "table_for_comparison" in structure_codes and body_sentences:
        sections.append("Comparison points:\n" + "\n".join(f"- {sentence}" for sentence in body_sentences))
    elif body_sentences:
        detail_label = "Details:" if density_codes & {"layered_detail", "detailed_by_default"} else "Key points:"
        sections.append(f"{detail_label} {_join_sentences(body_sentences)}")

    if not sections and sentences:
        sections.append(f"Summary: {sentences[0]}")
        if len(sentences) > 1:
            sections.append(f"Details: {_join_sentences(sentences[1:])}")

    if action_sentence is not None:
        sections.append(f"Next step: {action_sentence}")
    return "\n\n".join(sections)


def _profile_opening_label(codes: set[str]) -> str | None:
    if codes & {"bottom_line_first", "recommendation_first", "decision_request_first"}:
        return "Bottom line:"
    if "problem_first" in codes:
        return "Current issue:"
    if "context_first" in codes:
        return "Context:"
    return None


def _profile_tone_label(codes: set[str]) -> str | None:
    if "informal_direct" in codes:
        return "Quick update:"
    if "formal_for_decisions" in codes:
        return "Decision summary:"
    if "neutral_professional" in codes:
        return "Summary:"
    return None


def _first_matching_sentence(sentences: list[str], terms: tuple[str, ...]) -> str | None:
    return next(
        (
            sentence
            for sentence in sentences
            if any(term in sentence.casefold() for term in terms)
        ),
        None,
    )


def _empty_profile_transformation_summary() -> dict[str, Any]:
    return {
        "status": "not_applied",
        "appliedDimensions": [],
        "transformationCodes": [],
        "qualifiedDimensionCount": 0,
        "privateTerminologyMatchedSource": False,
        "privateTerminologyIntroduced": False,
        "privateContentIncluded": False,
        "claimEvidenceChanged": False,
    }


def _profile_distinctness_check(
    profile_result: dict[str, Any] | None,
    *,
    source_text: str,
    other_results: list[dict[str, Any]],
) -> dict[str, Any]:
    if profile_result is None:
        return {
            "passed": False,
            "byteDistinctFromSource": False,
            "semanticDistinctFromSource": False,
            "distinctFromOtherVariants": False,
            "duplicateStrategyIds": [],
            "comparisonMethod": "casefolded_token_sequence_v1",
        }
    copy = profile_result["copy"]
    copy_fingerprint = _semantic_fingerprint(copy)
    duplicate_strategy_ids = [
        result["strategyId"]
        for result in other_results
        if _semantic_fingerprint(result["copy"]) == copy_fingerprint
    ]
    byte_distinct = copy != source_text
    semantic_distinct = copy_fingerprint != _semantic_fingerprint(source_text)
    distinct_from_others = not duplicate_strategy_ids
    return {
        "passed": byte_distinct and semantic_distinct and distinct_from_others,
        "byteDistinctFromSource": byte_distinct,
        "semanticDistinctFromSource": semantic_distinct,
        "distinctFromOtherVariants": distinct_from_others,
        "duplicateStrategyIds": duplicate_strategy_ids,
        "comparisonMethod": "casefolded_token_sequence_v1",
    }


def _semantic_fingerprint(text: str) -> tuple[str, ...]:
    return tuple(re.findall(r"[A-Za-z0-9]+", text.casefold()))


def _interaction_assistance_summary(
    context: dict[str, Any] | None,
    *,
    applied: bool,
    transformation_summary: dict[str, Any],
    distinctness_check: dict[str, Any],
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
    if not applied:
        reason = (
            "no_qualified_actionable_guidance"
            if transformation_summary.get("qualifiedDimensionCount", 0) == 0
            else "no_distinct_profile_transformation"
        )
        return {
            "applied": False,
            "profileId": context["profileId"],
            "profileHash": context["profileHash"],
            "recipientNameIncluded": False,
            "matchedContext": context.get("matchedContext"),
            "contextMatched": True,
            "reason": reason,
            "transformationSummary": {
                **transformation_summary,
                "status": "not_applied",
                "privateContentIncluded": False,
                "claimEvidenceChanged": False,
            },
            "distinctnessCheck": distinctness_check,
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
        "privateGuidanceIncludedInBundle": False,
        "transformationSummary": {
            **transformation_summary,
            "status": "applied",
            "privateContentIncluded": False,
            "claimEvidenceChanged": False,
        },
        "distinctnessCheck": distinctness_check,
        "evidenceBoundary": context["evidenceBoundary"],
        "marketEvidenceCreated": False,
    }


def _build_variant(
    *,
    index: int,
    strategy_id: str,
    copy: str,
    brief: dict[str, Any],
    analysis_report: dict[str, Any],
) -> dict[str, Any]:
    gate_evaluation = evaluate_copy_gates(
        copy,
        source_text=brief["sourceText"],
        required_terms=brief.get("requiredTerms"),
        prohibited_terms=brief.get("prohibitedTerms"),
    )
    gate_status = gate_evaluation["claimGateStatus"]
    content_gate_status = gate_evaluation["contentGateStatus"]
    existing_claim_ids = [claim["claimId"] for claim in analysis_report["claims"]]
    has_unverified_claims = any(claim.get("supportStatus") != "supported" for claim in analysis_report["claims"])
    recommendation_state = "hypothesis_to_test"
    if gate_status == "blocked_new_unsupported_claim" or content_gate_status != "passed":
        recommendation_state = "blocked_unsupported"
    elif not has_unverified_claims:
        recommendation_state = "ready_for_small_test"

    variant = {
        "variantId": f"variant-{index:03d}",
        "strategyId": strategy_id,
        "copy": copy,
        "intendedEffect": _intended_effect(strategy_id),
        "tradeoffs": _tradeoffs(strategy_id),
        "introducedClaimIds": [],
        "preservedClaimIds": existing_claim_ids,
        "removedClaimIds": [],
        "recommendationState": recommendation_state,
        "evidenceBasis": "heuristic_inference",
        "requiresProofBeforePublishing": (
            has_unverified_claims or gate_status != "passed" or content_gate_status != "passed"
        ),
        **gate_evaluation,
        "recommendedValidation": "Run a small target-user comprehension test before treating this variant as ready.",
        "parentArtifactIds": [analysis_report["reportId"]],
        "sourceBriefHash": analysis_report["sourceBriefHash"],
        "templateHash": "sha256:not-used",
        "outputHash": "sha256:pending-until-written",
    }
    variant["outputHash"] = f"sha256:{_hash_text(json.dumps(variant, sort_keys=True))}"
    return variant


def evaluate_copy_gates(
    copy: str,
    *,
    source_text: str,
    required_terms: list[str] | None = None,
    prohibited_terms: list[str] | None = None,
) -> dict[str, Any]:
    """Recompute all claim and source-fidelity gates from the current copy."""

    claim_status, claim_reasons = _claim_gate(copy, source_text)
    content_status, content_reasons, content_metrics = _content_gate(
        copy,
        {
            "sourceText": source_text,
            "requiredTerms": required_terms or [],
            "prohibitedTerms": prohibited_terms or [],
        },
    )
    return {
        "claimGateStatus": claim_status,
        "claimGateReasons": claim_reasons,
        "contentGateStatus": content_status,
        "contentGateReasons": content_reasons,
        **content_metrics,
    }


def hash_gate_context(gate_context: dict[str, Any]) -> str:
    """Return the stable hash used to bind comparison inputs to rewrite context."""

    canonical = json.dumps(gate_context, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return f"sha256:{_hash_text(canonical)}"


def _build_gate_context(brief: dict[str, Any], analysis_report: dict[str, Any]) -> dict[str, Any]:
    return {
        "sourceText": brief["sourceText"],
        "requiredTerms": list(brief.get("requiredTerms") or []),
        "prohibitedTerms": list(brief.get("prohibitedTerms") or []),
        "analysisClaims": [
            {
                "claimId": claim["claimId"],
                "supportStatus": claim["supportStatus"],
            }
            for claim in analysis_report["claims"]
        ],
        "sourceTextHash": analysis_report["sourceTextHash"],
        "sourceBriefHash": analysis_report["sourceBriefHash"],
        "sourceAnalysisReportId": analysis_report["reportId"],
        "interactionProfileHash": (analysis_report.get("interactionAssistance") or {}).get("profileHash"),
    }


def _claim_gate(copy: str, source_text: str) -> tuple[str, list[str]]:
    copy_lower = copy.lower()
    source_lower = source_text.lower()
    reasons: list[str] = []
    for pattern in HIGH_RISK_CLAIM_PATTERNS:
        if re.search(pattern, copy_lower) and not re.search(pattern, source_lower):
            reasons.append(f"Variant introduces high-risk unsupported claim pattern: {pattern}.")

    if reasons:
        return "blocked_new_unsupported_claim", reasons
    return "passed", []


def _claim_gate_summary(variants: list[dict[str, Any]]) -> dict[str, Any]:
    blocked = [variant["variantId"] for variant in variants if variant["claimGateStatus"] != "passed"]
    return {
        "status": "blocked" if blocked else "passed",
        "blockedVariantIds": blocked,
        "passedVariantIds": [variant["variantId"] for variant in variants if variant["claimGateStatus"] == "passed"],
        "marketEvidenceCreated": False,
    }


def _content_gate(copy: str, brief: dict[str, Any]) -> tuple[str, list[str], dict[str, Any]]:
    source_text = _normalize_text(brief["sourceText"])
    copy_text = _normalize_text(copy)
    source_numbers = _numeric_tokens(source_text)
    copy_numbers = _numeric_tokens(copy_text)
    missing_numbers = list((Counter(source_numbers) - Counter(copy_numbers)).elements())
    introduced_numbers = list((Counter(copy_numbers) - Counter(source_numbers)).elements())
    required_terms = [term.strip() for term in brief.get("requiredTerms") or [] if term.strip()]
    prohibited_terms = [term.strip() for term in brief.get("prohibitedTerms") or [] if term.strip()]
    copy_lower = copy_text.lower()
    missing_terms = [term for term in required_terms if not _contains_semantic_term(copy_text, term)]
    present_prohibited_terms = [term for term in prohibited_terms if _contains_semantic_term(copy_text, term)]
    source_sentences = _sentences(source_text)
    preserved_sentences = [sentence for sentence in source_sentences if sentence.lower() in copy_lower]
    source_coverage = len(preserved_sentences) / len(source_sentences) if source_sentences else 1.0

    reasons: list[str] = []
    if missing_numbers:
        reasons.append(f"Variant omits source numeric tokens: {', '.join(missing_numbers)}.")
    if introduced_numbers:
        reasons.append(f"Variant introduces numeric tokens not present in the source: {', '.join(introduced_numbers)}.")
    if missing_terms:
        reasons.append(f"Variant omits required terms: {', '.join(missing_terms)}.")
    if present_prohibited_terms:
        reasons.append(f"Variant includes prohibited terms: {', '.join(present_prohibited_terms)}.")
    copy_mentions_mindfront = _contains_semantic_term(copy_text, "Mindfront")
    source_mentions_mindfront = _contains_semantic_term(source_text, "Mindfront")
    if copy_mentions_mindfront and not source_mentions_mindfront:
        reasons.append("Variant changes the source subject by introducing Mindfront.")
    if source_coverage < 1.0:
        reasons.append("Variant does not preserve every source sentence.")

    metrics = {
        "numericFidelity": 1.0 if not missing_numbers and not introduced_numbers else 0.0,
        "missingNumericTokens": missing_numbers,
        "introducedNumericTokens": introduced_numbers,
        "requiredTermCoverage": (
            (len(required_terms) - len(missing_terms)) / len(required_terms) if required_terms else 1.0
        ),
        "missingRequiredTerms": missing_terms,
        "presentProhibitedTerms": present_prohibited_terms,
        "sourceCoverage": round(source_coverage, 4),
        "sourceSubjectPreserved": not copy_mentions_mindfront or source_mentions_mindfront,
    }
    return ("passed" if not reasons else "blocked_source_fidelity"), reasons, metrics


def _content_gate_summary(variants: list[dict[str, Any]]) -> dict[str, Any]:
    blocked = [variant["variantId"] for variant in variants if variant["contentGateStatus"] != "passed"]
    return {
        "status": "blocked" if blocked else "passed",
        "blockedVariantIds": blocked,
        "passedVariantIds": [variant["variantId"] for variant in variants if variant["contentGateStatus"] == "passed"],
        "numericFidelityRequired": True,
        "sourceCoverageRequired": 1.0,
        "marketEvidenceCreated": False,
    }


def _intended_effect(strategy_id: str) -> str:
    effects = {
        "plain_english_clarity": "Make the offer, action, and validation limit easier to understand after one pass.",
        "proof_first": "Lead with the evidence boundary so readers do not mistake the copy for validated research.",
        "problem_first": "Start from the user's practical situation before describing the workflow.",
        "risk_reduction": "Reduce overclaim and manipulation risk while preserving a useful next step.",
        "technical_precision": "Make the artifact and output model more inspectable for evaluators.",
        "cta_clarity": "Make the requested next action explicit.",
        "profile_guided": "Order the same sourced content around the recipient's observed communication patterns.",
    }
    return effects[strategy_id]


def _tradeoffs(strategy_id: str) -> list[str]:
    tradeoffs = {
        "plain_english_clarity": ["Less distinctive phrasing", "More explicit caveats"],
        "proof_first": ["More conservative tone", "Lower emotional momentum"],
        "problem_first": ["Longer setup", "Depends on audience fit"],
        "risk_reduction": ["Less urgency", "May feel less promotional"],
        "technical_precision": ["More operational language", "Less broad appeal"],
        "cta_clarity": ["More direct ask", "Less room for narrative build"],
        "profile_guided": [
            "Context-specific rather than universal",
            "Requires human review because the profile is directional",
        ],
    }
    return tradeoffs[strategy_id]


def _clean_audience(audience: str) -> str:
    cleaned = audience.strip().rstrip(".")
    if len(cleaned) > 90:
        return "a team"
    return cleaned[:1].lower() + cleaned[1:]


def _action_phrase(desired_action: str) -> str:
    action = desired_action.replace("_", " ").strip().lower()
    article_actions = {
        "book demo": "book a demo",
        "request demo": "request a demo",
        "schedule demo": "schedule a demo",
        "start trial": "start a trial",
    }
    return article_actions.get(action, action)


def _normalize_text(text: str) -> str:
    return " ".join(text.split())


def _sentences(text: str) -> list[str]:
    return [part.strip() for part in re.split(r"(?<=[.!?])\s+", text) if part.strip()]


def _join_sentences(sentences: list[str]) -> str:
    return " ".join(sentences)


def _prioritize_sentences(sentences: list[str], terms: tuple[str, ...]) -> list[str]:
    priority = [sentence for sentence in sentences if any(term in sentence.lower() for term in terms)]
    remaining = [sentence for sentence in sentences if sentence not in priority]
    return priority + remaining


def _numeric_tokens(text: str) -> list[str]:
    return re.findall(r"(?<![A-Za-z0-9])\$?\d[\d,]*(?:\.\d+)?(?:[KMB])?(?:%|x)?(?![A-Za-z0-9])", text)


def _contains_semantic_term(text: str, term: str) -> bool:
    term_tokens = _semantic_tokens(term)
    if not term_tokens:
        return False
    text_tokens = _semantic_tokens(text)
    phrase_length = len(term_tokens)
    return any(
        text_tokens[index : index + phrase_length] == term_tokens
        for index in range(len(text_tokens) - phrase_length + 1)
    )


def _semantic_tokens(text: str) -> list[str]:
    return [
        token.casefold()
        for token in re.findall(r"[A-Za-z0-9]+(?:[+#][A-Za-z0-9+#]*)*", text)
    ]


def _words(text: str) -> list[str]:
    return re.findall(r"[A-Za-z0-9]+(?:[-'][A-Za-z0-9]+)?", text)


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()

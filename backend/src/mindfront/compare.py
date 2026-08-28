"""Deterministic comparison for gated copy variants."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from json import JSONDecodeError
from pathlib import Path
from typing import Any

from . import __version__
from .rewrite import evaluate_copy_gates, hash_gate_context


class CompareBlockedError(Exception):
    """Raised when a variant bundle cannot be compared."""

    def __init__(self, reasons: list[dict[str, str]]):
        self.reasons = reasons
        super().__init__("Variant comparison blocked by input errors.")


CTA_PATTERNS = (
    r"\brequest a demo\b",
    r"\bbook a demo\b",
    r"\bschedule a demo\b",
    r"\bstart a trial\b",
    r"\bnext step\b",
    r"\btry\b",
)

PROOF_BOUNDARY_TERMS = {
    "before formal market research",
    "does not replace market research",
    "hypotheses to test",
    "needs proof",
    "proof gaps",
    "validation",
    "validate",
}

PRESSURE_TERMS = {
    "act now",
    "before it is too late",
    "fall behind",
    "limited time",
    "only today",
    "serious teams",
}


def compare_variant_bundle(variant_bundle_path: str | Path) -> dict[str, Any]:
    """Compare a copy variant bundle using deterministic criteria."""

    path = Path(variant_bundle_path)
    bundle = _load_bundle(path)
    _validate_bundle(bundle, str(path))

    evaluations = [_evaluate_variant(variant, bundle) for variant in bundle["variants"]]
    ranked = _rank_evaluations(evaluations)
    claim_gate_summary = _claim_gate_summary(evaluations)
    content_gate_summary = _content_gate_summary(evaluations)
    recommended = [
        item["variantId"]
        for item in ranked
        if _gates_pass(item) and item["rank"] <= 2
    ]
    is_informational = bundle.get("communicationIntent") == "inform" or bundle.get("decisionRequired") is False

    report = {
        "artifactType": "variant_comparison_report",
        "comparisonId": f"comparison-{_hash_text(bundle['bundleId'] + bundle['sourceTextHash'])[:12]}",
        "sourceVariantBundleId": bundle["bundleId"],
        "briefId": bundle["briefId"],
        "summary": _summary(ranked, recommended),
        "rankedVariants": ranked,
        "recommendedVariantIds": recommended,
        "recommendationState": (
            "candidate_for_human_review" if recommended and is_informational
            else "hypothesis_to_test" if recommended
            else "blocked_unsupported"
        ),
        "evidenceBasis": "heuristic_inference",
        "claimGateSummary": claim_gate_summary,
        "contentGateSummary": content_gate_summary,
        "gateEvaluationSource": "recomputed_from_current_copy_and_bound_source_context",
        "documentArchetype": bundle.get("documentArchetype"),
        "communicationIntent": bundle.get("communicationIntent"),
        "decisionRequired": bundle.get("decisionRequired"),
        "interactionAssistance": _interaction_assistance_summary(bundle),
        "marketEvidenceCreated": False,
        "recommendedValidation": "Run a small target-user comprehension test on the top ranked variants before using the result.",
        "limitations": [
            "Comparison uses deterministic text features only.",
            "Ranking does not prove market preference, conversion lift, comprehension, or persuasion.",
            "Source-fidelity checks do not prove source completeness, business value, productivity, quality, or causation.",
            "Any variant with unverified source claims still requires proof before publishing.",
        ],
        "sourceBriefHash": bundle["sourceBriefHash"],
        "sourceTextHash": bundle["sourceTextHash"],
        "sourceVariantBundleHash": _hash_file(path),
        "configSetHash": bundle["configSetHash"],
        "templateHash": "sha256:not-used",
        "outputHash": "sha256:pending-until-written",
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "toolVersion": __version__,
    }
    return report


def _interaction_assistance_summary(bundle: dict[str, Any]) -> dict[str, Any]:
    source = bundle.get("interactionAssistance")
    if not isinstance(source, dict) or source.get("applied") is not True:
        return {
            "applied": False,
            "profileId": source.get("profileId") if isinstance(source, dict) else None,
            "profileHash": source.get("profileHash") if isinstance(source, dict) else None,
            "recipientNameIncluded": False,
            "matchedContext": source.get("matchedContext") if isinstance(source, dict) else None,
            "contextMatched": False,
            "reason": source.get("reason") if isinstance(source, dict) else None,
            "marketEvidenceCreated": False,
        }
    return {
        "applied": True,
        "profileId": source.get("profileId"),
        "profileHash": source.get("profileHash"),
        "recipientNameIncluded": False,
        "matchedContext": source.get("matchedContext"),
        "contextMatched": True,
        "expiresAt": source.get("expiresAt"),
        "humanReviewRequired": True,
        "automaticSendingAllowed": False,
        "privateGuidanceIncludedInComparison": False,
        "marketEvidenceCreated": False,
    }


def write_comparison_report(report: dict[str, Any], output_path: str | Path) -> Path:
    """Write a comparison report, filling its output hash."""

    destination = Path(output_path)
    if destination.suffix.lower() != ".json":
        destination.mkdir(parents=True, exist_ok=True)
        destination = destination / "variant-comparison.json"
    else:
        destination.parent.mkdir(parents=True, exist_ok=True)

    payload = finalize_comparison_report(report)
    destination.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return destination


def finalize_comparison_report(report: dict[str, Any]) -> dict[str, Any]:
    """Return a comparison report with a stable emitted-payload hash."""

    payload = dict(report)
    payload["outputHash"] = "sha256:pending-until-written"
    provisional = json.dumps(payload, indent=2, sort_keys=True)
    payload["outputHash"] = f"sha256:{_hash_text(provisional)}"
    return payload


def _load_bundle(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise CompareBlockedError(
            [
                {
                    "code": "missing_variant_bundle",
                    "message": "Variant bundle file does not exist.",
                    "path": str(path),
                }
            ]
        )
    if not path.is_file():
        raise CompareBlockedError(
            [
                {
                    "code": "invalid_variant_bundle_path",
                    "message": "Variant bundle path must be a file.",
                    "path": str(path),
                }
            ]
        )

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except JSONDecodeError as exc:
        raise CompareBlockedError(
            [
                {
                    "code": "invalid_json",
                    "message": f"Invalid JSON at line {exc.lineno}, column {exc.colno}: {exc.msg}.",
                    "path": str(path),
                }
            ]
        ) from exc

    if not isinstance(data, dict):
        raise CompareBlockedError(
            [
                {
                    "code": "invalid_json_shape",
                    "message": "Variant bundle must be a JSON object.",
                    "path": str(path),
                }
            ]
        )
    return data


def _validate_bundle(bundle: dict[str, Any], path: str) -> None:
    reasons: list[dict[str, str]] = []
    required_fields = (
        "artifactType",
        "bundleId",
        "briefId",
        "variants",
        "sourceBriefHash",
        "sourceTextHash",
        "configSetHash",
        "gateContext",
        "gateContextHash",
    )
    for field_name in required_fields:
        if field_name not in bundle:
            reasons.append(
                {
                    "code": "missing_required_field",
                    "message": f"Missing required field: {field_name}.",
                    "path": f"{path}.{field_name}",
                }
            )

    if bundle.get("artifactType") != "copy_variant_bundle":
        reasons.append(
            {
                "code": "invalid_artifact_type",
                "message": "Compare input must be a copy_variant_bundle.",
                "path": f"{path}.artifactType",
            }
        )

    variants = bundle.get("variants")
    if not isinstance(variants, list) or not variants:
        reasons.append(
            {
                "code": "invalid_field",
                "message": "variants must be a non-empty array.",
                "path": f"{path}.variants",
            }
        )
    elif isinstance(variants, list):
        seen_ids: set[str] = set()
        for index, variant in enumerate(variants):
            item_path = f"{path}.variants[{index}]"
            if not isinstance(variant, dict):
                reasons.append(
                    {
                        "code": "invalid_json_shape",
                        "message": "Variant records must be objects.",
                        "path": item_path,
                    }
                )
                continue
            for field_name in (
                "variantId",
                "strategyId",
                "copy",
                "claimGateStatus",
                "contentGateStatus",
                "recommendationState",
            ):
                if not isinstance(variant.get(field_name), str) or not variant[field_name].strip():
                    reasons.append(
                        {
                            "code": "missing_required_field",
                            "message": f"Variant must include non-empty {field_name}.",
                            "path": f"{item_path}.{field_name}",
                        }
                    )
            variant_id = variant.get("variantId")
            if isinstance(variant_id, str):
                if variant_id in seen_ids:
                    reasons.append(
                        {
                            "code": "duplicate_id",
                            "message": f"Duplicate variant id: {variant_id}.",
                            "path": f"{item_path}.variantId",
                        }
                    )
                seen_ids.add(variant_id)

    _validate_gate_context(bundle, path, reasons)

    if reasons:
        raise CompareBlockedError(reasons)


def _validate_gate_context(
    bundle: dict[str, Any],
    path: str,
    reasons: list[dict[str, str]],
) -> None:
    context = bundle.get("gateContext")
    context_path = f"{path}.gateContext"
    if not isinstance(context, dict):
        reasons.append(
            {
                "code": "invalid_gate_context",
                "message": "gateContext must be an object produced from the source brief and analysis.",
                "path": context_path,
            }
        )
        return

    source_text = context.get("sourceText")
    if not isinstance(source_text, str) or not source_text.strip():
        reasons.append(
            {
                "code": "invalid_gate_context",
                "message": "gateContext.sourceText must be a non-empty string.",
                "path": f"{context_path}.sourceText",
            }
        )
    else:
        expected_source_hash = f"sha256:{_hash_text(source_text)}"
        if context.get("sourceTextHash") != expected_source_hash:
            reasons.append(
                {
                    "code": "gate_context_source_hash_mismatch",
                    "message": "gateContext.sourceText does not match its sourceTextHash.",
                    "path": f"{context_path}.sourceTextHash",
                }
            )
        if bundle.get("sourceTextHash") != expected_source_hash:
            reasons.append(
                {
                    "code": "bundle_source_hash_mismatch",
                    "message": "gateContext.sourceText does not match the bundle sourceTextHash.",
                    "path": f"{path}.sourceTextHash",
                }
            )

    if context.get("sourceBriefHash") != bundle.get("sourceBriefHash"):
        reasons.append(
            {
                "code": "gate_context_brief_hash_mismatch",
                "message": "gateContext.sourceBriefHash does not match the bundle sourceBriefHash.",
                "path": f"{context_path}.sourceBriefHash",
            }
        )
    if context.get("sourceAnalysisReportId") != bundle.get("sourceAnalysisReportId"):
        reasons.append(
            {
                "code": "gate_context_analysis_mismatch",
                "message": "gateContext.sourceAnalysisReportId does not match the bundle analysis report.",
                "path": f"{context_path}.sourceAnalysisReportId",
            }
        )

    for field_name in ("requiredTerms", "prohibitedTerms"):
        terms = context.get(field_name)
        if not isinstance(terms, list) or any(not isinstance(term, str) for term in terms):
            reasons.append(
                {
                    "code": "invalid_gate_context",
                    "message": f"gateContext.{field_name} must be an array of strings.",
                    "path": f"{context_path}.{field_name}",
                }
            )

    claims = context.get("analysisClaims")
    if not isinstance(claims, list):
        reasons.append(
            {
                "code": "invalid_gate_context",
                "message": "gateContext.analysisClaims must be an array.",
                "path": f"{context_path}.analysisClaims",
            }
        )
    else:
        for index, claim in enumerate(claims):
            if (
                not isinstance(claim, dict)
                or not isinstance(claim.get("claimId"), str)
                or not isinstance(claim.get("supportStatus"), str)
            ):
                reasons.append(
                    {
                        "code": "invalid_gate_context",
                        "message": "Each analysis claim must include string claimId and supportStatus fields.",
                        "path": f"{context_path}.analysisClaims[{index}]",
                    }
                )

    context_hash = bundle.get("gateContextHash")
    if not isinstance(context_hash, str):
        reasons.append(
            {
                "code": "invalid_gate_context_hash",
                "message": "gateContextHash must be a string.",
                "path": f"{path}.gateContextHash",
            }
        )
    elif context_hash != hash_gate_context(context):
        reasons.append(
            {
                "code": "gate_context_hash_mismatch",
                "message": "gateContext does not match gateContextHash.",
                "path": f"{path}.gateContextHash",
            }
        )


def _evaluate_variant(variant: dict[str, Any], bundle: dict[str, Any]) -> dict[str, Any]:
    copy = variant["copy"]
    gate_context = bundle["gateContext"]
    gate_evaluation = evaluate_copy_gates(
        copy,
        source_text=gate_context["sourceText"],
        required_terms=gate_context["requiredTerms"],
        prohibited_terms=gate_context["prohibitedTerms"],
    )
    has_unverified_claims = any(
        claim.get("supportStatus") != "supported" for claim in gate_context["analysisClaims"]
    )
    requires_proof = (
        has_unverified_claims
        or gate_evaluation["claimGateStatus"] != "passed"
        or gate_evaluation["contentGateStatus"] != "passed"
    )
    evaluated_variant = {
        **variant,
        **gate_evaluation,
        "requiresProofBeforePublishing": requires_proof,
    }
    words = _words(copy)
    sentences = _sentences(copy)
    max_sentence_words = max((len(_words(sentence)) for sentence in sentences), default=0)
    has_cta = _has_cta(copy)
    has_proof_boundary = _has_proof_boundary(copy)
    has_pressure = _has_pressure(copy)
    claim_gate_passed = gate_evaluation["claimGateStatus"] == "passed"
    content_gate_passed = gate_evaluation["contentGateStatus"] == "passed"
    is_document = bundle.get("documentArchetype") in {
        "internal_executive_digest",
        "internal_operational_brief",
    }
    requires_action = not (
        bundle.get("communicationIntent") == "inform" or bundle.get("decisionRequired") is False
    )

    dimension_scores = {
        "clarity": _score_clarity(len(words), len(sentences), has_cta, requires_action, is_document),
        "cognitive_load": _score_cognitive_load(max_sentence_words, len(words), is_document),
        "proof_safety": _score_proof_safety(has_proof_boundary, evaluated_variant),
        "action_clarity": 5 if has_cta or not requires_action else 2,
        "ethical_risk": _score_ethical_risk(has_pressure, claim_gate_passed),
        "source_fidelity": 5 if content_gate_passed and gate_evaluation["sourceCoverage"] == 1.0 else 0,
        "numeric_fidelity": 5 if gate_evaluation["numericFidelity"] == 1.0 else 0,
        "intent_fit": _score_intent_fit(copy, requires_action),
    }
    total_score = sum(dimension_scores.values())

    return {
        "variantId": variant["variantId"],
        "strategyId": variant["strategyId"],
        "totalScore": total_score,
        "dimensionScores": dimension_scores,
        "wordCount": len(words),
        "sentenceCount": len(sentences),
        "maxSentenceWords": max_sentence_words,
        "claimGateStatus": gate_evaluation["claimGateStatus"],
        "claimGateReasons": gate_evaluation["claimGateReasons"],
        "contentGateStatus": gate_evaluation["contentGateStatus"],
        "contentGateReasons": gate_evaluation["contentGateReasons"],
        "sourceCoverage": gate_evaluation["sourceCoverage"],
        "numericFidelity": gate_evaluation["numericFidelity"],
        "missingNumericTokens": gate_evaluation["missingNumericTokens"],
        "introducedNumericTokens": gate_evaluation["introducedNumericTokens"],
        "requiredTermCoverage": gate_evaluation["requiredTermCoverage"],
        "missingRequiredTerms": gate_evaluation["missingRequiredTerms"],
        "presentProhibitedTerms": gate_evaluation["presentProhibitedTerms"],
        "sourceSubjectPreserved": gate_evaluation["sourceSubjectPreserved"],
        "serializedGateMetadataMatched": all(
            variant.get(field_name) == gate_evaluation[field_name]
            for field_name in (
                "claimGateStatus",
                "claimGateReasons",
                "contentGateStatus",
                "contentGateReasons",
                "sourceCoverage",
                "numericFidelity",
                "missingNumericTokens",
                "introducedNumericTokens",
                "requiredTermCoverage",
                "missingRequiredTerms",
                "presentProhibitedTerms",
                "sourceSubjectPreserved",
            )
        ),
        "gateEvaluationSource": "recomputed_from_current_copy_and_bound_source_context",
        "recommendationState": _recommendation_state(evaluated_variant, is_document),
        "evidenceBasis": "heuristic_inference",
        "requiresProofBeforePublishing": requires_proof,
        "strengths": _strengths(
            has_cta,
            has_proof_boundary,
            max_sentence_words,
            has_pressure,
            content_gate_passed,
            requires_action,
        ),
        "tradeoffs": _tradeoffs(
            has_cta,
            has_proof_boundary,
            max_sentence_words,
            evaluated_variant,
            requires_action,
        ),
        "recommendedValidation": (
            "Have a senior internal reader identify the period, scale, implication, owner, and next action without coaching."
            if is_document
            else "Test whether target users can accurately explain the offer, proof limit, and next step."
        ),
    }


def _rank_evaluations(evaluations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    sorted_items = sorted(
        evaluations,
        key=lambda item: (
            item["claimGateStatus"] != "passed",
            item["contentGateStatus"] != "passed",
            -item["totalScore"],
            item["wordCount"],
            item["variantId"],
        ),
    )
    for index, item in enumerate(sorted_items, start=1):
        item["rank"] = index
        item["recommendedForTesting"] = _gates_pass(item) and index <= 2
    return sorted_items


def _claim_gate_summary(evaluations: list[dict[str, Any]]) -> dict[str, Any]:
    blocked = [item["variantId"] for item in evaluations if item["claimGateStatus"] != "passed"]
    return {
        "status": "blocked" if blocked else "passed",
        "blockedVariantIds": blocked,
        "passedVariantIds": [
            item["variantId"] for item in evaluations if item["claimGateStatus"] == "passed"
        ],
        "gateEvaluationSource": "recomputed_from_current_copy_and_bound_source_context",
        "marketEvidenceCreated": False,
    }


def _content_gate_summary(evaluations: list[dict[str, Any]]) -> dict[str, Any]:
    blocked = [item["variantId"] for item in evaluations if item["contentGateStatus"] != "passed"]
    return {
        "status": "blocked" if blocked else "passed",
        "blockedVariantIds": blocked,
        "passedVariantIds": [
            item["variantId"] for item in evaluations if item["contentGateStatus"] == "passed"
        ],
        "numericFidelityRequired": True,
        "sourceCoverageRequired": 1.0,
        "gateEvaluationSource": "recomputed_from_current_copy_and_bound_source_context",
        "marketEvidenceCreated": False,
    }


def _summary(ranked: list[dict[str, Any]], recommended: list[str]) -> str:
    if not recommended:
        return "No variant is suitable for testing because claim gates or input checks blocked all candidates."
    top = ranked[0]
    return (
        f"{top['variantId']} ranked highest on deterministic clarity, proof-safety, source-fidelity, intent-fit, and ethical-risk checks. "
        "Treat this as a test candidate, not evidence of user preference."
    )


def _score_clarity(
    word_count: int,
    sentence_count: int,
    has_cta: bool,
    requires_action: bool,
    is_document: bool,
) -> int:
    score = 5
    if not is_document and word_count > 55:
        score -= 2
    elif not is_document and word_count > 40:
        score -= 1
    if not is_document and sentence_count > 3:
        score -= 1
    if requires_action and not has_cta:
        score -= 1
    return max(0, score)


def _score_cognitive_load(max_sentence_words: int, word_count: int, is_document: bool) -> int:
    score = 5
    if max_sentence_words > 32:
        score -= 3
    elif max_sentence_words > 24:
        score -= 2
    elif max_sentence_words > 18:
        score -= 1
    if word_count > 65 and not is_document:
        score -= 1
    return max(0, score)


def _score_proof_safety(has_proof_boundary: bool, evaluated_variant: dict[str, Any]) -> int:
    if evaluated_variant["claimGateStatus"] != "passed":
        return 0
    if has_proof_boundary and evaluated_variant.get("requiresProofBeforePublishing"):
        return 5
    if has_proof_boundary:
        return 4
    if evaluated_variant.get("requiresProofBeforePublishing"):
        return 3
    return 4


def _score_ethical_risk(has_pressure: bool, claim_gate_passed: bool) -> int:
    if not claim_gate_passed:
        return 0
    if has_pressure:
        return 2
    return 5


def _recommendation_state(evaluated_variant: dict[str, Any], is_document: bool) -> str:
    if (
        evaluated_variant["claimGateStatus"] != "passed"
        or evaluated_variant["contentGateStatus"] != "passed"
    ):
        return "blocked_unsupported"
    if is_document:
        return "candidate_for_human_review"
    return "hypothesis_to_test"


def _strengths(
    has_cta: bool,
    has_proof_boundary: bool,
    max_sentence_words: int,
    has_pressure: bool,
    content_gate_passed: bool,
    requires_action: bool,
) -> list[str]:
    strengths = []
    if has_cta and requires_action:
        strengths.append("Includes an explicit next step.")
    if not requires_action:
        strengths.append("Fits an informational document without forcing an approval or response.")
    if has_proof_boundary:
        strengths.append("Keeps the proof or validation boundary visible.")
    if max_sentence_words <= 24:
        strengths.append("Keeps sentence length within the Phase 0 readability target.")
    if not has_pressure:
        strengths.append("Avoids obvious urgency, shame, or pressure language.")
    if content_gate_passed:
        strengths.append("Preserves required source terms, sentences, and numeric tokens.")
    return strengths


def _tradeoffs(
    has_cta: bool,
    has_proof_boundary: bool,
    max_sentence_words: int,
    evaluated_variant: dict[str, Any],
    requires_action: bool,
) -> list[str]:
    tradeoffs = list(evaluated_variant.get("tradeoffs") or [])
    if requires_action and not has_cta:
        tradeoffs.append("The next action is less explicit.")
    if not has_proof_boundary:
        tradeoffs.append("The evidence boundary is less visible.")
    if max_sentence_words > 24:
        tradeoffs.append("At least one sentence may be too dense for fast scanning.")
    if evaluated_variant["claimGateStatus"] != "passed":
        tradeoffs.append("Claim gate did not pass, so this variant should not be tested as written.")
    if evaluated_variant["contentGateStatus"] != "passed":
        tradeoffs.append("Content gate did not pass, so source fidelity is not acceptable.")
    return tradeoffs


def _score_intent_fit(copy: str, requires_action: bool) -> int:
    has_explicit_request = bool(
        re.search(r"\b(?:request|approve|decide|authorize|book|schedule|start a trial)\b", copy.lower())
    )
    if requires_action:
        return 5 if _has_cta(copy) else 2
    return 3 if has_explicit_request else 5


def _gates_pass(item: dict[str, Any]) -> bool:
    return item.get("claimGateStatus") == "passed" and item.get("contentGateStatus") == "passed"


def _has_cta(copy: str) -> bool:
    lower = copy.lower()
    return any(re.search(pattern, lower) for pattern in CTA_PATTERNS)


def _has_proof_boundary(copy: str) -> bool:
    lower = copy.lower()
    return any(term in lower for term in PROOF_BOUNDARY_TERMS)


def _has_pressure(copy: str) -> bool:
    lower = copy.lower()
    return any(term in lower for term in PRESSURE_TERMS)


def _sentences(text: str) -> list[str]:
    return [part.strip() for part in re.split(r"(?<=[.!?])\s+", text) if part.strip()]


def _words(text: str) -> list[str]:
    return re.findall(r"[A-Za-z0-9]+(?:[-'][A-Za-z0-9]+)?", text)


def _hash_file(path: Path) -> str:
    return f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"


def _hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()

"""Motivation, friction, objection, and trust-gap classification."""

from __future__ import annotations

from typing import Any


MOTIVATION_SCORE_ANCHORS: dict[str, str] = {
    "0": "The reader has no clear reason to continue and the message may be blocked by risk or unsupported claims.",
    "1": "The message creates more hesitation than motivation.",
    "2": "The message has a plausible reason to continue but major friction remains.",
    "3": "The message is usable but needs clearer value, proof, or next step.",
    "4": "The message gives a clear reason to continue with manageable friction.",
    "5": "The message is clear, credible, low-pressure, and easy to act on as a test candidate.",
}


FRICTION_CATEGORIES: dict[str, dict[str, str]] = {
    "unclear_value": {
        "label": "Unclear Value",
        "defaultObjection": "I understand the words, but I do not know why this matters to me.",
    },
    "unclear_category": {
        "label": "Unclear Category",
        "defaultObjection": "I cannot quickly tell what this thing is.",
    },
    "unclear_time_relevance": {
        "label": "Unclear Time Relevance",
        "defaultObjection": "I do not know why this needs attention now.",
    },
    "no_proof": {
        "label": "No Proof",
        "defaultObjection": "I would need evidence before I believe this claim.",
    },
    "high_perceived_effort": {
        "label": "High Perceived Effort",
        "defaultObjection": "This sounds like it may take too much work to understand or use.",
    },
    "high_perceived_risk": {
        "label": "High Perceived Risk",
        "defaultObjection": "This may carry more risk than the copy acknowledges.",
    },
    "wrong_audience": {
        "label": "Wrong Audience",
        "defaultObjection": "I am not sure this is for someone like me.",
    },
    "premature_cta": {
        "label": "Premature CTA",
        "defaultObjection": "The copy asks me to act before I have enough clarity or proof.",
    },
    "jargon_barrier": {
        "label": "Jargon Barrier",
        "defaultObjection": "The wording feels too insider-heavy for a first pass.",
    },
    "missing_fast_path": {
        "label": "Missing Fast Path",
        "defaultObjection": "I cannot quickly find the part that helps me act.",
    },
    "expert_agency_risk": {
        "label": "Expert Agency Risk",
        "defaultObjection": "This feels like it is talking down to me or taking control away from me.",
    },
    "coercive_momentum_risk": {
        "label": "Coercive Momentum Risk",
        "defaultObjection": "This sounds like it wants dependency instead of helping me complete a task.",
    },
}


def build_motivation_friction_report(
    brief: dict[str, Any],
    findings: list[dict[str, Any]],
    claims: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build the Phase 5 motivation/friction report from deterministic analysis artifacts."""

    friction_items = _friction_items(brief, findings, claims)
    objection_map = [_objection_for(index + 1, item) for index, item in enumerate(friction_items)]
    trust_gaps = _trust_gaps(findings, claims)
    motivation_score = _motivation_score(friction_items, trust_gaps)

    return {
        "artifactType": "motivation_friction_report",
        "motivationScore": {
            "score": motivation_score,
            "scoreScale": "0_to_5",
            "scoreReason": _motivation_reason(motivation_score, friction_items, trust_gaps),
            "calibrationAnchor": MOTIVATION_SCORE_ANCHORS[str(motivation_score)],
            "evidenceBasis": "heuristic_inference",
        },
        "frictionCategories": friction_items,
        "objectionMap": objection_map,
        "trustGapReport": {
            "state": "trust_gap_detected" if trust_gaps else "no_material_trust_gap_detected",
            "separatedFromClarityGap": True,
            "gaps": trust_gaps,
            "limitation": "Trust gaps identify proof and risk issues separately from clarity issues; they are not evidence of user distrust.",
        },
        "limitations": [
            "Motivation scoring is heuristic and must not be treated as measured motivation.",
            "Friction categories are inferred from text properties, claims, and proof status.",
            "Objections are planning prompts for user research, not real user statements.",
        ],
    }


def _friction_items(
    brief: dict[str, Any],
    findings: list[dict[str, Any]],
    claims: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []

    if not _target_audience_is_specific(brief):
        items.append(
            _friction(
                "wrong_audience",
                "medium",
                "The target audience may be too broad for readers to self-identify quickly.",
                [],
                [],
                "Name the specific role, situation, or trigger that makes the message relevant.",
                "Ask target readers whether they know the message is meant for them.",
            )
        )

    for finding in findings:
        issue = finding["issue"].lower()
        if "category" in issue:
            items.append(
                _friction_from_finding(
                    "unclear_category",
                    finding,
                    "Add a concrete category label before describing value.",
                    "Ask readers to name what the product is after one pass.",
                )
            )
        elif "next action" in issue:
            items.append(
                _friction_from_finding(
                    "premature_cta",
                    finding,
                    "Make the next step explicit after the value and proof boundary are clear.",
                    "Ask readers what action they think the message requests.",
                )
            )
        elif "jargon" in issue:
            items.append(
                _friction_from_finding(
                    "jargon_barrier",
                    finding,
                    "Replace generic jargon with concrete nouns and actions.",
                    "Ask target readers which terms require explanation.",
                )
            )
        elif "long enough" in issue or "parsing" in issue:
            items.append(
                _friction_from_finding(
                    "high_perceived_effort",
                    finding,
                    "Break dense sentences into one idea per sentence.",
                    "Ask readers to paraphrase the message without rereading.",
                )
            )
        elif "fast path" in issue:
            items.append(
                _friction_from_finding(
                    "missing_fast_path",
                    finding,
                    "Put the first useful action, answer, or checklist before background explanation.",
                    "Ask readers to find the answer for a real task and time how long it takes.",
                )
            )
        elif "learning tax" in issue:
            items.append(
                _friction_from_finding(
                    "high_perceived_effort",
                    finding,
                    "Move framework learning after the task path and minimum viable action.",
                    "Ask readers where they first get enough information to act.",
                )
            )
        elif "abstract" in issue:
            items.append(
                _friction_from_finding(
                    "unclear_value",
                    finding,
                    "Replace abstract value language with a concrete outcome and use case.",
                    "Ask readers why the message matters in their own words.",
                )
            )
        elif "proof" in issue or "unverified" in issue:
            items.append(
                _friction_from_finding(
                    "no_proof",
                    finding,
                    "Attach method, sample, source id, and limitations before upgrading confidence.",
                    "Ask readers what proof they need before trusting the claim.",
                    claim_ids=finding.get("claimIds") or [],
                )
            )
        elif "evidence boundary" in issue:
            items.append(
                _friction_from_finding(
                    "no_proof",
                    finding,
                    "Separate sourced facts, assumptions, heuristic guidance, and validation status.",
                    "Ask technical reviewers which claims are proven, assumed, or still need validation.",
                    claim_ids=finding.get("claimIds") or [],
                )
            )
        elif "expert agency" in issue or "status-sensitive" in issue:
            items.append(
                _friction_from_finding(
                    "expert_agency_risk",
                    finding,
                    "Use respectful precision, options, and tradeoffs instead of remedial framing.",
                    "Ask specialists whether the document feels respectful and useful for their role.",
                )
            )
        elif "dependency or addiction" in issue or "addictive" in issue or "addicting" in issue:
            items.append(
                _friction_from_finding(
                    "coercive_momentum_risk",
                    finding,
                    "Reframe reading momentum as skim-to-answer speed, task completion, and voluntary reuse.",
                    "Measure whether readers reuse the document for real tasks without pressure or dependency framing.",
                )
            )
        elif "sensitive" in issue or "restricted" in issue or "risk" in issue:
            items.append(
                _friction_from_finding(
                    "high_perceived_risk",
                    finding,
                    "Make limits, required review, and support paths explicit.",
                    "Have the exact sensitive-domain claim reviewed by a qualified expert.",
                    claim_ids=finding.get("claimIds") or [],
                )
            )

    unsupported_claim_ids = [
        claim["claimId"] for claim in claims if claim["supportStatus"] in {"unsupported", "support_candidate", "blocked"}
    ]
    if unsupported_claim_ids and not any(item["categoryId"] == "no_proof" for item in items):
        items.append(
            _friction(
                "no_proof",
                "medium",
                "One or more claims still need stronger proof before publishing.",
                [],
                unsupported_claim_ids,
                "Create evidence records or caveat the claims as hypotheses.",
                "Ask readers what proof would make the claim believable.",
            )
        )

    return _dedupe_friction(items)


def _trust_gaps(findings: list[dict[str, Any]], claims: list[dict[str, Any]]) -> list[dict[str, Any]]:
    gaps: list[dict[str, Any]] = []
    for claim in claims:
        if claim["supportStatus"] in {"unsupported", "support_candidate", "blocked"}:
            gaps.append(
                {
                    "gapId": f"trust-gap-{len(gaps) + 1:03d}",
                    "claimIds": [claim["claimId"]],
                    "gapType": "proof_gap",
                    "evidenceBasis": claim["evidenceBasis"],
                    "summary": "Claim needs stronger proof before it can support publish-ready copy.",
                    "recommendedFix": "Record method, sample, source id, limitations, or remove the claim.",
                    "recommendedValidation": "Ask target readers what proof would make this claim believable.",
                }
            )

    for finding in findings:
        if finding["dimensionId"] == "ethical_risk":
            gaps.append(
                {
                    "gapId": f"trust-gap-{len(gaps) + 1:03d}",
                    "claimIds": finding.get("claimIds") or [],
                    "gapType": "risk_gap",
                    "evidenceBasis": finding["evidenceBasis"],
                    "summary": finding["issue"],
                    "recommendedFix": finding["recommendedFix"],
                    "recommendedValidation": finding["recommendedValidation"],
                }
            )
    return gaps


def _motivation_score(friction_items: list[dict[str, Any]], trust_gaps: list[dict[str, Any]]) -> int:
    score = 5
    severity_penalty = {"low": 1, "medium": 2, "high": 3, "blocked": 5}
    if friction_items:
        score -= max(severity_penalty[item["severity"]] for item in friction_items)
    if trust_gaps:
        score -= 1
    return max(0, score)


def _motivation_reason(
    score: int,
    friction_items: list[dict[str, Any]],
    trust_gaps: list[dict[str, Any]],
) -> str:
    if not friction_items and not trust_gaps:
        return "No material deterministic friction or trust gaps were detected; user validation is still required."
    categories = ", ".join(item["categoryId"] for item in friction_items) or "none"
    return f"Motivation scored {score}/5 because friction categories were detected: {categories}; trust gaps: {len(trust_gaps)}."


def _friction_from_finding(
    category_id: str,
    finding: dict[str, Any],
    recommended_fix: str,
    recommended_validation: str,
    *,
    claim_ids: list[str] | None = None,
) -> dict[str, Any]:
    return _friction(
        category_id,
        finding["severity"],
        finding["issue"],
        [finding["findingId"]],
        claim_ids or finding.get("claimIds") or [],
        recommended_fix,
        recommended_validation,
    )


def _friction(
    category_id: str,
    severity: str,
    summary: str,
    finding_ids: list[str],
    claim_ids: list[str],
    recommended_fix: str,
    recommended_validation: str,
) -> dict[str, Any]:
    category = FRICTION_CATEGORIES[category_id]
    return {
        "categoryId": category_id,
        "label": category["label"],
        "severity": severity,
        "summary": summary,
        "sourceFindingIds": finding_ids,
        "claimIds": claim_ids,
        "evidenceBasis": "heuristic_inference",
        "recommendedFix": recommended_fix,
        "recommendedValidation": recommended_validation,
    }


def _objection_for(index: int, friction_item: dict[str, Any]) -> dict[str, Any]:
    category = FRICTION_CATEGORIES[friction_item["categoryId"]]
    return {
        "objectionId": f"objection-{index:03d}",
        "categoryId": friction_item["categoryId"],
        "objection": category["defaultObjection"],
        "sourceFindingIds": friction_item["sourceFindingIds"],
        "claimIds": friction_item["claimIds"],
        "responseStrategy": friction_item["recommendedFix"],
        "recommendedValidation": friction_item["recommendedValidation"],
        "evidenceBasis": "heuristic_inference",
    }


def _dedupe_friction(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    severity_order = {"low": 0, "medium": 1, "high": 2, "blocked": 3}
    for item in items:
        existing = merged.get(item["categoryId"])
        if existing is None:
            merged[item["categoryId"]] = dict(item)
            continue
        if severity_order[item["severity"]] > severity_order[existing["severity"]]:
            existing["severity"] = item["severity"]
            existing["summary"] = item["summary"]
        existing["sourceFindingIds"] = sorted(set(existing["sourceFindingIds"]) | set(item["sourceFindingIds"]))
        existing["claimIds"] = sorted(set(existing["claimIds"]) | set(item["claimIds"]))
    return list(merged.values())


def _target_audience_is_specific(brief: dict[str, Any]) -> bool:
    audience = brief["targetAudience"].lower()
    return any(word in audience for word in ("lead", "manager", "team", "product", "marketing", "sales", "technical"))

"""Research-plan generation from Mindfront analysis uncertainty."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from json import JSONDecodeError
from pathlib import Path
from typing import Any

from . import __version__


class ResearchPlanBlockedError(Exception):
    """Raised when a research plan cannot be generated."""

    def __init__(self, reasons: list[dict[str, str]]):
        self.reasons = reasons
        super().__init__("Research plan blocked by input errors.")


DEFAULT_SENSITIVE_DATA_AVOIDANCE = (
    "Do not collect personal health, financial, legal, protected-class, employment eligibility, "
    "housing, insurance, education, crisis, or minor-related details. If a participant discloses "
    "sensitive information, stop the test, do not record the details, and mark the session for "
    "exclusion or expert review."
)

DEFAULT_CONSENT_SCRIPT = (
    "We are testing whether this message is understandable, credible, and easy to act on. "
    "This is not a test of you. You can skip any question or stop at any time."
)

DEFAULT_STOP_CONDITIONS = [
    "participant requests to stop",
    "participant distress",
    "sensitive personal disclosure",
    "participant appears to be a minor or vulnerable participant",
]

METHOD_BY_DIMENSION = {
    "clarity": "comprehension_test",
    "cognitive_load": "comprehension_test",
    "concreteness": "comprehension_test",
    "trust_proof": "user_interview",
    "ethical_risk": "user_interview",
}


def build_research_plan(analysis_path: str | Path) -> dict[str, Any]:
    """Build a runnable research handoff from a message analysis report."""

    path = Path(analysis_path)
    analysis = _load_analysis_report(path)
    findings = analysis["findings"]
    claims = analysis["claims"]
    major_findings = _major_findings(findings)
    questions = _build_questions(analysis, major_findings, claims)
    coverage = _coverage(major_findings, questions)
    generated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")

    plan = {
        "artifactType": "research_plan",
        "researchPlanId": f"research-plan-{_hash_text(analysis['reportId'] + analysis['sourceTextHash'])[:12]}",
        "sourceAnalysisReportId": analysis["reportId"],
        "briefId": analysis.get("briefId", "unknown"),
        "summary": _summary(questions, major_findings),
        "evidenceBasis": "heuristic_inference",
        "marketEvidenceCreated": False,
        "notMarketEvidence": True,
        "recommendedSequence": [
            "Run comprehension tests before preference, motivation, or A/B testing.",
            "Resolve blocked ethical or unsupported-claim findings before using any copy externally.",
            "Use survey or A/B results only within their exact sample, channel, and measurement limits.",
        ],
        "questions": questions,
        "uncertaintyCoverage": coverage,
        "motivationFrictionCoverage": _motivation_friction_coverage(analysis, questions),
        "trustGapCoverage": _trust_gap_coverage(analysis, questions),
        "interviewScript": _build_interview_script(questions),
        "surveyQuestions": _build_survey_questions(questions),
        "usabilityTasks": _build_usability_tasks(questions),
        "abHypotheses": _build_ab_hypotheses(analysis, questions),
        "decisionSummary": _decision_summary(questions),
        "limitations": [
            "This plan turns heuristic findings into validation work; it does not create user evidence.",
            "Small-sample comprehension, interview, and usability results are not statistical market proof.",
            "A/B hypotheses require adequate sample size, live-channel controls, and claim gates before use.",
            "Sensitive or regulated contexts still require appropriate expert review.",
        ],
        "sourceAnalysisHash": _hash_file(path),
        "sourceBriefHash": analysis["sourceBriefHash"],
        "sourceTextHash": analysis["sourceTextHash"],
        "configSetHash": analysis["configSetHash"],
        "templateHash": "sha256:not-used",
        "outputHash": "sha256:pending-until-written",
        "generatedAt": generated_at,
        "toolVersion": __version__,
    }
    return plan


def write_research_plan(plan: dict[str, Any], output_path: str | Path) -> list[Path]:
    """Write a research plan as JSON and, for directory outputs, Markdown."""

    destination = Path(output_path)
    payload = finalize_research_plan(plan)
    if destination.suffix.lower() == ".json":
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return [destination]

    if destination.suffix.lower() == ".md":
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(render_research_plan_markdown(payload), encoding="utf-8")
        return [destination]

    destination.mkdir(parents=True, exist_ok=True)
    json_path = destination / "research-plan.json"
    markdown_path = destination / "research-plan.md"
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    markdown_path.write_text(render_research_plan_markdown(payload), encoding="utf-8")
    return [json_path, markdown_path]


def finalize_research_plan(plan: dict[str, Any]) -> dict[str, Any]:
    """Return a research plan with a stable emitted-payload hash."""

    payload = dict(plan)
    payload["outputHash"] = "sha256:pending-until-written"
    provisional = json.dumps(payload, indent=2, sort_keys=True)
    payload["outputHash"] = f"sha256:{_hash_text(provisional)}"
    return payload


def render_research_plan_markdown(plan: dict[str, Any]) -> str:
    """Render the research plan into a human-readable handoff."""

    lines = [
        "# Mindfront Research Plan",
        "",
        f"Source analysis: `{plan['sourceAnalysisReportId']}`",
        f"Evidence basis: `{plan['evidenceBasis']}`",
        f"Market evidence created: `{str(plan['marketEvidenceCreated']).lower()}`",
        "",
        "## Sequence",
        "",
    ]
    lines.extend(f"- {item}" for item in plan["recommendedSequence"])
    lines.extend(["", "## Research Questions", ""])
    for question in plan["questions"]:
        lines.extend(
            [
                f"### {question['questionId']}",
                "",
                f"- Uncertainty: {question['uncertainty']}",
                f"- Method: `{question['method']}`",
                f"- Evidence target: `{question['evidenceGradeTarget']}`",
                f"- Sample: {question['sampleSize']}. Source: {question['sampleSource']}",
                f"- Decision threshold: {question['decisionThreshold']}",
                f"- Related findings: {', '.join(question['relatedFindingIds']) or 'none'}",
                f"- Related claims: {', '.join(question['relatedClaimIds']) or 'none'}",
                "",
            ]
        )

    lines.extend(["## Interview Script", ""])
    for item in plan["interviewScript"]["items"]:
        lines.extend(
            [
                f"- `{item['scriptItemId']}` for `{item['questionId']}`: {item['prompt']}",
                f"  Follow-up: {item['followUp']}",
            ]
        )

    lines.extend(["", "## Survey Questions", ""])
    for item in plan["surveyQuestions"]:
        lines.append(f"- `{item['surveyItemId']}`: {item['questionText']}")

    lines.extend(["", "## Usability Tasks", ""])
    for item in plan["usabilityTasks"]:
        lines.append(f"- `{item['taskId']}`: {item['taskPrompt']} Threshold: {item['successThreshold']}")

    lines.extend(["", "## A/B Hypotheses", ""])
    for item in plan["abHypotheses"]:
        lines.append(f"- `{item['hypothesisId']}`: {item['hypothesis']}")
        lines.append(f"  Caveat: {item['sampleSizeCaveat']}")

    lines.extend(["", "## Limitations", ""])
    lines.extend(f"- {item}" for item in plan["limitations"])
    lines.append("")
    return "\n".join(lines)


def _load_analysis_report(path: Path) -> dict[str, Any]:
    data = _load_json_file(path, "analysis")
    if data.get("artifactType") != "message_analysis_report":
        raise ResearchPlanBlockedError(
            [
                {
                    "code": "invalid_artifact_type",
                    "message": "Research plan requires a message_analysis_report input.",
                    "path": f"{path}.artifactType",
                }
            ]
        )

    required = ("reportId", "findings", "claims", "sourceBriefHash", "sourceTextHash", "configSetHash")
    reasons = [
        {
            "code": "missing_required_field",
            "message": f"Missing required field: {field_name}.",
            "path": f"{path}.{field_name}",
        }
        for field_name in required
        if field_name not in data
    ]
    if not isinstance(data.get("findings"), list):
        reasons.append(
            {
                "code": "invalid_field",
                "message": "findings must be an array.",
                "path": f"{path}.findings",
            }
        )
    if not isinstance(data.get("claims"), list):
        reasons.append(
            {
                "code": "invalid_field",
                "message": "claims must be an array.",
                "path": f"{path}.claims",
            }
        )
    if reasons:
        raise ResearchPlanBlockedError(reasons)
    return data


def _load_json_file(path: Path, label: str) -> dict[str, Any]:
    if not path.exists():
        raise ResearchPlanBlockedError(
            [{"code": f"missing_{label}_file", "message": f"Missing {label} file.", "path": str(path)}]
        )
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except JSONDecodeError as exc:
        raise ResearchPlanBlockedError(
            [
                {
                    "code": "invalid_json",
                    "message": f"Invalid JSON at line {exc.lineno}, column {exc.colno}: {exc.msg}.",
                    "path": str(path),
                }
            ]
        ) from exc
    if not isinstance(data, dict):
        raise ResearchPlanBlockedError(
            [{"code": "invalid_json_shape", "message": f"{label} file must contain a JSON object.", "path": str(path)}]
        )
    return data


def _major_findings(findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    major = [
        finding
        for finding in findings
        if finding.get("severity") in {"medium", "high", "blocked"}
        and isinstance(finding.get("findingId"), str)
    ]
    return major


def _build_questions(
    analysis: dict[str, Any],
    major_findings: list[dict[str, Any]],
    claims: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    audience = _target_audience(analysis)
    source_text_hash = analysis["sourceTextHash"]
    source_brief_id = analysis.get("briefId", "unknown")
    questions: list[dict[str, Any]] = []

    if not major_findings:
        questions.append(
            _question(
                index=1,
                analysis=analysis,
                method="comprehension_test",
                uncertainty="Whether target users can explain the offer, proof boundary, and next action after one pass.",
                sample_source=_sample_source(audience),
                sample_size=5,
                role_fit="target_user",
                related_finding_ids=[],
                related_claim_ids=_claim_ids(claims),
                decision_threshold=(
                    "If fewer than 4 of 5 target users can accurately name the offer, proof limit, "
                    "and next action without interviewer explanation, keep iterating before preference testing."
                ),
                source_brief_id=source_brief_id,
                source_text_hash=source_text_hash,
            )
        )
        return questions

    for finding in major_findings:
        method = _method_for_finding(finding)
        questions.append(
            _question(
                index=len(questions) + 1,
                analysis=analysis,
                method=method,
                uncertainty=_uncertainty_for_finding(finding),
                sample_source=_sample_source(audience),
                sample_size=_sample_size(method),
                role_fit=_role_fit_for_finding(finding),
                related_finding_ids=[finding["findingId"]],
                related_claim_ids=_related_claim_ids(finding, claims),
                decision_threshold=_threshold_for_finding(finding, method),
                source_brief_id=source_brief_id,
                source_text_hash=source_text_hash,
            )
        )

    questions = _add_uncovered_motivation_questions(
        analysis=analysis,
        questions=questions,
        audience=audience,
        claims=claims,
        source_brief_id=source_brief_id,
        source_text_hash=source_text_hash,
    )

    if not any(question["method"] == "comprehension_test" for question in questions):
        questions.insert(
            0,
            _question(
                index=1,
                analysis=analysis,
                method="comprehension_test",
                uncertainty="Whether target users can explain the offer, proof boundary, and next action after one pass.",
                sample_source=_sample_source(audience),
                sample_size=5,
                role_fit="target_user",
                related_finding_ids=[finding["findingId"] for finding in major_findings],
                related_claim_ids=_claim_ids(claims),
                decision_threshold=(
                    "If fewer than 4 of 5 target users can accurately explain the offer, proof limit, "
                    "and next action without interviewer explanation, keep iterating before preference testing."
                ),
                source_brief_id=source_brief_id,
                source_text_hash=source_text_hash,
            ),
        )
        questions = _renumber_questions(questions)

    return questions


def _question(
    *,
    index: int,
    analysis: dict[str, Any],
    method: str,
    uncertainty: str,
    sample_source: str,
    sample_size: int,
    role_fit: str,
    related_finding_ids: list[str],
    related_claim_ids: list[str],
    decision_threshold: str,
    source_brief_id: str,
    source_text_hash: str,
) -> dict[str, Any]:
    evidence_target = "directional" if method in {"comprehension_test", "usability_task", "survey"} else "exploratory"
    related_objection_ids = _related_objection_ids(analysis, related_finding_ids, related_claim_ids)
    related_trust_gap_ids = _related_trust_gap_ids(analysis, related_claim_ids)
    return {
        "artifactType": "research_question",
        "questionId": f"research-{index:03d}",
        "uncertainty": uncertainty,
        "method": method,
        "evidenceGradeTarget": evidence_target,
        "sampleSource": sample_source,
        "sampleSize": sample_size,
        "screenerCriteria": [
            "matches the target role or buying/evaluation role for the source brief",
            "has enough channel familiarity to judge this message context",
            "was not involved in writing the source message",
        ],
        "roleFit": role_fit,
        "protocolVersion": "0.1",
        "biasRisks": _bias_risks(method),
        "consentScript": DEFAULT_CONSENT_SCRIPT,
        "sensitiveDataAvoidance": DEFAULT_SENSITIVE_DATA_AVOIDANCE,
        "deceptionUsed": False,
        "minorOrVulnerableParticipantRule": "Do not recruit minors or vulnerable participants for MVP tests.",
        "stopConditions": DEFAULT_STOP_CONDITIONS,
        "decisionThreshold": decision_threshold,
        "relatedFindingIds": related_finding_ids,
        "relatedClaimIds": related_claim_ids,
        "relatedObjectionIds": related_objection_ids,
        "relatedTrustGapIds": related_trust_gap_ids,
        "sourceBriefId": source_brief_id,
        "sourceAnalysisReportId": analysis["reportId"],
        "sourceTextHash": source_text_hash,
        "analysisLimitation": "No real target-user data has been collected by this research plan.",
    }


def _method_for_finding(finding: dict[str, Any]) -> str:
    issue = finding.get("issue", "").lower()
    if "next action" in issue or "next step" in issue or "fast path" in issue or "learning tax" in issue:
        return "usability_task"
    return METHOD_BY_DIMENSION.get(finding.get("dimensionId", ""), "comprehension_test")


def _uncertainty_for_finding(finding: dict[str, Any]) -> str:
    issue = finding.get("issue", "The message may contain unresolved friction.")
    dimension = finding.get("dimensionId", "message_quality")
    if "evidence boundary" in issue.lower():
        return f"Whether target readers can tell what is sourced, assumed, heuristic, or unvalidated: {issue}"
    if dimension == "trust_proof":
        return f"Whether target evaluators can identify what proof supports the claim and what remains unproven: {issue}"
    if dimension == "ethical_risk":
        return f"Whether target readers experience pressure, reduced agency, or sensitive-context risk from the message: {issue}"
    if "fast path" in issue.lower() or "learning tax" in issue.lower():
        return f"Whether target readers can use the documentation for a real task without unnecessary learning tax: {issue}"
    if "next action" in issue.lower() or "next step" in issue.lower():
        return f"Whether target users know what action to take after reading the message: {issue}"
    return f"Whether target users understand the message without rereading or interviewer explanation: {issue}"


def _threshold_for_finding(finding: dict[str, Any], method: str) -> str:
    issue = finding.get("issue", "this uncertainty")
    if method == "usability_task":
        return (
            f"If fewer than 4 of 5 target users can state the intended next action and where they would click, respond, or look next, "
            f"revise the action language tied to: {issue}"
        )
    if method == "user_interview":
        return (
            f"If 3 or more of 5 participants raise the same proof, trust, pressure, or agency concern before prompting, "
            f"treat it as a priority fix tied to: {issue}"
        )
    return (
        f"If fewer than 4 of 5 target users can paraphrase the relevant message point accurately after one pass, "
        f"keep revising the finding tied to: {issue}"
    )


def _sample_size(method: str) -> int:
    if method == "survey":
        return 25
    return 5


def _sample_source(audience: str) -> str:
    return f"Recruit from {audience}; exclude the project team and anyone who helped write the message."


def _role_fit_for_finding(finding: dict[str, Any]) -> str:
    if finding.get("dimensionId") == "trust_proof":
        return "evaluator"
    return "target_user"


def _related_claim_ids(finding: dict[str, Any], claims: list[dict[str, Any]]) -> list[str]:
    claim_ids = [claim_id for claim_id in finding.get("claimIds", []) if isinstance(claim_id, str)]
    if claim_ids:
        return claim_ids
    if finding.get("dimensionId") == "trust_proof":
        return _claim_ids(claims)
    return []


def _claim_ids(claims: list[dict[str, Any]]) -> list[str]:
    return [claim["claimId"] for claim in claims if isinstance(claim, dict) and isinstance(claim.get("claimId"), str)]


def _target_audience(analysis: dict[str, Any]) -> str:
    for question in analysis.get("researchQuestions", []):
        audience = question.get("audience")
        if isinstance(audience, str) and audience.strip():
            return audience.strip()
    return "target users matching the source brief"


def _bias_risks(method: str) -> list[str]:
    risks = ["leading question risk", "social desirability bias", "interviewer explanation risk"]
    if method == "preference_test":
        risks.append("preference treated as behavior proof")
    if method == "ab_test":
        risks.append("underpowered live-channel result")
    return risks


def _coverage(major_findings: list[dict[str, Any]], questions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    coverage: list[dict[str, Any]] = []
    for finding in major_findings:
        finding_id = finding["findingId"]
        linked = [question["questionId"] for question in questions if finding_id in question["relatedFindingIds"]]
        coverage.append(
            {
                "findingId": finding_id,
                "severity": finding.get("severity", "unknown"),
                "dimensionId": finding.get("dimensionId", "unknown"),
                "questionIds": linked,
                "coverageState": "covered" if linked else "needs_manual_review",
            }
        )
    return coverage


def _add_uncovered_motivation_questions(
    *,
    analysis: dict[str, Any],
    questions: list[dict[str, Any]],
    audience: str,
    claims: list[dict[str, Any]],
    source_brief_id: str,
    source_text_hash: str,
) -> list[dict[str, Any]]:
    covered_objections = {
        objection_id
        for question in questions
        for objection_id in question.get("relatedObjectionIds", [])
    }
    covered_trust_gaps = {
        gap_id
        for question in questions
        for gap_id in question.get("relatedTrustGapIds", [])
    }
    for objection in _objection_items(analysis):
        objection_id = objection.get("objectionId")
        if not isinstance(objection_id, str) or objection_id in covered_objections:
            continue
        claim_ids = [claim_id for claim_id in objection.get("claimIds", []) if isinstance(claim_id, str)]
        finding_ids = [
            finding_id for finding_id in objection.get("sourceFindingIds", []) if isinstance(finding_id, str)
        ]
        questions.append(
            _question(
                index=len(questions) + 1,
                analysis=analysis,
                method="user_interview",
                uncertainty=f"Whether target readers independently raise this motivation objection: {objection.get('objection')}",
                sample_source=_sample_source(audience),
                sample_size=5,
                role_fit="target_user",
                related_finding_ids=finding_ids,
                related_claim_ids=claim_ids,
                decision_threshold=(
                    "If 3 or more of 5 participants raise this objection before prompting, "
                    "treat the linked friction as a priority before preference or A/B testing."
                ),
                source_brief_id=source_brief_id,
                source_text_hash=source_text_hash,
            )
        )
        covered_objections.add(objection_id)

    for gap in _trust_gap_items(analysis):
        gap_id = gap.get("gapId")
        if not isinstance(gap_id, str) or gap_id in covered_trust_gaps:
            continue
        claim_ids = [claim_id for claim_id in gap.get("claimIds", []) if isinstance(claim_id, str)]
        if not claim_ids:
            claim_ids = _claim_ids(claims)
        questions.append(
            _question(
                index=len(questions) + 1,
                analysis=analysis,
                method="user_interview",
                uncertainty=f"Whether target evaluators can name what evidence would resolve this trust gap: {gap.get('summary')}",
                sample_source=_sample_source(audience),
                sample_size=5,
                role_fit="evaluator",
                related_finding_ids=[],
                related_claim_ids=claim_ids,
                decision_threshold=(
                    "If 3 or more of 5 evaluators cannot identify sufficient proof from the message, "
                    "keep the linked claim caveated or blocked until better evidence is attached."
                ),
                source_brief_id=source_brief_id,
                source_text_hash=source_text_hash,
            )
        )
        covered_trust_gaps.add(gap_id)
    return questions


def _motivation_friction_coverage(
    analysis: dict[str, Any],
    questions: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    coverage = []
    for objection in _objection_items(analysis):
        objection_id = objection.get("objectionId")
        if not isinstance(objection_id, str):
            continue
        linked = [
            question["questionId"]
            for question in questions
            if objection_id in question.get("relatedObjectionIds", [])
        ]
        coverage.append(
            {
                "objectionId": objection_id,
                "categoryId": objection.get("categoryId", "unknown"),
                "questionIds": linked,
                "coverageState": "covered" if linked else "needs_manual_review",
            }
        )
    return coverage


def _trust_gap_coverage(
    analysis: dict[str, Any],
    questions: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    coverage = []
    for gap in _trust_gap_items(analysis):
        gap_id = gap.get("gapId")
        if not isinstance(gap_id, str):
            continue
        linked = [
            question["questionId"]
            for question in questions
            if gap_id in question.get("relatedTrustGapIds", [])
        ]
        coverage.append(
            {
                "gapId": gap_id,
                "gapType": gap.get("gapType", "unknown"),
                "questionIds": linked,
                "coverageState": "covered" if linked else "needs_manual_review",
            }
        )
    return coverage


def _related_objection_ids(
    analysis: dict[str, Any],
    finding_ids: list[str],
    claim_ids: list[str],
) -> list[str]:
    finding_set = set(finding_ids)
    claim_set = set(claim_ids)
    objection_ids = []
    for objection in _objection_items(analysis):
        objection_id = objection.get("objectionId")
        if not isinstance(objection_id, str):
            continue
        source_findings = set(objection.get("sourceFindingIds", []))
        source_claims = set(objection.get("claimIds", []))
        if source_findings.intersection(finding_set) or source_claims.intersection(claim_set):
            objection_ids.append(objection_id)
    return objection_ids


def _related_trust_gap_ids(analysis: dict[str, Any], claim_ids: list[str]) -> list[str]:
    claim_set = set(claim_ids)
    gap_ids = []
    for gap in _trust_gap_items(analysis):
        gap_id = gap.get("gapId")
        if not isinstance(gap_id, str):
            continue
        if set(gap.get("claimIds", [])).intersection(claim_set):
            gap_ids.append(gap_id)
    return gap_ids


def _objection_items(analysis: dict[str, Any]) -> list[dict[str, Any]]:
    objections = analysis.get("motivationFriction", {}).get("objectionMap", [])
    return [item for item in objections if isinstance(item, dict)]


def _trust_gap_items(analysis: dict[str, Any]) -> list[dict[str, Any]]:
    gaps = analysis.get("motivationFriction", {}).get("trustGapReport", {}).get("gaps", [])
    return [item for item in gaps if isinstance(item, dict)]


def _build_interview_script(questions: list[dict[str, Any]]) -> dict[str, Any]:
    interview_questions = [
        question for question in questions if question["method"] in {"user_interview", "comprehension_test"}
    ]
    if not interview_questions:
        interview_questions = questions[:1]

    items = []
    for index, question in enumerate(interview_questions, start=1):
        items.append(
            {
                "scriptItemId": f"script-{index:03d}",
                "questionId": question["questionId"],
                "prompt": _interview_prompt(question),
                "followUp": "What words or missing details made you say that?",
                "avoidAsking": "Do not ask whether the participant likes the message before they explain what it means.",
            }
        )
    return {
        "scriptId": "interview-script-001",
        "consentScript": DEFAULT_CONSENT_SCRIPT,
        "openingPrompt": "Please read this once at your normal speed, then tell me what you think it is saying.",
        "items": items,
        "closingPrompt": "What, if anything, would you need to see before trusting or acting on this message?",
        "sensitiveDataAvoidance": DEFAULT_SENSITIVE_DATA_AVOIDANCE,
    }


def _build_survey_questions(questions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    survey_items: list[dict[str, Any]] = []
    for index, question in enumerate(questions, start=1):
        survey_items.append(
            {
                "surveyItemId": f"survey-{index:03d}",
                "questionId": question["questionId"],
                "questionText": _survey_text(question),
                "responseType": "single_choice_plus_open_text",
                "allowedInterpretation": "directional input for the stated uncertainty only",
                "forbiddenInterpretation": "market preference, conversion lift, or statistically supported proof",
            }
        )
    return survey_items


def _build_usability_tasks(questions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    task_questions = [question for question in questions if question["method"] == "usability_task"]
    if not task_questions:
        task_questions = [questions[0]]

    tasks: list[dict[str, Any]] = []
    for index, question in enumerate(task_questions, start=1):
        tasks.append(
            {
                "taskId": f"task-{index:03d}",
                "questionId": question["questionId"],
                "taskPrompt": "After reading the message once, show or describe exactly what you would do next.",
                "successSignal": "Participant can identify the intended next action without moderator explanation.",
                "successThreshold": "At least 4 of 5 target users complete or accurately describe the intended next action.",
                "failureSignal": "Participant hesitates, names a different action, or asks what the message wants them to do.",
            }
        )
    return tasks


def _build_ab_hypotheses(analysis: dict[str, Any], questions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    primary = questions[0]
    return [
        {
            "hypothesisId": "ab-hypothesis-001",
            "sourceQuestionId": primary["questionId"],
            "hypothesis": (
                "A claim-gated variant that states the product category, proof boundary, and next action more explicitly "
                "will improve the exact live-channel action metric compared with the current message."
            ),
            "preconditions": [
                "Run comprehension testing first.",
                "Use only variants that passed the claim gate.",
                "Define one exact audience, channel, metric, and time window before launch.",
            ],
            "metric": "exact channel action rate for the stated desired action",
            "sampleSizeCaveat": (
                "Do not call an A/B result statistically supported unless the sample size, randomization, duration, "
                "and analysis plan are adequate for that exact channel."
            ),
            "evidenceGradeLimit": "exploratory unless the live test design supports statistical interpretation",
            "sourceAnalysisReportId": analysis["reportId"],
        }
    ]


def _decision_summary(questions: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "firstDecisionGate": "comprehension_test",
        "minimumPromotionRule": "Do not move to preference or A/B testing until comprehension questions meet their thresholds.",
        "blockedFindingRule": "If any blocked finding remains unresolved, keep publishing and live testing blocked.",
        "questionThresholds": [
            {
                "questionId": question["questionId"],
                "method": question["method"],
                "decisionThreshold": question["decisionThreshold"],
            }
            for question in questions
        ],
    }


def _interview_prompt(question: dict[str, Any]) -> str:
    if question["method"] == "user_interview":
        return "What did this message make you believe, and what would you need to verify before trusting it?"
    return "In your own words, what is this message offering, who is it for, and what should someone do next?"


def _survey_text(question: dict[str, Any]) -> str:
    if question["method"] == "usability_task":
        return "After reading this message, which next action do you think it is asking you to take?"
    if question["method"] == "user_interview":
        return "Which part of this message would you most need proof for before trusting it?"
    return "Which statement best describes what this message is offering?"


def _summary(questions: list[dict[str, Any]], major_findings: list[dict[str, Any]]) -> str:
    return (
        f"Generated {len(questions)} research questions covering {len(major_findings)} major uncertainties. "
        "Run comprehension validation before preference, persuasion, or live-channel testing."
    )


def _renumber_questions(questions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    renumbered = []
    for index, question in enumerate(questions, start=1):
        item = dict(question)
        item["questionId"] = f"research-{index:03d}"
        renumbered.append(item)
    return renumbered


def _hash_file(path: Path) -> str:
    return f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"


def _hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()

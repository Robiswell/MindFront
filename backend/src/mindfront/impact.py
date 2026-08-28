"""Documentation task-validation evidence for Mindfront.

This module handles measured task observations separately from heuristic
analysis. The output may represent exact-context small-sample evidence, but it
still is not market evidence and must not be generalized beyond the tested
document, audience, and tasks.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from json import JSONDecodeError
from pathlib import Path
from statistics import mean, median
from typing import Any

from . import __version__


class TaskValidationBlockedError(Exception):
    """Raised when task-validation input cannot be summarized."""

    def __init__(self, reasons: list[dict[str, str]]):
        self.reasons = reasons
        super().__init__("Task validation blocked by input errors.")


REQUIRED_INPUT_FIELDS = {
    "artifactType",
    "validationId",
    "observationSource",
    "sourceAnalysisReportId",
    "briefId",
    "documentId",
    "documentType",
    "targetAudience",
    "evidenceCollectionMethod",
    "containsPersonalData",
    "containsCustomerConfidentialData",
    "llmProcessingAllowed",
    "tasks",
    "sessions",
}

REQUIRED_SESSION_FIELDS = {
    "sessionId",
    "participantToken",
    "roleSegment",
    "taskId",
    "completed",
    "skimToAnswerSeconds",
    "followUpQuestionCount",
    "skippedSectionCount",
    "expertRespectRating",
    "reuseIntentRating",
    "trustObjectionCodes",
}

OBSERVATION_SOURCE_PROFILES = {
    "real_task_observation": {
        "evidenceBasis": "small_user_test",
        "evidenceGrade": "exact_context_directional",
        "realTaskEvidenceCreated": True,
        "decisionStates": {
            "directional_task_evidence_positive",
            "directional_task_evidence_mixed",
            "needs_documentation_iteration",
        },
    },
    "synthetic_fixture": {
        "evidenceBasis": "synthetic_task_fixture",
        "evidenceGrade": "synthetic_fixture_only",
        "realTaskEvidenceCreated": False,
        "decisionStates": {"synthetic_fixture_only"},
    },
}

FORBIDDEN_RESULT_MARKERS = {
    "small_user_test_supported",
    "validated_for_exact_context",
}


def build_task_validation_result(
    input_path: str | Path,
    *,
    analysis_path: str | Path | None = None,
) -> dict[str, Any]:
    """Summarize measured documentation task-validation observations."""

    input_file = Path(input_path)
    source = _load_json_file(input_file, "task validation input")
    _validate_input(source, str(input_file))
    analysis = _load_analysis(Path(analysis_path)) if analysis_path else None
    _validate_analysis_reference(source, analysis, str(input_file))

    sessions = source["sessions"]
    profile = OBSERVATION_SOURCE_PROFILES[source["observationSource"]]
    baseline = source.get("baselineMetrics") if isinstance(source.get("baselineMetrics"), dict) else {}
    aggregate = _aggregate_metrics(sessions)
    deltas = _before_after_deltas(aggregate, baseline)
    generated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    real_task_evidence_created = bool(profile["realTaskEvidenceCreated"])
    decision_state = _decision_state(aggregate) if real_task_evidence_created else "synthetic_fixture_only"

    result = {
        "artifactType": "documentation_task_validation_result",
        "validationResultId": f"task-validation-{_hash_text(source['validationId'] + source['sourceAnalysisReportId'])[:12]}",
        "sourceValidationId": source["validationId"],
        "observationSource": source["observationSource"],
        "sourceAnalysisReportId": source["sourceAnalysisReportId"],
        "briefId": source["briefId"],
        "documentId": source["documentId"],
        "documentType": source["documentType"],
        "targetAudience": source["targetAudience"],
        "sourceProtocolId": source.get("sourceProtocolId"),
        "sourceProtocolHash": source.get("sourceProtocolHash"),
        "sourceSessionsHash": source.get("sourceSessionsHash"),
        "evidenceBasis": profile["evidenceBasis"],
        "evidenceGrade": profile["evidenceGrade"],
        "marketEvidenceCreated": False,
        "notMarketEvidence": True,
        "realTaskEvidenceCreated": real_task_evidence_created,
        "rawParticipantDataStored": False,
        "dataBoundary": (
        "Task-validation output stores aggregate measurements, role segments, non-identifying participant tokens, "
            "and coded trust-objection categories. It must not include participant names, emails, raw comments, "
            "or personal data."
        ),
        "sample": {
            "participantCount": len({session["participantToken"] for session in sessions}),
            "sessionCount": len({session["sessionId"] for session in sessions}),
            "roleSegments": sorted({session["roleSegment"] for session in sessions}),
            "taskCount": len(source["tasks"]),
            "taskAttemptCount": len(sessions),
            "consentScriptUsed": bool(source.get("consentScriptUsed")),
            "collectionMethod": source["evidenceCollectionMethod"],
            "observationSource": source["observationSource"],
        },
        "tasks": source["tasks"],
        "aggregateMetrics": aggregate,
        "baselineMetrics": baseline,
        "beforeAfterDeltas": deltas,
        "executiveSignals": _executive_signals(aggregate, deltas, profile["evidenceBasis"], real_task_evidence_created),
        "decisionState": decision_state,
        "recommendedNextStep": _recommended_next_step(aggregate, real_task_evidence_created),
        "limitations": _limitations(real_task_evidence_created),
        "sourceInputHash": _hash_file(input_file),
        "sourceAnalysisHash": _hash_file(Path(analysis_path)) if analysis_path else None,
        "outputHash": "sha256:pending-until-written",
        "generatedAt": generated_at,
        "toolVersion": __version__,
    }
    return result


def write_task_validation_result(result: dict[str, Any], output_path: str | Path) -> Path:
    """Write a task-validation result JSON artifact."""

    destination = Path(output_path)
    payload = finalize_task_validation_result(result)
    if destination.suffix.lower() != ".json":
        destination.mkdir(parents=True, exist_ok=True)
        destination = destination / "documentation-task-validation-result.json"
    else:
        destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return destination


def finalize_task_validation_result(result: dict[str, Any]) -> dict[str, Any]:
    """Return a result with a stable payload hash."""

    payload = json.loads(json.dumps(result))
    payload["outputHash"] = "sha256:pending-until-written"
    provisional = json.dumps(payload, indent=2, sort_keys=True)
    payload["outputHash"] = f"sha256:{_hash_text(provisional)}"
    return payload


def task_validation_result_errors(data: dict[str, Any], path: str = "task_validation") -> list[dict[str, str]]:
    """Return evidence-boundary errors for a task-validation result artifact."""

    reasons: list[dict[str, str]] = []
    if data.get("artifactType") != "documentation_task_validation_result":
        reasons.append(
            {
                "code": "invalid_artifact_type",
                "message": "Task-validation result must use artifactType documentation_task_validation_result.",
                "path": f"{path}.artifactType",
            }
        )
    source = data.get("observationSource")
    profile = OBSERVATION_SOURCE_PROFILES.get(str(source))
    if not profile:
        reasons.append(
            {
                "code": "invalid_observation_source",
                "message": "observationSource must be real_task_observation or synthetic_fixture.",
                "path": f"{path}.observationSource",
            }
        )
    if data.get("marketEvidenceCreated") is not False:
        reasons.append(
            {
                "code": "evidence_boundary_violation",
                "message": "Task-validation artifacts cannot create market evidence.",
                "path": f"{path}.marketEvidenceCreated",
            }
        )
    if data.get("notMarketEvidence") is not True:
        reasons.append(
            {
                "code": "evidence_boundary_violation",
                "message": "Task-validation artifacts must keep notMarketEvidence true.",
                "path": f"{path}.notMarketEvidence",
            }
        )
    if data.get("rawParticipantDataStored") is not False:
        reasons.append(
            {
                "code": "raw_participant_data_not_allowed",
                "message": "Task-validation results must not store raw participant data.",
                "path": f"{path}.rawParticipantDataStored",
            }
        )
    for field_name in ("validationResultId", "sourceValidationId", "sourceAnalysisReportId", "briefId", "documentId"):
        if not isinstance(data.get(field_name), str) or not data.get(field_name).strip():
            reasons.append(
                {
                    "code": "missing_required_field",
                    "message": f"Task-validation result must include non-empty {field_name}.",
                    "path": f"{path}.{field_name}",
                }
            )
    for field_name in ("sourceProtocolId", "sourceProtocolHash", "sourceSessionsHash"):
        if data.get(field_name) is not None and not isinstance(data.get(field_name), str):
            reasons.append(
                {
                    "code": "invalid_optional_lineage_field",
                    "message": f"{field_name} must be a string when present.",
                    "path": f"{path}.{field_name}",
                }
            )
    if profile:
        if data.get("evidenceBasis") != profile["evidenceBasis"]:
            reasons.append(
                {
                    "code": "evidence_basis_mismatch",
                    "message": f"{source} must use evidenceBasis {profile['evidenceBasis']}.",
                    "path": f"{path}.evidenceBasis",
                }
            )
    sample = data.get("sample")
    if not isinstance(sample, dict):
        reasons.append(
            {
                "code": "invalid_sample",
                "message": "Task-validation result must include a sample object.",
                "path": f"{path}.sample",
            }
        )
    else:
        _validate_result_int(sample, "participantCount", f"{path}.sample", reasons, minimum=0, maximum=100000)
        _validate_result_int(sample, "sessionCount", f"{path}.sample", reasons, minimum=0, maximum=100000, required=False)
        _validate_result_int(sample, "taskCount", f"{path}.sample", reasons, minimum=1, maximum=100000)
        _validate_result_int(sample, "taskAttemptCount", f"{path}.sample", reasons, minimum=1, maximum=100000)
    metrics = data.get("aggregateMetrics")
    if not isinstance(metrics, dict):
        reasons.append(
            {
                "code": "invalid_metrics",
                "message": "Task-validation result must include aggregateMetrics.",
                "path": f"{path}.aggregateMetrics",
            }
        )
    else:
        _validate_result_number(metrics, "completionRate", f"{path}.aggregateMetrics", reasons, minimum=0, maximum=1)
        _validate_result_int(metrics, "completedTaskCount", f"{path}.aggregateMetrics", reasons, minimum=0, maximum=100000)
        _validate_result_int(metrics, "taskAttemptCount", f"{path}.aggregateMetrics", reasons, minimum=1, maximum=100000)
        _validate_result_number(
            metrics, "medianSkimToAnswerSeconds", f"{path}.aggregateMetrics", reasons, minimum=0, maximum=3600
        )
        _validate_result_number(
            metrics, "averageSkimToAnswerSeconds", f"{path}.aggregateMetrics", reasons, minimum=0, maximum=3600
        )
        _validate_result_number(
            metrics, "averageFollowUpQuestionCount", f"{path}.aggregateMetrics", reasons, minimum=0, maximum=50
        )
        _validate_result_number(
            metrics, "averageSkippedSectionCount", f"{path}.aggregateMetrics", reasons, minimum=0, maximum=50
        )
        _validate_result_number(
            metrics, "averageExpertRespectRating", f"{path}.aggregateMetrics", reasons, minimum=1, maximum=5
        )
        _validate_result_number(
            metrics, "averageReuseIntentRating", f"{path}.aggregateMetrics", reasons, minimum=1, maximum=5
        )
        _validate_result_int(metrics, "trustObjectionCount", f"{path}.aggregateMetrics", reasons, minimum=0, maximum=100000)
    if isinstance(sample, dict) and isinstance(metrics, dict):
        if (
            isinstance(sample.get("taskAttemptCount"), int)
            and isinstance(metrics.get("taskAttemptCount"), int)
            and sample.get("taskAttemptCount") != metrics.get("taskAttemptCount")
        ):
            reasons.append(
                {
                    "code": "task_attempt_count_mismatch",
                    "message": "sample.taskAttemptCount must match aggregateMetrics.taskAttemptCount.",
                    "path": f"{path}.sample.taskAttemptCount",
                }
            )
        if (
            isinstance(sample.get("participantCount"), int)
            and isinstance(sample.get("sessionCount"), int)
            and sample.get("participantCount") > sample.get("sessionCount")
        ):
            reasons.append(
                {
                    "code": "participant_count_mismatch",
                    "message": "sample.participantCount cannot exceed sample.sessionCount.",
                    "path": f"{path}.sample.participantCount",
                }
            )
    if profile:
        if data.get("evidenceGrade") != profile["evidenceGrade"]:
            reasons.append(
                {
                    "code": "evidence_grade_mismatch",
                    "message": f"{source} must use evidenceGrade {profile['evidenceGrade']}.",
                    "path": f"{path}.evidenceGrade",
                }
            )
        if data.get("realTaskEvidenceCreated") is not profile["realTaskEvidenceCreated"]:
            reasons.append(
                {
                    "code": "real_task_evidence_mismatch",
                    "message": f"{source} must use realTaskEvidenceCreated {profile['realTaskEvidenceCreated']}.",
                    "path": f"{path}.realTaskEvidenceCreated",
                }
            )
        if data.get("decisionState") not in profile["decisionStates"]:
            reasons.append(
                {
                    "code": "invalid_decision_state",
                    "message": f"{source} cannot use decisionState {data.get('decisionState')}.",
                    "path": f"{path}.decisionState",
                }
            )
    signals = data.get("executiveSignals")
    if not isinstance(signals, list):
        reasons.append(
            {
                "code": "invalid_executive_signals",
                "message": "Task-validation result must include executiveSignals array.",
                "path": f"{path}.executiveSignals",
            }
        )
    else:
        for index, signal in enumerate(signals):
            signal_path = f"{path}.executiveSignals[{index}]"
            if not isinstance(signal, dict):
                reasons.append(
                    {"code": "invalid_signal", "message": "Each executive signal must be an object.", "path": signal_path}
                )
                continue
            if profile and signal.get("evidenceBasis") != profile["evidenceBasis"]:
                reasons.append(
                    {
                        "code": "evidence_basis_mismatch",
                        "message": f"Executive signals for {source} must use {profile['evidenceBasis']}.",
                        "path": f"{signal_path}.evidenceBasis",
                    }
                )
            if signal.get("notMarketEvidence") is not True:
                reasons.append(
                    {
                        "code": "evidence_boundary_violation",
                        "message": "Executive signals must keep notMarketEvidence true.",
                        "path": f"{signal_path}.notMarketEvidence",
                    }
                )
    serialized = json.dumps(data, sort_keys=True)
    for marker in sorted(FORBIDDEN_RESULT_MARKERS):
        if marker in serialized:
            reasons.append(
                {
                    "code": "forbidden_confidence_upgrade",
                    "message": f"Task-validation artifacts must not contain {marker}.",
                    "path": path,
                }
            )
    return reasons


def _aggregate_metrics(sessions: list[dict[str, Any]]) -> dict[str, Any]:
    completion_count = sum(1 for session in sessions if session["completed"] is True)
    skim_times = [float(session["skimToAnswerSeconds"]) for session in sessions]
    follow_ups = [int(session["followUpQuestionCount"]) for session in sessions]
    skipped = [int(session["skippedSectionCount"]) for session in sessions]
    respect = [float(session["expertRespectRating"]) for session in sessions]
    reuse = [float(session["reuseIntentRating"]) for session in sessions]
    objections = [
        str(objection_code).strip()
        for session in sessions
        for objection_code in session.get("trustObjectionCodes", [])
        if str(objection_code).strip()
    ]
    return {
        "completionRate": round(completion_count / len(sessions), 4),
        "completedTaskCount": completion_count,
        "taskAttemptCount": len(sessions),
        "medianSkimToAnswerSeconds": round(median(skim_times), 2),
        "averageSkimToAnswerSeconds": round(mean(skim_times), 2),
        "averageFollowUpQuestionCount": round(mean(follow_ups), 2),
        "averageSkippedSectionCount": round(mean(skipped), 2),
        "averageExpertRespectRating": round(mean(respect), 2),
        "averageReuseIntentRating": round(mean(reuse), 2),
        "trustObjectionCount": len(objections),
        "topTrustObjectionCodes": _top_counts(objections),
    }


def _before_after_deltas(aggregate: dict[str, Any], baseline: dict[str, Any]) -> dict[str, Any]:
    fields = {
        "completionRate": "higher_is_better",
        "medianSkimToAnswerSeconds": "lower_is_better",
        "averageFollowUpQuestionCount": "lower_is_better",
        "averageExpertRespectRating": "higher_is_better",
        "averageReuseIntentRating": "higher_is_better",
    }
    deltas = {}
    for field_name, direction in fields.items():
        if field_name not in baseline:
            continue
        before = float(baseline[field_name])
        after = float(aggregate[field_name])
        raw_delta = after - before
        improved = raw_delta > 0 if direction == "higher_is_better" else raw_delta < 0
        deltas[field_name] = {
            "baseline": before,
            "observed": after,
            "delta": round(raw_delta, 4),
            "direction": direction,
            "improved": improved,
        }
    return deltas


def _executive_signals(
    aggregate: dict[str, Any],
    deltas: dict[str, Any],
    evidence_basis: str,
    real_task_evidence_created: bool,
) -> list[dict[str, Any]]:
    definitions = [
        ("task_completion_rate", "Task Completion Rate", "completionRate"),
        ("skim_to_answer_speed", "Median Skim-To-Answer Seconds", "medianSkimToAnswerSeconds"),
        ("follow_up_load", "Average Follow-Up Questions", "averageFollowUpQuestionCount"),
        ("expert_respect", "Expert Respect Rating", "averageExpertRespectRating"),
        ("reuse_intent", "Reuse Intent Rating", "averageReuseIntentRating"),
        ("trust_objections", "Trust Objection Count", "trustObjectionCount"),
    ]
    signals = []
    for signal_id, label, field_name in definitions:
        signals.append(
            {
                "signalId": signal_id,
                "label": label,
                "value": aggregate[field_name],
                "delta": deltas.get(field_name),
                "evidenceBasis": evidence_basis,
                "notMarketEvidence": True,
                "realTaskEvidenceCreated": real_task_evidence_created,
            }
        )
    return signals


def _decision_state(aggregate: dict[str, Any]) -> str:
    if (
        aggregate["taskAttemptCount"] >= 5
        and aggregate["completionRate"] >= 0.8
        and aggregate["averageExpertRespectRating"] >= 4
        and aggregate["medianSkimToAnswerSeconds"] <= 90
    ):
        return "directional_task_evidence_positive"
    if aggregate["completionRate"] < 0.6 or aggregate["averageExpertRespectRating"] < 3.5:
        return "needs_documentation_iteration"
    return "directional_task_evidence_mixed"


def _recommended_next_step(aggregate: dict[str, Any], real_task_evidence_created: bool) -> str:
    if not real_task_evidence_created:
        return "Use this fixture only to verify workflow behavior; collect real no-PII task observations before presenting impact evidence."
    if aggregate["taskAttemptCount"] < 5:
        return "Run at least five exact-context task attempts before presenting this as directional evidence."
    if aggregate["completionRate"] < 0.8:
        return "Revise the fast path and task instructions before broader validation."
    if aggregate["averageExpertRespectRating"] < 4:
        return "Revise language that may reduce expert agency before broader validation."
    return "Repeat the same task protocol across additional document types before making company-level impact claims."


def _limitations(real_task_evidence_created: bool) -> list[str]:
    if not real_task_evidence_created:
        return [
            "This is a synthetic workflow fixture, not real task evidence.",
            "Do not present synthetic fixture metrics as user evidence, market evidence, adoption proof, or performance proof.",
            "Collect real no-PII task observations before using this loop in an executive impact narrative.",
            "Participant identity and sensitive personal data must stay out of Mindfront artifacts.",
        ]
    return [
        "This is exact-context small-sample task evidence, not market evidence.",
        "Do not generalize beyond the tested document, audience, tasks, and date range.",
        "Do not claim company-wide performance lift until repeated task evidence exists across representative documentation types.",
        "Participant identity and sensitive personal data must stay out of Mindfront artifacts.",
    ]


def _validate_input(data: dict[str, Any], path: str) -> None:
    reasons = [
        {
            "code": "missing_required_field",
            "message": f"Missing required field: {field_name}.",
            "path": f"{path}.{field_name}",
        }
        for field_name in sorted(REQUIRED_INPUT_FIELDS)
        if field_name not in data
    ]
    if data.get("artifactType") != "documentation_task_validation_input":
        reasons.append(
            {
                "code": "invalid_artifact_type",
                "message": "Task validation input must use artifactType documentation_task_validation_input.",
                "path": f"{path}.artifactType",
            }
        )
    if data.get("observationSource") not in OBSERVATION_SOURCE_PROFILES:
        reasons.append(
            {
                "code": "invalid_observation_source",
                "message": "observationSource must be real_task_observation or synthetic_fixture.",
                "path": f"{path}.observationSource",
            }
        )
    if data.get("containsPersonalData") is not False:
        reasons.append(
            {
                "code": "personal_data_not_allowed",
                "message": "Task-validation inputs must not contain personal data.",
                "path": f"{path}.containsPersonalData",
            }
        )
    if data.get("containsCustomerConfidentialData") is not False:
        reasons.append(
            {
                "code": "customer_confidential_not_allowed",
                "message": "Task-validation inputs must not contain customer confidential data.",
                "path": f"{path}.containsCustomerConfidentialData",
            }
        )
    if data.get("llmProcessingAllowed") is not False:
        reasons.append(
            {
                "code": "llm_processing_must_remain_disabled",
                "message": "Task-validation inputs are processed locally and must keep llmProcessingAllowed false.",
                "path": f"{path}.llmProcessingAllowed",
            }
        )
    tasks = data.get("tasks", [])
    sessions = data.get("sessions", [])
    if not isinstance(tasks, list) or not tasks:
        reasons.append({"code": "invalid_tasks", "message": "tasks must be a non-empty array.", "path": f"{path}.tasks"})
    if not isinstance(sessions, list) or not sessions:
        reasons.append(
            {"code": "invalid_sessions", "message": "sessions must be a non-empty array.", "path": f"{path}.sessions"}
        )
    task_ids = {task.get("taskId") for task in tasks if isinstance(task, dict)}
    for index, session in enumerate(sessions):
        if not isinstance(session, dict):
            reasons.append(
                {"code": "invalid_session", "message": "Each session must be an object.", "path": f"{path}.sessions[{index}]"}
            )
            continue
        for field_name in sorted(REQUIRED_SESSION_FIELDS):
            if field_name not in session:
                reasons.append(
                    {
                        "code": "missing_required_field",
                        "message": f"Missing session field: {field_name}.",
                        "path": f"{path}.sessions[{index}].{field_name}",
                    }
                )
        if session.get("taskId") not in task_ids:
            reasons.append(
                {
                    "code": "unknown_task_id",
                    "message": f"Session references unknown task id: {session.get('taskId')}.",
                    "path": f"{path}.sessions[{index}].taskId",
                }
            )
        if not isinstance(session.get("completed"), bool):
            reasons.append(
                {
                    "code": "invalid_boolean_field",
                    "message": "completed must be a JSON boolean.",
                    "path": f"{path}.sessions[{index}].completed",
                }
            )
        _validate_token(session, "sessionId", path, index, reasons)
        _validate_token(session, "participantToken", path, index, reasons)
        _validate_numeric(session, "skimToAnswerSeconds", path, index, reasons, minimum=0, maximum=3600)
        _validate_integer(session, "followUpQuestionCount", path, index, reasons, minimum=0, maximum=50)
        _validate_integer(session, "skippedSectionCount", path, index, reasons, minimum=0, maximum=50)
        _validate_numeric(session, "expertRespectRating", path, index, reasons, minimum=1, maximum=5)
        _validate_numeric(session, "reuseIntentRating", path, index, reasons, minimum=1, maximum=5)
        if "trustObjections" in session and session.get("trustObjections"):
            reasons.append(
                {
                    "code": "raw_trust_objections_not_allowed",
                    "message": "Use coded trustObjectionCodes instead of raw trust-objection text.",
                    "path": f"{path}.sessions[{index}].trustObjections",
                }
            )
        if not isinstance(session.get("trustObjectionCodes", []), list):
            reasons.append(
                {
                    "code": "invalid_trust_objections",
                    "message": "trustObjectionCodes must be an array.",
                    "path": f"{path}.sessions[{index}].trustObjectionCodes",
                }
            )
        else:
            for code_index, objection_code in enumerate(session.get("trustObjectionCodes", [])):
                if not _is_safe_code(str(objection_code)):
                    reasons.append(
                        {
                            "code": "invalid_trust_objection_code",
                            "message": "trustObjectionCodes must be short non-identifying snake-case codes.",
                            "path": f"{path}.sessions[{index}].trustObjectionCodes[{code_index}]",
                        }
                    )
    if reasons:
        raise TaskValidationBlockedError(reasons)


def _validate_numeric(
    session: dict[str, Any],
    field_name: str,
    path: str,
    index: int,
    reasons: list[dict[str, str]],
    *,
    minimum: float,
    maximum: float,
) -> None:
    if field_name not in session:
        return
    if isinstance(session[field_name], bool):
        reasons.append(
            {
                "code": "invalid_numeric_field",
                "message": f"{field_name} must be numeric.",
                "path": f"{path}.sessions[{index}].{field_name}",
            }
        )
        return
    try:
        value = float(session[field_name])
    except (TypeError, ValueError):
        reasons.append(
            {
                "code": "invalid_numeric_field",
                "message": f"{field_name} must be numeric.",
                "path": f"{path}.sessions[{index}].{field_name}",
            }
        )
        return
    if value < minimum or value > maximum:
        reasons.append(
            {
                "code": "numeric_field_out_of_range",
                "message": f"{field_name} must be between {minimum:g} and {maximum:g}.",
                "path": f"{path}.sessions[{index}].{field_name}",
            }
        )


def _validate_integer(
    session: dict[str, Any],
    field_name: str,
    path: str,
    index: int,
    reasons: list[dict[str, str]],
    *,
    minimum: int,
    maximum: int,
) -> None:
    if field_name not in session:
        return
    value = session[field_name]
    if not isinstance(value, int) or isinstance(value, bool):
        reasons.append(
            {
                "code": "invalid_integer_field",
                "message": f"{field_name} must be an integer.",
                "path": f"{path}.sessions[{index}].{field_name}",
            }
        )
        return
    if value < minimum or value > maximum:
        reasons.append(
            {
                "code": "integer_field_out_of_range",
                "message": f"{field_name} must be between {minimum:g} and {maximum:g}.",
                "path": f"{path}.sessions[{index}].{field_name}",
            }
        )


def _validate_token(
    session: dict[str, Any],
    field_name: str,
    path: str,
    index: int,
    reasons: list[dict[str, str]],
) -> None:
    if field_name not in session:
        return
    value = session[field_name]
    if not isinstance(value, str) or not _is_safe_code(value):
        reasons.append(
            {
                "code": "invalid_non_identifying_token",
                "message": f"{field_name} must be a short non-identifying token.",
                "path": f"{path}.sessions[{index}].{field_name}",
            }
        )


def _validate_result_number(
    record: dict[str, Any],
    field_name: str,
    path: str,
    reasons: list[dict[str, str]],
    *,
    minimum: float,
    maximum: float,
    required: bool = True,
) -> None:
    if field_name not in record:
        if required:
            reasons.append(
                {
                    "code": "missing_required_field",
                    "message": f"Missing required metric: {field_name}.",
                    "path": f"{path}.aggregateMetrics.{field_name}",
                }
            )
        return
    if isinstance(record[field_name], bool):
        reasons.append(
            {
                "code": "invalid_numeric_field",
                "message": f"{field_name} must be numeric.",
                "path": f"{path}.{field_name}",
            }
        )
        return
    try:
        value = float(record[field_name])
    except (TypeError, ValueError):
        reasons.append(
            {
                "code": "invalid_numeric_field",
                "message": f"{field_name} must be numeric.",
                "path": f"{path}.{field_name}",
            }
        )
        return
    if value < minimum or value > maximum:
        reasons.append(
            {
                "code": "numeric_field_out_of_range",
                "message": f"{field_name} must be between {minimum:g} and {maximum:g}.",
                "path": f"{path}.{field_name}",
            }
        )


def _validate_result_int(
    record: dict[str, Any],
    field_name: str,
    path: str,
    reasons: list[dict[str, str]],
    *,
    minimum: int,
    maximum: int,
    required: bool = True,
) -> None:
    if field_name not in record:
        if required:
            reasons.append(
                {
                    "code": "missing_required_field",
                    "message": f"Missing required count: {field_name}.",
                    "path": f"{path}.{field_name}",
                }
            )
        return
    value = record[field_name]
    if not isinstance(value, int) or isinstance(value, bool):
        reasons.append(
            {
                "code": "invalid_integer_field",
                "message": f"{field_name} must be an integer.",
                "path": f"{path}.{field_name}",
            }
        )
        return
    if value < minimum or value > maximum:
        reasons.append(
            {
                "code": "integer_field_out_of_range",
                "message": f"{field_name} must be between {minimum:g} and {maximum:g}.",
                "path": f"{path}.{field_name}",
            }
        )


def _is_safe_code(value: str) -> bool:
    if not isinstance(value, str):
        return False
    stripped = value.strip()
    if not stripped or len(stripped) > 80:
        return False
    return all(character.islower() or character.isdigit() or character in "-_" for character in stripped)


def _validate_analysis_reference(source: dict[str, Any], analysis: dict[str, Any] | None, path: str) -> None:
    if analysis is None:
        return
    reasons = []
    if analysis.get("artifactType") != "message_analysis_report":
        reasons.append(
            {
                "code": "invalid_analysis_artifact",
                "message": "analysis must be a message_analysis_report.",
                "path": "analysis.artifactType",
            }
        )
    if analysis.get("reportId") != source["sourceAnalysisReportId"]:
        reasons.append(
            {
                "code": "source_mismatch",
                "message": "Task validation input does not reference the supplied analysis report.",
                "path": f"{path}.sourceAnalysisReportId",
            }
        )
    if analysis.get("briefId") != source["briefId"]:
        reasons.append(
            {
                "code": "brief_mismatch",
                "message": "Task validation input does not reference the supplied analysis brief id.",
                "path": f"{path}.briefId",
            }
        )
    if reasons:
        raise TaskValidationBlockedError(reasons)


def _load_analysis(path: Path) -> dict[str, Any]:
    data = _load_json_file(path, "analysis")
    if data.get("artifactType") != "message_analysis_report":
        raise TaskValidationBlockedError(
            [
                {
                    "code": "invalid_artifact_type",
                    "message": "analysis input must be a message_analysis_report.",
                    "path": f"{path}.artifactType",
                }
            ]
        )
    return data


def _top_counts(values: list[str]) -> list[dict[str, Any]]:
    counts: dict[str, int] = {}
    for value in values:
        counts[value] = counts.get(value, 0) + 1
    return [
        {"value": value, "count": count}
        for value, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    ]


def _load_json_file(path: Path, label: str) -> dict[str, Any]:
    if not path.exists():
        raise TaskValidationBlockedError(
            [{"code": f"missing_{label.replace(' ', '_')}_file", "message": f"Missing {label} file.", "path": str(path)}]
        )
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except JSONDecodeError as exc:
        raise TaskValidationBlockedError(
            [
                {
                    "code": "invalid_json",
                    "message": f"Invalid JSON at line {exc.lineno}, column {exc.colno}: {exc.msg}.",
                    "path": str(path),
                }
            ]
        ) from exc
    if not isinstance(data, dict):
        raise TaskValidationBlockedError(
            [{"code": "invalid_json_shape", "message": f"{label} file must contain a JSON object.", "path": str(path)}]
        )
    return data


def _hash_file(path: Path) -> str:
    return f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"


def _hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()

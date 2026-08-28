"""Documentation task-observation protocol generation for Mindfront."""

from __future__ import annotations

import csv
import hashlib
import json
from datetime import datetime, timezone
from json import JSONDecodeError
from pathlib import Path
from typing import Any

from . import __version__


class TaskProtocolBlockedError(Exception):
    """Raised when a task-observation protocol cannot be generated."""

    def __init__(self, reasons: list[dict[str, str]]):
        self.reasons = reasons
        super().__init__("Task observation protocol blocked by input errors.")


class TaskInputBlockedError(Exception):
    """Raised when task-observation sessions cannot be converted into input."""

    def __init__(self, reasons: list[dict[str, str]]):
        self.reasons = reasons
        super().__init__("Task validation input build blocked by input errors.")


SESSION_TEMPLATE_COLUMNS = [
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
]

PROHIBITED_SESSION_COLUMNS = {
    "name",
    "email",
    "participantname",
    "participantemail",
    "comment",
    "comments",
    "rawcomment",
    "rawcomments",
    "rawnote",
    "rawnotes",
    "freetext",
    "freetextnotes",
    "transcript",
    "quote",
    "notes",
}

OBSERVATION_SOURCES = {"real_task_observation", "synthetic_fixture"}


def build_task_observation_protocol(
    analysis_path: str | Path,
    *,
    research_plan_path: str | Path | None = None,
    document_id: str | None = None,
    document_type: str = "internal_documentation",
) -> dict[str, Any]:
    """Build a no-PII protocol for collecting documentation task observations."""

    analysis_file = Path(analysis_path)
    analysis = _load_analysis_report(analysis_file)
    research_file = Path(research_plan_path) if research_plan_path else None
    research = _load_research_plan(research_file) if research_file else None
    _validate_research_reference(analysis, research, str(research_file) if research_file else "research_plan")
    generated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    tasks = _protocol_tasks(analysis, research)
    protocol_id = f"task-protocol-{_hash_text(analysis['reportId'] + ''.join(task['taskId'] for task in tasks))[:12]}"
    source_research_id = research.get("researchPlanId") if research else None
    resolved_document_id = document_id or f"{analysis.get('briefId', 'brief')}-document"

    return {
        "artifactType": "documentation_task_observation_protocol",
        "protocolId": protocol_id,
        "sourceAnalysisReportId": analysis["reportId"],
        "sourceResearchPlanId": source_research_id,
        "briefId": analysis.get("briefId", "unknown"),
        "documentId": resolved_document_id,
        "documentType": document_type,
        "targetAudience": _target_audience(analysis),
        "observationSource": "real_task_observation",
        "evidenceCollectionMethod": "moderated_or_observed_documentation_task",
        "marketEvidenceCreated": False,
        "notMarketEvidence": True,
        "dataBoundary": (
            "Use only non-identifying participant tokens and aggregate task metrics. Do not collect names, "
            "emails, raw comments, transcripts, customer-confidential details, or personal data."
        ),
        "evidenceBoundary": (
            "This protocol can collect exact-context directional task observations. It does not create market "
            "evidence, adoption proof, or company-wide performance proof."
        ),
        "consentScript": _consent_script(research),
        "stopConditions": _stop_conditions(research),
        "participantTokenRule": (
            "Use short non-identifying tokens such as participant_001. Do not use initials, names, emails, "
            "employee ids, account names, or other identifying values."
        ),
        "observerInstructions": [
            "Give the participant the document and the task prompt without explaining the intended answer.",
            "Start timing when the participant begins reading for the task.",
            "Stop timing when the participant names or shows the answer they would use.",
            "Record only the structured fields in the CSV template.",
            "Use coded trustObjectionCodes such as source_register_clarity or owner_field_missing; do not write raw comments.",
            "Stop the session if personal, customer-confidential, or sensitive information is disclosed.",
        ],
        "tasks": tasks,
        "sessionTemplateColumns": SESSION_TEMPLATE_COLUMNS,
        "taskValidationInputDefaults": {
            "artifactType": "documentation_task_validation_input",
            "observationSource": "real_task_observation",
            "sourceAnalysisReportId": analysis["reportId"],
            "briefId": analysis.get("briefId", "unknown"),
            "documentId": resolved_document_id,
            "documentType": document_type,
            "targetAudience": _target_audience(analysis),
            "evidenceCollectionMethod": "moderated_or_observed_documentation_task",
            "containsPersonalData": False,
            "containsCustomerConfidentialData": False,
            "llmProcessingAllowed": False,
            "consentScriptUsed": True,
        },
        "limitations": [
            "Use this as an observation protocol, not as proof by itself.",
            "Small no-PII task observations are exact-context directional evidence only after sessions are collected.",
            "Do not generalize results beyond the tested document, audience, task set, and collection date.",
            "Synthetic or sample rows in the CSV template must be deleted before real collection.",
        ],
        "sourceAnalysisHash": _hash_file(analysis_file),
        "sourceResearchPlanHash": _hash_file(research_file) if research_file else None,
        "sourceBriefHash": analysis["sourceBriefHash"],
        "sourceTextHash": analysis["sourceTextHash"],
        "configSetHash": analysis["configSetHash"],
        "outputHash": "sha256:pending-until-written",
        "generatedAt": generated_at,
        "toolVersion": __version__,
    }


def write_task_observation_protocol(protocol: dict[str, Any], output_path: str | Path) -> list[Path]:
    """Write protocol JSON, Markdown, and CSV session template artifacts."""

    destination = Path(output_path)
    payload = finalize_task_observation_protocol(protocol)
    if destination.suffix.lower() == ".json":
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return [destination]
    if destination.suffix.lower() == ".md":
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(render_task_observation_protocol_markdown(payload), encoding="utf-8")
        return [destination]

    destination.mkdir(parents=True, exist_ok=True)
    json_path = destination / "documentation-task-observation-protocol.json"
    markdown_path = destination / "documentation-task-observation-protocol.md"
    csv_path = destination / "documentation-task-session-template.csv"
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    markdown_path.write_text(render_task_observation_protocol_markdown(payload), encoding="utf-8")
    _write_session_template_csv(payload, csv_path)
    return [json_path, markdown_path, csv_path]


def finalize_task_observation_protocol(protocol: dict[str, Any]) -> dict[str, Any]:
    """Return a protocol with a stable output hash."""

    payload = json.loads(json.dumps(protocol))
    payload["outputHash"] = "sha256:pending-until-written"
    provisional = json.dumps(payload, indent=2, sort_keys=True)
    payload["outputHash"] = f"sha256:{_hash_text(provisional)}"
    return payload


def render_task_observation_protocol_markdown(protocol: dict[str, Any]) -> str:
    """Render protocol instructions for observers."""

    lines = [
        "# Mindfront Documentation Task Observation Protocol",
        "",
        f"Protocol: `{protocol['protocolId']}`",
        f"Source analysis: `{protocol['sourceAnalysisReportId']}`",
        f"Intended observation source: `{protocol['observationSource']}`",
        "Evidence status: `not_collected`",
        f"Market evidence created: `{str(protocol['marketEvidenceCreated']).lower()}`",
        "",
        "## Evidence Boundary",
        "",
        protocol["evidenceBoundary"],
        "",
        "## Data Boundary",
        "",
        protocol["dataBoundary"],
        "",
        "## Consent Script",
        "",
        protocol["consentScript"],
        "",
        "## Observer Instructions",
        "",
    ]
    lines.extend(f"- {item}" for item in protocol["observerInstructions"])
    lines.extend(["", "## Tasks", ""])
    for task in protocol["tasks"]:
        lines.extend(
            [
                f"### {task['taskId']}",
                "",
                f"- Prompt: {task['taskPrompt']}",
                f"- Success signal: {task['successSignal']}",
                f"- Failure signal: {task['failureSignal']}",
                f"- Success threshold: {task['successThreshold']}",
                "",
            ]
        )
    lines.extend(["## CSV Columns", ""])
    lines.append(", ".join(f"`{column}`" for column in protocol["sessionTemplateColumns"]))
    lines.extend(["", "## Limitations", ""])
    lines.extend(f"- {item}" for item in protocol["limitations"])
    lines.append("")
    return "\n".join(lines)


def build_task_validation_input_from_protocol(
    protocol_path: str | Path,
    sessions_csv_path: str | Path,
    *,
    validation_id: str | None = None,
    observation_source: str = "synthetic_fixture",
) -> dict[str, Any]:
    """Build a documentation_task_validation_input artifact from a protocol and filled CSV."""

    protocol_file = Path(protocol_path)
    sessions_file = Path(sessions_csv_path)
    if observation_source not in OBSERVATION_SOURCES:
        raise TaskInputBlockedError(
            [
                {
                    "code": "invalid_observation_source",
                    "message": "observation_source must be real_task_observation or synthetic_fixture.",
                    "path": "observation_source",
                }
            ]
        )
    protocol = _load_protocol(protocol_file)
    sessions = _load_session_rows(sessions_file, protocol)
    resolved_validation_id = validation_id or f"validation-{_hash_text(protocol['protocolId'] + _hash_file(sessions_file))[:12]}"
    defaults = dict(protocol["taskValidationInputDefaults"])
    defaults["observationSource"] = observation_source
    if observation_source == "synthetic_fixture":
        defaults["evidenceCollectionMethod"] = "synthetic_workflow_fixture"
        defaults["consentScriptUsed"] = False
        provenance = "synthetic_fixture_or_generated_test_rows"
        provenance_boundary = (
            "The caller did not declare these rows as real no-PII observations. Treat the resulting task-validation "
            "artifact as a workflow fixture only."
        )
    else:
        provenance = "caller_declared_real_no_pii_observation"
        provenance_boundary = (
            "The caller explicitly declared this CSV contains real no-PII task observations collected with the "
            "source protocol. The result remains exact-context directional task evidence only."
        )
    return {
        **defaults,
        "validationId": resolved_validation_id,
        "sourceSessionsProvenance": provenance,
        "provenanceBoundary": provenance_boundary,
        "tasks": [
            {
                "taskId": task["taskId"],
                "taskPrompt": task["taskPrompt"],
                "successSignal": task["successSignal"],
                "failureSignal": task["failureSignal"],
                "successThreshold": task["successThreshold"],
            }
            for task in protocol["tasks"]
        ],
        "sessions": sessions,
        "sourceProtocolId": protocol["protocolId"],
        "sourceProtocolHash": _hash_file(protocol_file),
        "sourceSessionsHash": _hash_file(sessions_file),
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "toolVersion": __version__,
    }


def write_task_validation_input(data: dict[str, Any], output_path: str | Path) -> Path:
    """Write a documentation task-validation input JSON artifact."""

    destination = Path(output_path)
    if destination.suffix.lower() != ".json":
        destination.mkdir(parents=True, exist_ok=True)
        destination = destination / "documentation-task-validation-input.json"
    else:
        destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return destination


def _write_session_template_csv(protocol: dict[str, Any], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=SESSION_TEMPLATE_COLUMNS, lineterminator="\n")
        writer.writeheader()
        for index, task in enumerate(protocol["tasks"], start=1):
            writer.writerow(
                {
                    "sessionId": f"session_{index:03d}",
                    "participantToken": f"participant_{index:03d}",
                    "roleSegment": "target_reader",
                    "taskId": task["taskId"],
                    "completed": "",
                    "skimToAnswerSeconds": "",
                    "followUpQuestionCount": "",
                    "skippedSectionCount": "",
                    "expertRespectRating": "",
                    "reuseIntentRating": "",
                    "trustObjectionCodes": "",
                }
            )


def _protocol_tasks(analysis: dict[str, Any], research: dict[str, Any] | None) -> list[dict[str, Any]]:
    if research and isinstance(research.get("usabilityTasks"), list) and research["usabilityTasks"]:
        tasks = []
        for item in research["usabilityTasks"]:
            if not isinstance(item, dict):
                continue
            task_id = item.get("taskId")
            prompt = item.get("taskPrompt")
            if not isinstance(task_id, str) or not isinstance(prompt, str):
                continue
            tasks.append(
                {
                    "taskId": task_id,
                    "taskPrompt": prompt,
                    "successSignal": item.get(
                        "successSignal",
                        "Participant completes or accurately describes the requested documentation task.",
                    ),
                    "failureSignal": item.get(
                        "failureSignal",
                        "Participant cannot complete the task without moderator explanation.",
                    ),
                    "successThreshold": item.get(
                        "successThreshold",
                        "At least 4 of 5 target readers complete the task without moderator explanation.",
                    ),
                    "relatedQuestionId": item.get("questionId"),
                }
            )
        if tasks:
            return tasks[:5]

    return [
        {
            "taskId": "task-001",
            "taskPrompt": "After one pass through the document, show or describe the first action you would take.",
            "successSignal": "Participant can identify the intended next action without moderator explanation.",
            "failureSignal": "Participant hesitates, names a different action, or asks what the document wants them to do.",
            "successThreshold": "At least 4 of 5 target readers complete or accurately describe the intended next action.",
            "relatedQuestionId": None,
        },
        {
            "taskId": "task-002",
            "taskPrompt": "Find the source, owner, or evidence boundary you would rely on before acting.",
            "successSignal": "Participant can identify the source, owner, or evidence boundary without moderator explanation.",
            "failureSignal": "Participant cannot tell what is sourced, assumed, heuristic, or unvalidated.",
            "successThreshold": "At least 4 of 5 target readers identify the source or boundary without moderator explanation.",
            "relatedQuestionId": None,
        },
        {
            "taskId": "task-003",
            "taskPrompt": "Name the section you would skip and the section you would reuse for your own work.",
            "successSignal": "Participant can identify reusable material and low-value material without confusion.",
            "failureSignal": "Participant cannot locate a useful fast path or says the document feels like required onboarding.",
            "successThreshold": "At least 4 of 5 target readers identify a reusable section and a skip-worthy section.",
            "relatedQuestionId": None,
        },
    ]


def _load_session_rows(path: Path, protocol: dict[str, Any]) -> list[dict[str, Any]]:
    if not path.exists():
        raise TaskInputBlockedError(
            [{"code": "missing_sessions_file", "message": "Session CSV file does not exist.", "path": str(path)}]
        )
    task_ids = {task["taskId"] for task in protocol["tasks"]}
    reasons: list[dict[str, str]] = []
    rows: list[dict[str, Any]] = []
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            columns = reader.fieldnames or []
            missing = [column for column in SESSION_TEMPLATE_COLUMNS if column not in columns]
            if missing:
                reasons.extend(
                    {
                        "code": "missing_required_column",
                        "message": f"Missing required session CSV column: {column}.",
                        "path": f"{path}.{column}",
                    }
                    for column in missing
                )
            prohibited = [column for column in columns if column.strip().lower() in PROHIBITED_SESSION_COLUMNS]
            if prohibited:
                reasons.extend(
                    {
                        "code": "prohibited_session_column",
                        "message": f"Session CSV must not include identifying or raw-comment column: {column}.",
                        "path": f"{path}.{column}",
                    }
                    for column in prohibited
                )
            if reasons:
                raise TaskInputBlockedError(reasons)
            for index, row in enumerate(reader, start=2):
                if _row_is_blank(row):
                    continue
                rows.append(_normalize_session_row(row, path=str(path), row_number=index, task_ids=task_ids, reasons=reasons))
    except OSError as exc:
        raise TaskInputBlockedError(
            [{"code": "sessions_file_read_error", "message": f"Could not read session CSV: {exc}.", "path": str(path)}]
        ) from exc
    if not rows:
        reasons.append({"code": "missing_sessions", "message": "Session CSV must contain at least one session row.", "path": str(path)})
    if reasons:
        raise TaskInputBlockedError(reasons)
    return rows


def _normalize_session_row(
    row: dict[str, str],
    *,
    path: str,
    row_number: int,
    task_ids: set[str],
    reasons: list[dict[str, str]],
) -> dict[str, Any]:
    row_path = f"{path}:row{row_number}"
    task_id = _cell(row, "taskId")
    if task_id not in task_ids:
        reasons.append({"code": "unknown_task_id", "message": f"Unknown taskId: {task_id}.", "path": f"{row_path}.taskId"})
    session_id = _cell(row, "sessionId")
    participant_token = _cell(row, "participantToken")
    role_segment = _cell(row, "roleSegment")
    _validate_safe_code(session_id, f"{row_path}.sessionId", reasons)
    _validate_safe_code(participant_token, f"{row_path}.participantToken", reasons)
    _validate_safe_code(role_segment, f"{row_path}.roleSegment", reasons)
    completed = _parse_bool(_cell(row, "completed"), f"{row_path}.completed", reasons)
    skim = _parse_float(_cell(row, "skimToAnswerSeconds"), f"{row_path}.skimToAnswerSeconds", reasons, minimum=0, maximum=3600)
    follow_ups = _parse_int(_cell(row, "followUpQuestionCount"), f"{row_path}.followUpQuestionCount", reasons, minimum=0, maximum=50)
    skipped = _parse_int(_cell(row, "skippedSectionCount"), f"{row_path}.skippedSectionCount", reasons, minimum=0, maximum=50)
    respect = _parse_float(_cell(row, "expertRespectRating"), f"{row_path}.expertRespectRating", reasons, minimum=1, maximum=5)
    reuse = _parse_float(_cell(row, "reuseIntentRating"), f"{row_path}.reuseIntentRating", reasons, minimum=1, maximum=5)
    objection_codes = _parse_codes(_cell(row, "trustObjectionCodes"), f"{row_path}.trustObjectionCodes", reasons)
    return {
        "sessionId": session_id,
        "participantToken": participant_token,
        "roleSegment": role_segment,
        "taskId": task_id,
        "completed": completed,
        "skimToAnswerSeconds": skim,
        "followUpQuestionCount": follow_ups,
        "skippedSectionCount": skipped,
        "expertRespectRating": respect,
        "reuseIntentRating": reuse,
        "trustObjectionCodes": objection_codes,
    }


def _load_analysis_report(path: Path) -> dict[str, Any]:
    data = _load_json_file(path, "analysis")
    if data.get("artifactType") != "message_analysis_report":
        raise TaskProtocolBlockedError(
            [{"code": "invalid_artifact_type", "message": "analysis must be a message_analysis_report.", "path": f"{path}.artifactType"}]
        )
    required = ("reportId", "briefId", "sourceBriefHash", "sourceTextHash", "configSetHash")
    reasons = [
        {"code": "missing_required_field", "message": f"Missing analysis field: {field}.", "path": f"{path}.{field}"}
        for field in required
        if field not in data
    ]
    if reasons:
        raise TaskProtocolBlockedError(reasons)
    return data


def _load_research_plan(path: Path) -> dict[str, Any]:
    data = _load_json_file(path, "research plan")
    if data.get("artifactType") != "research_plan":
        raise TaskProtocolBlockedError(
            [{"code": "invalid_artifact_type", "message": "research plan must be a research_plan.", "path": f"{path}.artifactType"}]
        )
    return data


def _load_protocol(path: Path) -> dict[str, Any]:
    data = _load_json_file(path, "task observation protocol", error_class=TaskInputBlockedError)
    if data.get("artifactType") != "documentation_task_observation_protocol":
        raise TaskInputBlockedError(
            [
                {
                    "code": "invalid_artifact_type",
                    "message": "protocol must be a documentation_task_observation_protocol.",
                    "path": f"{path}.artifactType",
                }
            ]
        )
    return data


def _load_json_file(path: Path, label: str, *, error_class: type[Exception] = TaskProtocolBlockedError) -> dict[str, Any]:
    if not path.exists():
        raise error_class(
            [{"code": f"missing_{label.replace(' ', '_')}_file", "message": f"Missing {label} file.", "path": str(path)}]
        )
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except JSONDecodeError as exc:
        error = {"code": "invalid_json", "message": f"Invalid JSON at line {exc.lineno}, column {exc.colno}: {exc.msg}.", "path": str(path)}
        raise error_class([error]) from exc
    if not isinstance(data, dict):
        raise error_class(
            [{"code": "invalid_json_shape", "message": f"{label} file must contain a JSON object.", "path": str(path)}]
        )
    return data


def _validate_research_reference(analysis: dict[str, Any], research: dict[str, Any] | None, path: str) -> None:
    if not research:
        return
    reasons = []
    if research.get("sourceAnalysisReportId") != analysis["reportId"]:
        reasons.append({"code": "source_mismatch", "message": "Research plan does not reference analysis report.", "path": path})
    if research.get("briefId") != analysis.get("briefId"):
        reasons.append({"code": "brief_mismatch", "message": "Research plan does not reference analysis brief.", "path": path})
    if research.get("marketEvidenceCreated") is not False:
        reasons.append(
            {"code": "evidence_boundary_violation", "message": "Research plan cannot create market evidence.", "path": path}
        )
    if reasons:
        raise TaskProtocolBlockedError(reasons)


def _target_audience(analysis: dict[str, Any]) -> str:
    if isinstance(analysis.get("targetAudience"), str) and analysis["targetAudience"].strip():
        return analysis["targetAudience"]
    quality = analysis.get("documentationQuality")
    if isinstance(quality, dict) and quality.get("detected"):
        return "technical specialists and cross-functional documentation readers"
    return "target readers for the source brief"


def _consent_script(research: dict[str, Any] | None) -> str:
    if research and isinstance(research.get("interviewScript"), dict):
        for item in research["interviewScript"].get("items", []):
            question = _question_by_id(research, item.get("questionId"))
            if question and isinstance(question.get("consentScript"), str):
                return question["consentScript"]
    return "We are testing whether this documentation is understandable and usable. This is not a test of you. You can stop at any time."


def _stop_conditions(research: dict[str, Any] | None) -> list[str]:
    if research:
        for question in research.get("questions", []):
            if isinstance(question, dict) and isinstance(question.get("stopConditions"), list):
                return [str(item) for item in question["stopConditions"]]
    return [
        "participant requests to stop",
        "participant distress",
        "sensitive personal disclosure",
        "customer-confidential disclosure",
    ]


def _question_by_id(research: dict[str, Any], question_id: str | None) -> dict[str, Any] | None:
    for question in research.get("questions", []):
        if isinstance(question, dict) and question.get("questionId") == question_id:
            return question
    return None


def _row_is_blank(row: dict[str, str]) -> bool:
    return all(not str(value or "").strip() for value in row.values())


def _cell(row: dict[str, str], key: str) -> str:
    return str(row.get(key, "") or "").strip()


def _parse_bool(value: str, path: str, reasons: list[dict[str, str]]) -> bool:
    normalized = value.lower()
    if normalized == "true":
        return True
    if normalized == "false":
        return False
    reasons.append({"code": "invalid_boolean_field", "message": "completed must be true or false.", "path": path})
    return False


def _parse_float(value: str, path: str, reasons: list[dict[str, str]], *, minimum: float, maximum: float) -> float:
    try:
        parsed = float(value)
    except ValueError:
        reasons.append({"code": "invalid_numeric_field", "message": "Value must be numeric.", "path": path})
        return minimum
    if parsed < minimum or parsed > maximum:
        reasons.append({"code": "numeric_field_out_of_range", "message": f"Value must be between {minimum:g} and {maximum:g}.", "path": path})
    return parsed


def _parse_int(value: str, path: str, reasons: list[dict[str, str]], *, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except ValueError:
        reasons.append({"code": "invalid_integer_field", "message": "Value must be an integer.", "path": path})
        return minimum
    if str(parsed) != value:
        reasons.append({"code": "invalid_integer_field", "message": "Value must be an integer without decimals.", "path": path})
    if parsed < minimum or parsed > maximum:
        reasons.append({"code": "integer_field_out_of_range", "message": f"Value must be between {minimum:g} and {maximum:g}.", "path": path})
    return parsed


def _parse_codes(value: str, path: str, reasons: list[dict[str, str]]) -> list[str]:
    if not value:
        return []
    codes = [item.strip() for item in value.replace(";", "|").split("|") if item.strip()]
    for code in codes:
        _validate_safe_code(code, path, reasons)
    return codes


def _validate_safe_code(value: str, path: str, reasons: list[dict[str, str]]) -> None:
    if not value or len(value) > 80 or not all(character.islower() or character.isdigit() or character in "-_" for character in value):
        reasons.append(
            {
                "code": "invalid_non_identifying_token",
                "message": "Value must be a short non-identifying lowercase code.",
                "path": path,
            }
        )


def _hash_file(path: Path | None) -> str:
    if path is None:
        return "sha256:not-provided"
    return f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"


def _hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()

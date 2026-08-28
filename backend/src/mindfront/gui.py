"""Local-only browser GUI for Mindfront.

The GUI intentionally reuses Mindfront's deterministic Python contracts. It
does not call cloud services, expose private stores, or add an alternate
analysis path.
"""

from __future__ import annotations

import argparse
import json
import os
import secrets
import shutil
import subprocess
import sys
import threading
import uuid
import webbrowser
from datetime import date, datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .validation import validate_brief_file
from .workplace_assistance import (
    WorkplaceAssistanceBlockedError,
    build_workplace_assistance,
    finalize_workplace_assistance,
    get_self_assistance_profile,
    load_workplace_assistance_policy,
)


REPO_ROOT = Path(__file__).resolve().parents[3]
STATIC_ROOT = REPO_ROOT / "frontend" / "mindfront"
POLICY_PATH = REPO_ROOT / "config" / "workplace-assistance-policy.json"
SELF_PROFILE_PATH = REPO_ROOT / "runtime-data" / "self-workplace-assistance.vault"
GUI_RUN_ROOT = REPO_ROOT / "runtime-data" / "gui-runs"
WORKFLOW_SCRIPT = REPO_ROOT / "skills" / "mindfront" / "scripts" / "run_mindfront_workflow.ps1"
MAX_BODY_BYTES = 1_000_000
ARTIFACT_TIMEOUT_SECONDS = 240

ALLOWED_MODES = {"preflight", "interpret", "debrief", "career_review"}
ALLOWED_CONTEXTS = {
    "career_conversation",
    "conflict_repair",
    "credit_update",
    "cross_functional_handoff",
    "escalation",
    "executive_brief",
    "scope_negotiation",
    "stakeholder_alignment",
}
ALLOWED_CHANNELS = {
    "document",
    "email",
    "informal",
    "meeting",
    "other",
    "presentation",
    "teams_chat",
}
ALLOWED_ENERGY_STATES = {"fatigued", "overloaded", "rushed", "steady", "unknown"}
ALLOWED_AUTHORITY_STATES = {
    "explicitly_delegated",
    "formally_assigned",
    "nominated_pending_confirmation",
    "peer_partnership",
    "self_initiated",
    "sponsor_approved_workstream",
    "unknown",
}
CONFIRMED_AUTHORITY_STATES = {
    "explicitly_delegated",
    "formally_assigned",
    "peer_partnership",
    "sponsor_approved_workstream",
}
ALLOWED_CAREER_CATEGORIES = {
    "adoption_or_reuse",
    "credential_or_learning_evidence",
    "cross_functional_ownership",
    "decision_right",
    "delegated_scope",
    "executive_exposure",
    "measurable_result",
    "sponsor_confirmation",
    "teammate_enablement",
    "title_or_conversion_signal",
}
MODE_ACTIONS = {
    "preflight": ["prepare_talking_points", "flag_risks"],
    "interpret": ["interpret_ambiguity"],
    "debrief": ["debrief"],
    "career_review": ["review_career_evidence"],
}
ALLOWED_ARTIFACT_CHANNELS = {
    "document",
    "email",
    "landing_page",
    "meeting_follow_up",
    "presentation",
    "sales_narrative",
    "teams_chat",
}
ALLOWED_DATA_CLASSIFICATIONS = {"public", "internal", "confidential", "sensitive"}
ALLOWED_COMMUNICATION_INTENTS = {
    "enable_task",
    "inform",
    "persuade",
    "recommend",
    "request_decision",
}
ALLOWED_DOCUMENT_ARCHETYPES = {
    "internal_executive_digest",
    "internal_operational_brief",
    "landing_page",
    "product_message",
    "sales_narrative",
}


class GuiInputError(ValueError):
    """Raised when a GUI request cannot be converted to a Mindfront contract."""

    def __init__(self, field: str, message: str):
        self.field = field
        self.message = message
        super().__init__(message)

    def to_dict(self) -> dict[str, str]:
        return {"code": "gui_input_invalid", "path": self.field, "message": self.message}


class WorkflowExecutionError(RuntimeError):
    """Raised when the existing Mindfront artifact workflow fails."""

    def __init__(self, message: str, *, details: str = ""):
        self.details = details
        super().__init__(message)


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:16]}"


def _text(
    payload: dict[str, Any],
    field: str,
    *,
    required: bool = False,
    maximum: int = 30_000,
) -> str:
    value = payload.get(field, "")
    if value is None:
        value = ""
    if not isinstance(value, str):
        raise GuiInputError(field, "Expected text.")
    value = value.strip()
    if required and not value:
        raise GuiInputError(field, "This field is required.")
    if len(value) > maximum:
        raise GuiInputError(field, f"Keep this field under {maximum:,} characters.")
    return value


def _choice(
    payload: dict[str, Any],
    field: str,
    allowed: set[str],
    *,
    default: str,
) -> str:
    value = payload.get(field, default)
    if not isinstance(value, str) or value not in allowed:
        raise GuiInputError(field, f"Choose one of: {', '.join(sorted(allowed))}.")
    return value


def _lines(
    payload: dict[str, Any],
    field: str,
    *,
    maximum_items: int = 50,
    maximum_length: int = 5_000,
) -> list[str]:
    raw = payload.get(field, "")
    if raw is None:
        return []
    if isinstance(raw, str):
        values = [line.strip(" \t-*") for line in raw.splitlines()]
    elif isinstance(raw, list):
        values = [str(item).strip() for item in raw]
    else:
        raise GuiInputError(field, "Use one item per line.")
    values = [value for value in values if value]
    if len(values) > maximum_items:
        raise GuiInputError(field, f"Use no more than {maximum_items} items.")
    for value in values:
        if len(value) > maximum_length:
            raise GuiInputError(field, f"Keep each item under {maximum_length:,} characters.")
    return values


def _build_assistance_request(payload: dict[str, Any]) -> dict[str, Any]:
    """Translate the plain-language GUI form into the canonical assist schema."""

    if not isinstance(payload, dict):
        raise GuiInputError("$", "Request must be a JSON object.")

    mode = _choice(payload, "mode", ALLOWED_MODES, default="preflight")
    primary_text = _text(payload, "primaryText")
    if primary_text:
        normalized = dict(payload)
        normalized["summary"] = _text(payload, "summary") or {
            "preflight": "Prepare a clear workplace message or conversation.",
            "interpret": "Understand an unclear workplace message or interaction.",
            "debrief": "Debrief a workplace interaction and identify the next step.",
            "career_review": "Review evidence about my own work and career scope.",
        }[mode]
        goal = _text(payload, "desiredOutcome", maximum=2_000)
        if mode == "preflight":
            normalized["draftText"] = primary_text
            normalized["intendedAsk"] = (
                goal or "Help me choose the clearest ask and wording."
            )
        elif mode == "interpret":
            normalized["incomingText"] = primary_text
        elif mode == "debrief":
            normalized["knownFacts"] = primary_text
        else:
            normalized["careerEvidence"] = primary_text
        payload = normalized

    context_default = "career_conversation" if mode == "career_review" else "stakeholder_alignment"
    context = _choice(payload, "context", ALLOWED_CONTEXTS, default=context_default)
    channel = _choice(payload, "channel", ALLOWED_CHANNELS, default="meeting")
    energy = _choice(payload, "energyState", ALLOWED_ENERGY_STATES, default="steady")
    authority_state = _choice(
        payload,
        "authorityState",
        ALLOWED_AUTHORITY_STATES,
        default="unknown",
    )

    summary = _text(payload, "summary", required=True, maximum=5_000)
    audience = _text(payload, "audience", maximum=2_000) or "workplace stakeholder"
    desired_outcome = (
        _text(payload, "desiredOutcome", maximum=2_000)
        or "Clarify the next safe and useful action."
    )
    known_facts = _lines(payload, "knownFacts")
    unresolved_items = _lines(payload, "unresolvedItems", maximum_items=50, maximum_length=3_000)
    decisions = _lines(payload, "decisions", maximum_items=30, maximum_length=3_000)
    commitments = _lines(payload, "commitments", maximum_items=30, maximum_length=3_000)

    facts: list[dict[str, Any]] = [
        {
            "factId": f"fact-user-statement-{index:02d}",
            "statement": statement,
            "status": "user_provided_unverified",
            "sourceType": "user_statement",
            "category": "general",
        }
        for index, statement in enumerate(known_facts, start=1)
    ]

    authority_evidence = _text(payload, "authorityEvidence", maximum=5_000)
    authority_source = _text(payload, "authoritySource", maximum=1_000)
    authority_fact_ids: list[str] = []
    if authority_evidence or authority_source:
        if not authority_evidence or not authority_source:
            raise GuiInputError(
                "authorityEvidence",
                "Provide both the authority evidence and its inspectable source reference.",
            )
        authority_fact_id = "fact-authority-evidence-01"
        facts.append(
            {
                "factId": authority_fact_id,
                "statement": authority_evidence,
                "status": "explicit_fact",
                "sourceType": "documented_record",
                "category": "authority_evidence",
                "sourceReference": authority_source,
            }
        )
        authority_fact_ids.append(authority_fact_id)
    if authority_state in CONFIRMED_AUTHORITY_STATES and not authority_fact_ids:
        raise GuiInputError(
            "authoritySource",
            "Confirmed authority needs an inspectable source. Add the evidence and source, or choose a provisional authority state.",
        )

    authority: dict[str, Any] = {
        "state": authority_state,
        "domainOwners": [],
        "evidenceState": "source_supported" if authority_fact_ids else "user_asserted",
        "evidenceFactIds": authority_fact_ids,
    }
    delivery_owner = _text(payload, "deliveryOwner", maximum=300)
    approval_owner = _text(payload, "finalApprovalOwner", maximum=300)
    if delivery_owner:
        authority["deliveryOwner"] = delivery_owner
    if approval_owner:
        authority["finalApprovalOwner"] = approval_owner

    career_category = _choice(
        payload,
        "careerCategory",
        ALLOWED_CAREER_CATEGORIES,
        default="measurable_result",
    )
    career_lines = _lines(payload, "careerEvidence")
    career_proof = _text(payload, "careerProof", maximum=2_000)
    career_date = _text(payload, "careerDate", maximum=100)
    career_evidence: list[dict[str, Any]] = []
    for index, statement in enumerate(career_lines, start=1):
        item: dict[str, Any] = {
            "evidenceId": f"evidence-gui-{index:02d}",
            "category": career_category,
            "statement": statement,
            "evidenceState": "source_supported" if career_proof else "user_asserted",
        }
        if career_proof:
            item["proofReference"] = career_proof
        if career_date:
            item["occurredAt"] = career_date
        career_evidence.append(item)

    request: dict[str, Any] = {
        "artifactType": "workplace_assistance_request",
        "schemaVersion": 1,
        "requestId": _new_id("assist-request-gui"),
        "mode": mode,
        "createdAt": _utc_now(),
        "purpose": "self_workplace_communication_assistance",
        "situation": {
            "context": context,
            "summary": summary,
            "channel": channel,
            "audience": audience,
            "desiredOutcome": desired_outcome,
        },
        "facts": facts,
        "asks": _lines(payload, "asks", maximum_items=20, maximum_length=2_000),
        "authority": authority,
        "contributors": [],
        "decisions": [
            {
                "decisionId": f"decision-gui-{index:02d}",
                "statement": statement,
                "status": "proposed",
            }
            for index, statement in enumerate(decisions, start=1)
        ],
        "commitments": [
            {
                "commitmentId": f"commitment-gui-{index:02d}",
                "statement": statement,
                "status": "proposed",
            }
            for index, statement in enumerate(commitments, start=1)
        ],
        "unresolvedItems": unresolved_items,
        "careerEvidence": career_evidence,
        "energyState": energy,
        "requestedActions": MODE_ACTIONS[mode],
        "authorization": {
            "automaticSendingAllowed": False,
            "coworkerEvaluationAllowed": False,
            "humanReviewRequired": True,
            "profileBelongsToCurrentUser": True,
        },
    }

    draft_text = _text(payload, "draftText")
    incoming_text = _text(payload, "incomingText")
    intended_ask = _text(payload, "intendedAsk", maximum=3_000)
    recommendation = _text(payload, "recommendation", maximum=5_000)
    if draft_text:
        request["draftText"] = draft_text
    if incoming_text:
        request["incomingText"] = incoming_text
    if intended_ask:
        request["intendedAsk"] = intended_ask
        if not request["asks"]:
            request["asks"] = [intended_ask]
    if recommendation:
        request["recommendation"] = recommendation

    if mode == "preflight" and not request.get("intendedAsk") and not request["asks"]:
        raise GuiInputError("intendedAsk", "Preparing a message or meeting requires a clear ask.")
    if mode == "interpret" and not request.get("incomingText"):
        raise GuiInputError("incomingText", "Paste the message or wording you want to interpret.")
    if mode == "debrief" and not (
        request["facts"]
        or request["decisions"]
        or request["commitments"]
        or request["unresolvedItems"]
    ):
        raise GuiInputError(
            "knownFacts",
            "Add at least one observation, decision, commitment, or unresolved item.",
        )
    if mode == "career_review" and not request["careerEvidence"]:
        raise GuiInputError("careerEvidence", "Add at least one item about your own work or outcome.")
    return request


def _run_assistance(payload: dict[str, Any]) -> dict[str, Any]:
    if not SELF_PROFILE_PATH.is_file():
        raise GuiInputError(
            "selfProfile",
            "The encrypted self-assistance profile is not configured yet. Use the existing Mindfront profile setup before running private assistance.",
        )
    request = _build_assistance_request(payload)
    profile = get_self_assistance_profile(SELF_PROFILE_PATH)
    policy = load_workplace_assistance_policy(POLICY_PATH)
    return finalize_workplace_assistance(
        build_workplace_assistance(request, profile, policy)
    )


def _build_message_brief(payload: dict[str, Any]) -> dict[str, Any]:
    """Translate the audit form into the current message-brief contract."""

    if not isinstance(payload, dict):
        raise GuiInputError("$", "Request must be a JSON object.")
    project_name = (
        _text(payload, "projectName", maximum=300)
        or "Mindfront message and document review"
    )
    message_goal = (
        _text(payload, "messageGoal", maximum=2_000)
        or "Make the material clear, credible, and easy to act on."
    )
    audience = (
        _text(payload, "targetAudience", maximum=2_000)
        or "the intended workplace reader"
    )
    source_text = _text(payload, "primaryText") or _text(payload, "sourceText")
    if not source_text:
        raise GuiInputError(
            "primaryText",
            "Paste the message or document you want Mindfront to review.",
        )
    channel = _choice(
        payload,
        "artifactChannel",
        ALLOWED_ARTIFACT_CHANNELS,
        default="document",
    )
    data_classification = _choice(
        payload,
        "dataClassification",
        ALLOWED_DATA_CLASSIFICATIONS,
        default="internal",
    )
    intent = _choice(
        payload,
        "communicationIntent",
        ALLOWED_COMMUNICATION_INTENTS,
        default="inform",
    )
    archetype = _choice(
        payload,
        "documentArchetype",
        ALLOWED_DOCUMENT_ARCHETYPES,
        default="internal_operational_brief",
    )
    desired_action = _text(payload, "desiredAction", maximum=300) or "understand_next_step"
    constraints = _lines(payload, "constraints", maximum_items=40, maximum_length=3_000)
    unknowns = _lines(payload, "unknowns", maximum_items=40, maximum_length=3_000)
    proof_lines = _lines(payload, "proofAvailable", maximum_items=30, maximum_length=3_000)
    contains_personal = bool(payload.get("containsPersonalData", False))
    contains_confidential = bool(payload.get("containsCustomerConfidentialData", False))

    if not constraints:
        constraints = [
            "Do not present heuristic or synthetic output as user research or market validation.",
            "Preserve uncertainty, human review, and the current evidence boundary.",
        ]
    if not unknowns:
        unknowns = [
            "No real task observation or comprehension study was supplied for this exact audience and context."
        ]

    return {
        "schemaVersion": 1,
        "briefId": _new_id("brief-mindfront-gui"),
        "artifactType": "message_brief",
        "createdAt": date.today().isoformat(),
        "projectName": project_name,
        "messageGoal": message_goal,
        "targetAudience": audience,
        "audienceFamiliarity": "medium",
        "channel": channel,
        "desiredAction": desired_action,
        "sourceText": source_text,
        "proofAvailable": [
            {
                "type": "user_provided_unverified",
                "label": f"User-provided evidence {index}",
                "summary": statement,
            }
            for index, statement in enumerate(proof_lines, start=1)
        ],
        "constraints": constraints,
        "unknowns": unknowns,
        "dataClassification": data_classification,
        "containsPersonalData": contains_personal,
        "containsCustomerConfidentialData": contains_confidential,
        "llmProcessingAllowed": False,
        "retentionPolicy": "private_local_until_deleted",
        "domainContext": "general_b2b",
        "sensitiveDomainFlags": [],
        "expertReviewRequired": False,
        "expertReviewStatus": "not_required",
        "blockedClaimTypes": [],
        "publishReadiness": "not_assessed",
        "documentArchetype": archetype,
        "communicationIntent": intent,
        "decisionRequired": intent == "request_decision",
        "sourceContainsPersonalData": contains_personal,
        "sourceDataSanitized": not contains_personal,
    }


def _powershell_executable() -> str:
    for candidate in ("powershell.exe", "pwsh.exe", "powershell", "pwsh"):
        resolved = shutil.which(candidate)
        if resolved:
            return resolved
    raise WorkflowExecutionError("PowerShell was not found on this machine.")


def _run_artifact_workflow(payload: dict[str, Any]) -> dict[str, Any]:
    brief = _build_message_brief(payload)
    run_id = _new_id("artifact-run")
    run_root = GUI_RUN_ROOT / run_id
    input_root = run_root / "input"
    output_root = run_root / "artifacts"
    input_root.mkdir(parents=True, exist_ok=False)
    brief_path = input_root / "message-brief.json"
    brief_path.write_text(
        json.dumps(brief, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    validation = validate_brief_file(brief_path, strict=True)
    if not validation.ok:
        raise GuiInputError(
            "messageBrief",
            "; ".join(error.message for error in validation.errors[:5]),
        )

    command = [
        _powershell_executable(),
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(WORKFLOW_SCRIPT),
        "-BriefPath",
        str(brief_path),
        "-OutputRoot",
        str(output_root),
        "-Python",
        sys.executable,
    ]
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(REPO_ROOT / "backend" / "src")
    creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
    try:
        completed = subprocess.run(
            command,
            cwd=REPO_ROOT,
            env=environment,
            capture_output=True,
            text=True,
            timeout=ARTIFACT_TIMEOUT_SECONDS,
            check=False,
            creationflags=creation_flags,
        )
    except subprocess.TimeoutExpired as exc:
        raise WorkflowExecutionError(
            "The audit exceeded the local execution time limit.",
            details=str(exc),
        ) from exc

    if completed.returncode != 0:
        details = (completed.stderr or completed.stdout or "").strip()[-4_000:]
        raise WorkflowExecutionError(
            "Mindfront blocked or failed the audit. Review the validation details.",
            details=details,
        )

    report_path = output_root / "report" / "mindfront-audit-report.json"
    if not report_path.is_file():
        raise WorkflowExecutionError(
            "The workflow finished without creating its expected report.",
            details=str(report_path),
        )
    report = json.loads(report_path.read_text(encoding="utf-8"))
    return {
        "status": "completed",
        "runId": run_id,
        "privateLocalRun": True,
        "normalHistoryUpdated": False,
        "briefPath": str(brief_path),
        "runRoot": str(run_root),
        "reportPath": str(report_path),
        "report": report,
        "evidenceBoundary": (
            "This local audit is heuristic and synthetic. It is not user research, "
            "market validation, psychological truth, or proof of comprehension."
        ),
    }


def _bootstrap_payload(csrf_token: str) -> dict[str, Any]:
    return {
        "status": "ready",
        "version": "1.0-rc",
        "localOnly": True,
        "profileAvailable": SELF_PROFILE_PATH.is_file(),
        "artifactWorkflowAvailable": WORKFLOW_SCRIPT.is_file(),
        "csrfToken": csrf_token,
        "privacy": {
            "browserStorageUsed": False,
            "externalRequestsUsed": False,
            "automaticSendingAllowed": False,
            "humanReviewRequired": True,
        },
    }


class MindfrontGuiHandler(BaseHTTPRequestHandler):
    """Serve the local GUI and its two bounded API routes."""

    server_version = "MindfrontLocalGui/1.0"
    csrf_token = ""

    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-store, max-age=0")
        self.send_header("Pragma", "no-cache")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self'; style-src 'self'; "
            "img-src 'self' data:; connect-src 'self'; object-src 'none'; "
            "base-uri 'none'; form-action 'self'; frame-ancestors 'none'",
        )
        super().end_headers()

    def log_message(self, format_string: str, *args: Any) -> None:
        # Never log request bodies. The standard line contains only method/path/status.
        sys.stderr.write(
            f"[mindfront-gui] {self.address_string()} - {format_string % args}\n"
        )

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        parsed = urlparse(self.path)
        if parsed.path == "/api/bootstrap":
            self._send_json(HTTPStatus.OK, _bootstrap_payload(self.csrf_token))
            return
        if parsed.path == "/favicon.ico":
            self.send_response(HTTPStatus.NO_CONTENT)
            self.end_headers()
            return
        static_map = {
            "/": ("index.html", "text/html; charset=utf-8"),
            "/index.html": ("index.html", "text/html; charset=utf-8"),
            "/styles.css": ("styles.css", "text/css; charset=utf-8"),
            "/app.js": ("app.js", "text/javascript; charset=utf-8"),
        }
        target = static_map.get(parsed.path)
        if target is None:
            self._send_json(
                HTTPStatus.NOT_FOUND,
                {"status": "not_found", "message": "Route not found."},
            )
            return
        filename, content_type = target
        path = STATIC_ROOT / filename
        if not path.is_file():
            self._send_json(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                {"status": "error", "message": f"Missing GUI asset: {filename}"},
            )
            return
        body = path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        parsed = urlparse(self.path)
        if parsed.path not in {"/api/assist", "/api/artifact"}:
            self._send_json(
                HTTPStatus.NOT_FOUND,
                {"status": "not_found", "message": "Route not found."},
            )
            return
        if not self._request_is_local():
            self._send_json(
                HTTPStatus.FORBIDDEN,
                {"status": "blocked", "message": "Only same-origin local requests are allowed."},
            )
            return
        if self.headers.get("X-Mindfront-Token", "") != self.csrf_token:
            self._send_json(
                HTTPStatus.FORBIDDEN,
                {"status": "blocked", "message": "The local GUI session token is missing or stale."},
            )
            return
        content_type = self.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
        if content_type != "application/json":
            self._send_json(
                HTTPStatus.UNSUPPORTED_MEDIA_TYPE,
                {"status": "blocked", "message": "Use application/json."},
            )
            return
        try:
            payload = self._read_json_body()
            result = (
                _run_assistance(payload)
                if parsed.path == "/api/assist"
                else _run_artifact_workflow(payload)
            )
            self._send_json(HTTPStatus.OK, {"status": "ok", "result": result})
        except GuiInputError as exc:
            self._send_json(
                HTTPStatus.UNPROCESSABLE_ENTITY,
                {"status": "blocked", "errors": [exc.to_dict()]},
            )
        except WorkplaceAssistanceBlockedError as exc:
            self._send_json(
                HTTPStatus.UNPROCESSABLE_ENTITY,
                {"status": "blocked", "errors": exc.reasons},
            )
        except WorkflowExecutionError as exc:
            self._send_json(
                HTTPStatus.UNPROCESSABLE_ENTITY,
                {
                    "status": "blocked",
                    "errors": [
                        {
                            "code": "workflow_execution_failed",
                            "path": "artifactWorkflow",
                            "message": str(exc),
                            "details": exc.details,
                        }
                    ],
                },
            )
        except (json.JSONDecodeError, UnicodeDecodeError):
            self._send_json(
                HTTPStatus.BAD_REQUEST,
                {"status": "blocked", "message": "The request body is not valid JSON."},
            )
        except Exception as exc:  # pragma: no cover - final boundary
            self._send_json(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                {
                    "status": "error",
                    "message": "The local GUI encountered an unexpected error.",
                    "errorType": type(exc).__name__,
                },
            )

    def _request_is_local(self) -> bool:
        origin = self.headers.get("Origin")
        if not origin:
            return True
        try:
            return urlparse(origin).hostname in {"127.0.0.1", "localhost"}
        except ValueError:
            return False

    def _read_json_body(self) -> dict[str, Any]:
        length_value = self.headers.get("Content-Length")
        if not length_value or not length_value.isdigit():
            raise GuiInputError("$", "A valid Content-Length header is required.")
        length = int(length_value)
        if length <= 0 or length > MAX_BODY_BYTES:
            raise GuiInputError(
                "$",
                f"Request size must be between 1 byte and {MAX_BODY_BYTES:,} bytes.",
            )
        payload = json.loads(self.rfile.read(length).decode("utf-8"))
        if not isinstance(payload, dict):
            raise GuiInputError("$", "Request must be a JSON object.")
        return payload

    def _send_json(self, status: HTTPStatus, payload: dict[str, Any]) -> None:
        body = (
            json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
        ).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def run_server(host: str, port: int, *, open_browser: bool = False) -> None:
    if host not in {"127.0.0.1", "localhost"}:
        raise ValueError("Mindfront GUI only binds to the local loopback interface.")
    if not STATIC_ROOT.is_dir():
        raise FileNotFoundError(f"Mindfront GUI assets not found: {STATIC_ROOT}")
    MindfrontGuiHandler.csrf_token = secrets.token_urlsafe(32)
    server = ThreadingHTTPServer((host, port), MindfrontGuiHandler)
    url = f"http://127.0.0.1:{server.server_port}/"
    print(f"Mindfront GUI is available at {url}")
    print("Local only. Close this window or press Ctrl+C to stop it.")
    if open_browser:
        threading.Timer(0.65, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping Mindfront GUI.")
    finally:
        server.server_close()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run Mindfront's local-only browser GUI."
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--open-browser", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not 1 <= args.port <= 65535:
        raise SystemExit("--port must be between 1 and 65535.")
    run_server(args.host, args.port, open_browser=args.open_browser)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

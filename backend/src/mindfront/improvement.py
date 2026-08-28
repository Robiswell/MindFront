"""Repeat-run improvement planning for Mindfront history data."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from json import JSONDecodeError
from pathlib import Path
from typing import Any

from . import __version__
from .db import StoreBlockedError, compare_analysis_history, fetch_dashboard_data


class ImprovementPlanBlockedError(Exception):
    """Raised when an improvement plan cannot be built."""

    def __init__(self, reasons: list[dict[str, str]]):
        self.reasons = reasons
        super().__init__("Improvement plan operation blocked by input errors.")


CURRENT_STALE_STATES = {"current", "current_at_ingest"}
SEVERITY_WEIGHT = {"low": 1, "medium": 2, "high": 3, "blocked": 4}


def build_improvement_plan(
    db_path: str | Path,
    *,
    brief_id: str | None = None,
    max_actions: int = 10,
) -> dict[str, Any]:
    """Build a ranked next-action backlog from stored Mindfront runs."""

    if max_actions < 1:
        raise ImprovementPlanBlockedError(
            [
                {
                    "code": "invalid_max_actions",
                    "message": "max_actions must be at least 1.",
                    "path": "max_actions",
                }
            ]
        )
    try:
        data = fetch_dashboard_data(db_path)
        comparison = compare_analysis_history(db_path, brief_id=brief_id)
    except StoreBlockedError as exc:
        raise ImprovementPlanBlockedError(exc.reasons) from exc

    runs = [run for run in data["runs"] if brief_id is None or run["brief_id"] == brief_id]
    run_ids = {run["run_id"] for run in runs}
    actions: list[dict[str, Any]] = []
    actions.extend(_stale_actions(runs, data["staleState"]))
    actions.extend(_task_protocol_actions(runs, data["taskValidations"], data["staleState"]))
    actions.extend(_task_validation_actions(data["taskValidations"], run_ids))
    actions.extend(_repeated_failure_actions(comparison.get("repeatedFindings", [])))
    actions.extend(_score_actions(comparison.get("scoreChanges", [])))
    actions.extend(_history_depth_actions(runs, data["taskValidations"], run_ids))

    ranked = _rank_actions(actions, max_actions=max_actions)
    plan = {
        "artifactType": "mindfront_improvement_plan",
        "planId": _plan_id(data["dbPath"], brief_id, ranked),
        "dbPath": data["dbPath"],
        "briefId": brief_id,
        "runCount": len(runs),
        "actionCount": len(ranked),
        "priorityActions": ranked,
        "loopReadiness": _loop_readiness(runs, ranked, data["taskValidations"], run_ids),
        "sourceHistoryComparison": {
            "artifactType": comparison.get("artifactType"),
            "runCount": comparison.get("runCount", 0),
            "simulatedVsValidated": comparison.get("simulatedVsValidated", {}),
            "taskValidationSummary": comparison.get("taskValidationSummary", {}),
        },
        "evidenceBoundary": (
            "Improvement plans rank operational next actions from stored Mindfront artifacts. They do not create "
            "market evidence, prove user preference, predict conversion, or prove company-wide documentation impact. "
            "Real task signals remain exact-context only."
        ),
        "dataBoundary": (
            "Plan inputs are stored summaries, scores, hashes, status fields, task metrics, and artifact paths. "
            "The plan must not include full raw source text, participant identities, raw comments, or transcripts."
        ),
        "marketEvidenceCreated": False,
        "notMarketEvidence": True,
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "toolVersion": __version__,
    }
    return finalize_improvement_plan(plan)


def write_improvement_plan(plan: dict[str, Any], output_path: str | Path) -> list[Path]:
    """Write an improvement plan as JSON and Markdown."""

    payload = finalize_improvement_plan(plan)
    destination = Path(output_path)
    if destination.suffix.lower() == ".json":
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return [destination]
    if destination.suffix.lower() == ".md":
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(render_improvement_plan_markdown(payload), encoding="utf-8")
        return [destination]

    destination.mkdir(parents=True, exist_ok=True)
    json_path = destination / "mindfront-improvement-plan.json"
    markdown_path = destination / "mindfront-improvement-plan.md"
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    markdown_path.write_text(render_improvement_plan_markdown(payload), encoding="utf-8")
    return [json_path, markdown_path]


def finalize_improvement_plan(plan: dict[str, Any]) -> dict[str, Any]:
    """Return an improvement plan with a stable output hash."""

    payload = json.loads(json.dumps(plan))
    payload["outputHash"] = "sha256:pending-until-written"
    provisional = json.dumps(payload, indent=2, sort_keys=True)
    payload["outputHash"] = f"sha256:{_hash_text(provisional)}"
    return payload


def render_improvement_plan_markdown(plan: dict[str, Any]) -> str:
    """Render a human-readable improvement backlog."""

    lines = [
        "# Mindfront Improvement Plan",
        "",
        f"Plan: `{plan['planId']}`",
        f"Runs analyzed: {plan['runCount']}",
        f"Loop state: {plan['loopReadiness']['state']}",
        "",
        "## Evidence Boundary",
        "",
        plan["evidenceBoundary"],
        "",
        "## Priority Actions",
        "",
    ]
    if not plan["priorityActions"]:
        lines.append("- No ranked actions. Run more Mindfront passes or add task evidence before treating the loop as mature.")
    for action in plan["priorityActions"]:
        lines.extend(
            [
                f"- P{action['priority']} `{action['actionType']}`: {action['title']}",
                f"  Action: {action['recommendedAction']}",
                f"  Boundary: {action['evidenceBoundary']}",
            ]
        )
    lines.extend(
        [
            "",
            "## Loop Readiness",
            "",
            plan["loopReadiness"]["interpretation"],
        ]
    )
    return "\n".join(lines) + "\n"


def _stale_actions(runs: list[dict[str, Any]], stale_state: list[dict[str, Any]]) -> list[dict[str, Any]]:
    stale_by_run = {item["run_id"]: item for item in stale_state}
    actions = []
    for run in runs:
        state = stale_by_run.get(run["run_id"], {}).get("state", "unknown")
        if state in CURRENT_STALE_STATES:
            continue
        actions.append(
            _action(
                "refresh_stale_run",
                96 if state == "stale" else 72,
                f"Refresh stored artifacts for {run['brief_id']}",
                (
                    "Run store check-stale, regenerate the affected Mindfront workflow artifacts, and ingest the "
                    "fresh run before using history trends."
                ),
                [run["run_id"]],
                {"staleState": state, "briefId": run["brief_id"]},
            )
        )
    return actions


def _task_protocol_actions(
    runs: list[dict[str, Any]],
    validations: list[dict[str, Any]],
    stale_state: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    real_evidence_runs = {
        item["run_id"]
        for item in validations
        if int(item.get("real_task_evidence_created", 0)) == 1
    }
    stale_by_run = {item["run_id"]: item for item in stale_state}
    actions = []
    for run in runs:
        artifact_paths = json.loads(run["artifact_paths_json"])
        artifact_types = sorted(artifact_paths.keys())
        protocol_path = artifact_paths.get("task_protocol")
        state = stale_by_run.get(run["run_id"], {}).get("state", run.get("staleState", "unknown"))
        protocol_status = _protocol_collection_status(protocol_path) if protocol_path else None
        if (
            protocol_path
            and state in CURRENT_STALE_STATES
            and protocol_status
            and protocol_status["readyForCollection"]
            and run["run_id"] not in real_evidence_runs
        ):
            actions.append(
                _action(
                    "collect_task_sessions_from_protocol",
                    90,
                    f"Use the task-observation protocol for {run['brief_id']}",
                    (
                        "Collect no-PII task sessions with the generated CSV template, convert them with task-input, "
                        "then run task-validation before presenting exact-context directional task findings."
                    ),
                    [run["run_id"]],
                    {
                        "briefId": run["brief_id"],
                        "artifactTypes": artifact_types,
                        "protocolStatus": protocol_status,
                    },
                )
            )
    return actions


def _task_validation_actions(validations: list[dict[str, Any]], run_ids: set[str]) -> list[dict[str, Any]]:
    actions = []
    for validation in validations:
        if validation["run_id"] not in run_ids:
            continue
        if int(validation.get("real_task_evidence_created", 0)) != 1:
            continue
        friction = _task_friction_signals(validation)
        if not friction:
            continue
        priority = max(item["priority"] for item in friction)
        actions.append(
            _action(
                "reduce_documentation_task_friction",
                priority,
                f"Reduce observed task friction in {validation['validation_result_id']}",
                (
                    "Revise the document around the listed task friction signals, rerun the same task protocol, "
                    "and compare the next exact-context result before broadening claims."
                ),
                [validation["run_id"]],
                {
                    "validationResultId": validation["validation_result_id"],
                    "evidenceBasis": validation["evidence_basis"],
                    "evidenceGrade": validation.get("evidence_grade", "unknown"),
                    "frictionSignals": friction,
                },
            )
        )
    return actions


def _repeated_failure_actions(repeated_findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    actions = []
    for finding in repeated_findings:
        severity = finding.get("maxSeverity", "medium")
        count = int(finding.get("count", 0))
        if count < 2:
            continue
        priority = min(88, 45 + (SEVERITY_WEIGHT.get(severity, 2) * 9) + (min(count, 3) * 5))
        actions.append(
            _action(
                "fix_repeated_message_failure",
                priority,
                f"Fix repeated {finding['dimensionId']} issue",
                (
                    "Address this finding in the next rewrite before expanding variants; if the issue depends on "
                    "proof, keep claims gated until source evidence or expert review exists."
                ),
                finding.get("runIds", []),
                {
                    "dimensionId": finding["dimensionId"],
                    "issue": finding["issue"],
                    "count": count,
                    "maxSeverity": severity,
                    "evidenceBases": finding.get("evidenceBases", []),
                },
            )
        )
    return actions


def _score_actions(score_changes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    actions = []
    for score in score_changes:
        last_score = int(score.get("lastScore", 0))
        delta = int(score.get("delta", 0))
        if last_score > 3 and delta >= 0:
            continue
        priority = min(84, 54 + max(0, 4 - last_score) * 7 + max(0, -delta) * 6)
        actions.append(
            _action(
                "raise_low_or_regressed_dimension",
                priority,
                f"Improve {score['dimensionId']} score before the next report",
                (
                    "Use the latest analysis findings and rewrite variants to raise this dimension, then store "
                    "another run so the history comparison can confirm the direction."
                ),
                [score["firstRunId"], score["lastRunId"]],
                {
                    "dimensionId": score["dimensionId"],
                    "firstScore": score["firstScore"],
                    "lastScore": score["lastScore"],
                    "delta": delta,
                    "runCount": score["runCount"],
                },
            )
        )
    return actions


def _history_depth_actions(
    runs: list[dict[str, Any]],
    validations: list[dict[str, Any]],
    run_ids: set[str],
) -> list[dict[str, Any]]:
    actions = []
    real_task_count = sum(
        1
        for item in validations
        if item["run_id"] in run_ids and int(item.get("real_task_evidence_created", 0)) == 1
    )
    if not runs:
        actions.append(
            _action(
                "run_first_mindfront_pass",
                80,
                "Create the first stored Mindfront run",
                "Run the full Mindfront workflow with a DB path so future passes have a baseline to compare.",
                [],
                {},
            )
        )
        return actions
    if len(runs) < 2:
        actions.append(
            _action(
                "create_second_history_point",
                70,
                "Create a second stored run after revision",
                (
                    "Revise against the top backlog item, rerun the workflow, and store the next run so the loop can "
                    "measure direction instead of a one-run snapshot."
                ),
                [runs[-1]["run_id"]],
                {"runCount": len(runs)},
            )
        )
    if real_task_count == 0:
        has_protocol = any("task_protocol" in json.loads(run["artifact_paths_json"]) for run in runs)
        action_type = "collect_first_real_task_validation" if has_protocol else "generate_task_observation_protocol"
        recommended = (
            "Collect no-PII task sessions from the existing protocol and run task-validation."
            if has_protocol
            else "Generate a task-observation protocol, then collect no-PII sessions before presenting directional task findings."
        )
        actions.append(
            _action(
                action_type,
                86 if has_protocol else 74,
                "Add exact-context task evidence to the loop",
                recommended,
                [run["run_id"] for run in runs],
                {"realTaskEvidenceRunCount": real_task_count, "hasProtocol": has_protocol},
            )
        )
    return actions


def _task_friction_signals(validation: dict[str, Any]) -> list[dict[str, Any]]:
    signals = []
    completion_rate = float(validation["completion_rate"])
    median_seconds = float(validation["median_skim_to_answer_seconds"])
    followups = float(validation["average_follow_up_question_count"])
    respect = float(validation["average_expert_respect_rating"])
    reuse = float(validation["average_reuse_intent_rating"])
    objections = int(validation["trust_objection_count"])
    if completion_rate < 0.85:
        signals.append({"metric": "completionRate", "value": completion_rate, "target": ">= 0.85", "priority": 88})
    if median_seconds > 60:
        signals.append(
            {"metric": "medianSkimToAnswerSeconds", "value": median_seconds, "target": "<= 60", "priority": 82}
        )
    if followups > 1:
        signals.append({"metric": "averageFollowUpQuestionCount", "value": followups, "target": "<= 1", "priority": 78})
    if objections > 0:
        signals.append({"metric": "trustObjectionCount", "value": objections, "target": "0", "priority": 76})
    if respect < 4:
        signals.append({"metric": "averageExpertRespectRating", "value": respect, "target": ">= 4", "priority": 74})
    if reuse < 4:
        signals.append({"metric": "averageReuseIntentRating", "value": reuse, "target": ">= 4", "priority": 74})
    return signals


def _loop_readiness(
    runs: list[dict[str, Any]],
    actions: list[dict[str, Any]],
    validations: list[dict[str, Any]],
    run_ids: set[str],
) -> dict[str, Any]:
    real_task_count = sum(
        1
        for item in validations
        if item["run_id"] in run_ids and int(item.get("real_task_evidence_created", 0)) == 1
    )
    blocking = []
    if not runs:
        blocking.append("no_stored_runs")
    if len(runs) < 2:
        blocking.append("insufficient_repeat_history")
    if real_task_count == 0:
        blocking.append("no_real_task_validation")
    if any(action["actionType"] == "refresh_stale_run" for action in actions):
        blocking.append("stale_artifacts")
    if not blocking:
        state = "ready_for_next_revision_loop"
        interpretation = (
            "Mindfront has enough stored history and real task evidence to guide the next documentation pass, "
            "while still staying inside exact-context evidence limits."
        )
    else:
        state = "needs_loop_inputs"
        interpretation = (
            "Mindfront can rank next actions, but the loop needs the listed inputs before it can support stronger "
            "repeat-run conclusions."
        )
    return {
        "state": state,
        "canGuideNextCodexPass": bool(actions),
        "blockingGaps": blocking,
        "realTaskEvidenceRunCount": real_task_count,
        "interpretation": interpretation,
    }


def _rank_actions(actions: list[dict[str, Any]], *, max_actions: int) -> list[dict[str, Any]]:
    unique: dict[tuple[str, str], dict[str, Any]] = {}
    for action in actions:
        key = (action["actionType"], action["title"])
        current = unique.get(key)
        if current is None or action["priority"] > current["priority"]:
            unique[key] = action
    ranked = sorted(unique.values(), key=lambda item: (-int(item["priority"]), item["actionType"], item["title"]))
    for index, action in enumerate(ranked[:max_actions], start=1):
        action["rank"] = index
        action["actionId"] = f"improvement-action-{index:03d}"
    return ranked[:max_actions]


def _action(
    action_type: str,
    priority: int,
    title: str,
    recommended_action: str,
    source_run_ids: list[str],
    details: dict[str, Any],
) -> dict[str, Any]:
    return {
        "actionId": "pending-rank",
        "rank": 0,
        "actionType": action_type,
        "priority": int(max(1, min(100, priority))),
        "title": title,
        "recommendedAction": recommended_action,
        "sourceRunIds": sorted({run_id for run_id in source_run_ids if run_id}),
        "details": details,
        "evidenceBoundary": (
            "Operational planning only; this action does not create market evidence, validated user preference, "
            "conversion proof, adoption proof, company-wide performance proof, or C-suite impact proof."
        ),
    }


def _protocol_collection_status(protocol_path: str | None) -> dict[str, Any]:
    if not protocol_path:
        return {
            "readStatus": "missing",
            "readyForCollection": False,
            "reason": "No task protocol artifact path was stored.",
        }
    path = Path(protocol_path)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, JSONDecodeError, UnicodeDecodeError):
        return {
            "readStatus": "unreadable",
            "readyForCollection": False,
            "reason": "Task protocol artifact could not be read as JSON.",
        }
    if not isinstance(data, dict) or data.get("artifactType") != "documentation_task_observation_protocol":
        return {
            "readStatus": "invalid_artifact",
            "readyForCollection": False,
            "reason": "Task protocol artifact is missing the expected artifact type.",
        }
    if data.get("marketEvidenceCreated") is not False or data.get("notMarketEvidence") is not True:
        return {
            "readStatus": "evidence_boundary_invalid",
            "readyForCollection": False,
            "reason": "Task protocol artifact does not preserve the no-market-evidence boundary.",
        }
    tasks = data.get("tasks")
    if not isinstance(tasks, list) or not tasks:
        return {
            "readStatus": "missing_tasks",
            "readyForCollection": False,
            "reason": "Task protocol artifact does not include runnable tasks.",
        }
    return {
        "readStatus": "read",
        "readyForCollection": True,
        "protocolId": data.get("protocolId", "unknown_protocol"),
        "taskCount": len(tasks),
        "marketEvidenceCreated": data.get("marketEvidenceCreated"),
        "notMarketEvidence": data.get("notMarketEvidence"),
    }


def _plan_id(db_path: str, brief_id: str | None, actions: list[dict[str, Any]]) -> str:
    basis = json.dumps(
        {
            "dbPath": db_path,
            "briefId": brief_id,
            "actions": [
                {"actionType": action["actionType"], "title": action["title"], "priority": action["priority"]}
                for action in actions
            ],
        },
        sort_keys=True,
    )
    return f"improvement-plan-{_hash_text(basis)[:12]}"


def _hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()

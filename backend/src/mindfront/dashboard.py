"""Static local dashboard rendering for Mindfront history data."""

from __future__ import annotations

import html
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import __version__
from .db import compare_analysis_history, fetch_dashboard_data
from .improvement import build_improvement_plan


def build_static_dashboard(db_path: str | Path, output_path: str | Path) -> list[Path]:
    """Build a static dashboard JSON payload and editable HTML page."""

    destination = Path(output_path)
    destination.mkdir(parents=True, exist_ok=True)
    data = fetch_dashboard_data(db_path)
    comparison = compare_analysis_history(db_path)
    improvement_plan = build_improvement_plan(db_path)
    payload = _dashboard_payload(data, comparison, improvement_plan)
    json_path = destination / "mindfront-dashboard.json"
    html_path = destination / "index.html"
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    html_path.write_text(render_dashboard_html(payload), encoding="utf-8")
    return [json_path, html_path]


def render_dashboard_html(payload: dict[str, Any]) -> str:
    """Render dashboard payload into a static HTML file."""

    def esc(value: object) -> str:
        return html.escape(str(value), quote=True)

    run_rows = "".join(
        "<tr>"
        f"<td><code>{esc(run['runId'])}</code></td>"
        f"<td>{esc(run['briefId'])}</td>"
        f"<td>{esc(run['validationState'])}</td>"
        f"<td>{esc(run['sensitiveDomainState'])}</td>"
        f"<td>{esc(run['simulatedResultCount'])}</td>"
        f"<td>{esc(run['validatedSignalCount'])}</td>"
        f"<td>{esc(run['taskValidationSignalCount'])}</td>"
        f"<td>{esc(run['staleState'])}</td>"
        "</tr>"
        for run in payload["runs"]
    )
    score_rows = "".join(
        "<tr>"
        f"<td>{esc(item['dimensionId'])}</td>"
        f"<td>{esc(item['firstScore'])}</td>"
        f"<td>{esc(item['lastScore'])}</td>"
        f"<td>{esc(item['delta'])}</td>"
        f"<td>{esc(item['runCount'])}</td>"
        "</tr>"
        for item in payload["scoreChanges"]
    )
    failure_rows = "".join(
        "<tr>"
        f"<td>{esc(item['dimensionId'])}</td>"
        f"<td>{esc(item['count'])}</td>"
        f"<td>{esc(item['maxSeverity'])}</td>"
        f"<td>{esc(item['issue'])}</td>"
        f"<td>{esc(', '.join(item['evidenceBases']))}</td>"
        "</tr>"
        for item in payload["repeatedFailures"]
    )
    evidence_rows = "".join(
        "<tr>"
        f"<td>{esc(item['label'])}</td>"
        f"<td>{esc(item['count'])}</td>"
        f"<td>{esc(item['interpretation'])}</td>"
        "</tr>"
        for item in payload["evidenceSeparation"]
    )
    validation_rows = "".join(
        "<tr>"
        f"<td><code>{esc(item['validationResultId'])}</code></td>"
        f"<td>{esc(item['briefId'])}</td>"
        f"<td>{esc(item['observationSource'])}</td>"
        f"<td>{esc(item['evidenceBasis'])}</td>"
        f"<td>{esc(item['evidenceGrade'])}</td>"
        f"<td>{esc(item['realTaskEvidenceCreated'])}</td>"
        f"<td>{esc(item['decisionState'])}</td>"
        f"<td>{esc(item['participantCount'])}</td>"
        f"<td>{esc(item['completionRate'])}</td>"
        f"<td>{esc(item['medianSkimToAnswerSeconds'])}</td>"
        f"<td>{esc(item['averageExpertRespectRating'])}</td>"
        "</tr>"
        for item in payload["taskValidations"]
    )
    if not validation_rows:
        validation_rows = '<tr><td colspan="11">No task-validation evidence stored.</td></tr>'
    protocol_rows = "".join(
        "<tr>"
        f"<td><code>{esc(item['protocolId'])}</code></td>"
        f"<td>{esc(item['briefId'])}</td>"
        f"<td>{esc(item['taskCount'])}</td>"
        f"<td>{esc(item['marketEvidenceCreated'])}</td>"
        f"<td>{esc(item['notMarketEvidence'])}</td>"
        f"<td>{esc(item['readStatus'])}</td>"
        f"<td>{esc(item['artifactPath'])}</td>"
        f"<td>{esc(item['interpretation'])}</td>"
        "</tr>"
        for item in payload["taskProtocols"]
    )
    if not protocol_rows:
        protocol_rows = '<tr><td colspan="8">No task-observation protocols stored.</td></tr>'
    improvement_rows = "".join(
        "<tr>"
        f"<td>{esc(item['rank'])}</td>"
        f"<td>{esc(item['priority'])}</td>"
        f"<td>{esc(item['actionType'])}</td>"
        f"<td>{esc(item['title'])}</td>"
        f"<td>{esc(item['recommendedAction'])}</td>"
        f"<td>{esc(item['evidenceBoundary'])}</td>"
        "</tr>"
        for item in payload["improvementPlan"]["priorityActions"]
    )
    if not improvement_rows:
        improvement_rows = '<tr><td colspan="6">No ranked improvement actions.</td></tr>'
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Mindfront Local Dashboard</title>
  <style>
    :root {{ --ink: #1b1f24; --muted: #57606a; --line: #d0d7de; --panel: #ffffff; --bg: #f6f8fa; --accent: #0f766e; }}
    body {{ margin: 0; font-family: Arial, Helvetica, sans-serif; background: var(--bg); color: var(--ink); line-height: 1.45; }}
    main {{ max-width: 1120px; margin: 0 auto; padding: 34px 24px 64px; }}
    h1 {{ margin: 0 0 8px; font-size: 32px; letter-spacing: 0; }}
    h2 {{ font-size: 18px; margin: 30px 0 12px; }}
    .meta {{ color: var(--muted); margin: 0 0 20px; }}
    .cards {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 10px; }}
    .card {{ background: var(--panel); border: 1px solid var(--line); border-radius: 6px; padding: 14px; }}
    .card strong {{ display: block; font-size: 24px; }}
    .boundary {{ background: #eef7f5; border-left: 4px solid var(--accent); padding: 12px 14px; margin: 16px 0; }}
    table {{ width: 100%; border-collapse: collapse; background: var(--panel); }}
    th, td {{ border: 1px solid var(--line); padding: 8px; text-align: left; vertical-align: top; font-size: 13px; }}
    th {{ background: #f0f3f6; }}
    code {{ font-family: Consolas, monospace; font-size: 12px; }}
  </style>
</head>
<body>
<main>
  <h1>Mindfront Local Dashboard</h1>
  <p class="meta">Generated {esc(payload['generatedAt'])} from <code>{esc(payload['dbPath'])}</code></p>
  <p class="boundary">{esc(payload['evidenceBoundary'])}</p>
  <section class="cards">
    <div class="card"><span>Runs</span><strong>{esc(payload['summary']['runCount'])}</strong></div>
    <div class="card"><span>Briefs</span><strong>{esc(payload['summary']['briefCount'])}</strong></div>
    <div class="card"><span>Simulated Results</span><strong>{esc(payload['summary']['simulatedResultCount'])}</strong></div>
    <div class="card"><span>Validated Analysis Signals</span><strong>{esc(payload['summary']['validatedSignalCount'])}</strong></div>
    <div class="card"><span>Exact-Context Task Signals</span><strong>{esc(payload['summary']['taskValidationSignalCount'])}</strong></div>
    <div class="card"><span>Task Observation Protocols</span><strong>{esc(payload['summary']['taskProtocolCount'])}</strong></div>
    <div class="card"><span>Task Validation Runs</span><strong>{esc(payload['summary']['taskValidationRunCount'])}</strong></div>
  </section>

  <h2>Analysis History</h2>
  <table>
    <thead><tr><th>Run</th><th>Brief</th><th>Validation</th><th>Sensitive Domain</th><th>Simulated</th><th>Validated Analysis</th><th>Task Signals</th><th>Stale</th></tr></thead>
    <tbody>{run_rows}</tbody>
  </table>

  <h2>Score Changes</h2>
  <table>
    <thead><tr><th>Dimension</th><th>First</th><th>Latest</th><th>Delta</th><th>Runs</th></tr></thead>
    <tbody>{score_rows}</tbody>
  </table>

  <h2>Repeated Message Failures</h2>
  <table>
    <thead><tr><th>Dimension</th><th>Count</th><th>Max Severity</th><th>Issue</th><th>Evidence</th></tr></thead>
    <tbody>{failure_rows}</tbody>
  </table>

  <h2>Simulated Versus Validated</h2>
  <table>
    <thead><tr><th>Type</th><th>Count</th><th>Interpretation</th></tr></thead>
    <tbody>{evidence_rows}</tbody>
  </table>

  <h2>Task Validation Evidence</h2>
  <table>
    <thead><tr><th>Validation</th><th>Brief</th><th>Source</th><th>Evidence</th><th>Grade</th><th>Real Evidence</th><th>Decision</th><th>Participants</th><th>Completion</th><th>Median Seconds</th><th>Respect</th></tr></thead>
    <tbody>{validation_rows}</tbody>
  </table>

  <h2>Task Observation Protocols</h2>
  <table>
    <thead><tr><th>Protocol</th><th>Brief</th><th>Tasks</th><th>Market Evidence</th><th>Not Market Evidence</th><th>Status</th><th>Artifact</th><th>Interpretation</th></tr></thead>
    <tbody>{protocol_rows}</tbody>
  </table>

  <h2>Next Improvement Actions</h2>
  <table>
    <thead><tr><th>Rank</th><th>Priority</th><th>Type</th><th>Title</th><th>Action</th><th>Boundary</th></tr></thead>
    <tbody>{improvement_rows}</tbody>
  </table>
</main>
</body>
</html>
"""


def _dashboard_payload(
    data: dict[str, Any],
    comparison: dict[str, Any],
    improvement_plan: dict[str, Any],
) -> dict[str, Any]:
    stale_by_run = {item["run_id"]: item for item in data["staleState"]}
    runs = []
    for run in data["runs"]:
        runs.append(
            {
                "runId": run["run_id"],
                "briefId": run["brief_id"],
                "summary": run["summary"],
                "validationState": run["validation_state"],
                "sensitiveDomainState": run["sensitive_domain_state"],
                "sourceTextHash": run["source_text_hash"],
                "configSetHash": run["config_set_hash"],
                "simulatedResultCount": run["simulated_result_count"],
                "validatedSignalCount": run["validated_signal_count"],
                "taskValidationSignalCount": run["task_validation_signal_count"],
                "staleState": stale_by_run.get(run["run_id"], {}).get("state", "unknown"),
                "generatedAt": run["generated_at"],
                "storedAt": run["stored_at"],
                "artifactTypes": sorted(json.loads(run["artifact_paths_json"]).keys()),
            }
        )
    task_protocols = _task_protocols(data["runs"])
    summary = {
        "runCount": len(runs),
        "briefCount": len({run["briefId"] for run in runs}),
        "simulatedResultCount": sum(run["simulatedResultCount"] for run in runs),
        "validatedSignalCount": sum(run["validatedSignalCount"] for run in runs),
        "taskValidationSignalCount": sum(run["taskValidationSignalCount"] for run in runs),
        "taskProtocolCount": len(task_protocols),
        "taskValidationRunCount": len(data["taskValidations"]),
    }
    task_validations = _task_validations(data["taskValidations"], data["runs"])
    return {
        "artifactType": "static_dashboard_bundle",
        "dashboardId": "mindfront-static-dashboard",
        "dbPath": data["dbPath"],
        "schemaVersion": data["schemaVersion"],
        "summary": summary,
        "runs": runs,
        "scoreChanges": comparison["scoreChanges"],
        "repeatedFailures": comparison["repeatedFindings"],
        "taskProtocols": task_protocols,
        "taskValidations": task_validations,
        "taskValidationSummary": comparison.get("taskValidationSummary", {}),
        "improvementPlan": {
            "planId": improvement_plan["planId"],
            "actionCount": improvement_plan["actionCount"],
            "loopReadiness": improvement_plan["loopReadiness"],
            "priorityActions": improvement_plan["priorityActions"],
            "evidenceBoundary": improvement_plan["evidenceBoundary"],
            "marketEvidenceCreated": improvement_plan["marketEvidenceCreated"],
            "notMarketEvidence": improvement_plan["notMarketEvidence"],
        },
        "evidenceSeparation": [
            {
                "label": "simulated_reader_stress_test",
                "count": summary["simulatedResultCount"],
                "interpretation": "Simulated findings are hypotheses to test, not validated user evidence.",
            },
            {
                "label": "validated_signals",
                "count": summary["validatedSignalCount"],
                "interpretation": "Validated analysis signals require small-user-test, real-user-data, or expert-review evidence basis in analysis artifacts.",
            },
            {
                "label": "exact_context_task_signals",
                "count": summary["taskValidationSignalCount"],
                "interpretation": "Task-validation signals are exact-context documentation-task evidence and are not market, adoption, or company-wide performance proof.",
            },
            {
                "label": "documentation_task_observation_protocol",
                "count": summary["taskProtocolCount"],
                "interpretation": "Task-observation protocols are no-PII evidence-collection handoffs; they are not evidence until sessions are collected.",
            },
            {
                "label": "documentation_task_validation",
                "count": summary["taskValidationRunCount"],
                "interpretation": "Real task validation is exact-context directional evidence; synthetic task fixtures verify workflow behavior only.",
            },
            {
                "label": "mindfront_improvement_plan",
                "count": improvement_plan["actionCount"],
                "interpretation": "Improvement actions are operational backlog items, not market evidence or proof of impact.",
            },
        ],
        "evidenceBoundary": (
            "Dashboard cards separate heuristic, simulated, protocol handoff, and exact-context task evidence; "
            "dashboard display never upgrades confidence or market proof."
        ),
        "marketEvidenceCreated": False,
        "notMarketEvidence": True,
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "toolVersion": __version__,
    }


def _task_validations(validations: list[dict[str, Any]], runs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    run_by_id = {run["run_id"]: run for run in runs}
    rows = []
    for validation in validations:
        run = run_by_id.get(validation["run_id"], {})
        rows.append(
            {
                "runId": validation["run_id"],
                "briefId": run.get("brief_id", "unknown"),
                "validationResultId": validation["validation_result_id"],
                "observationSource": validation.get("observation_source", "unknown"),
                "evidenceBasis": validation["evidence_basis"],
                "evidenceGrade": validation.get("evidence_grade", "unknown"),
                "realTaskEvidenceCreated": bool(validation.get("real_task_evidence_created")),
                "decisionState": validation["decision_state"],
                "participantCount": validation["participant_count"],
                "taskAttemptCount": validation["task_attempt_count"],
                "completionRate": validation["completion_rate"],
                "medianSkimToAnswerSeconds": validation["median_skim_to_answer_seconds"],
                "averageFollowUpQuestionCount": validation["average_follow_up_question_count"],
                "averageExpertRespectRating": validation["average_expert_respect_rating"],
                "averageReuseIntentRating": validation["average_reuse_intent_rating"],
                "trustObjectionCount": validation["trust_objection_count"],
            }
        )
    return rows


def _task_protocols(runs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for run in runs:
        artifact_paths = json.loads(run["artifact_paths_json"])
        protocol_path = artifact_paths.get("task_protocol")
        if not protocol_path:
            continue
        metadata = _read_protocol_metadata(protocol_path)
        rows.append(
            {
                "runId": run["run_id"],
                "briefId": run["brief_id"],
                "artifactPath": protocol_path,
                "protocolId": metadata["protocolId"],
                "taskCount": metadata["taskCount"],
                "marketEvidenceCreated": metadata["marketEvidenceCreated"],
                "notMarketEvidence": metadata["notMarketEvidence"],
                "readStatus": metadata["readStatus"],
                "interpretation": (
                    "No-PII task-observation protocol stored as a collection handoff; not market evidence or "
                    "documentation-performance proof by itself."
                ),
            }
        )
    return rows


def _read_protocol_metadata(protocol_path: str) -> dict[str, Any]:
    path = Path(protocol_path)
    fallback = {
        "protocolId": "unreadable_protocol",
        "taskCount": 0,
        "marketEvidenceCreated": "unknown",
        "notMarketEvidence": "unknown",
        "readStatus": "unreadable",
    }
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return fallback
    if not isinstance(data, dict) or data.get("artifactType") != "documentation_task_observation_protocol":
        fallback["readStatus"] = "invalid_artifact"
        return fallback
    tasks = data.get("tasks", [])
    return {
        "protocolId": data.get("protocolId", "unknown_protocol"),
        "taskCount": len(tasks) if isinstance(tasks, list) else 0,
        "marketEvidenceCreated": data.get("marketEvidenceCreated", False),
        "notMarketEvidence": data.get("notMarketEvidence", True),
        "readStatus": "read",
    }

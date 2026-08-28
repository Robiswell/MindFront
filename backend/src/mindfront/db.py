"""SQLite history store for Mindfront audit artifacts."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from json import JSONDecodeError
from pathlib import Path
from statistics import median
from typing import Any

from . import __version__
from .impact import task_validation_result_errors


class StoreBlockedError(Exception):
    """Raised when artifacts cannot be stored."""

    def __init__(self, reasons: list[dict[str, str]]):
        self.reasons = reasons
        super().__init__("History store operation blocked by input errors.")


EXPECTED_TYPES = {
    "analysis": "message_analysis_report",
    "variants": "copy_variant_bundle",
    "comparison": "variant_comparison_report",
    "stress": "reader_stress_test_report",
    "research": "research_plan",
    "report": "audit_report_bundle",
    "task_protocol": "documentation_task_observation_protocol",
    "task_validation": "documentation_task_validation_result",
}

VALIDATED_EVIDENCE_BASES = {"real_user_data", "expert_review", "small_user_test"}
SCHEMA_VERSION = "2"


def store_artifact_set(
    db_path: str | Path,
    *,
    analysis_path: str | Path,
    variants_path: str | Path | None = None,
    comparison_path: str | Path | None = None,
    stress_path: str | Path | None = None,
    research_plan_path: str | Path | None = None,
    report_path: str | Path | None = None,
    task_protocol_path: str | Path | None = None,
    task_validation_path: str | Path | None = None,
) -> dict[str, Any]:
    """Store a validated artifact set in SQLite and return a run manifest."""

    db_file = Path(db_path)
    artifacts = _load_artifacts(
        analysis_path=analysis_path,
        variants_path=variants_path,
        comparison_path=comparison_path,
        stress_path=stress_path,
        research_plan_path=research_plan_path,
        report_path=report_path,
        task_protocol_path=task_protocol_path,
        task_validation_path=task_validation_path,
    )
    _validate_cross_refs(artifacts)
    db_file.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(db_file)) as connection:
        connection.row_factory = sqlite3.Row
        initialize_store(connection)
        _upsert_artifacts(connection, artifacts)
        connection.commit()
        run_count = connection.execute("SELECT COUNT(*) AS count FROM runs").fetchone()["count"]

    analysis = artifacts["analysis"]["data"]
    return {
        "artifactType": "history_store_result",
        "storeResultId": f"store-result-{_hash_text(str(db_file) + analysis['reportId'])[:12]}",
        "dbPath": str(db_file),
        "storedRunId": analysis["reportId"],
        "briefId": analysis.get("briefId", "unknown"),
        "runCount": run_count,
        "storedArtifactTypes": [name for name, artifact in artifacts.items() if artifact is not None],
        "marketEvidenceCreated": False,
        "notMarketEvidence": True,
        "rawSourceTextStored": False,
        "dataBoundary": (
            "SQLite stores artifact ids, hashes, summaries, excerpts, scores, status fields, and task-protocol "
            "artifact paths; it does not store full raw source text, participant identities, raw comments, or transcripts."
        ),
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "toolVersion": __version__,
    }


def initialize_store(connection: sqlite3.Connection) -> None:
    """Create or migrate the Mindfront SQLite schema."""

    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS schema_meta (
          key TEXT PRIMARY KEY,
          value TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS runs (
          run_id TEXT PRIMARY KEY,
          brief_id TEXT NOT NULL,
          summary TEXT NOT NULL,
          validation_state TEXT NOT NULL,
          sensitive_domain_state TEXT NOT NULL,
          data_classification TEXT NOT NULL,
          source_text_hash TEXT NOT NULL,
          source_brief_hash TEXT NOT NULL,
          config_set_hash TEXT NOT NULL,
          generated_at TEXT NOT NULL,
          stored_at TEXT NOT NULL,
          artifact_paths_json TEXT NOT NULL,
          artifact_hashes_json TEXT NOT NULL,
          market_evidence_created INTEGER NOT NULL,
          simulated_result_count INTEGER NOT NULL,
          validated_signal_count INTEGER NOT NULL,
          task_validation_signal_count INTEGER NOT NULL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS scores (
          run_id TEXT NOT NULL,
          dimension_id TEXT NOT NULL,
          score INTEGER NOT NULL,
          score_scale TEXT NOT NULL,
          score_reason TEXT NOT NULL,
          evidence_basis TEXT NOT NULL,
          finding_confidence TEXT NOT NULL,
          PRIMARY KEY (run_id, dimension_id),
          FOREIGN KEY (run_id) REFERENCES runs(run_id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS findings (
          run_id TEXT NOT NULL,
          finding_id TEXT NOT NULL,
          dimension_id TEXT NOT NULL,
          severity TEXT NOT NULL,
          issue TEXT NOT NULL,
          evidence_basis TEXT NOT NULL,
          finding_confidence TEXT NOT NULL,
          recommended_validation TEXT NOT NULL,
          claim_ids_json TEXT NOT NULL,
          PRIMARY KEY (run_id, finding_id),
          FOREIGN KEY (run_id) REFERENCES runs(run_id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS claims (
          run_id TEXT NOT NULL,
          claim_id TEXT NOT NULL,
          claim_type TEXT NOT NULL,
          claim_strength TEXT NOT NULL,
          support_status TEXT NOT NULL,
          evidence_basis TEXT NOT NULL,
          claim_excerpt TEXT NOT NULL,
          claim_hash TEXT NOT NULL,
          PRIMARY KEY (run_id, claim_id),
          FOREIGN KEY (run_id) REFERENCES runs(run_id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS variants (
          run_id TEXT NOT NULL,
          variant_id TEXT NOT NULL,
          strategy_id TEXT NOT NULL,
          recommendation_state TEXT NOT NULL,
          claim_gate_status TEXT NOT NULL,
          copy_excerpt TEXT NOT NULL,
          copy_hash TEXT NOT NULL,
          PRIMARY KEY (run_id, variant_id),
          FOREIGN KEY (run_id) REFERENCES runs(run_id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS stale_state (
          run_id TEXT PRIMARY KEY,
          state TEXT NOT NULL,
          reasons_json TEXT NOT NULL,
          stored_hashes_json TEXT NOT NULL,
          checked_at TEXT NOT NULL,
          FOREIGN KEY (run_id) REFERENCES runs(run_id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS task_validations (
          run_id TEXT NOT NULL,
          validation_result_id TEXT NOT NULL,
          observation_source TEXT NOT NULL DEFAULT 'unknown',
          evidence_basis TEXT NOT NULL,
          evidence_grade TEXT NOT NULL DEFAULT 'unknown',
          real_task_evidence_created INTEGER NOT NULL DEFAULT 0,
          decision_state TEXT NOT NULL,
          participant_count INTEGER NOT NULL,
          task_attempt_count INTEGER NOT NULL,
          completion_rate REAL NOT NULL,
          median_skim_to_answer_seconds REAL NOT NULL,
          average_follow_up_question_count REAL NOT NULL,
          average_expert_respect_rating REAL NOT NULL,
          average_reuse_intent_rating REAL NOT NULL,
          trust_objection_count INTEGER NOT NULL,
          source_path TEXT NOT NULL,
          PRIMARY KEY (run_id, validation_result_id),
          FOREIGN KEY (run_id) REFERENCES runs(run_id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_scores_dimension ON scores(dimension_id);
        CREATE INDEX IF NOT EXISTS idx_findings_issue ON findings(dimension_id, issue);
        CREATE INDEX IF NOT EXISTS idx_runs_generated_at ON runs(generated_at);
        CREATE INDEX IF NOT EXISTS idx_task_validations_run ON task_validations(run_id);
        """
    )
    connection.execute(
        "INSERT OR REPLACE INTO schema_meta(key, value) VALUES (?, ?)",
        ("schema_version", SCHEMA_VERSION),
    )
    _ensure_column(connection, "runs", "task_validation_signal_count", "INTEGER NOT NULL DEFAULT 0")
    _ensure_column(connection, "task_validations", "observation_source", "TEXT NOT NULL DEFAULT 'unknown'")
    _ensure_column(connection, "task_validations", "evidence_grade", "TEXT NOT NULL DEFAULT 'unknown'")
    _ensure_column(connection, "task_validations", "real_task_evidence_created", "INTEGER NOT NULL DEFAULT 0")


def _ensure_column(connection: sqlite3.Connection, table_name: str, column_name: str, declaration: str) -> None:
    columns = {
        str(row[1])
        for row in connection.execute(f"PRAGMA table_info({table_name})")
    }
    if column_name not in columns:
        connection.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {declaration}")


def fetch_dashboard_data(db_path: str | Path) -> dict[str, Any]:
    """Fetch normalized dashboard data from the SQLite store."""

    db_file = Path(db_path)
    if not db_file.exists():
        raise StoreBlockedError(
            [{"code": "missing_db_file", "message": "SQLite database does not exist.", "path": str(db_file)}]
        )
    with closing(sqlite3.connect(db_file)) as connection:
        connection.row_factory = sqlite3.Row
        initialize_store(connection)
        runs = [dict(row) for row in connection.execute("SELECT * FROM runs ORDER BY generated_at, stored_at")]
        scores = [dict(row) for row in connection.execute("SELECT * FROM scores ORDER BY run_id, dimension_id")]
        findings = [dict(row) for row in connection.execute("SELECT * FROM findings ORDER BY run_id, finding_id")]
        claims = [dict(row) for row in connection.execute("SELECT * FROM claims ORDER BY run_id, claim_id")]
        variants = [dict(row) for row in connection.execute("SELECT * FROM variants ORDER BY run_id, variant_id")]
        task_validations = [
            dict(row)
            for row in connection.execute("SELECT * FROM task_validations ORDER BY run_id, validation_result_id")
        ]
        stale = [dict(row) for row in connection.execute("SELECT * FROM stale_state ORDER BY run_id")]

    return {
        "dbPath": str(db_file),
        "schemaVersion": SCHEMA_VERSION,
        "runs": runs,
        "scores": scores,
        "findings": findings,
        "claims": claims,
        "variants": variants,
        "taskValidations": task_validations,
        "staleState": stale,
    }


def initialize_store_path(db_path: str | Path) -> dict[str, Any]:
    """Initialize the SQLite store at a path."""

    db_file = Path(db_path)
    db_file.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(db_file)) as connection:
        initialize_store(connection)
        connection.commit()
    return {
        "artifactType": "history_store_init_result",
        "dbPath": str(db_file),
        "schemaVersion": SCHEMA_VERSION,
        "marketEvidenceCreated": False,
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "toolVersion": __version__,
    }


def list_analysis_history(db_path: str | Path) -> dict[str, Any]:
    """Return a compact list of stored analyses."""

    data = fetch_dashboard_data(db_path)
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
                "taskValidationCount": sum(1 for item in data["taskValidations"] if item["run_id"] == run["run_id"]),
                "staleState": stale_by_run.get(run["run_id"], {}).get("state", "unknown"),
                "generatedAt": run["generated_at"],
                "storedAt": run["stored_at"],
            }
        )
    return {
        "artifactType": "history_analysis_list",
        "dbPath": data["dbPath"],
        "runCount": len(runs),
        "runs": runs,
        "marketEvidenceCreated": False,
        "notMarketEvidence": True,
    }


def compare_analysis_history(db_path: str | Path, *, brief_id: str | None = None) -> dict[str, Any]:
    """Compare score changes and repeated findings across stored analyses."""

    data = fetch_dashboard_data(db_path)
    selected_runs = [
        run for run in data["runs"] if brief_id is None or run["brief_id"] == brief_id
    ]
    selected_ids = {run["run_id"] for run in selected_runs}
    scores = [score for score in data["scores"] if score["run_id"] in selected_ids]
    findings = [finding for finding in data["findings"] if finding["run_id"] in selected_ids]
    score_changes = _score_changes(selected_runs, scores)
    repeated_findings = _repeated_findings(findings)
    task_validations = [item for item in data["taskValidations"] if item["run_id"] in selected_ids]
    return {
        "artifactType": "history_comparison_report",
        "dbPath": data["dbPath"],
        "briefId": brief_id,
        "runCount": len(selected_runs),
        "scoreChanges": score_changes,
        "repeatedFindings": repeated_findings,
        "simulatedVsValidated": {
            "simulatedResultCount": sum(run["simulated_result_count"] for run in selected_runs),
            "validatedSignalCount": sum(run["validated_signal_count"] for run in selected_runs),
            "taskValidationSignalCount": sum(run["task_validation_signal_count"] for run in selected_runs),
            "interpretation": (
                "Simulated results are hypotheses and are not counted as validated signals. "
                "Task-validation signals are counted separately as exact-context evidence and are not company-wide proof."
            ),
        },
        "taskValidationSummary": _task_validation_summary(task_validations),
        "marketEvidenceCreated": False,
        "notMarketEvidence": True,
    }


def export_store(db_path: str | Path, output_path: str | Path) -> Path:
    """Export dashboard/store data to a JSON file."""

    destination = Path(output_path)
    if destination.suffix.lower() != ".json":
        destination.mkdir(parents=True, exist_ok=True)
        destination = destination / "mindfront-store-export.json"
    else:
        destination.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "artifactType": "history_store_export",
        "exportedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "marketEvidenceCreated": False,
        "notMarketEvidence": True,
        "dataBoundary": "Export contains artifact summaries, hashes, excerpts, and status fields, not full raw source text.",
        "data": fetch_dashboard_data(db_path),
    }
    destination.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return destination


def refresh_stale_state(db_path: str | Path, *, update: bool = True) -> dict[str, Any]:
    """Compare stored artifact hashes against current files and update stale state."""

    db_file = Path(db_path)
    if not db_file.exists():
        raise StoreBlockedError(
            [{"code": "missing_db_file", "message": "SQLite database does not exist.", "path": str(db_file)}]
        )
    checked_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with closing(sqlite3.connect(db_file)) as connection:
        connection.row_factory = sqlite3.Row
        initialize_store(connection)
        rows = [dict(row) for row in connection.execute("SELECT * FROM runs ORDER BY generated_at, stored_at")]
        results = [_check_run_stale_state(run, checked_at) for run in rows]
        if update:
            for result in results:
                connection.execute(
                    """
                    INSERT OR REPLACE INTO stale_state(
                      run_id, state, reasons_json, stored_hashes_json, checked_at
                    ) VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        result["runId"],
                        result["state"],
                        json.dumps(result["reasons"], sort_keys=True),
                        json.dumps(result["storedHashes"], sort_keys=True),
                        checked_at,
                    ),
                )
            connection.commit()

    return {
        "artifactType": "history_stale_state_check",
        "dbPath": str(db_file),
        "checkedAt": checked_at,
        "updated": update,
        "runCount": len(results),
        "staleRunCount": sum(1 for result in results if result["state"] != "current"),
        "runs": results,
        "marketEvidenceCreated": False,
        "notMarketEvidence": True,
    }


def delete_run(db_path: str | Path, run_id: str) -> dict[str, Any]:
    """Delete one run and its dependent rows from the SQLite store."""

    db_file = Path(db_path)
    if not db_file.exists():
        raise StoreBlockedError(
            [{"code": "missing_db_file", "message": "SQLite database does not exist.", "path": str(db_file)}]
        )
    with closing(sqlite3.connect(db_file)) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        initialize_store(connection)
        existing = connection.execute("SELECT run_id FROM runs WHERE run_id = ?", (run_id,)).fetchone()
        if existing is None:
            raise StoreBlockedError(
                [{"code": "unknown_run", "message": f"Run does not exist: {run_id}.", "path": "run_id"}]
            )
        connection.execute("DELETE FROM runs WHERE run_id = ?", (run_id,))
        connection.commit()
        remaining = connection.execute("SELECT COUNT(*) FROM runs").fetchone()[0]
    return {
        "artifactType": "history_store_delete_result",
        "dbPath": str(db_file),
        "deletedRunId": run_id,
        "remainingRunCount": remaining,
        "marketEvidenceCreated": False,
    }


def _upsert_artifacts(connection: sqlite3.Connection, artifacts: dict[str, dict[str, Any] | None]) -> None:
    analysis = artifacts["analysis"]["data"]
    run_id = analysis["reportId"]
    connection.execute("PRAGMA foreign_keys = ON")
    for table in ("scores", "findings", "claims", "variants"):
        connection.execute(f"DELETE FROM {table} WHERE run_id = ?", (run_id,))

    artifact_paths = {
        name: artifact["path"]
        for name, artifact in artifacts.items()
        if artifact is not None
    }
    artifact_hashes = {
        name: _hash_file(Path(artifact["path"]))
        for name, artifact in artifacts.items()
        if artifact is not None
    }
    simulated_count = _simulated_result_count(artifacts)
    validated_count = _validated_signal_count(artifacts)
    task_validation_signal_count = _task_validation_signal_count(artifacts)
    connection.execute(
        """
        INSERT OR REPLACE INTO runs(
          run_id, brief_id, summary, validation_state, sensitive_domain_state, data_classification,
          source_text_hash, source_brief_hash, config_set_hash, generated_at, stored_at,
          artifact_paths_json, artifact_hashes_json, market_evidence_created, simulated_result_count,
          validated_signal_count, task_validation_signal_count
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            run_id,
            analysis.get("briefId", "unknown"),
            analysis.get("summary", ""),
            analysis.get("validationState", "unknown"),
            analysis.get("sensitiveDomainState", "unknown"),
            analysis.get("dataClassification", "unknown"),
            analysis["sourceTextHash"],
            analysis["sourceBriefHash"],
            analysis["configSetHash"],
            analysis.get("generatedAt", ""),
            datetime.now(timezone.utc).isoformat(timespec="seconds"),
            json.dumps(artifact_paths, sort_keys=True),
            json.dumps(artifact_hashes, sort_keys=True),
            0,
            simulated_count,
            validated_count,
            task_validation_signal_count,
        ),
    )
    _insert_scores(connection, run_id, analysis)
    _insert_findings(connection, run_id, analysis)
    _insert_claims(connection, run_id, analysis)
    variants = artifacts.get("variants")
    if variants:
        _insert_variants(connection, run_id, variants["data"])
    task_validation = artifacts.get("task_validation")
    if task_validation:
        _insert_task_validation(connection, run_id, task_validation)
    _upsert_stale_state(connection, run_id, artifact_hashes)


def _insert_scores(connection: sqlite3.Connection, run_id: str, analysis: dict[str, Any]) -> None:
    for score in analysis.get("scores", []):
        connection.execute(
            """
            INSERT INTO scores(
              run_id, dimension_id, score, score_scale, score_reason, evidence_basis, finding_confidence
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                score["dimensionId"],
                int(score["score"]),
                score["scoreScale"],
                score["scoreReason"],
                score.get("evidenceBasis", "unknown"),
                score.get("findingConfidence", "unknown"),
            ),
        )


def _insert_findings(connection: sqlite3.Connection, run_id: str, analysis: dict[str, Any]) -> None:
    for finding in analysis.get("findings", []):
        connection.execute(
            """
            INSERT INTO findings(
              run_id, finding_id, dimension_id, severity, issue, evidence_basis,
              finding_confidence, recommended_validation, claim_ids_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                finding["findingId"],
                finding["dimensionId"],
                finding["severity"],
                finding["issue"],
                finding.get("evidenceBasis", "unknown"),
                finding.get("findingConfidence", "unknown"),
                finding.get("recommendedValidation", ""),
                json.dumps(finding.get("claimIds", []), sort_keys=True),
            ),
        )


def _insert_claims(connection: sqlite3.Connection, run_id: str, analysis: dict[str, Any]) -> None:
    for claim in analysis.get("claims", []):
        claim_text = claim.get("claimText", "")
        connection.execute(
            """
            INSERT INTO claims(
              run_id, claim_id, claim_type, claim_strength, support_status,
              evidence_basis, claim_excerpt, claim_hash
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                claim["claimId"],
                claim.get("claimType", "unknown"),
                claim.get("claimStrength", "unknown"),
                claim.get("supportStatus", "unknown"),
                claim.get("evidenceBasis", "unknown"),
                _excerpt(claim_text),
                f"sha256:{_hash_text(claim_text)}",
            ),
        )


def _insert_variants(connection: sqlite3.Connection, run_id: str, variants: dict[str, Any]) -> None:
    for variant in variants.get("variants", []):
        copy = variant.get("copy", "")
        connection.execute(
            """
            INSERT INTO variants(
              run_id, variant_id, strategy_id, recommendation_state, claim_gate_status,
              copy_excerpt, copy_hash
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                variant["variantId"],
                variant.get("strategyId", "unknown"),
                variant.get("recommendationState", "unknown"),
                variant.get("claimGateStatus", "unknown"),
                _excerpt(copy),
                f"sha256:{_hash_text(copy)}",
            ),
        )


def _insert_task_validation(connection: sqlite3.Connection, run_id: str, artifact: dict[str, Any]) -> None:
    validation = artifact["data"]
    sample = validation.get("sample", {})
    metrics = validation.get("aggregateMetrics", {})
    connection.execute(
        """
        INSERT OR REPLACE INTO task_validations(
          run_id, validation_result_id, observation_source, evidence_basis, evidence_grade,
          real_task_evidence_created, decision_state, participant_count,
          task_attempt_count, completion_rate, median_skim_to_answer_seconds,
          average_follow_up_question_count, average_expert_respect_rating,
          average_reuse_intent_rating, trust_objection_count, source_path
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            run_id,
            validation["validationResultId"],
            validation.get("observationSource", "unknown"),
            validation.get("evidenceBasis", "unknown"),
            validation.get("evidenceGrade", "unknown"),
            1 if validation.get("realTaskEvidenceCreated") is True else 0,
            validation.get("decisionState", "unknown"),
            int(sample.get("participantCount", 0)),
            int(metrics.get("taskAttemptCount", 0)),
            float(metrics.get("completionRate", 0)),
            float(metrics.get("medianSkimToAnswerSeconds", 0)),
            float(metrics.get("averageFollowUpQuestionCount", 0)),
            float(metrics.get("averageExpertRespectRating", 0)),
            float(metrics.get("averageReuseIntentRating", 0)),
            int(metrics.get("trustObjectionCount", 0)),
            artifact["path"],
        ),
    )


def _upsert_stale_state(connection: sqlite3.Connection, run_id: str, artifact_hashes: dict[str, str]) -> None:
    connection.execute(
        """
        INSERT OR REPLACE INTO stale_state(
          run_id, state, reasons_json, stored_hashes_json, checked_at
        ) VALUES (?, ?, ?, ?, ?)
        """,
        (
            run_id,
            "current_at_ingest",
            "[]",
            json.dumps(artifact_hashes, sort_keys=True),
            datetime.now(timezone.utc).isoformat(timespec="seconds"),
        ),
    )


def _check_run_stale_state(run: dict[str, Any], checked_at: str) -> dict[str, Any]:
    artifact_paths = json.loads(run["artifact_paths_json"])
    stored_hashes = json.loads(run["artifact_hashes_json"])
    current_hashes: dict[str, str | None] = {}
    reasons: list[dict[str, str]] = []
    for artifact_name, path_text in sorted(artifact_paths.items()):
        artifact_path = Path(path_text)
        stored_hash = stored_hashes.get(artifact_name)
        if not artifact_path.exists():
            current_hashes[artifact_name] = None
            reasons.append(
                {
                    "code": "artifact_missing",
                    "artifact": artifact_name,
                    "path": str(artifact_path),
                    "message": "Stored artifact path no longer exists.",
                }
            )
            continue
        current_hash = _hash_file(artifact_path)
        current_hashes[artifact_name] = current_hash
        if stored_hash != current_hash:
            reasons.append(
                {
                    "code": "artifact_hash_changed",
                    "artifact": artifact_name,
                    "path": str(artifact_path),
                    "message": "Stored artifact hash no longer matches the current file.",
                }
            )
    state = "current" if not reasons else "stale"
    return {
        "runId": run["run_id"],
        "briefId": run["brief_id"],
        "state": state,
        "reasons": reasons,
        "storedHashes": stored_hashes,
        "currentHashes": current_hashes,
        "checkedAt": checked_at,
    }


def _score_changes(runs: list[dict[str, Any]], scores: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_dimension: dict[str, list[dict[str, Any]]] = {}
    run_order = {run["run_id"]: index for index, run in enumerate(runs)}
    for score in scores:
        by_dimension.setdefault(score["dimension_id"], []).append(score)

    changes = []
    for dimension, items in sorted(by_dimension.items()):
        ordered = sorted(items, key=lambda item: run_order.get(item["run_id"], 0))
        first = ordered[0]
        last = ordered[-1]
        changes.append(
            {
                "dimensionId": dimension,
                "firstRunId": first["run_id"],
                "lastRunId": last["run_id"],
                "firstScore": first["score"],
                "lastScore": last["score"],
                "delta": last["score"] - first["score"],
                "runCount": len(ordered),
            }
        )
    return changes


def _repeated_findings(findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for finding in findings:
        key = (finding["dimension_id"], finding["issue"])
        grouped.setdefault(key, []).append(finding)
    repeated = []
    for (dimension, issue), items in sorted(grouped.items(), key=lambda entry: (-len(entry[1]), entry[0])):
        if len(items) < 2:
            continue
        repeated.append(
            {
                "dimensionId": dimension,
                "issue": issue,
                "count": len(items),
                "runIds": [item["run_id"] for item in items],
                "maxSeverity": _max_severity([item["severity"] for item in items]),
                "evidenceBases": sorted({item["evidence_basis"] for item in items}),
            }
        )
    return repeated


def _task_validation_summary(task_validations: list[dict[str, Any]]) -> dict[str, Any]:
    if not task_validations:
        return {
            "validationRunCount": 0,
            "participantCount": 0,
            "realTaskEvidenceRunCount": 0,
            "syntheticFixtureRunCount": 0,
            "averageCompletionRate": None,
            "medianSkimToAnswerSeconds": None,
            "interpretation": "No measured task-validation evidence has been stored.",
        }
    return {
        "validationRunCount": len(task_validations),
        "participantCount": sum(int(item["participant_count"]) for item in task_validations),
        "realTaskEvidenceRunCount": sum(1 for item in task_validations if int(item.get("real_task_evidence_created", 0)) == 1),
        "syntheticFixtureRunCount": sum(1 for item in task_validations if item.get("observation_source") == "synthetic_fixture"),
        "averageCompletionRate": round(
            sum(float(item["completion_rate"]) for item in task_validations) / len(task_validations),
            4,
        ),
        "medianSkimToAnswerSeconds": round(
            median(float(item["median_skim_to_answer_seconds"]) for item in task_validations),
            2,
        ),
        "interpretation": (
            "Real task-validation rows are exact-context directional evidence, not market proof. "
            "Synthetic fixture rows verify workflow behavior only."
        ),
    }


def _max_severity(values: list[str]) -> str:
    order = {"low": 0, "medium": 1, "high": 2, "blocked": 3}
    return max(values or ["medium"], key=lambda value: order.get(value, 1))


def _load_artifacts(
    *,
    analysis_path: str | Path,
    variants_path: str | Path | None,
    comparison_path: str | Path | None,
    stress_path: str | Path | None,
    research_plan_path: str | Path | None,
    report_path: str | Path | None,
    task_protocol_path: str | Path | None,
    task_validation_path: str | Path | None,
) -> dict[str, dict[str, Any] | None]:
    return {
        "analysis": _load_artifact(Path(analysis_path), "analysis"),
        "variants": _load_artifact(Path(variants_path), "variants") if variants_path else None,
        "comparison": _load_artifact(Path(comparison_path), "comparison") if comparison_path else None,
        "stress": _load_artifact(Path(stress_path), "stress") if stress_path else None,
        "research": _load_artifact(Path(research_plan_path), "research") if research_plan_path else None,
        "report": _load_artifact(Path(report_path), "report") if report_path else None,
        "task_protocol": _load_artifact(Path(task_protocol_path), "task_protocol") if task_protocol_path else None,
        "task_validation": _load_artifact(Path(task_validation_path), "task_validation") if task_validation_path else None,
    }


def _load_artifact(path: Path, label: str) -> dict[str, Any]:
    data = _load_json_file(path, label)
    expected = EXPECTED_TYPES[label]
    if data.get("artifactType") != expected:
        raise StoreBlockedError(
            [
                {
                    "code": "invalid_artifact_type",
                    "message": f"{label} input must be a {expected}.",
                    "path": f"{path}.artifactType",
                }
            ]
        )
    if label == "analysis":
        _validate_analysis(data, str(path))
    return {"path": str(path), "data": data}


def _load_json_file(path: Path, label: str) -> dict[str, Any]:
    if not path.exists():
        raise StoreBlockedError(
            [{"code": f"missing_{label}_file", "message": f"Missing {label} file.", "path": str(path)}]
        )
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except JSONDecodeError as exc:
        raise StoreBlockedError(
            [
                {
                    "code": "invalid_json",
                    "message": f"Invalid JSON at line {exc.lineno}, column {exc.colno}: {exc.msg}.",
                    "path": str(path),
                }
            ]
        ) from exc
    if not isinstance(data, dict):
        raise StoreBlockedError(
            [{"code": "invalid_json_shape", "message": f"{label} file must contain a JSON object.", "path": str(path)}]
        )
    return data


def _validate_analysis(analysis: dict[str, Any], path: str) -> None:
    required = (
        "reportId",
        "briefId",
        "summary",
        "scores",
        "findings",
        "claims",
        "sourceBriefHash",
        "sourceTextHash",
        "configSetHash",
    )
    reasons = [
        {
            "code": "missing_required_field",
            "message": f"Missing required field: {field_name}.",
            "path": f"{path}.{field_name}",
        }
        for field_name in required
        if field_name not in analysis
    ]
    if reasons:
        raise StoreBlockedError(reasons)


def _validate_cross_refs(artifacts: dict[str, dict[str, Any] | None]) -> None:
    analysis = artifacts["analysis"]["data"]
    analysis_id = analysis["reportId"]
    variants = _artifact_data(artifacts, "variants")
    comparison = _artifact_data(artifacts, "comparison")
    stress = _artifact_data(artifacts, "stress")
    research = _artifact_data(artifacts, "research")
    report = _artifact_data(artifacts, "report")
    task_protocol = _artifact_data(artifacts, "task_protocol")
    task_validation = _artifact_data(artifacts, "task_validation")
    reasons: list[dict[str, str]] = []
    if variants and variants.get("sourceAnalysisReportId") != analysis_id:
        reasons.append({"code": "source_mismatch", "message": "Variant bundle source mismatch.", "path": "variants"})
    if comparison and variants and comparison.get("sourceVariantBundleId") != variants.get("bundleId"):
        reasons.append({"code": "source_mismatch", "message": "Comparison source mismatch.", "path": "comparison"})
    if stress and stress.get("sourceAnalysisReportId") != analysis_id:
        reasons.append({"code": "source_mismatch", "message": "Stress report source mismatch.", "path": "stress"})
    if research and research.get("sourceAnalysisReportId") != analysis_id:
        reasons.append({"code": "source_mismatch", "message": "Research plan source mismatch.", "path": "research"})
    if report and report.get("sourceAnalysisReportId") != analysis_id:
        reasons.append({"code": "source_mismatch", "message": "Audit report source mismatch.", "path": "report"})
    if task_protocol and task_protocol.get("sourceAnalysisReportId") != analysis_id:
        reasons.append(
            {"code": "source_mismatch", "message": "Task-observation protocol source mismatch.", "path": "task_protocol"}
        )
    if task_protocol and task_protocol.get("briefId") != analysis.get("briefId"):
        reasons.append(
            {"code": "brief_mismatch", "message": "Task-observation protocol brief mismatch.", "path": "task_protocol.briefId"}
        )
    if task_protocol and task_protocol.get("notMarketEvidence") is not True:
        reasons.append(
            {
                "code": "evidence_boundary_violation",
                "message": "Task-observation protocol must explicitly remain not market evidence.",
                "path": "task_protocol.notMarketEvidence",
            }
        )
    if task_validation and task_validation.get("sourceAnalysisReportId") != analysis_id:
        reasons.append(
            {"code": "source_mismatch", "message": "Task validation source mismatch.", "path": "task_validation"}
        )
    if task_validation and task_validation.get("briefId") != analysis.get("briefId"):
        reasons.append(
            {"code": "brief_mismatch", "message": "Task validation brief mismatch.", "path": "task_validation.briefId"}
        )
    for name in ("stress", "research", "report", "task_protocol"):
        artifact = _artifact_data(artifacts, name)
        if artifact and artifact.get("marketEvidenceCreated") is not False:
            reasons.append(
                {
                    "code": "evidence_boundary_violation",
                    "message": f"{name} artifact cannot create market evidence.",
                    "path": f"{name}.marketEvidenceCreated",
                }
            )
    if task_validation:
        reasons.extend(task_validation_result_errors(task_validation, path="task_validation"))
    if reasons:
        raise StoreBlockedError(reasons)


def _artifact_data(artifacts: dict[str, dict[str, Any] | None], name: str) -> dict[str, Any] | None:
    artifact = artifacts.get(name)
    return artifact["data"] if artifact else None


def _simulated_result_count(artifacts: dict[str, dict[str, Any] | None]) -> int:
    stress = _artifact_data(artifacts, "stress")
    if not stress:
        return 0
    return len(stress.get("results", []))


def _validated_signal_count(artifacts: dict[str, dict[str, Any] | None]) -> int:
    count = 0
    analysis = artifacts["analysis"]["data"]
    for item in [*analysis.get("scores", []), *analysis.get("findings", []), *analysis.get("claims", [])]:
        if item.get("evidenceBasis") in VALIDATED_EVIDENCE_BASES:
            count += 1
    return count


def _task_validation_signal_count(artifacts: dict[str, dict[str, Any] | None]) -> int:
    task_validation = _artifact_data(artifacts, "task_validation")
    if not task_validation:
        return 0
    if task_validation.get("realTaskEvidenceCreated") is not True:
        return 0
    return len(task_validation.get("executiveSignals", []))


def _excerpt(text: str, limit: int = 240) -> str:
    cleaned = " ".join(str(text).split())
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 3].rstrip() + "..."


def _hash_file(path: Path) -> str:
    return f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"


def _hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()

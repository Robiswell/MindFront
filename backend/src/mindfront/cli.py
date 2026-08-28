"""Mindfront command line interface."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .analysis import AnalysisBlockedError, analyze_message_brief, finalize_analysis_report, write_analysis_report
from .compare import (
    CompareBlockedError,
    compare_variant_bundle,
    finalize_comparison_report,
    write_comparison_report,
)
from .communication_vault import (
    corpus_batch_from_freshservice_jsonl,
    corpus_batch_from_outlook_export,
    corpus_batch_from_teams_export,
    delete_corpus_person,
    derive_observation_bundle,
    get_corpus_context,
    ingest_corpus_batch,
    invalidate_corpus_batch,
    list_corpus_people,
    validate_corpus_batch,
)
from .dashboard import build_static_dashboard
from .db import (
    StoreBlockedError,
    compare_analysis_history,
    delete_run,
    export_store,
    initialize_store_path,
    list_analysis_history,
    refresh_stale_state,
    store_artifact_set,
)
from .impact import (
    TaskValidationBlockedError,
    build_task_validation_result,
    finalize_task_validation_result,
    write_task_validation_result,
)
from .interaction_profiles import (
    ALLOWED_CONTEXTS,
    InteractionProfileBlockedError,
    build_interaction_profile,
    delete_interaction_profile,
    get_interaction_profile,
    invalidate_profile_batch,
    list_interaction_profiles,
    profile_guidance,
    upsert_profile_store,
    validate_observation_bundle,
)
from .improvement import (
    ImprovementPlanBlockedError,
    build_improvement_plan,
    finalize_improvement_plan,
    write_improvement_plan,
)
from .protocol import (
    TaskInputBlockedError,
    TaskProtocolBlockedError,
    build_task_observation_protocol,
    build_task_validation_input_from_protocol,
    finalize_task_observation_protocol,
    write_task_observation_protocol,
    write_task_validation_input,
)
from .rewrite import (
    RewriteBlockedError,
    finalize_rewrite_bundle,
    rewrite_message_brief,
    write_rewrite_bundle,
)
from .research import (
    ResearchPlanBlockedError,
    build_research_plan,
    finalize_research_plan,
    write_research_plan,
)
from .reports import (
    ReportBundleBlockedError,
    build_report_bundle,
    finalize_report_bundle,
    write_report_bundle,
)
from .stress import (
    StressTestBlockedError,
    finalize_stress_report,
    run_reader_stress_test,
    write_stress_report,
)
from .validation import ValidationResult, validate_workspace
from .vault_crypto import (
    CURRENT_ENCRYPTION,
    VaultEncryptionError,
    initialize_vault_key,
    inspect_vault,
    migrate_vault,
    vault_key_status,
)
from .workplace_assistance import (
    WorkplaceAssistanceBlockedError,
    build_self_assistance_context,
    build_self_assistance_profile,
    build_workplace_assistance,
    delete_self_assistance_profile,
    finalize_workplace_assistance,
    get_self_assistance_profile,
    load_workplace_assistance_policy,
    require_private_runtime_path,
    upsert_self_assistance_profile,
    validate_self_assistance_profile,
    write_workplace_assistance_result,
)


class OutputConflictError(Exception):
    """Raised when a requested output path would overwrite existing artifacts."""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="mindfront", description="Mindfront local CLI.")
    common_output_parser = argparse.ArgumentParser(add_help=False)
    common_output_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Resolve inputs and planned outputs without writing artifacts.",
    )
    common_output_parser.add_argument(
        "--overwrite",
        choices=("fail", "replace", "rename"),
        default="fail",
        help="Output conflict behavior. Defaults to fail.",
    )
    common_output_parser.add_argument(
        "--no-external-llm",
        action="store_true",
        help="Accepted for deterministic offline runs. Mindfront Phase 0/1 does not call external LLMs.",
    )
    subparsers = parser.add_subparsers(dest="command")

    validate_parser = subparsers.add_parser(
        "validate",
        parents=[common_output_parser],
        help="Validate Mindfront config files.",
    )
    validate_parser.add_argument(
        "--config-root",
        default="config",
        help="Directory containing Mindfront config JSON files. Defaults to ./config.",
    )
    validate_parser.add_argument(
        "--strict",
        action="store_true",
        help="Require the full canonical config set and enum values.",
    )
    validate_parser.add_argument(
        "--brief-root",
        default="examples/briefs",
        help="Directory containing message brief JSON files to validate when present.",
    )
    validate_parser.add_argument(
        "--task-validation-root",
        default="examples/task-validation",
        help="Directory containing task-validation input JSON files to validate when present.",
    )
    validate_parser.add_argument(
        "--json-errors",
        action="store_true",
        help="Emit machine-readable validation results.",
    )
    validate_parser.add_argument(
        "--output",
        help="Optional JSON file path or directory for the validation report.",
    )

    analyze_parser = subparsers.add_parser(
        "analyze",
        parents=[common_output_parser],
        help="Analyze one message brief with deterministic checks.",
    )
    analyze_parser.add_argument(
        "--brief",
        required=True,
        help="Path to a message brief JSON file.",
    )
    analyze_parser.add_argument(
        "--config-root",
        default="config",
        help="Directory containing Mindfront config JSON files. Defaults to ./config.",
    )
    analyze_parser.add_argument(
        "--output",
        help="Optional JSON file path or directory for the analysis report.",
    )
    analyze_parser.add_argument(
        "--json-errors",
        action="store_true",
        help="Emit machine-readable validation errors if analysis is blocked.",
    )
    analyze_parser.add_argument(
        "--profile-store",
        help="Optional encrypted interaction profile store path.",
    )
    analyze_parser.add_argument(
        "--profile-name",
        help="Exact named recipient profile to apply. Requires --profile-store.",
    )
    analyze_parser.add_argument(
        "--profile-context",
        choices=sorted(ALLOWED_CONTEXTS),
        help="Optional communication-context override. Defaults to deterministic inference from the brief.",
    )

    rewrite_parser = subparsers.add_parser(
        "rewrite",
        parents=[common_output_parser],
        help="Generate deterministic copy variants.",
    )
    rewrite_parser.add_argument(
        "--brief",
        required=True,
        help="Path to a message brief JSON file.",
    )
    rewrite_parser.add_argument(
        "--config-root",
        default="config",
        help="Directory containing Mindfront config JSON files. Defaults to ./config.",
    )
    rewrite_parser.add_argument(
        "--strategy",
        action="append",
        help="Optional rewrite strategy. Can be repeated. Defaults to the Phase 0 strategy set.",
    )
    rewrite_parser.add_argument(
        "--output",
        help="Optional JSON file path or directory for the copy variant bundle.",
    )
    rewrite_parser.add_argument(
        "--json-errors",
        action="store_true",
        help="Emit machine-readable errors if rewrite is blocked.",
    )
    rewrite_parser.add_argument(
        "--profile-store",
        help="Optional encrypted interaction profile store path.",
    )
    rewrite_parser.add_argument(
        "--profile-name",
        help="Exact named recipient profile to apply. Requires --profile-store.",
    )
    rewrite_parser.add_argument(
        "--profile-context",
        choices=sorted(ALLOWED_CONTEXTS),
        help="Optional communication-context override. Defaults to deterministic inference from the brief.",
    )

    compare_parser = subparsers.add_parser(
        "compare",
        parents=[common_output_parser],
        help="Compare gated copy variants.",
    )
    compare_parser.add_argument(
        "--variants",
        required=True,
        help="Path to a copy variant bundle JSON file.",
    )
    compare_parser.add_argument(
        "--output",
        help="Optional JSON file path or directory for the comparison report.",
    )
    compare_parser.add_argument(
        "--json-errors",
        action="store_true",
        help="Emit machine-readable errors if comparison is blocked.",
    )

    stress_parser = subparsers.add_parser(
        "reader-stress-test",
        parents=[common_output_parser],
        help="Run simulated reader stress tests through configured audience lenses.",
    )
    stress_parser.add_argument(
        "--analysis",
        required=True,
        help="Path to a message analysis report JSON file.",
    )
    stress_parser.add_argument(
        "--config-root",
        default="config",
        help="Directory containing Mindfront config JSON files. Defaults to ./config.",
    )
    stress_parser.add_argument(
        "--lens",
        action="append",
        help="Optional audience lens id. Can be repeated. Defaults to all active lenses.",
    )
    stress_parser.add_argument(
        "--output",
        help="Optional JSON file path or directory for the stress-test report.",
    )
    stress_parser.add_argument(
        "--json-errors",
        action="store_true",
        help="Emit machine-readable errors if the stress test is blocked.",
    )

    research_parser = subparsers.add_parser(
        "research-plan",
        parents=[common_output_parser],
        help="Generate a real-world research handoff.",
    )
    research_parser.add_argument(
        "--analysis",
        required=True,
        help="Path to a message analysis report JSON file.",
    )
    research_parser.add_argument(
        "--output",
        help="Optional JSON, Markdown, or directory output for the research plan.",
    )
    research_parser.add_argument(
        "--json-errors",
        action="store_true",
        help="Emit machine-readable errors if research planning is blocked.",
    )

    report_parser = subparsers.add_parser(
        "report",
        parents=[common_output_parser],
        help="Assemble a Markdown/HTML audit report bundle.",
    )
    report_parser.add_argument(
        "--analysis",
        required=True,
        help="Path to a message analysis report JSON file.",
    )
    report_parser.add_argument(
        "--variants",
        help="Optional path to a copy variant bundle JSON file.",
    )
    report_parser.add_argument(
        "--comparison",
        help="Optional path to a variant comparison report JSON file.",
    )
    report_parser.add_argument(
        "--stress",
        help="Optional path to a reader stress-test report JSON file.",
    )
    report_parser.add_argument(
        "--research-plan",
        help="Optional path to a research plan JSON file.",
    )
    report_parser.add_argument(
        "--task-protocol",
        help="Optional path to a documentation task-observation protocol JSON file.",
    )
    report_parser.add_argument(
        "--task-validation",
        help="Optional path to a documentation task-validation result JSON file.",
    )
    report_parser.add_argument(
        "--config-root",
        default="config",
        help="Directory containing Mindfront config JSON files. Defaults to ./config.",
    )
    report_parser.add_argument(
        "--output",
        help="Optional JSON, Markdown, HTML, CSV, or directory output for the audit report.",
    )
    report_parser.add_argument(
        "--json-errors",
        action="store_true",
        help="Emit machine-readable errors if report generation is blocked.",
    )

    task_validation_parser = subparsers.add_parser(
        "task-validation",
        parents=[common_output_parser],
        help="Summarize measured documentation task-validation observations.",
    )
    task_validation_parser.add_argument(
        "--input",
        required=True,
        help="Path to a documentation task-validation input JSON file.",
    )
    task_validation_parser.add_argument(
        "--analysis",
        help="Optional source message analysis report used to verify ids.",
    )
    task_validation_parser.add_argument(
        "--output",
        help="Optional JSON file path or directory for the task-validation result.",
    )
    task_validation_parser.add_argument(
        "--json-errors",
        action="store_true",
        help="Emit machine-readable errors if task validation is blocked.",
    )

    task_protocol_parser = subparsers.add_parser(
        "task-protocol",
        parents=[common_output_parser],
        help="Generate a no-PII documentation task-observation protocol and CSV template.",
    )
    task_protocol_parser.add_argument(
        "--analysis",
        required=True,
        help="Path to a source message analysis report JSON file.",
    )
    task_protocol_parser.add_argument(
        "--research-plan",
        help="Optional path to a research plan JSON file for task prompts.",
    )
    task_protocol_parser.add_argument(
        "--document-id",
        help="Optional stable document id to carry into later task-validation input.",
    )
    task_protocol_parser.add_argument(
        "--document-type",
        default="internal_documentation",
        help="Document type to carry into later task-validation input.",
    )
    task_protocol_parser.add_argument(
        "--output",
        help="Optional JSON, Markdown, or directory output for the task-observation protocol.",
    )
    task_protocol_parser.add_argument(
        "--json-errors",
        action="store_true",
        help="Emit machine-readable errors if protocol generation is blocked.",
    )

    task_input_parser = subparsers.add_parser(
        "task-input",
        parents=[common_output_parser],
        help="Convert a task-observation protocol and filled session CSV into task-validation input JSON.",
    )
    task_input_parser.add_argument(
        "--protocol",
        required=True,
        help="Path to documentation-task-observation-protocol.json.",
    )
    task_input_parser.add_argument(
        "--sessions-csv",
        required=True,
        help="Path to a filled documentation-task-session-template.csv file.",
    )
    task_input_parser.add_argument(
        "--validation-id",
        help="Optional validation id. Defaults to a deterministic id from protocol and sessions.",
    )
    task_input_parser.add_argument(
        "--observation-source",
        choices=["synthetic_fixture", "real_task_observation"],
        default="synthetic_fixture",
        help=(
            "Provenance for the filled session CSV. Defaults to synthetic_fixture so generated or test-filled rows "
            "cannot be promoted into real task evidence without an explicit declaration."
        ),
    )
    task_input_parser.add_argument(
        "--output",
        help="Optional JSON file path or directory for task-validation input.",
    )
    task_input_parser.add_argument(
        "--json-errors",
        action="store_true",
        help="Emit machine-readable errors if input generation is blocked.",
    )

    improvement_parser = subparsers.add_parser(
        "improvement-plan",
        parents=[common_output_parser],
        help="Build a ranked next-action backlog from stored Mindfront history.",
    )
    improvement_parser.add_argument("--db", required=True, help="SQLite database path.")
    improvement_parser.add_argument(
        "--brief-id",
        help="Optional brief id filter for the improvement backlog.",
    )
    improvement_parser.add_argument(
        "--max-actions",
        type=int,
        default=10,
        help="Maximum number of ranked actions to emit. Defaults to 10.",
    )
    improvement_parser.add_argument(
        "--output",
        help="Optional JSON, Markdown, or directory output for the improvement plan.",
    )
    improvement_parser.add_argument(
        "--json-errors",
        action="store_true",
        help="Emit machine-readable errors if improvement planning is blocked.",
    )

    store_parser = subparsers.add_parser("store", help="Manage the local SQLite artifact history store.")
    store_subparsers = store_parser.add_subparsers(dest="store_command")

    store_init_parser = store_subparsers.add_parser(
        "init",
        parents=[common_output_parser],
        help="Initialize a Mindfront SQLite store.",
    )
    store_init_parser.add_argument("--db", required=True, help="SQLite database path.")
    store_init_parser.add_argument("--json-errors", action="store_true", help="Emit machine-readable errors.")

    store_ingest_parser = store_subparsers.add_parser(
        "ingest",
        parents=[common_output_parser],
        help="Ingest a Mindfront artifact set.",
    )
    store_ingest_parser.add_argument("--db", required=True, help="SQLite database path.")
    store_ingest_parser.add_argument("--analysis", required=True, help="Message analysis report JSON path.")
    store_ingest_parser.add_argument("--variants", help="Optional copy variant bundle JSON path.")
    store_ingest_parser.add_argument("--comparison", help="Optional variant comparison report JSON path.")
    store_ingest_parser.add_argument("--stress", help="Optional reader stress-test report JSON path.")
    store_ingest_parser.add_argument("--research-plan", help="Optional research plan JSON path.")
    store_ingest_parser.add_argument("--report", help="Optional audit report bundle JSON path.")
    store_ingest_parser.add_argument("--task-protocol", help="Optional documentation task-observation protocol JSON path.")
    store_ingest_parser.add_argument("--task-validation", help="Optional documentation task-validation result JSON path.")
    store_ingest_parser.add_argument("--json-errors", action="store_true", help="Emit machine-readable errors.")

    store_list_parser = store_subparsers.add_parser(
        "list-analyses",
        parents=[common_output_parser],
        help="List stored analyses.",
    )
    store_list_parser.add_argument("--db", required=True, help="SQLite database path.")
    store_list_parser.add_argument("--output", help="Optional JSON file or directory output.")
    store_list_parser.add_argument("--json-errors", action="store_true", help="Emit machine-readable errors.")

    store_compare_parser = store_subparsers.add_parser(
        "compare",
        parents=[common_output_parser],
        help="Compare stored analysis history.",
    )
    store_compare_parser.add_argument("--db", required=True, help="SQLite database path.")
    store_compare_parser.add_argument("--brief-id", help="Optional brief id filter.")
    store_compare_parser.add_argument("--output", help="Optional JSON file or directory output.")
    store_compare_parser.add_argument("--json-errors", action="store_true", help="Emit machine-readable errors.")

    store_export_parser = store_subparsers.add_parser(
        "export",
        parents=[common_output_parser],
        help="Export the SQLite store as JSON.",
    )
    store_export_parser.add_argument("--db", required=True, help="SQLite database path.")
    store_export_parser.add_argument("--output", required=True, help="JSON file or directory output.")
    store_export_parser.add_argument("--json-errors", action="store_true", help="Emit machine-readable errors.")

    store_delete_parser = store_subparsers.add_parser(
        "delete-run",
        parents=[common_output_parser],
        help="Delete one stored run and dependent rows.",
    )
    store_delete_parser.add_argument("--db", required=True, help="SQLite database path.")
    store_delete_parser.add_argument("--run-id", required=True, help="Stored run id to delete.")
    store_delete_parser.add_argument("--json-errors", action="store_true", help="Emit machine-readable errors.")

    store_stale_parser = store_subparsers.add_parser(
        "check-stale",
        parents=[common_output_parser],
        help="Check stored artifact paths and hashes for stale runs.",
    )
    store_stale_parser.add_argument("--db", required=True, help="SQLite database path.")
    store_stale_parser.add_argument("--output", help="Optional JSON file or directory output.")
    store_stale_parser.add_argument("--json-errors", action="store_true", help="Emit machine-readable errors.")

    dashboard_parser = subparsers.add_parser("dashboard", help="Build a static local dashboard from the store.")
    dashboard_subparsers = dashboard_parser.add_subparsers(dest="dashboard_command")
    dashboard_build_parser = dashboard_subparsers.add_parser(
        "build",
        parents=[common_output_parser],
        help="Build dashboard JSON and HTML.",
    )
    dashboard_build_parser.add_argument("--db", required=True, help="SQLite database path.")
    dashboard_build_parser.add_argument("--output", required=True, help="Dashboard output directory.")
    dashboard_build_parser.add_argument("--json-errors", action="store_true", help="Emit machine-readable errors.")

    vault_parser = subparsers.add_parser(
        "vault",
        help="Manage the installation-local key and encrypted private vault formats.",
    )
    vault_subparsers = vault_parser.add_subparsers(dest="vault_command")

    vault_init_parser = vault_subparsers.add_parser(
        "init-key",
        help="Create or validate the installation-local Mindfront vault key.",
    )
    vault_init_parser.add_argument("--key-file", help="Optional key path override.")
    vault_init_parser.add_argument("--json-errors", action="store_true", help="Emit machine-readable errors.")

    vault_status_parser = vault_subparsers.add_parser(
        "key-status",
        help="Validate the configured key without exposing key material.",
    )
    vault_status_parser.add_argument("--key-file", help="Optional key path override.")
    vault_status_parser.add_argument("--json-errors", action="store_true", help="Emit machine-readable errors.")

    vault_inspect_parser = vault_subparsers.add_parser(
        "inspect",
        help="Inspect non-secret vault envelope metadata without decrypting it.",
    )
    vault_inspect_parser.add_argument("--path", required=True, help="Encrypted vault path.")
    vault_inspect_parser.add_argument("--json-errors", action="store_true", help="Emit machine-readable errors.")

    vault_migrate_parser = vault_subparsers.add_parser(
        "migrate",
        help="Migrate one readable legacy DPAPI vault without exposing plaintext.",
    )
    vault_migrate_parser.add_argument("--path", required=True, help="Encrypted vault path.")
    vault_migrate_parser.add_argument("--json-errors", action="store_true", help="Emit machine-readable errors.")

    assist_parser = subparsers.add_parser(
        "assist",
        help="Run private first-party workplace communication assistance.",
    )
    assist_subparsers = assist_parser.add_subparsers(dest="assist_command")
    assist_profile_parser = assist_subparsers.add_parser(
        "profile",
        help="Manage the current user's encrypted self-declared assistance profile.",
    )
    assist_profile_subparsers = assist_profile_parser.add_subparsers(dest="assist_profile_command")

    assist_profile_validate_parser = assist_profile_subparsers.add_parser(
        "validate",
        parents=[common_output_parser],
        help="Validate a self-declared assistance profile without storing it.",
    )
    assist_profile_validate_parser.add_argument("--input", required=True, help="Self-profile JSON path.")
    assist_profile_validate_parser.add_argument("--output", help="Optional validation JSON path or directory.")
    assist_profile_validate_parser.add_argument("--json-errors", action="store_true", help="Emit machine-readable errors.")

    assist_profile_upsert_parser = assist_profile_subparsers.add_parser(
        "upsert",
        parents=[common_output_parser],
        help="Create or replace the installation-local encrypted self profile.",
    )
    assist_profile_upsert_parser.add_argument("--input", required=True, help="Self-profile JSON path.")
    assist_profile_upsert_parser.add_argument(
        "--store",
        default="runtime-data/self-workplace-assistance.vault",
        help="Encrypted self-profile store path.",
    )
    assist_profile_upsert_parser.add_argument("--output", help="Optional result JSON path or directory.")
    assist_profile_upsert_parser.add_argument("--json-errors", action="store_true", help="Emit machine-readable errors.")

    assist_profile_show_parser = assist_profile_subparsers.add_parser(
        "show",
        parents=[common_output_parser],
        help="Show the current user's decrypted private self profile.",
    )
    assist_profile_show_parser.add_argument(
        "--store",
        default="runtime-data/self-workplace-assistance.vault",
        help="Encrypted self-profile store path.",
    )
    assist_profile_show_parser.add_argument("--output", help="Optional private JSON path or directory.")
    assist_profile_show_parser.add_argument("--json-errors", action="store_true", help="Emit machine-readable errors.")

    assist_profile_context_parser = assist_profile_subparsers.add_parser(
        "context",
        parents=[common_output_parser],
        help="Emit bounded private personalization context for inline assistance.",
    )
    assist_profile_context_parser.add_argument(
        "--store",
        default="runtime-data/self-workplace-assistance.vault",
        help="Encrypted self-profile store path.",
    )
    assist_profile_context_parser.add_argument(
        "--output",
        help="Optional private JSON path or directory.",
    )
    assist_profile_context_parser.add_argument(
        "--json-errors",
        action="store_true",
        help="Emit machine-readable errors.",
    )

    assist_profile_delete_parser = assist_profile_subparsers.add_parser(
        "delete",
        parents=[common_output_parser],
        help="Delete the current user's encrypted self profile.",
    )
    assist_profile_delete_parser.add_argument(
        "--store",
        default="runtime-data/self-workplace-assistance.vault",
        help="Encrypted self-profile store path.",
    )
    assist_profile_delete_parser.add_argument("--output", help="Optional deletion result JSON path or directory.")
    assist_profile_delete_parser.add_argument("--json-errors", action="store_true", help="Emit machine-readable errors.")

    for assist_command, assist_help in (
        ("preflight", "Prepare a message, meeting, decision, or executive update."),
        ("interpret", "Interpret an ambiguous workplace message without asserting motives."),
        ("debrief", "Separate decisions, commitments, owners, dates, and unresolved items."),
        ("career-review", "Review the user's own career evidence without predicting promotion."),
    ):
        mode_parser = assist_subparsers.add_parser(
            assist_command,
            parents=[common_output_parser],
            help=assist_help,
        )
        mode_parser.add_argument("--input", required=True, help="Private workplace-assistance request JSON path.")
        mode_parser.add_argument(
            "--self-store",
            default="runtime-data/self-workplace-assistance.vault",
            help="Encrypted self-profile store path.",
        )
        mode_parser.add_argument(
            "--policy",
            default="config/workplace-assistance-policy.json",
            help="Source-owned workplace-assistance policy path.",
        )
        mode_parser.add_argument(
            "--recipient-guidance",
            help="Optional already-validated private interaction-assistance guidance JSON path.",
        )
        mode_parser.add_argument("--output", help="Optional private result JSON path or directory.")
        mode_parser.add_argument("--json-errors", action="store_true", help="Emit machine-readable errors.")

    profile_parser = subparsers.add_parser(
        "profile",
        help="Manage the private encrypted interaction-assistance profile store.",
    )
    profile_subparsers = profile_parser.add_subparsers(dest="profile_command")

    profile_validate_parser = profile_subparsers.add_parser(
        "validate",
        parents=[common_output_parser],
        help="Validate a feature-only communication observation bundle.",
    )
    profile_validate_parser.add_argument("--input", required=True, help="Observation bundle JSON path.")
    profile_validate_parser.add_argument("--output", help="Optional validation result JSON path or directory.")
    profile_validate_parser.add_argument("--json-errors", action="store_true", help="Emit machine-readable errors.")

    profile_build_parser = profile_subparsers.add_parser(
        "build",
        parents=[common_output_parser],
        help="Build a profile preview without storing it.",
    )
    profile_build_parser.add_argument("--input", required=True, help="Observation bundle JSON path.")
    profile_build_parser.add_argument("--output", help="Optional profile preview JSON path or directory.")
    profile_build_parser.add_argument("--json-errors", action="store_true", help="Emit machine-readable errors.")

    profile_upsert_parser = profile_subparsers.add_parser(
        "upsert",
        parents=[common_output_parser],
        help="Create or update a profile in the installation-local encrypted store.",
    )
    profile_upsert_parser.add_argument("--input", required=True, help="Observation bundle JSON path.")
    profile_upsert_parser.add_argument("--store", required=True, help="Encrypted profile store path.")
    profile_upsert_parser.add_argument("--output", help="Optional result JSON path or directory.")
    profile_upsert_parser.add_argument("--json-errors", action="store_true", help="Emit machine-readable errors.")

    profile_show_parser = profile_subparsers.add_parser(
        "show",
        parents=[common_output_parser],
        help="Show one named profile.",
    )
    profile_show_parser.add_argument("--store", required=True, help="Encrypted profile store path.")
    profile_show_parser.add_argument("--name", required=True, help="Exact profile display name.")
    profile_show_parser.add_argument(
        "--include-collecting",
        action="store_true",
        help="Allow a profile that has not met the automatic-use threshold.",
    )
    profile_show_parser.add_argument("--output", help="Optional profile JSON path or directory.")
    profile_show_parser.add_argument("--json-errors", action="store_true", help="Emit machine-readable errors.")

    profile_context_parser = profile_subparsers.add_parser(
        "context",
        parents=[common_output_parser],
        help="Emit bounded assistive drafting guidance for one active profile.",
    )
    profile_context_parser.add_argument("--store", required=True, help="Encrypted profile store path.")
    profile_context_parser.add_argument("--name", required=True, help="Exact profile display name.")
    profile_context_parser.add_argument(
        "--vault",
        help="Optional encrypted communication vault used to verify current source lineage.",
    )
    profile_context_parser.add_argument(
        "--context",
        choices=sorted(ALLOWED_CONTEXTS),
        help="Optional context filter for the private guidance.",
    )
    profile_context_parser.add_argument("--output", help="Optional guidance JSON path or directory.")
    profile_context_parser.add_argument("--json-errors", action="store_true", help="Emit machine-readable errors.")

    profile_list_parser = profile_subparsers.add_parser(
        "list",
        parents=[common_output_parser],
        help="List named profiles and readiness states.",
    )
    profile_list_parser.add_argument("--store", required=True, help="Encrypted profile store path.")
    profile_list_parser.add_argument("--output", help="Optional index JSON path or directory.")
    profile_list_parser.add_argument("--json-errors", action="store_true", help="Emit machine-readable errors.")

    profile_delete_parser = profile_subparsers.add_parser(
        "delete",
        parents=[common_output_parser],
        help="Delete one named profile and all of its derived batches.",
    )
    profile_delete_parser.add_argument("--store", required=True, help="Encrypted profile store path.")
    profile_delete_parser.add_argument("--name", required=True, help="Exact profile display name.")
    profile_delete_parser.add_argument("--output", help="Optional deletion result JSON path or directory.")
    profile_delete_parser.add_argument("--json-errors", action="store_true", help="Emit machine-readable errors.")

    profile_invalidate_parser = profile_subparsers.add_parser(
        "invalidate-batch",
        parents=[common_output_parser],
        help="Remove one source batch and recompute affected profiles.",
    )
    profile_invalidate_parser.add_argument("--store", required=True, help="Encrypted profile store path.")
    profile_invalidate_parser.add_argument("--bundle-id", required=True, help="Source bundle id to remove.")
    profile_invalidate_parser.add_argument("--output", help="Optional invalidation result JSON path or directory.")
    profile_invalidate_parser.add_argument("--json-errors", action="store_true", help="Emit machine-readable errors.")

    corpus_parser = subparsers.add_parser(
        "corpus",
        help="Manage the installation-local encrypted full-message communication vault.",
    )
    corpus_subparsers = corpus_parser.add_subparsers(dest="corpus_command")

    corpus_validate_parser = corpus_subparsers.add_parser(
        "validate",
        parents=[common_output_parser],
        help="Validate a full-message communication corpus batch.",
    )
    corpus_validate_parser.add_argument("--input", required=True, help="Corpus batch JSON path.")
    corpus_validate_parser.add_argument("--output", help="Optional validation JSON path or directory.")
    corpus_validate_parser.add_argument("--json-errors", action="store_true", help="Emit machine-readable errors.")

    corpus_ingest_parser = corpus_subparsers.add_parser(
        "ingest",
        parents=[common_output_parser],
        help="Ingest complete messages into the encrypted vault.",
    )
    corpus_ingest_parser.add_argument("--input", required=True, help="Corpus batch JSON path.")
    corpus_ingest_parser.add_argument("--vault", required=True, help="Encrypted communication vault path.")
    corpus_ingest_parser.add_argument("--output", help="Optional ingest result JSON path or directory.")
    corpus_ingest_parser.add_argument("--json-errors", action="store_true", help="Emit machine-readable errors.")

    for command, help_text in (
        (
            "ingest-outlook-export",
            "Convert an Outlook connector export and ingest full messages directly into the encrypted vault.",
        ),
        (
            "ingest-teams-export",
            "Convert a Teams connector export and ingest full messages directly into the encrypted vault.",
        ),
    ):
        adapter_parser = corpus_subparsers.add_parser(
            command,
            parents=[common_output_parser],
            help=help_text,
        )
        adapter_parser.add_argument("--input", required=True, help="Temporary connector export JSON path.")
        adapter_parser.add_argument("--vault", required=True, help="Encrypted communication vault path.")
        adapter_parser.add_argument("--batch-id", required=True, help="Stable corpus-batch-* identifier.")
        adapter_parser.add_argument("--output", help="Optional ingest result JSON path or directory.")
        adapter_parser.add_argument("--json-errors", action="store_true", help="Emit machine-readable errors.")

    freshservice_parser = corpus_subparsers.add_parser(
        "ingest-freshservice-jsonl",
        parents=[common_output_parser],
        help="Validate a normalized Freshservice source pack and ingest resolved-ticket messages directly.",
    )
    freshservice_parser.add_argument("--input", required=True, help="freshservice-agent-cases.jsonl path.")
    freshservice_parser.add_argument(
        "--cleaning-manifest",
        required=True,
        help="Companion cleaning-manifest.json path.",
    )
    freshservice_parser.add_argument(
        "--export-manifest",
        required=True,
        help="Companion export-manifest.json path.",
    )
    freshservice_parser.add_argument(
        "--identity-map",
        help="Optional freshservice_identity_map JSON path for exact email or user-id resolution.",
    )
    freshservice_parser.add_argument("--vault", required=True, help="Encrypted communication vault path.")
    freshservice_parser.add_argument("--batch-id", required=True, help="Stable corpus-batch-* identifier.")
    freshservice_parser.add_argument("--output", help="Optional ingest result JSON path or directory.")
    freshservice_parser.add_argument("--json-errors", action="store_true", help="Emit machine-readable errors.")

    corpus_list_parser = corpus_subparsers.add_parser(
        "list-people",
        parents=[common_output_parser],
        help="List people and source coverage in the encrypted vault.",
    )
    corpus_list_parser.add_argument("--vault", required=True, help="Encrypted communication vault path.")
    corpus_list_parser.add_argument("--output", help="Optional people index JSON path or directory.")
    corpus_list_parser.add_argument("--json-errors", action="store_true", help="Emit machine-readable errors.")

    corpus_context_parser = corpus_subparsers.add_parser(
        "context",
        parents=[common_output_parser],
        help="Retrieve relevant complete messages for private assistive drafting.",
    )
    corpus_context_parser.add_argument("--vault", required=True, help="Encrypted communication vault path.")
    corpus_context_parser.add_argument("--name", required=True, help="Exact author display name.")
    corpus_context_parser.add_argument("--context", choices=sorted(ALLOWED_CONTEXTS), help="Optional context filter.")
    corpus_context_parser.add_argument("--limit", type=int, default=30, help="Maximum messages, 1-100.")
    corpus_context_parser.add_argument(
        "--include-thread-context",
        action="store_true",
        help="Include every ingested message from the most relevant selected conversations.",
    )
    corpus_context_parser.add_argument(
        "--thread-limit",
        type=int,
        default=5,
        help="Maximum complete ingested conversations to return with --include-thread-context, 1-20.",
    )
    corpus_context_parser.add_argument("--output", help="Optional private context JSON path or directory.")
    corpus_context_parser.add_argument("--json-errors", action="store_true", help="Emit machine-readable errors.")

    corpus_derive_parser = corpus_subparsers.add_parser(
        "derive-profile",
        parents=[common_output_parser],
        help="Derive a feature-only profile observation bundle from complete messages.",
    )
    corpus_derive_parser.add_argument("--vault", required=True, help="Encrypted communication vault path.")
    corpus_derive_parser.add_argument("--name", required=True, help="Exact author display name.")
    corpus_derive_parser.add_argument("--output", help="Optional observation bundle JSON path or directory.")
    corpus_derive_parser.add_argument("--json-errors", action="store_true", help="Emit machine-readable errors.")

    corpus_refresh_parser = corpus_subparsers.add_parser(
        "refresh-profile",
        parents=[common_output_parser],
        help="Derive and upsert one named profile from the encrypted communication vault.",
    )
    corpus_refresh_parser.add_argument("--vault", required=True, help="Encrypted communication vault path.")
    corpus_refresh_parser.add_argument("--profile-store", required=True, help="Encrypted interaction profile store path.")
    corpus_refresh_parser.add_argument("--name", required=True, help="Exact author display name.")
    corpus_refresh_parser.add_argument("--output", help="Optional refresh result JSON path or directory.")
    corpus_refresh_parser.add_argument("--json-errors", action="store_true", help="Emit machine-readable errors.")

    corpus_refresh_all_parser = corpus_subparsers.add_parser(
        "refresh-all-profiles",
        parents=[common_output_parser],
        help="Derive and replace every named profile snapshot from the encrypted communication vault.",
    )
    corpus_refresh_all_parser.add_argument("--vault", required=True, help="Encrypted communication vault path.")
    corpus_refresh_all_parser.add_argument(
        "--profile-store",
        required=True,
        help="Encrypted interaction profile store path.",
    )
    corpus_refresh_all_parser.add_argument(
        "--output",
        help="Optional count-only refresh result JSON path or directory.",
    )
    corpus_refresh_all_parser.add_argument(
        "--json-errors",
        action="store_true",
        help="Emit machine-readable errors.",
    )

    corpus_delete_parser = corpus_subparsers.add_parser(
        "delete-person",
        parents=[common_output_parser],
        help="Delete complete messages authored by one person.",
    )
    corpus_delete_parser.add_argument("--vault", required=True, help="Encrypted communication vault path.")
    corpus_delete_parser.add_argument("--name", required=True, help="Exact author display name.")
    corpus_delete_parser.add_argument("--output", help="Optional deletion result JSON path or directory.")
    corpus_delete_parser.add_argument("--json-errors", action="store_true", help="Emit machine-readable errors.")

    corpus_invalidate_parser = corpus_subparsers.add_parser(
        "invalidate-batch",
        parents=[common_output_parser],
        help="Remove one connector batch and unreferenced complete messages.",
    )
    corpus_invalidate_parser.add_argument("--vault", required=True, help="Encrypted communication vault path.")
    corpus_invalidate_parser.add_argument("--batch-id", required=True, help="Corpus batch id to invalidate.")
    corpus_invalidate_parser.add_argument("--output", help="Optional invalidation result JSON path or directory.")
    corpus_invalidate_parser.add_argument("--json-errors", action="store_true", help="Emit machine-readable errors.")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "validate":
        result = validate_workspace(
            Path(args.config_root),
            strict=args.strict,
            brief_root=Path(args.brief_root),
            task_validation_root=Path(args.task_validation_root),
        )
        if args.output:
            try:
                destination = _resolve_output_destination(Path(args.output), args.overwrite)
            except OutputConflictError as exc:
                _print_output_conflict(exc, json_errors=args.json_errors)
                return 4
            if args.dry_run:
                _print_dry_run(
                    "validate",
                    [destination],
                    {
                        "validation": result.to_dict(),
                        "noExternalLlm": bool(args.no_external_llm),
                    },
                )
                return result.exit_code
            output_path = _write_json_output(result.to_dict(), destination, "validation-report.json")
            print(f"Mindfront validation report written: {output_path}")
            return result.exit_code
        if args.dry_run:
            _print_dry_run(
                "validate",
                [],
                {
                    "validation": result.to_dict(),
                    "noExternalLlm": bool(args.no_external_llm),
                },
            )
            return result.exit_code
        _print_validation_result(result, json_errors=args.json_errors)
        return result.exit_code

    if args.command == "analyze":
        try:
            interaction_profile = _profile_from_args(args)
            report = analyze_message_brief(
                Path(args.brief),
                config_root=Path(args.config_root),
                interaction_profile=interaction_profile,
                interaction_profile_context=args.profile_context,
            )
        except AnalysisBlockedError as exc:
            _print_analysis_blocked(exc, json_errors=args.json_errors)
            return 1
        except InteractionProfileBlockedError as exc:
            _print_interaction_profile_blocked(exc, json_errors=args.json_errors)
            return 1

        if args.output:
            destination = _resolve_or_print_output_destination(args.output, args.overwrite, args.json_errors)
            if destination is None:
                return 4
            if args.dry_run:
                _print_dry_run("analyze", [destination], {"reportId": report["reportId"]})
                return 0
            output_path = write_analysis_report(report, destination)
            print(f"Mindfront analysis report written: {output_path}")
            return 0

        if args.dry_run:
            _print_dry_run("analyze", [], {"reportId": report["reportId"]})
            return 0
        print(json.dumps(finalize_analysis_report(report), indent=2, sort_keys=True))
        return 0

    if args.command == "rewrite":
        try:
            interaction_profile = _profile_from_args(args)
            bundle = rewrite_message_brief(
                Path(args.brief),
                config_root=Path(args.config_root),
                strategies=args.strategy,
                interaction_profile=interaction_profile,
                interaction_profile_context=args.profile_context,
            )
        except AnalysisBlockedError as exc:
            _print_analysis_blocked(exc, json_errors=args.json_errors)
            return 1
        except RewriteBlockedError as exc:
            _print_rewrite_blocked(exc, json_errors=args.json_errors)
            return 2
        except InteractionProfileBlockedError as exc:
            _print_interaction_profile_blocked(exc, json_errors=args.json_errors)
            return 1

        if args.output:
            destination = _resolve_or_print_output_destination(args.output, args.overwrite, args.json_errors)
            if destination is None:
                return 4
            if args.dry_run:
                _print_dry_run("rewrite", [destination], {"bundleId": bundle["bundleId"]})
                return 0
            output_path = write_rewrite_bundle(bundle, destination)
            print(f"Mindfront copy variants written: {output_path}")
            return 0

        if args.dry_run:
            _print_dry_run("rewrite", [], {"bundleId": bundle["bundleId"]})
            return 0
        print(json.dumps(finalize_rewrite_bundle(bundle), indent=2, sort_keys=True))
        return 0

    if args.command == "compare":
        try:
            report = compare_variant_bundle(Path(args.variants))
        except CompareBlockedError as exc:
            _print_compare_blocked(exc, json_errors=args.json_errors)
            return 1

        if args.output:
            destination = _resolve_or_print_output_destination(args.output, args.overwrite, args.json_errors)
            if destination is None:
                return 4
            if args.dry_run:
                _print_dry_run("compare", [destination], {"comparisonId": report["comparisonId"]})
                return 0
            output_path = write_comparison_report(report, destination)
            print(f"Mindfront variant comparison written: {output_path}")
            return 0

        if args.dry_run:
            _print_dry_run("compare", [], {"comparisonId": report["comparisonId"]})
            return 0
        print(json.dumps(finalize_comparison_report(report), indent=2, sort_keys=True))
        return 0

    if args.command == "reader-stress-test":
        try:
            report = run_reader_stress_test(
                Path(args.analysis),
                config_root=Path(args.config_root),
                lens_ids=args.lens,
            )
        except StressTestBlockedError as exc:
            _print_stress_blocked(exc, json_errors=args.json_errors)
            return 1

        if args.output:
            destination = _resolve_or_print_output_destination(args.output, args.overwrite, args.json_errors)
            if destination is None:
                return 4
            if args.dry_run:
                _print_dry_run("reader-stress-test", [destination], {"stressReportId": report["stressReportId"]})
                return 0
            output_path = write_stress_report(report, destination)
            print(f"Mindfront reader stress test written: {output_path}")
            return 0

        if args.dry_run:
            _print_dry_run("reader-stress-test", [], {"stressReportId": report["stressReportId"]})
            return 0
        print(json.dumps(finalize_stress_report(report), indent=2, sort_keys=True))
        return 0

    if args.command == "research-plan":
        try:
            plan = build_research_plan(Path(args.analysis))
        except ResearchPlanBlockedError as exc:
            _print_research_plan_blocked(exc, json_errors=args.json_errors)
            return 1

        if args.output:
            destination = _resolve_or_print_output_destination(args.output, args.overwrite, args.json_errors)
            if destination is None:
                return 4
            if args.dry_run:
                _print_dry_run("research-plan", [destination], {"researchPlanId": plan["researchPlanId"]})
                return 0
            output_paths = write_research_plan(plan, destination)
            formatted = ", ".join(str(path) for path in output_paths)
            print(f"Mindfront research plan written: {formatted}")
            return 0

        if args.dry_run:
            _print_dry_run("research-plan", [], {"researchPlanId": plan["researchPlanId"]})
            return 0
        print(json.dumps(finalize_research_plan(plan), indent=2, sort_keys=True))
        return 0

    if args.command == "report":
        try:
            bundle = build_report_bundle(
                Path(args.analysis),
                config_root=Path(args.config_root),
                variants_path=Path(args.variants) if args.variants else None,
                comparison_path=Path(args.comparison) if args.comparison else None,
                stress_path=Path(args.stress) if args.stress else None,
                research_plan_path=Path(args.research_plan) if args.research_plan else None,
                task_protocol_path=Path(args.task_protocol) if args.task_protocol else None,
                task_validation_path=Path(args.task_validation) if args.task_validation else None,
            )
        except ReportBundleBlockedError as exc:
            _print_report_bundle_blocked(exc, json_errors=args.json_errors)
            return 1

        if args.output:
            destination = _resolve_or_print_output_destination(args.output, args.overwrite, args.json_errors)
            if destination is None:
                return 4
            if args.dry_run:
                _print_dry_run("report", [destination], {"reportBundleId": bundle["reportBundleId"]})
                return 0
            output_paths = write_report_bundle(bundle, destination)
            formatted = ", ".join(str(path) for path in output_paths)
            print(f"Mindfront audit report written: {formatted}")
            return 0

        if args.dry_run:
            _print_dry_run("report", [], {"reportBundleId": bundle["reportBundleId"]})
            return 0
        print(json.dumps(finalize_report_bundle(bundle), indent=2, sort_keys=True))
        return 0

    if args.command == "task-validation":
        try:
            result = build_task_validation_result(
                Path(args.input),
                analysis_path=Path(args.analysis) if args.analysis else None,
            )
        except TaskValidationBlockedError as exc:
            _print_task_validation_blocked(exc, json_errors=args.json_errors)
            return 1

        if args.output:
            destination = _resolve_or_print_output_destination(args.output, args.overwrite, args.json_errors)
            if destination is None:
                return 4
            if args.dry_run:
                _print_dry_run("task-validation", [destination], {"validationResultId": result["validationResultId"]})
                return 0
            output_path = write_task_validation_result(result, destination)
            print(f"Mindfront task validation result written: {output_path}")
            return 0

        if args.dry_run:
            _print_dry_run("task-validation", [], {"validationResultId": result["validationResultId"]})
            return 0
        print(json.dumps(finalize_task_validation_result(result), indent=2, sort_keys=True))
        return 0

    if args.command == "task-protocol":
        try:
            protocol = build_task_observation_protocol(
                Path(args.analysis),
                research_plan_path=Path(args.research_plan) if args.research_plan else None,
                document_id=args.document_id,
                document_type=args.document_type,
            )
        except TaskProtocolBlockedError as exc:
            _print_task_protocol_blocked(exc, json_errors=args.json_errors)
            return 1

        if args.output:
            destination = _resolve_or_print_output_destination(args.output, args.overwrite, args.json_errors)
            if destination is None:
                return 4
            if args.dry_run:
                _print_dry_run("task-protocol", [destination], {"protocolId": protocol["protocolId"]})
                return 0
            output_paths = write_task_observation_protocol(protocol, destination)
            print("Mindfront task observation protocol written: " + ", ".join(str(path) for path in output_paths))
            return 0

        if args.dry_run:
            _print_dry_run("task-protocol", [], {"protocolId": protocol["protocolId"]})
            return 0
        print(json.dumps(finalize_task_observation_protocol(protocol), indent=2, sort_keys=True))
        return 0

    if args.command == "task-input":
        try:
            task_input = build_task_validation_input_from_protocol(
                Path(args.protocol),
                Path(args.sessions_csv),
                validation_id=args.validation_id,
                observation_source=args.observation_source,
            )
        except TaskInputBlockedError as exc:
            _print_task_input_blocked(exc, json_errors=args.json_errors)
            return 1

        if args.output:
            destination = _resolve_or_print_output_destination(args.output, args.overwrite, args.json_errors)
            if destination is None:
                return 4
            if args.dry_run:
                _print_dry_run("task-input", [destination], {"validationId": task_input["validationId"]})
                return 0
            output_path = write_task_validation_input(task_input, destination)
            print(f"Mindfront task validation input written: {output_path}")
            return 0

        if args.dry_run:
            _print_dry_run("task-input", [], {"validationId": task_input["validationId"]})
            return 0
        print(json.dumps(task_input, indent=2, sort_keys=True))
        return 0

    if args.command == "improvement-plan":
        try:
            plan = build_improvement_plan(
                Path(args.db),
                brief_id=args.brief_id,
                max_actions=args.max_actions,
            )
        except ImprovementPlanBlockedError as exc:
            _print_improvement_plan_blocked(exc, json_errors=args.json_errors)
            return 1

        if args.output:
            destination = _resolve_or_print_output_destination(args.output, args.overwrite, args.json_errors)
            if destination is None:
                return 4
            if args.dry_run:
                _print_dry_run(
                    "improvement-plan",
                    [destination],
                    {"planId": plan["planId"], "actionCount": plan["actionCount"]},
                )
                return 0
            output_paths = write_improvement_plan(plan, destination)
            formatted = ", ".join(str(path) for path in output_paths)
            print(f"Mindfront improvement plan written: {formatted}")
            return 0

        if args.dry_run:
            _print_dry_run("improvement-plan", [], {"planId": plan["planId"], "actionCount": plan["actionCount"]})
            return 0
        print(json.dumps(finalize_improvement_plan(plan), indent=2, sort_keys=True))
        return 0

    if args.command == "vault":
        return _handle_vault_command(args, parser)

    if args.command == "store":
        return _handle_store_command(args, parser)

    if args.command == "dashboard":
        return _handle_dashboard_command(args, parser)

    if args.command == "assist":
        return _handle_assist_command(args, parser)

    if args.command == "profile":
        return _handle_profile_command(args, parser)

    if args.command == "corpus":
        return _handle_corpus_command(args, parser)

    parser.print_help(sys.stderr)
    return 3


def _print_validation_result(result: ValidationResult, *, json_errors: bool) -> None:
    if json_errors:
        print(json.dumps(result.to_dict(), indent=2, sort_keys=True))
        return

    if result.ok:
        print(f"Mindfront config validation passed: {result.config_root}")
        return

    print(f"Mindfront config validation failed: {result.config_root}", file=sys.stderr)
    for error in result.errors:
        print(f"- {error.code} at {error.path}: {error.message}", file=sys.stderr)


def _print_analysis_blocked(error: AnalysisBlockedError, *, json_errors: bool) -> None:
    payload = {
        "status": "failed",
        "exitCode": 1,
        "errors": [validation_error.to_dict() for validation_error in error.errors],
    }
    if json_errors:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return

    print("Mindfront analysis blocked by validation errors.", file=sys.stderr)
    for validation_error in error.errors:
        print(f"- {validation_error.code} at {validation_error.path}: {validation_error.message}", file=sys.stderr)


def _print_rewrite_blocked(error: RewriteBlockedError, *, json_errors: bool) -> None:
    payload = {
        "status": "blocked",
        "exitCode": 2,
        "errors": error.reasons,
    }
    if json_errors:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return

    print("Mindfront rewrite blocked.", file=sys.stderr)
    for reason in error.reasons:
        print(f"- {reason['code']} at {reason['path']}: {reason['message']}", file=sys.stderr)


def _print_compare_blocked(error: CompareBlockedError, *, json_errors: bool) -> None:
    payload = {
        "status": "failed",
        "exitCode": 1,
        "errors": error.reasons,
    }
    if json_errors:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return

    print("Mindfront comparison blocked.", file=sys.stderr)
    for reason in error.reasons:
        print(f"- {reason['code']} at {reason['path']}: {reason['message']}", file=sys.stderr)


def _print_stress_blocked(error: StressTestBlockedError, *, json_errors: bool) -> None:
    payload = {
        "status": "failed",
        "exitCode": 1,
        "errors": error.reasons,
    }
    if json_errors:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return

    print("Mindfront reader stress test blocked.", file=sys.stderr)
    for reason in error.reasons:
        print(f"- {reason['code']} at {reason['path']}: {reason['message']}", file=sys.stderr)


def _print_research_plan_blocked(error: ResearchPlanBlockedError, *, json_errors: bool) -> None:
    payload = {
        "status": "failed",
        "exitCode": 1,
        "errors": error.reasons,
    }
    if json_errors:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return

    print("Mindfront research plan blocked.", file=sys.stderr)
    for reason in error.reasons:
        print(f"- {reason['code']} at {reason['path']}: {reason['message']}", file=sys.stderr)


def _print_report_bundle_blocked(error: ReportBundleBlockedError, *, json_errors: bool) -> None:
    payload = {
        "status": "failed",
        "exitCode": 1,
        "errors": error.reasons,
    }
    if json_errors:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return

    print("Mindfront audit report blocked.", file=sys.stderr)
    for reason in error.reasons:
        print(f"- {reason['code']} at {reason['path']}: {reason['message']}", file=sys.stderr)


def _print_task_validation_blocked(error: TaskValidationBlockedError, *, json_errors: bool) -> None:
    payload = {
        "status": "failed",
        "exitCode": 1,
        "errors": error.reasons,
    }
    if json_errors:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return

    print("Mindfront task validation blocked.", file=sys.stderr)
    for reason in error.reasons:
        print(f"- {reason['code']} at {reason['path']}: {reason['message']}", file=sys.stderr)


def _print_task_protocol_blocked(error: TaskProtocolBlockedError, *, json_errors: bool) -> None:
    payload = {
        "status": "failed",
        "exitCode": 1,
        "errors": error.reasons,
    }
    if json_errors:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return

    print("Mindfront task observation protocol blocked.", file=sys.stderr)
    for reason in error.reasons:
        print(f"- {reason['code']} at {reason['path']}: {reason['message']}", file=sys.stderr)


def _print_task_input_blocked(error: TaskInputBlockedError, *, json_errors: bool) -> None:
    payload = {
        "status": "failed",
        "exitCode": 1,
        "errors": error.reasons,
    }
    if json_errors:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return

    print("Mindfront task validation input blocked.", file=sys.stderr)
    for reason in error.reasons:
        print(f"- {reason['code']} at {reason['path']}: {reason['message']}", file=sys.stderr)


def _handle_vault_command(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    if not args.vault_command:
        parser.parse_args(["vault", "--help"])
        return 3
    try:
        if args.vault_command == "init-key":
            payload = initialize_vault_key(args.key_file)
        elif args.vault_command == "key-status":
            payload = vault_key_status(args.key_file)
        elif args.vault_command == "inspect":
            payload = inspect_vault(Path(args.path))
        elif args.vault_command == "migrate":
            payload = migrate_vault(Path(args.path))
        else:
            parser.error("Unknown vault command.")
            return 3
    except VaultEncryptionError as exc:
        error_payload = {
            "artifactType": "mindfront_vault_error",
            "schemaVersion": 1,
            "status": "blocked",
            "reasons": exc.reasons,
            "payloadExposed": False,
        }
        if args.json_errors:
            print(json.dumps(error_payload, indent=2, sort_keys=True))
        else:
            print("Mindfront vault operation blocked.", file=sys.stderr)
            for reason in exc.reasons:
                print(
                    f"- {reason['code']} at {reason['path']}: {reason['message']}",
                    file=sys.stderr,
                )
        return 1
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


def _handle_store_command(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    if not args.store_command:
        parser.print_help(sys.stderr)
        return 3
    try:
        if args.store_command == "init":
            if args.dry_run:
                _print_dry_run("store init", [Path(args.db)], {"wouldInitializeStore": True})
                return 0
            payload = initialize_store_path(Path(args.db))
            print(json.dumps(payload, indent=2, sort_keys=True))
            return 0
        if args.store_command == "ingest":
            if args.dry_run:
                _print_dry_run(
                    "store ingest",
                    [Path(args.db)],
                    {
                        "analysis": args.analysis,
                        "variants": args.variants,
                        "comparison": args.comparison,
                        "stress": args.stress,
                        "researchPlan": args.research_plan,
                        "report": args.report,
                        "taskProtocol": args.task_protocol,
                        "taskValidation": args.task_validation,
                    },
                )
                return 0
            payload = store_artifact_set(
                Path(args.db),
                analysis_path=Path(args.analysis),
                variants_path=Path(args.variants) if args.variants else None,
                comparison_path=Path(args.comparison) if args.comparison else None,
                stress_path=Path(args.stress) if args.stress else None,
                research_plan_path=Path(args.research_plan) if args.research_plan else None,
                report_path=Path(args.report) if args.report else None,
                task_protocol_path=Path(args.task_protocol) if args.task_protocol else None,
                task_validation_path=Path(args.task_validation) if args.task_validation else None,
            )
            print(json.dumps(payload, indent=2, sort_keys=True))
            return 0
        if args.store_command == "list-analyses":
            payload = list_analysis_history(Path(args.db))
            if args.output:
                destination = _resolve_or_print_output_destination(args.output, args.overwrite, args.json_errors)
                if destination is None:
                    return 4
                if args.dry_run:
                    _print_dry_run("store list-analyses", [destination], {"runCount": payload["runCount"]})
                    return 0
                output_path = _write_json_output(payload, destination, "analysis-history.json")
                print(f"Mindfront analysis history written: {output_path}")
                return 0
            if args.dry_run:
                _print_dry_run("store list-analyses", [], {"runCount": payload["runCount"]})
                return 0
            print(json.dumps(payload, indent=2, sort_keys=True))
            return 0
        if args.store_command == "compare":
            payload = compare_analysis_history(Path(args.db), brief_id=args.brief_id)
            if args.output:
                destination = _resolve_or_print_output_destination(args.output, args.overwrite, args.json_errors)
                if destination is None:
                    return 4
                if args.dry_run:
                    _print_dry_run("store compare", [destination], {"runCount": payload["runCount"]})
                    return 0
                output_path = _write_json_output(payload, destination, "history-comparison.json")
                print(f"Mindfront history comparison written: {output_path}")
                return 0
            if args.dry_run:
                _print_dry_run("store compare", [], {"runCount": payload["runCount"]})
                return 0
            print(json.dumps(payload, indent=2, sort_keys=True))
            return 0
        if args.store_command == "export":
            destination = _resolve_or_print_output_destination(args.output, args.overwrite, args.json_errors)
            if destination is None:
                return 4
            if args.dry_run:
                _print_dry_run("store export", [destination], {"dbPath": args.db})
                return 0
            output_path = export_store(Path(args.db), destination)
            print(f"Mindfront store export written: {output_path}")
            return 0
        if args.store_command == "delete-run":
            if args.dry_run:
                _print_dry_run("store delete-run", [Path(args.db)], {"runId": args.run_id})
                return 0
            payload = delete_run(Path(args.db), args.run_id)
            print(json.dumps(payload, indent=2, sort_keys=True))
            return 0
        if args.store_command == "check-stale":
            payload = refresh_stale_state(Path(args.db), update=not args.dry_run)
            if args.output:
                destination = _resolve_or_print_output_destination(args.output, args.overwrite, args.json_errors)
                if destination is None:
                    return 4
                if args.dry_run:
                    _print_dry_run("store check-stale", [destination], payload)
                    return 0
                output_path = _write_json_output(payload, destination, "stale-state-check.json")
                print(f"Mindfront stale-state check written: {output_path}")
                return 0
            print(json.dumps(payload, indent=2, sort_keys=True))
            return 0
    except StoreBlockedError as exc:
        _print_store_blocked(exc, json_errors=args.json_errors)
        return 1

    parser.print_help(sys.stderr)
    return 3


def _handle_dashboard_command(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    if args.dashboard_command != "build":
        parser.print_help(sys.stderr)
        return 3
    try:
        destination = _resolve_or_print_output_destination(args.output, args.overwrite, args.json_errors)
        if destination is None:
            return 4
        if args.dry_run:
            _print_dry_run("dashboard build", [destination], {"dbPath": args.db})
            return 0
        output_paths = build_static_dashboard(Path(args.db), destination)
    except StoreBlockedError as exc:
        _print_store_blocked(exc, json_errors=args.json_errors)
        return 1


def _handle_assist_command(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    if not args.assist_command:
        parser.parse_args(["assist", "--help"])
        return 3

    try:
        if args.assist_command == "profile":
            return _handle_self_assistance_profile_command(args, parser)

        mode_by_command = {
            "preflight": "preflight",
            "interpret": "interpret",
            "debrief": "debrief",
            "career-review": "career_review",
        }
        expected_mode = mode_by_command.get(args.assist_command)
        if expected_mode is None:
            parser.error("Unknown assist command.")
            return 3

        request = _read_workplace_assistance_json(Path(args.input), "request")
        if request.get("mode") != expected_mode:
            raise WorkplaceAssistanceBlockedError(
                [
                    {
                        "code": "assistance_mode_mismatch",
                        "path": "mode",
                        "message": (
                            f"The {args.assist_command} command requires request mode "
                            f"{expected_mode}."
                        ),
                    }
                ]
            )
        self_profile = get_self_assistance_profile(Path(args.self_store))
        policy = load_workplace_assistance_policy(Path(args.policy))
        recipient_guidance = (
            _read_workplace_assistance_json(Path(args.recipient_guidance), "recipientGuidance")
            if args.recipient_guidance
            else None
        )
        result = build_workplace_assistance(
            request,
            self_profile,
            policy,
            recipient_guidance=recipient_guidance,
        )

        if args.output:
            destination = _resolve_or_print_output_destination(
                args.output,
                args.overwrite,
                args.json_errors,
            )
            if destination is None:
                return 4
            if args.dry_run:
                _print_dry_run(
                    f"assist {args.assist_command}",
                    [destination],
                    {
                        "resultId": result["resultId"],
                        "mode": result["mode"],
                        "privateArtifact": True,
                        "humanReviewRequired": True,
                        "automaticSendingAllowed": False,
                    },
                )
                return 0
            output_path = write_workplace_assistance_result(result, destination)
            print(f"Mindfront private workplace assistance written: {output_path}")
            return 0

        if args.dry_run:
            _print_dry_run(
                f"assist {args.assist_command}",
                [],
                {
                    "resultId": result["resultId"],
                    "mode": result["mode"],
                    "privateArtifact": True,
                    "humanReviewRequired": True,
                    "automaticSendingAllowed": False,
                },
            )
            return 0
        print(json.dumps(finalize_workplace_assistance(result), indent=2, sort_keys=True))
        return 0
    except WorkplaceAssistanceBlockedError as exc:
        _print_workplace_assistance_blocked(exc, json_errors=args.json_errors)
        return 1


def _handle_self_assistance_profile_command(
    args: argparse.Namespace,
    parser: argparse.ArgumentParser,
) -> int:
    if not args.assist_profile_command:
        parser.parse_args(["assist", "profile", "--help"])
        return 3

    profile_command = args.assist_profile_command
    output = getattr(args, "output", None)
    if profile_command in {"upsert", "show", "context", "delete"}:
        require_private_runtime_path(Path(args.store), "selfProfileStore")
    if profile_command in {"validate", "upsert"}:
        profile = _read_workplace_assistance_json(Path(args.input), "selfProfile")

    if profile_command == "validate":
        errors = validate_self_assistance_profile(profile)
        payload = {
            "artifactType": "self_assistance_profile_validation_result",
            "schemaVersion": 1,
            "status": "failed" if errors else "passed",
            "errorCount": len(errors),
            "errors": errors,
            "privateArtifact": True,
            "normalHistoryEligible": False,
        }
        default_name = "self-assistance-profile-validation-result.json"
        exit_code = 1 if errors else 0
    elif profile_command == "upsert":
        if args.dry_run:
            preview = build_self_assistance_profile(profile)
            payload = {
                "artifactType": "self_assistance_profile_upsert_dry_run",
                "schemaVersion": 1,
                "wouldWriteStore": str(Path(args.store)),
                "profileId": preview["profileId"],
                "profileHash": preview["profileHash"],
                "privateArtifact": True,
            }
        else:
            payload = upsert_self_assistance_profile(Path(args.store), profile)
        default_name = "self-assistance-profile-store-result.json"
        exit_code = 0
    elif profile_command == "show":
        payload = get_self_assistance_profile(Path(args.store))
        default_name = "self-declared-workplace-assistance-profile.json"
        exit_code = 0
    elif profile_command == "context":
        payload = build_self_assistance_context(
            get_self_assistance_profile(Path(args.store))
        )
        default_name = "self-workplace-assistance-context.json"
        exit_code = 0
    elif profile_command == "delete":
        if args.dry_run:
            profile = get_self_assistance_profile(Path(args.store))
            payload = {
                "artifactType": "self_assistance_profile_delete_dry_run",
                "schemaVersion": 1,
                "wouldDeleteProfileId": profile["profileId"],
                "store": str(Path(args.store)),
                "privateArtifact": True,
            }
        else:
            payload = delete_self_assistance_profile(Path(args.store))
        default_name = "self-assistance-profile-delete-result.json"
        exit_code = 0
    else:
        parser.error("Unknown assist profile command.")
        return 3

    if output:
        destination = _resolve_or_print_output_destination(
            output,
            args.overwrite,
            args.json_errors,
        )
        if destination is None:
            return 4
        destination = require_private_runtime_path(
            destination,
            "selfProfileOutput",
        )
        if args.dry_run:
            _print_dry_run(f"assist profile {profile_command}", [destination], payload)
            return exit_code
        output_path = _write_json_output(payload, destination, default_name)
        print(f"Mindfront private self-profile artifact written: {output_path}")
        return exit_code

    print(json.dumps(payload, indent=2, sort_keys=True))
    return exit_code


def _read_workplace_assistance_json(path: Path, path_label: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise WorkplaceAssistanceBlockedError(
            [
                {
                    "code": "private_input_unreadable",
                    "path": path_label,
                    "message": str(exc),
                }
            ]
        ) from exc
    if not isinstance(payload, dict):
        raise WorkplaceAssistanceBlockedError(
            [
                {
                    "code": "private_input_not_object",
                    "path": path_label,
                    "message": "Private assistance input must be a JSON object.",
                }
            ]
        )
    return payload


def _handle_profile_command(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    if not args.profile_command:
        parser.parse_args(["profile", "--help"])
        return 3

    try:
        payload: dict[str, Any]
        default_name: str
        output = getattr(args, "output", None)

        if args.profile_command in {"validate", "build", "upsert"}:
            bundle = json.loads(Path(args.input).read_text(encoding="utf-8"))

        if args.profile_command == "validate":
            errors = validate_observation_bundle(bundle)
            payload = {
                "artifactType": "interaction_profile_validation_result",
                "status": "failed" if errors else "passed",
                "errorCount": len(errors),
                "errors": errors,
                "rawContentStored": False,
            }
            default_name = "interaction-profile-validation-result.json"
            exit_code = 1 if errors else 0
        elif args.profile_command == "build":
            payload = build_interaction_profile(bundle)
            default_name = "named-interaction-assistance-profile.json"
            exit_code = 0
        elif args.profile_command == "upsert":
            if args.dry_run:
                preview = build_interaction_profile(bundle)
                payload = {
                    "artifactType": "interaction_profile_dry_run",
                    "wouldWriteStore": str(Path(args.store)),
                    "profileId": preview["profileId"],
                    "status": preview["status"],
                }
            else:
                payload = upsert_profile_store(Path(args.store), bundle)
            default_name = "interaction-profile-store-result.json"
            exit_code = 0
        elif args.profile_command == "show":
            payload = get_interaction_profile(
                Path(args.store),
                args.name,
                include_collecting=args.include_collecting,
            )
            default_name = "named-interaction-assistance-profile.json"
            exit_code = 0
        elif args.profile_command == "context":
            current_source_bundle = None
            if args.vault:
                try:
                    current_source_bundle = derive_observation_bundle(Path(args.vault), args.name)
                except InteractionProfileBlockedError as exc:
                    raise InteractionProfileBlockedError(
                        [
                            {
                                "code": "source_mismatch",
                                "path": args.name,
                                "message": (
                                    "The current encrypted communication corpus cannot verify "
                                    "the stored profile source snapshot."
                                ),
                            }
                        ]
                    ) from exc
            profile = get_interaction_profile(
                Path(args.store),
                args.name,
                expected_source_bundle=current_source_bundle,
            )
            payload = profile_guidance(profile, context=args.context)
            default_name = "interaction-assistance-guidance.json"
            exit_code = 0
        elif args.profile_command == "list":
            payload = list_interaction_profiles(Path(args.store))
            default_name = "interaction-profile-index.json"
            exit_code = 0
        elif args.profile_command == "delete":
            if args.dry_run:
                profile = get_interaction_profile(
                    Path(args.store),
                    args.name,
                    include_collecting=True,
                )
                payload = {
                    "artifactType": "interaction_profile_delete_dry_run",
                    "wouldDeleteProfileId": profile["profileId"],
                    "displayName": profile["displayName"],
                }
            else:
                payload = delete_interaction_profile(Path(args.store), args.name)
            default_name = "interaction-profile-delete-result.json"
            exit_code = 0
        elif args.profile_command == "invalidate-batch":
            if args.dry_run:
                payload = {
                    "artifactType": "interaction_profile_invalidation_dry_run",
                    "wouldInvalidateBundleId": args.bundle_id,
                    "store": str(Path(args.store)),
                }
            else:
                payload = invalidate_profile_batch(Path(args.store), args.bundle_id)
            default_name = "interaction-profile-invalidation-result.json"
            exit_code = 0
        else:
            parser.error("Unknown profile command.")
            return 3

        if output:
            destination = _resolve_or_print_output_destination(output, args.overwrite, args.json_errors)
            if destination is None:
                return 4
            if args.dry_run and args.profile_command not in {"upsert", "delete", "invalidate-batch"}:
                _print_dry_run(f"profile {args.profile_command}", [destination], payload)
                return exit_code
            output_path = _write_json_output(payload, destination, default_name)
            print(f"Mindfront interaction profile artifact written: {output_path}")
            return exit_code

        print(json.dumps(payload, indent=2, sort_keys=True))
        return exit_code
    except InteractionProfileBlockedError as exc:
        _print_interaction_profile_blocked(exc, json_errors=args.json_errors)
        return 1


def _profile_from_args(args: argparse.Namespace) -> dict[str, Any] | None:
    store = getattr(args, "profile_store", None)
    name = getattr(args, "profile_name", None)
    if bool(store) != bool(name):
        raise InteractionProfileBlockedError(
            [
                {
                    "code": "incomplete_profile_selection",
                    "path": "profile",
                    "message": "--profile-store and --profile-name must be provided together.",
                }
            ]
        )
    if not store:
        return None
    return get_interaction_profile(Path(store), name)


def _handle_corpus_command(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    if not args.corpus_command:
        parser.parse_args(["corpus", "--help"])
        return 3
    try:
        payload: dict[str, Any]
        default_name: str
        output = getattr(args, "output", None)

        if args.corpus_command in {
            "validate",
            "ingest",
            "ingest-outlook-export",
            "ingest-teams-export",
        }:
            source_payload = json.loads(Path(args.input).read_text(encoding="utf-8"))
            if args.corpus_command == "ingest-outlook-export":
                batch = corpus_batch_from_outlook_export(source_payload, batch_id=args.batch_id)
            elif args.corpus_command == "ingest-teams-export":
                batch = corpus_batch_from_teams_export(source_payload, batch_id=args.batch_id)
            else:
                batch = source_payload
        elif args.corpus_command == "ingest-freshservice-jsonl":
            identity_map = (
                json.loads(Path(args.identity_map).read_text(encoding="utf-8-sig"))
                if args.identity_map
                else None
            )
            batch = corpus_batch_from_freshservice_jsonl(
                Path(args.input),
                cleaning_manifest_path=Path(args.cleaning_manifest),
                export_manifest_path=Path(args.export_manifest),
                batch_id=args.batch_id,
                existing_vault_path=Path(args.vault),
                identity_map=identity_map,
            )

        if args.corpus_command == "validate":
            errors = validate_corpus_batch(batch)
            payload = {
                "artifactType": "communication_corpus_validation_result",
                "status": "failed" if errors else "passed",
                "errorCount": len(errors),
                "errors": errors,
            }
            default_name = "communication-corpus-validation-result.json"
            exit_code = 1 if errors else 0
        elif args.corpus_command in {
            "ingest",
            "ingest-outlook-export",
            "ingest-teams-export",
            "ingest-freshservice-jsonl",
        }:
            if args.dry_run:
                errors = validate_corpus_batch(batch)
                if errors:
                    raise InteractionProfileBlockedError(errors)
                payload = {
                    "artifactType": "communication_corpus_ingest_dry_run",
                    "wouldWriteVault": str(Path(args.vault)),
                    "batchId": batch["batchId"],
                    "messageCount": len(batch["messages"]),
                }
            else:
                payload = ingest_corpus_batch(Path(args.vault), batch)
                if args.corpus_command != "ingest":
                    payload["connectorAdapter"] = (
                        "freshservice"
                        if args.corpus_command == "ingest-freshservice-jsonl"
                        else args.corpus_command.removeprefix("ingest-").removesuffix("-export")
                    )
            default_name = "communication-corpus-ingest-result.json"
            exit_code = 0
        elif args.corpus_command == "list-people":
            payload = list_corpus_people(Path(args.vault))
            default_name = "communication-corpus-people-index.json"
            exit_code = 0
        elif args.corpus_command == "context":
            payload = get_corpus_context(
                Path(args.vault),
                args.name,
                context=args.context,
                limit=args.limit,
                include_thread_context=args.include_thread_context,
                thread_limit=args.thread_limit,
            )
            default_name = "private-communication-context.json"
            exit_code = 0
        elif args.corpus_command == "derive-profile":
            payload = derive_observation_bundle(Path(args.vault), args.name)
            default_name = "communication-observation-bundle.json"
            exit_code = 0
        elif args.corpus_command == "refresh-profile":
            bundle = derive_observation_bundle(Path(args.vault), args.name)
            if args.dry_run:
                preview = build_interaction_profile(bundle)
                payload = {
                    "artifactType": "communication_profile_refresh_dry_run",
                    "wouldWriteProfileStore": str(Path(args.profile_store)),
                    "profileId": preview["profileId"],
                    "status": preview["status"],
                }
            else:
                payload = upsert_profile_store(
                    Path(args.profile_store),
                    bundle,
                    replace_existing=True,
                )
            default_name = "communication-profile-refresh-result.json"
            exit_code = 0
        elif args.corpus_command == "refresh-all-profiles":
            people = list_corpus_people(Path(args.vault))["people"]
            status_counts = {"active": 0, "collecting": 0, "stale": 0}
            action_counts: dict[str, int] = {}
            failures: list[dict[str, Any]] = []
            for person in people:
                try:
                    bundle = derive_observation_bundle(Path(args.vault), person["displayName"])
                    if args.dry_run:
                        profile = build_interaction_profile(bundle)
                        action = "would_refresh"
                    else:
                        result = upsert_profile_store(
                            Path(args.profile_store),
                            bundle,
                            replace_existing=True,
                        )
                        profile = result["profile"]
                        action = result["status"]
                    status_counts[profile["status"]] = status_counts.get(profile["status"], 0) + 1
                    action_counts[action] = action_counts.get(action, 0) + 1
                except InteractionProfileBlockedError as exc:
                    failures.append(
                        {
                            "identityFingerprint": person["identityFingerprint"],
                            "errorCodes": sorted({item["code"] for item in exc.reasons}),
                        }
                    )
            payload = {
                "artifactType": "communication_profile_bulk_refresh_result",
                "status": "partial" if failures else ("dry_run" if args.dry_run else "complete"),
                "sourcePersonCount": len(people),
                "profileRefreshCount": sum(status_counts.values()),
                "activeProfileCount": status_counts.get("active", 0),
                "collectingProfileCount": status_counts.get("collecting", 0),
                "staleProfileCount": status_counts.get("stale", 0),
                "actionCounts": dict(sorted(action_counts.items())),
                "failureCount": len(failures),
                "failures": failures,
                "profileStoreEncryption": CURRENT_ENCRYPTION,
                "namesIncluded": False,
                "marketEvidenceCreated": False,
            }
            default_name = "communication-profile-bulk-refresh-result.json"
            exit_code = 1 if failures else 0
        elif args.corpus_command == "delete-person":
            if args.dry_run:
                context = get_corpus_context(Path(args.vault), args.name, limit=100)
                payload = {
                    "artifactType": "communication_corpus_person_delete_dry_run",
                    "displayName": args.name,
                    "atLeastMessageCount": context["messageCount"],
                }
            else:
                payload = delete_corpus_person(Path(args.vault), args.name)
            default_name = "communication-corpus-person-delete-result.json"
            exit_code = 0
        elif args.corpus_command == "invalidate-batch":
            if args.dry_run:
                payload = {
                    "artifactType": "communication_corpus_invalidation_dry_run",
                    "wouldInvalidateBatchId": args.batch_id,
                    "vault": str(Path(args.vault)),
                }
            else:
                payload = invalidate_corpus_batch(Path(args.vault), args.batch_id)
            default_name = "communication-corpus-invalidation-result.json"
            exit_code = 0
        else:
            parser.error("Unknown corpus command.")
            return 3

        if output:
            destination = _resolve_or_print_output_destination(output, args.overwrite, args.json_errors)
            if destination is None:
                return 4
            if args.dry_run and args.corpus_command not in {
                "ingest",
                "ingest-outlook-export",
                "ingest-teams-export",
                "ingest-freshservice-jsonl",
                "refresh-profile",
                "delete-person",
                "invalidate-batch",
            }:
                _print_dry_run(f"corpus {args.corpus_command}", [destination], payload)
                return exit_code
            output_path = _write_json_output(payload, destination, default_name)
            print(f"Mindfront private communication artifact written: {output_path}")
            return exit_code
        print(json.dumps(payload, indent=2, sort_keys=True))
        return exit_code
    except InteractionProfileBlockedError as exc:
        _print_interaction_profile_blocked(exc, json_errors=args.json_errors)
        return 1
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        payload = {
            "status": "failed",
            "exitCode": 1,
            "errors": [{"code": "communication_corpus_input_error", "path": "corpus", "message": str(exc)}],
        }
        if args.json_errors:
            print(json.dumps(payload, indent=2, sort_keys=True))
        else:
            print(f"Mindfront communication corpus operation blocked: {exc}", file=sys.stderr)
        return 1
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        payload = {
            "status": "failed",
            "exitCode": 1,
            "errors": [{"code": "profile_input_error", "path": "profile", "message": str(exc)}],
        }
        if args.json_errors:
            print(json.dumps(payload, indent=2, sort_keys=True))
        else:
            print(f"Mindfront interaction profile operation blocked: {exc}", file=sys.stderr)
        return 1
    formatted = ", ".join(str(path) for path in output_paths)
    print(f"Mindfront dashboard written: {formatted}")
    return 0


def _write_json_output(payload: dict, output_path: Path, default_name: str) -> Path:
    destination = output_path
    if destination.suffix.lower() != ".json":
        destination.mkdir(parents=True, exist_ok=True)
        destination = destination / default_name
    else:
        destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return destination


def _resolve_or_print_output_destination(
    output_path: str | Path,
    overwrite: str,
    json_errors: bool,
) -> Path | None:
    try:
        return _resolve_output_destination(Path(output_path), overwrite)
    except OutputConflictError as exc:
        _print_output_conflict(exc, json_errors=json_errors)
        return None


def _resolve_output_destination(destination: Path, overwrite: str) -> Path:
    if not destination.exists():
        return destination
    if overwrite == "replace":
        return destination
    if overwrite == "rename":
        return _renamed_destination(destination)
    raise OutputConflictError(
        f"Output path already exists: {destination}. Use --overwrite replace or --overwrite rename."
    )


def _renamed_destination(destination: Path) -> Path:
    parent = destination.parent
    stem = destination.stem if destination.suffix else destination.name
    suffix = destination.suffix
    for index in range(1, 1000):
        candidate = parent / f"{stem}-{index:03d}{suffix}"
        if not candidate.exists():
            return candidate
    raise OutputConflictError(f"Could not find a rename target for output path: {destination}")


def _print_dry_run(command: str, planned_outputs: list[Path], details: dict) -> None:
    payload = {
        "artifactType": "dry_run_result",
        "status": "dry_run",
        "command": command,
        "plannedOutputs": [str(path) for path in planned_outputs],
        "writesSkipped": True,
        "details": details,
    }
    print(json.dumps(payload, indent=2, sort_keys=True))


def _print_output_conflict(error: OutputConflictError, *, json_errors: bool) -> None:
    payload = {
        "status": "failed",
        "exitCode": 4,
        "errors": [
            {
                "code": "output_conflict",
                "message": str(error),
                "path": "output",
            }
        ],
    }
    if json_errors:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return
    print(f"Mindfront output conflict: {error}", file=sys.stderr)


def _print_store_blocked(error: StoreBlockedError, *, json_errors: bool) -> None:
    payload = {
        "status": "failed",
        "exitCode": 1,
        "errors": error.reasons,
    }
    if json_errors:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return

    print("Mindfront store/dashboard operation blocked.", file=sys.stderr)
    for reason in error.reasons:
        print(f"- {reason['code']} at {reason['path']}: {reason['message']}", file=sys.stderr)


def _print_interaction_profile_blocked(
    error: InteractionProfileBlockedError,
    *,
    json_errors: bool,
) -> None:
    payload = {
        "status": "failed",
        "exitCode": 1,
        "errors": error.reasons,
    }
    if json_errors:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return
    print("Mindfront private interaction-assistance operation blocked.", file=sys.stderr)
    for reason in error.reasons:
        print(f"- {reason['code']} at {reason['path']}: {reason['message']}", file=sys.stderr)


def _print_workplace_assistance_blocked(
    error: WorkplaceAssistanceBlockedError,
    *,
    json_errors: bool,
) -> None:
    payload = {
        "status": "failed",
        "exitCode": 1,
        "errors": error.reasons,
    }
    if json_errors:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return
    print("Mindfront private workplace-assistance operation blocked.", file=sys.stderr)
    for reason in error.reasons:
        print(f"- {reason['code']} at {reason['path']}: {reason['message']}", file=sys.stderr)


def _print_improvement_plan_blocked(error: ImprovementPlanBlockedError, *, json_errors: bool) -> None:
    payload = {
        "status": "failed",
        "exitCode": 1,
        "errors": error.reasons,
    }
    if json_errors:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return

    print("Mindfront improvement planning blocked.", file=sys.stderr)
    for reason in error.reasons:
        print(f"- {reason['code']} at {reason['path']}: {reason['message']}", file=sys.stderr)


if __name__ == "__main__":
    raise SystemExit(main())

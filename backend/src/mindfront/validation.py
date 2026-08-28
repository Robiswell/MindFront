"""Mindfront configuration validator."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import date
from json import JSONDecodeError
from pathlib import Path
from typing import Any, Iterable

from .impact import TaskValidationBlockedError, build_task_validation_result
from .schemas import (
    CANONICAL_CONFIDENCE_ENUMS,
    CONFIDENCE_ENUM_KEY_ALIASES,
    EVIDENCE_SOURCE_ARRAY_FIELDS,
    EVIDENCE_SOURCE_BOOLEAN_FIELDS,
    LENS_ARRAY_FIELDS,
    MESSAGE_BRIEF_ARRAY_FIELDS,
    MESSAGE_BRIEF_BOOLEAN_FIELDS,
    MESSAGE_BRIEF_ENUMS,
    MESSAGE_BRIEF_STRING_FIELDS,
    PRINCIPLE_ARRAY_FIELDS,
    REQUIRED_CONFIG_FILES,
    REQUIRED_EVIDENCE_SOURCE_FIELDS,
    REQUIRED_LENS_FIELDS,
    REQUIRED_MESSAGE_BRIEF_FIELDS,
    REQUIRED_PRINCIPLE_FIELDS,
    REQUIRED_RUBRIC_DIMENSIONS,
    RUBRIC_ARRAY_FIELDS,
    RUBRIC_PRINCIPLE_REF_FIELDS,
    SENSITIVE_DOMAIN_CONTEXTS,
)
from .workplace_assistance import validate_workplace_assistance_policy

SHA256_PATTERN = re.compile(r"sha256:[0-9a-f]{64}")
PLACEHOLDER_SHA256_DIGESTS = {
    "0" * 64,
    "f" * 64,
    "deadbeef" * 8,
    "0123456789abcdef" * 4,
}
PHONE_NUMBER_PATTERN = re.compile(
    r"(?<![A-Za-z0-9])(?:\+?1[\s.-]+)?"
    r"(?:\([2-9][0-9]{2}\)|[2-9][0-9]{2})[\s.-]+"
    r"[2-9][0-9]{2}[\s.-]+[0-9]{4}(?![0-9])"
)
SSN_STYLE_PATTERN = re.compile(r"(?<![A-Za-z0-9])[0-9]{3}-[0-9]{2}-[0-9]{4}(?![0-9])")


@dataclass(frozen=True)
class ValidationError:
    """A machine-readable validation error."""

    code: str
    message: str
    path: str

    def to_dict(self) -> dict[str, str]:
        return {
            "code": self.code,
            "message": self.message,
            "path": self.path,
        }


@dataclass
class ValidationResult:
    """Validation outcome for one config root."""

    config_root: Path
    strict: bool
    errors: list[ValidationError] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors

    @property
    def exit_code(self) -> int:
        return 0 if self.ok else 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": "ok" if self.ok else "failed",
            "exitCode": self.exit_code,
            "configRoot": str(self.config_root),
            "strict": self.strict,
            "errors": [error.to_dict() for error in self.errors],
        }


@dataclass(frozen=True)
class BriefEvidenceResolution:
    """Resolved evidence available to a message brief."""

    registered_source_ids: frozenset[str]
    resolved_proof_source_ids: frozenset[str]
    unresolved_proof_source_ids: frozenset[str]
    resolved_real_user_source_ids: frozenset[str]
    source_fact_manifest_hash: str | None
    source_fact_manifest_resolved: bool


def validate_config_root(config_root: str | Path, *, strict: bool = False) -> ValidationResult:
    """Validate the source-owned Mindfront config set."""

    root = Path(config_root)
    result = ValidationResult(config_root=root, strict=strict)

    if not root.exists():
        result.errors.append(
            ValidationError(
                code="missing_config_root",
                message="Config root does not exist.",
                path=str(root),
            )
        )
        return result

    if not root.is_dir():
        result.errors.append(
            ValidationError(
                code="invalid_config_root",
                message="Config root must be a directory.",
                path=str(root),
            )
        )
        return result

    loaded: dict[str, Any] = {}
    for config_key, spec in REQUIRED_CONFIG_FILES.items():
        file_path = root / spec.file_name
        if not file_path.exists():
            result.errors.append(
                ValidationError(
                    code="missing_config_file",
                    message=f"Required config file is missing: {spec.file_name}.",
                    path=spec.file_name,
                )
            )
            continue
        loaded[config_key] = _load_json(file_path, spec.file_name, result.errors)

    if "confidence_labels" in loaded:
        _validate_confidence_labels(
            loaded["confidence_labels"],
            strict=strict,
            errors=result.errors,
            path=REQUIRED_CONFIG_FILES["confidence_labels"].file_name,
        )

    source_ids: set[str] = set()
    if "evidence_sources" in loaded:
        evidence_records = _extract_records(
            loaded["evidence_sources"],
            collection_keys=REQUIRED_CONFIG_FILES["evidence_sources"].collection_keys,
            file_name=REQUIRED_CONFIG_FILES["evidence_sources"].file_name,
            record_name="evidence source",
            errors=result.errors,
        )
        source_ids = _validate_evidence_sources(evidence_records, result.errors)

    principle_ids: set[str] = set()
    if "principles" in loaded:
        principle_records = _extract_records(
            loaded["principles"],
            collection_keys=REQUIRED_CONFIG_FILES["principles"].collection_keys,
            file_name=REQUIRED_CONFIG_FILES["principles"].file_name,
            record_name="principle",
            errors=result.errors,
        )
        principle_ids = _validate_principles(principle_records, source_ids, result.errors)

    if "lenses" in loaded:
        lens_records = _extract_records(
            loaded["lenses"],
            collection_keys=REQUIRED_CONFIG_FILES["lenses"].collection_keys,
            file_name=REQUIRED_CONFIG_FILES["lenses"].file_name,
            record_name="audience lens",
            errors=result.errors,
        )
        _validate_lenses(lens_records, principle_ids, result.errors)

    if "rubric" in loaded:
        rubric_records = _extract_records(
            loaded["rubric"],
            collection_keys=REQUIRED_CONFIG_FILES["rubric"].collection_keys,
            file_name=REQUIRED_CONFIG_FILES["rubric"].file_name,
            record_name="rubric dimension",
            errors=result.errors,
        )
        _validate_rubric(rubric_records, principle_ids, strict=strict, errors=result.errors)

    if "workplace_assistance_policy" in loaded:
        policy_errors = validate_workplace_assistance_policy(
            loaded["workplace_assistance_policy"]
        )
        for error in policy_errors:
            result.errors.append(
                ValidationError(
                    code=error["code"],
                    message=error["message"],
                    path=(
                        f"{REQUIRED_CONFIG_FILES['workplace_assistance_policy'].file_name}"
                        f".{error['path']}"
                    ),
                )
            )

    return result


def validate_workspace(
    config_root: str | Path,
    *,
    strict: bool = False,
    brief_root: str | Path | None = None,
    task_validation_root: str | Path | None = None,
) -> ValidationResult:
    """Validate the config set plus local sample/input briefs when present."""

    result = validate_config_root(config_root, strict=strict)
    if brief_root is not None:
        _validate_brief_root(
            Path(brief_root),
            config_root=Path(config_root),
            strict=strict,
            errors=result.errors,
        )
    if task_validation_root is not None:
        _validate_task_validation_root(Path(task_validation_root), errors=result.errors)
    return result


def resolve_brief_evidence(
    brief_path: str | Path,
    config_root: str | Path,
    *,
    brief: dict[str, Any] | None = None,
) -> BriefEvidenceResolution:
    """Resolve proof source ids and a self-validating fact manifest for a brief."""

    brief_file = Path(brief_path)
    config_path = Path(config_root)
    brief_data = brief if isinstance(brief, dict) else _read_json_object(brief_file)
    registered_source_ids = _registered_evidence_source_ids(config_path)

    proof_items = brief_data.get("proofAvailable") or []
    proof_source_ids = {
        item["sourceId"]
        for item in proof_items
        if isinstance(item, dict) and isinstance(item.get("sourceId"), str)
    }
    resolved_proof_source_ids = proof_source_ids & registered_source_ids
    unresolved_proof_source_ids = proof_source_ids - registered_source_ids
    resolved_real_user_source_ids = {
        item["sourceId"]
        for item in proof_items
        if isinstance(item, dict)
        and item.get("type") == "real_user_data"
        and isinstance(item.get("sourceId"), str)
        and item["sourceId"] in registered_source_ids
    }

    source_fact_manifest_hash = brief_data.get("sourceFactManifestHash")
    if not isinstance(source_fact_manifest_hash, str):
        source_fact_manifest_hash = None
    source_fact_manifest_resolved = bool(
        source_fact_manifest_hash
        and _is_non_placeholder_sha256(source_fact_manifest_hash)
        and _find_matching_fact_manifest(
            brief_file,
            config_path,
            source_fact_manifest_hash,
        )
    )

    return BriefEvidenceResolution(
        registered_source_ids=frozenset(registered_source_ids),
        resolved_proof_source_ids=frozenset(resolved_proof_source_ids),
        unresolved_proof_source_ids=frozenset(unresolved_proof_source_ids),
        resolved_real_user_source_ids=frozenset(resolved_real_user_source_ids),
        source_fact_manifest_hash=source_fact_manifest_hash,
        source_fact_manifest_resolved=source_fact_manifest_resolved,
    )


def validate_brief_file(brief_path: str | Path, *, strict: bool = False) -> ValidationResult:
    """Validate one message brief file."""

    path = Path(brief_path)
    result = ValidationResult(config_root=path.parent, strict=strict)
    if not path.exists():
        result.errors.append(
            ValidationError(
                code="missing_brief_file",
                message="Message brief file does not exist.",
                path=str(path),
            )
        )
        return result
    if not path.is_file():
        result.errors.append(
            ValidationError(
                code="invalid_brief_file",
                message="Message brief path must be a file.",
                path=str(path),
            )
        )
        return result

    data = _load_json(path, str(path), result.errors)
    _validate_message_brief(data, path=str(path), strict=strict, errors=result.errors)
    return result


def _load_json(file_path: Path, display_path: str, errors: list[ValidationError]) -> Any:
    try:
        return json.loads(file_path.read_text(encoding="utf-8"))
    except JSONDecodeError as exc:
        errors.append(
            ValidationError(
                code="invalid_json",
                message=f"Invalid JSON at line {exc.lineno}, column {exc.colno}: {exc.msg}.",
                path=display_path,
            )
        )
    except OSError as exc:
        errors.append(
            ValidationError(
                code="config_file_read_error",
                message=f"Could not read config file: {exc}.",
                path=display_path,
            )
        )
    return None


def _read_json_object(file_path: Path) -> dict[str, Any]:
    try:
        data = json.loads(file_path.read_text(encoding="utf-8"))
    except (JSONDecodeError, OSError):
        return {}
    return data if isinstance(data, dict) else {}


def _registered_evidence_source_ids(config_root: Path) -> set[str]:
    data = _read_json_object(config_root / REQUIRED_CONFIG_FILES["evidence_sources"].file_name)
    raw_sources = data.get("sources")
    if not isinstance(raw_sources, list):
        return set()
    return {
        source["sourceId"]
        for source in raw_sources
        if isinstance(source, dict)
        and isinstance(source.get("sourceId"), str)
        and source.get("status") == "active"
    }


def _is_non_placeholder_sha256(value: str) -> bool:
    if not SHA256_PATTERN.fullmatch(value):
        return False
    digest = value.removeprefix("sha256:")
    return len(set(digest)) > 1 and digest not in PLACEHOLDER_SHA256_DIGESTS


def _find_matching_fact_manifest(
    brief_path: Path,
    config_root: Path,
    expected_hash: str,
) -> Path | None:
    candidate_directories = (
        brief_path.parent / "evidence",
        brief_path.parent.parent / "evidence",
        config_root / "evidence",
        brief_path.parent,
    )
    seen_directories: set[Path] = set()
    for directory in candidate_directories:
        resolved_directory = directory.resolve()
        if resolved_directory in seen_directories or not resolved_directory.is_dir():
            continue
        seen_directories.add(resolved_directory)
        for candidate in sorted(resolved_directory.glob("*.json")):
            manifest = _read_json_object(candidate)
            if _is_self_validating_fact_manifest(manifest, expected_hash):
                return candidate
    return None


def _is_self_validating_fact_manifest(manifest: dict[str, Any], expected_hash: str) -> bool:
    artifact_type = manifest.get("artifactType")
    if (
        not isinstance(artifact_type, str)
        or not artifact_type.endswith("_fact_manifest")
        or manifest.get("outputHash") != expected_hash
    ):
        return False
    payload = dict(manifest)
    payload["outputHash"] = "sha256:pending-until-written"
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    calculated_hash = f"sha256:{hashlib.sha256(canonical.encode('utf-8')).hexdigest()}"
    return calculated_hash == expected_hash


def _validate_brief_root(
    brief_root: Path,
    *,
    config_root: Path,
    strict: bool,
    errors: list[ValidationError],
) -> None:
    if not brief_root.exists():
        return

    if not brief_root.is_dir():
        errors.append(
            ValidationError(
                code="invalid_brief_root",
                message="Brief root must be a directory.",
                path=str(brief_root),
            )
        )
        return

    for brief_path in sorted(brief_root.glob("*.json")):
        data = _load_json(brief_path, str(brief_path), errors)
        _validate_message_brief(data, path=str(brief_path), strict=strict, errors=errors)
        if strict and isinstance(data, dict):
            _validate_brief_evidence_resolution(
                data,
                brief_path=brief_path,
                config_root=config_root,
                errors=errors,
            )


def _validate_task_validation_root(task_validation_root: Path, *, errors: list[ValidationError]) -> None:
    if not task_validation_root.exists():
        return
    if not task_validation_root.is_dir():
        errors.append(
            ValidationError(
                code="invalid_task_validation_root",
                message="Task-validation root must be a directory when provided.",
                path=str(task_validation_root),
            )
        )
        return
    for validation_path in sorted(task_validation_root.glob("*.json")):
        try:
            build_task_validation_result(validation_path)
        except TaskValidationBlockedError as exc:
            errors.extend(
                ValidationError(
                    code=reason["code"],
                    message=reason["message"],
                    path=reason["path"],
                )
                for reason in exc.reasons
            )


def _validate_message_brief(
    data: Any,
    *,
    path: str,
    strict: bool,
    errors: list[ValidationError],
) -> None:
    if data is None:
        return

    if not isinstance(data, dict):
        errors.append(
            ValidationError(
                code="invalid_json_shape",
                message="Expected message brief to be an object.",
                path=path,
            )
        )
        return

    _validate_required_fields(data, REQUIRED_MESSAGE_BRIEF_FIELDS, path, errors)
    _validate_string_fields(data, MESSAGE_BRIEF_STRING_FIELDS, path, errors)
    _validate_string_arrays(data, MESSAGE_BRIEF_ARRAY_FIELDS, path, errors, allow_empty=True)

    for field_name in MESSAGE_BRIEF_BOOLEAN_FIELDS:
        if field_name in data and not isinstance(data[field_name], bool):
            errors.append(
                ValidationError(
                    code="invalid_field",
                    message=f"{field_name} must be a boolean.",
                    path=f"{path}.{field_name}",
                )
            )

    if data.get("artifactType") != "message_brief":
        errors.append(
            ValidationError(
                code="invalid_field",
                message="artifactType must be message_brief.",
                path=f"{path}.artifactType",
            )
        )

    if isinstance(data.get("briefId"), str) and not re.fullmatch(r"brief-[a-z0-9][a-z0-9-]*", data["briefId"]):
        errors.append(
            ValidationError(
                code="invalid_id",
                message="briefId must use the brief-kebab-case pattern.",
                path=f"{path}.briefId",
            )
        )

    for field_name, allowed_values in MESSAGE_BRIEF_ENUMS.items():
        value = data.get(field_name)
        if isinstance(value, str) and value not in allowed_values:
            errors.append(
                ValidationError(
                    code="invalid_enum",
                    message=f"Unknown {field_name} value: {value}.",
                    path=f"{path}.{field_name}",
                )
            )

    if data.get("dataClassification") in {"confidential", "sensitive"} and data.get("llmProcessingAllowed") is True:
        errors.append(
            ValidationError(
                code="data_boundary_violation",
                message="Confidential or sensitive briefs cannot allow external LLM processing by default.",
                path=f"{path}.llmProcessingAllowed",
            )
        )

    if data.get("containsPersonalData") is True or data.get("containsCustomerConfidentialData") is True:
        errors.append(
            ValidationError(
                code="unsafe_sample_data",
                message="Example briefs must not contain personal or customer-confidential data.",
                path=path,
            )
        )

    if data.get("sourceContainsPersonalData") is True and data.get("sourceDataSanitized") is not True:
        errors.append(
            ValidationError(
                code="source_data_not_sanitized",
                message="A brief derived from personal data must declare sourceDataSanitized as true.",
                path=f"{path}.sourceDataSanitized",
            )
        )

    source_text = data.get("sourceText")
    if isinstance(source_text, str) and data.get("containsPersonalData") is False:
        if re.search(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", source_text, flags=re.IGNORECASE):
            errors.append(
                ValidationError(
                    code="undeclared_personal_data",
                    message="sourceText appears to contain an email address while containsPersonalData is false.",
                    path=f"{path}.sourceText",
                )
            )
        if PHONE_NUMBER_PATTERN.search(source_text):
            errors.append(
                ValidationError(
                    code="undeclared_personal_data",
                    message=(
                        "sourceText appears to contain a formatted North American phone number "
                        "while containsPersonalData is false."
                    ),
                    path=f"{path}.sourceText",
                )
            )
        if SSN_STYLE_PATTERN.search(source_text):
            errors.append(
                ValidationError(
                    code="undeclared_personal_data",
                    message=(
                        "sourceText appears to contain an SSN-style identifier while "
                        "containsPersonalData is false."
                    ),
                    path=f"{path}.sourceText",
                )
            )
        if re.search(
            r"\b[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\b",
            source_text,
            flags=re.IGNORECASE,
        ):
            errors.append(
                ValidationError(
                    code="undeclared_personal_data",
                    message="sourceText appears to contain a UUID-style user identifier while containsPersonalData is false.",
                    path=f"{path}.sourceText",
                )
            )

    document_archetype = data.get("documentArchetype")
    if document_archetype == "internal_executive_digest":
        for required_field in (
            "communicationIntent",
            "decisionRequired",
            "readerTimeBudgetSeconds",
            "sourceFactManifestHash",
            "verifiedFactStatements",
        ):
            if required_field not in data:
                errors.append(
                    ValidationError(
                        code="missing_required_field",
                        message=f"internal_executive_digest briefs require {required_field}.",
                        path=f"{path}.{required_field}",
                    )
                )

        verified_statements = data.get("verifiedFactStatements")
        if isinstance(verified_statements, list) and not verified_statements:
            errors.append(
                ValidationError(
                    code="invalid_field",
                    message="internal_executive_digest verifiedFactStatements must not be empty.",
                    path=f"{path}.verifiedFactStatements",
                )
            )

    reader_time_budget = data.get("readerTimeBudgetSeconds")
    if reader_time_budget is not None and (
        isinstance(reader_time_budget, bool)
        or not isinstance(reader_time_budget, int)
        or reader_time_budget <= 0
    ):
        errors.append(
            ValidationError(
                code="invalid_field",
                message="readerTimeBudgetSeconds must be a positive integer.",
                path=f"{path}.readerTimeBudgetSeconds",
            )
        )

    source_fact_hash = data.get("sourceFactManifestHash")
    if isinstance(source_fact_hash, str) and not SHA256_PATTERN.fullmatch(source_fact_hash):
        errors.append(
            ValidationError(
                code="invalid_hash",
                message="sourceFactManifestHash must be a lowercase sha256 hash.",
                path=f"{path}.sourceFactManifestHash",
            )
        )

    if data.get("communicationIntent") == "inform" and data.get("decisionRequired") is True:
        errors.append(
            ValidationError(
                code="intent_decision_conflict",
                message="An informational brief cannot require a decision.",
                path=f"{path}.decisionRequired",
            )
        )

    sensitive_flags = data.get("sensitiveDomainFlags")
    has_sensitive_flags = isinstance(sensitive_flags, list) and len(sensitive_flags) > 0
    is_sensitive_context = data.get("domainContext") in SENSITIVE_DOMAIN_CONTEXTS or has_sensitive_flags
    if is_sensitive_context and data.get("expertReviewRequired") is not True:
        errors.append(
            ValidationError(
                code="sensitive_domain_requires_review",
                message="Sensitive-domain briefs must require expert review.",
                path=f"{path}.expertReviewRequired",
            )
        )

    if is_sensitive_context and data.get("publishReadiness") == "ready_for_small_test" and data.get("expertReviewStatus") != "completed":
        errors.append(
            ValidationError(
                code="sensitive_domain_blocks_publish_readiness",
                message="Sensitive-domain briefs cannot be ready for testing until required expert review is completed.",
                path=f"{path}.publishReadiness",
            )
        )

    proof_available = data.get("proofAvailable")
    if proof_available is not None:
        _validate_brief_proof_items(proof_available, path=f"{path}.proofAvailable", errors=errors)


def _validate_brief_evidence_resolution(
    data: dict[str, Any],
    *,
    brief_path: Path,
    config_root: Path,
    errors: list[ValidationError],
) -> None:
    resolution = resolve_brief_evidence(brief_path, config_root, brief=data)
    manifest_hash = resolution.source_fact_manifest_hash
    if manifest_hash and SHA256_PATTERN.fullmatch(manifest_hash):
        if not _is_non_placeholder_sha256(manifest_hash):
            errors.append(
                ValidationError(
                    code="placeholder_evidence_manifest_hash",
                    message="sourceFactManifestHash must not use a placeholder digest.",
                    path=f"{brief_path}.sourceFactManifestHash",
                )
            )
        elif not resolution.source_fact_manifest_resolved:
            errors.append(
                ValidationError(
                    code="unresolved_evidence_manifest",
                    message=(
                        "sourceFactManifestHash must resolve to a supplied, self-validating "
                        "fact manifest."
                    ),
                    path=f"{brief_path}.sourceFactManifestHash",
                )
            )

    proof_items = data.get("proofAvailable")
    if not isinstance(proof_items, list):
        return
    for index, item in enumerate(proof_items):
        if not isinstance(item, dict):
            continue
        source_id = item.get("sourceId")
        if item.get("type") == "real_user_data" and not isinstance(source_id, str):
            errors.append(
                ValidationError(
                    code="missing_evidence_source_ref",
                    message="real_user_data proof must reference a registered sourceId.",
                    path=f"{brief_path}.proofAvailable[{index}].sourceId",
                )
            )
        elif isinstance(source_id, str) and source_id not in resolution.registered_source_ids:
            errors.append(
                ValidationError(
                    code="unknown_evidence_source_ref",
                    message=f"proofAvailable sourceId does not resolve to active evidence: {source_id}.",
                    path=f"{brief_path}.proofAvailable[{index}].sourceId",
                )
            )


def _validate_brief_proof_items(proof_available: Any, *, path: str, errors: list[ValidationError]) -> None:
    if not isinstance(proof_available, list):
        errors.append(
            ValidationError(
                code="invalid_field",
                message="proofAvailable must be an array when provided.",
                path=path,
            )
        )
        return

    for index, item in enumerate(proof_available):
        item_path = f"{path}[{index}]"
        if not isinstance(item, dict):
            errors.append(
                ValidationError(
                    code="invalid_json_shape",
                    message="proofAvailable entries must be objects.",
                    path=item_path,
                )
            )
            continue
        _validate_string_fields(item, ("type", "label", "summary"), item_path, errors)
        if "sourceId" in item:
            _validate_string_fields(item, ("sourceId",), item_path, errors)
            if isinstance(item.get("sourceId"), str) and not re.fullmatch(
                r"source-[0-9]{3}",
                item["sourceId"],
            ):
                errors.append(
                    ValidationError(
                        code="invalid_id",
                        message="proofAvailable sourceId must use the source-001 pattern.",
                        path=f"{item_path}.sourceId",
                    )
                )
        proof_type = item.get("type")
        if isinstance(proof_type, str) and proof_type not in CANONICAL_CONFIDENCE_ENUMS["evidenceBasis"]:
            errors.append(
                ValidationError(
                    code="invalid_confidence_enum",
                    message=f"Unknown proofAvailable type: {proof_type}.",
                    path=f"{item_path}.type",
                )
            )


def _extract_records(
    data: Any,
    *,
    collection_keys: tuple[str, ...],
    file_name: str,
    record_name: str,
    errors: list[ValidationError],
) -> list[tuple[dict[str, Any], str]]:
    if data is None:
        return []

    raw_records: Any
    base_path: str
    if isinstance(data, list):
        raw_records = data
        base_path = file_name
    elif isinstance(data, dict):
        matching_key = next((key for key in collection_keys if key in data), None)
        if matching_key is not None:
            raw_records = data[matching_key]
            base_path = f"{file_name}.{matching_key}"
        elif data and all(isinstance(value, dict) for value in data.values()):
            raw_records = list(data.values())
            base_path = file_name
        else:
            errors.append(
                ValidationError(
                    code="invalid_json_shape",
                    message=f"Expected {record_name} records as a list or named collection.",
                    path=file_name,
                )
            )
            return []
    else:
        errors.append(
            ValidationError(
                code="invalid_json_shape",
                message=f"Expected {record_name} config to be an object or array.",
                path=file_name,
            )
        )
        return []

    if not isinstance(raw_records, list):
        errors.append(
            ValidationError(
                code="invalid_json_shape",
                message=f"Expected {record_name} records to be an array.",
                path=base_path,
            )
        )
        return []

    if not raw_records:
        errors.append(
            ValidationError(
                code="empty_collection",
                message=f"Expected at least one {record_name} record.",
                path=base_path,
            )
        )
        return []

    records: list[tuple[dict[str, Any], str]] = []
    for index, item in enumerate(raw_records):
        item_path = f"{base_path}[{index}]"
        if not isinstance(item, dict):
            errors.append(
                ValidationError(
                    code="invalid_json_shape",
                    message=f"Expected {record_name} record to be an object.",
                    path=item_path,
                )
            )
            continue
        records.append((item, item_path))
    return records


def _validate_confidence_labels(
    data: Any,
    *,
    strict: bool,
    errors: list[ValidationError],
    path: str,
) -> None:
    if data is None:
        return
    if not isinstance(data, dict):
        errors.append(
            ValidationError(
                code="invalid_json_shape",
                message="Expected confidence labels config to be an object.",
                path=path,
            )
        )
        return

    enum_root = data.get("concepts", data.get("enums", data))
    if not isinstance(enum_root, dict):
        errors.append(
            ValidationError(
                code="invalid_json_shape",
                message="Expected confidence labels concepts or enums to be an object.",
                path=f"{path}.concepts",
            )
        )
        return

    for canonical_key, canonical_values in CANONICAL_CONFIDENCE_ENUMS.items():
        aliases = CONFIDENCE_ENUM_KEY_ALIASES[canonical_key]
        found_key = next((key for key in aliases if key in enum_root), None)
        enum_path = f"{path}.{found_key or canonical_key}"
        if found_key is None:
            errors.append(
                ValidationError(
                    code="missing_confidence_enum",
                    message=f"Missing confidence enum: {canonical_key}.",
                    path=enum_path,
                )
            )
            continue

        values = _extract_enum_values(enum_root[found_key], enum_path, errors)
        _validate_unique_values(values, code="duplicate_confidence_enum_value", errors=errors, path=enum_path)

        allowed = set(canonical_values)
        for value in values:
            if value not in allowed:
                errors.append(
                    ValidationError(
                        code="invalid_confidence_enum",
                        message=f"Unknown {canonical_key} value: {value}.",
                        path=enum_path,
                    )
                )

        if strict:
            missing_values = [value for value in canonical_values if value not in values]
            for value in missing_values:
                errors.append(
                    ValidationError(
                        code="missing_confidence_enum_value",
                        message=f"Missing canonical {canonical_key} value: {value}.",
                        path=enum_path,
                    )
                )


def _extract_enum_values(
    enum_data: Any,
    path: str,
    errors: list[ValidationError],
) -> list[str]:
    if isinstance(enum_data, dict) and "values" in enum_data:
        enum_data = enum_data["values"]

    if not isinstance(enum_data, list):
        errors.append(
            ValidationError(
                code="invalid_json_shape",
                message="Expected confidence enum values to be an array.",
                path=path,
            )
        )
        return []

    values: list[str] = []
    for index, item in enumerate(enum_data):
        item_path = f"{path}[{index}]"
        if isinstance(item, str):
            value = item
        elif isinstance(item, dict):
            value = _first_string(item, ("id", "value", "name"))
            if value is None:
                errors.append(
                    ValidationError(
                        code="invalid_json_shape",
                        message="Expected confidence enum object to include id, value, or name.",
                        path=item_path,
                    )
                )
                continue
        else:
            errors.append(
                ValidationError(
                    code="invalid_json_shape",
                    message="Expected confidence enum value to be a string or object.",
                    path=item_path,
                )
            )
            continue

        if not value.strip():
            errors.append(
                ValidationError(
                    code="invalid_field",
                    message="Confidence enum values must be non-empty strings.",
                    path=item_path,
                )
            )
            continue
        values.append(value)
    return values


def _validate_principles(
    records: list[tuple[dict[str, Any], str]],
    source_ids: set[str],
    errors: list[ValidationError],
) -> set[str]:
    principle_ids = _validate_unique_record_ids(records, id_key="principleId", label="principle", errors=errors)
    for record, path in records:
        _validate_required_fields(record, REQUIRED_PRINCIPLE_FIELDS, path, errors)
        _validate_string_fields(
            record,
            ("principleId", "label", "status", "evidenceBasis", "definition", "requiredCaveat", "reviewedAt"),
            path,
            errors,
        )
        _validate_string_arrays(record, PRINCIPLE_ARRAY_FIELDS, path, errors)
        ref_path, refs = _extract_refs(record, "sourceIds", path, label="Source", errors=errors)
        for ref in refs:
            if ref not in source_ids:
                errors.append(
                    ValidationError(
                        code="unknown_source_ref",
                        message=f"Principle references unknown source id: {ref}.",
                        path=ref_path,
                    )
                )
        evidence_basis = record.get("evidenceBasis")
        if isinstance(evidence_basis, str) and evidence_basis not in CANONICAL_CONFIDENCE_ENUMS["evidenceBasis"]:
            errors.append(
                ValidationError(
                    code="invalid_confidence_enum",
                    message=f"Unknown principle evidenceBasis value: {evidence_basis}.",
                    path=f"{path}.evidenceBasis",
                )
            )
        _validate_iso_date_field(record, "reviewedAt", path, errors)
    return principle_ids


def _validate_lenses(
    records: list[tuple[dict[str, Any], str]],
    principle_ids: set[str],
    errors: list[ValidationError],
) -> set[str]:
    lens_ids = _validate_unique_record_ids(records, id_key="lensId", label="audience lens", errors=errors)
    for record, path in records:
        _validate_required_fields(record, REQUIRED_LENS_FIELDS, path, errors)
        _validate_string_fields(
            record,
            ("lensId", "label", "status", "roleFit", "defaultEvidenceBasis", "purpose", "recommendedValidation"),
            path,
            errors,
        )
        _validate_string_arrays(record, LENS_ARRAY_FIELDS, path, errors)
        if record.get("notMarketEvidence") is not True:
            errors.append(
                ValidationError(
                    code="invalid_field",
                    message="Audience lenses must explicitly set notMarketEvidence to true.",
                    path=f"{path}.notMarketEvidence",
                )
            )
        default_basis = record.get("defaultEvidenceBasis")
        if isinstance(default_basis, str) and default_basis not in CANONICAL_CONFIDENCE_ENUMS["evidenceBasis"]:
            errors.append(
                ValidationError(
                    code="invalid_confidence_enum",
                    message=f"Unknown audience lens defaultEvidenceBasis value: {default_basis}.",
                    path=f"{path}.defaultEvidenceBasis",
                )
            )
        ref_path, refs = _extract_refs(record, "principleIds", path, label="Audience lens principle", errors=errors)
        for ref in refs:
            if ref not in principle_ids:
                errors.append(
                    ValidationError(
                        code="unknown_principle_ref",
                        message=f"Audience lens references unknown principle id: {ref}.",
                        path=ref_path,
                    )
                )
    return lens_ids


def _validate_evidence_sources(
    records: list[tuple[dict[str, Any], str]],
    errors: list[ValidationError],
) -> set[str]:
    source_ids = _validate_unique_record_ids(records, id_key="sourceId", label="evidence source", errors=errors)
    for record, path in records:
        _validate_required_fields(record, REQUIRED_EVIDENCE_SOURCE_FIELDS, path, errors)
        _validate_string_fields(
            record,
            ("sourceId", "label", "sourceType", "supportTier", "excerptPolicy", "owner", "reviewedAt", "status"),
            path,
            errors,
        )
        if isinstance(record.get("sourceId"), str) and not re.fullmatch(r"source-[0-9]{3}", record["sourceId"]):
            errors.append(
                ValidationError(
                    code="invalid_id",
                    message="sourceId must use the source-001 pattern.",
                    path=f"{path}.sourceId",
                )
            )
        _validate_string_arrays(record, EVIDENCE_SOURCE_ARRAY_FIELDS, path, errors)
        for field_name in EVIDENCE_SOURCE_BOOLEAN_FIELDS:
            if field_name in record and not isinstance(record[field_name], bool):
                errors.append(
                    ValidationError(
                        code="invalid_field",
                        message=f"{field_name} must be a boolean.",
                        path=f"{path}.{field_name}",
                    )
                )
        if "retentionDays" in record:
            retention_days = record["retentionDays"]
            if not isinstance(retention_days, int) or isinstance(retention_days, bool) or retention_days < 0:
                errors.append(
                    ValidationError(
                        code="invalid_field",
                        message="retentionDays must be a non-negative integer.",
                        path=f"{path}.retentionDays",
                    )
                )
        _validate_iso_date_field(record, "reviewedAt", path, errors)
    return source_ids


def _validate_rubric(
    records: list[tuple[dict[str, Any], str]],
    principle_ids: set[str],
    *,
    strict: bool,
    errors: list[ValidationError],
) -> set[str]:
    dimension_ids: set[str] = set()
    seen_paths: dict[str, str] = {}
    for record, path in records:
        dimension_id = _dimension_id(record)
        if dimension_id is None:
            errors.append(
                ValidationError(
                    code="missing_required_field",
                    message="Rubric dimension must include id, dimensionId, or name.",
                    path=path,
                )
            )
        else:
            normalized_id = _normalize_identifier(dimension_id)
            if normalized_id in seen_paths:
                errors.append(
                    ValidationError(
                        code="duplicate_id",
                        message=f"Duplicate rubric dimension id: {dimension_id}.",
                        path=path,
                    )
                )
            seen_paths[normalized_id] = path
            dimension_ids.add(normalized_id)

        _validate_rubric_shape(record, path, errors)
        ref_path, refs = _extract_principle_refs(record, path, errors)
        for ref in refs:
            if ref not in principle_ids:
                errors.append(
                    ValidationError(
                        code="unknown_principle_ref",
                        message=f"Rubric dimension references unknown principle id: {ref}.",
                        path=ref_path,
                    )
                )

    if strict:
        missing = [dimension for dimension in REQUIRED_RUBRIC_DIMENSIONS if dimension not in dimension_ids]
        for dimension in missing:
            errors.append(
                ValidationError(
                    code="missing_rubric_dimension",
                    message=f"Missing required rubric dimension: {dimension}.",
                    path=REQUIRED_CONFIG_FILES["rubric"].file_name,
                )
            )

    return dimension_ids


def _validate_rubric_shape(record: dict[str, Any], path: str, errors: list[ValidationError]) -> None:
    if _dimension_id(record) is None:
        return

    score_range = record.get("scoreRange")
    score_scale = record.get("scoreScale")
    has_score_bounds = "scoreMin" in record and "scoreMax" in record
    has_score_scale = isinstance(score_scale, str) and bool(score_scale.strip())
    has_range_object = isinstance(score_range, dict) and "min" in score_range and "max" in score_range
    has_range_list = (
        isinstance(score_range, list)
        and len(score_range) == 2
        and all(isinstance(value, (int, float)) and not isinstance(value, bool) for value in score_range)
    )
    if not (has_score_scale or has_score_bounds or has_range_object or has_range_list):
        errors.append(
            ValidationError(
                code="missing_required_field",
                message="Rubric dimension must include scoreScale, scoreRange, or scoreMin/scoreMax.",
                path=f"{path}.scoreScale",
            )
        )

    _validate_string_arrays(record, RUBRIC_ARRAY_FIELDS, path, errors)
    _validate_score_anchors(record, path, errors)
    if not any(field_name in record for field_name in RUBRIC_PRINCIPLE_REF_FIELDS):
        errors.append(
            ValidationError(
                code="missing_required_field",
                message="Rubric dimension must include applicable principle references.",
                path=path,
            )
        )


def _extract_principle_refs(
    record: dict[str, Any],
    path: str,
    errors: list[ValidationError],
) -> tuple[str, list[str]]:
    field_name = next((candidate for candidate in RUBRIC_PRINCIPLE_REF_FIELDS if candidate in record), None)
    if field_name is None:
        return path, []

    return _extract_refs(record, field_name, path, label="Principle", errors=errors)


def _extract_refs(
    record: dict[str, Any],
    field_name: str,
    path: str,
    *,
    label: str,
    errors: list[ValidationError],
) -> tuple[str, list[str]]:
    ref_path = f"{path}.{field_name}"
    raw_refs = record[field_name]
    if not isinstance(raw_refs, list):
        errors.append(
            ValidationError(
                code="invalid_field",
                message=f"{field_name} must be an array.",
                path=ref_path,
            )
        )
        return ref_path, []

    refs: list[str] = []
    for index, raw_ref in enumerate(raw_refs):
        item_path = f"{ref_path}[{index}]"
        if isinstance(raw_ref, str):
            ref = raw_ref
        elif isinstance(raw_ref, dict):
            ref = _first_string(raw_ref, ("id", "principleId", "principle_id", "sourceId", "lensId", "dimensionId"))
            if ref is None:
                errors.append(
                    ValidationError(
                        code="invalid_field",
                        message=f"{label} reference objects must include a recognized id field.",
                        path=item_path,
                    )
                )
                continue
        else:
            errors.append(
                ValidationError(
                    code="invalid_field",
                    message=f"{label} references must be strings or objects.",
                    path=item_path,
                )
            )
            continue

        if not ref.strip():
            errors.append(
                ValidationError(
                    code="invalid_field",
                    message=f"{label} references must be non-empty.",
                    path=item_path,
                )
            )
            continue
        refs.append(ref)

    if not refs:
        errors.append(
            ValidationError(
                code="invalid_field",
                message=f"{field_name} must include at least one reference.",
                path=ref_path,
            )
        )
    return ref_path, refs


def _validate_score_anchors(record: dict[str, Any], path: str, errors: list[ValidationError]) -> None:
    anchors = record.get("scoreAnchors")
    if not isinstance(anchors, dict):
        errors.append(
            ValidationError(
                code="missing_required_field",
                message="Rubric dimension must include scoreAnchors.",
                path=f"{path}.scoreAnchors",
            )
        )
        return

    for score in ("0", "1", "2", "3", "4", "5"):
        value = anchors.get(score)
        if not isinstance(value, str) or not value.strip():
            errors.append(
                ValidationError(
                    code="missing_score_anchor",
                    message=f"Rubric dimension must include a non-empty score anchor for {score}.",
                    path=f"{path}.scoreAnchors.{score}",
                )
            )


def _validate_required_fields(
    record: dict[str, Any],
    required_fields: Iterable[str],
    path: str,
    errors: list[ValidationError],
) -> None:
    for field_name in required_fields:
        if field_name not in record:
            errors.append(
                ValidationError(
                    code="missing_required_field",
                    message=f"Missing required field: {field_name}.",
                    path=f"{path}.{field_name}",
                )
            )


def _validate_string_fields(
    record: dict[str, Any],
    field_names: Iterable[str],
    path: str,
    errors: list[ValidationError],
) -> None:
    for field_name in field_names:
        if field_name not in record:
            continue
        value = record[field_name]
        if not isinstance(value, str) or not value.strip():
            errors.append(
                ValidationError(
                    code="invalid_field",
                    message=f"{field_name} must be a non-empty string.",
                    path=f"{path}.{field_name}",
                )
            )


def _validate_string_arrays(
    record: dict[str, Any],
    field_names: Iterable[str],
    path: str,
    errors: list[ValidationError],
    *,
    allow_empty: bool = False,
) -> None:
    for field_name in field_names:
        if field_name not in record:
            continue
        value = record[field_name]
        field_path = f"{path}.{field_name}"
        if not isinstance(value, list) or (not allow_empty and not value):
            errors.append(
                ValidationError(
                    code="invalid_field",
                    message=f"{field_name} must be an array{'' if allow_empty else ' with at least one entry'}.",
                    path=field_path,
                )
            )
            continue
        for index, item in enumerate(value):
            if not isinstance(item, str) or not item.strip():
                errors.append(
                    ValidationError(
                        code="invalid_field",
                        message=f"{field_name} entries must be non-empty strings.",
                        path=f"{field_path}[{index}]",
                    )
                )


def _validate_iso_date_field(
    record: dict[str, Any],
    field_name: str,
    path: str,
    errors: list[ValidationError],
) -> None:
    if field_name not in record or not isinstance(record[field_name], str):
        return
    try:
        date.fromisoformat(record[field_name])
    except ValueError:
        errors.append(
            ValidationError(
                code="invalid_field",
                message=f"{field_name} must use ISO date format YYYY-MM-DD.",
                path=f"{path}.{field_name}",
            )
        )


def _validate_unique_record_ids(
    records: list[tuple[dict[str, Any], str]],
    *,
    id_key: str,
    label: str,
    errors: list[ValidationError],
) -> set[str]:
    ids: set[str] = set()
    for record, path in records:
        raw_id = record.get(id_key)
        if not isinstance(raw_id, str) or not raw_id.strip():
            errors.append(
                ValidationError(
                    code="missing_required_field",
                    message=f"{label} must include non-empty {id_key}.",
                    path=f"{path}.{id_key}",
                )
            )
            continue
        value = raw_id.strip()
        if value in ids:
            errors.append(
                ValidationError(
                    code="duplicate_id",
                    message=f"Duplicate {label} id: {value}.",
                    path=f"{path}.{id_key}",
                )
            )
            continue
        ids.add(value)
    return ids


def _validate_unique_values(
    values: list[str],
    *,
    code: str,
    errors: list[ValidationError],
    path: str,
) -> None:
    seen: set[str] = set()
    for value in values:
        if value in seen:
            errors.append(
                ValidationError(
                    code=code,
                    message=f"Duplicate value: {value}.",
                    path=path,
                )
            )
        seen.add(value)


def _dimension_id(record: dict[str, Any]) -> str | None:
    return _first_string(record, ("id", "dimensionId", "dimension_id", "name"))


def _first_string(record: dict[str, Any], keys: Iterable[str]) -> str | None:
    for key in keys:
        value = record.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _normalize_identifier(value: str) -> str:
    return "_".join(value.strip().lower().replace("-", "_").split())

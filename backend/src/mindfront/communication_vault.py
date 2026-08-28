"""Encrypted full-message corpus for Mindfront interaction assistance.

Connector content can be useful when wording, conversational sequence, and
resolved-ticket outcomes matter. This vault keeps the complete messages under
installation-local authenticated encryption and outside normal Mindfront
artifacts. Derived profiles remain bounded communication aids rather than
employee or psychological assessments.
"""

from __future__ import annotations

import hashlib
import html
import json
import os
import re
from collections import Counter, defaultdict
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from typing import Any

from .interaction_profiles import (
    ALLOWED_CONTEXTS,
    ALLOWED_PURPOSE,
    ALLOWED_SOURCE_SYSTEMS,
    InteractionProfileBlockedError,
    _normalize_name,
    _now,
    _parse_iso_datetime,
)
from .vault_crypto import (
    CURRENT_ENCRYPTION,
    VaultEncryptionError,
    decrypt_envelope,
    write_encrypted_payload,
)


INTERNAL_EMAIL_DOMAIN = os.getenv("MINDFRONT_INTERNAL_EMAIL_DOMAIN", "corp.example").strip().casefold().lstrip("@")


def _is_internal_email(address: str) -> bool:
    return bool(address and INTERNAL_EMAIL_DOMAIN and address.strip().casefold().endswith(f"@{INTERNAL_EMAIL_DOMAIN}"))

ALLOWED_CONTAINER_TYPES = {
    "outlook_email",
    "support_ticket",
    "teams_channel",
    "teams_chat",
}
ALLOWED_TICKET_OUTCOMES = {
    "advanced_work",
    "approved",
    "approved_with_conditions",
    "clarified",
    "deferred",
    "redirected",
    "resolved_ticket",
    "unknown",
}
ALLOWED_EXCLUSION_REASONS = {
    "credentials_and_secrets",
    "cui_and_export_controlled",
    "invalid_record",
    "missing_authored_content",
    "non_internal_author",
    "non_person_sender",
    "non_terminal_ticket",
    "unresolved_identity",
}
SECRET_PATTERNS = (
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----", re.IGNORECASE),
    re.compile(r"\b(?:api[_ -]?key|client[_ -]?secret|password|access[_ -]?token)\s*[:=]\s*\S+", re.IGNORECASE),
    re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]{20,}", re.IGNORECASE),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
)
CONTROLLED_MARKER_PATTERNS = (
    re.compile(r"\bCONTROLLED UNCLASSIFIED INFORMATION\b", re.IGNORECASE),
    re.compile(r"^\s*CUI(?:\s*//\s*[A-Z0-9/_-]+)?(?:\s+(?:BASIC|SPECIFIED))?\s*$", re.IGNORECASE | re.MULTILINE),
    re.compile(
        r"^\s*(?:CLASSIFICATION|HANDLING|DISTRIBUTION(?:\s+STATEMENT)?)\s*:\s*CUI\b",
        re.IGNORECASE | re.MULTILINE,
    ),
    re.compile(r"^\s*(?:ITAR|NOFORN)\s*$", re.IGNORECASE | re.MULTILINE),
    re.compile(r"\bEXPORT[\s-]+CONTROLLED\b", re.IGNORECASE),
)
WORD_PATTERN = re.compile(r"[A-Za-z][A-Za-z0-9'-]{1,40}")
URL_PATTERN = re.compile(r"https?://\S+", re.IGNORECASE)
EMAIL_PATTERN = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
PHONE_PATTERN = re.compile(
    r"(?<!\d)(?:\+?1[\s.-]?)?(?:\(\d{3}\)|\d{3})[\s.-]?\d{3}[\s.-]?\d{4}(?!\d)"
)
SSN_PATTERN = re.compile(r"(?<!\d)\d{3}-\d{2}-\d{4}(?!\d)")
HTML_TAG_PATTERN = re.compile(r"<[^>]+>")
OUTLOOK_QUOTE_HTML_PATTERN = re.compile(
    r"""(?is)<(?:div|blockquote)\b[^>]*(?:id|class)\s*=\s*["'][^"']*(?:divRplyFwdMsg|gmail_quote|yahoo_quoted)[^"']*["'][^>]*>"""
)
ORIGINAL_MESSAGE_PATTERN = re.compile(
    r"(?im)^(?:-{2,}\s*original\s+message\s*-{2,}|from:\s*.+\r?\n(?:sent|date):\s*.+|on\s+.+\s+wrote:\s*$)"
)
TICKET_QUOTE_HTML_PATTERN = re.compile(
    r"""(?is)(?:<blockquote\b[^>]*>|<div\b[^>]*(?:class|id)\s*=\s*["'][^"']*(?:quote|quoted|reply-history|previous-message)[^"']*["'][^>]*>)"""
)
TICKET_QUOTE_TEXT_PATTERN = re.compile(
    r"(?im)^(?:>{1,}\s*.+|_{5,}\s*$|-{2,}\s*(?:previous reply|ticket history)\s*-{2,}\s*$)"
)
ALLOWED_SENT_AT_PRECISIONS = {
    "message_timestamp",
    "snapshot_timestamp",
}
STOP_WORDS = {
    "about",
    "after",
    "again",
    "also",
    "and",
    "are",
    "because",
    "been",
    "before",
    "being",
    "but",
    "can",
    "could",
    "did",
    "does",
    "for",
    "from",
    "have",
    "here",
    "into",
    "just",
    "like",
    "more",
    "not",
    "our",
    "out",
    "please",
    "should",
    "that",
    "the",
    "their",
    "there",
    "they",
    "this",
    "was",
    "we",
    "were",
    "what",
    "when",
    "where",
    "which",
    "will",
    "with",
    "would",
    "you",
    "your",
}


def validate_corpus_batch(batch: dict[str, Any]) -> list[dict[str, str]]:
    """Validate a raw communication batch intended for encrypted storage."""

    errors: list[dict[str, str]] = []
    allowed_top = {
        "artifactType",
        "schemaVersion",
        "batchId",
        "purpose",
        "authorization",
        "collection",
        "messages",
    }
    _unknown_fields(batch, allowed_top, "$", errors)
    if batch.get("artifactType") != "communication_corpus_batch":
        _error(errors, "invalid_artifact_type", "artifactType", "Expected communication_corpus_batch.")
    if batch.get("schemaVersion") != 1:
        _error(errors, "invalid_schema_version", "schemaVersion", "Expected schemaVersion 1.")
    if not isinstance(batch.get("batchId"), str) or not re.fullmatch(
        r"corpus-batch-[a-z0-9][a-z0-9-]{5,80}",
        batch.get("batchId", ""),
    ):
        _error(errors, "invalid_batch_id", "batchId", "Batch id must use corpus-batch- naming.")
    if batch.get("purpose") != ALLOWED_PURPOSE:
        _error(errors, "invalid_purpose", "purpose", f"Purpose must be {ALLOWED_PURPOSE}.")

    authorization = batch.get("authorization")
    if not isinstance(authorization, dict):
        _error(errors, "missing_authorization", "authorization", "Authorization metadata is required.")
    else:
        _unknown_fields(
            authorization,
            {
                "requesterHasLegitimateAccess",
                "companySystemContentAuthorized",
                "codexProcessingAuthorized",
                "assistiveUseOnly",
                "noEmploymentDecisionUse",
                "humanReviewRequired",
                "privateOneToOneIncluded",
                "privateOneToOneUseApproved",
                "governanceBasis",
            },
            "authorization",
            errors,
        )
        for field in (
            "requesterHasLegitimateAccess",
            "companySystemContentAuthorized",
            "codexProcessingAuthorized",
            "assistiveUseOnly",
            "noEmploymentDecisionUse",
            "humanReviewRequired",
        ):
            if authorization.get(field) is not True:
                _error(errors, "authorization_gate_failed", f"authorization.{field}", f"{field} must be true.")
        if authorization.get("governanceBasis") != "user_asserted_company_policy":
            _error(
                errors,
                "governance_basis_missing",
                "authorization.governanceBasis",
                "The current approved basis is user_asserted_company_policy.",
            )
        if authorization.get("privateOneToOneIncluded") is True and authorization.get(
            "privateOneToOneUseApproved"
        ) is not True:
            _error(
                errors,
                "private_message_approval_missing",
                "authorization.privateOneToOneUseApproved",
                "Private one-to-one use must be explicitly approved.",
            )

    collection = batch.get("collection")
    if not isinstance(collection, dict):
        _error(errors, "missing_collection", "collection", "Collection metadata is required.")
    else:
        _unknown_fields(
            collection,
            {
                "sourceSystems",
                "windowStart",
                "windowEnd",
                "coverageComplete",
                "attachmentsProcessed",
                "restrictedMaterialPresent",
                "credentialSecretScanPassed",
                "rawContentRetainedEncrypted",
                "externalModelProcessingUsed",
                "excludedMessageCount",
                "excludedReasonCounts",
                "sourceFormat",
                "sourceArtifactHashes",
            },
            "collection",
            errors,
        )
        sources = collection.get("sourceSystems")
        if not isinstance(sources, list) or not sources:
            _error(errors, "missing_sources", "collection.sourceSystems", "At least one source is required.")
        else:
            unknown = sorted(set(sources) - ALLOWED_SOURCE_SYSTEMS)
            if unknown:
                _error(errors, "unknown_source", "collection.sourceSystems", f"Unknown sources: {', '.join(unknown)}.")
        if collection.get("coverageComplete") is not False:
            _error(errors, "coverage_overclaim", "collection.coverageComplete", "Coverage must remain partial.")
        if collection.get("attachmentsProcessed") is not False:
            _error(errors, "attachments_not_allowed", "collection.attachmentsProcessed", "Attachments are not ingested.")
        if collection.get("restrictedMaterialPresent") is not False:
            _error(
                errors,
                "restricted_material_present",
                "collection.restrictedMaterialPresent",
                "Controlled or restricted material must use an approved enclave-specific path.",
            )
        if collection.get("credentialSecretScanPassed") is not True:
            _error(
                errors,
                "credential_scan_missing",
                "collection.credentialSecretScanPassed",
                "Credential and secret scanning must pass before ingestion.",
            )
        if collection.get("rawContentRetainedEncrypted") is not True:
            _error(
                errors,
                "raw_retention_disclosure_missing",
                "collection.rawContentRetainedEncrypted",
                "Full-message retention must be explicitly declared.",
            )
        if not isinstance(collection.get("externalModelProcessingUsed"), bool):
            _error(
                errors,
                "model_processing_disclosure_missing",
                "collection.externalModelProcessingUsed",
                "externalModelProcessingUsed must be a boolean.",
            )
        excluded_count = collection.get("excludedMessageCount", 0)
        if not isinstance(excluded_count, int) or isinstance(excluded_count, bool) or excluded_count < 0:
            _error(
                errors,
                "invalid_excluded_message_count",
                "collection.excludedMessageCount",
                "excludedMessageCount must be a nonnegative integer.",
            )
        reason_counts = collection.get("excludedReasonCounts", {})
        if not isinstance(reason_counts, dict) or any(
            key not in ALLOWED_EXCLUSION_REASONS
            or not isinstance(value, int)
            or isinstance(value, bool)
            or value < 0
            for key, value in reason_counts.items()
        ):
            _error(
                errors,
                "invalid_excluded_reason_counts",
                "collection.excludedReasonCounts",
                "Excluded reason counts must use supported categories and nonnegative integers.",
            )
        elif isinstance(excluded_count, int) and sum(reason_counts.values()) != excluded_count:
            _error(
                errors,
                "excluded_count_mismatch",
                "collection.excludedReasonCounts",
                "Excluded reason counts must sum to excludedMessageCount.",
            )
        _validate_datetime(collection.get("windowStart"), "collection.windowStart", errors)
        _validate_datetime(collection.get("windowEnd"), "collection.windowEnd", errors)
        if collection.get("sourceFormat") is not None and not isinstance(collection.get("sourceFormat"), str):
            _error(
                errors,
                "invalid_source_format",
                "collection.sourceFormat",
                "sourceFormat must be text when supplied.",
            )
        source_hashes = collection.get("sourceArtifactHashes", {})
        if not isinstance(source_hashes, dict) or any(
            not isinstance(label, str)
            or not re.fullmatch(r"sha256:[0-9a-f]{64}", value if isinstance(value, str) else "")
            for label, value in source_hashes.items()
        ):
            _error(
                errors,
                "invalid_source_artifact_hashes",
                "collection.sourceArtifactHashes",
                "Source artifact hashes must be SHA-256 values keyed by artifact label.",
            )

    messages = batch.get("messages")
    if not isinstance(messages, list) or not messages:
        _error(errors, "missing_messages", "messages", "At least one full message is required.")
    else:
        for index, message in enumerate(messages):
            _validate_message(message, index, errors)
    return errors


def corpus_batch_from_outlook_export(export: dict[str, Any], *, batch_id: str) -> dict[str, Any]:
    """Convert one Outlook search page into an internal-person corpus batch."""

    results = export.get("results")
    if not isinstance(results, list):
        raise InteractionProfileBlockedError(
            [{"code": "invalid_outlook_export", "path": "results", "message": "Outlook results list is missing."}]
        )
    messages: list[dict[str, Any]] = []
    excluded_reason_counts: Counter[str] = Counter()
    for item in results:
        if not isinstance(item, dict):
            continue
        sender_container = item.get("sender") or item.get("from") or {}
        sender = (sender_container.get("emailAddress") or {}) if isinstance(sender_container, dict) else {}
        address = str(sender.get("address") or "").strip().casefold()
        name = str(sender.get("name") or "").strip()
        if not _is_internal_email(address) or not name or _looks_automated_sender(name, address):
            continue
        body = str(((item.get("body") or {}).get("content") or "")).strip()
        if not body:
            continue
        excluded_reason = _excluded_content_reason(body)
        if excluded_reason:
            excluded_reason_counts[excluded_reason] += 1
            continue
        sent_at = str(item.get("sentDateTime") or item.get("receivedDateTime") or "")
        try:
            _parse_iso_datetime(sent_at)
        except (TypeError, ValueError):
            continue
        recipients = [
            str(((recipient or {}).get("emailAddress") or {}).get("address") or "").strip().casefold()
            for field in ("toRecipients", "ccRecipients", "bccRecipients")
            for recipient in item.get(field) or []
        ]
        subject = str(item.get("subject") or "").strip()
        native_conversation_id = str(
            item.get("conversationId") or item.get("conversation_id") or ""
        ).strip()
        if native_conversation_id:
            conversation_seed = f"outlook-conversation:{native_conversation_id}"
        else:
            conversation_seed = "|".join(
                [
                    _normalized_subject(subject),
                    *sorted({address, *[recipient for recipient in recipients if recipient]}),
                ]
            )
        messages.append(
            {
                "sourceSystem": "microsoft_outlook",
                "sourceRecordId": str(item.get("id") or _sha256(subject + sent_at + address)),
                "modifiedAt": sent_at,
                "author": {
                    "displayName": name,
                    "identityResolution": "confirmed_directory_identity",
                    "identityFingerprint": _sha256(address),
                },
                "sentAt": sent_at,
                "sentAtPrecision": "message_timestamp",
                "sequenceIndex": 0,
                "context": _classify_context(subject, body),
                "conversationFingerprint": _sha256(conversation_seed),
                "containerType": "outlook_email",
                "subject": subject or None,
                "body": body,
                "ticketOutcome": None,
            }
        )
    return _connector_corpus_batch(
        batch_id=batch_id,
        messages=messages,
        source_systems=["microsoft_outlook"],
        excluded_reason_counts=excluded_reason_counts,
    )


def corpus_batch_from_teams_export(export: dict[str, Any], *, batch_id: str) -> dict[str, Any]:
    """Convert fetched Teams transcripts and member maps into a corpus batch."""

    threads = export.get("threads")
    if not isinstance(threads, list):
        raise InteractionProfileBlockedError(
            [{"code": "invalid_teams_export", "path": "threads", "message": "Teams thread list is missing."}]
        )
    messages: list[dict[str, Any]] = []
    excluded_reason_counts: Counter[str] = Counter()
    for entry in threads:
        if not isinstance(entry, dict):
            continue
        thread = entry.get("thread") or {}
        transcript = entry.get("transcript") or {}
        members = entry.get("members") or {}
        chat_id = str(thread.get("chat_id") or transcript.get("chat_id") or "")
        if not chat_id:
            continue
        member_indexes = _teams_member_indexes(members.get("members") or [])
        content = str(transcript.get("content") or "")
        title = str(transcript.get("title") or thread.get("container_title") or "").strip()
        observed_at = _valid_iso_value(
            transcript.get("created_at") or thread.get("latest_message_at")
        )
        transcript_identity = _teams_transcript_identity(
            chat_id=chat_id,
            transcript=transcript,
            content=content,
            title=title,
        )
        chunks = _teams_message_chunks(entry, transcript, content)
        for sequence, chunk in enumerate(chunks):
            member = _resolve_teams_member(chunk, member_indexes)
            if not member:
                excluded_reason_counts["unresolved_identity"] += 1
                continue
            author_name = str(
                member.get("display_name")
                or member.get("displayName")
                or chunk.get("authorName")
                or ""
            ).strip()
            address = _teams_member_email(member)
            member_id = _teams_member_id(member)
            if address and not _is_internal_email(address):
                excluded_reason_counts["non_internal_author"] += 1
                continue
            if not address and not member_id:
                excluded_reason_counts["unresolved_identity"] += 1
                continue
            if _looks_automated_sender(author_name, address):
                continue
            body = str(chunk.get("body") or "").strip()
            if not body or re.fullmatch(r"(?:!\[[^\]]*\]\([^)]+\)\s*)+", body):
                continue
            excluded_reason = _excluded_content_reason(body)
            if excluded_reason:
                excluded_reason_counts[excluded_reason] += 1
                continue
            sent_at = _valid_iso_value(chunk.get("sentAt"))
            if sent_at:
                sent_at_precision = "message_timestamp"
            elif observed_at:
                sent_at = observed_at
                sent_at_precision = "snapshot_timestamp"
            else:
                excluded_reason_counts["invalid_record"] += 1
                continue
            modified_at = _valid_iso_value(chunk.get("modifiedAt")) or sent_at
            native_message_id = str(chunk.get("messageId") or "").strip()
            if native_message_id:
                source_record_id = f"teams:{chat_id}:message:{native_message_id}"
            else:
                source_record_id = (
                    f"teams:{chat_id}:transcript:{transcript_identity}:chunk:{sequence}"
                )
            identity_seed = address or f"teams-user:{member_id}"
            messages.append(
                {
                    "sourceSystem": "microsoft_teams",
                    "sourceRecordId": source_record_id,
                    "modifiedAt": modified_at,
                    "author": {
                        "displayName": author_name,
                        "identityResolution": "confirmed_directory_identity",
                        "identityFingerprint": _sha256(identity_seed),
                    },
                    "sentAt": sent_at,
                    "sentAtPrecision": sent_at_precision,
                    "sequenceIndex": sequence,
                    "context": _classify_context(title, body),
                    "conversationFingerprint": _sha256(chat_id),
                    "containerType": "teams_chat",
                    "subject": title or None,
                    "body": body,
                    "ticketOutcome": None,
                }
            )
    return _connector_corpus_batch(
        batch_id=batch_id,
        messages=messages,
        source_systems=["microsoft_teams"],
        excluded_reason_counts=excluded_reason_counts,
    )


def corpus_batch_from_freshservice_jsonl(
    cases_path: str | Path,
    *,
    cleaning_manifest_path: str | Path,
    export_manifest_path: str | Path,
    batch_id: str,
    existing_vault_path: str | Path | None = None,
    identity_map: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Convert the normalized Freshservice source pack into a resolved-ticket batch."""

    cases_file = Path(cases_path)
    cleaning_file = Path(cleaning_manifest_path)
    export_file = Path(export_manifest_path)
    try:
        cleaning_manifest = json.loads(cleaning_file.read_text(encoding="utf-8-sig"))
        export_manifest = json.loads(export_file.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise InteractionProfileBlockedError(
            [
                {
                    "code": "freshservice_manifest_unreadable",
                    "path": str(cleaning_file),
                    "message": str(exc),
                }
            ]
        ) from exc

    manifest_errors: list[dict[str, str]] = []
    if export_manifest.get("read_only") is not True:
        _error(
            manifest_errors,
            "freshservice_export_not_read_only",
            str(export_file),
            "The Freshservice export manifest must declare read_only true.",
        )
    if cleaning_manifest.get("include_private_notes") is not True:
        _error(
            manifest_errors,
            "freshservice_private_notes_missing",
            str(cleaning_file),
            "The full internal source pack must include private notes.",
        )
    if cleaning_manifest.get("deduplicate_messages") is not False:
        _error(
            manifest_errors,
            "freshservice_messages_deduplicated",
            str(cleaning_file),
            "The source pack must preserve duplicate conversation rows.",
        )
    if ((cleaning_manifest.get("redaction_mode") or {}).get("secret_like_values")) != "always":
        _error(
            manifest_errors,
            "freshservice_secret_redaction_unverified",
            str(cleaning_file),
            "The cleaning manifest must declare always-on secret-like value redaction.",
        )
    source_ticket_count = cleaning_manifest.get("source_ticket_count")
    export_ticket_count = export_manifest.get("ticket_count")
    if not isinstance(source_ticket_count, int) or source_ticket_count != export_ticket_count:
        _error(
            manifest_errors,
            "freshservice_ticket_count_mismatch",
            str(cleaning_file),
            "Cleaning and export manifests must agree on ticket count.",
        )
    source_conversation_count = cleaning_manifest.get("source_conversation_count")
    export_conversation_count = export_manifest.get("conversation_count")
    if not isinstance(source_conversation_count, int) or source_conversation_count != export_conversation_count:
        _error(
            manifest_errors,
            "freshservice_conversation_count_mismatch",
            str(cleaning_file),
            "Cleaning and export manifests must agree on conversation count.",
        )
    if manifest_errors:
        raise InteractionProfileBlockedError(manifest_errors)

    name_by_fingerprint: dict[str, str] = {}
    if existing_vault_path is not None:
        vault = _load_vault(Path(existing_vault_path), missing_ok=True)
        name_by_fingerprint.update(_identity_name_index(vault))
    email_map, user_id_map = _validate_freshservice_identity_map(identity_map)

    messages: list[dict[str, Any]] = []
    excluded_reason_counts: Counter[str] = Counter()
    seen_ticket_ids: set[str] = set()
    seen_source_ids: set[str] = set()
    case_count = 0
    conversation_count = 0
    integrity_errors: list[dict[str, str]] = []
    try:
        with cases_file.open("r", encoding="utf-8-sig") as handle:
            for line_number, raw_line in enumerate(handle, start=1):
                if not raw_line.strip():
                    continue
                case_count += 1
                try:
                    case = json.loads(raw_line)
                except json.JSONDecodeError as exc:
                    _error(
                        integrity_errors,
                        "freshservice_invalid_jsonl",
                        f"{cases_file}:{line_number}",
                        str(exc),
                    )
                    continue
                if not isinstance(case, dict):
                    _error(
                        integrity_errors,
                        "freshservice_invalid_case",
                        f"{cases_file}:{line_number}",
                        "Each JSONL line must be an object.",
                    )
                    continue
                ticket_id = str(case.get("ticket_id") or "").strip()
                if not ticket_id or ticket_id in seen_ticket_ids:
                    _error(
                        integrity_errors,
                        "freshservice_duplicate_or_missing_ticket_id",
                        f"{cases_file}:{line_number}",
                        "Every case requires a unique ticket_id.",
                    )
                    continue
                seen_ticket_ids.add(ticket_id)
                case_messages = case.get("messages")
                if not isinstance(case_messages, list):
                    _error(
                        integrity_errors,
                        "freshservice_messages_missing",
                        f"{cases_file}:{line_number}",
                        "Each case requires a messages list.",
                    )
                    continue
                conversation_count += len(case_messages)
                status = str(case.get("status_code") or "").strip()
                if status not in {"4", "5"}:
                    excluded_reason_counts["non_terminal_ticket"] += len(case_messages)
                    continue
                subject = str(case.get("subject") or "").strip() or None
                context = (
                    "incident_response"
                    if "incident" in str(case.get("type") or "").casefold()
                    else "support_request"
                )
                for sequence, item in enumerate(case_messages):
                    item_path = f"{cases_file}:{line_number}:messages[{sequence}]"
                    if not isinstance(item, dict):
                        _error(
                            integrity_errors,
                            "freshservice_invalid_message",
                            item_path,
                            "Conversation row must be an object.",
                        )
                        continue
                    conversation_id = str(item.get("conversation_id") or "").strip()
                    source_record_id = (
                        f"freshservice:ticket:{ticket_id}:conversation:{conversation_id}"
                        if conversation_id
                        else ""
                    )
                    if not source_record_id or source_record_id in seen_source_ids:
                        _error(
                            integrity_errors,
                            "freshservice_duplicate_or_missing_conversation_id",
                            item_path,
                            "Every conversation requires a unique conversation_id.",
                        )
                        continue
                    seen_source_ids.add(source_record_id)
                    body = str(item.get("body") or "").strip()
                    if not body or body.startswith("[No body text returned by Freshservice"):
                        excluded_reason_counts["missing_authored_content"] += 1
                        continue
                    excluded_reason = _excluded_content_reason(body)
                    if excluded_reason:
                        excluded_reason_counts[excluded_reason] += 1
                        continue
                    sent_at = str(item.get("created_at") or "").strip()
                    modified_at = str(item.get("updated_at") or sent_at).strip() or sent_at
                    try:
                        _parse_iso_datetime(sent_at)
                        _parse_iso_datetime(modified_at)
                    except (TypeError, ValueError):
                        _error(
                            integrity_errors,
                            "freshservice_invalid_timestamp",
                            item_path,
                            "Conversation timestamps must be ISO 8601 values with timezone.",
                        )
                        continue
                    email = str(item.get("from_email") or "").strip().casefold()
                    user_id = str(item.get("user_id") or "").strip()
                    display_name = ""
                    identity_fingerprint = ""
                    if _is_internal_email(email):
                        identity_fingerprint = _sha256(email)
                        display_name = email_map.get(email) or name_by_fingerprint.get(identity_fingerprint, "")
                    elif email:
                        excluded_reason_counts["non_internal_author"] += 1
                        continue
                    if not display_name and user_id:
                        mapped = user_id_map.get(user_id)
                        if mapped:
                            display_name = mapped["displayName"]
                            identity_fingerprint = mapped["identityFingerprint"]
                    if not display_name or not identity_fingerprint:
                        excluded_reason_counts["unresolved_identity"] += 1
                        continue
                    if _looks_automated_sender(display_name, email):
                        excluded_reason_counts["non_person_sender"] += 1
                        continue
                    messages.append(
                        {
                            "sourceSystem": "resolved_support_ticket",
                            "sourceRecordId": source_record_id,
                            "modifiedAt": modified_at,
                            "author": {
                                "displayName": display_name,
                                "identityResolution": "confirmed_ticket_identity",
                                "identityFingerprint": identity_fingerprint,
                            },
                            "sentAt": sent_at,
                            "sentAtPrecision": "message_timestamp",
                            "sequenceIndex": sequence,
                            "context": context,
                            "conversationFingerprint": _sha256(f"freshservice:ticket:{ticket_id}"),
                            "containerType": "support_ticket",
                            "subject": subject,
                            "body": body,
                            "ticketOutcome": "resolved_ticket",
                        }
                    )
    except OSError as exc:
        raise InteractionProfileBlockedError(
            [{"code": "freshservice_jsonl_unreadable", "path": str(cases_file), "message": str(exc)}]
        ) from exc

    if case_count != source_ticket_count:
        _error(
            integrity_errors,
            "freshservice_case_count_mismatch",
            str(cases_file),
            f"JSONL contains {case_count} cases; manifest declares {source_ticket_count}.",
        )
    if conversation_count != source_conversation_count:
        _error(
            integrity_errors,
            "freshservice_message_count_mismatch",
            str(cases_file),
            f"JSONL contains {conversation_count} messages; manifest declares {source_conversation_count}.",
        )
    if integrity_errors:
        raise InteractionProfileBlockedError(integrity_errors[:50])

    return _connector_corpus_batch(
        batch_id=batch_id,
        messages=messages,
        source_systems=["resolved_support_ticket"],
        excluded_reason_counts=excluded_reason_counts,
        external_model_processing_used=False,
        source_format="freshservice-agent-cases-jsonl-v1",
        source_artifact_hashes={
            "casesJsonl": _file_sha256(cases_file),
            "cleaningManifest": _file_sha256(cleaning_file),
            "exportManifest": _file_sha256(export_file),
        },
    )


def _connector_corpus_batch(
    *,
    batch_id: str,
    messages: list[dict[str, Any]],
    source_systems: list[str],
    excluded_reason_counts: Counter[str] | None = None,
    external_model_processing_used: bool = True,
    source_format: str | None = None,
    source_artifact_hashes: dict[str, str] | None = None,
) -> dict[str, Any]:
    if not messages:
        raise InteractionProfileBlockedError(
            [
                {
                    "code": "no_usable_connector_messages",
                    "path": batch_id,
                    "message": "The connector export contained no authored internal messages eligible for ingestion.",
                }
            ]
        )
    ordered = sorted(messages, key=_message_sort_key)
    excluded_reason_counts = excluded_reason_counts or Counter()
    return {
        "artifactType": "communication_corpus_batch",
        "schemaVersion": 1,
        "batchId": batch_id,
        "purpose": ALLOWED_PURPOSE,
        "authorization": {
            "requesterHasLegitimateAccess": True,
            "companySystemContentAuthorized": True,
            "codexProcessingAuthorized": True,
            "assistiveUseOnly": True,
            "noEmploymentDecisionUse": True,
            "humanReviewRequired": True,
            "privateOneToOneIncluded": True,
            "privateOneToOneUseApproved": True,
            "governanceBasis": "user_asserted_company_policy",
        },
        "collection": {
            "sourceSystems": sorted(set(source_systems)),
            "windowStart": ordered[0]["sentAt"],
            "windowEnd": ordered[-1]["sentAt"],
            "coverageComplete": False,
            "attachmentsProcessed": False,
            "restrictedMaterialPresent": False,
            "credentialSecretScanPassed": True,
            "rawContentRetainedEncrypted": True,
            "externalModelProcessingUsed": external_model_processing_used,
            "excludedMessageCount": sum(excluded_reason_counts.values()),
            "excludedReasonCounts": dict(sorted(excluded_reason_counts.items())),
            "sourceFormat": source_format,
            "sourceArtifactHashes": dict(sorted((source_artifact_hashes or {}).items())),
        },
        "messages": ordered,
    }


def _parse_teams_transcript(content: str) -> list[tuple[str, str]]:
    marker = re.compile(
        r"(?m)^(?:\[([^\]\r\n]{1,120})\]:|([^\r\n]{1,120}?)\s+said:)[ \t]*"
    )
    matches = list(marker.finditer(content))
    chunks: list[tuple[str, str]] = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(content)
        body = content[match.end() : end].strip()
        if body:
            chunks.append(((match.group(1) or match.group(2)).strip(), body))
    return chunks


def _teams_message_chunks(
    entry: dict[str, Any],
    transcript: dict[str, Any],
    content: str,
) -> list[dict[str, Any]]:
    structured = transcript.get("messages")
    if not isinstance(structured, list):
        structured = entry.get("messages")
    if isinstance(structured, list):
        chunks: list[dict[str, Any]] = []
        for item in structured:
            if not isinstance(item, dict):
                continue
            author = item.get("author") or item.get("from") or item.get("sender") or {}
            if not isinstance(author, dict):
                author = {}
            nested_user = author.get("user") or {}
            if not isinstance(nested_user, dict):
                nested_user = {}
            body_value = item.get("body")
            if isinstance(body_value, dict):
                body_value = body_value.get("content") or body_value.get("text")
            chunks.append(
                {
                    "authorName": _first_text(
                        author.get("display_name"),
                        author.get("displayName"),
                        author.get("name"),
                        nested_user.get("display_name"),
                        nested_user.get("displayName"),
                    ),
                    "authorId": _first_text(
                        author.get("id"),
                        author.get("user_id"),
                        author.get("userId"),
                        author.get("aadObjectId"),
                        nested_user.get("id"),
                        nested_user.get("userId"),
                    ),
                    "authorEmail": _first_text(
                        author.get("email"),
                        author.get("mail"),
                        author.get("userPrincipalName"),
                        nested_user.get("email"),
                        nested_user.get("mail"),
                        nested_user.get("userPrincipalName"),
                    ).casefold(),
                    "body": str(body_value or item.get("content") or item.get("text") or ""),
                    "messageId": _first_text(
                        item.get("id"),
                        item.get("message_id"),
                        item.get("messageId"),
                    ),
                    "sentAt": _first_text(
                        item.get("sent_at"),
                        item.get("sentDateTime"),
                        item.get("created_at"),
                        item.get("createdDateTime"),
                        item.get("timestamp"),
                    ),
                    "modifiedAt": _first_text(
                        item.get("modified_at"),
                        item.get("modifiedDateTime"),
                        item.get("lastModifiedDateTime"),
                    ),
                }
            )
        return chunks
    return [
        {
            "authorName": author_name,
            "authorId": "",
            "authorEmail": "",
            "body": body,
            "messageId": "",
            "sentAt": "",
            "modifiedAt": "",
        }
        for author_name, body in _parse_teams_transcript(content)
    ]


def _teams_member_indexes(
    raw_members: list[Any],
) -> dict[str, dict[str, list[dict[str, Any]]]]:
    indexes: dict[str, dict[str, list[dict[str, Any]]]] = {
        "id": defaultdict(list),
        "email": defaultdict(list),
        "name": defaultdict(list),
    }
    for member in raw_members:
        if not isinstance(member, dict):
            continue
        member_id = _teams_member_id(member)
        email = _teams_member_email(member)
        display_name = str(
            member.get("display_name")
            or member.get("displayName")
            or member.get("name")
            or ""
        ).strip()
        if member_id:
            indexes["id"][member_id].append(member)
        if email:
            indexes["email"][email].append(member)
        if display_name:
            indexes["name"][_normalize_name(display_name)].append(member)
    return indexes


def _resolve_teams_member(
    chunk: dict[str, Any],
    indexes: dict[str, dict[str, list[dict[str, Any]]]],
) -> dict[str, Any] | None:
    author_id = str(chunk.get("authorId") or "").strip()
    author_email = str(chunk.get("authorEmail") or "").strip().casefold()
    if author_id and author_email:
        by_id = _one_confirmed_teams_member(indexes["id"].get(author_id, []))
        by_email = _one_confirmed_teams_member(indexes["email"].get(author_email, []))
        if (
            by_id is None
            or by_email is None
            or _teams_identity_key(by_id) != _teams_identity_key(by_email)
        ):
            return None
        return by_id
    if author_id:
        return _one_confirmed_teams_member(indexes["id"].get(author_id, []))
    if author_email:
        return _one_confirmed_teams_member(indexes["email"].get(author_email, []))
    author_name = str(chunk.get("authorName") or "").strip()
    if not author_name:
        return None
    return _one_confirmed_teams_member(
        indexes["name"].get(_normalize_name(author_name), [])
    )


def _one_confirmed_teams_member(
    candidates: list[dict[str, Any]],
) -> dict[str, Any] | None:
    by_identity: dict[str, dict[str, Any]] = {}
    for member in candidates:
        identity = _teams_identity_key(member)
        if identity:
            by_identity[identity] = member
    if len(by_identity) != 1:
        return None
    return next(iter(by_identity.values()))


def _teams_identity_key(member: dict[str, Any]) -> str:
    email = _teams_member_email(member)
    if email:
        return email
    member_id = _teams_member_id(member)
    return f"teams-user:{member_id}" if member_id else ""


def _teams_member_id(member: dict[str, Any]) -> str:
    return _first_text(
        member.get("id"),
        member.get("user_id"),
        member.get("userId"),
        member.get("aad_object_id"),
        member.get("aadObjectId"),
        member.get("tenant_user_id"),
    )


def _teams_member_email(member: dict[str, Any]) -> str:
    return _first_text(
        member.get("email"),
        member.get("mail"),
        member.get("userPrincipalName"),
    ).casefold()


def _teams_transcript_identity(
    *,
    chat_id: str,
    transcript: dict[str, Any],
    content: str,
    title: str,
) -> str:
    native_id = _first_text(
        transcript.get("id"),
        transcript.get("transcript_id"),
        transcript.get("transcriptId"),
    )
    if native_id:
        return hashlib.sha256(f"native:{native_id}".encode("utf-8")).hexdigest()[:24]
    created_at = _first_text(transcript.get("created_at"), transcript.get("createdDateTime"))
    structured_messages = transcript.get("messages")
    transcript_payload = (
        json.dumps(
            structured_messages,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        if isinstance(structured_messages, list)
        else content
    )
    payload_hash = hashlib.sha256(transcript_payload.encode("utf-8")).hexdigest()
    seed = f"{chat_id}|{created_at}|{title}|{payload_hash}"
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()[:24]


def _first_text(*values: Any) -> str:
    for value in values:
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def _valid_iso_value(value: Any) -> str:
    candidate = str(value or "").strip()
    if not candidate:
        return ""
    try:
        _parse_iso_datetime(candidate)
    except (TypeError, ValueError):
        return ""
    return candidate


def _looks_automated_sender(name: str, address: str) -> bool:
    combined = f"{name} {address}".casefold()
    return any(
        marker in combined
        for marker in (
            "do-not-reply",
            "donotreply",
            "helpdesk",
            "mailer-daemon",
            "microsoft power automate",
            "no-reply",
            "noreply",
            "notification",
            "notifications",
            "postmaster",
            "service account",
            "teams meeting",
        )
    )


def _excluded_content_reason(body: str) -> str | None:
    if any(pattern.search(body) for pattern in SECRET_PATTERNS):
        return "credentials_and_secrets"
    if any(pattern.search(body) for pattern in CONTROLLED_MARKER_PATTERNS):
        return "cui_and_export_controlled"
    return None


def _validate_freshservice_identity_map(
    identity_map: dict[str, Any] | None,
) -> tuple[dict[str, str], dict[str, dict[str, str]]]:
    if identity_map is None:
        return {}, {}
    errors: list[dict[str, str]] = []
    if set(identity_map) - {"artifactType", "schemaVersion", "people"}:
        _error(errors, "invalid_identity_map_field", "$", "Identity map contains unsupported fields.")
    if identity_map.get("artifactType") != "freshservice_identity_map":
        _error(errors, "invalid_identity_map_type", "artifactType", "Expected freshservice_identity_map.")
    if identity_map.get("schemaVersion") != 1:
        _error(errors, "invalid_identity_map_version", "schemaVersion", "Expected schemaVersion 1.")
    people = identity_map.get("people")
    if not isinstance(people, list):
        _error(errors, "invalid_identity_map_people", "people", "Identity map people must be a list.")
        people = []
    email_map: dict[str, str] = {}
    user_id_map: dict[str, dict[str, str]] = {}
    for index, person in enumerate(people):
        path = f"people[{index}]"
        if not isinstance(person, dict):
            _error(errors, "invalid_identity_map_person", path, "Identity map person must be an object.")
            continue
        if set(person) - {"displayName", "emails", "freshserviceUserIds"}:
            _error(errors, "invalid_identity_map_person_field", path, "Identity map person has unsupported fields.")
        display_name = str(person.get("displayName") or "").strip()
        if len(display_name) < 2 or len(display_name) > 120:
            _error(errors, "invalid_identity_map_name", f"{path}.displayName", "Actual display name is required.")
            continue
        emails = person.get("emails") or []
        user_ids = person.get("freshserviceUserIds") or []
        if not isinstance(emails, list) or not isinstance(user_ids, list) or not (emails or user_ids):
            _error(
                errors,
                "identity_map_key_missing",
                path,
                "At least one internal email or Freshservice user id is required.",
            )
            continue
        canonical_fingerprint = ""
        for raw_email in emails:
            email = str(raw_email or "").strip().casefold()
            if not _is_internal_email(email):
                _error(
                    errors,
                    "identity_map_non_internal_email",
                    f"{path}.emails",
                    "Identity-map emails must use the configured internal email domain.",
                )
                continue
            existing_name = email_map.get(email)
            if existing_name and existing_name != display_name:
                _error(
                    errors,
                    "identity_map_email_collision",
                    f"{path}.emails",
                    "One email cannot map to multiple people.",
                )
                continue
            email_map[email] = display_name
            canonical_fingerprint = canonical_fingerprint or _sha256(email)
        for raw_user_id in user_ids:
            user_id = str(raw_user_id or "").strip()
            if not user_id:
                _error(
                    errors,
                    "identity_map_user_id_missing",
                    f"{path}.freshserviceUserIds",
                    "Freshservice user ids must be non-empty.",
                )
                continue
            fingerprint = canonical_fingerprint or _sha256(f"freshservice-user:{user_id}")
            existing_person = user_id_map.get(user_id)
            if existing_person and existing_person["displayName"] != display_name:
                _error(
                    errors,
                    "identity_map_user_id_collision",
                    f"{path}.freshserviceUserIds",
                    "One Freshservice user id cannot map to multiple people.",
                )
                continue
            user_id_map[user_id] = {
                "displayName": display_name,
                "identityFingerprint": fingerprint,
            }
    if errors:
        raise InteractionProfileBlockedError(errors)
    return email_map, user_id_map


def _normalized_subject(subject: str) -> str:
    normalized = re.sub(r"(?i)^\s*(?:(?:re|fw|fwd)\s*:\s*)+", "", subject).strip()
    return re.sub(r"\s+", " ", normalized).casefold()


def _classify_context(subject: str, body: str) -> str:
    text = f"{subject}\n{_current_authored_content_text(body)}".casefold()
    rules = (
        ("incident_response", ("incident", "outage", "service down", "sev1", "sev 1", "unavailable")),
        ("support_request", ("ticket", "helpdesk", "support request", "troubleshoot", "unable to")),
        ("meeting_follow_up", ("meeting notes", "meeting recap", "recap", "follow-up", "follow up")),
        ("decision_request", ("decision", "approve", "approval", "recommend", "which option", "choose")),
        ("executive_update", ("executive", "leadership", "board", "cio", "ceo")),
        ("project_planning", ("project plan", "roadmap", "milestone", "timeline", "workstream")),
        ("status_update", ("status", "update", "progress", "fyi", "for awareness")),
        (
            "technical_discussion",
            ("architecture", "azure", "configure", "deployment", "implementation", "network", "security"),
        ),
    )
    for context, terms in rules:
        if any(term in text for term in terms):
            return context
    return "informal_coordination"


def _sha256(value: str) -> str:
    return f"sha256:{hashlib.sha256(value.encode('utf-8')).hexdigest()}"


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def _message_sort_key(message: dict[str, Any]) -> tuple[str, int, str]:
    sequence = message.get("sequenceIndex", 0)
    if not isinstance(sequence, int) or isinstance(sequence, bool):
        sequence = 0
    return (str(message.get("sentAt") or ""), sequence, str(message.get("sourceRecordId") or ""))


def _message_for_analysis(message: dict[str, Any]) -> dict[str, Any]:
    prepared = deepcopy(message)
    prepared["body"] = _current_authored_content(message)
    return prepared


def _current_authored_content(message: dict[str, Any]) -> str:
    body = str(message.get("body") or "")
    source_system = message.get("sourceSystem")
    if source_system == "microsoft_outlook":
        quote_match = OUTLOOK_QUOTE_HTML_PATTERN.search(body)
        if quote_match:
            body = body[: quote_match.start()]
    elif source_system == "resolved_support_ticket":
        quote_match = TICKET_QUOTE_HTML_PATTERN.search(body)
        if quote_match:
            body = body[: quote_match.start()]
    text = _current_authored_content_text(body)
    if source_system in {"microsoft_outlook", "resolved_support_ticket"}:
        quote_match = ORIGINAL_MESSAGE_PATTERN.search(text)
        if quote_match:
            text = text[: quote_match.start()]
        if source_system == "resolved_support_ticket":
            quote_match = TICKET_QUOTE_TEXT_PATTERN.search(text)
            if quote_match:
                text = text[: quote_match.start()]
        text = _trim_email_signature(text)
    return text.strip()


def _current_authored_content_text(value: str) -> str:
    text = re.sub(r"(?i)<br\s*/?>|</p\s*>|</div\s*>|</li\s*>|</tr\s*>", "\n", value)
    text = re.sub(r"(?i)<li\b[^>]*>", "- ", text)
    text = HTML_TAG_PATTERN.sub(" ", text)
    text = html.unescape(text).replace("\u00a0", " ")
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line).strip()


def _trim_email_signature(text: str) -> str:
    lines = text.splitlines()
    closing = re.compile(r"(?i)^(?:best|best regards|kind regards|regards|respectfully|sincerely|thanks|thank you)[,!]?$")
    for index, line in enumerate(lines):
        if not closing.fullmatch(line.strip()):
            continue
        tail_lines = [item.strip() for item in lines[index + 1 :] if item.strip()]
        tail = "\n".join(tail_lines)
        compact_signature = (
            1 <= len(tail_lines) <= 6
            and all(len(item) <= 100 for item in tail_lines)
            and index >= max(0, len(lines) - 8)
        )
        if EMAIL_PATTERN.search(tail) or PHONE_PATTERN.search(tail) or compact_signature:
            return "\n".join(lines[: index + 1]).strip()
    return text


def _sanitize_example_text(text: str) -> str:
    cleaned = EMAIL_PATTERN.sub("[email]", text)
    cleaned = PHONE_PATTERN.sub("[phone]", cleaned)
    cleaned = SSN_PATTERN.sub("[identifier]", cleaned)
    return cleaned.strip()[:600]


def ingest_corpus_batch(vault_path: str | Path, batch: dict[str, Any]) -> dict[str, Any]:
    """Store or update complete messages in the encrypted communication vault."""

    errors = validate_corpus_batch(batch)
    if errors:
        raise InteractionProfileBlockedError(errors)
    path = Path(vault_path)
    vault = _load_vault(path, missing_ok=True)
    inserted = 0
    updated = 0
    unchanged = 0
    previous_event_keys = set(vault["batches"].get(batch["batchId"], []))
    event_keys: list[str] = []
    for message in batch["messages"]:
        event_key = _event_key(message)
        event_keys.append(event_key)
        stored = deepcopy(message)
        stored["eventKey"] = event_key
        stored["sourceVersionHash"] = _message_version_hash(message)
        existing = vault["messages"].get(event_key)
        if existing is None:
            inserted += 1
        elif existing["sourceVersionHash"] != stored["sourceVersionHash"]:
            updated += 1
        else:
            unchanged += 1
        vault["messages"][event_key] = stored
    new_event_keys = set(event_keys)
    vault["batches"][batch["batchId"]] = sorted(new_event_keys)
    vault["batchMetadata"][batch["batchId"]] = {
        "collection": deepcopy(batch["collection"]),
        "authorization": deepcopy(batch["authorization"]),
        "ingestedAt": _now(),
    }
    referenced_elsewhere = {
        key
        for other_batch_id, keys in vault["batches"].items()
        if other_batch_id != batch["batchId"]
        for key in keys
    }
    removed = 0
    for stale_key in previous_event_keys - new_event_keys:
        if stale_key not in referenced_elsewhere and stale_key in vault["messages"]:
            del vault["messages"][stale_key]
            removed += 1
    vault["updatedAt"] = _now()
    _save_vault(path, vault)
    status = "unchanged" if inserted == 0 and updated == 0 and removed == 0 else "stored"
    return {
        "artifactType": "communication_corpus_ingest_result",
        "status": status,
        "batchId": batch["batchId"],
        "insertedMessageCount": inserted,
        "updatedMessageCount": updated,
        "unchangedMessageCount": unchanged,
        "removedMessageCount": removed,
        "excludedMessageCount": int(batch["collection"].get("excludedMessageCount", 0)),
        "totalVaultMessageCount": len(vault["messages"]),
        "vaultEncryption": CURRENT_ENCRYPTION,
        "fullMessageContentRetained": True,
        "normalMindfrontHistoryUpdated": False,
    }


def list_corpus_people(vault_path: str | Path) -> dict[str, Any]:
    """List author coverage without returning message content."""

    vault = _load_vault(Path(vault_path), missing_ok=True)
    people: dict[str, dict[str, Any]] = {}
    for message in vault["messages"].values():
        author = message["author"]
        key = author["identityFingerprint"]
        row = people.setdefault(
            key,
            {
                "displayName": author["displayName"],
                "identityFingerprint": author["identityFingerprint"],
                "_nameCounts": Counter(),
                "messageCount": 0,
                "sourceSystems": set(),
                "firstObservedAt": message["sentAt"],
                "lastObservedAt": message["sentAt"],
            },
        )
        row["_nameCounts"][author["displayName"]] += 1
        row["messageCount"] += 1
        row["sourceSystems"].add(message["sourceSystem"])
        row["firstObservedAt"] = min(row["firstObservedAt"], message["sentAt"])
        row["lastObservedAt"] = max(row["lastObservedAt"], message["sentAt"])
    output = []
    for row in people.values():
        name_counts = row.pop("_nameCounts")
        row["displayName"] = sorted(
            name_counts,
            key=lambda name: (name_counts[name], len(name), name.casefold()),
            reverse=True,
        )[0]
        row["aliases"] = sorted(
            (name for name in name_counts if name != row["displayName"]),
            key=str.casefold,
        )
        row["sourceSystems"] = sorted(row["sourceSystems"])
        output.append(row)
    return {
        "artifactType": "communication_corpus_people_index",
        "personCount": len(output),
        "people": sorted(output, key=lambda item: item["displayName"].casefold()),
        "vaultEncryption": CURRENT_ENCRYPTION,
        "fullMessageContentIncluded": False,
    }


def get_corpus_context(
    vault_path: str | Path,
    display_name: str,
    *,
    context: str | None = None,
    limit: int = 30,
    include_thread_context: bool = False,
    thread_limit: int = 5,
) -> dict[str, Any]:
    """Return complete authored messages and optional surrounding threads for private Codex use."""

    if context is not None and context not in ALLOWED_CONTEXTS:
        raise InteractionProfileBlockedError(
            [{"code": "unknown_context", "path": context, "message": "Unknown interaction context."}]
        )
    vault = _load_vault(Path(vault_path))
    messages = _messages_for_name(vault, display_name)
    if context:
        exact = [message for message in messages if message["context"] == context]
        fallback = [message for message in messages if message["context"] != context]
        messages = exact + fallback
    messages = sorted(
        messages,
        key=lambda item: (
            item.get("ticketOutcome") == "resolved_ticket",
            item["sentAt"],
            item.get("sequenceIndex", 0),
        ),
        reverse=True,
    )[: max(1, min(limit, 100))]
    threads: list[dict[str, Any]] = []
    returned_message_count = len(messages)
    if include_thread_context:
        focus_identity = messages[0]["author"]["identityFingerprint"]
        selected_conversations: list[str] = []
        for message in messages:
            conversation = message["conversationFingerprint"]
            if conversation not in selected_conversations:
                selected_conversations.append(conversation)
            if len(selected_conversations) >= max(1, min(thread_limit, 20)):
                break

        all_messages = list(vault["messages"].values())
        canonical_names = _identity_name_index(vault)
        for conversation in selected_conversations:
            thread_messages = sorted(
                (
                    item
                    for item in all_messages
                    if item["conversationFingerprint"] == conversation
                ),
                key=_message_sort_key,
            )
            threads.append(
                {
                    "conversationFingerprint": conversation,
                    "coverage": "complete_within_ingested_vault",
                    "messageCount": len(thread_messages),
                    "focusAuthorMessageCount": sum(
                        item["author"]["identityFingerprint"] == focus_identity
                        for item in thread_messages
                    ),
                    "sourceSystems": sorted({item["sourceSystem"] for item in thread_messages}),
                    "contexts": sorted({item["context"] for item in thread_messages}),
                    "messages": [
                        {
                            "sourceSystem": item["sourceSystem"],
                            "containerType": item["containerType"],
                            "authorDisplayName": canonical_names.get(
                                item["author"]["identityFingerprint"],
                                item["author"]["displayName"],
                            ),
                            "focusAuthor": item["author"]["identityFingerprint"] == focus_identity,
                            "sentAt": item["sentAt"],
                            "sequenceIndex": item.get("sequenceIndex", 0),
                            "context": item["context"],
                            "subject": item.get("subject"),
                            "body": item["body"],
                            "ticketOutcome": item.get("ticketOutcome"),
                        }
                        for item in thread_messages
                    ],
                }
            )
        returned_message_count = sum(thread["messageCount"] for thread in threads)

    return {
        "artifactType": "private_communication_context",
        "displayName": display_name,
        "requestedContext": context,
        "messageCount": len(messages),
        "focusMessageCount": len(messages),
        "returnedMessageCount": returned_message_count,
        "threadCount": len(threads),
        "fullMessageBodiesIncluded": True,
        "fullThreadContextIncluded": include_thread_context,
        "threadCoverage": (
            "complete_within_ingested_vault"
            if include_thread_context
            else "not_requested"
        ),
        "messages": [
            {
                "sourceSystem": item["sourceSystem"],
                "containerType": item["containerType"],
                "sentAt": item["sentAt"],
                "context": item["context"],
                "subject": item.get("subject"),
                "body": item["body"],
                "ticketOutcome": item.get("ticketOutcome"),
            }
            for item in messages
        ],
        "threads": threads,
        "useBoundary": (
            "Private assistive context. Full wording and thread sequence may guide terminology, tone, "
            "and continuity, but must not be copied into a shareable report as evidence or presented "
            "as a prediction of exact future words. Thread completeness applies only to messages "
            "present in the encrypted vault; source-system coverage remains bounded."
        ),
        "marketEvidenceCreated": False,
    }


def derive_observation_bundle(vault_path: str | Path, display_name: str) -> dict[str, Any]:
    """Derive a feature bundle and high-signal examples from full messages."""

    vault = _load_vault(Path(vault_path))
    authored_raw = _messages_for_name(vault, display_name)
    fingerprints = {item["author"]["identityFingerprint"] for item in authored_raw}
    if len(fingerprints) != 1:
        raise InteractionProfileBlockedError(
            [
                {
                    "code": "ambiguous_identity",
                    "path": display_name,
                    "message": "Display name does not resolve to one confirmed identity.",
                }
            ]
        )
    authored = sorted(
        (_message_for_analysis(item) for item in authored_raw),
        key=_message_sort_key,
    )
    authored = [item for item in authored if item["body"].strip()]
    if not authored:
        raise InteractionProfileBlockedError(
            [
                {
                    "code": "no_authored_content_after_quote_removal",
                    "path": display_name,
                    "message": "No authored message content remained after quoted history and signatures were removed.",
                }
            ]
        )
    all_messages = sorted(
        (_message_for_analysis(item) for item in vault["messages"].values()),
        key=_message_sort_key,
    )
    all_messages = [item for item in all_messages if item["body"].strip()]
    observations = _derive_observations(authored)
    hypotheses = _derive_response_hypotheses(authored, all_messages)
    lexicon = _derive_lexicon(authored)
    examples = _derive_examples(authored)
    precise_authored = [
        item
        for item in authored
        if item.get("sentAtPrecision", "message_timestamp") == "message_timestamp"
    ]
    if precise_authored:
        window_start = precise_authored[0]["sentAt"]
        window_end = precise_authored[-1]["sentAt"]
    else:
        window_start = authored[0]["sentAt"]
        window_end = authored[0]["sentAt"]
    contexts = sorted({item["context"] for item in authored})
    conversations = {item["conversationFingerprint"] for item in authored}
    active_days = {
        _parse_iso_datetime(item["sentAt"]).date().isoformat()
        for item in precise_authored
    }
    source_systems = sorted({item["sourceSystem"] for item in authored})
    relevant_batches = [
        metadata
        for batch_id, metadata in vault["batchMetadata"].items()
        if set(vault["batches"].get(batch_id, [])) & {_event_key(item) for item in authored_raw}
    ]
    external_model_used = any(
        bool(item["collection"].get("externalModelProcessingUsed", False))
        for item in relevant_batches
    )
    private_one_to_one = any(
        bool(item["authorization"].get("privateOneToOneIncluded", False))
        for item in relevant_batches
    )
    digest_seed = "|".join(item["sourceVersionHash"] for item in authored_raw)
    bundle_id = f"comms-bundle-{hashlib.sha256(digest_seed.encode('utf-8')).hexdigest()[:20]}"
    return {
        "artifactType": "communication_observation_bundle",
        "schemaVersion": 1,
        "bundleId": bundle_id,
        "purpose": ALLOWED_PURPOSE,
        "subject": {
            "displayName": display_name.strip(),
            "identityResolution": authored[-1]["author"]["identityResolution"],
            "identityFingerprint": next(iter(fingerprints)),
        },
        "authorization": {
            "requesterHasLegitimateAccess": True,
            "subjectAuthoredOnly": True,
            "assistiveUseOnly": True,
            "humanReviewRequired": True,
            "noEmploymentDecisionUse": True,
            "companySystemContentAuthorized": True,
            "codexProcessingAuthorized": True,
            "privateOneToOneIncluded": private_one_to_one,
            "privateOneToOneUseApproved": private_one_to_one,
            "governanceBasis": "user_asserted_company_policy",
        },
        "collection": {
            "sourceSystems": source_systems,
            "coverageComplete": False,
            "windowStart": window_start,
            "windowEnd": window_end,
            "authoredMessageCount": len(authored),
            "conversationCount": len(conversations),
            "contextCount": len(contexts),
            "activeDayCount": len(active_days),
            "excludedSensitiveMessageCount": sum(
                sum(
                    int(count)
                    for reason, count in item["collection"].get("excludedReasonCounts", {}).items()
                    if reason in {"credentials_and_secrets", "cui_and_export_controlled"}
                )
                for item in relevant_batches
            ),
            "sensitiveCategoriesExcluded": [
                "credentials_and_secrets",
                "cui_and_export_controlled",
            ],
            "rawContentPersisted": False,
            "attachmentsProcessed": False,
            "externalModelProcessingUsed": external_model_used,
            "resolvedTicketCount": sum(
                1 for item in authored if item.get("ticketOutcome") == "resolved_ticket"
            ),
            "resolutionOutcomeKnown": all(
                item.get("ticketOutcome") is not None
                for item in authored
                if item["sourceSystem"] == "resolved_support_ticket"
            ),
        },
        "observations": observations,
        "responseHypotheses": hypotheses,
        "privateLexicon": lexicon,
        "privateExamples": examples,
    }


def invalidate_corpus_batch(vault_path: str | Path, batch_id: str) -> dict[str, Any]:
    """Remove one source batch and unreferenced messages from the encrypted vault."""

    path = Path(vault_path)
    vault = _load_vault(path)
    event_keys = vault["batches"].pop(batch_id, None)
    if event_keys is None:
        raise InteractionProfileBlockedError(
            [{"code": "unknown_corpus_batch", "path": batch_id, "message": "No matching corpus batch exists."}]
        )
    vault["batchMetadata"].pop(batch_id, None)
    referenced = {key for keys in vault["batches"].values() for key in keys}
    removed = 0
    for event_key in event_keys:
        if event_key not in referenced and event_key in vault["messages"]:
            del vault["messages"][event_key]
            removed += 1
    vault["updatedAt"] = _now()
    _save_vault(path, vault)
    return {
        "artifactType": "communication_corpus_invalidation_result",
        "status": "invalidated",
        "batchId": batch_id,
        "removedMessageCount": removed,
        "remainingMessageCount": len(vault["messages"]),
    }


def delete_corpus_person(vault_path: str | Path, display_name: str) -> dict[str, Any]:
    """Delete every complete message authored by one confirmed person."""

    path = Path(vault_path)
    vault = _load_vault(path)
    matches = _messages_for_name(vault, display_name)
    event_keys = {_event_key(item) for item in matches}
    for key in event_keys:
        vault["messages"].pop(key, None)
    empty_batches = []
    for batch_id, keys in vault["batches"].items():
        vault["batches"][batch_id] = [key for key in keys if key not in event_keys]
        if not vault["batches"][batch_id]:
            empty_batches.append(batch_id)
    for batch_id in empty_batches:
        vault["batches"].pop(batch_id, None)
        vault["batchMetadata"].pop(batch_id, None)
    vault["updatedAt"] = _now()
    _save_vault(path, vault)
    return {
        "artifactType": "communication_corpus_person_delete_result",
        "status": "deleted",
        "displayName": display_name,
        "removedMessageCount": len(event_keys),
    }


def _validate_message(message: Any, index: int, errors: list[dict[str, str]]) -> None:
    path = f"messages[{index}]"
    if not isinstance(message, dict):
        _error(errors, "invalid_message", path, "Message must be an object.")
        return
    _unknown_fields(
        message,
        {
            "sourceSystem",
            "sourceRecordId",
            "modifiedAt",
            "author",
            "sentAt",
            "sentAtPrecision",
            "context",
            "conversationFingerprint",
            "containerType",
            "subject",
            "body",
            "ticketOutcome",
            "sequenceIndex",
        },
        path,
        errors,
    )
    if message.get("sourceSystem") not in ALLOWED_SOURCE_SYSTEMS:
        _error(errors, "unknown_source", f"{path}.sourceSystem", "Unknown source system.")
    source_id = message.get("sourceRecordId")
    if not isinstance(source_id, str) or not source_id.strip() or len(source_id) > 800:
        _error(errors, "invalid_source_record_id", f"{path}.sourceRecordId", "Opaque source record id is required.")
    author = message.get("author")
    if not isinstance(author, dict):
        _error(errors, "missing_author", f"{path}.author", "Author identity is required.")
    else:
        _unknown_fields(
            author,
            {"displayName", "identityResolution", "identityFingerprint"},
            f"{path}.author",
            errors,
        )
        if not isinstance(author.get("displayName"), str) or not author["displayName"].strip():
            _error(errors, "invalid_author_name", f"{path}.author.displayName", "Author display name is required.")
        if author.get("identityResolution") not in {
            "confirmed_directory_identity",
            "confirmed_ticket_identity",
        }:
            _error(errors, "identity_not_confirmed", f"{path}.author.identityResolution", "Identity must be confirmed.")
        if not isinstance(author.get("identityFingerprint"), str) or not re.fullmatch(
            r"sha256:[0-9a-f]{64}",
            author.get("identityFingerprint", ""),
        ):
            _error(
                errors,
                "invalid_identity_fingerprint",
                f"{path}.author.identityFingerprint",
                "A SHA-256 identity fingerprint is required.",
            )
    _validate_datetime(message.get("sentAt"), f"{path}.sentAt", errors)
    _validate_datetime(message.get("modifiedAt"), f"{path}.modifiedAt", errors)
    sent_at_precision = message.get("sentAtPrecision", "message_timestamp")
    if sent_at_precision not in ALLOWED_SENT_AT_PRECISIONS:
        _error(
            errors,
            "invalid_sent_at_precision",
            f"{path}.sentAtPrecision",
            "sentAtPrecision must distinguish a message timestamp from a snapshot timestamp.",
        )
    sequence_index = message.get("sequenceIndex", 0)
    if not isinstance(sequence_index, int) or isinstance(sequence_index, bool) or sequence_index < 0:
        _error(
            errors,
            "invalid_sequence_index",
            f"{path}.sequenceIndex",
            "sequenceIndex must be a nonnegative integer when supplied.",
        )
    if message.get("context") not in ALLOWED_CONTEXTS:
        _error(errors, "unknown_context", f"{path}.context", "Unknown message context.")
    if not isinstance(message.get("conversationFingerprint"), str) or not re.fullmatch(
        r"sha256:[0-9a-f]{64}",
        message.get("conversationFingerprint", ""),
    ):
        _error(
            errors,
            "invalid_conversation_fingerprint",
            f"{path}.conversationFingerprint",
            "A SHA-256 conversation fingerprint is required.",
        )
    if message.get("containerType") not in ALLOWED_CONTAINER_TYPES:
        _error(errors, "invalid_container_type", f"{path}.containerType", "Unknown container type.")
    if message.get("subject") is not None and not isinstance(message.get("subject"), str):
        _error(errors, "invalid_subject", f"{path}.subject", "Subject must be text or null.")
    body = message.get("body")
    if not isinstance(body, str) or not body.strip():
        _error(errors, "invalid_body", f"{path}.body", "Complete message body is required.")
    elif len(body) > 200_000:
        _error(errors, "message_too_large", f"{path}.body", "One message body exceeds 200,000 characters.")
    else:
        for pattern in SECRET_PATTERNS:
            if pattern.search(body):
                _error(
                    errors,
                    "credential_or_secret_detected",
                    f"{path}.body",
                    "A credential or secret pattern must be removed before ingestion.",
                )
                break
    ticket_outcome = message.get("ticketOutcome")
    if ticket_outcome is not None and ticket_outcome not in ALLOWED_TICKET_OUTCOMES:
        _error(errors, "invalid_ticket_outcome", f"{path}.ticketOutcome", "Unknown ticket outcome.")
    if message.get("sourceSystem") == "resolved_support_ticket" and ticket_outcome is None:
        _error(
            errors,
            "missing_ticket_outcome",
            f"{path}.ticketOutcome",
            "Resolved-ticket messages require an outcome.",
        )


def _derive_observations(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    by_context: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for message in messages:
        by_context[message["context"]].append(message)
    for context in sorted(by_context):
        rows.extend(_derive_context_observations(by_context[context]))
    return [row for row in rows if row["supportCount"] >= 3]


def _derive_context_observations(
    messages: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if not messages:
        return []
    rows: list[dict[str, Any]] = []
    word_counts = [len(_words(item["body"])) for item in messages]
    typical = median(word_counts)
    if typical <= 80:
        density = "concise_first"
    elif typical <= 220:
        density = "layered_detail"
    else:
        density = "detailed_by_default"
    rows.append(_observation(messages, "information_density", density, lambda item: _density(item) == density))

    structure_counts = Counter(
        classification
        for item in messages
        if (classification := _structure_class(item["body"])) is not None
    )
    if structure_counts:
        structure = structure_counts.most_common(1)[0][0]
        rows.append(
            _observation(
                messages,
                "structure_preference",
                structure,
                lambda item: (
                    None
                    if _structure_class(item["body"]) is None
                    else _structure_class(item["body"]) == structure
                ),
            )
        )

    opening_counts = Counter(_opening_class(item["body"]) for item in messages)
    opening = opening_counts.most_common(1)[0][0]
    rows.append(_observation(messages, "opening_preference", opening, lambda item: _opening_class(item["body"]) == opening))

    tone_counts = Counter(_tone_class(item["body"]) for item in messages)
    tone = tone_counts.most_common(1)[0][0]
    rows.append(_observation(messages, "tone_register", tone, lambda item: _tone_class(item["body"]) == tone))

    action_counts = Counter(
        classification
        for item in messages
        if (classification := _action_class(item["body"])) is not None
    )
    if action_counts:
        action = action_counts.most_common(1)[0][0]
        rows.append(
            _observation(
                messages,
                "action_clarity",
                action,
                lambda item: (
                    None
                    if _action_class(item["body"]) is None
                    else _action_class(item["body"]) == action
                ),
            )
        )

    for tendency, terms in {
        "ownership": ("owner", "own", "responsible", "who"),
        "next_step": ("next step", "what next", "then what"),
        "scope": ("scope", "include", "exclude", "boundary"),
        "risk": ("risk", "security", "control"),
        "evidence": ("evidence", "source", "data", "proof"),
        "implementation": ("implement", "build", "deploy", "configure"),
        "cost_or_effort": ("cost", "effort", "hours", "resource"),
        "timeline": ("when", "timeline", "date", "deadline"),
    }.items():
        matched = [
            item
            for item in messages
            if _question_contains_any(item["body"], terms)
        ]
        if len(matched) >= 3:
            rows.append(
                _observation(
                    messages,
                    "question_pattern",
                    tendency,
                    lambda item, terms=terms: _question_contains_any(
                        item["body"],
                        terms,
                    ),
                )
            )
    return rows


def _derive_response_hypotheses(
    authored: list[dict[str, Any]],
    all_messages: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    by_conversation: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in all_messages:
        by_conversation[item["conversationFingerprint"]].append(item)
    authored_keys = {_event_key(item) for item in authored}
    pairs: list[tuple[str, str, str]] = []
    for messages in by_conversation.values():
        ordered = sorted(messages, key=_message_sort_key)
        for index, item in enumerate(ordered):
            if _event_key(item) not in authored_keys or index == 0:
                continue
            previous = ordered[index - 1]
            if previous["author"]["identityFingerprint"] == item["author"]["identityFingerprint"]:
                continue
            response_class = _response_class(item["body"])
            if response_class is None:
                continue
            pairs.append((previous["context"], response_class, item["sourceSystem"]))
    counts = Counter((trigger, response) for trigger, response, _ in pairs)
    results = []
    for (trigger, response), support in counts.most_common():
        if support < 5:
            continue
        sources = sorted({source for pair_trigger, pair_response, source in pairs if (pair_trigger, pair_response) == (trigger, response)})
        competing = sum(
            count
            for (pair_trigger, pair_response), count in counts.items()
            if pair_trigger == trigger and pair_response != response
        )
        results.append(
            {
                "triggerClass": trigger,
                "responseClass": response,
                "supportCount": support,
                "contradictionCount": competing,
                "contexts": sorted({trigger, *[item["context"] for item in authored if item["context"] == trigger]}),
                "sourceSystems": sources,
            }
        )
    return results[:12]


def _derive_lexicon(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    phrase_messages: dict[str, set[int]] = defaultdict(set)
    phrase_sources: dict[str, set[str]] = defaultdict(set)
    phrase_contexts: dict[str, set[str]] = defaultdict(set)
    for index, message in enumerate(messages):
        words = [
            word.casefold()
            for word in WORD_PATTERN.findall(URL_PATTERN.sub(" ", message["body"]))
            if word.casefold() not in STOP_WORDS and not word.isdigit()
        ]
        phrases = set(words)
        phrases.update(" ".join(words[offset : offset + 2]) for offset in range(max(0, len(words) - 1)))
        for phrase in phrases:
            if len(phrase) < 3 or len(phrase) > 64:
                continue
            phrase_messages[phrase].add(index)
            phrase_sources[phrase].add(message["sourceSystem"])
            phrase_contexts[phrase].add(message["context"])
    ranked = sorted(
        (
            (phrase, len(indexes))
            for phrase, indexes in phrase_messages.items()
            if len(indexes) >= 3
        ),
        key=lambda item: (item[1], len(item[0].split()), len(item[0])),
        reverse=True,
    )
    return [
        {
            "term": phrase,
            "category": "preferred_term",
            "supportCount": count,
            "contexts": sorted(phrase_contexts[phrase]),
            "sourceSystems": sorted(phrase_sources[phrase]),
        }
        for phrase, count in ranked[:20]
    ]


def _derive_examples(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for message in messages:
        response_class = _response_class(message["body"])
        if response_class is None:
            continue
        grouped[(message["context"], response_class)].append(message)
    examples = []
    for (context, response), items in sorted(grouped.items(), key=lambda item: len(item[1]), reverse=True):
        if len(items) < 2:
            continue
        representative = sorted(items, key=lambda item: len(item["body"]))[len(items) // 2]
        kind = {
            "request_scope_clarification": "clarifying_question",
            "request_ownership": "clarifying_question",
            "request_next_step": "clarifying_question",
            "request_evidence": "clarifying_question",
            "approve": "decision_response",
            "approve_with_conditions": "decision_response",
            "challenge_assumption": "correction",
        }.get(response, "typical_response")
        if representative.get("ticketOutcome") == "resolved_ticket":
            kind = "resolution_close"
        example_text = _sanitize_example_text(representative["body"])
        if not example_text:
            continue
        examples.append(
            {
                "exampleText": example_text,
                "exampleKind": kind,
                "outcomeClass": representative.get("ticketOutcome") or "unknown",
                "similarExample Organizationunt": len(items),
                "contexts": [context],
                "sourceSystems": sorted({item["sourceSystem"] for item in items}),
                "observedAt": representative["sentAt"],
            }
        )
    return examples[:12]


def _observation(
    messages: list[dict[str, Any]],
    dimension: str,
    tendency: str,
    predicate: Any,
) -> dict[str, Any]:
    classified = [(item, predicate(item)) for item in messages]
    matched = [item for item, result in classified if result is True]
    unmatched = [item for item, result in classified if result is False]
    observed = matched or unmatched or messages
    return {
        "dimension": dimension,
        "tendencyCode": tendency,
        "basis": "behavioral_pattern",
        "subjectConfirmed": False,
        "supportCount": len(matched),
        "contradictionCount": len(unmatched),
        "contexts": sorted({item["context"] for item in observed}),
        "sourceSystems": sorted({item["sourceSystem"] for item in observed}),
        "firstObservedAt": min(item["sentAt"] for item in observed),
        "lastObservedAt": max(item["sentAt"] for item in observed),
    }


def _density(message: dict[str, Any]) -> str:
    count = len(_words(message["body"]))
    if count <= 80:
        return "concise_first"
    if count <= 220:
        return "layered_detail"
    return "detailed_by_default"


def _structure_class(text: str) -> str | None:
    if _has_bullets(text):
        return "bullets"
    if len(_words(text)) <= 120:
        return "short_prose"
    return None


def _opening_class(text: str) -> str:
    opening = " ".join(_words(text)[:25]).casefold()
    if _contains_any(opening, ("issue", "problem", "risk", "blocked", "gap")):
        return "problem_first"
    if _contains_any(opening, ("recommend", "decision", "result", "status", "next step", "please", "need")):
        return "bottom_line_first"
    return "context_first"


def _tone_class(text: str) -> str:
    lower = text.casefold()
    informal = sum(lower.count(term) for term in ("can't", "don't", "won't", "i'm", "we're", "thanks", "hey"))
    informal += sum(lower.count(term) for term in ("damn", "hell", "shit", "fuck"))
    if informal:
        return "informal_direct"
    if re.search(r"\b(?:dear|sincerely|respectfully|kind regards)\b", lower):
        return "formal_for_decisions"
    return "neutral_professional"


def _action_class(text: str) -> str | None:
    lower = text.casefold()
    ownership = _contains_any(lower, ("owner", "responsible", "assigned to"))
    timing = _contains_any(
        lower,
        ("due", "deadline", "by friday", "by monday", "by tuesday", "by wednesday", "by thursday"),
    )
    if ownership and timing:
        return "owner_and_timing"
    if _contains_any(lower, ("recommend", "default", "option")):
        return "choice_with_default"
    if _contains_any(
        lower,
        ("next step", "please ", "please\n", "need to", "must ", "should ", "i will", "we will"),
    ):
        return "explicit_next_step"
    return None


def _response_class(text: str) -> str | None:
    lower = text.casefold()
    question_text = " ".join(_question_segments(text)).casefold()
    if question_text:
        if _contains_any(question_text, ("who", "owner", "responsible")):
            return "request_ownership"
        if _contains_any(question_text, ("next", "then", "what happens")):
            return "request_next_step"
        if _contains_any(question_text, ("source", "evidence", "data", "proof")):
            return "request_evidence"
        if _contains_any(question_text, ("scope", "include", "exclude", "boundary")):
            return "request_scope_clarification"
        if _contains_any(question_text, ("implement", "deploy", "configure", "how")):
            return "request_implementation_detail"
        if _contains_any(question_text, ("cost", "effort", "resource", "hours")):
            return "request_cost_or_effort"
        if _contains_any(question_text, ("risk", "security", "control")):
            return "request_risk_controls"
        if _contains_any(question_text, ("when", "timeline", "date", "deadline")):
            return "request_timeline"
        return None
    if _contains_any(lower, ("approved", "go ahead", "looks good", "yes")):
        if _contains_any(lower, ("if", "provided", "assuming", "once")):
            return "approve_with_conditions"
        return "approve"
    if _contains_any(lower, ("not yet", "later", "defer", "hold")):
        return "defer"
    if _contains_any(lower, ("instead", "redirect", "talk to", "send to")):
        return "redirect"
    if _contains_any(lower, ("but", "however", "assumption", "disagree")):
        return "challenge_assumption"
    return "acknowledge"


def _has_bullets(text: str) -> bool:
    return bool(re.search(r"(?m)^\s*(?:[-*]|\d+[.)])\s+\S", text))


def _words(text: str) -> list[str]:
    return WORD_PATTERN.findall(text)


def _contains_any(text: str, terms: tuple[str, ...]) -> bool:
    lower = text.casefold()
    return any(term in lower for term in terms)


def _question_segments(text: str) -> list[str]:
    segments: list[str] = []
    boundary = 0
    for match in re.finditer(r"[?]", text):
        start = boundary
        for separator in (".", "!", ";", "\n"):
            candidate = text.rfind(separator, boundary, match.start())
            if candidate >= start:
                start = candidate + 1
        segment = text[start : match.end()].strip()
        if segment:
            segments.append(segment[-500:])
        boundary = match.end()
    return segments


def _question_contains_any(text: str, terms: tuple[str, ...]) -> bool:
    return any(_contains_any(segment, terms) for segment in _question_segments(text))


def _messages_for_name(vault: dict[str, Any], display_name: str) -> list[dict[str, Any]]:
    key = _normalize_name(display_name)
    direct_matches = [
        message
        for message in vault["messages"].values()
        if _normalize_name(message["author"]["displayName"]) == key
    ]
    if not direct_matches:
        raise InteractionProfileBlockedError(
            [{"code": "corpus_person_not_found", "path": display_name, "message": "No authored messages match."}]
        )
    identities = {item["author"]["identityFingerprint"] for item in direct_matches}
    if len(identities) != 1:
        raise InteractionProfileBlockedError(
            [{"code": "ambiguous_corpus_name", "path": display_name, "message": "Name maps to multiple identities."}]
        )
    identity = next(iter(identities))
    return [
        message
        for message in vault["messages"].values()
        if message["author"]["identityFingerprint"] == identity
    ]


def _identity_name_index(vault: dict[str, Any]) -> dict[str, str]:
    counts: dict[str, Counter[str]] = defaultdict(Counter)
    for message in vault["messages"].values():
        author = message["author"]
        counts[author["identityFingerprint"]][author["displayName"]] += 1
    return {
        fingerprint: sorted(
            name_counts,
            key=lambda name: (name_counts[name], len(name), name.casefold()),
            reverse=True,
        )[0]
        for fingerprint, name_counts in counts.items()
    }


def _event_key(message: dict[str, Any]) -> str:
    seed = f"{message['sourceSystem']}|{message['sourceRecordId']}"
    return f"sha256:{hashlib.sha256(seed.encode('utf-8')).hexdigest()}"


def _message_version_hash(message: dict[str, Any]) -> str:
    seed = json.dumps(
        {
            "modifiedAt": message["modifiedAt"],
            "sentAt": message["sentAt"],
            "sentAtPrecision": message.get("sentAtPrecision", "message_timestamp"),
            "subject": message.get("subject"),
            "body": message["body"],
            "sequenceIndex": message.get("sequenceIndex", 0),
        },
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return f"sha256:{hashlib.sha256(seed.encode('utf-8')).hexdigest()}"


def _new_vault() -> dict[str, Any]:
    now = _now()
    return {
        "artifactType": "mindfront_private_communication_vault",
        "schemaVersion": 1,
        "createdAt": now,
        "updatedAt": now,
        "messages": {},
        "batches": {},
        "batchMetadata": {},
        "dataBoundary": (
            "Complete company-system communications retained under installation-local encryption for private "
            "assistive drafting. Excluded from Git, normal Mindfront history, dashboards, and shareable reports."
        ),
    }


def _load_vault(path: Path, *, missing_ok: bool = False) -> dict[str, Any]:
    if not path.exists():
        if missing_ok:
            return _new_vault()
        raise InteractionProfileBlockedError(
            [{"code": "communication_vault_missing", "path": str(path), "message": "Vault does not exist."}]
        )
    try:
        envelope = json.loads(path.read_text(encoding="utf-8"))
        payload = decrypt_envelope(
            envelope,
            expected_artifact_type="mindfront_encrypted_communication_vault",
        )
        vault = json.loads(payload.decode("utf-8"))
        if vault.get("artifactType") != "mindfront_private_communication_vault":
            raise ValueError("unexpected decrypted vault type")
        return vault
    except InteractionProfileBlockedError:
        raise
    except VaultEncryptionError as exc:
        raise InteractionProfileBlockedError(
            [
                {
                    "code": "communication_vault_unreadable",
                    "path": str(path),
                    "message": reason["message"],
                }
                for reason in exc.reasons
            ]
        ) from exc
    except Exception as exc:
        raise InteractionProfileBlockedError(
            [{"code": "communication_vault_unreadable", "path": str(path), "message": str(exc)}]
        ) from exc


def _save_vault(path: Path, vault: dict[str, Any]) -> None:
    payload = json.dumps(vault, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
    try:
        write_encrypted_payload(
            path,
            payload,
            artifact_type="mindfront_encrypted_communication_vault",
        )
    except VaultEncryptionError as exc:
        raise InteractionProfileBlockedError(
            [
                {
                    "code": "communication_vault_encryption_failed",
                    "path": str(path),
                    "message": reason["message"],
                }
                for reason in exc.reasons
            ]
        ) from exc


def _validate_datetime(value: Any, path: str, errors: list[dict[str, str]]) -> None:
    if not isinstance(value, str):
        _error(errors, "invalid_datetime", path, "ISO 8601 datetime with timezone is required.")
        return
    try:
        _parse_iso_datetime(value)
    except ValueError:
        _error(errors, "invalid_datetime", path, "ISO 8601 datetime with timezone is required.")


def _unknown_fields(
    value: dict[str, Any],
    allowed: set[str],
    path: str,
    errors: list[dict[str, str]],
) -> None:
    unknown = sorted(set(value) - allowed)
    if unknown:
        _error(errors, "unknown_corpus_field", path, f"Unsupported fields: {', '.join(unknown)}.")


def _error(errors: list[dict[str, str]], code: str, path: str, message: str) -> None:
    errors.append({"code": code, "path": path, "message": message})

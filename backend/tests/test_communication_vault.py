from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from mindfront.communication_vault import (
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
from mindfront.interaction_profiles import (
    InteractionProfileBlockedError,
    build_interaction_profile,
)


def _sha(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


def _message(
    *,
    index: int,
    author: str,
    author_key: str,
    sent_at: datetime,
    conversation: int,
    body: str,
    source: str,
) -> dict:
    return {
        "sourceSystem": source,
        "sourceRecordId": f"{source}-message-{index}",
        "modifiedAt": sent_at.isoformat(),
        "author": {
            "displayName": author,
            "identityResolution": (
                "confirmed_ticket_identity"
                if source == "resolved_support_ticket"
                else "confirmed_directory_identity"
            ),
            "identityFingerprint": _sha(author_key),
        },
        "sentAt": sent_at.isoformat(),
        "context": "decision_request" if conversation % 2 == 0 else "status_update",
        "conversationFingerprint": _sha(f"conversation-{conversation}"),
        "containerType": {
            "microsoft_teams": "teams_chat",
            "microsoft_outlook": "outlook_email",
            "resolved_support_ticket": "support_ticket",
        }[source],
        "subject": f"Work item {conversation}",
        "body": body,
        "ticketOutcome": "resolved_ticket" if source == "resolved_support_ticket" else None,
    }


def _batch(message_count: int = 60) -> dict:
    start = datetime(2026, 4, 1, tzinfo=timezone.utc)
    messages = []
    source_cycle = ("microsoft_teams", "microsoft_outlook", "resolved_support_ticket")
    index = 0
    for offset in range(message_count):
        source = source_cycle[offset % len(source_cycle)]
        sent = start + timedelta(days=offset)
        conversation = offset % 8
        messages.append(
            _message(
                index=index,
                author="Taylor Morgan",
                author_key="primary-user-directory-id",
                sent_at=sent - timedelta(minutes=5),
                conversation=conversation,
                body="Here is the current proposal. Can you confirm the next step and owner?",
                source=source,
            )
        )
        index += 1
        messages.append(
            _message(
                index=index,
                author="Jordan Lee",
                author_key="mike-directory-id",
                sent_at=sent,
                conversation=conversation,
                body=(
                    "Bottom line: who owns the next step? Keep the status short, then include the "
                    "implementation detail and source. Thanks."
                ),
                source=source,
            )
        )
        index += 1
    return {
        "artifactType": "communication_corpus_batch",
        "schemaVersion": 1,
        "batchId": "corpus-batch-fixture-001",
        "purpose": "autistic_communication_assistance",
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
            "sourceSystems": list(source_cycle),
            "windowStart": start.isoformat(),
            "windowEnd": (start + timedelta(days=message_count)).isoformat(),
            "coverageComplete": False,
            "attachmentsProcessed": False,
            "restrictedMaterialPresent": False,
            "credentialSecretScanPassed": True,
            "rawContentRetainedEncrypted": True,
            "externalModelProcessingUsed": True,
        },
        "messages": messages,
    }


def test_corpus_batch_rejects_secret_pattern() -> None:
    batch = _batch(2)
    batch["messages"][0]["body"] = "client_secret = do-not-store-this"

    errors = validate_corpus_batch(batch)

    assert any(error["code"] == "credential_or_secret_detected" for error in errors)


def test_corpus_batch_requires_explicit_company_and_codex_authorization() -> None:
    batch = _batch(2)
    batch["authorization"]["companySystemContentAuthorized"] = False
    batch["authorization"]["codexProcessingAuthorized"] = False

    errors = validate_corpus_batch(batch)

    assert sum(error["code"] == "authorization_gate_failed" for error in errors) >= 2


def test_outlook_adapter_keeps_complete_message_and_filters_non_people() -> None:
    export = {
        "results": [
            {
                "id": "message-1",
                "subject": "Re: Pilot status",
                "sentDateTime": "2026-07-20T15:00:00+00:00",
                "sender": {
                    "emailAddress": {
                        "name": "Jordan Lee",
                        "address": "jordan.lee@corp.example",
                    }
                },
                "toRecipients": [
                    {"emailAddress": {"name": "Taylor Morgan", "address": "taylor.morgan@corp.example"}}
                ],
                "body": {
                    "content": (
                        "Bottom line: keep the update short.<br><br>"
                        "<div id=\"divRplyFwdMsg\">From: Taylor Morgan<br>Sent: Sunday<br>"
                        "This quoted history is intentionally long.</div>"
                    )
                },
            },
            {
                "id": "message-2",
                "subject": "System notification",
                "sentDateTime": "2026-07-20T16:00:00+00:00",
                "sender": {
                    "emailAddress": {
                        "name": "Helpdesk Notifications",
                        "address": "helpdesk@corp.example",
                    }
                },
                "body": {"content": "Automated ticket wrapper."},
            },
            {
                "id": "message-3",
                "subject": "External",
                "sentDateTime": "2026-07-20T17:00:00+00:00",
                "sender": {
                    "emailAddress": {
                        "name": "External Person",
                        "address": "person@example.com",
                    }
                },
                "body": {"content": "External content."},
            },
        ]
    }

    batch = corpus_batch_from_outlook_export(export, batch_id="corpus-batch-outlook-test-001")

    assert validate_corpus_batch(batch) == []
    assert len(batch["messages"]) == 1
    assert batch["messages"][0]["author"]["displayName"] == "Jordan Lee"
    assert "quoted history" in batch["messages"][0]["body"]
    assert batch["messages"][0]["author"]["identityFingerprint"].startswith("sha256:")


def test_outlook_adapter_skips_secret_and_controlled_messages_individually() -> None:
    def item(message_id: str, body: str) -> dict:
        return {
            "id": message_id,
            "subject": "Internal note",
            "sentDateTime": "2026-07-20T15:00:00+00:00",
            "sender": {
                "emailAddress": {
                    "name": "Jordan Lee",
                    "address": "jordan.lee@corp.example",
                }
            },
            "body": {"content": body},
        }

    batch = corpus_batch_from_outlook_export(
        {
            "results": [
                item("message-safe", "Normal internal coordination."),
                item("message-secret", "client_secret = do-not-store"),
                item("message-cui", "CONTROLLED UNCLASSIFIED INFORMATION"),
            ]
        },
        batch_id="corpus-batch-outlook-exclusions-001",
    )

    assert validate_corpus_batch(batch) == []
    assert [message["sourceRecordId"] for message in batch["messages"]] == ["message-safe"]
    assert batch["collection"]["excludedMessageCount"] == 2
    assert batch["collection"]["excludedReasonCounts"] == {
        "credentials_and_secrets": 1,
        "cui_and_export_controlled": 1,
    }


def test_outlook_adapter_keeps_ordinary_internal_cui_planning_discussion() -> None:
    export = {
        "results": [
            {
                "id": "message-cui-planning",
                "subject": "Quantum Compute direction",
                "sentDateTime": "2026-07-20T15:00:00+00:00",
                "sender": {
                    "emailAddress": {
                        "name": "Jordan Lee",
                        "address": "jordan.lee@corp.example",
                    }
                },
                "body": {
                    "content": (
                        "Move the Quantum Compute CUI work to the GCC High enclave "
                        "and Azure Government Foundry."
                    )
                },
            }
        ]
    }

    batch = corpus_batch_from_outlook_export(
        export,
        batch_id="corpus-batch-outlook-cui-planning-001",
    )

    assert validate_corpus_batch(batch) == []
    assert len(batch["messages"]) == 1
    assert batch["collection"]["excludedMessageCount"] == 0


def test_teams_adapter_preserves_order_and_directory_identity() -> None:
    export = {
        "threads": [
            {
                "thread": {
                    "chat_id": "19:fixture@thread.v2",
                    "container_title": "Jordan Lee, Taylor Morgan",
                    "latest_message_at": "2026-07-20T18:00:00+00:00",
                },
                "members": {
                    "members": [
                        {"display_name": "Jordan Lee", "email": "jordan.lee@corp.example"},
                        {"display_name": "Taylor Morgan", "email": "taylor.morgan@corp.example"},
                    ]
                },
                "transcript": {
                    "chat_id": "19:fixture@thread.v2",
                    "created_at": "2026-07-20T18:00:00+00:00",
                    "content": (
                        "[Taylor Morgan]: Here is the pilot status.\n\n"
                        "Jordan Lee said:What is the next step?\n\n"
                        "[Taylor Morgan]: I will send the implementation path."
                    ),
                },
            }
        ]
    }

    batch = corpus_batch_from_teams_export(export, batch_id="corpus-batch-teams-test-001")

    assert validate_corpus_batch(batch) == []
    assert [item["sequenceIndex"] for item in batch["messages"]] == [0, 1, 2]
    assert [item["author"]["displayName"] for item in batch["messages"]] == [
        "Taylor Morgan",
        "Jordan Lee",
        "Taylor Morgan",
    ]
    assert batch["messages"][1]["body"] == "What is the next step?"


def test_freshservice_adapter_validates_manifests_and_resolves_exact_people(tmp_path: Path) -> None:
    cases = [
        {
            "ticket_id": "100",
            "subject": "Resolved access issue",
            "type": "Service Request",
            "status_code": "4",
            "messages": [
                {
                    "conversation_id": "1001",
                    "created_at": "2026-07-01T10:00:00+00:00",
                    "updated_at": "2026-07-01T10:05:00+00:00",
                    "user_id": "501",
                    "role": "Customer",
                    "incoming": True,
                    "private": False,
                    "from_email": "jordan.lee@corp.example",
                    "body": "The access path works now. Thank you.",
                },
                {
                    "conversation_id": "1002",
                    "created_at": "2026-07-01T10:10:00+00:00",
                    "updated_at": "",
                    "user_id": "502",
                    "role": "Agent",
                    "incoming": False,
                    "private": False,
                    "from_email": "",
                    "body": "Closing this as resolved.",
                },
                {
                    "conversation_id": "1003",
                    "created_at": "2026-07-01T10:20:00+00:00",
                    "updated_at": "",
                    "user_id": "",
                    "role": "Customer",
                    "incoming": True,
                    "private": False,
                    "from_email": "external@example.com",
                    "body": "External sender.",
                },
                {
                    "conversation_id": "1004",
                    "created_at": "2026-07-01T10:30:00+00:00",
                    "updated_at": "",
                    "user_id": "501",
                    "role": "Internal note",
                    "incoming": False,
                    "private": True,
                    "from_email": "jordan.lee@corp.example",
                    "body": "CONTROLLED UNCLASSIFIED INFORMATION",
                },
            ],
        },
        {
            "ticket_id": "101",
            "subject": "Still open",
            "type": "Incident",
            "status_code": "2",
            "messages": [
                {
                    "conversation_id": "1011",
                    "created_at": "2026-07-02T10:00:00+00:00",
                    "updated_at": "",
                    "user_id": "501",
                    "role": "Customer",
                    "incoming": True,
                    "private": False,
                    "from_email": "jordan.lee@corp.example",
                    "body": "This ticket is not terminal.",
                }
            ],
        },
    ]
    cases_path = tmp_path / "freshservice-agent-cases.jsonl"
    cases_path.write_text(
        "\n".join(json.dumps(case) for case in cases) + "\n",
        encoding="utf-8",
    )
    cleaning_path = tmp_path / "cleaning-manifest.json"
    cleaning_path.write_text(
        json.dumps(
            {
                "source_ticket_count": 2,
                "source_conversation_count": 5,
                "include_private_notes": True,
                "deduplicate_messages": False,
                "redaction_mode": {"secret_like_values": "always"},
            }
        ),
        encoding="utf-8",
    )
    export_path = tmp_path / "export-manifest.json"
    export_path.write_text(
        json.dumps({"ticket_count": 2, "conversation_count": 5, "read_only": True}),
        encoding="utf-8",
    )
    identity_map = {
        "artifactType": "freshservice_identity_map",
        "schemaVersion": 1,
        "people": [
            {
                "displayName": "Jordan Lee",
                "emails": ["jordan.lee@corp.example"],
                "freshserviceUserIds": ["501"],
            },
            {
                "displayName": "Taylor Morgan",
                "emails": ["taylor.morgan@corp.example"],
                "freshserviceUserIds": ["502"],
            },
        ],
    }

    batch = corpus_batch_from_freshservice_jsonl(
        cases_path,
        cleaning_manifest_path=cleaning_path,
        export_manifest_path=export_path,
        batch_id="corpus-batch-freshservice-test-001",
        identity_map=identity_map,
    )

    assert validate_corpus_batch(batch) == []
    assert [message["author"]["displayName"] for message in batch["messages"]] == [
        "Jordan Lee",
        "Taylor Morgan",
    ]
    assert all(message["ticketOutcome"] == "resolved_ticket" for message in batch["messages"])
    assert batch["collection"]["externalModelProcessingUsed"] is False
    assert batch["collection"]["sourceFormat"] == "freshservice-agent-cases-jsonl-v1"
    assert batch["collection"]["excludedReasonCounts"] == {
        "cui_and_export_controlled": 1,
        "non_internal_author": 1,
        "non_terminal_ticket": 1,
    }
    assert set(batch["collection"]["sourceArtifactHashes"]) == {
        "casesJsonl",
        "cleaningManifest",
        "exportManifest",
    }


def test_freshservice_adapter_rejects_non_preserving_source_pack(tmp_path: Path) -> None:
    cases_path = tmp_path / "freshservice-agent-cases.jsonl"
    cases_path.write_text("", encoding="utf-8")
    cleaning_path = tmp_path / "cleaning-manifest.json"
    cleaning_path.write_text(
        json.dumps(
            {
                "source_ticket_count": 0,
                "source_conversation_count": 0,
                "include_private_notes": False,
                "deduplicate_messages": True,
                "redaction_mode": {"secret_like_values": "optional"},
            }
        ),
        encoding="utf-8",
    )
    export_path = tmp_path / "export-manifest.json"
    export_path.write_text(
        json.dumps({"ticket_count": 0, "conversation_count": 0, "read_only": True}),
        encoding="utf-8",
    )

    with pytest.raises(InteractionProfileBlockedError) as error:
        corpus_batch_from_freshservice_jsonl(
            cases_path,
            cleaning_manifest_path=cleaning_path,
            export_manifest_path=export_path,
            batch_id="corpus-batch-freshservice-test-002",
        )

    codes = {item["code"] for item in error.value.reasons}
    assert "freshservice_private_notes_missing" in codes
    assert "freshservice_messages_deduplicated" in codes
    assert "freshservice_secret_redaction_unverified" in codes


@pytest.mark.skipif(os.name != "nt", reason="Current-user DPAPI is Windows-only.")
def test_outlook_derivation_excludes_quoted_history_but_vault_retains_it(tmp_path: Path) -> None:
    results = []
    for index in range(4):
        results.append(
            {
                "id": f"message-{index}",
                "subject": f"Re: Pilot status {index}",
                "sentDateTime": f"2026-07-{20 + index:02d}T15:00:00+00:00",
                "sender": {
                    "emailAddress": {
                        "name": "Jordan Lee",
                        "address": "jordan.lee@corp.example",
                    }
                },
                "body": {
                    "content": (
                        "Keep this short and show the next step.<br><br>"
                        "<div id=\"divRplyFwdMsg\">From: Taylor Morgan<br>Sent: Sunday<br>"
                        + ("quoted implementation detail " * 120)
                        + "</div>"
                    )
                },
            }
        )
    batch = corpus_batch_from_outlook_export(
        {"results": results},
        batch_id="corpus-batch-outlook-quotes-001",
    )
    vault_path = tmp_path / "communications.vault"

    ingest_corpus_batch(vault_path, batch)
    context = get_corpus_context(vault_path, "Jordan Lee")
    bundle = derive_observation_bundle(vault_path, "Jordan Lee")

    density = next(
        item
        for item in bundle["observations"]
        if item["dimension"] == "information_density"
    )
    assert density["tendencyCode"] == "concise_first"
    assert "quoted implementation detail" in context["messages"][0]["body"]
    assert all(
        "quoted implementation detail" not in item["exampleText"]
        for item in bundle["privateExamples"]
    )


@pytest.mark.skipif(os.name != "nt", reason="Current-user DPAPI is Windows-only.")
def test_full_message_vault_derives_active_profile_and_keeps_plaintext_encrypted(tmp_path: Path) -> None:
    vault_path = tmp_path / "communications.vault"
    batch = _batch()

    ingest = ingest_corpus_batch(vault_path, batch)
    people = list_corpus_people(vault_path)
    private_context = get_corpus_context(vault_path, "Jordan Lee", context="decision_request", limit=5)
    observation_bundle = derive_observation_bundle(vault_path, "Jordan Lee")
    profile = build_interaction_profile(observation_bundle)

    assert ingest["insertedMessageCount"] == 120
    assert people["personCount"] == 2
    assert private_context["messageCount"] == 5
    assert "who owns the next step" in private_context["messages"][0]["body"].lower()
    assert observation_bundle["collection"]["authoredMessageCount"] == 60
    assert "resolved_support_ticket" in observation_bundle["collection"]["sourceSystems"]
    assert profile["status"] == "active"
    assert profile["eligibleForAutomaticUse"] is True
    assert profile["assistiveGuidance"]["representativeExamples"]

    envelope_text = vault_path.read_text(encoding="utf-8")
    envelope = json.loads(envelope_text)
    assert envelope["encryption"] == "aes_256_gcm_local_key_v1"
    assert "Jordan Lee" not in envelope_text
    assert "who owns the next step" not in envelope_text.lower()


@pytest.mark.skipif(os.name != "nt", reason="Current-user DPAPI is Windows-only.")
def test_private_context_can_return_complete_ingested_threads(tmp_path: Path) -> None:
    vault_path = tmp_path / "communications.vault"
    batch = _batch(12)
    ingest_corpus_batch(vault_path, batch)

    private_context = get_corpus_context(
        vault_path,
        "Jordan Lee",
        context="decision_request",
        limit=5,
        include_thread_context=True,
        thread_limit=2,
    )

    assert private_context["focusMessageCount"] == 5
    assert private_context["threadCount"] == 2
    assert private_context["fullMessageBodiesIncluded"] is True
    assert private_context["fullThreadContextIncluded"] is True
    assert private_context["threadCoverage"] == "complete_within_ingested_vault"
    assert private_context["returnedMessageCount"] == sum(
        thread["messageCount"] for thread in private_context["threads"]
    )
    for thread in private_context["threads"]:
        assert thread["coverage"] == "complete_within_ingested_vault"
        assert {message["authorDisplayName"] for message in thread["messages"]} == {
            "Jordan Lee",
            "Taylor Morgan",
        }
        assert all(message["body"] for message in thread["messages"])
        assert any(message["focusAuthor"] for message in thread["messages"])
        assert any(not message["focusAuthor"] for message in thread["messages"])


@pytest.mark.skipif(os.name != "nt", reason="Current-user DPAPI is Windows-only.")
def test_vault_rerun_is_idempotent_and_edit_replaces_source_version(tmp_path: Path) -> None:
    vault_path = tmp_path / "communications.vault"
    batch = _batch(4)

    first = ingest_corpus_batch(vault_path, batch)
    second = ingest_corpus_batch(vault_path, batch)
    edited = json.loads(json.dumps(batch))
    edited["messages"][1]["body"] = "Bottom line: updated complete wording."
    edited["messages"][1]["modifiedAt"] = (
        datetime.fromisoformat(edited["messages"][1]["modifiedAt"]) + timedelta(minutes=1)
    ).isoformat()
    third = ingest_corpus_batch(vault_path, edited)
    context = get_corpus_context(vault_path, "Jordan Lee", limit=10)

    assert first["status"] == "stored"
    assert second["status"] == "unchanged"
    assert third["updatedMessageCount"] == 1
    assert any(item["body"] == "Bottom line: updated complete wording." for item in context["messages"])


@pytest.mark.skipif(os.name != "nt", reason="Current-user DPAPI is Windows-only.")
def test_identity_rename_merges_aliases_without_splitting_profile_source(tmp_path: Path) -> None:
    vault_path = tmp_path / "communications.vault"
    batch = _batch(6)
    mike_messages = [
        message
        for message in batch["messages"]
        if message["author"]["displayName"] == "Jordan Lee"
    ]
    mike_messages[0]["author"]["displayName"] = "Michael Lee"

    ingest_corpus_batch(vault_path, batch)
    people = list_corpus_people(vault_path)
    by_name = {person["displayName"]: person for person in people["people"]}
    context = get_corpus_context(vault_path, "Michael Lee", limit=20)

    jordan_row = by_name["Jordan Lee"]
    assert people["personCount"] == 2
    assert jordan_row["aliases"] == ["Michael Lee"]
    assert jordan_row["messageCount"] == 6
    assert context["messageCount"] == 6


@pytest.mark.skipif(os.name != "nt", reason="Current-user DPAPI is Windows-only.")
def test_vault_invalidation_and_person_deletion_remove_data(tmp_path: Path) -> None:
    vault_path = tmp_path / "communications.vault"
    batch = _batch(6)
    ingest_corpus_batch(vault_path, batch)

    deleted = delete_corpus_person(vault_path, "Jordan Lee")
    assert deleted["removedMessageCount"] == 6
    with pytest.raises(InteractionProfileBlockedError):
        get_corpus_context(vault_path, "Jordan Lee")

    invalidated = invalidate_corpus_batch(vault_path, batch["batchId"])
    assert invalidated["remainingMessageCount"] == 0


def test_teams_duplicate_display_name_fails_closed_without_native_identity() -> None:
    export = {
        "threads": [
            {
                "thread": {
                    "chat_id": "19:duplicate-name@thread.v2",
                    "latest_message_at": "2026-07-20T18:00:00+00:00",
                },
                "members": {
                    "members": [
                        {
                            "id": "user-alex-one",
                            "display_name": "Alex Smith",
                            "email": "alex.one@corp.example",
                        },
                        {
                            "id": "user-alex-two",
                            "display_name": "Alex Smith",
                            "email": "alex.two@corp.example",
                        },
                        {
                            "id": "user-taylor",
                            "display_name": "Taylor Morgan",
                            "email": "taylor.morgan@corp.example",
                        },
                    ]
                },
                "transcript": {
                    "id": "transcript-duplicate-name",
                    "created_at": "2026-07-20T18:00:00+00:00",
                    "content": (
                        "[Alex Smith]: This must not be attributed by name alone.\n\n"
                        "[Taylor Morgan]: This identity is unique."
                    ),
                },
            }
        ]
    }

    batch = corpus_batch_from_teams_export(
        export,
        batch_id="corpus-batch-teams-duplicate-name-001",
    )

    assert [item["author"]["displayName"] for item in batch["messages"]] == [
        "Taylor Morgan"
    ]
    assert batch["collection"]["excludedReasonCounts"] == {"unresolved_identity": 1}


def test_teams_prefers_native_identity_message_id_and_timestamp() -> None:
    export = {
        "threads": [
            {
                "thread": {
                    "chat_id": "19:native-metadata@thread.v2",
                    "latest_message_at": "2026-07-20T20:00:00+00:00",
                },
                "members": {
                    "members": [
                        {
                            "id": "user-alex-one",
                            "display_name": "Alex Smith",
                            "email": "alex.one@corp.example",
                        },
                        {
                            "id": "user-alex-two",
                            "display_name": "Alex Smith",
                            "email": "alex.two@corp.example",
                        },
                    ]
                },
                "transcript": {
                    "id": "transcript-native-metadata",
                    "created_at": "2026-07-20T20:00:00+00:00",
                    "messages": [
                        {
                            "id": "native-message-001",
                            "createdDateTime": "2026-07-18T14:30:00+00:00",
                            "lastModifiedDateTime": "2026-07-18T14:31:00+00:00",
                            "from": {
                                "user": {
                                    "id": "user-alex-two",
                                    "displayName": "Alex Smith",
                                }
                            },
                            "body": {"content": "Use the native message metadata."},
                        }
                    ],
                },
            }
        ]
    }

    batch = corpus_batch_from_teams_export(
        export,
        batch_id="corpus-batch-teams-native-metadata-001",
    )
    message = batch["messages"][0]

    assert validate_corpus_batch(batch) == []
    assert message["author"]["identityFingerprint"] == _sha(
        "alex.two@corp.example"
    )
    assert message["sourceRecordId"].endswith(":message:native-message-001")
    assert message["sentAt"] == "2026-07-18T14:30:00+00:00"
    assert message["modifiedAt"] == "2026-07-18T14:31:00+00:00"
    assert message["sentAtPrecision"] == "message_timestamp"


def test_teams_fallback_ids_include_transcript_identity_and_sequence() -> None:
    export = {
        "threads": [
            {
                "thread": {
                    "chat_id": "19:fallback-id@thread.v2",
                    "latest_message_at": "2026-07-20T20:00:00+00:00",
                },
                "members": {
                    "members": [
                        {
                            "id": "user-taylor",
                            "display_name": "Taylor Morgan",
                            "email": "taylor.morgan@corp.example",
                        }
                    ]
                },
                "transcript": {
                    "id": "stable-transcript-001",
                    "created_at": "2026-07-20T20:00:00+00:00",
                    "content": (
                        "[Taylor Morgan]: Same short response.\n\n"
                        "[Taylor Morgan]: Same short response."
                    ),
                },
            }
        ]
    }

    first = corpus_batch_from_teams_export(
        export,
        batch_id="corpus-batch-teams-fallback-id-001",
    )
    second = corpus_batch_from_teams_export(
        export,
        batch_id="corpus-batch-teams-fallback-id-002",
    )
    first_ids = [message["sourceRecordId"] for message in first["messages"]]

    assert len(first_ids) == len(set(first_ids)) == 2
    assert first_ids == [message["sourceRecordId"] for message in second["messages"]]
    assert first_ids[0].endswith(":chunk:0")
    assert first_ids[1].endswith(":chunk:1")


def test_teams_fallback_ids_are_stable_when_export_order_changes() -> None:
    def entry(chat_id: str, created_at: str, body: str) -> dict:
        return {
            "thread": {
                "chat_id": chat_id,
                "latest_message_at": created_at,
            },
            "members": {
                "members": [
                    {
                        "id": "user-taylor",
                        "display_name": "Taylor Morgan",
                        "email": "taylor.morgan@corp.example",
                    }
                ]
            },
            "transcript": {
                "created_at": created_at,
                "content": f"[Taylor Morgan]: {body}",
            },
        }

    target = entry(
        "19:stable-target@thread.v2",
        "2026-07-20T20:00:00+00:00",
        "Stable message.",
    )
    other = entry(
        "19:other@thread.v2",
        "2026-07-21T20:00:00+00:00",
        "Other message.",
    )

    first = corpus_batch_from_teams_export(
        {"threads": [target, other]},
        batch_id="corpus-batch-teams-order-a-001",
    )
    second = corpus_batch_from_teams_export(
        {"threads": [other, target]},
        batch_id="corpus-batch-teams-order-b-001",
    )

    first_target = next(
        item
        for item in first["messages"]
        if item["conversationFingerprint"] == _sha("19:stable-target@thread.v2")
    )
    second_target = next(
        item
        for item in second["messages"]
        if item["conversationFingerprint"] == _sha("19:stable-target@thread.v2")
    )
    assert first_target["sourceRecordId"] == second_target["sourceRecordId"]


def test_outlook_native_conversation_id_separates_repeated_subjects() -> None:
    def message(message_id: str, conversation_id: str, sent_at: str) -> dict:
        return {
            "id": message_id,
            "conversationId": conversation_id,
            "subject": "Weekly status",
            "sentDateTime": sent_at,
            "sender": {
                "emailAddress": {
                    "name": "Jordan Lee",
                    "address": "jordan.lee@corp.example",
                }
            },
            "toRecipients": [
                {
                    "emailAddress": {
                        "name": "Taylor Morgan",
                        "address": "taylor.morgan@corp.example",
                    }
                }
            ],
            "body": {"content": "The current workstream is on track."},
        }

    batch = corpus_batch_from_outlook_export(
        {
            "results": [
                message(
                    "message-conversation-one",
                    "native-conversation-one",
                    "2026-07-18T14:30:00+00:00",
                ),
                message(
                    "message-conversation-two",
                    "native-conversation-two",
                    "2026-07-19T14:30:00+00:00",
                ),
            ]
        },
        batch_id="corpus-batch-outlook-native-conversation-001",
    )

    assert validate_corpus_batch(batch) == []
    assert len(
        {message["conversationFingerprint"] for message in batch["messages"]}
    ) == 2


@pytest.mark.skipif(os.name != "nt", reason="Current-user DPAPI is Windows-only.")
def test_snapshot_only_teams_time_does_not_create_longitudinal_readiness(
    tmp_path: Path,
) -> None:
    export = {
        "threads": [
            {
                "thread": {
                    "chat_id": "19:snapshot-only@thread.v2",
                    "latest_message_at": "2026-07-20T20:00:00+00:00",
                },
                "members": {
                    "members": [
                        {
                            "id": "user-mike",
                            "display_name": "Jordan Lee",
                            "email": "jordan.lee@corp.example",
                        }
                    ]
                },
                "transcript": {
                    "id": "snapshot-only-transcript",
                    "created_at": "2026-07-20T20:00:00+00:00",
                    "content": "\n\n".join(
                        f"[Jordan Lee]: Status note {index}." for index in range(6)
                    ),
                },
            }
        ]
    }
    batch = corpus_batch_from_teams_export(
        export,
        batch_id="corpus-batch-teams-snapshot-only-001",
    )
    vault_path = tmp_path / "snapshot-only.vault"

    ingest_corpus_batch(vault_path, batch)
    bundle = derive_observation_bundle(vault_path, "Jordan Lee")

    assert {
        message["sentAtPrecision"] for message in batch["messages"]
    } == {"snapshot_timestamp"}
    assert bundle["collection"]["activeDayCount"] == 0
    assert bundle["collection"]["windowStart"] == bundle["collection"]["windowEnd"]


@pytest.mark.skipif(os.name != "nt", reason="Current-user DPAPI is Windows-only.")
def test_freshservice_analysis_strips_quotes_and_signature_but_vault_keeps_body(
    tmp_path: Path,
) -> None:
    messages = []
    for index in range(3):
        messages.append(
            {
                "conversation_id": str(8000 + index),
                "created_at": f"2026-07-{10 + index:02d}T10:00:00+00:00",
                "updated_at": "",
                "user_id": "501",
                "role": "Agent",
                "incoming": False,
                "private": False,
                "from_email": "jordan.lee@corp.example",
                "body": (
                    "Use the reset path and close the ticket.<br>"
                    "Thanks,<br>Jordan Lee<br>IT Support<br>"
                    "jordan.lee@corp.example<br><br>"
                    "<blockquote>Customer said: always write a very long explanation."
                    "</blockquote>"
                ),
            }
        )
    cases_path = tmp_path / "freshservice-agent-cases.jsonl"
    cases_path.write_text(
        json.dumps(
            {
                "ticket_id": "800",
                "subject": "Resolved reset request",
                "type": "Service Request",
                "status_code": "4",
                "messages": messages,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    cleaning_path = tmp_path / "cleaning-manifest.json"
    cleaning_path.write_text(
        json.dumps(
            {
                "source_ticket_count": 1,
                "source_conversation_count": 3,
                "include_private_notes": True,
                "deduplicate_messages": False,
                "redaction_mode": {"secret_like_values": "always"},
            }
        ),
        encoding="utf-8",
    )
    export_path = tmp_path / "export-manifest.json"
    export_path.write_text(
        json.dumps(
            {"ticket_count": 1, "conversation_count": 3, "read_only": True}
        ),
        encoding="utf-8",
    )
    identity_map = {
        "artifactType": "freshservice_identity_map",
        "schemaVersion": 1,
        "people": [
            {
                "displayName": "Jordan Lee",
                "emails": ["jordan.lee@corp.example"],
                "freshserviceUserIds": ["501"],
            }
        ],
    }
    batch = corpus_batch_from_freshservice_jsonl(
        cases_path,
        cleaning_manifest_path=cleaning_path,
        export_manifest_path=export_path,
        batch_id="corpus-batch-freshservice-quote-strip-001",
        identity_map=identity_map,
    )
    vault_path = tmp_path / "freshservice-quotes.vault"

    ingest_corpus_batch(vault_path, batch)
    context = get_corpus_context(vault_path, "Jordan Lee")
    bundle = derive_observation_bundle(vault_path, "Jordan Lee")
    private_examples = " ".join(
        item["exampleText"] for item in bundle["privateExamples"]
    ).casefold()

    assert "customer said" in context["messages"][0]["body"].casefold()
    assert "jordan lee" in context["messages"][0]["body"].casefold()
    assert "customer said" not in private_examples
    assert "jordan lee" not in private_examples
    assert "it support" not in private_examples


@pytest.mark.skipif(os.name != "nt", reason="Current-user DPAPI is Windows-only.")
def test_observation_counts_are_scoped_to_each_context(tmp_path: Path) -> None:
    start = datetime(2026, 5, 1, tzinfo=timezone.utc)
    messages = []
    for index in range(32):
        context = "status_update" if index < 21 else "decision_request"
        body = (
            "Short status."
            if index < 22
            else " ".join(["detailed"] * 240)
        )
        item = _message(
            index=index,
            author="Jordan Lee",
            author_key="mike-directory-id",
            sent_at=start + timedelta(days=index),
            conversation=index,
            body=body,
            source="microsoft_outlook",
        )
        item["context"] = context
        messages.append(item)
    batch = _batch(1)
    batch["batchId"] = "corpus-batch-context-evidence-001"
    batch["messages"] = messages
    vault_path = tmp_path / "context-evidence.vault"

    ingest_corpus_batch(vault_path, batch)
    bundle = derive_observation_bundle(vault_path, "Jordan Lee")
    density_rows = [
        item
        for item in bundle["observations"]
        if item["dimension"] == "information_density"
    ]
    by_context = {item["contexts"][0]: item for item in density_rows}

    assert all(len(item["contexts"]) == 1 for item in density_rows)
    assert by_context["status_update"]["tendencyCode"] == "concise_first"
    assert by_context["status_update"]["supportCount"] == 21
    assert by_context["status_update"]["contradictionCount"] == 0
    assert by_context["decision_request"]["tendencyCode"] == "detailed_by_default"
    assert by_context["decision_request"]["supportCount"] == 10
    assert by_context["decision_request"]["contradictionCount"] == 1


@pytest.mark.skipif(os.name != "nt", reason="Current-user DPAPI is Windows-only.")
def test_classifiers_abstain_when_action_structure_and_question_evidence_is_missing(
    tmp_path: Path,
) -> None:
    start = datetime(2026, 6, 1, tzinfo=timezone.utc)
    body = (
        "Is the conference room on the third floor? "
        + " ".join(["background"] * 140)
    )
    messages = []
    for index in range(5):
        item = _message(
            index=index,
            author="Jordan Lee",
            author_key="mike-directory-id",
            sent_at=start + timedelta(days=index),
            conversation=index,
            body=body,
            source="microsoft_outlook",
        )
        item["context"] = "informal_coordination"
        messages.append(item)
    batch = _batch(1)
    batch["batchId"] = "corpus-batch-classifier-abstention-001"
    batch["messages"] = messages
    vault_path = tmp_path / "classifier-abstention.vault"

    ingest_corpus_batch(vault_path, batch)
    bundle = derive_observation_bundle(vault_path, "Jordan Lee")
    dimensions = {item["dimension"] for item in bundle["observations"]}

    assert "action_clarity" not in dimensions
    assert "structure_preference" not in dimensions
    assert bundle["responseHypotheses"] == []
    assert bundle["privateExamples"] == []


@pytest.mark.skipif(os.name != "nt", reason="Current-user DPAPI is Windows-only.")
def test_question_patterns_use_only_the_question_clause(tmp_path: Path) -> None:
    start = datetime(2026, 6, 1, tzinfo=timezone.utc)
    messages = []
    for index in range(5):
        item = _message(
            index=index,
            author="Jordan Lee",
            author_key="mike-directory-id",
            sent_at=start + timedelta(days=index),
            conversation=index,
            body=(
                "Who owns this? The later note will include implementation, "
                "source data, and scope detail."
            ),
            source="microsoft_outlook",
        )
        item["context"] = "decision_request"
        messages.append(item)
    batch = _batch(1)
    batch["batchId"] = "corpus-batch-question-clause-001"
    batch["messages"] = messages
    vault_path = tmp_path / "question-clause.vault"

    ingest_corpus_batch(vault_path, batch)
    bundle = derive_observation_bundle(vault_path, "Jordan Lee")
    question_codes = {
        item["tendencyCode"]
        for item in bundle["observations"]
        if item["dimension"] == "question_pattern"
    }

    assert question_codes == {"ownership"}

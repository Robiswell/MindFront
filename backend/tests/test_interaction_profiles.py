from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from mindfront import interaction_profiles as profile_module
from mindfront.interaction_profiles import (
    InteractionProfileBlockedError,
    build_interaction_profile,
    delete_interaction_profile,
    get_interaction_profile,
    infer_interaction_context,
    invalidate_profile_batch,
    list_interaction_profiles,
    profile_guidance,
    upsert_profile_store,
    validate_observation_bundle,
)
from mindfront.analysis import analyze_message_brief, write_analysis_report
from mindfront.compare import compare_variant_bundle, write_comparison_report
from mindfront.reports import build_report_bundle
from mindfront.rewrite import rewrite_message_brief, write_rewrite_bundle


def _bundle(
    *,
    bundle_id: str = "comms-bundle-mike-001",
    name: str = "Jordan Lee",
    fingerprint: str = "sha256:" + "a" * 64,
    support: int = 40,
    contradictions: int = 10,
) -> dict:
    start = datetime(2026, 5, 1, tzinfo=timezone.utc)
    end = start + timedelta(days=60)
    return {
        "artifactType": "communication_observation_bundle",
        "schemaVersion": 1,
        "bundleId": bundle_id,
        "purpose": "autistic_communication_assistance",
        "subject": {
            "displayName": name,
            "identityResolution": "confirmed_directory_identity",
            "identityFingerprint": fingerprint,
        },
        "authorization": {
            "requesterHasLegitimateAccess": True,
            "subjectAuthoredOnly": True,
            "assistiveUseOnly": True,
            "humanReviewRequired": True,
            "noEmploymentDecisionUse": True,
            "companySystemContentAuthorized": True,
            "codexProcessingAuthorized": True,
            "privateOneToOneIncluded": True,
            "privateOneToOneUseApproved": True,
            "governanceBasis": "user_asserted_company_policy",
        },
        "collection": {
            "sourceSystems": ["microsoft_teams", "microsoft_outlook", "resolved_support_ticket"],
            "coverageComplete": False,
            "windowStart": start.isoformat(),
            "windowEnd": end.isoformat(),
            "authoredMessageCount": 80,
            "conversationCount": 12,
            "contextCount": 4,
            "activeDayCount": 42,
            "excludedSensitiveMessageCount": 0,
            "sensitiveCategoriesExcluded": [
                "credentials_and_secrets",
                "cui_and_export_controlled",
            ],
            "rawContentPersisted": False,
            "attachmentsProcessed": False,
            "externalModelProcessingUsed": True,
            "resolvedTicketCount": 10,
            "resolutionOutcomeKnown": True,
        },
        "observations": [
            {
                "dimension": "opening_preference",
                "tendencyCode": "bottom_line_first",
                "basis": "behavioral_pattern",
                "subjectConfirmed": False,
                "supportCount": support,
                "contradictionCount": contradictions,
                "contexts": ["executive_update", "decision_request"],
                "contextEvidence": [
                    {
                        "context": "executive_update",
                        "supportCount": support,
                        "contradictionCount": contradictions,
                        "sampleSize": support + contradictions,
                    },
                    {
                        "context": "decision_request",
                        "supportCount": support,
                        "contradictionCount": contradictions,
                        "sampleSize": support + contradictions,
                    },
                ],
                "sourceSystems": ["microsoft_teams", "microsoft_outlook"],
                "firstObservedAt": start.isoformat(),
                "lastObservedAt": end.isoformat(),
            },
            {
                "dimension": "tone_register",
                "tendencyCode": "informal_direct",
                "basis": "behavioral_pattern",
                "subjectConfirmed": False,
                "supportCount": 30,
                "contradictionCount": 5,
                "contexts": ["informal_coordination", "status_update"],
                "contextEvidence": [
                    {
                        "context": "informal_coordination",
                        "supportCount": 24,
                        "contradictionCount": 4,
                        "sampleSize": 28,
                    },
                    {
                        "context": "status_update",
                        "supportCount": 24,
                        "contradictionCount": 4,
                        "sampleSize": 28,
                    },
                ],
                "sourceSystems": ["microsoft_teams"],
                "firstObservedAt": start.isoformat(),
                "lastObservedAt": end.isoformat(),
            },
        ],
        "responseHypotheses": [
            {
                "triggerClass": "decision_request",
                "responseClass": "request_ownership",
                "supportCount": 12,
                "contradictionCount": 3,
                "contexts": ["decision_request", "project_planning"],
                "sourceSystems": ["microsoft_teams", "microsoft_outlook"],
            }
        ],
        "privateLexicon": [
            {
                "term": "bottom line",
                "category": "decision_phrase",
                "supportCount": 8,
                "contexts": ["decision_request"],
                "sourceSystems": ["microsoft_teams"],
            }
        ],
        "privateExamples": [
            {
                "exampleText": "Bottom line: the owner and next step need to be clear.",
                "exampleKind": "decision_response",
                "outcomeClass": "advanced_work",
                "similarExample Organizationunt": 4,
                "contexts": ["decision_request"],
                "sourceSystems": ["microsoft_teams"],
                "observedAt": end.isoformat(),
            }
        ],
    }


def test_builds_active_profile_with_private_assistive_context() -> None:
    profile = build_interaction_profile(_bundle())

    assert profile["status"] == "active"
    assert profile["eligibleForAutomaticUse"] is True
    assert profile["displayName"] == "Jordan Lee"
    assert profile["marketEvidenceCreated"] is False
    assert profile["rawContentStored"] is False
    assert profile["assistiveGuidance"]["preferredTerminology"] == ["bottom line"]
    assert profile["assistiveGuidance"]["representativeExamples"][0]["exampleText"].startswith("Bottom line")
    assert "exact future behavior" in profile["evidenceBoundary"]


def test_response_hypothesis_can_qualify_within_one_trigger_context() -> None:
    bundle = _bundle()
    bundle["responseHypotheses"][0].update(
        {
            "supportCount": 25,
            "contradictionCount": 5,
            "contexts": ["decision_request"],
        }
    )

    profile = build_interaction_profile(bundle)

    assert profile["likelyResponsePatterns"][0]["confidence"] == "context_supported"
    assert profile["assistiveGuidance"]["likelyQuestionsOrReactions"]


def test_context_inference_uses_communication_purpose_not_audience_job_title() -> None:
    context = infer_interaction_context(
        {
            "messageGoal": "Explain an early product message.",
            "targetAudience": "A technical solutions lead",
            "channel": "landing_page",
            "sourceText": "The draft explains the product and the next validation step.",
        }
    )

    assert context == "informal_coordination"


def test_profile_guidance_filters_patterns_to_the_current_context() -> None:
    profile = build_interaction_profile(_bundle())

    decision = profile_guidance(profile, context="decision_request")
    unsupported = profile_guidance(profile, context="support_request")

    assert decision["contextMatched"] is True
    assert decision["matchedContext"] == "decision_request"
    assert decision["observedCommunicationPatterns"]
    assert all(
        "decision_request" in observation["contexts"]
        for observation in decision["observedCommunicationPatterns"]
    )
    assert unsupported["contextMatched"] is False
    assert unsupported["observedCommunicationPatterns"] == []
    assert unsupported["likelyResponsePatterns"] == []


def test_separate_single_context_observations_can_activate_profile() -> None:
    bundle = _bundle()
    bundle["observations"] = [
        {
            **bundle["observations"][0],
            "supportCount": 32,
            "contradictionCount": 4,
            "contexts": ["executive_update"],
        },
        {
            **bundle["observations"][1],
            "supportCount": 28,
            "contradictionCount": 3,
            "contexts": ["status_update"],
        },
    ]
    for observation in bundle["observations"]:
        observation.pop("contextEvidence", None)

    profile = build_interaction_profile(bundle)

    assert profile["status"] == "active"
    assert profile["eligibleForAutomaticUse"] is True
    assert profile_guidance(profile, context="executive_update")["contextMatched"] is True
    assert profile_guidance(profile, context="status_update")["contextMatched"] is True


def test_context_a_evidence_cannot_qualify_context_b() -> None:
    bundle = _bundle()
    observation = bundle["observations"][0]
    observation["supportCount"] = 50
    observation["contradictionCount"] = 5
    observation["contexts"] = ["executive_update", "decision_request"]
    observation["contextEvidence"] = [
        {
            "context": "executive_update",
            "supportCount": 30,
            "contradictionCount": 2,
            "sampleSize": 32,
        },
        {
            "context": "decision_request",
            "supportCount": 4,
            "contradictionCount": 8,
            "sampleSize": 12,
        },
    ]
    bundle["observations"] = [observation]
    bundle["responseHypotheses"] = []
    bundle["privateLexicon"] = []
    bundle["privateExamples"] = []

    profile = build_interaction_profile(bundle)
    executive = profile_guidance(profile, context="executive_update")
    decision = profile_guidance(profile, context="decision_request")

    assert executive["contextMatched"] is True
    assert executive["observedCommunicationPatterns"]
    assert decision["contextMatched"] is False
    assert decision["observedCommunicationPatterns"] == []


def test_top_level_context_evidence_is_a_same_context_guard() -> None:
    bundle = _bundle()
    bundle["observations"] = [
        {
            **bundle["observations"][0],
            "supportCount": 30,
            "contradictionCount": 2,
            "contexts": ["executive_update"],
        },
        {
            **bundle["observations"][1],
            "supportCount": 30,
            "contradictionCount": 2,
            "contexts": ["status_update"],
        },
    ]
    for observation in bundle["observations"]:
        observation.pop("contextEvidence", None)
    bundle["contextEvidence"] = [
        {
            "context": "executive_update",
            "supportCount": 30,
            "contradictionCount": 2,
            "sampleSize": 32,
        },
        {
            "context": "status_update",
            "supportCount": 6,
            "contradictionCount": 12,
            "sampleSize": 18,
        },
    ]

    profile = build_interaction_profile(bundle)

    assert profile_guidance(profile, context="executive_update")["contextMatched"] is True
    assert profile_guidance(profile, context="status_update")["contextMatched"] is False


def test_rejects_raw_message_fields_in_feature_bundle() -> None:
    bundle = _bundle()
    bundle["observations"][0]["messageBody"] = "private full message"

    errors = validate_observation_bundle(bundle)

    assert any(error["code"] == "raw_content_field_prohibited" for error in errors)
    assert any(error["code"] == "free_text_or_unknown_observation_field" for error in errors)


def test_rejects_unconfirmed_identity_and_absolute_prediction_field() -> None:
    bundle = _bundle()
    bundle["subject"]["identityResolution"] = "display_name_guess"
    bundle["responseHypotheses"][0]["likelyResponsePattern"] = "Mike will always ask who owns this."

    errors = validate_observation_bundle(bundle)

    assert any(error["code"] == "identity_not_confirmed" for error in errors)
    assert any(error["code"] == "free_text_or_unknown_hypothesis_field" for error in errors)


def test_collecting_profile_does_not_emit_automatic_guidance() -> None:
    bundle = _bundle(support=4, contradictions=20)
    bundle["collection"]["authoredMessageCount"] = 12
    bundle["collection"]["activeDayCount"] = 5

    profile = build_interaction_profile(bundle)

    assert profile["status"] == "collecting"
    assert profile["eligibleForAutomaticUse"] is False
    with pytest.raises(InteractionProfileBlockedError):
        profile_guidance(profile)


def test_active_profile_guides_analysis_and_rewrite_without_changing_evidence() -> None:
    profile = build_interaction_profile(_bundle())
    brief = Path("examples/briefs/sample-message-brief.json")

    analysis = analyze_message_brief(brief, config_root=Path("config"), interaction_profile=profile)
    rewrite = rewrite_message_brief(brief, config_root=Path("config"), interaction_profile=profile)

    assert analysis["interactionAssistance"]["applied"] is True
    assert analysis["interactionAssistance"]["recipientNameIncluded"] is False
    assert "recipientName" not in analysis["interactionAssistance"]
    assert analysis["interactionAssistance"]["privateGuidanceIncludedInReport"] is False
    assert analysis["evidenceBasisSummary"]["marketEvidenceAvailable"] is False
    assert rewrite["interactionAssistance"]["applied"] is True
    assert rewrite["interactionAssistance"]["recipientNameIncluded"] is False
    assert "recipientName" not in rewrite["interactionAssistance"]
    assert rewrite["variants"][0]["strategyId"] == "profile_guided"
    assert rewrite["claimGateSummary"]["marketEvidenceCreated"] is False


def test_context_mismatch_prevents_profile_guided_rewrite() -> None:
    profile = build_interaction_profile(_bundle())
    brief = Path("examples/briefs/sample-message-brief.json")

    analysis = analyze_message_brief(
        brief,
        config_root=Path("config"),
        interaction_profile=profile,
        interaction_profile_context="support_request",
    )
    rewrite = rewrite_message_brief(
        brief,
        config_root=Path("config"),
        interaction_profile=profile,
        interaction_profile_context="support_request",
    )

    assert analysis["interactionAssistance"]["applied"] is False
    assert analysis["interactionAssistance"]["contextMatched"] is False
    assert analysis["interactionAssistance"]["matchedContext"] == "support_request"
    assert analysis["interactionAssistance"]["reason"] == "no_context_supported_profile_observation"
    assert rewrite["interactionAssistance"]["applied"] is False
    assert rewrite["interactionAssistance"]["contextMatched"] is False
    assert all(variant["strategyId"] != "profile_guided" for variant in rewrite["variants"])


def test_profile_lineage_reaches_report_without_recipient_name(tmp_path: Path) -> None:
    profile = build_interaction_profile(_bundle())
    brief = Path("examples/briefs/sample-message-brief.json")
    analysis = analyze_message_brief(brief, config_root=Path("config"), interaction_profile=profile)
    rewrite = rewrite_message_brief(brief, config_root=Path("config"), interaction_profile=profile)
    analysis_path = write_analysis_report(analysis, tmp_path / "analysis")
    rewrite_path = write_rewrite_bundle(rewrite, tmp_path / "rewrite")
    comparison = compare_variant_bundle(rewrite_path)
    comparison_path = write_comparison_report(comparison, tmp_path / "compare")

    report = build_report_bundle(
        analysis_path,
        config_root=Path("config"),
        variants_path=rewrite_path,
        comparison_path=comparison_path,
    )
    serialized = json.dumps(
        {
            "analysis": analysis,
            "rewrite": rewrite,
            "comparison": comparison,
            "report": report,
        }
    )

    assert comparison["interactionAssistance"]["profileHash"] == profile["profileHash"]
    assert report["interactionAssistance"]["profileHash"] == profile["profileHash"]
    assert "Jordan Lee" not in serialized
    assert '"recipientName"' not in serialized


@pytest.mark.skipif(os.name != "nt", reason="Current-user DPAPI is Windows-only.")
def test_dpapi_store_upsert_duplicate_list_invalidate_and_delete(tmp_path: Path) -> None:
    store = tmp_path / "profiles.vault"
    bundle = _bundle()

    first = upsert_profile_store(store, bundle)
    second = upsert_profile_store(store, bundle)
    loaded = get_interaction_profile(store, "Jordan Lee")
    index = list_interaction_profiles(store)

    assert first["status"] == "created"
    assert second["status"] == "unchanged"
    assert loaded["displayName"] == "Jordan Lee"
    assert index["profileCount"] == 1
    envelope = json.loads(store.read_text(encoding="utf-8"))
    assert envelope["encryption"] == "aes_256_gcm_local_key_v1"
    assert "Jordan Lee" not in store.read_text(encoding="utf-8")

    invalidated = invalidate_profile_batch(store, bundle["bundleId"])
    assert invalidated["removedBatchCount"] == 1
    assert list_interaction_profiles(store)["profileCount"] == 0

    upsert_profile_store(store, _bundle(bundle_id="comms-bundle-mike-002"))
    deleted = delete_interaction_profile(store, "Jordan Lee")
    assert deleted["displayNameRemoved"] is True
    assert list_interaction_profiles(store)["profileCount"] == 0


@pytest.mark.skipif(os.name != "nt", reason="Current-user DPAPI is Windows-only.")
def test_full_corpus_refresh_replaces_snapshot_without_double_counting(tmp_path: Path) -> None:
    store = tmp_path / "profiles.vault"
    first = upsert_profile_store(store, _bundle())
    refreshed_bundle = _bundle(
        bundle_id="comms-bundle-mike-refreshed-001",
        support=28,
        contradictions=7,
    )

    refreshed = upsert_profile_store(
        store,
        refreshed_bundle,
        replace_existing=True,
    )
    loaded = get_interaction_profile(store, "Jordan Lee")

    opening = next(
        item
        for item in loaded["observedCommunicationPatterns"]
        if item["dimension"] == "opening_preference"
    )
    assert refreshed["status"] == "refreshed"
    assert loaded["profileId"] == first["profile"]["profileId"]
    assert loaded["sourceBatchCount"] == 1
    assert opening["supportCount"] == 28
    assert opening["contradictionCount"] == 7


@pytest.mark.skipif(os.name != "nt", reason="Current-user DPAPI is Windows-only.")
def test_generic_upsert_replaces_new_snapshot_and_replay_is_idempotent(tmp_path: Path) -> None:
    store = tmp_path / "profiles.vault"
    upsert_profile_store(store, _bundle())
    new_snapshot = _bundle(
        bundle_id="comms-bundle-mike-generic-refresh-001",
        support=26,
        contradictions=4,
    )

    refreshed = upsert_profile_store(store, new_snapshot)
    replay = upsert_profile_store(
        store,
        {
            **new_snapshot,
            "bundleId": "comms-bundle-mike-generic-replay-001",
        },
    )
    loaded = get_interaction_profile(store, "Jordan Lee")
    opening = next(
        item
        for item in loaded["observedCommunicationPatterns"]
        if item["dimension"] == "opening_preference"
    )

    assert refreshed["status"] == "refreshed"
    assert replay["status"] == "unchanged"
    assert loaded["sourceBatchCount"] == 1
    assert opening["supportCount"] == 26
    assert opening["contradictionCount"] == 4


@pytest.mark.skipif(os.name != "nt", reason="Current-user DPAPI is Windows-only.")
def test_same_bundle_refresh_migrates_legacy_profile_without_source_digest(tmp_path: Path) -> None:
    store = tmp_path / "profiles.vault"
    bundle = _bundle()
    upsert_profile_store(store, bundle)
    private_store = profile_module._load_store(store)
    private_store["profiles"][0].pop("_sourceCorpusDigest", None)
    profile_module._save_store(store, private_store)

    refreshed = upsert_profile_store(store, bundle)
    current = get_interaction_profile(
        store,
        "Jordan Lee",
        expected_source_bundle=bundle,
    )

    assert refreshed["status"] == "refreshed"
    assert current["status"] == "active"


@pytest.mark.skipif(os.name != "nt", reason="Current-user DPAPI is Windows-only.")
def test_profile_source_lineage_fails_closed_after_snapshot_replacement(tmp_path: Path) -> None:
    store = tmp_path / "profiles.vault"
    original = _bundle()
    upsert_profile_store(store, original)
    replacement = _bundle(
        bundle_id="comms-bundle-mike-replaced-corpus-001",
        support=31,
        contradictions=3,
    )

    with pytest.raises(InteractionProfileBlockedError) as exc:
        get_interaction_profile(
            store,
            "Jordan Lee",
            expected_source_bundle=replacement,
        )

    assert exc.value.reasons[0]["code"] == "source_mismatch"


@pytest.mark.skipif(os.name != "nt", reason="Current-user DPAPI is Windows-only.")
def test_store_blocks_same_display_name_for_different_identity(tmp_path: Path) -> None:
    store = tmp_path / "profiles.vault"
    upsert_profile_store(store, _bundle())

    with pytest.raises(InteractionProfileBlockedError) as exc:
        upsert_profile_store(
            store,
            _bundle(
                bundle_id="comms-bundle-collision-001",
                fingerprint="sha256:" + "b" * 64,
            ),
        )

    assert exc.value.reasons[0]["code"] == "display_name_identity_collision"

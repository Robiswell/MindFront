from __future__ import annotations

import json
import os
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

from mindfront.workplace_assistance import (
    WorkplaceAssistanceBlockedError,
    build_self_assistance_context,
    build_self_assistance_profile,
    build_workplace_assistance,
    delete_self_assistance_profile,
    finalize_workplace_assistance,
    get_self_assistance_profile,
    load_workplace_assistance_policy,
    upsert_self_assistance_profile,
    validate_self_assistance_profile,
    validate_workplace_assistance_policy,
    validate_workplace_assistance_request,
    write_workplace_assistance_result,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
EXAMPLE_ROOT = REPO_ROOT / "examples" / "workplace-assistance"
POLICY_PATH = REPO_ROOT / "config" / "workplace-assistance-policy.json"


def _json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _profile() -> dict:
    return _json(EXAMPLE_ROOT / "synthetic-self-profile.json")


def _request(mode: str) -> dict:
    return _json(EXAMPLE_ROOT / f"synthetic-{mode.replace('_', '-')}.json")


def _policy() -> dict:
    return load_workplace_assistance_policy(POLICY_PATH)


def _recipient_guidance() -> dict:
    return {
        "artifactType": "interaction_assistance_guidance",
        "profileId": "interaction-profile-synthetic-recipient",
        "displayName": "Synthetic Recipient",
        "purpose": "autistic_communication_assistance",
        "guidance": {
            "draftingAdjustments": [
                "Put the decision and owner in the first sentence.",
            ],
            "likelyQuestionsOrReactions": [
                "A request for the implementation owner is plausible.",
            ],
            "preferredTerminology": [],
            "terminologyToAvoid": [],
            "representativeExamples": [],
            "useRules": [
                "Require human review before sending or publishing.",
            ],
        },
        "likelyResponsePatterns": [],
        "observedCommunicationPatterns": [],
        "matchedContext": "decision_request",
        "contextMatched": True,
        "profileHash": "sha256:" + ("a" * 64),
        "expiresAt": "2099-01-01T00:00:00+00:00",
        "humanReviewRequired": True,
        "automaticSendingAllowed": False,
        "evidenceBoundary": "Synthetic directional guidance only.",
        "marketEvidenceCreated": False,
    }


def _gate_map(result: dict) -> dict[str, dict]:
    return {item["gateId"]: item for item in result["gates"]}


class SelfAssistanceProfileTests(unittest.TestCase):
    def test_valid_profile_is_explicitly_self_declared_and_voice_preserving(self) -> None:
        source = _profile()

        self.assertEqual([], validate_self_assistance_profile(source))
        built = build_self_assistance_profile(source)

        self.assertTrue(built["selfDeclared"])
        self.assertEqual(
            "single_point_of_accountability_with_distributed_ownership",
            built["careerAccountabilityModel"],
        )
        self.assertTrue(built["authenticityConstraints"]["preserveAmbition"])
        self.assertTrue(built["authenticityConstraints"]["doNotSuppressPersonality"])
        self.assertRegex(built["profileHash"], r"^sha256:[0-9a-f]{64}$")
        context = build_self_assistance_context(built)
        self.assertEqual(
            built["careerGoals"],
            context["careerGoals"],
        )
        self.assertEqual(
            built["knownCommunicationRisks"],
            context["knownCommunicationRisks"],
        )
        self.assertTrue(context["privateArtifact"])
        self.assertFalse(context["normalHistoryEligible"])

    def test_profile_rejects_unknown_fields_non_self_declaration_and_diagnosis(self) -> None:
        source = _profile()
        source["selfDeclared"] = False
        source["diagnosis"] = "This field must not be accepted."
        source["careerGoals"]["privateRanking"] = "not allowed"

        errors = validate_self_assistance_profile(source)
        codes = {item["code"] for item in errors}

        self.assertIn("profile_not_self_declared", codes)
        self.assertIn("diagnosis_field_not_allowed", codes)
        self.assertIn("unknown_field", codes)

    def test_profile_rejects_unsafe_delivery_boundaries(self) -> None:
        source = _profile()
        source["authorization"]["automaticSendingAllowed"] = True
        source["authorization"]["coworkerEvaluationAllowed"] = True
        source["authorization"]["humanReviewRequired"] = False

        errors = validate_self_assistance_profile(source)

        self.assertGreaterEqual(
            sum(item["code"] == "authorization_gate_failed" for item in errors),
            3,
        )

    def test_profile_rejects_mutated_content_with_stale_lineage_hash(self) -> None:
        built = build_self_assistance_profile(_profile())
        original_hash = built["profileHash"]
        built["careerGoals"]["targetRole"] = "Mutated Role"

        errors = validate_self_assistance_profile(built)

        self.assertEqual(original_hash, built["profileHash"])
        self.assertIn("profile_hash_mismatch", {item["code"] for item in errors})
        with self.assertRaises(WorkplaceAssistanceBlockedError):
            build_workplace_assistance(
                _request("preflight"),
                built,
                _policy(),
            )

    @unittest.skipUnless(os.name == "nt", "Current-user DPAPI is Windows-only.")
    def test_encrypted_profile_lifecycle_create_show_replace_and_delete(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store_path = (
                Path(temp_dir)
                / "runtime-data"
                / "self-assistance-profile.vault"
            )
            created = upsert_self_assistance_profile(store_path, _profile())

            self.assertEqual("created", created["status"])
            self.assertEqual(
                "self-assistance-profile-synthetic-primary",
                created["profileId"],
            )
            self.assertRegex(created["profileHash"], r"^sha256:[0-9a-f]{64}$")
            self.assertNotIn("profile", created)
            self.assertTrue(store_path.is_file())
            envelope_text = store_path.read_text(encoding="utf-8")
            self.assertNotIn("Example Dynamics", envelope_text)
            self.assertNotIn("preserveAmbition", envelope_text)
            self.assertIn("mindfront_encrypted_self_assistance_profile_store", envelope_text)

            shown = get_self_assistance_profile(store_path)
            self.assertEqual(
                "AI Enablement Lead at Example Dynamics",
                shown["careerGoals"]["targetRole"],
            )

            replacement = _profile()
            replacement["careerGoals"]["targetRole"] = "Enterprise Automation Lead at Example Dynamics"
            replaced = upsert_self_assistance_profile(store_path, replacement)
            self.assertEqual("replaced", replaced["status"])
            self.assertEqual(
                "Enterprise Automation Lead at Example Dynamics",
                get_self_assistance_profile(store_path)["careerGoals"]["targetRole"],
            )

            deleted = delete_self_assistance_profile(store_path)
            self.assertEqual("deleted", deleted["status"])
            self.assertTrue(deleted["storeRemoved"])
            self.assertFalse(store_path.exists())

    def test_private_store_rejects_paths_outside_runtime_data(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            unsafe_path = Path(temp_dir) / "self-assistance-profile.vault"

            with self.assertRaises(WorkplaceAssistanceBlockedError) as blocked:
                upsert_self_assistance_profile(unsafe_path, _profile())

        self.assertEqual(
            "private_runtime_path_required",
            blocked.exception.reasons[0]["code"],
        )


class WorkplaceAssistancePolicyTests(unittest.TestCase):
    def test_policy_is_strict_and_source_owned(self) -> None:
        policy = _policy()

        self.assertEqual([], validate_workplace_assistance_policy(policy))
        self.assertEqual(
            {
                "career_review",
                "debrief",
                "interpret",
                "preflight",
            },
            set(policy["modes"]),
        )
        self.assertFalse(policy["requiredBoundaries"]["automaticSendingAllowed"])
        self.assertFalse(policy["requiredBoundaries"]["coworkerEvaluationAllowed"])

    def test_policy_rejects_unknown_fields_and_unsafe_boundary(self) -> None:
        policy = _policy()
        policy["unknownPolicy"] = True
        policy["requiredBoundaries"]["promotionPredictionCreated"] = True

        errors = validate_workplace_assistance_policy(policy)
        codes = {item["code"] for item in errors}

        self.assertIn("unknown_field", codes)
        self.assertIn("unsafe_policy_boundary", codes)


class WorkplaceAssistanceModeTests(unittest.TestCase):
    def test_all_synthetic_modes_validate_and_keep_required_boundaries(self) -> None:
        profile = build_self_assistance_profile(_profile())
        policy = _policy()
        for mode in ("preflight", "interpret", "debrief", "career_review"):
            with self.subTest(mode=mode):
                request = _request(mode)
                self.assertEqual(
                    [],
                    validate_workplace_assistance_request(request, policy=policy),
                )
                result = build_workplace_assistance(request, profile, policy)
                self.assertTrue(result["humanReviewRequired"])
                self.assertFalse(result["automaticSendingAllowed"])
                self.assertFalse(result["coworkerEvaluationAllowed"])
                self.assertFalse(result["promotionPredictionCreated"])
                self.assertFalse(result["diagnosisCreated"])
                self.assertTrue(result["privateArtifact"])
                self.assertFalse(result["normalHistoryEligible"])
                self.assertEqual(mode, result["mode"])
                self.assertIn("heuristic_inference", result["evidenceBasis"])

    def test_preflight_partnership_keeps_domain_credit_and_approval_distinct(self) -> None:
        result = build_workplace_assistance(
            _request("preflight"),
            build_self_assistance_profile(_profile()),
            _policy(),
        )
        gates = _gate_map(result)
        assistance = result["assistance"]

        self.assertEqual("pass", gates["unsupported_authority"]["status"])
        self.assertEqual("pass", gates["ownership_approval_boundary"]["status"])
        self.assertEqual("pass", gates["visible_credit"]["status"])
        self.assertIn(
            "security specialist",
            assistance["layeredPlan"]["authorityAndApproval"],
        )
        self.assertIn(
            "security specialist",
            assistance["layeredPlan"]["visibleCredit"],
        )
        self.assertEqual(
            ["fact-pilot-direction-01"],
            assistance["authorityBasis"]["evidenceFactIds"],
        )
        self.assertIn("security specialist", assistance["shortVersion"])
        self.assertTrue(assistance["shortVersion"])
        self.assertTrue(assistance["interruptionSafeSentence"].startswith("Bottom line:"))
        self.assertEqual(
            70,
            assistance["supportProfileApplied"]["careerEffectivenessWeight"],
        )
        self.assertTrue(assistance["supportProfileApplied"]["layeredDetail"])
        self.assertTrue(assistance["supportProfileApplied"]["preserveDirectness"])
        self.assertEqual(
            "career_effectiveness_first",
            assistance["supportProfileApplied"]["optimizationPriority"],
        )

    def test_profile_tuning_changes_risk_priority_and_energy_protection(self) -> None:
        request = _request("preflight")
        request["draftText"] = (
            "Only I can do this. This is obvious, and they are just trying to look good. "
            "Approve the program, budget, and ownership change."
        )
        request["asks"] = [
            "Approve the program.",
            "Approve the budget.",
            "Approve the ownership change.",
        ]
        request["energyState"] = "rushed"
        primary_profile = build_self_assistance_profile(_profile())
        lower_career_profile_source = _profile()
        lower_career_profile_source["knownCommunicationRisks"] = ["overexplaining"]
        lower_career_profile_source["supportPreferences"][
            "careerEffectivenessWeight"
        ] = 20
        lower_career_profile_source["energyPreferences"][
            "rushedStateRequiresPause"
        ] = False
        lower_career_profile = build_self_assistance_profile(
            lower_career_profile_source
        )

        primary = build_workplace_assistance(request, primary_profile, _policy())
        lower_career = build_workplace_assistance(
            request,
            lower_career_profile,
            _policy(),
        )

        self.assertEqual(
            "career_effectiveness_first",
            primary["assistance"]["supportProfileApplied"][
                "optimizationPriority"
            ],
        )
        self.assertEqual(
            "social_load_reduction_first",
            lower_career["assistance"]["supportProfileApplied"][
                "optimizationPriority"
            ],
        )
        self.assertNotEqual(
            primary["assistance"]["supportProfileApplied"]["focusedRiskGateIds"][0],
            lower_career["assistance"]["supportProfileApplied"][
                "focusedRiskGateIds"
            ][0],
        )
        self.assertTrue(
            primary["assistance"]["supportProfileApplied"][
                "energyProtectionApplied"
            ]["pauseBeforeUse"]
        )
        self.assertFalse(
            lower_career["assistance"]["supportProfileApplied"][
                "energyProtectionApplied"
            ]["pauseBeforeUse"]
        )
        self.assertNotEqual(
            primary["assistance"]["smallestNextAction"],
            lower_career["assistance"]["smallestNextAction"],
        )

    def test_strict_recipient_guidance_materially_changes_private_assistance(self) -> None:
        baseline = build_workplace_assistance(
            _request("preflight"),
            build_self_assistance_profile(_profile()),
            _policy(),
        )
        guided = build_workplace_assistance(
            _request("preflight"),
            build_self_assistance_profile(_profile()),
            _policy(),
            recipient_guidance=_recipient_guidance(),
        )

        self.assertFalse(baseline["recipientAssistance"]["applied"])
        self.assertTrue(guided["recipientAssistance"]["applied"])
        self.assertTrue(guided["assistance"]["recipientGuidance"]["applied"])
        self.assertEqual(
            ["Put the decision and owner in the first sentence."],
            guided["assistance"]["recipientGuidance"]["draftingAdjustments"],
        )
        self.assertNotEqual(
            baseline["assistance"]["recipientGuidance"],
            guided["assistance"]["recipientGuidance"],
        )
        self.assertNotIn(
            "Synthetic Recipient",
            json.dumps(guided, sort_keys=True),
        )

    def test_minimal_or_expired_recipient_guidance_fails_closed(self) -> None:
        minimal = {
            "artifactType": "interaction_assistance_guidance",
            "contextMatched": True,
            "humanReviewRequired": True,
            "automaticSendingAllowed": False,
        }
        with self.assertRaises(WorkplaceAssistanceBlockedError):
            build_workplace_assistance(
                _request("preflight"),
                build_self_assistance_profile(_profile()),
                _policy(),
                recipient_guidance=minimal,
            )

        expired = _recipient_guidance()
        expired["expiresAt"] = "2020-01-01T00:00:00+00:00"
        with self.assertRaises(WorkplaceAssistanceBlockedError):
            build_workplace_assistance(
                _request("preflight"),
                build_self_assistance_profile(_profile()),
                _policy(),
                recipient_guidance=expired,
            )

    def test_interpret_returns_multiple_non_motive_alternatives(self) -> None:
        request = _request("interpret")
        request["incomingText"] = (
            "Only I can own this. I am just trying to make this work. "
            "Can you clarify the owner and date?"
        )
        result = build_workplace_assistance(
            request,
            build_self_assistance_profile(_profile()),
            _policy(),
        )
        alternatives = result["assistance"]["plausibleInterpretations"]
        gates = _gate_map(result)

        self.assertGreaterEqual(len(alternatives), 2)
        self.assertTrue(all(item["notFact"] for item in alternatives))
        self.assertTrue(all(item["motiveClaim"] is False for item in alternatives))
        self.assertTrue(all(item["confidence"] == "low" for item in alternatives))
        self.assertEqual("pass", gates["monopoly_language"]["status"])
        self.assertEqual("pass", gates["motive_attribution"]["status"])
        self.assertFalse(gates["exact_ask"]["applicable"])
        self.assertFalse(gates["message_stacking"]["applicable"])
        self.assertTrue(result["explicitFacts"])
        self.assertTrue(result["unknowns"])
        self.assertTrue(result["clarifyingQuestion"])

    def test_interpret_recognizes_bounded_support_before_expansion(self) -> None:
        request = _request("interpret")
        request["incomingText"] = (
            "Interesting. Let's keep this small and make sure the owners are clear "
            "before it goes wider."
        )

        result = build_workplace_assistance(
            request,
            build_self_assistance_profile(_profile()),
            _policy(),
        )
        statements = [
            item["statement"]
            for item in result["assistance"]["plausibleInterpretations"]
        ]

        self.assertTrue(
            any("conditional support" in statement for statement in statements)
        )
        self.assertTrue(
            any("before considering expansion" in statement for statement in statements)
        )

    def test_preflight_turns_a_fifteen_minute_constraint_into_an_agenda(self) -> None:
        request = _request("preflight")
        request["situation"]["channel"] = "meeting"
        request["situation"]["durationMinutes"] = 15

        result = build_workplace_assistance(
            request,
            build_self_assistance_profile(_profile()),
            _policy(),
        )
        agenda = result["assistance"]["timeBoxPlan"]

        self.assertEqual(15, sum(item["minutes"] for item in agenda))
        self.assertEqual(4, len(agenda))
        self.assertIn("exact ask", agenda[0]["focus"])
        self.assertIn("decision, owner, date", agenda[-1]["focus"])

    def test_debrief_separates_decisions_owners_dates_and_unresolved_items(self) -> None:
        result = build_workplace_assistance(
            _request("debrief"),
            build_self_assistance_profile(_profile()),
            _policy(),
        )
        assistance = result["assistance"]

        self.assertEqual(1, len(assistance["decisions"]))
        self.assertEqual(1, len(assistance["commitments"]))
        self.assertEqual(2, len(assistance["ownersAndDates"]))
        self.assertTrue(all(item["owner"] for item in assistance["ownersAndDates"]))
        self.assertTrue(all(item["dueDate"] for item in assistance["ownersAndDates"]))
        self.assertEqual(
            ["Confirm the final pilot participant list."],
            assistance["unresolvedItems"],
        )
        self.assertGreaterEqual(len(assistance["plausibleInterpretations"]), 2)

    def test_career_review_classifies_evidence_and_gaps_without_prediction(self) -> None:
        result = build_workplace_assistance(
            _request("career_review"),
            build_self_assistance_profile(_profile()),
            _policy(),
        )
        assistance = result["assistance"]
        gap_codes = {item["gapCode"] for item in assistance["evidenceGaps"]}

        self.assertEqual(
            1,
            len(assistance["evidenceByCategory"]["measurable_result"]),
        )
        self.assertEqual(
            2,
            assistance["evidenceStateCounts"]["stakeholder_confirmed"],
        )
        self.assertIn("missing_decision_owner", gap_codes)
        self.assertIn("missing_decision_date", gap_codes)
        self.assertFalse(assistance["promotionPredictionCreated"])
        self.assertFalse(result["promotionPredictionCreated"])
        self.assertEqual(
            "single_point_of_accountability_with_distributed_ownership",
            assistance["positioningModel"],
        )
        self.assertFalse(_gate_map(result)["exact_ask"]["applicable"])
        self.assertEqual(
            "AI Enablement Lead at Example Dynamics",
            assistance["careerTarget"]["targetRole"],
        )
        self.assertEqual(
            "people_leadership",
            assistance["careerTarget"]["primaryDirection"],
        )
        self.assertEqual(
            [
                "evidence-delegated-scope-01",
                "evidence-conversion-signal-01",
                "evidence-measurable-result-01",
            ],
            assistance["strongestSupportableCase"]["evidenceIds"],
        )
        self.assertIn(
            "do not establish",
            assistance["strongestSupportableCase"]["boundary"],
        )

    def test_fact_and_unverified_claims_remain_separate(self) -> None:
        request = _request("preflight")
        request["facts"].insert(
            0,
            {
                "factId": "fact-synthetic-unverified-01",
                "statement": "The user believes this may become a larger program.",
                "status": "user_provided_unverified",
                "sourceType": "user_statement",
                "category": "general",
            }
        )
        result = build_workplace_assistance(
            request,
            build_self_assistance_profile(_profile()),
            _policy(),
        )

        self.assertEqual(2, len(result["explicitFacts"]))
        self.assertEqual(1, len(result["userProvidedUnverifiedClaims"]))
        self.assertIn("source_evidence", result["evidenceBasis"])
        self.assertIn("user_provided_unverified", result["evidenceBasis"])
        layered_plan = result["assistance"]["layeredPlan"]
        self.assertNotIn(
            request["facts"][0]["statement"],
            layered_plan["leadingFacts"],
        )
        self.assertIn(
            request["facts"][0]["statement"],
            layered_plan["leadingUnverifiedClaims"],
        )
        self.assertTrue(
            any(
                item["factId"] == "fact-synthetic-unverified-01"
                and item["status"] == "user_provided_unverified"
                for item in layered_plan["leadingEvidence"]
            )
        )

    def test_non_user_evidence_requires_inspectable_references(self) -> None:
        request = _request("career_review")
        request["careerEvidence"][0].pop("proofReference")

        errors = validate_workplace_assistance_request(request, policy=_policy())

        self.assertIn(
            "career_evidence_proof_reference_missing",
            {item["code"] for item in errors},
        )
        with self.assertRaises(WorkplaceAssistanceBlockedError):
            build_workplace_assistance(
                request,
                build_self_assistance_profile(_profile()),
                _policy(),
            )

        preflight = _request("preflight")
        preflight["facts"][0].pop("sourceReference")
        errors = validate_workplace_assistance_request(
            preflight,
            policy=_policy(),
        )
        self.assertIn(
            "explicit_fact_source_reference_missing",
            {item["code"] for item in errors},
        )

    def test_confirmed_authority_cannot_rest_on_user_assertion(self) -> None:
        for state in (
            "explicitly_delegated",
            "formally_assigned",
            "peer_partnership",
            "sponsor_approved_workstream",
        ):
            with self.subTest(state=state):
                request = _request("preflight")
                request["authority"]["state"] = state
                request["authority"]["evidenceState"] = "user_asserted"

                errors = validate_workplace_assistance_request(
                    request,
                    policy=_policy(),
                )

                self.assertIn(
                    "authority_state_evidence_mismatch",
                    {item["code"] for item in errors},
                )
                with self.assertRaises(WorkplaceAssistanceBlockedError):
                    build_workplace_assistance(
                        request,
                        build_self_assistance_profile(_profile()),
                        _policy(),
                    )

    def test_confirmed_authority_requires_linked_inspectable_authority_fact(self) -> None:
        request = _request("preflight")
        request["authority"]["evidenceFactIds"] = []

        errors = validate_workplace_assistance_request(
            request,
            policy=_policy(),
        )

        self.assertIn(
            "confirmed_authority_evidence_missing",
            {item["code"] for item in errors},
        )
        with self.assertRaises(WorkplaceAssistanceBlockedError):
            build_workplace_assistance(
                request,
                build_self_assistance_profile(_profile()),
                _policy(),
            )

    def test_authority_evidence_links_must_resolve_and_be_qualified(self) -> None:
        request = _request("preflight")
        request["authority"]["evidenceFactIds"] = [
            "fact-security-partner-01",
        ]
        errors = validate_workplace_assistance_request(
            request,
            policy=_policy(),
        )
        self.assertIn(
            "authority_evidence_fact_not_qualified",
            {item["code"] for item in errors},
        )

        request["authority"]["evidenceFactIds"] = ["fact-does-not-exist"]
        errors = validate_workplace_assistance_request(
            request,
            policy=_policy(),
        )
        self.assertIn(
            "authority_evidence_fact_not_found",
            {item["code"] for item in errors},
        )

        request["authority"]["evidenceFactIds"] = [
            "fact-pilot-direction-01",
            "fact-pilot-direction-01",
        ]
        errors = validate_workplace_assistance_request(
            request,
            policy=_policy(),
        )
        self.assertIn(
            "duplicate_authority_evidence_fact_id",
            {item["code"] for item in errors},
        )

    def test_user_asserted_career_evidence_is_not_promoted_into_supportable_case(self) -> None:
        request = _request("career_review")
        request["careerEvidence"] = [
            {
                "evidenceId": "evidence-user-credential-01",
                "category": "credential_or_learning_evidence",
                "statement": "The user reports completing a synthetic leadership course.",
                "evidenceState": "user_asserted",
                "occurredAt": "2026-07-20",
                "proofReference": "User-supplied synthetic course note",
            }
        ]

        result = build_workplace_assistance(
            request,
            build_self_assistance_profile(_profile()),
            _policy(),
        )
        assistance = result["assistance"]
        strongest_case = assistance["strongestSupportableCase"]

        self.assertEqual("not_yet_supportable", strongest_case["status"])
        self.assertEqual([], strongest_case["evidenceIds"])
        self.assertEqual([], strongest_case["evidenceStates"])
        self.assertEqual(
            ["evidence-user-credential-01"],
            strongest_case["userAssertedCandidateEvidenceIds"],
        )
        self.assertIn(
            "evidence_state_unconfirmed",
            {item["gapCode"] for item in assistance["evidenceGaps"]},
        )
        self.assertIn("do not establish", strongest_case["boundary"])


class WorkplaceAssistanceGateTests(unittest.TestCase):
    def test_high_risk_planned_language_triggers_review_gates(self) -> None:
        request = _request("preflight")
        request["situation"]["context"] = "executive_brief"
        request["draftText"] = (
            "Only I can do this and everyone must go through me. "
            "This is obvious and you should already know the answer. "
            "The other lead is just trying to look good and is incompetent. "
            "I assigned the specialist because this is illegal and out of compliance. "
            "I am not sure, but I know for sure. I am better than the other team. "
            "I heard they are discussing promotion. "
            + " ".join(["detail"] * 160)
        )
        request["authority"]["state"] = "self_initiated"
        request["authority"]["evidenceState"] = "user_asserted"
        request["contributors"][0]["creditIncluded"] = False
        request["asks"] = [
            "Approve the pilot.",
            "Approve the budget.",
            "Change the ownership model.",
        ]
        request["intendedAsk"] = "Approve the pilot, budget, and ownership model."
        request["energyState"] = "rushed"

        result = build_workplace_assistance(
            request,
            build_self_assistance_profile(_profile()),
            _policy(),
        )
        gates = _gate_map(result)
        expected_review = {
            "comparative_superiority",
            "compliance_certainty",
            "condescension_risk",
            "contradictory_certainty",
            "disparagement",
            "exact_ask",
            "executive_altitude",
            "message_stacking",
            "monopoly_language",
            "motive_attribution",
            "personnel_sensitivity",
            "rushed_or_fatigued_state",
            "territorial_language",
            "unsupported_authority",
            "visible_credit",
        }

        self.assertTrue(expected_review.issubset(gates))
        for gate_id in expected_review:
            with self.subTest(gate_id=gate_id):
                self.assertEqual("review", gates[gate_id]["status"])
                self.assertTrue(gates[gate_id]["intentPreserved"])

    def test_nobody_else_can_do_this_triggers_monopoly_and_comparison(self) -> None:
        request = _request("preflight")
        request["draftText"] = "Nobody else can do this."
        result = build_workplace_assistance(
            request,
            build_self_assistance_profile(_profile()),
            _policy(),
        )
        gates = _gate_map(result)

        self.assertEqual("review", gates["monopoly_language"]["status"])
        self.assertEqual("review", gates["comparative_superiority"]["status"])

    def test_compliance_gate_passes_when_explicit_support_is_supplied(self) -> None:
        request = _request("preflight")
        request["draftText"] += " The documented control owner confirmed this is out of compliance."
        request["facts"].append(
            {
                "factId": "fact-compliance-evidence-01",
                "statement": "The control owner documented the exact unmet requirement.",
                "status": "explicit_fact",
                "sourceType": "documented_record",
                "category": "compliance_evidence",
                "sourceReference": "Synthetic control review C",
            }
        )

        result = build_workplace_assistance(
            request,
            build_self_assistance_profile(_profile()),
            _policy(),
        )
        gate = _gate_map(result)["compliance_certainty"]

        self.assertEqual("pass", gate["status"])
        self.assertIn("out of compliance", gate["matchedText"])

    def test_unsafe_actions_and_coworker_evaluation_fail_closed(self) -> None:
        request = _request("interpret")
        request["requestedActions"] = ["auto_send", "rank_coworkers"]
        request["authorization"]["coworkerEvaluationAllowed"] = True
        request["authorization"]["humanReviewRequired"] = False

        errors = validate_workplace_assistance_request(request, policy=_policy())
        codes = {item["code"] for item in errors}

        self.assertIn("disallowed_assistance_action", codes)
        self.assertIn("authorization_gate_failed", codes)
        with self.assertRaises(WorkplaceAssistanceBlockedError):
            build_workplace_assistance(
                request,
                build_self_assistance_profile(_profile()),
                _policy(),
            )

    def test_unknown_request_fields_and_user_statement_as_fact_fail_closed(self) -> None:
        request = _request("preflight")
        request["psychologicalProfile"] = {"confidence": 1}
        request["facts"][0]["sourceType"] = "user_statement"
        request["facts"][1]["statement"] = "The stakeholder is just trying to look good."
        request["decisions"] = [
            {
                "decisionId": "decision-invalid-date-01",
                "statement": "Use an invalid date to prove strict validation.",
                "owner": "the synthetic owner",
                "dueDate": "sometime later",
                "status": "confirmed",
            }
        ]

        errors = validate_workplace_assistance_request(request, policy=_policy())
        codes = {item["code"] for item in errors}

        self.assertIn("unknown_field", codes)
        self.assertIn("unverified_statement_mislabeled", codes)
        self.assertIn("motive_claim_mislabeled_as_fact", codes)
        self.assertIn("invalid_date", codes)

    def test_career_ledger_rejects_coworker_evaluation_content(self) -> None:
        request = _request("career_review")
        request["careerEvidence"][0]["statement"] = "The candidate is incompetent."

        errors = validate_workplace_assistance_request(request, policy=_policy())

        self.assertIn(
            "coworker_evaluation_content_not_allowed",
            {item["code"] for item in errors},
        )


class WorkplaceAssistanceOutputTests(unittest.TestCase):
    def test_finalize_and_write_produce_stable_hash(self) -> None:
        result = build_workplace_assistance(
            _request("preflight"),
            build_self_assistance_profile(_profile()),
            _policy(),
        )
        finalized = finalize_workplace_assistance(result)
        finalized_again = finalize_workplace_assistance(finalized)

        self.assertRegex(finalized["outputHash"], r"^sha256:[0-9a-f]{64}$")
        self.assertEqual(finalized["outputHash"], finalized_again["outputHash"])

        with tempfile.TemporaryDirectory() as temp_dir:
            output = write_workplace_assistance_result(
                result,
                Path(temp_dir) / "runtime-data",
            )
            payload = _json(output)

        self.assertEqual(finalized["outputHash"], payload["outputHash"])
        self.assertTrue(payload["privateArtifact"])

    def test_output_rejects_paths_outside_runtime_data(self) -> None:
        result = build_workplace_assistance(
            _request("preflight"),
            build_self_assistance_profile(_profile()),
            _policy(),
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            with self.assertRaises(WorkplaceAssistanceBlockedError) as blocked:
                write_workplace_assistance_result(result, Path(temp_dir) / "result.json")

        self.assertEqual(
            "private_runtime_path_required",
            blocked.exception.reasons[0]["code"],
        )


if __name__ == "__main__":
    unittest.main()

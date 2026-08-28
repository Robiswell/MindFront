"""Private workplace communication and career-effectiveness assistance.

This module is deliberately separate from recipient interaction profiles.
Recipient profiles are third-party, observation-derived, thresholded evidence.
The profile managed here is first-party, explicitly self-declared accommodation
context. It may be used immediately, but it remains private, user-controlled,
and unable to authorize sending or evaluation of another person.
"""

from __future__ import annotations

import hashlib
import json
import re
from copy import deepcopy
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from .interaction_profiles import (
    ALLOWED_CONTEXTS as ALLOWED_RECIPIENT_CONTEXTS,
    ALLOWED_PURPOSE as RECIPIENT_GUIDANCE_PURPOSE,
)
from .vault_crypto import (
    CURRENT_ENCRYPTION,
    VaultEncryptionError,
    decrypt_envelope,
    write_encrypted_payload,
)


class WorkplaceAssistanceBlockedError(Exception):
    """Raised when private assistance input or storage violates its boundary."""

    def __init__(self, reasons: list[dict[str, str]]):
        self.reasons = reasons
        super().__init__("Workplace assistance operation blocked.")


PROFILE_ARTIFACT_TYPE = "self_declared_workplace_assistance_profile"
PROFILE_PURPOSE = "autistic_workplace_communication_accommodation"
REQUEST_ARTIFACT_TYPE = "workplace_assistance_request"
REQUEST_PURPOSE = "self_workplace_communication_assistance"
POLICY_ARTIFACT_TYPE = "workplace_assistance_policy"
RESULT_ARTIFACT_TYPE = "workplace_assistance_result"
STORE_ARTIFACT_TYPE = "mindfront_private_self_assistance_profile_store"
ENCRYPTED_STORE_ARTIFACT_TYPE = "mindfront_encrypted_self_assistance_profile_store"

ALLOWED_MODES = {
    "career_review",
    "debrief",
    "interpret",
    "preflight",
}
ALLOWED_STRENGTHS = {
    "ambition",
    "decisive_action",
    "follow_through",
    "knowledge_seeking",
    "leadership_drive",
    "open_mindedness",
    "stakeholder_initiative",
    "team_advocacy",
    "technical_depth",
}
ALLOWED_COMMUNICATION_RISKS = {
    "authority_ambiguity",
    "dismissive_language",
    "fatigue_errors",
    "message_stacking",
    "motive_attribution",
    "overexplaining",
    "perceived_condescension",
    "premature_certainty",
    "spotlight_competition",
    "territorial_framing",
}
ALLOWED_LEADERSHIP_DIRECTIONS = {
    "hybrid",
    "people_leadership",
    "technical_leadership",
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
ALLOWED_AUTHORITY_STATES = {
    "explicitly_delegated",
    "formally_assigned",
    "nominated_pending_confirmation",
    "peer_partnership",
    "self_initiated",
    "sponsor_approved_workstream",
    "unknown",
}
ALLOWED_EVIDENCE_STATES = {
    "formally_decided",
    "source_supported",
    "stakeholder_confirmed",
    "user_asserted",
}
ALLOWED_FACT_STATES = {
    "explicit_fact",
    "user_provided_unverified",
}
ALLOWED_FACT_SOURCES = {
    "direct_observation",
    "direct_quote",
    "documented_record",
    "user_statement",
}
ALLOWED_FACT_CATEGORIES = {
    "authority_evidence",
    "commitment",
    "compliance_evidence",
    "decision",
    "general",
    "result_evidence",
}
ALLOWED_OWNERSHIP_TYPES = {
    "advises",
    "approves",
    "contributes",
    "coordinates",
    "owns_workstream",
    "reviews",
}
ALLOWED_DECISION_STATES = {
    "confirmed",
    "proposed",
    "unknown",
}
ALLOWED_REQUESTED_ACTIONS = {
    "debrief",
    "draft_private_response",
    "flag_risks",
    "interpret_ambiguity",
    "prepare_talking_points",
    "review_career_evidence",
}
DISALLOWED_REQUESTED_ACTIONS = {
    "auto_post",
    "auto_send",
    "diagnose_coworker",
    "evaluate_coworker",
    "impersonate",
    "infer_motive_as_fact",
    "predict_promotion",
    "rank_coworkers",
}
ALLOWED_ENERGY_STATES = {
    "fatigued",
    "overloaded",
    "rushed",
    "steady",
    "unknown",
}
ALLOWED_SUPPORT_PREFERENCE_FIELDS = {
    "alternativeInterpretationCount",
    "careerEffectivenessWeight",
    "factInferenceSeparation",
    "includeInterruptionSentence",
    "includeShortVersion",
    "layeredDetail",
}
ALLOWED_AUTHENTICITY_FIELDS = {
    "doNotImitateRecipient",
    "doNotSuppressPersonality",
    "preserveAmbition",
    "preserveDirectness",
    "preserveTeamAdvocacy",
    "preserveTechnicalPrecision",
}
ALLOWED_ENERGY_PREFERENCE_FIELDS = {
    "fatigueRequiresShortMode",
    "rushedStateRequiresPause",
}
PROFILE_RISK_GATE_MAP = {
    "authority_ambiguity": {
        "ownership_approval_boundary",
        "unsupported_authority",
    },
    "dismissive_language": {
        "comparative_superiority",
        "condescension_risk",
        "disparagement",
    },
    "fatigue_errors": {"rushed_or_fatigued_state"},
    "message_stacking": {"exact_ask", "message_stacking"},
    "motive_attribution": {"motive_attribution"},
    "overexplaining": {"executive_altitude", "message_stacking"},
    "perceived_condescension": {"condescension_risk"},
    "premature_certainty": {
        "compliance_certainty",
        "contradictory_certainty",
    },
    "spotlight_competition": {
        "comparative_superiority",
        "monopoly_language",
        "visible_credit",
    },
    "territorial_framing": {
        "monopoly_language",
        "territorial_language",
    },
}

PROFILE_ID_PATTERN = re.compile(r"self-assistance-profile-[a-z0-9][a-z0-9-]{2,80}\Z")
REQUEST_ID_PATTERN = re.compile(r"assist-request-[a-z0-9][a-z0-9-]{2,100}\Z")
EVIDENCE_ID_PATTERN = re.compile(r"(?:fact|evidence|decision|commitment|contributor)-[a-z0-9][a-z0-9-]{1,100}\Z")
SHA256_PATTERN = re.compile(r"sha256:[0-9a-f]{64}\Z")
SECRET_PATTERNS = (
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----", re.IGNORECASE),
    re.compile(
        r"\b(?:api[_ -]?key|client[_ -]?secret|password|access[_ -]?token)\s*[:=]\s*\S+",
        re.IGNORECASE,
    ),
    re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]{20,}", re.IGNORECASE),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
)
CONTROLLED_MARKER_PATTERNS = (
    re.compile(r"\bCONTROLLED UNCLASSIFIED INFORMATION\b", re.IGNORECASE),
    re.compile(r"^\s*CUI(?:\s*//\s*[A-Z0-9/_-]+)?\s*$", re.IGNORECASE | re.MULTILINE),
    re.compile(r"^\s*(?:ITAR|NOFORN)\s*$", re.IGNORECASE | re.MULTILINE),
    re.compile(r"\bEXPORT[\s-]+CONTROLLED\b", re.IGNORECASE),
)
AUTHORITY_OVERCLAIM_PATTERNS = (
    re.compile(r"\bi assigned\b", re.IGNORECASE),
    re.compile(r"\bi told (?:him|her|them|the team)\s+to\b", re.IGNORECASE),
    re.compile(r"\bi have (?:him|her|them|the team)\s+(?:doing|working on)\b", re.IGNORECASE),
    re.compile(r"\bmy team\b", re.IGNORECASE),
)
UNCERTAINTY_PATTERNS = (
    re.compile(r"\bnot sure\b", re.IGNORECASE),
    re.compile(r"\buncertain\b", re.IGNORECASE),
    re.compile(r"\bmaybe\b", re.IGNORECASE),
    re.compile(r"\bmight\b", re.IGNORECASE),
)
CERTAINTY_PATTERNS = (
    re.compile(r"\bknow for sure\b", re.IGNORECASE),
    re.compile(r"\bdefinitely\b", re.IGNORECASE),
    re.compile(r"\bcertainly\b", re.IGNORECASE),
    re.compile(r"\bwithout question\b", re.IGNORECASE),
)
MOTIVE_AS_FACT_PATTERNS = (
    re.compile(
        r"\b(?:he|she|they|the (?:candidate|coworker|colleague|manager|stakeholder)) "
        r"(?:is|are|was|were) (?:just|only) trying to\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:he|she|they|the (?:candidate|coworker|colleague|manager|stakeholder)) "
        r"(?:did|does|is doing) (?:it|this|that) (?:just|only) because\b",
        re.IGNORECASE,
    ),
)
COWORKER_EVALUATION_PATTERNS = (
    re.compile(
        r"\b(?:he|she|they|the (?:candidate|coworker|colleague|manager|stakeholder)) "
        r"(?:is|are|was|were) (?:incompetent|unqualified|lazy|clueless|bad at|worse than)\b",
        re.IGNORECASE,
    ),
    re.compile(r"\b(?:rank|ranking|performance rating) (?:the |our )?(?:candidate|coworker|colleague)s?\b", re.IGNORECASE),
    re.compile(
        r"\b(?:better|worse|more capable|less capable) than "
        r"(?:him|her|them|the (?:candidate|coworker|colleague))\b",
        re.IGNORECASE,
    ),
)


def validate_self_assistance_profile(profile: dict[str, Any]) -> list[dict[str, str]]:
    """Return strict validation errors for a first-party assistance profile."""

    errors: list[dict[str, str]] = []
    if not isinstance(profile, dict):
        return [_reason("invalid_profile", "$", "Profile must be a JSON object.")]

    _reject_diagnosis_fields(profile, "$", errors)
    _reject_unknown_fields(
        profile,
        {
            "artifactType",
            "schemaVersion",
            "profileId",
            "purpose",
            "selfDeclared",
            "userDeclaredAccommodationContext",
            "careerGoals",
            "strengths",
            "knownCommunicationRisks",
            "supportPreferences",
            "authenticityConstraints",
            "energyPreferences",
            "careerAccountabilityModel",
            "authorization",
            "createdAt",
            "updatedAt",
            "profileHash",
        },
        "$",
        errors,
    )

    if profile.get("artifactType") != PROFILE_ARTIFACT_TYPE:
        _error(errors, "invalid_artifact_type", "artifactType", f"Expected {PROFILE_ARTIFACT_TYPE}.")
    if profile.get("schemaVersion") != 1:
        _error(errors, "invalid_schema_version", "schemaVersion", "Expected schemaVersion 1.")
    if not isinstance(profile.get("profileId"), str) or not PROFILE_ID_PATTERN.fullmatch(
        profile.get("profileId", "")
    ):
        _error(
            errors,
            "invalid_profile_id",
            "profileId",
            "profileId must start with self-assistance-profile- and use lowercase letters, digits, or hyphens.",
        )
    if profile.get("purpose") != PROFILE_PURPOSE:
        _error(
            errors,
            "invalid_profile_purpose",
            "purpose",
            f"Self profiles are limited to {PROFILE_PURPOSE}.",
        )
    if profile.get("selfDeclared") is not True:
        _error(
            errors,
            "profile_not_self_declared",
            "selfDeclared",
            "Accommodation context must be explicitly self-declared.",
        )
    if profile.get("userDeclaredAccommodationContext") != "autistic_workplace_communication":
        _error(
            errors,
            "invalid_accommodation_context",
            "userDeclaredAccommodationContext",
            "The supported user-declared context is autistic_workplace_communication.",
        )

    goals = profile.get("careerGoals")
    if not isinstance(goals, dict):
        _error(errors, "missing_career_goals", "careerGoals", "careerGoals must be an object.")
    else:
        _reject_unknown_fields(
            goals,
            {
                "targetRole",
                "targetHorizon",
                "primaryDirection",
                "successDefinition",
            },
            "careerGoals",
            errors,
        )
        _require_string(goals, "targetRole", "careerGoals", errors, minimum=2, maximum=160)
        _require_string(goals, "targetHorizon", "careerGoals", errors, minimum=2, maximum=160)
        _require_string(goals, "successDefinition", "careerGoals", errors, minimum=4, maximum=1000)
        if goals.get("primaryDirection") not in ALLOWED_LEADERSHIP_DIRECTIONS:
            _error(
                errors,
                "invalid_leadership_direction",
                "careerGoals.primaryDirection",
                f"Expected one of: {', '.join(sorted(ALLOWED_LEADERSHIP_DIRECTIONS))}.",
            )

    _validate_controlled_string_list(
        profile.get("strengths"),
        path="strengths",
        allowed=ALLOWED_STRENGTHS,
        errors=errors,
        require_nonempty=True,
    )
    _validate_controlled_string_list(
        profile.get("knownCommunicationRisks"),
        path="knownCommunicationRisks",
        allowed=ALLOWED_COMMUNICATION_RISKS,
        errors=errors,
        require_nonempty=True,
    )

    preferences = profile.get("supportPreferences")
    if not isinstance(preferences, dict):
        _error(
            errors,
            "missing_support_preferences",
            "supportPreferences",
            "supportPreferences must be an object.",
        )
    else:
        _reject_unknown_fields(
            preferences,
            ALLOWED_SUPPORT_PREFERENCE_FIELDS,
            "supportPreferences",
            errors,
        )
        for field in (
            "factInferenceSeparation",
            "layeredDetail",
            "includeShortVersion",
            "includeInterruptionSentence",
        ):
            if preferences.get(field) is not True:
                _error(
                    errors,
                    "required_support_preference_disabled",
                    f"supportPreferences.{field}",
                    f"{field} must be true.",
                )
        alternatives = preferences.get("alternativeInterpretationCount")
        if not isinstance(alternatives, int) or isinstance(alternatives, bool) or not 2 <= alternatives <= 5:
            _error(
                errors,
                "invalid_alternative_count",
                "supportPreferences.alternativeInterpretationCount",
                "alternativeInterpretationCount must be an integer from 2 through 5.",
            )
        weight = preferences.get("careerEffectivenessWeight")
        if not isinstance(weight, int) or isinstance(weight, bool) or not 0 <= weight <= 100:
            _error(
                errors,
                "invalid_career_effectiveness_weight",
                "supportPreferences.careerEffectivenessWeight",
                "careerEffectivenessWeight must be an integer from 0 through 100.",
            )

    authenticity = profile.get("authenticityConstraints")
    if not isinstance(authenticity, dict):
        _error(
            errors,
            "missing_authenticity_constraints",
            "authenticityConstraints",
            "authenticityConstraints must be an object.",
        )
    else:
        _reject_unknown_fields(
            authenticity,
            ALLOWED_AUTHENTICITY_FIELDS,
            "authenticityConstraints",
            errors,
        )
        for field in sorted(ALLOWED_AUTHENTICITY_FIELDS):
            if authenticity.get(field) is not True:
                _error(
                    errors,
                    "authenticity_constraint_disabled",
                    f"authenticityConstraints.{field}",
                    f"{field} must be true.",
                )

    energy_preferences = profile.get("energyPreferences")
    if not isinstance(energy_preferences, dict):
        _error(
            errors,
            "missing_energy_preferences",
            "energyPreferences",
            "energyPreferences must be an object.",
        )
    else:
        _reject_unknown_fields(
            energy_preferences,
            ALLOWED_ENERGY_PREFERENCE_FIELDS,
            "energyPreferences",
            errors,
        )
        for field in sorted(ALLOWED_ENERGY_PREFERENCE_FIELDS):
            if not isinstance(energy_preferences.get(field), bool):
                _error(
                    errors,
                    "invalid_energy_preference",
                    f"energyPreferences.{field}",
                    f"{field} must be boolean.",
                )

    if profile.get("careerAccountabilityModel") != "single_point_of_accountability_with_distributed_ownership":
        _error(
            errors,
            "invalid_accountability_model",
            "careerAccountabilityModel",
            "Use single_point_of_accountability_with_distributed_ownership.",
        )

    _validate_authorization(profile.get("authorization"), "authorization", errors)

    for field in ("createdAt", "updatedAt"):
        if field in profile:
            _validate_datetime(profile.get(field), field, errors)
    if "profileHash" in profile:
        supplied_profile_hash = profile.get("profileHash")
        if (
            not isinstance(supplied_profile_hash, str)
            or not SHA256_PATTERN.fullmatch(supplied_profile_hash)
        ):
            _error(
                errors,
                "invalid_profile_hash",
                "profileHash",
                "profileHash must be a lowercase SHA-256 value.",
            )
        elif supplied_profile_hash != _profile_hash(profile):
            _error(
                errors,
                "profile_hash_mismatch",
                "profileHash",
                "profileHash does not match the current self-profile content.",
            )

    _scan_restricted_content(profile, errors, root="$")
    return errors


def build_self_assistance_profile(
    profile: dict[str, Any],
    *,
    existing_profile: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Normalize a valid first-party profile and add private lineage metadata."""

    errors = validate_self_assistance_profile(profile)
    if errors:
        raise WorkplaceAssistanceBlockedError(errors)
    if existing_profile is not None:
        existing_errors = validate_self_assistance_profile(existing_profile)
        if existing_errors:
            raise WorkplaceAssistanceBlockedError(existing_errors)
        if existing_profile["profileId"] != profile["profileId"]:
            raise WorkplaceAssistanceBlockedError(
                [
                    _reason(
                        "profile_id_change_not_allowed",
                        "profileId",
                        "Replacing the current self profile cannot change its profileId.",
                    )
                ]
            )

    now = _now()
    normalized = {
        key: deepcopy(value)
        for key, value in profile.items()
        if key not in {"createdAt", "updatedAt", "profileHash"}
    }
    normalized["createdAt"] = (
        existing_profile.get("createdAt", now) if existing_profile is not None else profile.get("createdAt", now)
    )
    normalized["updatedAt"] = now
    normalized["profileHash"] = _profile_hash(normalized)
    return normalized


def upsert_self_assistance_profile(
    store_path: str | Path,
    profile: dict[str, Any],
) -> dict[str, Any]:
    """Create or replace the single installation-local encrypted self profile."""

    path = require_private_runtime_path(
        Path(store_path),
        "selfProfileStore",
    )
    store = _load_self_store(path, missing_ok=True)
    existing = store.get("profile")
    normalized = build_self_assistance_profile(profile, existing_profile=existing)
    if existing is not None and existing.get("profileHash") == normalized.get("profileHash"):
        status = "unchanged"
    else:
        status = "replaced" if existing is not None else "created"
        store["profile"] = normalized
        store["updatedAt"] = _now()
        _save_self_store(path, store)
    return {
        "artifactType": "self_assistance_profile_store_result",
        "schemaVersion": 1,
        "status": status,
        "profileId": normalized["profileId"],
        "profileHash": (
            existing["profileHash"]
            if status == "unchanged"
            else normalized["profileHash"]
        ),
        "storeEncryption": CURRENT_ENCRYPTION,
        "privateArtifact": True,
        "normalHistoryEligible": False,
    }


def get_self_assistance_profile(store_path: str | Path) -> dict[str, Any]:
    """Return the current user's decrypted self profile."""

    path = require_private_runtime_path(
        Path(store_path),
        "selfProfileStore",
    )
    store = _load_self_store(path)
    profile = store.get("profile")
    if not isinstance(profile, dict):
        raise WorkplaceAssistanceBlockedError(
            [_reason("self_profile_missing", str(store_path), "The encrypted store has no self profile.")]
        )
    errors = validate_self_assistance_profile(profile)
    if errors:
        raise WorkplaceAssistanceBlockedError(errors)
    return deepcopy(profile)


def build_self_assistance_context(profile: dict[str, Any]) -> dict[str, Any]:
    """Return the bounded private context used to personalize inline assistance."""

    errors = validate_self_assistance_profile(profile)
    if errors:
        raise WorkplaceAssistanceBlockedError(errors)
    return {
        "artifactType": "self_workplace_assistance_context",
        "schemaVersion": 1,
        "profileId": profile["profileId"],
        "profileHash": profile.get("profileHash") or _profile_hash(profile),
        "careerGoals": deepcopy(profile["careerGoals"]),
        "strengthsToPreserve": deepcopy(profile["strengths"]),
        "knownCommunicationRisks": deepcopy(
            profile["knownCommunicationRisks"]
        ),
        "supportPreferences": deepcopy(profile["supportPreferences"]),
        "authenticityConstraints": deepcopy(profile["authenticityConstraints"]),
        "energyPreferences": deepcopy(profile["energyPreferences"]),
        "careerAccountabilityModel": profile["careerAccountabilityModel"],
        "humanReviewRequired": True,
        "automaticSendingAllowed": False,
        "coworkerEvaluationAllowed": False,
        "privateArtifact": True,
        "normalHistoryEligible": False,
    }


def delete_self_assistance_profile(store_path: str | Path) -> dict[str, Any]:
    """Delete the current-user self-profile store."""

    path = require_private_runtime_path(
        Path(store_path),
        "selfProfileStore",
    )
    profile = get_self_assistance_profile(path)
    try:
        path.unlink()
    except OSError as exc:
        raise WorkplaceAssistanceBlockedError(
            [_reason("self_profile_delete_failed", str(path), str(exc))]
        ) from exc
    return {
        "artifactType": "self_assistance_profile_delete_result",
        "schemaVersion": 1,
        "status": "deleted",
        "profileId": profile["profileId"],
        "storeRemoved": True,
        "privateArtifact": True,
    }


def validate_workplace_assistance_policy(policy: dict[str, Any]) -> list[dict[str, str]]:
    """Return strict validation errors for the source-owned assistance policy."""

    errors: list[dict[str, str]] = []
    if not isinstance(policy, dict):
        return [_reason("invalid_policy", "$", "Policy must be a JSON object.")]
    _reject_unknown_fields(
        policy,
        {
            "artifactType",
            "schemaVersion",
            "purpose",
            "modes",
            "scenarioContexts",
            "authorityStates",
            "careerEvidenceCategories",
            "evidenceStates",
            "languageGates",
            "thresholds",
            "hardBlockedActions",
            "requiredBoundaries",
        },
        "$",
        errors,
    )
    if policy.get("artifactType") != POLICY_ARTIFACT_TYPE:
        _error(errors, "invalid_policy_type", "artifactType", f"Expected {POLICY_ARTIFACT_TYPE}.")
    if policy.get("schemaVersion") != 1:
        _error(errors, "invalid_schema_version", "schemaVersion", "Expected schemaVersion 1.")
    if policy.get("purpose") != PROFILE_PURPOSE:
        _error(errors, "invalid_policy_purpose", "purpose", f"Expected {PROFILE_PURPOSE}.")
    _validate_exact_string_set(policy.get("modes"), ALLOWED_MODES, "modes", errors)

    contexts = policy.get("scenarioContexts")
    if not isinstance(contexts, list) or not contexts or not all(_valid_code(item) for item in contexts):
        _error(
            errors,
            "invalid_scenario_contexts",
            "scenarioContexts",
            "scenarioContexts must be a non-empty unique list of lowercase codes.",
        )
    elif len(contexts) != len(set(contexts)):
        _error(errors, "duplicate_scenario_context", "scenarioContexts", "Scenario contexts must be unique.")

    authority_states = policy.get("authorityStates")
    if not isinstance(authority_states, dict):
        _error(errors, "invalid_authority_states", "authorityStates", "authorityStates must be an object.")
    else:
        if set(authority_states) != ALLOWED_AUTHORITY_STATES:
            _error(
                errors,
                "authority_state_set_mismatch",
                "authorityStates",
                "authorityStates must define the complete supported authority-state set.",
            )
        for state, record in authority_states.items():
            path = f"authorityStates.{state}"
            if not isinstance(record, dict):
                _error(errors, "invalid_authority_state", path, "Authority state must be an object.")
                continue
            _reject_unknown_fields(record, {"claimLevel", "recommendedVerb"}, path, errors)
            _require_string(record, "claimLevel", path, errors, minimum=2, maximum=80)
            _require_string(record, "recommendedVerb", path, errors, minimum=2, maximum=80)

    categories = policy.get("careerEvidenceCategories")
    if not isinstance(categories, list) or not categories or not all(_valid_code(item) for item in categories):
        _error(
            errors,
            "invalid_career_categories",
            "careerEvidenceCategories",
            "careerEvidenceCategories must be a non-empty unique list of lowercase codes.",
        )
    elif len(categories) != len(set(categories)):
        _error(
            errors,
            "duplicate_career_category",
            "careerEvidenceCategories",
            "Career evidence categories must be unique.",
        )

    _validate_exact_string_set(policy.get("evidenceStates"), ALLOWED_EVIDENCE_STATES, "evidenceStates", errors)
    _validate_exact_string_set(
        policy.get("hardBlockedActions"),
        DISALLOWED_REQUESTED_ACTIONS,
        "hardBlockedActions",
        errors,
    )

    gates = policy.get("languageGates")
    if not isinstance(gates, list) or not gates:
        _error(errors, "missing_language_gates", "languageGates", "At least one language gate is required.")
    else:
        gate_ids: set[str] = set()
        for index, gate in enumerate(gates):
            path = f"languageGates[{index}]"
            if not isinstance(gate, dict):
                _error(errors, "invalid_language_gate", path, "Language gate must be an object.")
                continue
            _reject_unknown_fields(
                gate,
                {
                    "gateId",
                    "label",
                    "severity",
                    "patterns",
                    "explanation",
                    "recommendedAdjustment",
                },
                path,
                errors,
            )
            gate_id = gate.get("gateId")
            if not _valid_code(gate_id):
                _error(errors, "invalid_gate_id", f"{path}.gateId", "gateId must be a lowercase code.")
            elif gate_id in gate_ids:
                _error(errors, "duplicate_gate_id", f"{path}.gateId", "gateId must be unique.")
            else:
                gate_ids.add(gate_id)
            for field in ("label", "explanation", "recommendedAdjustment"):
                _require_string(gate, field, path, errors, minimum=4, maximum=1000)
            if gate.get("severity") != "review":
                _error(
                    errors,
                    "invalid_gate_severity",
                    f"{path}.severity",
                    "Language gates are review aids and must use severity review.",
                )
            patterns = gate.get("patterns")
            if not isinstance(patterns, list) or not patterns:
                _error(errors, "missing_gate_patterns", f"{path}.patterns", "patterns must be non-empty.")
            else:
                for pattern_index, pattern in enumerate(patterns):
                    if not isinstance(pattern, str) or not pattern:
                        _error(
                            errors,
                            "invalid_gate_pattern",
                            f"{path}.patterns[{pattern_index}]",
                            "Pattern must be a non-empty regular expression.",
                        )
                        continue
                    try:
                        re.compile(pattern, re.IGNORECASE)
                    except re.error as exc:
                        _error(
                            errors,
                            "invalid_gate_pattern",
                            f"{path}.patterns[{pattern_index}]",
                            str(exc),
                        )

    thresholds = policy.get("thresholds")
    if not isinstance(thresholds, dict):
        _error(errors, "missing_thresholds", "thresholds", "thresholds must be an object.")
    else:
        expected_thresholds = {
            "maxAsksBeforeStacking",
            "maxExactAskWords",
            "maxExecutiveDraftWords",
            "maxShortVersionWords",
        }
        _reject_unknown_fields(thresholds, expected_thresholds, "thresholds", errors)
        for field in sorted(expected_thresholds):
            value = thresholds.get(field)
            if not isinstance(value, int) or isinstance(value, bool) or value < 1:
                _error(
                    errors,
                    "invalid_threshold",
                    f"thresholds.{field}",
                    f"{field} must be a positive integer.",
                )

    boundaries = policy.get("requiredBoundaries")
    if not isinstance(boundaries, dict):
        _error(
            errors,
            "missing_required_boundaries",
            "requiredBoundaries",
            "requiredBoundaries must be an object.",
        )
    else:
        expected = {
            "automaticSendingAllowed": False,
            "coworkerEvaluationAllowed": False,
            "humanReviewRequired": True,
            "promotionPredictionCreated": False,
        }
        _reject_unknown_fields(boundaries, set(expected), "requiredBoundaries", errors)
        for field, required in expected.items():
            if boundaries.get(field) is not required:
                _error(
                    errors,
                    "unsafe_policy_boundary",
                    f"requiredBoundaries.{field}",
                    f"{field} must be {str(required).lower()}.",
                )
    return errors


def load_workplace_assistance_policy(path: str | Path) -> dict[str, Any]:
    """Load and validate the source-owned workplace-assistance policy."""

    source = Path(path)
    try:
        policy = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise WorkplaceAssistanceBlockedError(
            [_reason("policy_unreadable", str(source), str(exc))]
        ) from exc
    errors = validate_workplace_assistance_policy(policy)
    if errors:
        raise WorkplaceAssistanceBlockedError(errors)
    return policy


def validate_workplace_assistance_request(
    request: dict[str, Any],
    *,
    policy: dict[str, Any] | None = None,
) -> list[dict[str, str]]:
    """Return strict mode-aware validation errors for one private request."""

    errors: list[dict[str, str]] = []
    if not isinstance(request, dict):
        return [_reason("invalid_request", "$", "Request must be a JSON object.")]
    if policy is not None:
        errors.extend(validate_workplace_assistance_policy(policy))

    _reject_unknown_fields(
        request,
        {
            "artifactType",
            "schemaVersion",
            "requestId",
            "mode",
            "createdAt",
            "purpose",
            "situation",
            "facts",
            "draftText",
            "incomingText",
            "intendedAsk",
            "asks",
            "recommendation",
            "authority",
            "contributors",
            "decisions",
            "commitments",
            "unresolvedItems",
            "careerEvidence",
            "energyState",
            "requestedActions",
            "authorization",
        },
        "$",
        errors,
    )
    if request.get("artifactType") != REQUEST_ARTIFACT_TYPE:
        _error(errors, "invalid_artifact_type", "artifactType", f"Expected {REQUEST_ARTIFACT_TYPE}.")
    if request.get("schemaVersion") != 1:
        _error(errors, "invalid_schema_version", "schemaVersion", "Expected schemaVersion 1.")
    if not isinstance(request.get("requestId"), str) or not REQUEST_ID_PATTERN.fullmatch(
        request.get("requestId", "")
    ):
        _error(
            errors,
            "invalid_request_id",
            "requestId",
            "requestId must start with assist-request- and use lowercase letters, digits, or hyphens.",
        )
    mode = request.get("mode")
    if mode not in ALLOWED_MODES:
        _error(errors, "invalid_assistance_mode", "mode", f"Expected one of: {', '.join(sorted(ALLOWED_MODES))}.")
    if request.get("purpose") != REQUEST_PURPOSE:
        _error(errors, "invalid_request_purpose", "purpose", f"Expected {REQUEST_PURPOSE}.")
    _validate_datetime(request.get("createdAt"), "createdAt", errors)
    _validate_situation(request.get("situation"), policy, errors)
    _validate_fact_records(request.get("facts", []), errors)
    _validate_optional_text(request, "draftText", errors, maximum=30000)
    _validate_optional_text(request, "incomingText", errors, maximum=30000)
    _validate_optional_text(request, "intendedAsk", errors, maximum=3000)
    _validate_optional_text(request, "recommendation", errors, maximum=5000)
    _validate_string_list(request.get("asks", []), "asks", errors, maximum_items=20, maximum_length=2000)
    _validate_authority(
        request.get("authority"),
        request.get("facts", []),
        errors,
    )
    _validate_contributors(request.get("contributors", []), errors)
    _validate_decisions(request.get("decisions", []), errors)
    _validate_commitments(request.get("commitments", []), errors)
    _validate_string_list(
        request.get("unresolvedItems", []),
        "unresolvedItems",
        errors,
        maximum_items=50,
        maximum_length=3000,
    )
    _validate_career_evidence(request.get("careerEvidence", []), policy, errors)
    if request.get("energyState") not in ALLOWED_ENERGY_STATES:
        _error(
            errors,
            "invalid_energy_state",
            "energyState",
            f"Expected one of: {', '.join(sorted(ALLOWED_ENERGY_STATES))}.",
        )
    _validate_requested_actions(request.get("requestedActions"), policy, errors)
    _validate_authorization(request.get("authorization"), "authorization", errors)

    if mode == "preflight" and not (
        _nonempty(request.get("intendedAsk")) or request.get("asks")
    ):
        _error(
            errors,
            "preflight_ask_missing",
            "intendedAsk",
            "Preflight requires intendedAsk or at least one asks entry.",
        )
    if mode == "interpret" and not _nonempty(request.get("incomingText")):
        _error(errors, "interpret_text_missing", "incomingText", "Interpret mode requires incomingText.")
    if mode == "debrief" and not (
        request.get("facts")
        or request.get("decisions")
        or request.get("commitments")
        or request.get("unresolvedItems")
    ):
        _error(
            errors,
            "debrief_evidence_missing",
            "facts",
            "Debrief requires facts, decisions, commitments, or unresolvedItems.",
        )
    if mode == "career_review" and not request.get("careerEvidence"):
        _error(
            errors,
            "career_evidence_missing",
            "careerEvidence",
            "Career review requires at least one careerEvidence item.",
        )

    _scan_restricted_content(request, errors, root="$")
    return errors


def build_workplace_assistance(
    request: dict[str, Any],
    self_profile: dict[str, Any],
    policy: dict[str, Any],
    *,
    recipient_guidance: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build one deterministic private workplace-assistance result."""

    policy_errors = validate_workplace_assistance_policy(policy)
    profile_errors = validate_self_assistance_profile(self_profile)
    request_errors = validate_workplace_assistance_request(request, policy=policy)
    errors = [*policy_errors, *profile_errors, *request_errors]
    if errors:
        raise WorkplaceAssistanceBlockedError(_deduplicate_reasons(errors))

    if recipient_guidance is not None:
        _validate_recipient_guidance(recipient_guidance)

    explicit_facts = [
        deepcopy(item) for item in request.get("facts", []) if item["status"] == "explicit_fact"
    ]
    unverified_claims = [
        deepcopy(item)
        for item in request.get("facts", [])
        if item["status"] == "user_provided_unverified"
    ]
    gates = _evaluate_gates(request, policy)
    mode = request["mode"]
    if mode == "preflight":
        assistance = _build_preflight(request, self_profile, policy, gates)
    elif mode == "interpret":
        assistance = _build_interpretation(request, self_profile)
    elif mode == "debrief":
        assistance = _build_debrief(request, self_profile)
    else:
        assistance = _build_career_review(request, self_profile, policy)
    assistance["authorityBasis"] = _authority_basis(request["authority"])
    assistance["recipientGuidance"] = _recipient_guidance_application(
        recipient_guidance
    )

    inferences = assistance.pop("boundedInferences", [])
    unknowns = _unique_strings(
        [
            *_common_unknowns(request),
            *assistance.pop("unknowns", []),
        ]
    )
    clarifying_question = assistance.pop("clarifyingQuestion", None)
    profile_hash = _profile_hash(self_profile)
    policy_hash = _payload_hash(policy)
    result_seed = json.dumps(
        {
            "request": request,
            "profileHash": profile_hash,
            "policyHash": policy_hash,
            "recipientProfileHash": (
                recipient_guidance.get("profileHash") if recipient_guidance is not None else None
            ),
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    evidence_basis = {"heuristic_inference"}
    if explicit_facts:
        evidence_basis.add("source_evidence")
    if unverified_claims:
        evidence_basis.add("user_provided_unverified")

    result = {
        "artifactType": RESULT_ARTIFACT_TYPE,
        "schemaVersion": 1,
        "resultId": f"workplace-assistance-{hashlib.sha256(result_seed.encode('utf-8')).hexdigest()[:16]}",
        "requestId": request["requestId"],
        "mode": mode,
        "generatedAt": _now(),
        "selfProfileHash": profile_hash,
        "policyHash": policy_hash,
        "recipientAssistance": _recipient_assistance_summary(recipient_guidance),
        "evidenceBasis": sorted(evidence_basis),
        "explicitFacts": explicit_facts,
        "userProvidedUnverifiedClaims": unverified_claims,
        "boundedInferences": inferences,
        "unknowns": unknowns,
        "clarifyingQuestion": clarifying_question,
        "gates": gates,
        "assistance": assistance,
        "strengthsPreserved": list(self_profile["strengths"]),
        "authenticity": {
            "minimalIntervention": True,
            "voiceConstraintsApplied": deepcopy(self_profile["authenticityConstraints"]),
            "maskingOrPersonalitySuppressionAllowed": False,
            "recipientImitationAllowed": False,
        },
        "humanReviewRequired": True,
        "automaticSendingAllowed": False,
        "coworkerEvaluationAllowed": False,
        "promotionPredictionCreated": False,
        "diagnosisCreated": False,
        "marketEvidenceCreated": False,
        "privateArtifact": True,
        "normalHistoryEligible": False,
        "evidenceBoundary": (
            "This private output separates supplied facts from bounded interpretations. "
            "It does not establish coworker motives, psychological truth, guaranteed social outcomes, "
            "promotion readiness, sponsor commitment, or workplace-policy compliance."
        ),
        "outputHash": "sha256:pending",
    }
    return result


def finalize_workplace_assistance(result: dict[str, Any]) -> dict[str, Any]:
    """Return a deep-copied result with a deterministic output hash."""

    finalized = deepcopy(result)
    finalized["outputHash"] = _payload_hash(finalized, omit={"outputHash"})
    return finalized


def write_workplace_assistance_result(
    result: dict[str, Any],
    output_path: str | Path,
) -> Path:
    """Write a finalized private result to a caller-selected private path."""

    destination = require_private_runtime_path(
        Path(output_path),
        "workplaceAssistanceOutput",
    )
    if destination.suffix.lower() != ".json":
        destination.mkdir(parents=True, exist_ok=True)
        destination = destination / "workplace-assistance-result.json"
    else:
        destination.parent.mkdir(parents=True, exist_ok=True)
    finalized = finalize_workplace_assistance(result)
    destination.write_text(
        json.dumps(finalized, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return destination


def _build_preflight(
    request: dict[str, Any],
    self_profile: dict[str, Any],
    policy: dict[str, Any],
    gates: list[dict[str, Any]],
) -> dict[str, Any]:
    facts = request.get("facts", [])
    explicit_facts = [
        item for item in facts if item["status"] == "explicit_fact"
    ]
    unverified_claims = [
        item for item in facts if item["status"] == "user_provided_unverified"
    ]
    leading_evidence = [*explicit_facts, *unverified_claims][:3]
    fact_statements = [
        item["statement"]
        for item in leading_evidence
        if item["status"] == "explicit_fact"
    ]
    unverified_statements = [
        item["statement"]
        for item in leading_evidence
        if item["status"] == "user_provided_unverified"
    ]
    ask = _exact_ask(request)
    desired_outcome = request["situation"].get("desiredOutcome", "")
    recommendation = request.get("recommendation") or desired_outcome or "Confirm the next useful step."
    authority_line = _authority_line(request.get("authority", {}))
    credit_line = _credit_line(request.get("contributors", []))
    short_parts = [
        part
        for part in (
            recommendation,
            credit_line if request.get("contributors") else "",
            ask,
        )
        if _nonempty(part)
    ]
    short_version = _truncate_words(
        " ".join(short_parts),
        policy["thresholds"]["maxShortVersionWords"],
    )
    interruption_sentence = _truncate_words(
        f"Bottom line: {ask or recommendation}",
        policy["thresholds"]["maxShortVersionWords"],
    )
    inferences = [
        _inference(
            "The proposed structure may reduce first-pass ambiguity by separating the outcome, evidence, "
            "ownership, credit, and ask.",
            "layered_preflight_structure",
        )
    ]
    review_gates = [gate["gateId"] for gate in gates if gate["status"] == "review"]
    prioritized_review_gates = _prioritize_profile_risk_gates(
        gates,
        self_profile["knownCommunicationRisks"],
    )
    first_review_gate = next(
        (
            gate
            for gate_id in prioritized_review_gates
            for gate in gates
            if gate["gateId"] == gate_id
        ),
        None,
    )
    energy_state = request.get("energyState")
    short_mode = (
        energy_state in {"fatigued", "overloaded"}
        and self_profile["energyPreferences"]["fatigueRequiresShortMode"]
    )
    pause_before_use = (
        energy_state == "rushed"
        and self_profile["energyPreferences"]["rushedStateRequiresPause"]
    )
    career_weight = self_profile["supportPreferences"]["careerEffectivenessWeight"]
    if career_weight >= 67:
        optimization_priority = "career_effectiveness_first"
    elif career_weight <= 33:
        optimization_priority = "social_load_reduction_first"
    else:
        optimization_priority = "balanced"

    if pause_before_use:
        smallest_next_action = (
            "Pause before using the wording, then verify the primary ask, authority, "
            "names, and visible credit."
        )
    elif short_mode:
        smallest_next_action = (
            "Use only the short version for the first pass, then add detail if requested."
        )
    elif first_review_gate is not None:
        smallest_next_action = (
            f"Resolve {first_review_gate['gateId']}: "
            f"{first_review_gate['recommendedAdjustment']}"
        )
    elif optimization_priority == "career_effectiveness_first":
        smallest_next_action = (
            "Use the outcome-first short version, then add evidence only if requested."
        )
    else:
        smallest_next_action = "Use the short version, then add detail only if requested."

    return {
        "layeredPlan": {
            "desiredOutcome": desired_outcome or None,
            "exactAsk": ask or None,
            "leadingFacts": fact_statements,
            "leadingUnverifiedClaims": unverified_statements,
            "leadingEvidence": deepcopy(leading_evidence),
            "recommendation": recommendation,
            "authorityAndApproval": authority_line,
            "visibleCredit": credit_line,
            "nextStep": ask or "Confirm the owner, timing, and decision needed.",
        },
        "timeBoxPlan": _time_box_plan(
            request["situation"].get("durationMinutes")
        ),
        "supportProfileApplied": {
            "careerEffectivenessWeight": self_profile["supportPreferences"][
                "careerEffectivenessWeight"
            ],
            "optimizationPriority": optimization_priority,
            "layeredDetail": self_profile["supportPreferences"]["layeredDetail"],
            "preserveDirectness": self_profile["authenticityConstraints"][
                "preserveDirectness"
            ],
            "focusedRiskGateIds": prioritized_review_gates,
            "energyProtectionApplied": {
                "reportedState": energy_state,
                "shortMode": short_mode,
                "pauseBeforeUse": pause_before_use,
            },
        },
        "shortVersion": short_version,
        "interruptionSafeSentence": interruption_sentence,
        "reviewGateIds": review_gates,
        "smallestNextAction": smallest_next_action,
        "boundedInferences": inferences,
        "unknowns": _preflight_unknowns(request),
        "clarifyingQuestion": (
            "What single decision or action should the other person take after this conversation?"
            if not ask
            else "Who has final approval, and what date should be stated?"
        ),
    }


def _build_interpretation(
    request: dict[str, Any],
    self_profile: dict[str, Any],
) -> dict[str, Any]:
    count = self_profile["supportPreferences"]["alternativeInterpretationCount"]
    interpretations = _interpretations_for_text(request["incomingText"], count=count)
    return {
        "plausibleInterpretations": interpretations,
        "smallestSafeResponse": (
            "I want to make sure I answer the right question. Are you looking for a decision, "
            "an owner and timing, or a brief status update?"
        ),
        "riskIfWrong": (
            "Treating one interpretation as fact could create an unnecessary defensive response "
            "or leave the actual request unanswered."
        ),
        "boundedInferences": deepcopy(interpretations),
        "unknowns": [
            "The sender's internal motive and emotional state are unknown.",
            "Whether this message changes decision rights or approval status is unknown.",
            "The intended urgency is unknown unless it was stated directly.",
        ],
        "clarifyingQuestion": (
            "Could you confirm whether you want a decision, an owner and timing, or just a status update?"
        ),
    }


def _build_debrief(
    request: dict[str, Any],
    self_profile: dict[str, Any],
) -> dict[str, Any]:
    decisions = deepcopy(request.get("decisions", []))
    commitments = deepcopy(request.get("commitments", []))
    owners_and_dates = []
    unresolved = list(request.get("unresolvedItems", []))
    for record in [*decisions, *commitments]:
        owner = record.get("owner")
        due_date = record.get("dueDate")
        owners_and_dates.append(
            {
                "sourceId": record.get("decisionId") or record.get("commitmentId"),
                "owner": owner or None,
                "dueDate": due_date or None,
            }
        )
        if not owner:
            unresolved.append(f"Owner is not confirmed for: {record['statement']}")
        if not due_date:
            unresolved.append(f"Date is not confirmed for: {record['statement']}")
    interpretations = _interpretations_for_text(
        request.get("incomingText", ""),
        count=self_profile["supportPreferences"]["alternativeInterpretationCount"],
    )
    next_action = (
        "Send a short confirmation of the decision, owner, date, and unresolved item."
        if decisions or commitments
        else "Ask for the decision, owner, and date before recording the outcome."
    )
    return {
        "decisions": decisions,
        "commitments": commitments,
        "ownersAndDates": owners_and_dates,
        "unresolvedItems": _unique_strings(unresolved),
        "plausibleInterpretations": interpretations,
        "smallestNextAction": next_action,
        "boundedInferences": deepcopy(interpretations),
        "unknowns": unresolved,
        "clarifyingQuestion": "Can we confirm the owner and date for each commitment before I send the recap?",
    }


def _build_career_review(
    request: dict[str, Any],
    self_profile: dict[str, Any],
    policy: dict[str, Any],
) -> dict[str, Any]:
    evidence = deepcopy(request.get("careerEvidence", []))
    by_category = {
        category: [item for item in evidence if item["category"] == category]
        for category in policy["careerEvidenceCategories"]
    }
    by_state = {
        state: sum(1 for item in evidence if item["evidenceState"] == state)
        for state in policy["evidenceStates"]
    }
    gaps: list[dict[str, str]] = []
    for item in evidence:
        gaps.extend(_career_item_gaps(item))
    priority_order = {
        "title_or_conversion_signal": 0,
        "decision_right": 1,
        "sponsor_confirmation": 2,
        "adoption_or_reuse": 3,
        "delegated_scope": 4,
    }
    gaps.sort(
        key=lambda item: (
            priority_order.get(item["category"], 10),
            item["evidenceId"],
            item["gapCode"],
        )
    )
    if gaps:
        next_move = (
            f"Close {gaps[0]['gapCode']} for {gaps[0]['evidenceId']}: "
            f"{gaps[0]['recommendedAction']}"
        )
        clarifying = (
            f"What is the smallest source or stakeholder confirmation that would close "
            f"{gaps[0]['gapCode']} for {gaps[0]['evidenceId']}?"
        )
    else:
        next_move = "Package the confirmed evidence into a concise scope, outcomes, and decision-rights discussion."
        clarifying = "Who owns the next formal role or scope decision, and when will it be made?"
    strongest_states = [
        state
        for state in ("formally_decided", "stakeholder_confirmed", "source_supported")
        if by_state.get(state, 0)
    ]
    evidence_rank = {
        "formally_decided": 4,
        "stakeholder_confirmed": 3,
        "source_supported": 2,
        "user_asserted": 1,
    }
    supportable_evidence = [
        item
        for item in evidence
        if item["evidenceState"]
        in {"source_supported", "stakeholder_confirmed", "formally_decided"}
    ]
    strongest_evidence = sorted(
        supportable_evidence,
        key=lambda item: (
            -evidence_rank[item["evidenceState"]],
            item["category"],
            item["evidenceId"],
        ),
    )[:3]
    user_asserted_candidates = sorted(
        (
            item
            for item in evidence
            if item["evidenceState"] == "user_asserted"
        ),
        key=lambda item: item["evidenceId"],
    )
    inferences = [
        _inference(
            (
                "The strongest current evidence is in: " + ", ".join(strongest_states)
                if strongest_states
                else "The current ledger is user-asserted and needs source or stakeholder confirmation."
            ),
            "career_evidence_strength",
        )
    ]
    return {
        "careerTarget": deepcopy(self_profile["careerGoals"]),
        "evidenceByCategory": by_category,
        "evidenceStateCounts": by_state,
        "evidenceGaps": gaps,
        "strongestSupportableCase": {
            "status": "supported" if strongest_evidence else "not_yet_supportable",
            "evidenceIds": [item["evidenceId"] for item in strongest_evidence],
            "evidenceStates": _unique_strings(
                [item["evidenceState"] for item in strongest_evidence]
            ),
            "categories": _unique_strings(
                [item["category"] for item in strongest_evidence]
            ),
            "statements": [item["statement"] for item in strongest_evidence],
            "evidenceRecords": deepcopy(strongest_evidence),
            "userAssertedCandidateEvidenceIds": [
                item["evidenceId"] for item in user_asserted_candidates
            ],
            "boundary": (
                (
                    "These source-supported or confirmed records support a scope-and-outcomes "
                    "discussion. They do not establish a promotion, conversion, title, or "
                    "decision that has not been formally made."
                )
                if strongest_evidence
                else (
                    "No source-supported or confirmed record currently forms a supportable case. "
                    "User assertions identify what to verify; they do not establish a promotion, "
                    "conversion, title, scope, or decision."
                )
            ),
        },
        "positioningModel": "single_point_of_accountability_with_distributed_ownership",
        "positioningGuidance": (
            "Frame leadership as accountable coordination that creates visible domain ownership, "
            "repeatable systems, teammate capability, and sponsor-confirmed outcomes."
        ),
        "smallestNextAction": next_move,
        "promotionPredictionCreated": False,
        "boundedInferences": inferences,
        "unknowns": [item["description"] for item in gaps],
        "clarifyingQuestion": clarifying,
    }


def _evaluate_gates(
    request: dict[str, Any],
    policy: dict[str, Any],
) -> list[dict[str, Any]]:
    planned_text = "\n".join(
        value
        for value in (
            request.get("draftText", ""),
            request.get("intendedAsk", ""),
            request.get("recommendation", ""),
            *request.get("asks", []),
        )
        if _nonempty(value)
    )
    explicit_fact_categories = {
        item.get("category")
        for item in request.get("facts", [])
        if item.get("status") == "explicit_fact"
    }
    gates: list[dict[str, Any]] = []
    for configured in policy["languageGates"]:
        matches = _pattern_matches(planned_text, configured["patterns"])
        status = "review" if matches else "pass"
        if configured["gateId"] == "compliance_certainty" and "compliance_evidence" in explicit_fact_categories:
            status = "pass"
        gates.append(
            _gate(
                configured["gateId"],
                status,
                configured["explanation"],
                configured["recommendedAdjustment"],
                matched_text=matches,
            )
        )

    authority = request.get("authority", {})
    authority_state = authority.get("state", "unknown")
    authority_matches = [
        match.group(0)
        for pattern in AUTHORITY_OVERCLAIM_PATTERNS
        if (match := pattern.search(planned_text)) is not None
    ]
    unsupported_states = {
        "nominated_pending_confirmation",
        "peer_partnership",
        "self_initiated",
        "unknown",
    }
    authority_review = bool(authority_matches and authority_state in unsupported_states)
    gates.append(
        _gate(
            "unsupported_authority",
            "review" if authority_review else "pass",
            "Ownership wording may exceed the authority basis supplied in the request.",
            "Use propose, coordinate, partner, or support unless formal or delegated ownership is recorded.",
            matched_text=authority_matches,
        )
    )

    domain_owners = authority.get("domainOwners", [])
    final_approval_owner = authority.get("finalApprovalOwner")
    role_boundary_review = authority_state == "peer_partnership" and (
        not authority.get("deliveryOwner")
        or not domain_owners
        or not _nonempty(final_approval_owner)
    )
    gates.append(
        _gate(
            "ownership_approval_boundary",
            "review" if role_boundary_review else "pass",
            "Delivery ownership, specialist domain ownership, and final approval must remain distinct.",
            "Name the delivery coordinator, each domain owner, and the final approval owner.",
        )
    )

    contributors = request.get("contributors", [])
    omitted_credit = [
        item["contributorId"] for item in contributors if item.get("creditIncluded") is not True
    ]
    gates.append(
        _gate(
            "visible_credit",
            "review" if omitted_credit else "pass",
            "Contributor ownership or credit is not yet explicit.",
            "Name the teammate's workstream or contribution without reducing your own coordination role.",
            matched_text=omitted_credit,
        )
    )

    uncertain = any(pattern.search(planned_text) for pattern in UNCERTAINTY_PATTERNS)
    certain = any(pattern.search(planned_text) for pattern in CERTAINTY_PATTERNS)
    gates.append(
        _gate(
            "contradictory_certainty",
            "review" if uncertain and certain else "pass",
            "The wording combines uncertainty with absolute certainty.",
            "State what is known, what is uncertain, and what evidence will resolve it.",
        )
    )

    ask_count = len(request.get("asks", []))
    if ask_count == 0:
        ask_count = planned_text.count("?")
    ask_gate_applicable = request.get("mode") == "preflight"
    gates.append(
        _gate(
            "message_stacking",
            (
                "review"
                if ask_gate_applicable
                and ask_count > policy["thresholds"]["maxAsksBeforeStacking"]
                else "pass"
            ),
            "Multiple asks may obscure the decision or action that matters most.",
            "Lead with one primary ask and move secondary items into a follow-up list.",
            observed_value=str(ask_count),
            applicable=ask_gate_applicable,
        )
    )

    ask = _exact_ask(request)
    ask_words = len(_words(ask))
    exact_ask_review = ask_gate_applicable and (
        not ask
        or ask_count > 1
        or ask_words > policy["thresholds"]["maxExactAskWords"]
    )
    gates.append(
        _gate(
            "exact_ask",
            "review" if exact_ask_review else "pass",
            "The primary requested decision or action is missing, multiplied, or too long.",
            "Reduce the request to one decision or action with an owner or timing cue.",
            observed_value=str(ask_words),
            applicable=ask_gate_applicable,
        )
    )

    energy = request.get("energyState")
    gates.append(
        _gate(
            "rushed_or_fatigued_state",
            "review" if energy in {"rushed", "fatigued", "overloaded"} else "pass",
            "The user explicitly reported an energy state associated with avoidable communication errors.",
            "Use the short version, pause before sending, and verify the ask, authority, and names.",
            observed_value=str(energy),
        )
    )

    scenario = request.get("situation", {}).get("context")
    draft_words = len(_words(request.get("draftText", "")))
    executive_review = scenario == "executive_brief" and (
        draft_words > policy["thresholds"]["maxExecutiveDraftWords"] or not ask
    )
    gates.append(
        _gate(
            "executive_altitude",
            "review" if executive_review else "pass",
            "An executive interaction may be carrying more detail than the opening can support.",
            "Lead with the outcome, evidence, recommendation, and ask; keep implementation detail as a second layer.",
            observed_value=str(draft_words),
        )
    )
    return gates


def _career_item_gaps(item: dict[str, Any]) -> list[dict[str, str]]:
    gaps: list[dict[str, str]] = []

    def add(code: str, description: str, action: str) -> None:
        gaps.append(
            {
                "evidenceId": item["evidenceId"],
                "category": item["category"],
                "gapCode": code,
                "description": description,
                "recommendedAction": action,
            }
        )

    if not item.get("occurredAt"):
        add("missing_date", f"{item['evidenceId']} has no occurrence date.", "Record the exact date or bounded period.")
    if item["evidenceState"] == "user_asserted" and not item.get("proofReference"):
        add(
            "missing_proof",
            f"{item['evidenceId']} is user-asserted without an inspectable source.",
            "Link or identify the message, artifact, metric source, or stakeholder confirmation.",
        )
    if item["evidenceState"] == "user_asserted":
        add(
            "evidence_state_unconfirmed",
            f"{item['evidenceId']} remains a user assertion even if a candidate reference is supplied.",
            "Verify the source or obtain stakeholder confirmation, then update the evidence state.",
        )
    category = item["category"]
    if category == "measurable_result" and not item.get("metric"):
        add(
            "missing_metric",
            f"{item['evidenceId']} describes a result without a metric.",
            "Add a sourced count, rate, time reduction, quality measure, or bounded before-and-after result.",
        )
    if category in {"delegated_scope", "decision_right"} and item["evidenceState"] == "user_asserted":
        add(
            "missing_authority_confirmation",
            f"{item['evidenceId']} does not yet prove delegated scope or a decision right.",
            "Obtain written confirmation from the person authorized to delegate the scope.",
        )
    if category == "sponsor_confirmation" and (
        not item.get("sponsorRole")
        or item["evidenceState"] not in {"stakeholder_confirmed", "formally_decided"}
    ):
        add(
            "missing_sponsor_confirmation",
            f"{item['evidenceId']} lacks a named sponsor role or confirmed sponsor evidence.",
            "Record the sponsor's role and the exact scope or outcome they confirmed.",
        )
    if category == "adoption_or_reuse" and not item.get("adoptionScope"):
        add(
            "missing_adoption_scope",
            f"{item['evidenceId']} does not show who adopted or reused the work.",
            "Record the team, workflow, system, or repeat use that demonstrates adoption.",
        )
    if category == "teammate_enablement" and not item.get("teammateRole"):
        add(
            "missing_teammate_role",
            f"{item['evidenceId']} does not identify the enabled role.",
            "Record the teammate role, owned workstream, and observable capability gained.",
        )
    if category == "title_or_conversion_signal":
        if not item.get("decisionOwner"):
            add(
                "missing_decision_owner",
                f"{item['evidenceId']} has no formal conversion or title decision owner.",
                "Identify who can approve the employment or title decision.",
            )
        if not item.get("effectiveDate"):
            add(
                "missing_decision_date",
                f"{item['evidenceId']} has no decision or effective date.",
                "Ask for the decision milestone and the date it must occur.",
            )
    return gaps


def _interpretations_for_text(text: str, *, count: int) -> list[dict[str, Any]]:
    lowered = text.casefold()
    if any(
        term in lowered
        for term in (
            "keep this small",
            "keep it small",
            "before it goes wider",
            "before going wider",
            "bounded pilot",
            "limited pilot",
        )
    ):
        candidates = [
            "The sender may be offering conditional support for a bounded first step while withholding support for a broader rollout.",
            "The sender may want the scope and owners made explicit before considering expansion.",
            "The message may be setting a sequencing condition rather than rejecting the work.",
            "The sender may expect a small pilot result before another decision is made.",
            "The sender may be asking for risk containment and accountability, not less ambition.",
        ]
    elif any(term in lowered for term in ("who", "when", "clarify", "owner", "?")):
        candidates = [
            "The sender may be requesting missing ownership, timing, or implementation detail before acting.",
            "The sender may be checking alignment and completeness rather than rejecting the proposal.",
            "The sender may expect a shorter answer focused on the immediate decision or next step.",
            "The message may be informational, with no action expected until a follow-up is stated.",
            "The sender may be surfacing a dependency that is not yet visible in the current context.",
        ]
    elif any(term in lowered for term in ("approved", "looks good", "great", "go ahead")):
        candidates = [
            "The wording may indicate support within the scope that was explicitly discussed.",
            "The message may be an acknowledgement rather than a formal grant of broader authority.",
            "Approval may still depend on an unstated owner, control, or implementation condition.",
            "The sender may expect a concise confirmation of the next step.",
            "The message may close only the current question, not the larger workstream.",
        ]
    else:
        candidates = [
            "The sender may be sharing information without requesting immediate action.",
            "The sender may be inviting clarification or coordination, but the requested outcome is not explicit.",
            "The message may be a partial response whose decision or timing will follow later.",
            "The sender may expect acknowledgement before providing more detail.",
            "The sender may be redirecting attention to a practical dependency rather than expressing a personal judgment.",
        ]
    return [
        _inference(statement, f"plausible_interpretation_{index:02d}")
        for index, statement in enumerate(candidates[:count], start=1)
    ]


def _time_box_plan(duration_minutes: Any) -> list[dict[str, Any]] | None:
    if not isinstance(duration_minutes, int) or isinstance(duration_minutes, bool):
        return None
    opening = max(1, round(duration_minutes * 0.15))
    evidence = max(1, round(duration_minutes * 0.25))
    discussion = max(1, round(duration_minutes * 0.40))
    close = duration_minutes - opening - evidence - discussion
    if close < 1:
        discussion = max(1, discussion - (1 - close))
        close = duration_minutes - opening - evidence - discussion
    return [
        {
            "minutes": opening,
            "focus": "State the desired outcome and exact ask.",
        },
        {
            "minutes": evidence,
            "focus": "Give the strongest facts, recommendation, and authority boundary.",
        },
        {
            "minutes": discussion,
            "focus": "Discuss scope, concerns, delegation, and ownership.",
        },
        {
            "minutes": close,
            "focus": "Confirm the decision, owner, date, and next step.",
        },
    ]


def _authority_line(authority: dict[str, Any]) -> str:
    state = authority.get("state", "unknown")
    delivery_owner = authority.get("deliveryOwner") or "the delivery coordinator"
    final_owner = authority.get("finalApprovalOwner") or "the designated approval owner"
    domains = authority.get("domainOwners", [])
    domain_text = "; ".join(
        f"{item['ownerRole']} owns {item['domain']}"
        if item["ownershipType"] == "owns_workstream"
        else f"{item['ownerRole']} {item['ownershipType'].replace('_', ' ')} {item['domain']}"
        for item in domains
    )
    if state in {"formally_assigned", "explicitly_delegated", "sponsor_approved_workstream"}:
        opening = f"{delivery_owner} owns the assigned delivery scope"
    elif state == "peer_partnership":
        opening = f"{delivery_owner} coordinates delivery"
    elif state == "nominated_pending_confirmation":
        opening = f"{delivery_owner} is the nominated coordinator pending confirmation"
    elif state == "self_initiated":
        opening = f"{delivery_owner} is proposing and coordinating the work"
    else:
        opening = "Delivery ownership is not yet confirmed"
    parts = [opening]
    if domain_text:
        parts.append(domain_text)
    parts.append(f"final approval remains with {final_owner}")
    return "; ".join(parts) + "."


def _authority_basis(authority: dict[str, Any]) -> dict[str, Any]:
    return {
        "state": authority.get("state", "unknown"),
        "evidenceState": authority.get("evidenceState", "user_asserted"),
        "evidenceFactIds": list(authority.get("evidenceFactIds", [])),
        "deliveryOwner": authority.get("deliveryOwner"),
        "domainOwners": deepcopy(authority.get("domainOwners", [])),
        "finalApprovalOwner": authority.get("finalApprovalOwner"),
    }


def _credit_line(contributors: list[dict[str, Any]]) -> str | None:
    if not contributors:
        return None
    statements = []
    for item in contributors:
        if item["ownershipType"] == "owns_workstream":
            statements.append(f"{item['role']} owns {item['contribution']}")
        else:
            statements.append(
                f"{item['role']} {item['ownershipType'].replace('_', ' ')} {item['contribution']}"
            )
    return "; ".join(statements) + "."


def _common_unknowns(request: dict[str, Any]) -> list[str]:
    unknowns: list[str] = []
    authority = request.get("authority", {})
    if authority.get("state") == "unknown":
        unknowns.append("The user's authority state is not confirmed.")
    if not _nonempty(authority.get("finalApprovalOwner")):
        unknowns.append("The final approval owner is not confirmed.")
    if not request.get("facts"):
        unknowns.append("No explicit facts or user-provided claims were supplied.")
    return unknowns


def _preflight_unknowns(request: dict[str, Any]) -> list[str]:
    unknowns: list[str] = []
    if not request["situation"].get("desiredOutcome"):
        unknowns.append("The desired outcome is not explicit.")
    if not _exact_ask(request):
        unknowns.append("The primary ask is not explicit.")
    if not request.get("contributors"):
        unknowns.append("Whether anyone else should receive visible credit is unknown.")
    return unknowns


def _recipient_assistance_summary(guidance: dict[str, Any] | None) -> dict[str, Any]:
    if guidance is None:
        return {
            "applied": False,
            "profileHash": None,
            "recipientNameIncluded": False,
            "reason": "no_active_recipient_guidance_supplied",
        }
    actionable = _recipient_guidance_is_actionable(guidance)
    return {
        "applied": actionable,
        "profileHash": guidance.get("profileHash"),
        "recipientNameIncluded": False,
        "matchedContext": guidance.get("matchedContext"),
        "contextMatched": bool(guidance.get("contextMatched")),
        "reason": (
            "qualified_context_guidance_applied"
            if actionable
            else "no_qualified_actionable_guidance"
        ),
        "humanReviewRequired": True,
        "automaticSendingAllowed": False,
    }


def _validate_recipient_guidance(guidance: dict[str, Any]) -> None:
    errors: list[dict[str, str]] = []
    if not isinstance(guidance, dict):
        errors.append(
            _reason(
                "invalid_recipient_guidance",
                "recipientGuidance",
                "Recipient guidance must be a JSON object.",
            )
        )
    else:
        required_fields = {
            "artifactType",
            "profileId",
            "displayName",
            "purpose",
            "guidance",
            "likelyResponsePatterns",
            "observedCommunicationPatterns",
            "matchedContext",
            "contextMatched",
            "profileHash",
            "expiresAt",
            "humanReviewRequired",
            "automaticSendingAllowed",
            "evidenceBoundary",
            "marketEvidenceCreated",
        }
        _reject_unknown_fields(
            guidance,
            required_fields,
            "recipientGuidance",
            errors,
        )
        missing = sorted(required_fields - set(guidance))
        for field in missing:
            _error(
                errors,
                "missing_recipient_guidance_field",
                f"recipientGuidance.{field}",
                "Required recipient-guidance field is missing.",
            )
        if guidance.get("artifactType") != "interaction_assistance_guidance":
            _error(
                errors,
                "invalid_recipient_guidance_type",
                "recipientGuidance.artifactType",
                "Expected interaction_assistance_guidance.",
            )
        for field in ("profileId", "displayName", "evidenceBoundary"):
            _require_string(
                guidance,
                field,
                "recipientGuidance",
                errors,
                minimum=2,
                maximum=5000,
            )
        if guidance.get("purpose") != RECIPIENT_GUIDANCE_PURPOSE:
            _error(
                errors,
                "invalid_recipient_guidance_purpose",
                "recipientGuidance.purpose",
                f"Expected {RECIPIENT_GUIDANCE_PURPOSE}.",
            )
        if guidance.get("matchedContext") not in ALLOWED_RECIPIENT_CONTEXTS:
            _error(
                errors,
                "invalid_recipient_guidance_context",
                "recipientGuidance.matchedContext",
                "Recipient guidance must identify a supported exact communication context.",
            )
        if guidance.get("contextMatched") is not True:
            _error(
                errors,
                "recipient_guidance_context_not_matched",
                "recipientGuidance.contextMatched",
                "Only context-matched recipient guidance may be supplied.",
            )
        if (
            not isinstance(guidance.get("profileHash"), str)
            or not SHA256_PATTERN.fullmatch(guidance.get("profileHash", ""))
        ):
            _error(
                errors,
                "invalid_recipient_profile_hash",
                "recipientGuidance.profileHash",
                "profileHash must be a lowercase SHA-256 value.",
            )
        _validate_datetime(
            guidance.get("expiresAt"),
            "recipientGuidance.expiresAt",
            errors,
        )
        if isinstance(guidance.get("expiresAt"), str):
            try:
                expires_at = datetime.fromisoformat(
                    guidance["expiresAt"].replace("Z", "+00:00")
                )
                if (
                    expires_at.tzinfo is not None
                    and expires_at.astimezone(timezone.utc) <= datetime.now(timezone.utc)
                ):
                    _error(
                        errors,
                        "recipient_guidance_expired",
                        "recipientGuidance.expiresAt",
                        "Expired recipient guidance cannot be applied.",
                    )
            except ValueError:
                pass
        expected_boundaries = {
            "humanReviewRequired": True,
            "automaticSendingAllowed": False,
            "marketEvidenceCreated": False,
        }
        for field, required in expected_boundaries.items():
            if guidance.get(field) is not required:
                _error(
                    errors,
                    "recipient_guidance_boundary_failed",
                    f"recipientGuidance.{field}",
                    f"{field} must be {str(required).lower()}.",
                )
        for field in (
            "likelyResponsePatterns",
            "observedCommunicationPatterns",
        ):
            if not isinstance(guidance.get(field), list):
                _error(
                    errors,
                    "invalid_recipient_guidance_collection",
                    f"recipientGuidance.{field}",
                    f"{field} must be a list.",
                )
        _validate_recipient_guidance_payload(guidance.get("guidance"), errors)
        _scan_restricted_content(
            guidance,
            errors,
            root="recipientGuidance",
        )

    if errors:
        raise WorkplaceAssistanceBlockedError(
            _deduplicate_reasons(errors)
        )


def _validate_recipient_guidance_payload(
    payload: Any,
    errors: list[dict[str, str]],
) -> None:
    path = "recipientGuidance.guidance"
    if not isinstance(payload, dict):
        _error(
            errors,
            "invalid_recipient_guidance_payload",
            path,
            "guidance must be an object.",
        )
        return
    allowed = {
        "draftingAdjustments",
        "likelyQuestionsOrReactions",
        "preferredTerminology",
        "terminologyToAvoid",
        "representativeExamples",
        "useRules",
    }
    _reject_unknown_fields(payload, allowed, path, errors)
    for field in sorted(allowed):
        if field not in payload:
            _error(
                errors,
                "missing_recipient_guidance_field",
                f"{path}.{field}",
                "Required guidance field is missing.",
            )
        elif not isinstance(payload[field], list):
            _error(
                errors,
                "invalid_recipient_guidance_collection",
                f"{path}.{field}",
                f"{field} must be a list.",
            )
    for field, maximum_items, maximum_length in (
        ("draftingAdjustments", 6, 2000),
        ("likelyQuestionsOrReactions", 5, 2000),
        ("preferredTerminology", 12, 300),
        ("terminologyToAvoid", 12, 300),
        ("useRules", 10, 2000),
    ):
        if isinstance(payload.get(field), list):
            _validate_string_list(
                payload[field],
                f"{path}.{field}",
                errors,
                maximum_items=maximum_items,
                maximum_length=maximum_length,
            )
    if isinstance(payload.get("representativeExamples"), list) and len(
        payload["representativeExamples"]
    ) > 8:
        _error(
            errors,
            "too_many_recipient_examples",
            f"{path}.representativeExamples",
            "At most eight representative examples are allowed.",
        )


def _recipient_guidance_is_actionable(guidance: dict[str, Any]) -> bool:
    if guidance.get("contextMatched") is not True:
        return False
    payload = guidance.get("guidance")
    if not isinstance(payload, dict):
        return False
    return bool(
        payload.get("draftingAdjustments")
        or payload.get("likelyQuestionsOrReactions")
    )


def _recipient_guidance_application(
    guidance: dict[str, Any] | None,
) -> dict[str, Any]:
    if guidance is None or not _recipient_guidance_is_actionable(guidance):
        return {
            "applied": False,
            "draftingAdjustments": [],
            "likelyQuestionClasses": [],
            "privateRecipientNameIncluded": False,
            "reason": (
                "no_active_recipient_guidance_supplied"
                if guidance is None
                else "no_qualified_actionable_guidance"
            ),
        }
    payload = guidance["guidance"]
    return {
        "applied": True,
        "draftingAdjustments": deepcopy(payload["draftingAdjustments"]),
        "likelyQuestionClasses": deepcopy(
            payload["likelyQuestionsOrReactions"]
        ),
        "privateRecipientNameIncluded": False,
        "evidenceBoundary": (
            "Exact-context directional communication assistance only. "
            "It does not establish intent, preference, or future response."
        ),
    }


def _prioritize_profile_risk_gates(
    gates: list[dict[str, Any]],
    known_risks: list[str],
) -> list[str]:
    review_ids = [
        gate["gateId"]
        for gate in gates
        if gate["status"] == "review" and gate.get("applicable", True)
    ]
    focused_ids = {
        gate_id
        for risk in known_risks
        for gate_id in PROFILE_RISK_GATE_MAP.get(risk, set())
    }
    return [
        *[gate_id for gate_id in review_ids if gate_id in focused_ids],
        *[gate_id for gate_id in review_ids if gate_id not in focused_ids],
    ]


def _validate_situation(
    situation: Any,
    policy: dict[str, Any] | None,
    errors: list[dict[str, str]],
) -> None:
    if not isinstance(situation, dict):
        _error(errors, "missing_situation", "situation", "situation must be an object.")
        return
    _reject_unknown_fields(
        situation,
        {
            "context",
            "summary",
            "channel",
            "audience",
            "desiredOutcome",
            "durationMinutes",
        },
        "situation",
        errors,
    )
    _require_string(situation, "summary", "situation", errors, minimum=2, maximum=5000)
    context = situation.get("context")
    allowed_contexts = set(policy.get("scenarioContexts", [])) if isinstance(policy, dict) else set()
    if allowed_contexts and context not in allowed_contexts:
        _error(
            errors,
            "invalid_scenario_context",
            "situation.context",
            f"Expected one of: {', '.join(sorted(allowed_contexts))}.",
        )
    elif not allowed_contexts and not _valid_code(context):
        _error(errors, "invalid_scenario_context", "situation.context", "Context must be a lowercase code.")
    if situation.get("channel") not in ALLOWED_CHANNELS:
        _error(
            errors,
            "invalid_channel",
            "situation.channel",
            f"Expected one of: {', '.join(sorted(ALLOWED_CHANNELS))}.",
        )
    for field in ("audience", "desiredOutcome"):
        if field in situation:
            _validate_optional_text(situation, field, errors, path_prefix="situation", maximum=2000)
    if "durationMinutes" in situation:
        duration = situation.get("durationMinutes")
        if (
            not isinstance(duration, int)
            or isinstance(duration, bool)
            or not 5 <= duration <= 240
        ):
            _error(
                errors,
                "invalid_meeting_duration",
                "situation.durationMinutes",
                "durationMinutes must be an integer from 5 through 240.",
            )


def _validate_fact_records(value: Any, errors: list[dict[str, str]]) -> None:
    if not isinstance(value, list):
        _error(errors, "invalid_facts", "facts", "facts must be a list.")
        return
    seen: set[str] = set()
    for index, item in enumerate(value):
        path = f"facts[{index}]"
        if not isinstance(item, dict):
            _error(errors, "invalid_fact", path, "Fact must be an object.")
            continue
        _reject_unknown_fields(
            item,
            {"factId", "statement", "status", "sourceType", "category", "sourceReference"},
            path,
            errors,
        )
        fact_id = item.get("factId")
        if not isinstance(fact_id, str) or not fact_id.startswith("fact-") or not EVIDENCE_ID_PATTERN.fullmatch(fact_id):
            _error(errors, "invalid_fact_id", f"{path}.factId", "factId must start with fact-.")
        elif fact_id in seen:
            _error(errors, "duplicate_fact_id", f"{path}.factId", "factId must be unique.")
        else:
            seen.add(fact_id)
        _require_string(item, "statement", path, errors, minimum=2, maximum=5000)
        if item.get("status") not in ALLOWED_FACT_STATES:
            _error(errors, "invalid_fact_status", f"{path}.status", "Unsupported fact status.")
        if item.get("sourceType") not in ALLOWED_FACT_SOURCES:
            _error(errors, "invalid_fact_source", f"{path}.sourceType", "Unsupported fact source.")
        if item.get("category") not in ALLOWED_FACT_CATEGORIES:
            _error(errors, "invalid_fact_category", f"{path}.category", "Unsupported fact category.")
        if (
            item.get("status") == "explicit_fact"
            and item.get("sourceType") == "user_statement"
        ):
            _error(
                errors,
                "unverified_statement_mislabeled",
                f"{path}.status",
                "A user_statement must be user_provided_unverified unless an inspectable source is supplied.",
            )
        if (
            item.get("status") == "explicit_fact"
            and item.get("sourceType") != "user_statement"
            and not _nonempty(item.get("sourceReference"))
        ):
            _error(
                errors,
                "explicit_fact_source_reference_missing",
                f"{path}.sourceReference",
                "An explicit fact requires an inspectable sourceReference.",
            )
        if (
            item.get("status") == "explicit_fact"
            and isinstance(item.get("statement"), str)
            and any(pattern.search(item["statement"]) for pattern in MOTIVE_AS_FACT_PATTERNS)
        ):
            _error(
                errors,
                "motive_claim_mislabeled_as_fact",
                f"{path}.statement",
                "An inferred motive cannot be stored or emitted as an explicit fact.",
            )
        if "sourceReference" in item:
            _validate_optional_text(item, "sourceReference", errors, path_prefix=path, maximum=1000)


def _validate_authority(
    value: Any,
    facts: Any,
    errors: list[dict[str, str]],
) -> None:
    if not isinstance(value, dict):
        _error(errors, "missing_authority", "authority", "authority must be an object.")
        return
    _reject_unknown_fields(
        value,
        {
            "state",
            "deliveryOwner",
            "domainOwners",
            "finalApprovalOwner",
            "evidenceState",
            "evidenceFactIds",
        },
        "authority",
        errors,
    )
    if value.get("state") not in ALLOWED_AUTHORITY_STATES:
        _error(errors, "invalid_authority_state", "authority.state", "Unsupported authority state.")
    if value.get("evidenceState") not in ALLOWED_EVIDENCE_STATES:
        _error(errors, "invalid_authority_evidence", "authority.evidenceState", "Unsupported evidence state.")
    confirmed_authority_states = {
        "explicitly_delegated",
        "formally_assigned",
        "peer_partnership",
        "sponsor_approved_workstream",
    }
    if (
        value.get("state") in confirmed_authority_states
        and value.get("evidenceState") == "user_asserted"
    ):
        _error(
            errors,
            "authority_state_evidence_mismatch",
            "authority.evidenceState",
            "Confirmed assignment, delegation, partnership, or approved-workstream language requires source or stakeholder support.",
        )
    evidence_fact_ids = value.get("evidenceFactIds", [])
    if not isinstance(evidence_fact_ids, list):
        _error(
            errors,
            "invalid_authority_evidence_fact_ids",
            "authority.evidenceFactIds",
            "evidenceFactIds must be a list of fact IDs.",
        )
        evidence_fact_ids = []
    if (
        value.get("state") in confirmed_authority_states
        and not evidence_fact_ids
    ):
        _error(
            errors,
            "confirmed_authority_evidence_missing",
            "authority.evidenceFactIds",
            "Confirmed authority requires at least one linked, sourced authority-evidence fact.",
        )
    fact_records = facts if isinstance(facts, list) else []
    fact_index = {
        item.get("factId"): item
        for item in fact_records
        if isinstance(item, dict) and isinstance(item.get("factId"), str)
    }
    seen_evidence_fact_ids: set[str] = set()
    for index, fact_id in enumerate(evidence_fact_ids):
        path = f"authority.evidenceFactIds[{index}]"
        if (
            not isinstance(fact_id, str)
            or not fact_id.startswith("fact-")
            or not EVIDENCE_ID_PATTERN.fullmatch(fact_id)
        ):
            _error(
                errors,
                "invalid_authority_evidence_fact_id",
                path,
                "Each authority evidence reference must be a valid factId.",
            )
            continue
        if fact_id in seen_evidence_fact_ids:
            _error(
                errors,
                "duplicate_authority_evidence_fact_id",
                path,
                "Authority evidence fact IDs must be unique.",
            )
            continue
        seen_evidence_fact_ids.add(fact_id)
        fact = fact_index.get(fact_id)
        if fact is None:
            _error(
                errors,
                "authority_evidence_fact_not_found",
                path,
                "The referenced authority-evidence fact does not exist in facts.",
            )
            continue
        if not (
            fact.get("status") == "explicit_fact"
            and fact.get("category") == "authority_evidence"
            and _nonempty(fact.get("sourceReference"))
        ):
            _error(
                errors,
                "authority_evidence_fact_not_qualified",
                path,
                "Authority evidence must reference an explicit authority_evidence fact with an inspectable sourceReference.",
            )
    for field in ("deliveryOwner", "finalApprovalOwner"):
        if field in value:
            _validate_optional_text(value, field, errors, path_prefix="authority", maximum=300)
    owners = value.get("domainOwners", [])
    if not isinstance(owners, list):
        _error(errors, "invalid_domain_owners", "authority.domainOwners", "domainOwners must be a list.")
        return
    for index, owner in enumerate(owners):
        path = f"authority.domainOwners[{index}]"
        if not isinstance(owner, dict):
            _error(errors, "invalid_domain_owner", path, "Domain owner must be an object.")
            continue
        _reject_unknown_fields(owner, {"domain", "ownerRole", "ownershipType"}, path, errors)
        _require_string(owner, "domain", path, errors, minimum=2, maximum=300)
        _require_string(owner, "ownerRole", path, errors, minimum=2, maximum=300)
        if owner.get("ownershipType") not in ALLOWED_OWNERSHIP_TYPES:
            _error(errors, "invalid_ownership_type", f"{path}.ownershipType", "Unsupported ownership type.")


def _validate_contributors(value: Any, errors: list[dict[str, str]]) -> None:
    if not isinstance(value, list):
        _error(errors, "invalid_contributors", "contributors", "contributors must be a list.")
        return
    seen: set[str] = set()
    for index, item in enumerate(value):
        path = f"contributors[{index}]"
        if not isinstance(item, dict):
            _error(errors, "invalid_contributor", path, "Contributor must be an object.")
            continue
        _reject_unknown_fields(
            item,
            {"contributorId", "role", "contribution", "creditIncluded", "ownershipType"},
            path,
            errors,
        )
        contributor_id = item.get("contributorId")
        if (
            not isinstance(contributor_id, str)
            or not contributor_id.startswith("contributor-")
            or not EVIDENCE_ID_PATTERN.fullmatch(contributor_id)
        ):
            _error(errors, "invalid_contributor_id", f"{path}.contributorId", "Invalid contributorId.")
        elif contributor_id in seen:
            _error(errors, "duplicate_contributor_id", f"{path}.contributorId", "contributorId must be unique.")
        else:
            seen.add(contributor_id)
        _require_string(item, "role", path, errors, minimum=2, maximum=300)
        _require_string(item, "contribution", path, errors, minimum=2, maximum=1000)
        if not isinstance(item.get("creditIncluded"), bool):
            _error(errors, "invalid_credit_flag", f"{path}.creditIncluded", "creditIncluded must be boolean.")
        if item.get("ownershipType") not in ALLOWED_OWNERSHIP_TYPES:
            _error(errors, "invalid_ownership_type", f"{path}.ownershipType", "Unsupported ownership type.")


def _validate_decisions(value: Any, errors: list[dict[str, str]]) -> None:
    _validate_outcome_records(value, "decisions", "decisionId", errors)


def _validate_commitments(value: Any, errors: list[dict[str, str]]) -> None:
    _validate_outcome_records(value, "commitments", "commitmentId", errors)


def _validate_outcome_records(
    value: Any,
    collection_name: str,
    id_field: str,
    errors: list[dict[str, str]],
) -> None:
    if not isinstance(value, list):
        _error(errors, f"invalid_{collection_name}", collection_name, f"{collection_name} must be a list.")
        return
    seen: set[str] = set()
    expected_prefix = "decision-" if id_field == "decisionId" else "commitment-"
    for index, item in enumerate(value):
        path = f"{collection_name}[{index}]"
        if not isinstance(item, dict):
            _error(errors, f"invalid_{collection_name[:-1]}", path, "Record must be an object.")
            continue
        _reject_unknown_fields(item, {id_field, "statement", "owner", "dueDate", "status"}, path, errors)
        record_id = item.get(id_field)
        if (
            not isinstance(record_id, str)
            or not record_id.startswith(expected_prefix)
            or not EVIDENCE_ID_PATTERN.fullmatch(record_id)
        ):
            _error(errors, "invalid_outcome_id", f"{path}.{id_field}", f"{id_field} has an invalid format.")
        elif record_id in seen:
            _error(errors, "duplicate_outcome_id", f"{path}.{id_field}", f"{id_field} must be unique.")
        else:
            seen.add(record_id)
        _require_string(item, "statement", path, errors, minimum=2, maximum=3000)
        for field in ("owner", "dueDate"):
            if field in item:
                _validate_optional_text(item, field, errors, path_prefix=path, maximum=300)
        if _nonempty(item.get("dueDate")):
            _validate_dateish(item["dueDate"], f"{path}.dueDate", errors)
        if item.get("status") not in ALLOWED_DECISION_STATES:
            _error(errors, "invalid_outcome_status", f"{path}.status", "Unsupported status.")


def _validate_career_evidence(
    value: Any,
    policy: dict[str, Any] | None,
    errors: list[dict[str, str]],
) -> None:
    if not isinstance(value, list):
        _error(errors, "invalid_career_evidence", "careerEvidence", "careerEvidence must be a list.")
        return
    categories = (
        set(policy.get("careerEvidenceCategories", []))
        if isinstance(policy, dict)
        else set()
    )
    seen: set[str] = set()
    for index, item in enumerate(value):
        path = f"careerEvidence[{index}]"
        if not isinstance(item, dict):
            _error(errors, "invalid_career_evidence_item", path, "Career evidence must be an object.")
            continue
        _reject_unknown_fields(
            item,
            {
                "evidenceId",
                "category",
                "statement",
                "evidenceState",
                "occurredAt",
                "metric",
                "decisionOwner",
                "effectiveDate",
                "sponsorRole",
                "proofReference",
                "adoptionScope",
                "teammateRole",
                "authorityScope",
            },
            path,
            errors,
        )
        evidence_id = item.get("evidenceId")
        if (
            not isinstance(evidence_id, str)
            or not evidence_id.startswith("evidence-")
            or not EVIDENCE_ID_PATTERN.fullmatch(evidence_id)
        ):
            _error(errors, "invalid_career_evidence_id", f"{path}.evidenceId", "Invalid evidenceId.")
        elif evidence_id in seen:
            _error(errors, "duplicate_career_evidence_id", f"{path}.evidenceId", "evidenceId must be unique.")
        else:
            seen.add(evidence_id)
        _require_string(item, "statement", path, errors, minimum=2, maximum=5000)
        if isinstance(item.get("statement"), str) and any(
            pattern.search(item["statement"])
            for pattern in COWORKER_EVALUATION_PATTERNS
        ):
            _error(
                errors,
                "coworker_evaluation_content_not_allowed",
                f"{path}.statement",
                "Career evidence must describe the user's work and outcomes without evaluating another person.",
            )
        if categories and item.get("category") not in categories:
            _error(errors, "invalid_career_evidence_category", f"{path}.category", "Unsupported category.")
        elif not categories and not _valid_code(item.get("category")):
            _error(errors, "invalid_career_evidence_category", f"{path}.category", "Invalid category.")
        if item.get("evidenceState") not in ALLOWED_EVIDENCE_STATES:
            _error(errors, "invalid_career_evidence_state", f"{path}.evidenceState", "Unsupported evidence state.")
        if (
            item.get("evidenceState")
            in {"source_supported", "stakeholder_confirmed", "formally_decided"}
            and not _nonempty(item.get("proofReference"))
        ):
            _error(
                errors,
                "career_evidence_proof_reference_missing",
                f"{path}.proofReference",
                "Non-user career evidence requires an inspectable proofReference.",
            )
        for field in (
            "occurredAt",
            "metric",
            "decisionOwner",
            "effectiveDate",
            "sponsorRole",
            "proofReference",
            "adoptionScope",
            "teammateRole",
            "authorityScope",
        ):
            if field in item:
                _validate_optional_text(item, field, errors, path_prefix=path, maximum=2000)
        if _nonempty(item.get("occurredAt")):
            _validate_dateish(item["occurredAt"], f"{path}.occurredAt", errors)
        if _nonempty(item.get("effectiveDate")):
            _validate_dateish(item["effectiveDate"], f"{path}.effectiveDate", errors)


def _validate_requested_actions(
    value: Any,
    policy: dict[str, Any] | None,
    errors: list[dict[str, str]],
) -> None:
    if not isinstance(value, list) or not value:
        _error(
            errors,
            "missing_requested_actions",
            "requestedActions",
            "requestedActions must be a non-empty list.",
        )
        return
    hard_blocked = (
        set(policy.get("hardBlockedActions", []))
        if isinstance(policy, dict)
        else DISALLOWED_REQUESTED_ACTIONS
    )
    for index, action in enumerate(value):
        path = f"requestedActions[{index}]"
        if action in hard_blocked or action in DISALLOWED_REQUESTED_ACTIONS:
            _error(
                errors,
                "disallowed_assistance_action",
                path,
                f"{action} is prohibited for workplace assistance.",
            )
        elif action not in ALLOWED_REQUESTED_ACTIONS:
            _error(errors, "unknown_assistance_action", path, "Unknown requested action.")


def _validate_authorization(
    value: Any,
    path: str,
    errors: list[dict[str, str]],
) -> None:
    if not isinstance(value, dict):
        _error(errors, "missing_authorization", path, "Authorization must be an object.")
        return
    expected = {
        "automaticSendingAllowed": False,
        "coworkerEvaluationAllowed": False,
        "humanReviewRequired": True,
        "profileBelongsToCurrentUser": True,
    }
    _reject_unknown_fields(value, set(expected), path, errors)
    for field, required in expected.items():
        if value.get(field) is not required:
            _error(
                errors,
                "authorization_gate_failed",
                f"{path}.{field}",
                f"{field} must be {str(required).lower()}.",
            )


def _new_self_store() -> dict[str, Any]:
    now = _now()
    return {
        "artifactType": STORE_ARTIFACT_TYPE,
        "schemaVersion": 1,
        "createdAt": now,
        "updatedAt": now,
        "profile": None,
        "dataBoundary": (
            "Installation-local encrypted, explicitly self-declared workplace accommodation context. "
            "Excluded from normal Mindfront history, reports, dashboards, and improvement plans."
        ),
    }


def _load_self_store(path: Path, *, missing_ok: bool = False) -> dict[str, Any]:
    if not path.exists():
        if missing_ok:
            return _new_self_store()
        raise WorkplaceAssistanceBlockedError(
            [_reason("self_profile_store_missing", str(path), "Self-profile store does not exist.")]
        )
    try:
        envelope = json.loads(path.read_text(encoding="utf-8"))
        payload = decrypt_envelope(
            envelope,
            expected_artifact_type=ENCRYPTED_STORE_ARTIFACT_TYPE,
        )
        store = json.loads(payload.decode("utf-8"))
        if store.get("artifactType") != STORE_ARTIFACT_TYPE:
            raise ValueError("unexpected decrypted self-profile store type")
        return store
    except WorkplaceAssistanceBlockedError:
        raise
    except VaultEncryptionError as exc:
        raise WorkplaceAssistanceBlockedError(
            [
                _reason(
                    "self_profile_store_unreadable",
                    str(path),
                    reason["message"],
                )
                for reason in exc.reasons
            ]
        ) from exc
    except Exception as exc:
        raise WorkplaceAssistanceBlockedError(
            [_reason("self_profile_store_unreadable", str(path), str(exc))]
        ) from exc


def _save_self_store(path: Path, store: dict[str, Any]) -> None:
    payload = json.dumps(
        store,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    try:
        write_encrypted_payload(
            path,
            payload,
            artifact_type=ENCRYPTED_STORE_ARTIFACT_TYPE,
        )
    except VaultEncryptionError as exc:
        raise WorkplaceAssistanceBlockedError(
            [
                _reason(
                    "self_profile_store_encryption_failed",
                    str(path),
                    reason["message"],
                )
                for reason in exc.reasons
            ]
        ) from exc


def _gate(
    gate_id: str,
    status: str,
    explanation: str,
    recommended_adjustment: str,
    *,
    matched_text: Iterable[str] | None = None,
    observed_value: str | None = None,
    applicable: bool = True,
) -> dict[str, Any]:
    return {
        "gateId": gate_id,
        "status": status,
        "severity": "review",
        "evidenceBasis": "heuristic_inference",
        "explanation": explanation,
        "recommendedAdjustment": recommended_adjustment,
        "matchedText": list(matched_text or []),
        "observedValue": observed_value,
        "applicable": applicable,
        "intentPreserved": True,
        "notDiagnosis": True,
    }


def _inference(statement: str, inference_id: str) -> dict[str, Any]:
    return {
        "inferenceId": inference_id,
        "statement": statement,
        "evidenceBasis": "heuristic_inference",
        "confidence": "low",
        "notFact": True,
        "motiveClaim": False,
    }


def _exact_ask(request: dict[str, Any]) -> str:
    if _nonempty(request.get("intendedAsk")):
        return request["intendedAsk"].strip()
    asks = request.get("asks", [])
    return asks[0].strip() if asks else ""


def _pattern_matches(text: str, patterns: Iterable[str]) -> list[str]:
    matches: list[str] = []
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match is not None:
            matches.append(match.group(0))
    return _unique_strings(matches)


def _profile_hash(profile: dict[str, Any]) -> str:
    return _payload_hash(
        profile,
        omit={"createdAt", "updatedAt", "profileHash"},
    )


def require_private_runtime_path(path: Path, path_label: str) -> Path:
    """Require persisted private assistance data to live below runtime-data."""

    candidate = path.expanduser().resolve(strict=False)
    if "runtime-data" not in {part.casefold() for part in candidate.parts}:
        raise WorkplaceAssistanceBlockedError(
            [
                _reason(
                    "private_runtime_path_required",
                    path_label,
                    "Private workplace-assistance stores and outputs must remain below a runtime-data directory.",
                )
            ]
        )
    return candidate


def _payload_hash(payload: dict[str, Any], *, omit: set[str] | None = None) -> str:
    candidate = deepcopy(payload)
    for key in omit or set():
        candidate.pop(key, None)
    canonical = json.dumps(candidate, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return f"sha256:{hashlib.sha256(canonical.encode('utf-8')).hexdigest()}"


def _sha256_bytes(payload: bytes) -> str:
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


def _truncate_words(text: str, limit: int) -> str:
    words = text.split()
    if len(words) <= limit:
        return text.strip()
    return " ".join(words[:limit]).rstrip(" ,;:") + "..."


def _words(text: str) -> list[str]:
    return re.findall(r"[A-Za-z0-9][A-Za-z0-9'-]*", text or "")


def _validate_exact_string_set(
    value: Any,
    expected: set[str],
    path: str,
    errors: list[dict[str, str]],
) -> None:
    if not isinstance(value, list) or set(value) != expected or len(value) != len(expected):
        _error(
            errors,
            "controlled_set_mismatch",
            path,
            f"Expected exactly: {', '.join(sorted(expected))}.",
        )


def _validate_controlled_string_list(
    value: Any,
    *,
    path: str,
    allowed: set[str],
    errors: list[dict[str, str]],
    require_nonempty: bool,
) -> None:
    if not isinstance(value, list) or (require_nonempty and not value):
        _error(errors, "invalid_controlled_list", path, "Expected a non-empty list.")
        return
    if not all(isinstance(item, str) for item in value):
        _error(errors, "invalid_controlled_list", path, "Every item must be a string.")
        return
    if len(value) != len(set(value)):
        _error(errors, "duplicate_controlled_value", path, "Values must be unique.")
    unknown = sorted(set(value) - allowed)
    if unknown:
        _error(errors, "unknown_controlled_value", path, f"Unsupported values: {', '.join(unknown)}.")


def _validate_string_list(
    value: Any,
    path: str,
    errors: list[dict[str, str]],
    *,
    maximum_items: int,
    maximum_length: int,
) -> None:
    if not isinstance(value, list):
        _error(errors, "invalid_string_list", path, f"{path} must be a list.")
        return
    if len(value) > maximum_items:
        _error(errors, "too_many_items", path, f"{path} may contain at most {maximum_items} items.")
    for index, item in enumerate(value):
        if not isinstance(item, str) or not item.strip() or len(item) > maximum_length:
            _error(
                errors,
                "invalid_string_item",
                f"{path}[{index}]",
                f"Item must be a non-empty string no longer than {maximum_length} characters.",
            )


def _validate_optional_text(
    obj: dict[str, Any],
    field: str,
    errors: list[dict[str, str]],
    *,
    path_prefix: str = "",
    maximum: int,
) -> None:
    if field not in obj:
        return
    value = obj.get(field)
    path = f"{path_prefix}.{field}" if path_prefix else field
    if value is not None and (
        not isinstance(value, str) or len(value) > maximum
    ):
        _error(errors, "invalid_optional_text", path, f"{field} must be null or at most {maximum} characters.")


def _require_string(
    obj: dict[str, Any],
    field: str,
    path: str,
    errors: list[dict[str, str]],
    *,
    minimum: int,
    maximum: int,
) -> None:
    value = obj.get(field)
    if not isinstance(value, str) or not minimum <= len(value.strip()) <= maximum:
        _error(
            errors,
            "invalid_string",
            f"{path}.{field}",
            f"{field} must contain {minimum} to {maximum} characters.",
        )


def _validate_datetime(
    value: Any,
    path: str,
    errors: list[dict[str, str]],
) -> None:
    if not isinstance(value, str):
        _error(errors, "invalid_datetime", path, "Expected an ISO-8601 datetime string.")
        return
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise ValueError("timezone is required")
    except ValueError:
        _error(errors, "invalid_datetime", path, "Expected a timezone-aware ISO-8601 datetime string.")


def _validate_dateish(
    value: str,
    path: str,
    errors: list[dict[str, str]],
) -> None:
    try:
        if "T" in value:
            datetime.fromisoformat(value.replace("Z", "+00:00"))
        else:
            date.fromisoformat(value)
    except ValueError:
        _error(errors, "invalid_date", path, "Expected an ISO-8601 date or datetime.")


def _reject_unknown_fields(
    value: dict[str, Any],
    allowed: set[str],
    path: str,
    errors: list[dict[str, str]],
) -> None:
    for field in sorted(set(value) - allowed):
        _error(
            errors,
            "unknown_field",
            f"{path}.{field}" if path != "$" else field,
            "Unknown fields are rejected.",
        )


def _reject_diagnosis_fields(
    value: Any,
    path: str,
    errors: list[dict[str, str]],
) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            child = f"{path}.{key}" if path != "$" else key
            if "diagnos" in key.casefold():
                _error(
                    errors,
                    "diagnosis_field_not_allowed",
                    child,
                    "Mindfront accepts user-declared accommodation context, not diagnosis fields.",
                )
            _reject_diagnosis_fields(item, child, errors)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _reject_diagnosis_fields(item, f"{path}[{index}]", errors)


def _scan_restricted_content(
    value: Any,
    errors: list[dict[str, str]],
    *,
    root: str,
) -> None:
    for path, text in _string_values(value, root):
        if any(pattern.search(text) for pattern in SECRET_PATTERNS):
            _error(
                errors,
                "credential_or_secret_detected",
                path,
                "Credentials or secret-like values are not accepted by this private workflow.",
            )
        if any(pattern.search(text) for pattern in CONTROLLED_MARKER_PATTERNS):
            _error(
                errors,
                "controlled_material_detected",
                path,
                "Explicitly controlled material must remain in its approved enclave workflow.",
            )


def _string_values(value: Any, path: str) -> Iterable[tuple[str, str]]:
    if isinstance(value, dict):
        for key, item in value.items():
            child = f"{path}.{key}" if path != "$" else key
            yield from _string_values(item, child)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from _string_values(item, f"{path}[{index}]")
    elif isinstance(value, str):
        yield path, value


def _valid_code(value: Any) -> bool:
    return isinstance(value, str) and bool(re.fullmatch(r"[a-z][a-z0-9_]{1,80}", value))


def _nonempty(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _unique_strings(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value not in seen:
            result.append(value)
            seen.add(value)
    return result


def _deduplicate_reasons(reasons: Iterable[dict[str, str]]) -> list[dict[str, str]]:
    seen: set[tuple[str, str, str]] = set()
    result = []
    for reason in reasons:
        key = (reason["code"], reason["path"], reason["message"])
        if key not in seen:
            result.append(reason)
            seen.add(key)
    return result


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _reason(code: str, path: str, message: str) -> dict[str, str]:
    return {"code": code, "path": path, "message": message}


def _error(
    errors: list[dict[str, str]],
    code: str,
    path: str,
    message: str,
) -> None:
    errors.append(_reason(code, path, message))

"""Private interaction-assistance profiles derived from communication observations.

The profile store is deliberately separate from Mindfront history artifacts. It
contains names and therefore uses installation-local authenticated encryption.
Raw message text, message subjects, quotes, attachments, and source-system
message identifiers are rejected at the observation boundary.
"""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
import uuid
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .vault_crypto import (
    CURRENT_ENCRYPTION,
    VaultEncryptionError,
    decrypt_envelope,
    write_encrypted_payload,
)


class InteractionProfileBlockedError(Exception):
    """Raised when profile input or storage violates the assistance boundary."""

    def __init__(self, reasons: list[dict[str, str]]):
        self.reasons = reasons
        super().__init__("Interaction profile operation blocked.")


ALLOWED_PURPOSE = "autistic_communication_assistance"
ALLOWED_SOURCE_SYSTEMS = {
    "microsoft_teams",
    "microsoft_outlook",
    "resolved_support_ticket",
}
ALLOWED_DIMENSIONS = {
    "action_clarity",
    "context_need",
    "decision_framing",
    "evidence_expectation",
    "information_density",
    "meeting_follow_up",
    "objection_pattern",
    "opening_preference",
    "question_pattern",
    "risk_attention",
    "structure_preference",
    "terminology",
    "tone_register",
    "uncertainty_handling",
}
TENDENCY_CATALOG: dict[str, dict[str, dict[str, str]]] = {
    "action_clarity": {
        "explicit_next_step": {
            "description": "Responses were more decisive when the next step was explicit.",
            "impact": "An implied action may create a clarification loop.",
            "adjustment": "End with one concrete next step.",
        },
        "owner_and_timing": {
            "description": "Responses frequently focused on ownership and timing.",
            "impact": "Unassigned work may be treated as incomplete.",
            "adjustment": "Name the owner and timing when those facts are known.",
        },
        "choice_with_default": {
            "description": "Decision exchanges moved faster when one option was identified as the default.",
            "impact": "An unranked option list may shift comparison work to the reader.",
            "adjustment": "State the recommended option, then show alternatives.",
        },
    },
    "context_need": {
        "minimal_context": {
            "description": "Short operational exchanges usually proceeded with minimal setup.",
            "impact": "A long preamble may hide the useful point.",
            "adjustment": "Use one line of context before the result or request.",
        },
        "brief_context": {
            "description": "A short explanation of why generally preceded useful decisions.",
            "impact": "A bare request may leave the reason unclear.",
            "adjustment": "Add a compact why-now sentence before the action.",
        },
        "detailed_context": {
            "description": "Complex exchanges benefited from explicit background and constraints.",
            "impact": "Compressed context may create avoidable follow-up questions.",
            "adjustment": "Include assumptions, constraints, and relevant history for complex work.",
        },
    },
    "decision_framing": {
        "recommendation_first": {
            "description": "Decision exchanges most often advanced from a clear recommendation.",
            "impact": "Neutral option lists may obscure the requested judgment.",
            "adjustment": "Lead with the recommendation and its main reason.",
        },
        "options_with_tradeoffs": {
            "description": "Decision exchanges often examined alternatives and tradeoffs.",
            "impact": "A single option may appear underexplored.",
            "adjustment": "Show the leading options with concise tradeoffs.",
        },
        "decision_request_first": {
            "description": "Explicit decision requests made the purpose of an exchange clearer.",
            "impact": "A decision buried late may be missed.",
            "adjustment": "State the decision needed near the beginning.",
        },
    },
    "evidence_expectation": {
        "source_reference": {
            "description": "Questions frequently sought an inspectable source or reference.",
            "impact": "Unsupported assertions may trigger a proof request.",
            "adjustment": "Attach the most relevant source or mark the claim as unverified.",
        },
        "quantified_evidence": {
            "description": "Quantified evidence often shaped follow-up questions.",
            "impact": "Vague scale language may not support a decision.",
            "adjustment": "Use sourced counts or ranges when available.",
        },
        "implementation_detail": {
            "description": "Responses often tested whether the proposed path was operationally concrete.",
            "impact": "Conceptual value alone may not answer feasibility concerns.",
            "adjustment": "Include the implementation path, owner, and boundary.",
        },
        "visible_caveats": {
            "description": "Caveats and limitations were material to technical exchanges.",
            "impact": "Hidden limitations may reduce trust when discovered later.",
            "adjustment": "Put the material limitation beside the claim it qualifies.",
        },
    },
    "information_density": {
        "concise_first": {
            "description": "Short summaries commonly carried the first useful exchange.",
            "impact": "Dense opening detail may delay comprehension.",
            "adjustment": "Start with the shortest complete summary, then add detail.",
        },
        "layered_detail": {
            "description": "Exchanges worked well when detail followed a compact summary.",
            "impact": "One undifferentiated block may be hard to scan.",
            "adjustment": "Use summary, key facts, then optional detail.",
        },
        "detailed_by_default": {
            "description": "Technical exchanges regularly required substantial detail.",
            "impact": "Overcompression may create repeated clarification.",
            "adjustment": "Include the relevant mechanics and constraints in the first pass.",
        },
    },
    "meeting_follow_up": {
        "concise_summary": {
            "description": "Short post-meeting summaries supported continuity.",
            "impact": "Unrecorded context may be lost between conversations.",
            "adjustment": "Send a brief outcome summary after substantive discussions.",
        },
        "decision_action_log": {
            "description": "Follow-up exchanges frequently centered on decisions and owners.",
            "impact": "Narrative notes may obscure accountability.",
            "adjustment": "Record decisions, actions, owners, and timing.",
        },
        "follow_up_only_when_needed": {
            "description": "Routine exchanges rarely needed a separate written recap.",
            "impact": "Excess follow-up can add communication overhead.",
            "adjustment": "Reserve recaps for decisions, commitments, or unresolved points.",
        },
    },
    "objection_pattern": {
        "scope": {
            "description": "Comparable proposals often produced scope questions.",
            "impact": "An undefined boundary may become the main concern.",
            "adjustment": "State what is included and excluded.",
        },
        "ownership": {
            "description": "Comparable proposals often produced ownership questions.",
            "impact": "A proposal without an operator may appear incomplete.",
            "adjustment": "Name who will build, review, and support the work.",
        },
        "evidence": {
            "description": "Comparable proposals often produced evidence questions.",
            "impact": "Claims without an inspectable basis may stall.",
            "adjustment": "Pair each material claim with its strongest available evidence.",
        },
        "cost_or_effort": {
            "description": "Comparable proposals often produced cost or effort questions.",
            "impact": "Benefits alone may not support prioritization.",
            "adjustment": "Include the expected effort, dependencies, and avoidable cost.",
        },
        "risk_controls": {
            "description": "Comparable proposals often produced control or risk questions.",
            "impact": "An undefined control boundary may block progress.",
            "adjustment": "Show the main risk and the control owner.",
        },
        "timeline": {
            "description": "Comparable proposals often produced sequencing or timing questions.",
            "impact": "A plan without timing may be difficult to prioritize.",
            "adjustment": "Show the next milestone and the dependency that controls it.",
        },
    },
    "opening_preference": {
        "bottom_line_first": {
            "description": "The result or request commonly appeared before supporting context.",
            "impact": "A delayed point may increase scanning effort.",
            "adjustment": "Put the result, recommendation, or request in the first two sentences.",
        },
        "problem_first": {
            "description": "Exchanges commonly established the practical issue before the proposed path.",
            "impact": "A solution-first opening may feel disconnected from need.",
            "adjustment": "Name the business issue before the proposed response.",
        },
        "context_first": {
            "description": "Some complex exchanges established constraints before asking for action.",
            "impact": "A bare conclusion may seem unsupported.",
            "adjustment": "Give the minimum decision-relevant context before the conclusion.",
        },
    },
    "question_pattern": {
        "ownership": {
            "description": "Questions frequently tested who owned the next step.",
            "impact": "Ownership ambiguity may dominate the response.",
            "adjustment": "Answer ownership before it has to be requested.",
        },
        "next_step": {
            "description": "Questions frequently tested what happens next.",
            "impact": "A status-only update may feel incomplete.",
            "adjustment": "Include the next action or explicitly state that none is needed.",
        },
        "scope": {
            "description": "Questions frequently tested boundaries and inclusions.",
            "impact": "Broad language may trigger scope clarification.",
            "adjustment": "Define the working boundary in one concise line.",
        },
        "risk": {
            "description": "Questions frequently tested operational or governance risk.",
            "impact": "Unaddressed controls may eclipse the proposed value.",
            "adjustment": "Surface the primary risk and mitigation early.",
        },
        "evidence": {
            "description": "Questions frequently tested the basis for a claim.",
            "impact": "A claim without evidence may create a verification loop.",
            "adjustment": "Provide the source or label the statement as an estimate.",
        },
        "implementation": {
            "description": "Questions frequently tested how the work would actually be implemented.",
            "impact": "A strategy-only answer may not feel actionable.",
            "adjustment": "Include the concrete operating path.",
        },
        "cost_or_effort": {
            "description": "Questions frequently tested effort or resource demand.",
            "impact": "An uncosted proposal may be hard to compare.",
            "adjustment": "Include a bounded effort estimate when available.",
        },
        "timeline": {
            "description": "Questions frequently tested timing or sequence.",
            "impact": "A timeless plan may not support prioritization.",
            "adjustment": "Name the next milestone and timing dependency.",
        },
    },
    "risk_attention": {
        "governance": {
            "description": "Governance boundaries were recurrent in comparable exchanges.",
            "impact": "Unclear authority or policy fit may slow agreement.",
            "adjustment": "State the governing boundary and decision owner.",
        },
        "security": {
            "description": "Security and network constraints were recurrent in comparable exchanges.",
            "impact": "Security ambiguity may block implementation discussion.",
            "adjustment": "Name the security dependency and who will advise on it.",
        },
        "operational_support": {
            "description": "Support and ownership after launch were recurrent concerns.",
            "impact": "An unsupported rollout may appear unsustainable.",
            "adjustment": "Show the operating owner and support path.",
        },
        "cost_control": {
            "description": "Cost visibility was recurrent in comparable exchanges.",
            "impact": "Unbounded cost may outweigh the stated value.",
            "adjustment": "Include the cost boundary and measurement plan.",
        },
    },
    "structure_preference": {
        "bullets": {
            "description": "Scannable lists commonly carried actions and decisions.",
            "impact": "Dense prose may hide discrete points.",
            "adjustment": "Use short bullets for facts, decisions, and actions.",
        },
        "short_prose": {
            "description": "Brief prose commonly carried routine updates.",
            "impact": "Heavy formatting may add unnecessary structure.",
            "adjustment": "Use two or three short paragraphs for a simple update.",
        },
        "table_for_comparison": {
            "description": "Structured comparison helped when alternatives were material.",
            "impact": "Prose comparisons may require extra synthesis.",
            "adjustment": "Use a compact table for options, tradeoffs, or ownership.",
        },
        "decision_action_sections": {
            "description": "Decision and action labels made operational exchanges easier to scan.",
            "impact": "Mixed narrative may blur status and required action.",
            "adjustment": "Separate status, decision, and next action.",
        },
    },
    "terminology": {
        "technical_precision": {
            "description": "Technical exchanges retained domain-specific terminology.",
            "impact": "Over-simplification may remove necessary precision.",
            "adjustment": "Keep essential technical terms and define only unfamiliar boundaries.",
        },
        "business_language": {
            "description": "Cross-functional exchanges favored business effects over internal mechanics.",
            "impact": "Implementation jargon may obscure why the work matters.",
            "adjustment": "Lead with business impact, then include technical detail as support.",
        },
        "mixed_register": {
            "description": "Effective exchanges connected technical detail to business effect.",
            "impact": "A one-sided technical or business framing may leave gaps.",
            "adjustment": "Pair each important technical fact with its practical consequence.",
        },
    },
    "tone_register": {
        "informal_direct": {
            "description": "Routine exchanges used a direct, informal professional register.",
            "impact": "Ceremonial wording may feel distant or inefficient.",
            "adjustment": "Use natural, direct wording without imitating slang or profanity.",
        },
        "neutral_professional": {
            "description": "Routine exchanges used a neutral professional register.",
            "impact": "Overly casual or ornate wording may distract from the point.",
            "adjustment": "Use straightforward professional language.",
        },
        "formal_for_decisions": {
            "description": "Higher-impact decisions used a more formal register.",
            "impact": "Casual wording may undersell a material decision.",
            "adjustment": "Use formal clarity for commitments, risks, and decisions.",
        },
    },
    "uncertainty_handling": {
        "recommendation_with_caveat": {
            "description": "Uncertain exchanges still benefited from a leading recommendation.",
            "impact": "Caveats without direction may transfer the decision burden.",
            "adjustment": "Give the best current recommendation and state the key uncertainty.",
        },
        "caveat_first": {
            "description": "Material uncertainty was commonly made visible before action.",
            "impact": "A buried caveat may weaken trust.",
            "adjustment": "Surface the decision-limiting uncertainty before the recommendation.",
        },
        "options_pending_evidence": {
            "description": "Some uncertain exchanges remained exploratory until evidence was available.",
            "impact": "Premature certainty may create rework.",
            "adjustment": "Show the viable options and the evidence needed to choose.",
        },
    },
}
ALLOWED_RESPONSE_CLASSES = {
    "acknowledge",
    "approve",
    "approve_with_conditions",
    "challenge_assumption",
    "defer",
    "redirect",
    "request_cost_or_effort",
    "request_evidence",
    "request_implementation_detail",
    "request_next_step",
    "request_ownership",
    "request_risk_controls",
    "request_scope_clarification",
    "request_timeline",
}
ALLOWED_LEXICON_CATEGORIES = {
    "decision_phrase",
    "informal_marker",
    "preferred_term",
    "question_stem",
    "term_to_avoid",
}
ALLOWED_EXAMPLE_KINDS = {
    "clarifying_question",
    "correction",
    "decision_response",
    "preferred_wording",
    "resolution_close",
    "typical_response",
}
ALLOWED_OUTCOME_CLASSES = {
    "advanced_work",
    "approved",
    "approved_with_conditions",
    "clarified",
    "deferred",
    "redirected",
    "resolved_ticket",
    "unknown",
}
LEXICON_SENSITIVE_PATTERN = re.compile(
    r"\b(?:accommodation|citizenship|compensation|diagnosis|disability|ethnicity|"
    r"health|leave|medical|political|race|religion|salary|sexual|union|veteran)\b",
    re.IGNORECASE,
)
EMAIL_PATTERN = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
PHONE_PATTERN = re.compile(r"(?<!\d)(?:\+?1[\s.-]?)?(?:\(\d{3}\)|\d{3})[\s.-]\d{3}[\s.-]\d{4}(?!\d)")
SSN_PATTERN = re.compile(r"(?<!\d)\d{3}-\d{2}-\d{4}(?!\d)")
UUID_PATTERN = re.compile(
    r"\b[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\b",
    re.IGNORECASE,
)
RESPONSE_CATALOG: dict[str, dict[str, str]] = {
    "acknowledge": {
        "pattern": "A brief acknowledgement is a plausible response in comparable routine exchanges.",
        "implication": "Keep the update complete enough that acknowledgement is sufficient.",
    },
    "approve": {
        "pattern": "A direct approval is a plausible response when the decision boundary is already clear.",
        "implication": "Make the requested decision explicit and keep supporting detail compact.",
    },
    "approve_with_conditions": {
        "pattern": "Conditional approval is a plausible response when dependencies remain.",
        "implication": "Name the likely dependency and how it will be resolved.",
    },
    "challenge_assumption": {
        "pattern": "A challenge to a key assumption is plausible in comparable proposals.",
        "implication": "Make the main assumption visible and attach its evidence or limitation.",
    },
    "defer": {
        "pattern": "Deferral is plausible when timing, ownership, or evidence is incomplete.",
        "implication": "Clarify why this matters now and what would unblock a later decision.",
    },
    "redirect": {
        "pattern": "Redirection to another owner or path is plausible in comparable requests.",
        "implication": "Confirm the decision owner and routing path before asking for action.",
    },
    "request_cost_or_effort": {
        "pattern": "A request for cost or effort is plausible in comparable proposals.",
        "implication": "Include a bounded effort, resource, or cost view.",
    },
    "request_evidence": {
        "pattern": "A request for supporting evidence is plausible in comparable proposals.",
        "implication": "Put the strongest available evidence beside the claim.",
    },
    "request_implementation_detail": {
        "pattern": "A request for implementation detail is plausible in comparable proposals.",
        "implication": "Show how the path would work in practice.",
    },
    "request_next_step": {
        "pattern": "A question about the next step is plausible after a status-only update.",
        "implication": "State what happens next or explicitly say that no action is required.",
    },
    "request_ownership": {
        "pattern": "A question about ownership is plausible when responsibilities are implicit.",
        "implication": "Name the operator, advisor, and decision owner when known.",
    },
    "request_risk_controls": {
        "pattern": "A request for risk controls is plausible in comparable implementation discussions.",
        "implication": "Surface the main control, boundary, and reviewer.",
    },
    "request_scope_clarification": {
        "pattern": "A scope clarification is plausible when the proposal boundary is broad.",
        "implication": "State what is included, excluded, and deferred.",
    },
    "request_timeline": {
        "pattern": "A timing question is plausible when sequence or urgency is unclear.",
        "implication": "Name the next milestone and dependency.",
    },
}
ALLOWED_BASIS = {"behavioral_pattern", "explicit_preference"}
ALLOWED_CONTEXTS = {
    "decision_request",
    "executive_update",
    "incident_response",
    "informal_coordination",
    "meeting_follow_up",
    "project_planning",
    "status_update",
    "support_request",
    "technical_discussion",
}
REQUIRED_SENSITIVE_EXCLUSIONS = {
    "credentials_and_secrets",
    "cui_and_export_controlled",
}
RAW_CONTENT_KEYS = {
    "attachment",
    "attachments",
    "body",
    "bodycontent",
    "content",
    "email",
    "excerpt",
    "html",
    "message",
    "messagebody",
    "messageid",
    "quote",
    "rawtext",
    "recipient",
    "recipientemail",
    "sender",
    "senderemail",
    "signature",
    "subjectline",
    "ticketid",
    "transcript",
}
MIN_AUTHORED_MESSAGES = 50
MIN_CONVERSATIONS = 5
MIN_CONTEXTS = 2
MIN_ACTIVE_DAYS = 30
MIN_WINDOW_DAYS = 45
MIN_PATTERN_SUPPORT = 20
MIN_PATTERN_CONSISTENCY = 0.65
PROFILE_TTL_DAYS = 90


def validate_observation_bundle(bundle: dict[str, Any]) -> list[dict[str, str]]:
    """Return structured validation errors for an aggregate observation bundle."""

    errors: list[dict[str, str]] = []
    _reject_raw_content_keys(bundle, "$", errors)
    _reject_unknown_fields(
        bundle,
        {
            "artifactType",
            "schemaVersion",
            "bundleId",
            "purpose",
            "subject",
            "authorization",
            "collection",
            "observations",
            "contextEvidence",
            "responseHypotheses",
            "privateLexicon",
            "privateExamples",
        },
        "$",
        errors,
    )

    if bundle.get("artifactType") != "communication_observation_bundle":
        _error(errors, "invalid_artifact_type", "artifactType", "Expected communication_observation_bundle.")
    if bundle.get("schemaVersion") != 1:
        _error(errors, "invalid_schema_version", "schemaVersion", "Expected schemaVersion 1.")
    if not _is_identifier(bundle.get("bundleId"), "comms-bundle-"):
        _error(errors, "invalid_bundle_id", "bundleId", "Bundle id must start with comms-bundle-.")
    if bundle.get("purpose") != ALLOWED_PURPOSE:
        _error(
            errors,
            "invalid_profile_purpose",
            "purpose",
            f"Named profiles are limited to {ALLOWED_PURPOSE}.",
        )

    subject = bundle.get("subject")
    if not isinstance(subject, dict):
        _error(errors, "missing_subject", "subject", "A subject object is required.")
    else:
        name = subject.get("displayName")
        if not isinstance(name, str) or len(name.strip()) < 2 or len(name.strip()) > 120:
            _error(errors, "invalid_display_name", "subject.displayName", "A real display name is required.")
        if subject.get("identityResolution") not in {
            "confirmed_directory_identity",
            "confirmed_ticket_identity",
        }:
            _error(
                errors,
                "identity_not_confirmed",
                "subject.identityResolution",
                "Identity must be resolved to a confirmed directory or ticket identity.",
            )
        if not isinstance(subject.get("identityFingerprint"), str) or not re.fullmatch(
            r"sha256:[0-9a-f]{64}",
            subject.get("identityFingerprint", ""),
        ):
            _error(
                errors,
                "invalid_identity_fingerprint",
                "subject.identityFingerprint",
                "A SHA-256 fingerprint of the connector-local opaque identity is required.",
            )
        if set(subject) - {"displayName", "identityResolution", "identityFingerprint"}:
            _error(
                errors,
                "identity_data_excess",
                "subject",
                "Only displayName, identityResolution, and identityFingerprint may cross the intake boundary.",
            )

    authorization = bundle.get("authorization")
    if not isinstance(authorization, dict):
        _error(errors, "missing_authorization", "authorization", "Authorization metadata is required.")
    else:
        _reject_unknown_fields(
            authorization,
            {
                "requesterHasLegitimateAccess",
                "subjectAuthoredOnly",
                "assistiveUseOnly",
                "humanReviewRequired",
                "noEmploymentDecisionUse",
                "privateOneToOneIncluded",
                "privateOneToOneUseApproved",
                "companySystemContentAuthorized",
                "codexProcessingAuthorized",
                "governanceBasis",
            },
            "authorization",
            errors,
        )
        required_true = (
            "requesterHasLegitimateAccess",
            "subjectAuthoredOnly",
            "assistiveUseOnly",
            "humanReviewRequired",
            "noEmploymentDecisionUse",
            "companySystemContentAuthorized",
            "codexProcessingAuthorized",
        )
        for field in required_true:
            if authorization.get(field) is not True:
                _error(
                    errors,
                    "authorization_gate_failed",
                    f"authorization.{field}",
                    f"{field} must be true.",
                )
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
                "Private one-to-one content requires explicit approval for assistive use.",
            )

    collection = bundle.get("collection")
    if not isinstance(collection, dict):
        _error(errors, "missing_collection", "collection", "Collection metadata is required.")
    else:
        _reject_unknown_fields(
            collection,
            {
                "sourceSystems",
                "coverageComplete",
                "windowStart",
                "windowEnd",
                "authoredMessageCount",
                "conversationCount",
                "contextCount",
                "activeDayCount",
                "excludedSensitiveMessageCount",
                "sensitiveCategoriesExcluded",
                "rawContentPersisted",
                "attachmentsProcessed",
                "externalModelProcessingUsed",
                "resolvedTicketCount",
                "resolutionOutcomeKnown",
            },
            "collection",
            errors,
        )
        sources = collection.get("sourceSystems")
        if not isinstance(sources, list) or not sources:
            _error(errors, "missing_source_systems", "collection.sourceSystems", "At least one source is required.")
        else:
            unknown_sources = sorted(set(sources) - ALLOWED_SOURCE_SYSTEMS)
            if unknown_sources:
                _error(
                    errors,
                    "unknown_source_system",
                    "collection.sourceSystems",
                    f"Unsupported sources: {', '.join(unknown_sources)}.",
                )
        for field in ("rawContentPersisted", "attachmentsProcessed"):
            if collection.get(field) is not False:
                _error(
                    errors,
                    "raw_data_boundary_failed",
                    f"collection.{field}",
                    f"{field} must be false.",
                )
        if not isinstance(collection.get("externalModelProcessingUsed"), bool):
            _error(
                errors,
                "missing_model_processing_disclosure",
                "collection.externalModelProcessingUsed",
                "externalModelProcessingUsed must be a boolean.",
            )
        exclusions = set(collection.get("sensitiveCategoriesExcluded") or [])
        missing_exclusions = sorted(REQUIRED_SENSITIVE_EXCLUSIONS - exclusions)
        if missing_exclusions:
            _error(
                errors,
                "sensitive_exclusions_missing",
                "collection.sensitiveCategoriesExcluded",
                f"Required exclusions are missing: {', '.join(missing_exclusions)}.",
            )
        _validate_nonnegative_int(collection, "authoredMessageCount", errors, "collection")
        _validate_nonnegative_int(collection, "conversationCount", errors, "collection")
        _validate_nonnegative_int(collection, "contextCount", errors, "collection")
        _validate_nonnegative_int(collection, "activeDayCount", errors, "collection")
        _validate_nonnegative_int(collection, "excludedSensitiveMessageCount", errors, "collection")
        if "resolved_support_ticket" in set(sources or []):
            _validate_nonnegative_int(collection, "resolvedTicketCount", errors, "collection")
            if collection.get("resolutionOutcomeKnown") is not True:
                _error(
                    errors,
                    "ticket_resolution_boundary_missing",
                    "collection.resolutionOutcomeKnown",
                    "Resolved-ticket observations must confirm that resolution outcome is known.",
                )
        if collection.get("coverageComplete") is not False:
            _error(
                errors,
                "coverage_overclaim",
                "collection.coverageComplete",
                "Connector-derived communication samples must declare coverageComplete false.",
            )
        start = _parse_datetime(collection.get("windowStart"), "collection.windowStart", errors)
        end = _parse_datetime(collection.get("windowEnd"), "collection.windowEnd", errors)
        if start and end and end < start:
            _error(errors, "invalid_collection_window", "collection.windowEnd", "windowEnd precedes windowStart.")

    observations = bundle.get("observations")
    if not isinstance(observations, list):
        _error(errors, "missing_observations", "observations", "Observations must be a list.")
    else:
        for index, observation in enumerate(observations):
            _validate_observation(observation, index, errors)

    _validate_context_evidence(
        bundle.get("contextEvidence", []),
        "contextEvidence",
        errors,
        required=False,
    )

    hypotheses = bundle.get("responseHypotheses", [])
    if not isinstance(hypotheses, list):
        _error(errors, "invalid_hypotheses", "responseHypotheses", "Response hypotheses must be a list.")
    else:
        for index, hypothesis in enumerate(hypotheses):
            _validate_hypothesis(hypothesis, index, errors)

    lexicon = bundle.get("privateLexicon", [])
    if not isinstance(lexicon, list):
        _error(errors, "invalid_private_lexicon", "privateLexicon", "Private lexicon must be a list.")
    else:
        for index, item in enumerate(lexicon):
            _validate_lexicon_item(item, index, errors)

    examples = bundle.get("privateExamples", [])
    if not isinstance(examples, list):
        _error(errors, "invalid_private_examples", "privateExamples", "Private examples must be a list.")
    else:
        for index, item in enumerate(examples):
            _validate_private_example(item, index, errors)

    return errors


def build_interaction_profile(bundle: dict[str, Any]) -> dict[str, Any]:
    """Build one non-diagnostic interaction-assistance profile."""

    errors = validate_observation_bundle(bundle)
    if errors:
        raise InteractionProfileBlockedError(errors)

    collection = bundle["collection"]
    eligible, readiness_reasons = _automatic_use_readiness(collection)
    window_end = _parse_iso_datetime(collection["windowEnd"])
    profile_id = f"interaction-profile-{uuid.uuid4().hex[:16]}"
    now = _now()
    bundle_context_evidence = _normalize_context_evidence(bundle.get("contextEvidence", []))
    observations = [
        _normalize_observation(item, bundle_context_evidence=bundle_context_evidence)
        for item in bundle["observations"]
    ]
    hypotheses = [_normalize_hypothesis(item) for item in bundle.get("responseHypotheses", [])]
    lexicon = [_normalize_lexicon_item(item) for item in bundle.get("privateLexicon", [])]
    examples = [_normalize_private_example(item) for item in bundle.get("privateExamples", [])]
    if not any(
        item["confidence"] in {"subject_confirmed", "context_supported"}
        for item in observations
    ):
        eligible = False
        readiness_reasons.append(
            "At least one pattern must be subject-confirmed or meet the support and consistency threshold."
        )
    profile = {
        "artifactType": "named_interaction_assistance_profile",
        "schemaVersion": 1,
        "profileId": profile_id,
        "displayName": bundle["subject"]["displayName"].strip(),
        "identityResolution": bundle["subject"]["identityResolution"],
        "_identityFingerprint": bundle["subject"]["identityFingerprint"],
        "_sourceCorpusDigest": _bundle_source_digest(bundle),
        "purpose": ALLOWED_PURPOSE,
        "governanceBoundary": {
            "basis": "user_asserted_company_policy",
            "independentlyVerified": False,
            "scope": "private internal assistive drafting",
        },
        "status": "active" if eligible else "collecting",
        "eligibleForAutomaticUse": eligible,
        "readinessReasons": readiness_reasons,
        "createdAt": now,
        "updatedAt": now,
        "expiresAt": (window_end + timedelta(days=PROFILE_TTL_DAYS)).isoformat(),
        "sourceSummary": _source_summary(collection),
        "observedCommunicationPatterns": observations,
        "likelyResponsePatterns": hypotheses,
        "privateLexicon": lexicon,
        "privateExamples": examples,
        "assistiveGuidance": _build_assistive_guidance(observations, hypotheses, lexicon, examples),
        "prohibitedUses": [
            "employment decisions or performance evaluation",
            "diagnosis or sensitive-trait inference",
            "ranking or comparison of people",
            "automatic sending or impersonation",
            "claims about exact future words, motives, or mental state",
        ],
        "evidenceBoundary": (
            "This is a private, context-specific assistive memory derived from observable communication patterns. "
            "It is not a psychological diagnosis, personality truth, employee evaluation, or reliable prediction "
            "of exact future behavior."
        ),
        "marketEvidenceCreated": False,
        "rawContentStored": False,
        "sourceBatchCount": 1,
    }
    profile["profileHash"] = _profile_hash(profile)
    return profile


def upsert_profile_store(
    store_path: str | Path,
    bundle: dict[str, Any],
    *,
    replace_existing: bool = False,
) -> dict[str, Any]:
    """Replace one identity's source snapshot in the encrypted profile store.

    Observation bundles are full snapshots. Replaying an identical bundle is
    idempotent, and a different snapshot replaces the prior snapshot so counts
    cannot accumulate merely because a refresh was repeated.
    """

    candidate = build_interaction_profile(bundle)
    store = _load_store(Path(store_path), missing_ok=True)
    name_key = _normalize_name(candidate["displayName"])
    fingerprint = candidate["_identityFingerprint"]
    existing = next(
        (profile for profile in store["profiles"] if profile.get("_identityFingerprint") == fingerprint),
        None,
    )
    name_collision = next(
        (
            profile
            for profile in store["profiles"]
            if _normalize_name(profile["displayName"]) == name_key
            and profile.get("_identityFingerprint") != fingerprint
        ),
        None,
    )
    if name_collision is not None:
        raise InteractionProfileBlockedError(
            [
                {
                    "code": "display_name_identity_collision",
                    "path": candidate["displayName"],
                    "message": "That display name already belongs to a different confirmed identity.",
                }
            ]
        )
    if existing is None:
        private_profile = deepcopy(candidate)
        private_profile["_sourceBatches"] = [_private_batch_record(bundle)]
        store["profiles"].append(private_profile)
        action = "created"
    else:
        if (
            existing.get("_sourceCorpusDigest")
            and existing.get("_sourceCorpusDigest") == candidate.get("_sourceCorpusDigest")
        ):
            return {
                "artifactType": "interaction_profile_store_result",
                "status": "unchanged",
                "profile": _public_profile(existing),
                "storeEncryption": CURRENT_ENCRYPTION,
                "rawContentStored": False,
            }
        candidate["profileId"] = existing["profileId"]
        candidate["createdAt"] = existing["createdAt"]
        candidate["updatedAt"] = _now()
        candidate["_sourceBatches"] = [_private_batch_record(bundle)]
        candidate["profileHash"] = _profile_hash(candidate)
        store["profiles"] = [
            candidate if profile.get("_identityFingerprint") == fingerprint else profile
            for profile in store["profiles"]
        ]
        action = "refreshed"

    store["updatedAt"] = _now()
    _save_store(Path(store_path), store)
    selected = next(profile for profile in store["profiles"] if profile.get("_identityFingerprint") == fingerprint)
    return {
        "artifactType": "interaction_profile_store_result",
        "status": action,
        "profile": _public_profile(selected),
        "storeEncryption": CURRENT_ENCRYPTION,
        "rawContentStored": False,
    }


def get_interaction_profile(
    store_path: str | Path,
    display_name: str,
    *,
    include_collecting: bool = False,
    expected_source_bundle: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return one public profile view by actual display name."""

    store = _load_store(Path(store_path))
    profile = _find_profile(store, display_name)
    _refresh_stale_state(profile)
    if expected_source_bundle is not None:
        expected_fingerprint = expected_source_bundle.get("subject", {}).get("identityFingerprint")
        expected_digest = _bundle_source_digest(expected_source_bundle)
        if (
            profile.get("_identityFingerprint") != expected_fingerprint
            or profile.get("_sourceCorpusDigest") != expected_digest
        ):
            raise InteractionProfileBlockedError(
                [
                    {
                        "code": "source_mismatch",
                        "path": display_name,
                        "message": (
                            "The stored profile does not match the current encrypted "
                            "communication corpus snapshot."
                        ),
                    }
                ]
            )
    if profile["status"] == "collecting" and not include_collecting:
        raise InteractionProfileBlockedError(
            [
                {
                    "code": "profile_not_ready",
                    "path": display_name,
                    "message": "Profile has not met the minimum evidence threshold for automatic use.",
                }
            ]
        )
    return _public_profile(profile)


def list_interaction_profiles(store_path: str | Path) -> dict[str, Any]:
    """List private profile names and readiness without exposing evidence details."""

    store = _load_store(Path(store_path), missing_ok=True)
    profiles: list[dict[str, Any]] = []
    for profile in store["profiles"]:
        _refresh_stale_state(profile)
        profiles.append(
            {
                "profileId": profile["profileId"],
                "displayName": profile["displayName"],
                "status": profile["status"],
                "eligibleForAutomaticUse": profile["eligibleForAutomaticUse"],
                "updatedAt": profile["updatedAt"],
                "expiresAt": profile["expiresAt"],
                "sourceBatchCount": profile.get("sourceBatchCount", 0),
            }
        )
    return {
        "artifactType": "interaction_profile_index",
        "profileCount": len(profiles),
        "profiles": sorted(profiles, key=lambda item: item["displayName"].casefold()),
        "storeEncryption": CURRENT_ENCRYPTION,
        "rawContentStored": False,
    }


def delete_interaction_profile(store_path: str | Path, display_name: str) -> dict[str, Any]:
    """Delete a named profile and all encrypted derived batches."""

    path = Path(store_path)
    store = _load_store(path)
    profile = _find_profile(store, display_name)
    profile_id = profile["profileId"]
    store["profiles"] = [item for item in store["profiles"] if item["profileId"] != profile_id]
    store["updatedAt"] = _now()
    _save_store(path, store)
    return {
        "artifactType": "interaction_profile_delete_result",
        "status": "deleted",
        "profileId": profile_id,
        "displayNameRemoved": True,
        "derivedBatchesRemoved": True,
    }


def invalidate_profile_batch(store_path: str | Path, bundle_id: str) -> dict[str, Any]:
    """Remove one source batch and recompute every affected profile."""

    path = Path(store_path)
    store = _load_store(path)
    affected: list[str] = []
    removed = 0
    retained_profiles: list[dict[str, Any]] = []
    for profile in store["profiles"]:
        before = list(profile.get("_sourceBatches", []))
        after = [item for item in before if item["bundleId"] != bundle_id]
        removed += len(before) - len(after)
        if len(after) == len(before):
            retained_profiles.append(profile)
            continue
        affected.append(profile["profileId"])
        if after:
            profile["_sourceBatches"] = after
            _rebuild_profile_from_batches(profile)
            retained_profiles.append(profile)
    if removed == 0:
        raise InteractionProfileBlockedError(
            [{"code": "unknown_bundle_id", "path": bundle_id, "message": "No profile batch matched that id."}]
        )
    store["profiles"] = retained_profiles
    store["updatedAt"] = _now()
    _save_store(path, store)
    return {
        "artifactType": "interaction_profile_invalidation_result",
        "status": "invalidated",
        "bundleId": bundle_id,
        "removedBatchCount": removed,
        "affectedProfileIds": affected,
        "profilesDeletedAfterInvalidation": len(affected) - sum(
            1 for profile in retained_profiles if profile["profileId"] in affected
        ),
    }


def profile_guidance(
    profile: dict[str, Any],
    *,
    context: str | None = None,
) -> dict[str, Any]:
    """Return the bounded context that analysis/rewrite may consume."""

    if profile.get("eligibleForAutomaticUse") is not True or profile.get("status") != "active":
        raise InteractionProfileBlockedError(
            [
                {
                    "code": "profile_not_active",
                    "path": profile.get("profileId", "profile"),
                    "message": "Only active, non-expired profiles may guide copy.",
                }
            ]
        )
    if context is not None and context not in ALLOWED_CONTEXTS:
        raise InteractionProfileBlockedError(
            [
                {
                    "code": "unknown_profile_context",
                    "path": str(context),
                    "message": "Interaction context is not supported.",
                }
            ]
        )
    observations = [
        item
        for item in profile["observedCommunicationPatterns"]
        if (
            item.get("confidence") in {"subject_confirmed", "context_supported"}
            if context is None
            else _observation_qualified_for_context(item, context)
        )
    ]
    hypotheses = [
        item
        for item in profile["likelyResponsePatterns"]
        if context is None or item.get("triggerClass") == context
    ]
    lexicon = [
        item
        for item in profile.get("privateLexicon", [])
        if context is None or context in item.get("contexts", [])
    ]
    examples = [
        item
        for item in profile.get("privateExamples", [])
        if context is None or context in item.get("contexts", [])
    ]
    context_matched = context is None or bool(observations or hypotheses or lexicon or examples)
    return {
        "artifactType": "interaction_assistance_guidance",
        "profileId": profile["profileId"],
        "displayName": profile["displayName"],
        "purpose": ALLOWED_PURPOSE,
        "guidance": _build_assistive_guidance(observations, hypotheses, lexicon, examples),
        "likelyResponsePatterns": deepcopy(hypotheses),
        "observedCommunicationPatterns": deepcopy(observations),
        "matchedContext": context,
        "contextMatched": context_matched,
        "profileHash": profile["profileHash"],
        "expiresAt": profile["expiresAt"],
        "humanReviewRequired": True,
        "automaticSendingAllowed": False,
        "evidenceBoundary": profile["evidenceBoundary"],
        "marketEvidenceCreated": False,
    }


def infer_interaction_context(
    brief: dict[str, Any],
    *,
    explicit_context: str | None = None,
) -> str:
    """Map a message brief to the nearest controlled communication context."""

    if explicit_context is not None:
        if explicit_context not in ALLOWED_CONTEXTS:
            raise InteractionProfileBlockedError(
                [
                    {
                        "code": "unknown_profile_context",
                        "path": explicit_context,
                        "message": "Interaction context is not supported.",
                    }
                ]
            )
        return explicit_context
    text = " ".join(
        str(brief.get(field) or "")
        for field in (
            "sourceText",
            "messageGoal",
            "documentArchetype",
            "communicationIntent",
            "desiredAction",
            "channel",
        )
    ).casefold()
    audience_text = str(brief.get("targetAudience") or "").casefold()
    if any(term in text for term in ("incident", "outage", "service down", "sev1", "sev 1")):
        return "incident_response"
    if any(term in text for term in ("support request", "helpdesk", "ticket", "troubleshoot")):
        return "support_request"
    if any(term in text for term in ("meeting recap", "meeting notes", "follow-up", "follow up")):
        return "meeting_follow_up"
    if brief.get("decisionRequired") is True or any(
        term in text for term in ("decision needed", "approve", "approval", "choose an option")
    ):
        return "decision_request"
    if any(
        term in f"{text} {audience_text}"
        for term in ("executive", "leadership", "c-suite", "c suite", "board", "cio", "ceo")
    ):
        return "executive_update"
    if any(term in text for term in ("project plan", "roadmap", "milestone", "workstream", "implementation plan")):
        return "project_planning"
    if any(term in text for term in ("status update", "progress update", "for awareness", "fyi")):
        return "status_update"
    if any(
        term in text
        for term in ("architecture", "technical", "deployment", "configure", "network", "security", "azure")
    ):
        return "technical_discussion"
    return "informal_coordination"


def _validate_observation(
    observation: Any,
    index: int,
    errors: list[dict[str, str]],
) -> None:
    path = f"observations[{index}]"
    if not isinstance(observation, dict):
        _error(errors, "invalid_observation", path, "Observation must be an object.")
        return
    if observation.get("dimension") not in ALLOWED_DIMENSIONS:
        _error(errors, "invalid_dimension", f"{path}.dimension", "Unknown communication dimension.")
    if observation.get("basis") not in ALLOWED_BASIS:
        _error(errors, "invalid_observation_basis", f"{path}.basis", "Unknown observation basis.")
    if observation.get("basis") == "explicit_preference" and observation.get("subjectConfirmed") is not True:
        _error(
            errors,
            "explicit_preference_unconfirmed",
            f"{path}.subjectConfirmed",
            "Explicit preferences require subject confirmation.",
        )
    _validate_count_pair(observation, path, errors)
    _validate_contexts(observation.get("contexts"), f"{path}.contexts", errors)
    _validate_context_evidence(
        observation.get("contextEvidence", []),
        f"{path}.contextEvidence",
        errors,
        required=False,
    )
    observation_contexts = set(observation.get("contexts") or [])
    for evidence_index, record in enumerate(observation.get("contextEvidence") or []):
        if (
            isinstance(record, dict)
            and record.get("context") in ALLOWED_CONTEXTS
            and record.get("context") not in observation_contexts
        ):
            _error(
                errors,
                "context_evidence_scope_mismatch",
                f"{path}.contextEvidence[{evidence_index}].context",
                "Observation context evidence must match one of the observation contexts.",
            )
    _validate_sources(observation.get("sourceSystems"), f"{path}.sourceSystems", errors)
    dimension = observation.get("dimension")
    tendency = observation.get("tendencyCode")
    if isinstance(dimension, str) and tendency not in TENDENCY_CATALOG.get(dimension, {}):
        _error(
            errors,
            "invalid_tendency_code",
            f"{path}.tendencyCode",
            "Tendency code is not valid for the selected dimension.",
        )
    allowed_fields = {
        "dimension",
        "tendencyCode",
        "basis",
        "subjectConfirmed",
        "supportCount",
        "contradictionCount",
        "contexts",
        "contextEvidence",
        "sourceSystems",
        "firstObservedAt",
        "lastObservedAt",
    }
    unknown_fields = sorted(set(observation) - allowed_fields)
    if unknown_fields:
        _error(
            errors,
            "free_text_or_unknown_observation_field",
            path,
            f"Observation contains unsupported fields: {', '.join(unknown_fields)}.",
        )
    _parse_datetime(observation.get("firstObservedAt"), f"{path}.firstObservedAt", errors)
    _parse_datetime(observation.get("lastObservedAt"), f"{path}.lastObservedAt", errors)


def _validate_hypothesis(
    hypothesis: Any,
    index: int,
    errors: list[dict[str, str]],
) -> None:
    path = f"responseHypotheses[{index}]"
    if not isinstance(hypothesis, dict):
        _error(errors, "invalid_hypothesis", path, "Response hypothesis must be an object.")
        return
    _validate_count_pair(hypothesis, path, errors, minimum_support=5)
    _validate_contexts(hypothesis.get("contexts"), f"{path}.contexts", errors)
    _validate_sources(hypothesis.get("sourceSystems"), f"{path}.sourceSystems", errors)
    if hypothesis.get("triggerClass") not in ALLOWED_CONTEXTS:
        _error(errors, "invalid_trigger_class", f"{path}.triggerClass", "Unknown trigger class.")
    if hypothesis.get("responseClass") not in ALLOWED_RESPONSE_CLASSES:
        _error(errors, "invalid_response_class", f"{path}.responseClass", "Unknown response class.")
    allowed_fields = {
        "triggerClass",
        "responseClass",
        "supportCount",
        "contradictionCount",
        "contexts",
        "sourceSystems",
    }
    unknown_fields = sorted(set(hypothesis) - allowed_fields)
    if unknown_fields:
        _error(
            errors,
            "free_text_or_unknown_hypothesis_field",
            path,
            f"Response hypothesis contains unsupported fields: {', '.join(unknown_fields)}.",
        )


def _validate_lexicon_item(
    item: Any,
    index: int,
    errors: list[dict[str, str]],
) -> None:
    path = f"privateLexicon[{index}]"
    if not isinstance(item, dict):
        _error(errors, "invalid_lexicon_item", path, "Private lexicon item must be an object.")
        return
    allowed_fields = {"term", "category", "supportCount", "contexts", "sourceSystems"}
    unknown_fields = sorted(set(item) - allowed_fields)
    if unknown_fields:
        _error(
            errors,
            "unknown_lexicon_field",
            path,
            f"Private lexicon item contains unsupported fields: {', '.join(unknown_fields)}.",
        )
    term = item.get("term")
    if not isinstance(term, str) or not term.strip():
        _error(errors, "invalid_lexicon_term", f"{path}.term", "A short recurring term is required.")
    else:
        stripped = term.strip()
        if len(stripped) > 64 or len(stripped.split()) > 6 or "\n" in stripped or "\r" in stripped:
            _error(
                errors,
                "lexicon_term_too_long",
                f"{path}.term",
                "Private lexicon entries are limited to six words and 64 characters.",
            )
        if (
            EMAIL_PATTERN.search(stripped)
            or PHONE_PATTERN.search(stripped)
            or SSN_PATTERN.search(stripped)
            or UUID_PATTERN.search(stripped)
        ):
            _error(errors, "pii_in_lexicon", f"{path}.term", "Private lexicon terms must not contain identifiers.")
        if LEXICON_SENSITIVE_PATTERN.search(stripped):
            _error(
                errors,
                "sensitive_term_in_lexicon",
                f"{path}.term",
                "Sensitive-category wording cannot be retained in a communication profile.",
            )
    if item.get("category") not in ALLOWED_LEXICON_CATEGORIES:
        _error(errors, "invalid_lexicon_category", f"{path}.category", "Unknown lexicon category.")
    _validate_nonnegative_int(item, "supportCount", errors, path)
    if isinstance(item.get("supportCount"), int) and item["supportCount"] < 3:
        _error(
            errors,
            "insufficient_lexicon_support",
            f"{path}.supportCount",
            "A private lexicon term requires at least three observations.",
        )
    _validate_contexts(item.get("contexts"), f"{path}.contexts", errors)
    _validate_sources(item.get("sourceSystems"), f"{path}.sourceSystems", errors)


def _validate_private_example(
    item: Any,
    index: int,
    errors: list[dict[str, str]],
) -> None:
    path = f"privateExamples[{index}]"
    if not isinstance(item, dict):
        _error(errors, "invalid_private_example", path, "Private example must be an object.")
        return
    allowed_fields = {
        "exampleText",
        "exampleKind",
        "outcomeClass",
        "similarExample Organizationunt",
        "contexts",
        "sourceSystems",
        "observedAt",
    }
    unknown_fields = sorted(set(item) - allowed_fields)
    if unknown_fields:
        _error(
            errors,
            "unknown_private_example_field",
            path,
            f"Private example contains unsupported fields: {', '.join(unknown_fields)}.",
        )
    text = item.get("exampleText")
    if not isinstance(text, str) or not text.strip():
        _error(errors, "invalid_private_example_text", f"{path}.exampleText", "Example text is required.")
    else:
        stripped = text.strip()
        if len(stripped) > 600:
            _error(
                errors,
                "private_example_too_long",
                f"{path}.exampleText",
                "Representative examples are limited to 600 characters.",
            )
        if EMAIL_PATTERN.search(stripped) or PHONE_PATTERN.search(stripped) or SSN_PATTERN.search(stripped):
            _error(
                errors,
                "pii_in_private_example",
                f"{path}.exampleText",
                "Representative examples must remove contact and government identifier values.",
            )
    if item.get("exampleKind") not in ALLOWED_EXAMPLE_KINDS:
        _error(errors, "invalid_example_kind", f"{path}.exampleKind", "Unknown private example kind.")
    if item.get("outcomeClass") not in ALLOWED_OUTCOME_CLASSES:
        _error(errors, "invalid_outcome_class", f"{path}.outcomeClass", "Unknown outcome class.")
    _validate_nonnegative_int(item, "similarExample Organizationunt", errors, path)
    if isinstance(item.get("similarExample Organizationunt"), int) and item["similarExample Organizationunt"] < 2:
        _error(
            errors,
            "insufficient_example_support",
            f"{path}.similarExample Organizationunt",
            "A retained example requires at least one similar exchange.",
        )
    _validate_contexts(item.get("contexts"), f"{path}.contexts", errors)
    _validate_sources(item.get("sourceSystems"), f"{path}.sourceSystems", errors)
    _parse_datetime(item.get("observedAt"), f"{path}.observedAt", errors)


def _validate_count_pair(
    item: dict[str, Any],
    path: str,
    errors: list[dict[str, str]],
    *,
    minimum_support: int = 3,
) -> None:
    _validate_nonnegative_int(item, "supportCount", errors, path)
    _validate_nonnegative_int(item, "contradictionCount", errors, path)
    if isinstance(item.get("supportCount"), int) and item["supportCount"] < minimum_support:
        _error(
            errors,
            "insufficient_observation_support",
            f"{path}.supportCount",
            f"Each retained pattern requires at least {minimum_support} supporting messages.",
        )


def _validate_contexts(value: Any, path: str, errors: list[dict[str, str]]) -> None:
    if not isinstance(value, list) or not value:
        _error(errors, "missing_contexts", path, "At least one context is required.")
        return
    unknown = sorted(set(value) - ALLOWED_CONTEXTS)
    if unknown:
        _error(errors, "unknown_context", path, f"Unsupported contexts: {', '.join(unknown)}.")


def _validate_context_evidence(
    value: Any,
    path: str,
    errors: list[dict[str, str]],
    *,
    required: bool,
) -> None:
    if value is None and not required:
        return
    if not isinstance(value, list):
        _error(errors, "invalid_context_evidence", path, "Context evidence must be a list.")
        return
    if required and not value:
        _error(errors, "missing_context_evidence", path, "At least one context evidence record is required.")
        return
    seen: set[str] = set()
    for index, record in enumerate(value):
        record_path = f"{path}[{index}]"
        if not isinstance(record, dict):
            _error(errors, "invalid_context_evidence", record_path, "Context evidence must be an object.")
            continue
        unknown = sorted(
            set(record) - {"context", "supportCount", "contradictionCount", "sampleSize"}
        )
        if unknown:
            _error(
                errors,
                "unknown_context_evidence_field",
                record_path,
                f"Unsupported context evidence fields: {', '.join(unknown)}.",
            )
        context = record.get("context")
        if context not in ALLOWED_CONTEXTS:
            _error(errors, "unknown_context", f"{record_path}.context", "Unsupported context.")
        elif context in seen:
            _error(
                errors,
                "duplicate_context_evidence",
                f"{record_path}.context",
                "A context may appear only once in the same evidence list.",
            )
        else:
            seen.add(context)
        for field in ("supportCount", "contradictionCount", "sampleSize"):
            _validate_nonnegative_int(record, field, errors, record_path)
        support = record.get("supportCount")
        contradictions = record.get("contradictionCount")
        sample_size = record.get("sampleSize")
        if (
            isinstance(support, int)
            and isinstance(contradictions, int)
            and isinstance(sample_size, int)
            and sample_size < support + contradictions
        ):
            _error(
                errors,
                "context_sample_too_small",
                f"{record_path}.sampleSize",
                "sampleSize cannot be smaller than supportCount plus contradictionCount.",
            )


def _validate_sources(value: Any, path: str, errors: list[dict[str, str]]) -> None:
    if not isinstance(value, list) or not value:
        _error(errors, "missing_observation_sources", path, "At least one source system is required.")
        return
    unknown = sorted(set(value) - ALLOWED_SOURCE_SYSTEMS)
    if unknown:
        _error(errors, "unknown_source_system", path, f"Unsupported sources: {', '.join(unknown)}.")


def _reject_raw_content_keys(value: Any, path: str, errors: list[dict[str, str]]) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            normalized = re.sub(r"[^a-z0-9]", "", str(key).casefold())
            if normalized in RAW_CONTENT_KEYS and not (path == "$" and key == "subject"):
                _error(
                    errors,
                    "raw_content_field_prohibited",
                    f"{path}.{key}",
                    "Raw communication content and identifiers may not enter the profile artifact.",
                )
            _reject_raw_content_keys(child, f"{path}.{key}", errors)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _reject_raw_content_keys(child, f"{path}[{index}]", errors)


def _reject_unknown_fields(
    value: dict[str, Any],
    allowed: set[str],
    path: str,
    errors: list[dict[str, str]],
) -> None:
    unknown = sorted(set(value) - allowed)
    if unknown:
        _error(
            errors,
            "unknown_profile_field",
            path,
            f"Unsupported fields are not allowed: {', '.join(unknown)}.",
        )


def _automatic_use_readiness(collection: dict[str, Any]) -> tuple[bool, list[str]]:
    requirements = (
        ("authoredMessageCount", MIN_AUTHORED_MESSAGES),
        ("conversationCount", MIN_CONVERSATIONS),
        ("contextCount", MIN_CONTEXTS),
        ("activeDayCount", MIN_ACTIVE_DAYS),
    )
    reasons = [
        f"{field} requires at least {minimum}; observed {int(collection.get(field, 0))}."
        for field, minimum in requirements
        if int(collection.get(field, 0)) < minimum
    ]
    start = _parse_iso_datetime(collection["windowStart"])
    end = _parse_iso_datetime(collection["windowEnd"])
    window_days = max(0, (end - start).days)
    if window_days < MIN_WINDOW_DAYS:
        reasons.append(f"Collection window requires at least {MIN_WINDOW_DAYS} days; observed {window_days}.")
    return not reasons, reasons


def _normalize_observation(
    item: dict[str, Any],
    *,
    bundle_context_evidence: dict[str, dict[str, int | str]] | None = None,
) -> dict[str, Any]:
    catalog = TENDENCY_CATALOG[item["dimension"]][item["tendencyCode"]]
    context_evidence = _observation_context_evidence(
        item,
        bundle_context_evidence=bundle_context_evidence or {},
    )
    normalized = {
        "dimension": item["dimension"],
        "tendencyCode": item["tendencyCode"],
        "basis": item["basis"],
        "description": catalog["description"],
        "likelyImpact": catalog["impact"],
        "suggestedAdjustment": catalog["adjustment"],
        "supportCount": item["supportCount"],
        "contradictionCount": item["contradictionCount"],
        "contexts": sorted(set(item["contexts"])),
        "contextEvidence": context_evidence,
        "sourceSystems": sorted(set(item["sourceSystems"])),
        "firstObservedAt": _parse_iso_datetime(item["firstObservedAt"]).isoformat(),
        "lastObservedAt": _parse_iso_datetime(item["lastObservedAt"]).isoformat(),
        "subjectConfirmed": bool(item.get("subjectConfirmed", False)),
    }
    normalized["confidenceByContext"] = {
        record["context"]: _context_confidence(
            record,
            subject_confirmed=normalized["subjectConfirmed"],
        )
        for record in context_evidence
    }
    normalized["confidence"] = _confidence(normalized)
    return normalized


def _normalize_hypothesis(item: dict[str, Any]) -> dict[str, Any]:
    catalog = RESPONSE_CATALOG[item["responseClass"]]
    return {
        "triggerClass": item["triggerClass"],
        "responseClass": item["responseClass"],
        "likelyResponsePattern": catalog["pattern"],
        "draftingImplication": catalog["implication"],
        "supportCount": item["supportCount"],
        "contradictionCount": item["contradictionCount"],
        "contexts": sorted(set(item["contexts"])),
        "sourceSystems": sorted(set(item["sourceSystems"])),
        "confidence": _hypothesis_confidence(item),
        "predictionBoundary": "Likely pattern in the observed contexts, not a prediction of exact words or behavior.",
    }


def _normalize_lexicon_item(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "term": item["term"].strip(),
        "category": item["category"],
        "supportCount": item["supportCount"],
        "contexts": sorted(set(item["contexts"])),
        "sourceSystems": sorted(set(item["sourceSystems"])),
    }


def _normalize_private_example(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "exampleText": item["exampleText"].strip(),
        "exampleKind": item["exampleKind"],
        "outcomeClass": item["outcomeClass"],
        "similarExample Organizationunt": item["similarExample Organizationunt"],
        "contexts": sorted(set(item["contexts"])),
        "sourceSystems": sorted(set(item["sourceSystems"])),
        "observedAt": _parse_iso_datetime(item["observedAt"]).isoformat(),
        "useBoundary": "Representative prior wording, not a forecast or authorized impersonation.",
    }


def _confidence(item: dict[str, Any]) -> str:
    if item.get("basis") == "explicit_preference" and item.get("subjectConfirmed") is True:
        return "subject_confirmed"
    if any(
        confidence == "context_supported"
        for confidence in item.get("confidenceByContext", {}).values()
    ):
        return "context_supported"
    return "tentative"


def _context_confidence(
    record: dict[str, Any],
    *,
    subject_confirmed: bool,
) -> str:
    if subject_confirmed:
        return "subject_confirmed"
    support = int(record.get("supportCount", 0))
    contradictions = int(record.get("contradictionCount", 0))
    sample_size = int(record.get("sampleSize", 0))
    total = support + contradictions
    if (
        support >= MIN_PATTERN_SUPPORT
        and sample_size >= total
        and (support / total if total else 0.0) >= MIN_PATTERN_CONSISTENCY
    ):
        return "context_supported"
    return "tentative"


def _normalize_context_evidence(value: Any) -> dict[str, dict[str, int | str]]:
    if not isinstance(value, list):
        return {}
    return {
        str(record["context"]): {
            "context": str(record["context"]),
            "supportCount": int(record["supportCount"]),
            "contradictionCount": int(record["contradictionCount"]),
            "sampleSize": int(record["sampleSize"]),
        }
        for record in value
        if isinstance(record, dict)
        and record.get("context") in ALLOWED_CONTEXTS
        and all(isinstance(record.get(field), int) for field in ("supportCount", "contradictionCount", "sampleSize"))
    }


def _observation_context_evidence(
    item: dict[str, Any],
    *,
    bundle_context_evidence: dict[str, dict[str, int | str]],
) -> list[dict[str, Any]]:
    explicit = _normalize_context_evidence(item.get("contextEvidence", []))
    contexts = sorted(set(item.get("contexts") or []))
    records: list[dict[str, Any]] = []
    for context in contexts:
        record = explicit.get(context)
        if record is None and len(contexts) == 1:
            support = int(item.get("supportCount", 0))
            contradictions = int(item.get("contradictionCount", 0))
            record = {
                "context": context,
                "supportCount": support,
                "contradictionCount": contradictions,
                "sampleSize": support + contradictions,
            }
        if record is None:
            continue
        aggregate = bundle_context_evidence.get(context)
        if aggregate is not None:
            record = deepcopy(record)
            record["supportCount"] = min(
                int(record["supportCount"]),
                int(aggregate["supportCount"]),
            )
            record["contradictionCount"] = max(
                int(record["contradictionCount"]),
                int(aggregate["contradictionCount"]),
            )
            record["sampleSize"] = min(
                int(record["sampleSize"]),
                int(aggregate["sampleSize"]),
            )
        records.append(record)
    return records


def _hypothesis_confidence(item: dict[str, Any]) -> str:
    """Score a response pattern within its trigger context.

    Unlike a general communication tendency, a response hypothesis is already
    conditioned on one trigger class. Requiring two contexts would make every
    correctly scoped hypothesis permanently tentative.
    """

    support = int(item.get("supportCount", 0))
    contradictions = int(item.get("contradictionCount", 0))
    total = support + contradictions
    if support >= MIN_PATTERN_SUPPORT and (support / total if total else 0.0) >= MIN_PATTERN_CONSISTENCY:
        return "context_supported"
    return "tentative"


def _observation_qualified_for_context(item: dict[str, Any], context: str) -> bool:
    if context not in item.get("contexts", []):
        return False
    if item.get("basis") == "explicit_preference" and item.get("subjectConfirmed") is True:
        return True
    confidence_by_context = item.get("confidenceByContext")
    if isinstance(confidence_by_context, dict) and confidence_by_context:
        return confidence_by_context.get(context) == "context_supported"
    return (
        len(set(item.get("contexts") or [])) == 1
        and item.get("confidence") in {"subject_confirmed", "context_supported"}
    )


def _build_assistive_guidance(
    observations: list[dict[str, Any]],
    hypotheses: list[dict[str, Any]],
    lexicon: list[dict[str, Any]],
    examples: list[dict[str, Any]],
) -> dict[str, Any]:
    qualified = [
        item
        for item in observations
        if item["confidence"] in {"subject_confirmed", "context_supported"}
    ]
    ranked = sorted(
        qualified,
        key=lambda item: (
            item["confidence"] == "subject_confirmed",
            item["confidence"] == "context_supported",
            item["supportCount"] - item["contradictionCount"],
        ),
        reverse=True,
    )
    adjustments = [item["suggestedAdjustment"] for item in ranked[:6]]
    likely_questions = [
        item["likelyResponsePattern"]
        for item in hypotheses
        if item["confidence"] == "context_supported"
    ][:5]
    preferred_terms = [
        item["term"]
        for item in lexicon
        if item["category"] in {"preferred_term", "decision_phrase"}
    ][:12]
    terms_to_avoid = [item["term"] for item in lexicon if item["category"] == "term_to_avoid"][:12]
    return {
        "draftingAdjustments": adjustments,
        "likelyQuestionsOrReactions": likely_questions,
        "preferredTerminology": preferred_terms,
        "terminologyToAvoid": terms_to_avoid,
        "representativeExamples": sorted(
            examples,
            key=lambda item: item["similarExample Organizationunt"],
            reverse=True,
        )[:8],
        "useRules": [
            "Apply only when the current communication context matches the recorded contexts.",
            "Prefer subject-confirmed preferences over behavioral hypotheses.",
            "Show the user which observations shaped the draft.",
            "Require human review before sending or publishing.",
            "Treat contradictions as uncertainty, not noise.",
        ],
    }


def _private_batch_record(bundle: dict[str, Any]) -> dict[str, Any]:
    bundle_context_evidence = _normalize_context_evidence(bundle.get("contextEvidence", []))
    return {
        "bundleId": bundle["bundleId"],
        "sourceCorpusDigest": _bundle_source_digest(bundle),
        "collection": deepcopy(bundle["collection"]),
        "observations": [
            _normalize_observation(item, bundle_context_evidence=bundle_context_evidence)
            for item in bundle["observations"]
        ],
        "responseHypotheses": [_normalize_hypothesis(item) for item in bundle.get("responseHypotheses", [])],
        "privateLexicon": [_normalize_lexicon_item(item) for item in bundle.get("privateLexicon", [])],
        "privateExamples": [_normalize_private_example(item) for item in bundle.get("privateExamples", [])],
    }


def _rebuild_profile_from_batches(profile: dict[str, Any]) -> None:
    batches = profile["_sourceBatches"]
    observations: dict[tuple[str, str, tuple[str, ...]], dict[str, Any]] = {}
    hypotheses: dict[tuple[str, tuple[str, ...]], dict[str, Any]] = {}
    lexicon: dict[tuple[str, str, tuple[str, ...]], dict[str, Any]] = {}
    examples: dict[tuple[str, str, tuple[str, ...]], dict[str, Any]] = {}
    for batch in batches:
        for item in batch["observations"]:
            key = (item["dimension"], item["tendencyCode"], tuple(item["contexts"]))
            if key not in observations:
                observations[key] = deepcopy(item)
            else:
                target = observations[key]
                target["supportCount"] += item["supportCount"]
                target["contradictionCount"] += item["contradictionCount"]
                target["sourceSystems"] = sorted(set(target["sourceSystems"]) | set(item["sourceSystems"]))
                target["firstObservedAt"] = min(target["firstObservedAt"], item["firstObservedAt"])
                target["lastObservedAt"] = max(target["lastObservedAt"], item["lastObservedAt"])
                target["subjectConfirmed"] = target["subjectConfirmed"] or item["subjectConfirmed"]
                target["contextEvidence"] = _merge_context_evidence(
                    target.get("contextEvidence", []),
                    item.get("contextEvidence", []),
                )
                target["confidenceByContext"] = {
                    record["context"]: _context_confidence(
                        record,
                        subject_confirmed=target["subjectConfirmed"],
                    )
                    for record in target["contextEvidence"]
                }
                target["confidence"] = _confidence(target)
        for item in batch["responseHypotheses"]:
            key = (item["triggerClass"], item["responseClass"], tuple(item["contexts"]))
            if key not in hypotheses:
                hypotheses[key] = deepcopy(item)
            else:
                target = hypotheses[key]
                target["supportCount"] += item["supportCount"]
                target["contradictionCount"] += item["contradictionCount"]
                target["sourceSystems"] = sorted(set(target["sourceSystems"]) | set(item["sourceSystems"]))
                target["confidence"] = _hypothesis_confidence(target)
        for item in batch.get("privateLexicon", []):
            key = (item["category"], item["term"].casefold(), tuple(item["contexts"]))
            if key not in lexicon:
                lexicon[key] = deepcopy(item)
            else:
                target = lexicon[key]
                target["supportCount"] += item["supportCount"]
                target["sourceSystems"] = sorted(set(target["sourceSystems"]) | set(item["sourceSystems"]))
        for item in batch.get("privateExamples", []):
            key = (item["exampleKind"], item["exampleText"].casefold(), tuple(item["contexts"]))
            if key not in examples:
                examples[key] = deepcopy(item)
            else:
                target = examples[key]
                target["similarExample Organizationunt"] += item["similarExample Organizationunt"]
                target["sourceSystems"] = sorted(set(target["sourceSystems"]) | set(item["sourceSystems"]))
                target["observedAt"] = max(target["observedAt"], item["observedAt"])

    collections = [batch["collection"] for batch in batches]
    aggregate_collection = {
        "sourceSystems": sorted(
            {source for collection in collections for source in collection.get("sourceSystems", [])}
        ),
        "windowStart": min(collection["windowStart"] for collection in collections),
        "windowEnd": max(collection["windowEnd"] for collection in collections),
        "authoredMessageCount": sum(int(collection.get("authoredMessageCount", 0)) for collection in collections),
        "conversationCount": sum(int(collection.get("conversationCount", 0)) for collection in collections),
        "contextCount": len(
            {context for item in observations.values() for context in item.get("contexts", [])}
        ),
        "activeDayCount": sum(int(collection.get("activeDayCount", 0)) for collection in collections),
        "excludedSensitiveMessageCount": sum(
            int(collection.get("excludedSensitiveMessageCount", 0)) for collection in collections
        ),
        "resolvedTicketCount": sum(int(collection.get("resolvedTicketCount", 0)) for collection in collections),
    }
    eligible, readiness_reasons = _automatic_use_readiness(aggregate_collection)
    if not any(
        item["confidence"] in {"subject_confirmed", "context_supported"}
        for item in observations.values()
    ):
        eligible = False
        readiness_reasons.append(
            "At least one pattern must be subject-confirmed or meet the support and consistency threshold."
        )
    window_end = _parse_iso_datetime(aggregate_collection["windowEnd"])
    profile["status"] = "active" if eligible else "collecting"
    profile["eligibleForAutomaticUse"] = eligible
    profile["readinessReasons"] = readiness_reasons
    profile["updatedAt"] = _now()
    profile["expiresAt"] = (window_end + timedelta(days=PROFILE_TTL_DAYS)).isoformat()
    profile["sourceSummary"] = _source_summary(aggregate_collection)
    profile["observedCommunicationPatterns"] = list(observations.values())
    profile["likelyResponsePatterns"] = list(hypotheses.values())
    profile["privateLexicon"] = list(lexicon.values())
    profile["privateExamples"] = list(examples.values())
    profile["assistiveGuidance"] = _build_assistive_guidance(
        profile["observedCommunicationPatterns"],
        profile["likelyResponsePatterns"],
        profile["privateLexicon"],
        profile["privateExamples"],
    )
    profile["sourceBatchCount"] = len(batches)
    profile["_sourceCorpusDigest"] = (
        batches[0].get("sourceCorpusDigest")
        if len(batches) == 1
        else _digest_values(batch.get("sourceCorpusDigest", "") for batch in batches)
    )
    profile["profileHash"] = _profile_hash(profile)


def _source_summary(collection: dict[str, Any]) -> dict[str, Any]:
    return {
        "sourceSystems": sorted(set(collection.get("sourceSystems", []))),
        "windowStart": collection["windowStart"],
        "windowEnd": collection["windowEnd"],
        "authoredMessageCount": int(collection.get("authoredMessageCount", 0)),
        "conversationCount": int(collection.get("conversationCount", 0)),
        "contextCount": int(collection.get("contextCount", 0)),
        "activeDayCount": int(collection.get("activeDayCount", 0)),
        "excludedSensitiveMessageCount": int(collection.get("excludedSensitiveMessageCount", 0)),
        "resolvedTicketCount": int(collection.get("resolvedTicketCount", 0)),
        "coverageComplete": False,
        "rawContentPersisted": False,
        "attachmentsProcessed": False,
        "externalModelProcessingUsed": bool(collection.get("externalModelProcessingUsed", False)),
    }


def _bundle_source_digest(bundle: dict[str, Any]) -> str:
    payload = {
        key: value
        for key, value in bundle.items()
        if key not in {"bundleId"}
    }
    canonical = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return f"sha256:{hashlib.sha256(canonical.encode('utf-8')).hexdigest()}"


def _digest_values(values: Any) -> str:
    canonical = "|".join(sorted(str(value) for value in values if value))
    return f"sha256:{hashlib.sha256(canonical.encode('utf-8')).hexdigest()}"


def _merge_context_evidence(
    left: list[dict[str, Any]],
    right: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    merged = {
        record["context"]: deepcopy(record)
        for record in left
    }
    for record in right:
        context = record["context"]
        if context not in merged:
            merged[context] = deepcopy(record)
            continue
        target = merged[context]
        target["supportCount"] += int(record["supportCount"])
        target["contradictionCount"] += int(record["contradictionCount"])
        target["sampleSize"] += int(record["sampleSize"])
    return [merged[context] for context in sorted(merged)]


def _public_profile(profile: dict[str, Any]) -> dict[str, Any]:
    return {key: deepcopy(value) for key, value in profile.items() if not key.startswith("_")}


def _profile_hash(profile: dict[str, Any]) -> str:
    payload = {key: value for key, value in profile.items() if key not in {"profileHash", "_sourceBatches"}}
    canonical = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return f"sha256:{hashlib.sha256(canonical.encode('utf-8')).hexdigest()}"


def _refresh_stale_state(profile: dict[str, Any]) -> None:
    expires = _parse_iso_datetime(profile["expiresAt"])
    if expires < datetime.now(timezone.utc):
        profile["status"] = "stale"
        profile["eligibleForAutomaticUse"] = False


def _find_profile(store: dict[str, Any], display_name: str) -> dict[str, Any]:
    key = _normalize_name(display_name)
    matches = [profile for profile in store["profiles"] if _normalize_name(profile["displayName"]) == key]
    if not matches:
        raise InteractionProfileBlockedError(
            [{"code": "profile_not_found", "path": display_name, "message": "No matching named profile exists."}]
        )
    if len(matches) > 1:
        raise InteractionProfileBlockedError(
            [
                {
                    "code": "ambiguous_profile_name",
                    "path": display_name,
                    "message": "More than one profile matches this display name.",
                }
            ]
        )
    return matches[0]


def _new_store() -> dict[str, Any]:
    now = _now()
    return {
        "artifactType": "mindfront_private_interaction_profile_store",
        "schemaVersion": 1,
        "createdAt": now,
        "updatedAt": now,
        "profiles": [],
        "dataBoundary": (
            "Installation-local encrypted assistive memory. No raw message text, attachments, subjects, "
            "source-system message identifiers, or normal Mindfront history artifacts."
        ),
    }


def _load_store(path: Path, *, missing_ok: bool = False) -> dict[str, Any]:
    if not path.exists():
        if missing_ok:
            return _new_store()
        raise InteractionProfileBlockedError(
            [{"code": "profile_store_missing", "path": str(path), "message": "Profile store does not exist."}]
        )
    try:
        envelope = json.loads(path.read_text(encoding="utf-8"))
        payload = decrypt_envelope(
            envelope,
            expected_artifact_type="mindfront_encrypted_profile_store",
        )
        store = json.loads(payload.decode("utf-8"))
        if store.get("artifactType") != "mindfront_private_interaction_profile_store":
            raise ValueError("unexpected decrypted store type")
        return store
    except InteractionProfileBlockedError:
        raise
    except VaultEncryptionError as exc:
        raise InteractionProfileBlockedError(
            [
                {
                    "code": "profile_store_unreadable",
                    "path": str(path),
                    "message": reason["message"],
                }
                for reason in exc.reasons
            ]
        ) from exc
    except Exception as exc:
        raise InteractionProfileBlockedError(
            [{"code": "profile_store_unreadable", "path": str(path), "message": str(exc)}]
        ) from exc


def _save_store(path: Path, store: dict[str, Any]) -> None:
    payload = json.dumps(store, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
    try:
        write_encrypted_payload(
            path,
            payload,
            artifact_type="mindfront_encrypted_profile_store",
        )
    except VaultEncryptionError as exc:
        raise InteractionProfileBlockedError(
            [
                {
                    "code": "profile_store_encryption_failed",
                    "path": str(path),
                    "message": reason["message"],
                }
                for reason in exc.reasons
            ]
        ) from exc


def _validate_nonnegative_int(
    item: dict[str, Any],
    field: str,
    errors: list[dict[str, str]],
    path: str,
) -> None:
    value = item.get(field)
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        _error(errors, "invalid_count", f"{path}.{field}", f"{field} must be a non-negative integer.")


def _parse_datetime(value: Any, path: str, errors: list[dict[str, str]]) -> datetime | None:
    if not isinstance(value, str):
        _error(errors, "invalid_datetime", path, "An ISO 8601 datetime is required.")
        return None
    try:
        return _parse_iso_datetime(value)
    except ValueError:
        _error(errors, "invalid_datetime", path, "An ISO 8601 datetime with timezone is required.")
        return None


def _parse_iso_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timezone required")
    return parsed.astimezone(timezone.utc)


def _is_identifier(value: Any, prefix: str) -> bool:
    return isinstance(value, str) and value.startswith(prefix) and bool(
        re.fullmatch(r"[a-z0-9][a-z0-9-]{5,80}", value)
    )


def _normalize_name(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).strip().casefold()
    return re.sub(r"\s+", " ", normalized)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _error(errors: list[dict[str, str]], code: str, path: str, message: str) -> None:
    errors.append({"code": code, "path": path, "message": message})

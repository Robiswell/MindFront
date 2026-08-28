"""Schema constants for Mindfront configuration validation.

The validator intentionally stays stdlib-only and schema-light. These constants
make the source-owned JSON contracts explicit without adding a JSON Schema
dependency.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ConfigFileSpec:
    """A required config file and the collection keys it may expose."""

    file_name: str
    collection_keys: tuple[str, ...]


REQUIRED_CONFIG_FILES: dict[str, ConfigFileSpec] = {
    "confidence_labels": ConfigFileSpec(
        file_name="confidence-labels.json",
        collection_keys=("confidenceLabels", "confidence_labels", "concepts", "enums"),
    ),
    "evidence_sources": ConfigFileSpec(
        file_name="evidence-sources.json",
        collection_keys=("sources", "evidenceSources", "evidence_sources", "items"),
    ),
    "principles": ConfigFileSpec(
        file_name="psychology-principles.json",
        collection_keys=("principles", "psychologyPrinciples", "psychology_principles", "items"),
    ),
    "lenses": ConfigFileSpec(
        file_name="audience-lenses.json",
        collection_keys=("lenses", "audienceLenses", "audience_lenses", "items"),
    ),
    "rubric": ConfigFileSpec(
        file_name="message-quality-rubric.json",
        collection_keys=("dimensions", "rubricDimensions", "rubric_dimensions", "items"),
    ),
    "workplace_assistance_policy": ConfigFileSpec(
        file_name="workplace-assistance-policy.json",
        collection_keys=(),
    ),
}


CANONICAL_CONFIDENCE_ENUMS: dict[str, tuple[str, ...]] = {
    "evidenceBasis": (
        "unsupported",
        "user_provided_unverified",
        "source_evidence",
        "heuristic_inference",
        "synthetic_reader_stress_test",
        "synthetic_task_fixture",
        "local_validation",
        "small_user_test",
        "real_user_data",
        "expert_review",
    ),
    "findingConfidence": (
        "low",
        "medium",
        "high_observable_text_issue",
        "high_source_supported",
        "blocked_sensitive_domain",
    ),
    "recommendationState": (
        "blocked_unsupported",
        "blocked_sensitive_domain",
        "needs_domain_evidence",
        "needs_user_research",
        "needs_expert_review",
        "hypothesis_to_test",
        "ready_for_small_test",
        "locally_checked",
        "small_user_test_supported",
        "validated_for_exact_context",
    ),
}


CONFIDENCE_ENUM_KEY_ALIASES: dict[str, tuple[str, ...]] = {
    "evidenceBasis": ("evidenceBasis", "evidence_basis"),
    "findingConfidence": ("findingConfidence", "finding_confidence"),
    "recommendationState": ("recommendationState", "recommendation_state"),
}


REQUIRED_PRINCIPLE_FIELDS: tuple[str, ...] = (
    "principleId",
    "label",
    "status",
    "evidenceBasis",
    "sourceIds",
    "definition",
    "appliesToDimensions",
    "allowedUses",
    "misuseRisks",
    "prohibitedUses",
    "requiredCaveat",
    "reviewedAt",
)


PRINCIPLE_ARRAY_FIELDS: tuple[str, ...] = (
    "sourceIds",
    "appliesToDimensions",
    "allowedUses",
    "misuseRisks",
    "prohibitedUses",
)


REQUIRED_LENS_FIELDS: tuple[str, ...] = (
    "lensId",
    "label",
    "status",
    "roleFit",
    "defaultEvidenceBasis",
    "notMarketEvidence",
    "purpose",
    "assumptions",
    "reviewQuestions",
    "frictionSignals",
    "safetyRules",
    "blockedUses",
    "recommendedValidation",
    "principleIds",
)


LENS_ARRAY_FIELDS: tuple[str, ...] = (
    "assumptions",
    "reviewQuestions",
    "frictionSignals",
    "safetyRules",
    "blockedUses",
    "principleIds",
)


REQUIRED_EVIDENCE_SOURCE_FIELDS: tuple[str, ...] = (
    "sourceId",
    "label",
    "sourceType",
    "supportTier",
    "allowedUses",
    "llmProcessingAllowed",
    "retentionDays",
    "excerptPolicy",
    "sensitiveDataAllowed",
    "owner",
    "reviewedAt",
    "status",
    "limitations",
)


EVIDENCE_SOURCE_ARRAY_FIELDS: tuple[str, ...] = (
    "allowedUses",
    "limitations",
)


EVIDENCE_SOURCE_BOOLEAN_FIELDS: tuple[str, ...] = (
    "llmProcessingAllowed",
    "sensitiveDataAllowed",
)


REQUIRED_RUBRIC_DIMENSIONS: tuple[str, ...] = (
    "clarity",
    "cognitive_load",
    "concreteness",
    "trust_proof",
    "ethical_risk",
)


RUBRIC_ARRAY_FIELDS: tuple[str, ...] = (
    "principleIds",
    "deterministicSignals",
)


RUBRIC_PRINCIPLE_REF_FIELDS: tuple[str, ...] = (
    "principleIds",
    "applicablePrincipleIds",
    "applicablePrinciples",
    "principles",
)


REQUIRED_MESSAGE_BRIEF_FIELDS: tuple[str, ...] = (
    "briefId",
    "artifactType",
    "schemaVersion",
    "createdAt",
    "sourceText",
    "targetAudience",
    "channel",
    "desiredAction",
    "dataClassification",
    "containsPersonalData",
    "containsCustomerConfidentialData",
    "llmProcessingAllowed",
    "retentionPolicy",
    "domainContext",
    "sensitiveDomainFlags",
    "expertReviewRequired",
    "expertReviewStatus",
    "blockedClaimTypes",
    "publishReadiness",
)


MESSAGE_BRIEF_STRING_FIELDS: tuple[str, ...] = (
    "briefId",
    "artifactType",
    "createdAt",
    "sourceText",
    "targetAudience",
    "channel",
    "desiredAction",
    "dataClassification",
    "retentionPolicy",
    "domainContext",
    "expertReviewStatus",
    "publishReadiness",
    "documentArchetype",
    "communicationIntent",
    "sourceFactManifestHash",
)


MESSAGE_BRIEF_ARRAY_FIELDS: tuple[str, ...] = (
    "sensitiveDomainFlags",
    "blockedClaimTypes",
    "requiredTerms",
    "prohibitedTerms",
    "verifiedFactStatements",
)


MESSAGE_BRIEF_BOOLEAN_FIELDS: tuple[str, ...] = (
    "containsPersonalData",
    "containsCustomerConfidentialData",
    "llmProcessingAllowed",
    "expertReviewRequired",
    "decisionRequired",
    "sourceContainsPersonalData",
    "sourceDataSanitized",
)


MESSAGE_BRIEF_ENUMS: dict[str, tuple[str, ...]] = {
    "dataClassification": ("public", "internal", "confidential", "sensitive"),
    "domainContext": (
        "general_b2b",
        "health",
        "finance",
        "legal",
        "employment",
        "housing",
        "insurance",
        "education",
        "security",
        "minors",
        "crisis",
        "political_civic",
        "public_benefits",
    ),
    "expertReviewStatus": ("not_required", "required_not_started", "completed"),
    "publishReadiness": ("not_assessed", "blocked_until_review", "not_ready", "ready_for_small_test"),
    "documentArchetype": (
        "internal_executive_digest",
        "internal_operational_brief",
        "product_message",
        "landing_page",
        "sales_narrative",
    ),
    "communicationIntent": ("inform", "recommend", "request_decision", "persuade", "enable_task"),
}


SENSITIVE_DOMAIN_CONTEXTS: tuple[str, ...] = tuple(
    value for value in MESSAGE_BRIEF_ENUMS["domainContext"] if value != "general_b2b"
)

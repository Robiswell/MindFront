"""Synthetic reader stress tests using configured audience lenses."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from json import JSONDecodeError
from pathlib import Path
from typing import Any

from . import __version__


class StressTestBlockedError(Exception):
    """Raised when a reader stress test cannot run."""

    def __init__(self, reasons: list[dict[str, str]]):
        self.reasons = reasons
        super().__init__("Reader stress test blocked by input errors.")


SIGNAL_STOP_WORDS = {
    "generic",
    "hidden",
    "missing",
    "unclear",
    "vague",
}


def run_reader_stress_test(
    analysis_path: str | Path,
    *,
    config_root: str | Path = "config",
    lens_ids: list[str] | None = None,
) -> dict[str, Any]:
    """Run configured synthetic reader stress-test lenses against an analysis report."""

    analysis_file = Path(analysis_path)
    config_path = Path(config_root)
    analysis_report = _load_analysis_report(analysis_file)
    lens_config = _load_lens_config(config_path)
    lenses = _select_lenses(lens_config, lens_ids)
    boundary = lens_config["syntheticBoundary"]

    results = [
        _run_lens(index + 1, lens, analysis_report, boundary)
        for index, lens in enumerate(lenses)
    ]
    report = {
        "artifactType": "reader_stress_test_report",
        "stressReportId": f"stress-report-{_hash_text(analysis_report['reportId'] + lens_config['version'])[:12]}",
        "sourceAnalysisReportId": analysis_report["reportId"],
        "simulationNotice": boundary["simulationNotice"],
        "notMarketEvidence": True,
        "marketEvidenceCreated": False,
        "evidenceBasis": "synthetic_reader_stress_test",
        "results": results,
        "recommendedValidation": "Use these simulated stress-test notes to choose real target-user comprehension and proof-review questions.",
        "limitations": [
            "This is simulated feedback from configured audience lenses, not real user research.",
            "Lens output can identify hypotheses to test, but cannot validate market preference, comprehension, conversion, or trust.",
            "Every material recommendation still requires real target-user research or expert review where applicable.",
        ],
        "sourceAnalysisHash": _hash_file(analysis_file),
        "audienceLensHash": _hash_file(config_path / "audience-lenses.json"),
        "sourceBriefHash": analysis_report["sourceBriefHash"],
        "sourceTextHash": analysis_report["sourceTextHash"],
        "configSetHash": analysis_report["configSetHash"],
        "templateHash": "sha256:not-used",
        "outputHash": "sha256:pending-until-written",
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "toolVersion": __version__,
    }
    return report


def write_stress_report(report: dict[str, Any], output_path: str | Path) -> Path:
    """Write a reader stress-test report, filling its output hash."""

    destination = Path(output_path)
    if destination.suffix.lower() != ".json":
        destination.mkdir(parents=True, exist_ok=True)
        destination = destination / "reader-stress-test.json"
    else:
        destination.parent.mkdir(parents=True, exist_ok=True)

    payload = finalize_stress_report(report)
    destination.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return destination


def finalize_stress_report(report: dict[str, Any]) -> dict[str, Any]:
    """Return a stress report with a stable emitted-payload hash."""

    payload = dict(report)
    payload["outputHash"] = "sha256:pending-until-written"
    provisional = json.dumps(payload, indent=2, sort_keys=True)
    payload["outputHash"] = f"sha256:{_hash_text(provisional)}"
    return payload


def _load_analysis_report(path: Path) -> dict[str, Any]:
    data = _load_json_file(path, "analysis")
    if data.get("artifactType") != "message_analysis_report":
        raise StressTestBlockedError(
            [
                {
                    "code": "invalid_artifact_type",
                    "message": "Reader stress test requires a message_analysis_report input.",
                    "path": f"{path}.artifactType",
                }
            ]
        )
    required = ("reportId", "findings", "claims", "recommendations", "sourceBriefHash", "sourceTextHash", "configSetHash")
    reasons = [
        {
            "code": "missing_required_field",
            "message": f"Missing required field: {field_name}.",
            "path": f"{path}.{field_name}",
        }
        for field_name in required
        if field_name not in data
    ]
    if reasons:
        raise StressTestBlockedError(reasons)
    return data


def _load_lens_config(config_root: Path) -> dict[str, Any]:
    path = config_root / "audience-lenses.json"
    data = _load_json_file(path, "audience-lenses")
    if not isinstance(data.get("syntheticBoundary"), dict):
        raise StressTestBlockedError(
            [
                {
                    "code": "missing_required_field",
                    "message": "Audience lens config must include syntheticBoundary.",
                    "path": str(path),
                }
            ]
        )
    return data


def _load_json_file(path: Path, label: str) -> dict[str, Any]:
    if not path.exists():
        raise StressTestBlockedError(
            [{"code": f"missing_{label}_file", "message": f"Missing {label} file.", "path": str(path)}]
        )
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except JSONDecodeError as exc:
        raise StressTestBlockedError(
            [
                {
                    "code": "invalid_json",
                    "message": f"Invalid JSON at line {exc.lineno}, column {exc.colno}: {exc.msg}.",
                    "path": str(path),
                }
            ]
        ) from exc
    if not isinstance(data, dict):
        raise StressTestBlockedError(
            [{"code": "invalid_json_shape", "message": f"{label} file must contain a JSON object.", "path": str(path)}]
        )
    return data


def _select_lenses(lens_config: dict[str, Any], lens_ids: list[str] | None) -> list[dict[str, Any]]:
    lenses = [lens for lens in lens_config.get("lenses", []) if lens.get("status") == "active"]
    available = {lens["lensId"]: lens for lens in lenses}
    if not lens_ids:
        return lenses

    missing = [lens_id for lens_id in lens_ids if lens_id not in available]
    if missing:
        raise StressTestBlockedError(
            [
                {
                    "code": "unknown_lens",
                    "message": f"Unknown or inactive audience lens: {lens_id}.",
                    "path": "lens",
                }
                for lens_id in missing
            ]
        )
    return [available[lens_id] for lens_id in dict.fromkeys(lens_ids)]


def _run_lens(
    index: int,
    lens: dict[str, Any],
    analysis_report: dict[str, Any],
    boundary: dict[str, Any],
) -> dict[str, Any]:
    observed = _observed_friction(lens, analysis_report)
    finding_ids = sorted({finding_id for item in observed for finding_id in item["findingIds"]})
    recommendation_state = "hypothesis_to_test" if observed else "needs_user_research"
    return {
        "stressTestId": f"stress-{index:03d}",
        "lensId": lens["lensId"],
        "lensLabel": lens["label"],
        "roleFit": lens["roleFit"],
        "simulationNotice": boundary["simulationNotice"],
        "notMarketEvidence": True,
        "sourceArtifactId": analysis_report["reportId"],
        "observedFriction": observed,
        "findingIds": finding_ids,
        "reviewQuestions": lens["reviewQuestions"],
        "recommendationState": recommendation_state,
        "evidenceBasis": "synthetic_reader_stress_test",
        "recommendedValidation": lens["recommendedValidation"],
        "limitations": [
            "This lens result is simulated and must be tested with real target users before use as evidence.",
            "The lens can highlight likely friction but cannot prove comprehension, trust, or preference.",
        ],
    }


def _observed_friction(lens: dict[str, Any], analysis_report: dict[str, Any]) -> list[dict[str, Any]]:
    findings = analysis_report.get("findings", [])
    friction_categories = (
        analysis_report.get("motivationFriction", {})
        .get("frictionCategories", [])
    )
    observed: list[dict[str, Any]] = []

    for signal in lens.get("frictionSignals", []):
        signal_lower = signal.lower()
        matched_findings = [
            finding
            for finding in findings
            if _signal_matches_finding(signal_lower, finding)
        ]
        matched_categories = [
            category
            for category in friction_categories
            if _signal_matches_category(signal_lower, category)
        ]
        if matched_findings or matched_categories:
            observed.append(
                {
                    "signal": signal,
                    "findingIds": sorted({finding["findingId"] for finding in matched_findings}),
                    "frictionCategoryIds": sorted({category["categoryId"] for category in matched_categories}),
                    "severity": _max_severity(
                        [finding.get("severity", "medium") for finding in matched_findings]
                        + [category.get("severity", "medium") for category in matched_categories]
                    ),
                    "simulatedInterpretation": _interpretation(signal, lens),
                }
            )

    if not observed and friction_categories:
        first = friction_categories[0]
        observed.append(
            {
                "signal": first["label"].lower(),
                "findingIds": first.get("sourceFindingIds", []),
                "frictionCategoryIds": [first["categoryId"]],
                "severity": first.get("severity", "medium"),
                "simulatedInterpretation": "This configured lens may notice the most prominent unresolved friction category.",
            }
        )
    return observed


def _signal_matches_finding(signal: str, finding: dict[str, Any]) -> bool:
    issue = finding.get("issue", "").lower()
    dimension = finding.get("dimensionId", "").lower()
    if "learning tax" in signal:
        return "learning tax" in issue or "onboarding" in issue
    if "fast path" in signal:
        return "fast path" in issue
    if "agency" in signal:
        return "agency" in issue
    if "onboarding" in signal:
        return "onboarding" in issue or "learning tax" in issue
    if "remedial" in signal:
        return "remedial" in issue or "expert agency" in issue
    if "process language" in signal:
        return "process" in issue or "jargon" in issue
    if "coercive reading momentum" in signal:
        return "dependency or addiction" in issue or "addict" in issue or "cannot live without" in issue
    if "evidence boundary" in signal:
        return "evidence boundary" in issue or dimension == "trust_proof"
    if "proof" in signal and ("proof" in issue or dimension == "trust_proof"):
        return True
    if "category" in signal and "category" in issue:
        return True
    if "next step" in signal or "decision path" in signal:
        return "next action" in issue or "next step" in issue
    if "jargon" in signal or "acronym" in signal:
        return "jargon" in issue or "acronym" in issue
    if "risk" in signal or "pressure" in signal or "urgency" in signal:
        return dimension == "ethical_risk" or "pressure" in issue or "risk" in issue
    if "value" in signal or "hype" in signal:
        return "abstract" in issue or "value" in issue or dimension == "concreteness"
    return any(word in issue for word in _signal_words(signal))


def _signal_matches_category(signal: str, category: dict[str, Any]) -> bool:
    category_id = category.get("categoryId", "")
    label = category.get("label", "").lower()
    if "evidence boundary" in signal:
        return category_id == "no_proof"
    if "fast path" in signal:
        return category_id == "missing_fast_path"
    if "agency" in signal:
        return category_id == "expert_agency_risk"
    if "learning tax" in signal:
        return category_id == "high_perceived_effort"
    if "proof" in signal and category_id == "no_proof":
        return True
    if "category" in signal and category_id == "unclear_category":
        return True
    if "next step" in signal or "decision path" in signal:
        return category_id == "premature_cta"
    if "jargon" in signal or "acronym" in signal:
        return category_id == "jargon_barrier"
    if "risk" in signal or "pressure" in signal or "urgency" in signal:
        return category_id == "high_perceived_risk"
    if "value" in signal or "hype" in signal:
        return category_id in {"unclear_value", "unclear_time_relevance"}
    return any(word in label for word in _signal_words(signal))


def _signal_words(signal: str) -> list[str]:
    return [
        word
        for word in signal.split()
        if len(word) > 4 and word not in SIGNAL_STOP_WORDS
    ]


def _max_severity(values: list[str]) -> str:
    order = {"low": 0, "medium": 1, "high": 2, "blocked": 3}
    return max(values or ["medium"], key=lambda value: order.get(value, 1))


def _interpretation(signal: str, lens: dict[str, Any]) -> str:
    return f"Under {lens['label']}, the signal '{signal}' is a simulated friction hypothesis to validate."


def _hash_file(path: Path) -> str:
    return f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"


def _hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()

"""Deterministic audit report assembly for Mindfront artifacts."""

from __future__ import annotations

import csv
import hashlib
import html
import io
import json
from datetime import datetime, timezone
from json import JSONDecodeError
from pathlib import Path
from typing import Any

from . import __version__
from .impact import task_validation_result_errors


class ReportBundleBlockedError(Exception):
    """Raised when an audit report bundle cannot be generated."""

    def __init__(self, reasons: list[dict[str, str]]):
        self.reasons = reasons
        super().__init__("Audit report blocked by input errors.")


EXPECTED_ARTIFACT_TYPES = {
    "analysis": "message_analysis_report",
    "variants": "copy_variant_bundle",
    "comparison": "variant_comparison_report",
    "stress": "reader_stress_test_report",
    "research": "research_plan",
    "task_protocol": "documentation_task_observation_protocol",
    "task_validation": "documentation_task_validation_result",
}

SEVERITY_ORDER = {"blocked": 0, "high": 1, "medium": 2, "low": 3}


def build_report_bundle(
    analysis_path: str | Path,
    *,
    config_root: str | Path = "config",
    variants_path: str | Path | None = None,
    comparison_path: str | Path | None = None,
    stress_path: str | Path | None = None,
    research_plan_path: str | Path | None = None,
    task_protocol_path: str | Path | None = None,
    task_validation_path: str | Path | None = None,
) -> dict[str, Any]:
    """Build a report-ready bundle from validated Mindfront artifacts."""

    config_path = Path(config_root)
    analysis_file = Path(analysis_path)
    analysis = _load_required_artifact(analysis_file, "analysis")
    confidence_registry = _load_confidence_registry(config_path)
    optional = _load_optional_artifacts(
        analysis=analysis,
        variants_path=variants_path,
        comparison_path=comparison_path,
        stress_path=stress_path,
        research_plan_path=research_plan_path,
        task_protocol_path=task_protocol_path,
        task_validation_path=task_validation_path,
    )
    generated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    included_artifacts = _included_artifacts(analysis, optional)

    bundle = {
        "artifactType": "audit_report_bundle",
        "reportBundleId": f"audit-report-{_hash_text(analysis['reportId'] + analysis['sourceTextHash'])[:12]}",
        "sourceAnalysisReportId": analysis["reportId"],
        "briefId": analysis.get("briefId", "unknown"),
        "summary": _summary(analysis, optional),
        "marketEvidenceCreated": False,
        "notMarketEvidence": True,
        "evidenceBoundary": (
            "This report summarizes local heuristic, gated rewrite, simulated stress-test, research-plan, optional "
            "task-observation protocol, and optional task-validation artifacts. Protocols are evidence-collection "
            "handoffs only; they are not evidence until sessions are collected. This report does not create market "
            "evidence, conversion prediction, or publish-ready validation."
        ),
        "includedArtifactIds": included_artifacts,
        "missingOptionalArtifacts": _missing_optional_artifacts(optional),
        "interactionAssistance": _interaction_assistance_summary(analysis),
        "sections": {
            "shortVersion": _short_version(analysis, optional),
            "confidenceLabels": _confidence_labels(analysis, optional, confidence_registry),
            "scorecard": _scorecard(analysis),
            "messageDiagnosis": _message_diagnosis(analysis),
            "documentationQuality": _documentation_quality(analysis),
            "taskProtocol": _task_protocol(optional),
            "taskValidation": _task_validation(optional),
            "claimProofMap": _claim_proof_map(analysis),
            "motivationAndFriction": _motivation_and_friction(analysis),
            "copyVariants": _copy_variants(optional),
            "syntheticAudienceReview": _synthetic_audience_review(optional),
            "whatToTestNext": _what_to_test_next(analysis, optional),
            "limitations": _limitations(analysis, optional),
        },
        "reportOutputManifest": {
            "jsonPath": "pending-until-written",
            "markdownPath": "pending-until-written",
            "editableSourcePath": "pending-until-written",
            "spreadsheetPath": "pending-until-written",
            "documentationHandoffPath": "pending-until-written",
            "finalOutputPath": "pending-until-written",
            "pdfStatus": "not_generated_by_cli",
            "pdfSourceEditablePath": "pending-until-written",
            "pdfFinalOutputPath": None,
            "pdfPlannedOutputPath": "pending-until-written",
            "pdfVerificationStatus": "not_run",
            "pdfInstruction": (
                "Use the editable HTML source with the document workflow when a polished PDF is requested. "
                "If a PDF is rendered, record both the source/editable path and final PDF output path."
            ),
        },
        "sourceHashes": _source_hashes(analysis_file, optional),
        "sourceBriefHash": analysis["sourceBriefHash"],
        "sourceTextHash": analysis["sourceTextHash"],
        "configSetHash": analysis["configSetHash"],
        "confidenceLabelHash": _hash_file(config_path / "confidence-labels.json"),
        "templateHash": "sha256:mindfront-report-template-v1",
        "outputHash": "sha256:pending-until-written",
        "generatedAt": generated_at,
        "toolVersion": __version__,
    }
    return bundle


def write_report_bundle(bundle: dict[str, Any], output_path: str | Path) -> list[Path]:
    """Write an audit report bundle as JSON, Markdown, HTML, and CSV."""

    destination = Path(output_path)
    if destination.suffix.lower() in {".json", ".md", ".html", ".csv"}:
        destination.parent.mkdir(parents=True, exist_ok=True)
        output_paths = _single_output_paths(destination)
        payload = finalize_report_bundle(bundle, output_paths=output_paths)
        _write_single_report_file(payload, destination)
        return [destination]

    destination.mkdir(parents=True, exist_ok=True)
    paths = {
        "jsonPath": str(destination / "mindfront-audit-report.json"),
        "markdownPath": str(destination / "mindfront-audit-report.md"),
        "editableSourcePath": str(destination / "source.html"),
        "auditReportHtmlPath": str(destination / "mindfront-audit-report.html"),
        "spreadsheetPath": str(destination / "mindfront-audit-scorecard.csv"),
        "documentationHandoffPath": str(destination / "mindfront-document-workflow-handoff.md"),
        "finalOutputPath": str(destination / "source.html"),
        "pdfSourceEditablePath": str(destination / "source.html"),
        "pdfFinalOutputPath": None,
        "pdfPlannedOutputPath": str(destination / "mindfront-audit-report.pdf"),
        "pdfVerificationStatus": "not_run",
    }
    payload = finalize_report_bundle(bundle, output_paths=paths)
    json_path = Path(paths["jsonPath"])
    markdown_path = Path(paths["markdownPath"])
    html_path = Path(paths["editableSourcePath"])
    named_html_path = Path(paths["auditReportHtmlPath"])
    csv_path = Path(paths["spreadsheetPath"])
    handoff_path = Path(paths["documentationHandoffPath"])
    html_text = render_report_html(payload)
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    markdown_path.write_text(render_report_markdown(payload), encoding="utf-8")
    html_path.write_text(html_text, encoding="utf-8")
    named_html_path.write_text(html_text, encoding="utf-8")
    csv_path.write_text(render_report_csv(payload), encoding="utf-8", newline="")
    handoff_path.write_text(render_document_workflow_handoff(payload), encoding="utf-8")
    return [json_path, markdown_path, html_path, named_html_path, csv_path, handoff_path]


def finalize_report_bundle(
    bundle: dict[str, Any],
    *,
    output_paths: dict[str, str | None] | None = None,
) -> dict[str, Any]:
    """Return a report bundle with stable output paths and output hash."""

    payload = json.loads(json.dumps(bundle))
    if output_paths:
        manifest = dict(payload["reportOutputManifest"])
        manifest.update(output_paths)
        payload["reportOutputManifest"] = manifest
    payload["outputHash"] = "sha256:pending-until-written"
    provisional = json.dumps(payload, indent=2, sort_keys=True)
    payload["outputHash"] = f"sha256:{_hash_text(provisional)}"
    return payload


def render_report_markdown(bundle: dict[str, Any]) -> str:
    """Render a report bundle as Markdown."""

    sections = bundle["sections"]
    manifest = bundle["reportOutputManifest"]
    lines = [
        "# Mindfront Audit Report",
        "",
        f"Source analysis: `{bundle['sourceAnalysisReportId']}`",
        f"Evidence boundary: {bundle['evidenceBoundary']}",
        f"Market evidence created: `{str(bundle['marketEvidenceCreated']).lower()}`",
        "",
        "## Output Paths",
        "",
        f"- Editable source: `{manifest['editableSourcePath']}`",
        f"- Final output: `{manifest['finalOutputPath']}`",
        f"- Documentation handoff: `{manifest['documentationHandoffPath']}`",
        f"- PDF status: `{manifest['pdfStatus']}`",
        f"- PDF final output: `{manifest['pdfFinalOutputPath']}`",
        f"- Planned PDF output: `{manifest['pdfPlannedOutputPath']}`",
        f"- PDF verification: `{manifest['pdfVerificationStatus']}`",
        "",
        "## The Short Version",
        "",
    ]
    lines.extend(f"- {item}" for item in sections["shortVersion"]["bullets"])
    lines.extend(["", "## Confidence Labels", ""])
    for item in sections["confidenceLabels"]["labels"]:
        lines.append(f"- `{item['labelType']}.{item['id']}`: {item['definition']}")

    lines.extend(["", "## Message Diagnosis", ""])
    for item in sections["messageDiagnosis"]["findings"]:
        lines.append(f"- `{item['findingId']}` {item['severity']}: {item['issue']}")
        lines.append(f"  Validation: {item['recommendedValidation']}")

    lines.extend(["", "## Documentation Quality", ""])
    doc_quality = sections["documentationQuality"]
    if doc_quality["detected"]:
        lines.append(f"- Specialist-bandwidth lens applied: `{', '.join(doc_quality['appliedLensIds'])}`")
        for name, value in doc_quality["signals"].items():
            lines.append(f"- `{name}`: `{str(value).lower()}`")
        lines.append(f"- Validation: {doc_quality['recommendedValidation']}")
    else:
        lines.append("- Documentation-specific analysis was not detected for this brief.")

    lines.extend(["", "## Task Observation Protocol", ""])
    task_protocol = sections["taskProtocol"]
    if task_protocol["included"]:
        lines.append(f"- Protocol: `{task_protocol['protocolId']}`")
        lines.append(f"- Intended observation source: `{task_protocol['observationSource']}`")
        lines.append("- Evidence status: `not_collected` until filled no-PII task sessions are converted into a task-validation artifact.")
        lines.append(f"- Task count: `{task_protocol['taskCount']}`")
        lines.append(f"- Session template columns: `{', '.join(task_protocol['sessionTemplateColumns'])}`")
        lines.append(f"- Boundary: {task_protocol['evidenceBoundary']}")
    else:
        lines.append("- No task-observation protocol artifact was included.")

    lines.extend(["", "## Task Validation Evidence", ""])
    task_validation = sections["taskValidation"]
    if task_validation["included"]:
        lines.append(f"- Observation source: `{task_validation['observationSource']}`")
        lines.append(f"- Evidence basis: `{task_validation['evidenceBasis']}`")
        lines.append(f"- Evidence grade: `{task_validation['evidenceGrade']}`")
        lines.append(f"- Decision state: `{task_validation['decisionState']}`")
        lines.append(f"- Real task evidence created: `{task_validation['realTaskEvidenceCreated']}`")
        metrics = task_validation["aggregateMetrics"]
        lines.append(f"- Task completion rate: `{metrics['completionRate']}`")
        lines.append(f"- Median skim-to-answer seconds: `{metrics['medianSkimToAnswerSeconds']}`")
        lines.append(f"- Average expert-respect rating: `{metrics['averageExpertRespectRating']}`")
        lines.append(f"- Average reuse-intent rating: `{metrics['averageReuseIntentRating']}`")
        lines.append(f"- Boundary: {task_validation['evidenceBoundary']}")
    else:
        lines.append("- No measured task-validation artifact was included.")

    lines.extend(["", "## Comprehension Scorecard", ""])
    for item in sections["scorecard"]["scores"]:
        lines.append(f"- `{item['dimensionId']}`: {item['score']}/{item['scoreScale'].replace('_', ' ')}")
        lines.append(f"  {item['scoreReason']}")

    lines.extend(["", "## Claim And Proof Map", ""])
    for item in sections["claimProofMap"]["claims"]:
        lines.append(f"- `{item['claimId']}` {item['supportStatus']}: {item['claimText']}")

    lines.extend(["", "## Motivation And Friction", ""])
    lines.append(sections["motivationAndFriction"]["summary"])
    for item in sections["motivationAndFriction"]["frictionCategories"]:
        lines.append(f"- `{item['categoryId']}` {item['severity']}: {item['summary']}")

    lines.extend(["", "## Copy Variants", ""])
    if sections["copyVariants"]["variants"]:
        for item in sections["copyVariants"]["variants"]:
            lines.append(f"- `{item['variantId']}` {item['strategyId']}: {item['recommendationState']}")
    else:
        lines.append("- No variant bundle was included.")

    lines.extend(["", "## Synthetic Audience Review", ""])
    if sections["syntheticAudienceReview"]["results"]:
        for item in sections["syntheticAudienceReview"]["results"]:
            lines.append(f"- `{item['lensId']}`: {item['recommendedValidation']}")
    else:
        lines.append("- No reader stress-test report was included.")

    lines.extend(["", "## What To Test Next", ""])
    for item in sections["whatToTestNext"]["items"]:
        lines.append(f"- `{item['testId']}` {item['method']}: {item['question']}")
        lines.append(f"  Threshold: {item['decisionThreshold']}")

    lines.extend(["", "## Limitations", ""])
    lines.extend(f"- {item}" for item in sections["limitations"]["items"])
    lines.append("")
    return "\n".join(lines)


def render_report_html(bundle: dict[str, Any]) -> str:
    """Render a print-friendly editable HTML report."""

    sections = bundle["sections"]
    manifest = bundle["reportOutputManifest"]

    def esc(value: object) -> str:
        return html.escape(str(value), quote=True)

    def bullet_list(items: list[str]) -> str:
        return "<ul>" + "".join(f"<li>{esc(item)}</li>" for item in items) + "</ul>"

    score_rows = "".join(
        "<tr>"
        f"<td>{esc(score['dimensionId'])}</td>"
        f"<td>{esc(score['score'])}/{esc(score['scoreScale'].replace('_', ' '))}</td>"
        f"<td>{esc(score['scoreReason'])}</td>"
        f"<td>{esc(score['evidenceBasis'])}</td>"
        "</tr>"
        for score in sections["scorecard"]["scores"]
    )
    finding_items = "".join(
        "<li>"
        f"<strong>{esc(item['severity'])}</strong> {esc(item['issue'])}"
        f"<br><span>{esc(item['recommendedValidation'])}</span>"
        "</li>"
        for item in sections["messageDiagnosis"]["findings"]
    )
    doc_quality = sections["documentationQuality"]
    if doc_quality["detected"]:
        doc_quality_items = "".join(
            f"<li><code>{esc(name)}</code>: {esc(str(value).lower())}</li>"
            for name, value in doc_quality["signals"].items()
        )
        doc_quality_html = (
            f"<p>Specialist-bandwidth lens applied: <code>{esc(', '.join(doc_quality['appliedLensIds']))}</code></p>"
            f"<ul>{doc_quality_items}</ul>"
            f"<p>{esc(doc_quality['recommendedValidation'])}</p>"
        )
    else:
        doc_quality_html = "<p>Documentation-specific analysis was not detected for this brief.</p>"
    task_protocol = sections["taskProtocol"]
    if task_protocol["included"]:
        task_protocol_html = (
            f"<p>Protocol: <code>{esc(task_protocol['protocolId'])}</code>; "
            f"intended observation source: <code>{esc(task_protocol['observationSource'])}</code>; "
            f"tasks: <code>{esc(task_protocol['taskCount'])}</code>.</p>"
            "<p>Evidence status: <code>not_collected</code> until filled no-PII task sessions are converted into a task-validation artifact.</p>"
            f"<p>{esc(task_protocol['evidenceBoundary'])}</p>"
        )
    else:
        task_protocol_html = "<p>No task-observation protocol artifact was included.</p>"
    task_validation = sections["taskValidation"]
    if task_validation["included"]:
        metrics = task_validation["aggregateMetrics"]
        signal_items = "".join(
            "<li>"
            f"<code>{esc(item['signalId'])}</code>: {esc(item['value'])}"
            "</li>"
            for item in task_validation["executiveSignals"]
        )
        task_validation_html = (
            f"<p>Observation source: <code>{esc(task_validation['observationSource'])}</code>; "
            f"evidence basis: <code>{esc(task_validation['evidenceBasis'])}</code>; "
            f"evidence grade: <code>{esc(task_validation['evidenceGrade'])}</code>; "
            f"decision state: <code>{esc(task_validation['decisionState'])}</code>.</p>"
            "<table><thead><tr><th>Metric</th><th>Value</th></tr></thead><tbody>"
            f"<tr><td>Task completion rate</td><td>{esc(metrics['completionRate'])}</td></tr>"
            f"<tr><td>Median skim-to-answer seconds</td><td>{esc(metrics['medianSkimToAnswerSeconds'])}</td></tr>"
            f"<tr><td>Average follow-up questions</td><td>{esc(metrics['averageFollowUpQuestionCount'])}</td></tr>"
            f"<tr><td>Average expert-respect rating</td><td>{esc(metrics['averageExpertRespectRating'])}</td></tr>"
            f"<tr><td>Average reuse-intent rating</td><td>{esc(metrics['averageReuseIntentRating'])}</td></tr>"
            "</tbody></table>"
            f"<ul>{signal_items}</ul>"
            f"<p>{esc(task_validation['evidenceBoundary'])}</p>"
        )
    else:
        task_validation_html = "<p>No measured task-validation artifact was included.</p>"
    claim_items = "".join(
        "<li>"
        f"<code>{esc(item['claimId'])}</code> {esc(item['supportStatus'])}: {esc(item['claimText'])}"
        "</li>"
        for item in sections["claimProofMap"]["claims"]
    )
    friction_items = "".join(
        "<li>"
        f"<code>{esc(item['categoryId'])}</code> {esc(item['severity'])}: {esc(item['summary'])}"
        "</li>"
        for item in sections["motivationAndFriction"]["frictionCategories"]
    )
    variant_items = "".join(
        "<li>"
        f"<code>{esc(item['variantId'])}</code> {esc(item['strategyId'])}: {esc(item['recommendationState'])}"
        "</li>"
        for item in sections["copyVariants"]["variants"]
    ) or "<li>No variant bundle was included.</li>"
    synthetic_items = "".join(
        "<li>"
        f"<code>{esc(item['lensId'])}</code>: {esc(item['recommendedValidation'])}"
        "</li>"
        for item in sections["syntheticAudienceReview"]["results"]
    ) or "<li>No reader stress-test report was included.</li>"
    test_items = "".join(
        "<li>"
        f"<strong>{esc(item['method'])}</strong>: {esc(item['question'])}"
        f"<br><span>Threshold: {esc(item['decisionThreshold'])}</span>"
        "</li>"
        for item in sections["whatToTestNext"]["items"]
    )
    label_items = "".join(
        "<li>"
        f"<code>{esc(item['labelType'])}.{esc(item['id'])}</code>: {esc(item['definition'])}"
        "</li>"
        for item in sections["confidenceLabels"]["labels"]
    )
    limitation_items = bullet_list(sections["limitations"]["items"])

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Mindfront Audit Report</title>
  <style>
    :root {{ color-scheme: light; --ink: #1b1f24; --muted: #5a6472; --line: #d8dee6; --paper: #ffffff; --accent: #0f766e; }}
    body {{ margin: 0; font-family: Arial, Helvetica, sans-serif; background: #f6f8fa; color: var(--ink); line-height: 1.45; }}
    main {{ max-width: 980px; margin: 0 auto; padding: 40px 28px 72px; background: var(--paper); }}
    h1 {{ font-size: 34px; margin: 0 0 8px; letter-spacing: 0; }}
    h2 {{ font-size: 20px; margin: 34px 0 12px; border-bottom: 1px solid var(--line); padding-bottom: 6px; }}
    p, li, td, th {{ font-size: 14px; }}
    .meta {{ color: var(--muted); margin: 0 0 20px; }}
    .boundary {{ border-left: 4px solid var(--accent); padding: 10px 14px; background: #eef7f5; }}
    table {{ width: 100%; border-collapse: collapse; margin: 10px 0 18px; }}
    th, td {{ border: 1px solid var(--line); padding: 8px; text-align: left; vertical-align: top; }}
    th {{ background: #f0f3f6; }}
    code {{ font-family: Consolas, monospace; font-size: 13px; }}
    @page {{ size: Letter; margin: 0.45in; }}
    @media print {{
      body {{ background: white; line-height: 1.32; }}
      main {{ padding: 0; max-width: none; }}
      h1 {{ font-size: 28px; margin-bottom: 6px; }}
      h2 {{ font-size: 16px; margin: 18px 0 8px; padding-bottom: 4px; }}
      p, li, td, th {{ font-size: 12px; }}
      table {{ margin: 8px 0 12px; }}
      th, td {{ padding: 5px 6px; }}
      .boundary {{ padding: 8px 12px; }}
    }}
  </style>
</head>
<body>
<main>
  <h1>Mindfront Audit Report</h1>
  <p class="meta">Source analysis: <code>{esc(bundle['sourceAnalysisReportId'])}</code></p>
  <p class="boundary">{esc(bundle['evidenceBoundary'])}</p>

  <h2>Output Paths</h2>
  <ul>
    <li>Editable source: <code>{esc(manifest['editableSourcePath'])}</code></li>
    <li>Final output: <code>{esc(manifest['finalOutputPath'])}</code></li>
    <li>Documentation handoff: <code>{esc(manifest['documentationHandoffPath'])}</code></li>
    <li>PDF status: <code>{esc(manifest['pdfStatus'])}</code></li>
    <li>PDF final output: <code>{esc(manifest['pdfFinalOutputPath'])}</code></li>
    <li>Planned PDF output: <code>{esc(manifest['pdfPlannedOutputPath'])}</code></li>
    <li>PDF verification: <code>{esc(manifest['pdfVerificationStatus'])}</code></li>
  </ul>

  <h2>The Short Version</h2>
  {bullet_list(sections['shortVersion']['bullets'])}

  <h2>Confidence Labels</h2>
  <ul>{label_items}</ul>

  <h2>Message Diagnosis</h2>
  <ul>{finding_items}</ul>

  <h2>Documentation Quality</h2>
  {doc_quality_html}

  <h2>Task Observation Protocol</h2>
  {task_protocol_html}

  <h2>Task Validation Evidence</h2>
  {task_validation_html}

  <h2>Comprehension Scorecard</h2>
  <table>
    <thead><tr><th>Dimension</th><th>Score</th><th>Reason</th><th>Evidence</th></tr></thead>
    <tbody>{score_rows}</tbody>
  </table>

  <h2>Claim And Proof Map</h2>
  <ul>{claim_items}</ul>

  <h2>Motivation And Friction</h2>
  <p>{esc(sections['motivationAndFriction']['summary'])}</p>
  <ul>{friction_items}</ul>

  <h2>Copy Variants</h2>
  <ul>{variant_items}</ul>

  <h2>Synthetic Audience Review</h2>
  <ul>{synthetic_items}</ul>

  <h2>What To Test Next</h2>
  <ul>{test_items}</ul>

  <h2>Limitations</h2>
  {limitation_items}
</main>
</body>
</html>
"""


def render_document_workflow_handoff(bundle: dict[str, Any]) -> str:
    """Render instructions for turning the editable report source into a verified PDF."""

    manifest = bundle["reportOutputManifest"]
    source = manifest["editableSourcePath"]
    planned_pdf = manifest["pdfPlannedOutputPath"]
    lines = [
        "# Mindfront Document Workflow Handoff",
        "",
        f"Source analysis: `{bundle['sourceAnalysisReportId']}`",
        "",
        "## Evidence Boundary",
        "",
        bundle["evidenceBoundary"],
        "",
        "## Required Output",
        "",
        f"- Editable source: `{source}`",
        f"- Planned PDF output: `{planned_pdf}`",
        "- Required verification: render the PDF, confirm it exists and is non-empty, then visually inspect the pages before treating it as final.",
        "",
        "## Render Command",
        "",
        "```powershell",
        (
            "powershell -NoProfile -ExecutionPolicy Bypass -File .\\project-tools\\render-mindfront-report-pdf.ps1 "
            f"-InputHtml \"{source}\" -OutputPdf \"{planned_pdf}\""
        ),
        "```",
        "",
        "## Completion Rule",
        "",
        "Do not present this as a polished PDF deliverable until the PDF render result records the editable source, final PDF path, non-empty file check, and visual QA status.",
        "",
    ]
    return "\n".join(lines)


def render_report_csv(bundle: dict[str, Any]) -> str:
    """Render a compact CSV scorecard/finding export."""

    output = io.StringIO()
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(["section", "id", "dimension", "score_or_severity", "summary", "evidence_basis"])
    for score in bundle["sections"]["scorecard"]["scores"]:
        writer.writerow(
            [
                "score",
                score["scoreId"],
                score["dimensionId"],
                score["score"],
                score["scoreReason"],
                score["evidenceBasis"],
            ]
        )
    for finding in bundle["sections"]["messageDiagnosis"]["findings"]:
        writer.writerow(
            [
                "finding",
                finding["findingId"],
                finding["dimensionId"],
                finding["severity"],
                finding["issue"],
                finding["evidenceBasis"],
            ]
        )
    return output.getvalue()


def _write_single_report_file(bundle: dict[str, Any], destination: Path) -> None:
    suffix = destination.suffix.lower()
    if suffix == ".json":
        destination.write_text(json.dumps(bundle, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    elif suffix == ".md":
        destination.write_text(render_report_markdown(bundle), encoding="utf-8")
    elif suffix == ".html":
        destination.write_text(render_report_html(bundle), encoding="utf-8")
    elif suffix == ".csv":
        destination.write_text(render_report_csv(bundle), encoding="utf-8", newline="")
    else:
        raise ReportBundleBlockedError(
            [{"code": "unsupported_output_type", "message": "Unsupported report output type.", "path": str(destination)}]
        )


def _single_output_paths(destination: Path) -> dict[str, str | None]:
    paths: dict[str, str | None] = {
        "jsonPath": None,
        "markdownPath": None,
        "editableSourcePath": None,
        "spreadsheetPath": None,
        "documentationHandoffPath": None,
        "finalOutputPath": str(destination),
        "pdfSourceEditablePath": None,
        "pdfFinalOutputPath": None,
        "pdfPlannedOutputPath": None,
        "pdfVerificationStatus": "not_run",
    }
    if destination.suffix.lower() == ".json":
        paths["jsonPath"] = str(destination)
    elif destination.suffix.lower() == ".md":
        paths["markdownPath"] = str(destination)
    elif destination.suffix.lower() == ".html":
        paths["editableSourcePath"] = str(destination)
        paths["pdfSourceEditablePath"] = str(destination)
        paths["pdfPlannedOutputPath"] = str(destination.with_suffix(".pdf"))
    elif destination.suffix.lower() == ".csv":
        paths["spreadsheetPath"] = str(destination)
    return paths


def _load_required_artifact(path: Path, label: str) -> dict[str, Any]:
    data = _load_json_file(path, label)
    expected = EXPECTED_ARTIFACT_TYPES[label]
    if data.get("artifactType") != expected:
        raise ReportBundleBlockedError(
            [
                {
                    "code": "invalid_artifact_type",
                    "message": f"{label} input must be a {expected}.",
                    "path": f"{path}.artifactType",
                }
            ]
        )
    _validate_analysis(data, str(path))
    return data


def _load_optional_artifacts(
    *,
    analysis: dict[str, Any],
    variants_path: str | Path | None,
    comparison_path: str | Path | None,
    stress_path: str | Path | None,
    research_plan_path: str | Path | None,
    task_protocol_path: str | Path | None,
    task_validation_path: str | Path | None,
) -> dict[str, dict[str, Any] | None]:
    optional: dict[str, dict[str, Any] | None] = {
        "variants": _load_optional_artifact(variants_path, "variants"),
        "comparison": _load_optional_artifact(comparison_path, "comparison"),
        "stress": _load_optional_artifact(stress_path, "stress"),
        "research": _load_optional_artifact(research_plan_path, "research"),
        "task_protocol": _load_optional_artifact(task_protocol_path, "task_protocol"),
        "task_validation": _load_optional_artifact(task_validation_path, "task_validation"),
    }
    _validate_optional_cross_refs(analysis, optional)
    return optional


def _load_optional_artifact(path_value: str | Path | None, label: str) -> dict[str, Any] | None:
    if path_value is None:
        return None
    path = Path(path_value)
    data = _load_json_file(path, label)
    expected = EXPECTED_ARTIFACT_TYPES[label]
    if data.get("artifactType") != expected:
        raise ReportBundleBlockedError(
            [
                {
                    "code": "invalid_artifact_type",
                    "message": f"{label} input must be a {expected}.",
                    "path": f"{path}.artifactType",
                }
            ]
        )
    data["_sourcePath"] = str(path)
    return data


def _load_json_file(path: Path, label: str) -> dict[str, Any]:
    if not path.exists():
        raise ReportBundleBlockedError(
            [{"code": f"missing_{label}_file", "message": f"Missing {label} file.", "path": str(path)}]
        )
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except JSONDecodeError as exc:
        raise ReportBundleBlockedError(
            [
                {
                    "code": "invalid_json",
                    "message": f"Invalid JSON at line {exc.lineno}, column {exc.colno}: {exc.msg}.",
                    "path": str(path),
                }
            ]
        ) from exc
    if not isinstance(data, dict):
        raise ReportBundleBlockedError(
            [{"code": "invalid_json_shape", "message": f"{label} file must contain a JSON object.", "path": str(path)}]
        )
    return data


def _validate_analysis(analysis: dict[str, Any], path: str) -> None:
    required = (
        "reportId",
        "briefId",
        "summary",
        "scores",
        "findings",
        "claims",
        "recommendations",
        "limitations",
        "sourceBriefHash",
        "sourceTextHash",
        "configSetHash",
    )
    reasons = [
        {
            "code": "missing_required_field",
            "message": f"Missing required field: {field_name}.",
            "path": f"{path}.{field_name}",
        }
        for field_name in required
        if field_name not in analysis
    ]
    if reasons:
        raise ReportBundleBlockedError(reasons)


def _validate_optional_cross_refs(
    analysis: dict[str, Any],
    optional: dict[str, dict[str, Any] | None],
) -> None:
    reasons: list[dict[str, str]] = []
    analysis_id = analysis["reportId"]
    variants = optional["variants"]
    comparison = optional["comparison"]
    stress = optional["stress"]
    research = optional["research"]
    task_protocol = optional["task_protocol"]
    task_validation = optional["task_validation"]
    if variants and variants.get("sourceAnalysisReportId") != analysis_id:
        reasons.append(
            {
                "code": "source_mismatch",
                "message": "Variant bundle does not reference the source analysis report.",
                "path": "variants.sourceAnalysisReportId",
            }
        )
    if comparison and variants and comparison.get("sourceVariantBundleId") != variants.get("bundleId"):
        reasons.append(
            {
                "code": "source_mismatch",
                "message": "Comparison report does not reference the supplied variant bundle.",
                "path": "comparison.sourceVariantBundleId",
            }
        )
    analysis_profile = analysis.get("interactionAssistance")
    analysis_profile_hash = (
        analysis_profile.get("profileHash")
        if isinstance(analysis_profile, dict) and analysis_profile.get("applied") is True
        else None
    )
    for artifact_name, artifact in (("variants", variants), ("comparison", comparison)):
        if not artifact:
            continue
        artifact_profile = artifact.get("interactionAssistance")
        artifact_profile_hash = (
            artifact_profile.get("profileHash")
            if isinstance(artifact_profile, dict) and artifact_profile.get("applied") is True
            else None
        )
        if artifact_profile_hash != analysis_profile_hash:
            reasons.append(
                {
                    "code": "interaction_profile_mismatch",
                    "message": "Interaction-assistance lineage must match the source analysis.",
                    "path": f"{artifact_name}.interactionAssistance.profileHash",
                }
            )
    if stress and stress.get("sourceAnalysisReportId") != analysis_id:
        reasons.append(
            {
                "code": "source_mismatch",
                "message": "Reader stress-test report does not reference the source analysis report.",
                "path": "stress.sourceAnalysisReportId",
            }
        )
    if research and research.get("sourceAnalysisReportId") != analysis_id:
        reasons.append(
            {
                "code": "source_mismatch",
                "message": "Research plan does not reference the source analysis report.",
                "path": "research.sourceAnalysisReportId",
            }
        )
    if task_protocol and task_protocol.get("sourceAnalysisReportId") != analysis_id:
        reasons.append(
            {
                "code": "source_mismatch",
                "message": "Task-observation protocol does not reference the source analysis report.",
                "path": "task_protocol.sourceAnalysisReportId",
            }
        )
    if task_protocol and task_protocol.get("briefId") != analysis.get("briefId"):
        reasons.append(
            {
                "code": "brief_mismatch",
                "message": "Task-observation protocol does not reference the source analysis brief.",
                "path": "task_protocol.briefId",
            }
        )
    if task_protocol and task_protocol.get("marketEvidenceCreated") is not False:
        reasons.append(
            {
                "code": "evidence_boundary_violation",
                "message": "Task-observation protocols cannot create market evidence.",
                "path": "task_protocol.marketEvidenceCreated",
            }
        )
    if task_protocol and task_protocol.get("notMarketEvidence") is not True:
        reasons.append(
            {
                "code": "evidence_boundary_violation",
                "message": "Task-observation protocols must explicitly remain not market evidence.",
                "path": "task_protocol.notMarketEvidence",
            }
        )
    if task_validation and task_validation.get("sourceAnalysisReportId") != analysis_id:
        reasons.append(
            {
                "code": "source_mismatch",
                "message": "Task validation result does not reference the source analysis report.",
                "path": "task_validation.sourceAnalysisReportId",
            }
        )
    if task_validation and task_validation.get("briefId") != analysis.get("briefId"):
        reasons.append(
            {
                "code": "brief_mismatch",
                "message": "Task validation result does not reference the source analysis brief.",
                "path": "task_validation.briefId",
            }
        )
    if task_validation:
        reasons.extend(task_validation_result_errors(task_validation, path="task_validation"))
    if stress and stress.get("marketEvidenceCreated") is not False:
        reasons.append(
            {
                "code": "evidence_boundary_violation",
                "message": "Reader stress-test reports cannot create market evidence.",
                "path": "stress.marketEvidenceCreated",
            }
        )
    if research and research.get("marketEvidenceCreated") is not False:
        reasons.append(
            {
                "code": "evidence_boundary_violation",
                "message": "Research plans cannot create market evidence.",
                "path": "research.marketEvidenceCreated",
            }
        )
    if reasons:
        raise ReportBundleBlockedError(reasons)


def _load_confidence_registry(config_root: Path) -> dict[str, Any]:
    path = config_root / "confidence-labels.json"
    data = _load_json_file(path, "confidence-labels")
    if not isinstance(data.get("concepts"), dict):
        raise ReportBundleBlockedError(
            [
                {
                    "code": "missing_required_field",
                    "message": "Confidence registry must include concepts.",
                    "path": str(path),
                }
            ]
        )
    return data


def _interaction_assistance_summary(analysis: dict[str, Any]) -> dict[str, Any]:
    source = analysis.get("interactionAssistance")
    if not isinstance(source, dict) or source.get("applied") is not True:
        return {
            "applied": False,
            "profileId": source.get("profileId") if isinstance(source, dict) else None,
            "profileHash": source.get("profileHash") if isinstance(source, dict) else None,
            "recipientNameIncluded": False,
            "matchedContext": source.get("matchedContext") if isinstance(source, dict) else None,
            "contextMatched": False,
            "reason": source.get("reason") if isinstance(source, dict) else None,
            "marketEvidenceCreated": False,
        }
    return {
        "applied": True,
        "profileId": source.get("profileId"),
        "profileHash": source.get("profileHash"),
        "recipientNameIncluded": False,
        "matchedContext": source.get("matchedContext"),
        "contextMatched": True,
        "expiresAt": source.get("expiresAt"),
        "humanReviewRequired": True,
        "automaticSendingAllowed": False,
        "privateGuidanceIncludedInReport": False,
        "marketEvidenceCreated": False,
    }


def _included_artifacts(analysis: dict[str, Any], optional: dict[str, dict[str, Any] | None]) -> list[str]:
    ids = [analysis["reportId"]]
    variants = optional["variants"]
    comparison = optional["comparison"]
    stress = optional["stress"]
    research = optional["research"]
    task_protocol = optional["task_protocol"]
    task_validation = optional["task_validation"]
    if variants:
        ids.append(variants["bundleId"])
    if comparison:
        ids.append(comparison["comparisonId"])
    if stress:
        ids.append(stress["stressReportId"])
    if research:
        ids.append(research["researchPlanId"])
    if task_protocol:
        ids.append(task_protocol["protocolId"])
    if task_validation:
        ids.append(task_validation["validationResultId"])
    return ids


def _missing_optional_artifacts(optional: dict[str, dict[str, Any] | None]) -> list[str]:
    return [name for name, artifact in optional.items() if artifact is None]


def _summary(analysis: dict[str, Any], optional: dict[str, dict[str, Any] | None]) -> str:
    included = ", ".join(name for name, artifact in optional.items() if artifact is not None)
    included_text = included or "analysis only"
    return f"Audit report assembled from {included_text}. Source summary: {analysis['summary']}"


def _short_version(analysis: dict[str, Any], optional: dict[str, dict[str, Any] | None]) -> dict[str, Any]:
    findings = _sorted_findings(analysis)
    blocked = [finding for finding in findings if finding.get("severity") == "blocked"]
    top_finding = findings[0]["issue"] if findings else "No deterministic findings were detected."
    bullets = [
        analysis["summary"],
        f"Primary issue to address: {top_finding}",
        f"Validation state: {analysis.get('validationState', 'unknown')}",
        "Treat all recommendations as hypotheses until exact-context user evidence or expert review exists.",
    ]
    if blocked:
        bullets.append("At least one blocked issue must be resolved before live testing or publishing.")
    if optional.get("research"):
        bullets.append("A research plan is included; use its first comprehension gate before preference testing.")
    if optional.get("task_protocol"):
        bullets.append("A task-observation protocol is included; it is an evidence-collection handoff, not evidence by itself.")
    if optional.get("task_validation"):
        if optional["task_validation"].get("realTaskEvidenceCreated") is True:
            bullets.append(
                "Task-validation evidence is included; treat it as exact-context directional evidence, not market proof."
            )
        else:
            bullets.append(
                "A synthetic task-validation fixture is included; use it to verify workflow behavior, not as user evidence."
            )
    return {"bullets": bullets}


def _confidence_labels(
    analysis: dict[str, Any],
    optional: dict[str, dict[str, Any] | None],
    registry: dict[str, Any],
) -> dict[str, Any]:
    used = {
        "evidenceBasis": set(),
        "findingConfidence": set(),
        "recommendationState": set(),
    }
    for score in analysis.get("scores", []):
        _add_if_string(used["evidenceBasis"], score.get("evidenceBasis"))
        _add_if_string(used["findingConfidence"], score.get("findingConfidence"))
    for finding in analysis.get("findings", []):
        _add_if_string(used["evidenceBasis"], finding.get("evidenceBasis"))
        _add_if_string(used["findingConfidence"], finding.get("findingConfidence"))
    for recommendation in analysis.get("recommendations", []):
        _add_if_string(used["evidenceBasis"], recommendation.get("evidenceBasis"))
        _add_if_string(used["recommendationState"], recommendation.get("recommendationState"))
    comparison = optional.get("comparison")
    if comparison:
        _add_if_string(used["evidenceBasis"], comparison.get("evidenceBasis"))
        _add_if_string(used["recommendationState"], comparison.get("recommendationState"))
    stress = optional.get("stress")
    if stress:
        _add_if_string(used["evidenceBasis"], stress.get("evidenceBasis"))
        for result in stress.get("results", []):
            _add_if_string(used["evidenceBasis"], result.get("evidenceBasis"))
            _add_if_string(used["recommendationState"], result.get("recommendationState"))
    research = optional.get("research")
    if research:
        _add_if_string(used["evidenceBasis"], research.get("evidenceBasis"))
    task_validation = optional.get("task_validation")
    if task_validation:
        _add_if_string(used["evidenceBasis"], task_validation.get("evidenceBasis"))
        for signal in task_validation.get("executiveSignals", []):
            _add_if_string(used["evidenceBasis"], signal.get("evidenceBasis"))

    labels = []
    concepts = registry["concepts"]
    for label_type, ids in used.items():
        definitions = {item["id"]: item for item in concepts.get(label_type, []) if isinstance(item, dict)}
        for label_id in sorted(ids):
            definition = definitions.get(label_id, {})
            labels.append(
                {
                    "labelType": label_type,
                    "id": label_id,
                    "definition": definition.get("definition", "Definition not found in confidence registry."),
                    "rank": definition.get("rank"),
                    "maySupportPublishReadiness": definition.get("maySupportPublishReadiness", False),
                }
            )
    return {"labels": labels, "registryId": registry.get("registryId"), "version": registry.get("version")}


def _scorecard(analysis: dict[str, Any]) -> dict[str, Any]:
    scores = []
    for score in analysis.get("scores", []):
        scores.append(
            {
                "scoreId": score["scoreId"],
                "dimensionId": score["dimensionId"],
                "score": score["score"],
                "scoreScale": score["scoreScale"],
                "scoreReason": score["scoreReason"],
                "findingIds": score.get("findingIds", []),
                "evidenceBasis": score.get("evidenceBasis", "unknown"),
                "findingConfidence": score.get("findingConfidence", "unknown"),
            }
        )
    return {"scores": scores}


def _message_diagnosis(analysis: dict[str, Any]) -> dict[str, Any]:
    findings = []
    for finding in _sorted_findings(analysis):
        findings.append(
            {
                "findingId": finding["findingId"],
                "dimensionId": finding["dimensionId"],
                "severity": finding["severity"],
                "issue": finding["issue"],
                "whyItMatters": finding["whyItMatters"],
                "evidenceBasis": finding.get("evidenceBasis", "unknown"),
                "findingConfidence": finding.get("findingConfidence", "unknown"),
                "recommendedFix": finding["recommendedFix"],
                "recommendedValidation": finding["recommendedValidation"],
                "claimIds": finding.get("claimIds", []),
            }
        )
    return {"findings": findings}


def _documentation_quality(analysis: dict[str, Any]) -> dict[str, Any]:
    quality = analysis.get("documentationQuality")
    if not isinstance(quality, dict):
        return {
            "detected": False,
            "signals": {},
            "appliedLensIds": [],
            "recommendedValidation": "No documentation-quality signal was included in the source analysis.",
        }
    return {
        "detected": bool(quality.get("detected")),
        "signals": quality.get("signals", {}) if isinstance(quality.get("signals"), dict) else {},
        "findingIds": quality.get("findingIds", []) if isinstance(quality.get("findingIds"), list) else [],
        "appliedLensIds": quality.get("appliedLensIds", []) if isinstance(quality.get("appliedLensIds"), list) else [],
        "evidenceBasis": quality.get("evidenceBasis", "heuristic_inference"),
        "notMarketEvidence": quality.get("notMarketEvidence", True),
        "recommendedValidation": quality.get(
            "recommendedValidation",
            "Run task-based validation before making documentation-performance claims.",
        ),
    }


def _task_validation(optional: dict[str, dict[str, Any] | None]) -> dict[str, Any]:
    validation = optional.get("task_validation")
    if not validation:
        return {
            "included": False,
            "evidenceBasis": "not_provided",
            "decisionState": "not_provided",
            "aggregateMetrics": {},
            "executiveSignals": [],
            "evidenceBoundary": "No measured task-validation artifact was included.",
        }
    return {
        "included": True,
        "validationResultId": validation.get("validationResultId"),
        "observationSource": validation.get("observationSource", "unknown"),
        "evidenceBasis": validation.get("evidenceBasis", "unknown"),
        "evidenceGrade": validation.get("evidenceGrade", "unknown"),
        "decisionState": validation.get("decisionState", "unknown"),
        "realTaskEvidenceCreated": validation.get("realTaskEvidenceCreated", False),
        "sample": validation.get("sample", {}),
        "aggregateMetrics": validation.get("aggregateMetrics", {}),
        "beforeAfterDeltas": validation.get("beforeAfterDeltas", {}),
        "executiveSignals": validation.get("executiveSignals", []),
        "evidenceBoundary": _task_validation_boundary(validation),
        "notMarketEvidence": validation.get("notMarketEvidence", True),
        "marketEvidenceCreated": validation.get("marketEvidenceCreated", False),
    }


def _task_protocol(optional: dict[str, dict[str, Any] | None]) -> dict[str, Any]:
    protocol = optional.get("task_protocol")
    if not protocol:
        return {
            "included": False,
            "protocolId": None,
            "taskCount": 0,
            "sessionTemplateColumns": [],
            "evidenceBoundary": "No task-observation protocol artifact was included.",
        }
    return {
        "included": True,
        "protocolId": protocol.get("protocolId"),
        "observationSource": protocol.get("observationSource", "unknown"),
        "taskCount": len(protocol.get("tasks", [])),
        "sessionTemplateColumns": protocol.get("sessionTemplateColumns", []),
        "evidenceBoundary": protocol.get(
            "evidenceBoundary",
            "Task-observation protocols are collection handoffs, not market evidence.",
        ),
        "marketEvidenceCreated": protocol.get("marketEvidenceCreated", False),
        "notMarketEvidence": protocol.get("notMarketEvidence", True),
    }


def _task_validation_boundary(validation: dict[str, Any]) -> str:
    if validation.get("realTaskEvidenceCreated") is True:
        return (
            "Task validation is exact-context directional evidence for the tested document and tasks; "
            "it is not market evidence or company-wide performance proof."
        )
    return (
        "This task-validation artifact is a synthetic workflow fixture; it verifies pipeline behavior only "
        "and is not user evidence, market evidence, adoption proof, or performance proof."
    )


def _claim_proof_map(analysis: dict[str, Any]) -> dict[str, Any]:
    claims = []
    for claim in analysis.get("claims", []):
        claims.append(
            {
                "claimId": claim["claimId"],
                "claimText": claim["claimText"],
                "claimType": claim.get("claimType", "unknown"),
                "claimStrength": claim.get("claimStrength", "unknown"),
                "evidenceBasis": claim.get("evidenceBasis", "unknown"),
                "supportStatus": claim.get("supportStatus", "unknown"),
                "limitations": claim.get("limitations", []),
            }
        )
    return {"claims": claims}


def _motivation_and_friction(analysis: dict[str, Any]) -> dict[str, Any]:
    motivation = analysis.get("motivationFriction", {})
    score = motivation.get("motivationScore", {})
    categories = motivation.get("frictionCategories", [])
    trust_gaps = motivation.get("trustGapReport", {}).get("gaps", [])
    summary = score.get("scoreReason", "No motivation/friction report was included in the source analysis.")
    return {
        "summary": summary,
        "motivationScore": score,
        "frictionCategories": categories if isinstance(categories, list) else [],
        "objectionMap": motivation.get("objectionMap", []),
        "trustGaps": trust_gaps if isinstance(trust_gaps, list) else [],
    }


def _copy_variants(optional: dict[str, dict[str, Any] | None]) -> dict[str, Any]:
    variants = optional.get("variants")
    comparison = optional.get("comparison")
    if not variants:
        return {"variants": [], "rankedVariants": [], "recommendedVariantIds": []}
    return {
        "variants": variants.get("variants", []),
        "rankedVariants": comparison.get("rankedVariants", []) if comparison else [],
        "recommendedVariantIds": comparison.get("recommendedVariantIds", []) if comparison else [],
        "claimGateSummary": variants.get("claimGateSummary", {}),
    }


def _synthetic_audience_review(optional: dict[str, dict[str, Any] | None]) -> dict[str, Any]:
    stress = optional.get("stress")
    if not stress:
        return {"results": [], "status": "not_provided"}
    return {
        "results": stress.get("results", []),
        "status": "included",
        "simulationNotice": stress.get("simulationNotice"),
        "notMarketEvidence": stress.get("notMarketEvidence", True),
        "recommendedValidation": stress.get("recommendedValidation"),
    }


def _what_to_test_next(
    analysis: dict[str, Any],
    optional: dict[str, dict[str, Any] | None],
) -> dict[str, Any]:
    research = optional.get("research")
    items = []
    if research:
        for question in research.get("questions", []):
            items.append(
                {
                    "testId": question["questionId"],
                    "method": question["method"],
                    "question": question["uncertainty"],
                    "decisionThreshold": question["decisionThreshold"],
                    "relatedFindingIds": question.get("relatedFindingIds", []),
                    "relatedClaimIds": question.get("relatedClaimIds", []),
                }
            )
    else:
        for index, recommendation in enumerate(analysis.get("recommendations", []), start=1):
            items.append(
                {
                    "testId": f"recommended-test-{index:03d}",
                    "method": "comprehension_test",
                    "question": recommendation.get("recommendedValidation", recommendation["summary"]),
                    "decisionThreshold": (
                        "If fewer than 4 of 5 target users can explain the offer, proof limit, and next step, "
                        "keep revising before preference or live-channel testing."
                    ),
                    "relatedFindingIds": recommendation.get("findingIds", []),
                    "relatedClaimIds": recommendation.get("claimIds", []),
                }
            )
    return {"items": items}


def _limitations(analysis: dict[str, Any], optional: dict[str, dict[str, Any] | None]) -> dict[str, Any]:
    items = []
    items.extend(analysis.get("limitations", []))
    for artifact in optional.values():
        if artifact:
            items.extend(artifact.get("limitations", []))
    items.append("This report is a packaging layer and does not upgrade confidence or evidence state.")
    items.append("Use the listed research plan before treating any recommendation as validated.")
    return {"items": list(dict.fromkeys(items))}


def _source_hashes(analysis_file: Path, optional: dict[str, dict[str, Any] | None]) -> dict[str, str]:
    hashes = {"analysis": _hash_file(analysis_file)}
    for name, artifact in optional.items():
        if artifact and artifact.get("_sourcePath"):
            hashes[name] = _hash_file(Path(artifact["_sourcePath"]))
    return hashes


def _sorted_findings(analysis: dict[str, Any]) -> list[dict[str, Any]]:
    return sorted(
        analysis.get("findings", []),
        key=lambda item: (SEVERITY_ORDER.get(item.get("severity", "medium"), 2), item.get("findingId", "")),
    )


def _add_if_string(values: set[str], value: Any) -> None:
    if isinstance(value, str) and value:
        values.add(value)


def _hash_file(path: Path) -> str:
    return f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"


def _hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()

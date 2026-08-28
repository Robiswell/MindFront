"""Build a de-identified aggregate manifest from a ChatGPT Enterprise user export."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import Any

REQUIRED_COLUMNS = (
    "Rank",
    "User ID",
    "Name",
    "Email",
    "Credits",
    "Estimated costs",
    "Estimated cost currency",
    "Tokens",
    "Lines of code",
)


class UsageManifestError(Exception):
    """Raised when the source export is unsafe or structurally invalid."""


def build_usage_manifest(source_path: str | Path) -> dict[str, Any]:
    """Validate an export and return a de-identified aggregate fact manifest."""

    source = Path(source_path).resolve()
    if not source.is_file():
        raise UsageManifestError(f"Source export does not exist: {source}")

    rows = _read_rows(source)
    if not rows:
        raise UsageManifestError("Source export contains no user rows.")

    _validate_columns(rows[0])
    parsed = [_parse_row(row, index + 2) for index, row in enumerate(rows)]
    _validate_population(parsed)

    costs = [row["estimatedCost"] for row in parsed]
    sorted_costs = sorted(costs, reverse=True)
    total_cost = sum(costs, Decimal("0"))
    nonzero_cost_count = sum(cost > 0 for cost in costs)
    positive_code_count = sum(row["linesOfCode"] > 0 for row in parsed)
    top_5_cost = sum(sorted_costs[:5], Decimal("0"))
    top_10_cost = sum(sorted_costs[:10], Decimal("0"))
    users_to_80, users_to_80_cost = _users_to_share(sorted_costs, total_cost, Decimal("0.80"))
    period_start, period_end = _period_from_filename(source.name)

    manifest: dict[str, Any] = {
        "artifactType": "deidentified_usage_fact_manifest",
        "schemaVersion": 1,
        "source": {
            "fileName": source.name,
            "sha256": f"sha256:{_hash_file(source)}",
            "periodStart": period_start,
            "periodEnd": period_end,
            "periodLabelSource": "filename",
            "observedFileLastWriteUtc": datetime.fromtimestamp(
                source.stat().st_mtime, tz=timezone.utc
            ).isoformat(timespec="seconds"),
            "rowCount": len(parsed),
            "currency": parsed[0]["currency"],
        },
        "facts": {
            "userCount": len(parsed),
            "usersWithNonzeroEstimatedCostField": nonzero_cost_count,
            "usersWithZeroEstimatedCostField": len(parsed) - nonzero_cost_count,
            "usersWithNonzeroEstimatedCostFieldSharePercent": _percent(
                Decimal(nonzero_cost_count), Decimal(len(parsed))
            ),
            "totalEstimatedCostField": _decimal_string(total_cost),
            "averageEstimatedCostField": _decimal_string(total_cost / Decimal(len(parsed)), places=2),
            "medianEstimatedCostField": _decimal_string(_median(costs), places=2),
            "totalTokens": sum(row["tokens"] for row in parsed),
            "totalLinesOfCode": sum(row["linesOfCode"] for row in parsed),
            "usersWithLinesOfCode": positive_code_count,
            "usersWithoutLinesOfCode": len(parsed) - positive_code_count,
            "estimatedCostFieldDistribution": {
                "zero": sum(cost == 0 for cost in costs),
                "greaterThanZeroBelow10": sum(Decimal("0") < cost < Decimal("10") for cost in costs),
                "from10Below100": sum(Decimal("10") <= cost < Decimal("100") for cost in costs),
                "from100Below1000": sum(Decimal("100") <= cost < Decimal("1000") for cost in costs),
                "atLeast1000": sum(cost >= Decimal("1000") for cost in costs),
            },
            "concentration": {
                "top5": {
                    "userCount": 5,
                    "estimatedCostField": _decimal_string(top_5_cost),
                    "sharePercent": _percent(top_5_cost, total_cost),
                },
                "top10": {
                    "userCount": 10,
                    "estimatedCostField": _decimal_string(top_10_cost),
                    "sharePercent": _percent(top_10_cost, total_cost),
                },
                "usersToAtLeast80Percent": {
                    "userCount": users_to_80,
                    "estimatedCostField": _decimal_string(users_to_80_cost),
                    "sharePercent": _percent(users_to_80_cost, total_cost),
                },
            },
        },
        "presentationFacts": {
            "userCount": f"{len(parsed):,}",
            "activeUserCount": f"{nonzero_cost_count:,}",
            "activeUserShare": f"{_percent(Decimal(nonzero_cost_count), Decimal(len(parsed)), places=1)}%",
            "totalEstimatedCostField": _compact_currency(total_cost),
            "top5Share": f"{_percent(top_5_cost, total_cost, places=1)}%",
            "top10Share": f"{_percent(top_10_cost, total_cost, places=1)}%",
            "usersTo80Percent": f"{users_to_80:,}",
            "linesOfCodeUserSplit": f"{positive_code_count:,} / {len(parsed) - positive_code_count:,}",
        },
        "definitions": {
            "activeUserCount": "Users whose Estimated costs field is greater than zero in the export.",
            "estimatedCostField": (
                "The export column named Estimated costs. It is reported as an activity indicator and is not "
                "represented as an invoice, actual spend, realized savings, or business value."
            ),
            "tokens": "The export token count. It does not establish productive use, quality, or business outcome.",
            "linesOfCode": (
                "The export Lines of code count. A zero can reflect a non-coding use pattern; the field is not a "
                "productivity or quality measure."
            ),
            "concentration": (
                "Users sorted by the Estimated costs field descending; cumulative field values divided by the "
                "total Estimated costs field."
            ),
        },
        "calculationContract": {
            "decimalArithmetic": "Python Decimal from source strings; no binary floating-point aggregation.",
            "topNShareFormula": "sum(top N Estimated costs) / sum(all Estimated costs) * 100",
            "usersTo80Formula": (
                "Smallest user count, sorted by Estimated costs descending, whose cumulative field value is "
                "at least 80% of the total field value."
            ),
            "rounding": "Currency display uses ROUND_HALF_UP; exact aggregate values remain in facts.",
        },
        "privacy": {
            "deidentified": True,
            "sourceContainsPersonalData": True,
            "omittedSourceFields": ["Rank", "User ID", "Name", "Email"],
            "rawRowsStored": False,
            "piiScanStatus": "passed",
        },
        "validation": {
            "requiredColumnsPresent": True,
            "rowCountMatchesUniqueUserIds": True,
            "ranksAreUniqueAndContiguous": True,
            "currencyIsUniform": True,
            "nonnegativeNumericFields": True,
            "distributionCountMatchesUserCount": True,
            "status": "passed",
        },
        "evidenceBoundary": {
            "supports": [
                "Descriptive aggregate activity for this export and labeled period.",
                "Concentration of the export's Estimated costs field.",
            ],
            "doesNotSupport": [
                "Actual spend or invoice reconciliation.",
                "Business value, productivity, quality, adoption depth, policy compliance, or causation.",
                "Department, use-case, or outcome conclusions because those fields are absent.",
            ],
            "marketEvidenceCreated": False,
        },
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "outputHash": "sha256:pending-until-written",
    }
    _assert_distribution(manifest)
    _assert_deidentified(manifest)
    manifest["outputHash"] = f"sha256:{_hash_payload(manifest)}"
    return manifest


def write_usage_manifest(manifest: dict[str, Any], destination: str | Path) -> Path:
    """Write a finalized manifest."""

    output = Path(destination)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return output


def _read_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as source_file:
        return list(csv.DictReader(source_file))


def _validate_columns(row: dict[str, str]) -> None:
    missing = [column for column in REQUIRED_COLUMNS if column not in row]
    if missing:
        raise UsageManifestError(f"Source export is missing required columns: {', '.join(missing)}")


def _parse_row(row: dict[str, str], line_number: int) -> dict[str, Any]:
    for field in ("Rank", "User ID", "Name", "Email", "Estimated cost currency"):
        if not (row.get(field) or "").strip():
            raise UsageManifestError(f"Line {line_number} has a blank {field} value.")
    try:
        rank = int(row["Rank"])
        estimated_cost = Decimal(row["Estimated costs"])
        tokens = int(row["Tokens"])
        lines_of_code = int(row["Lines of code"])
        Decimal(row["Credits"])
    except (InvalidOperation, ValueError) as exc:
        raise UsageManifestError(f"Line {line_number} contains an invalid numeric value.") from exc
    if rank < 1 or estimated_cost < 0 or tokens < 0 or lines_of_code < 0:
        raise UsageManifestError(f"Line {line_number} contains a negative or invalid rank/numeric value.")
    return {
        "rank": rank,
        "userId": row["User ID"].strip(),
        "email": row["Email"].strip(),
        "estimatedCost": estimated_cost,
        "currency": row["Estimated cost currency"].strip(),
        "tokens": tokens,
        "linesOfCode": lines_of_code,
    }


def _validate_population(rows: list[dict[str, Any]]) -> None:
    user_ids = [row["userId"] for row in rows]
    ranks = [row["rank"] for row in rows]
    currencies = {row["currency"] for row in rows}
    if len(user_ids) != len(set(user_ids)):
        raise UsageManifestError("Source export contains duplicate user IDs.")
    if len(ranks) != len(set(ranks)) or sorted(ranks) != list(range(1, len(rows) + 1)):
        raise UsageManifestError("Source export ranks must be unique and contiguous from 1.")
    if len(currencies) != 1:
        raise UsageManifestError("Source export must use one currency.")


def _period_from_filename(file_name: str) -> tuple[str | None, str | None]:
    match = re.search(r"_(\d{4}-\d{2}-\d{2})-to-(\d{4}-\d{2}-\d{2})\.csv$", file_name)
    if not match:
        return None, None
    return match.group(1), match.group(2)


def _median(values: list[Decimal]) -> Decimal:
    ordered = sorted(values)
    midpoint = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[midpoint]
    return (ordered[midpoint - 1] + ordered[midpoint]) / Decimal("2")


def _users_to_share(
    sorted_values: list[Decimal],
    total: Decimal,
    target_share: Decimal,
) -> tuple[int, Decimal]:
    running = Decimal("0")
    for index, value in enumerate(sorted_values, start=1):
        running += value
        if running >= total * target_share:
            return index, running
    return len(sorted_values), running


def _percent(part: Decimal, total: Decimal, places: int = 4) -> str:
    if total == 0:
        return _decimal_string(Decimal("0"), places=places)
    return _decimal_string(part / total * Decimal("100"), places=places)


def _decimal_string(value: Decimal, places: int | None = None) -> str:
    if places is not None:
        quantum = Decimal("1").scaleb(-places)
        value = value.quantize(quantum, rounding=ROUND_HALF_UP)
    return format(value, "f")


def _compact_currency(value: Decimal) -> str:
    if value >= Decimal("1000"):
        compact = (value / Decimal("1000")).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
        return f"${compact}K"
    return f"${value.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)}"


def _assert_distribution(manifest: dict[str, Any]) -> None:
    distribution = manifest["facts"]["estimatedCostFieldDistribution"]
    if sum(distribution.values()) != manifest["facts"]["userCount"]:
        raise UsageManifestError("Estimated-cost distribution does not reconcile to the user count.")


def _assert_deidentified(manifest: dict[str, Any]) -> None:
    serialized = json.dumps(manifest, sort_keys=True)
    if re.search(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", serialized, flags=re.IGNORECASE):
        raise UsageManifestError("Generated manifest contains an email address.")
    if re.search(r"\buser-[A-Za-z0-9]{8,}\b", serialized):
        raise UsageManifestError("Generated manifest contains a source user identifier.")


def _hash_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _hash_payload(payload: dict[str, Any]) -> str:
    copy = dict(payload)
    copy["outputHash"] = "sha256:pending-until-written"
    canonical = json.dumps(copy, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    try:
        manifest = build_usage_manifest(args.source)
        output = write_usage_manifest(manifest, args.output)
    except UsageManifestError as exc:
        parser.error(str(exc))
    print(f"De-identified usage fact manifest written: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

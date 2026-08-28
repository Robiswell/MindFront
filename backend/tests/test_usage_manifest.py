from __future__ import annotations

import csv
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from mindfront.usage_manifest import UsageManifestError, build_usage_manifest


class UsageManifestTests(unittest.TestCase):
    def test_manifest_is_aggregate_exact_and_deidentified(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "leaderboard_2026-01-01-to-2026-01-31.csv"
            _write_fixture(source)
            manifest = build_usage_manifest(source)

        self.assertEqual("passed", manifest["validation"]["status"])
        self.assertEqual(3, manifest["facts"]["userCount"])
        self.assertEqual("60.00", manifest["facts"]["totalEstimatedCostField"])
        self.assertEqual(
            "100.0000",
            manifest["facts"]["usersWithNonzeroEstimatedCostFieldSharePercent"],
        )
        self.assertEqual("83.3333", manifest["facts"]["concentration"]["usersToAtLeast80Percent"]["sharePercent"])
        self.assertTrue(manifest["privacy"]["deidentified"])
        serialized = json.dumps(manifest)
        self.assertNotIn("test.user@example.com", serialized)
        self.assertNotIn("user-aaaaaaaa", serialized)
        self.assertNotIn("Test User", serialized)

    def test_duplicate_user_id_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "leaderboard_2026-01-01-to-2026-01-31.csv"
            _write_fixture(source, duplicate_user_id=True)
            with self.assertRaises(UsageManifestError):
                build_usage_manifest(source)


def _write_fixture(path: Path, *, duplicate_user_id: bool = False) -> None:
    rows = [
        ["1", "user-aaaaaaaa", "Test User", "test.user@example.com", "10", "30.00", "USD", "100", "10"],
        [
            "2",
            "user-aaaaaaaa" if duplicate_user_id else "user-bbbbbbbb",
            "Taylor Example",
            "taylor@example.com",
            "9",
            "20.00",
            "USD",
            "90",
            "0",
        ],
        ["3", "user-cccccccc", "Jordan Example", "jordan@example.com", "8", "10.00", "USD", "80", "5"],
    ]
    with path.open("w", encoding="utf-8", newline="") as output:
        writer = csv.writer(output)
        writer.writerow(
            [
                "Rank",
                "User ID",
                "Name",
                "Email",
                "Credits",
                "Estimated costs",
                "Estimated cost currency",
                "Tokens",
                "Lines of code",
            ]
        )
        writer.writerows(rows)


if __name__ == "__main__":
    unittest.main()

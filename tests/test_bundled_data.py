"""The demo must run from an installed wheel, with no repository checkout."""

from __future__ import annotations

import json
import unittest

from legal_function_os.bundled import bundled_path
from legal_function_os.cli import main as cli_main
from legal_function_os.raas_cli import main as raas_main

BUNDLED = (
    "sample_requests.json",
    "capacity_scenarios.json",
    "outcome_config.json",
    "service_events.json",
    "raas_deal.json",
    "dpa_documents.json",
)


class BundledDataTest(unittest.TestCase):
    def test_every_bundled_file_resolves_and_parses(self) -> None:
        for name in BUNDLED:
            with self.subTest(name=name):
                path = bundled_path(name)
                self.assertTrue(path.is_file())
                json.loads(path.read_text(encoding="utf-8"))

    def test_missing_bundled_file_is_reported(self) -> None:
        with self.assertRaises(FileNotFoundError):
            bundled_path("not_a_real_fixture.json")

    def test_both_entry_points_run_without_an_input_path(self) -> None:
        self.assertEqual(cli_main(["--quiet"]), 0)
        self.assertEqual(raas_main(["--quiet"]), 0)


if __name__ == "__main__":
    unittest.main()

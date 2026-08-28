import json
import tempfile
import unittest
from pathlib import Path

from legal_function_os.cli import main

ROOT = Path(__file__).resolve().parents[1]
SAMPLE = str(ROOT / "src" / "legal_function_os" / "data" / "sample_requests.json")


class CliNewOutputsTests(unittest.TestCase):
    def test_agent_runs_and_shared_space_outputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            runs_path = Path(tmp) / "agent-runs.json"
            space_path = Path(tmp) / "shared-space.json"
            code = main(["--input", SAMPLE, "--quiet", "--agent-runs-output", str(runs_path), "--shared-space-output", str(space_path)])
            self.assertEqual(code, 0)
            self.assertEqual(json.loads(runs_path.read_text())["schema"], "legal-function-os.agent-runs.v1")
            self.assertEqual(json.loads(space_path.read_text())["summary"]["shared"], 0)

    def test_dpa_output_requires_dpa_input(self):
        with tempfile.TemporaryDirectory() as tmp:
            code = main(["--input", SAMPLE, "--quiet", "--dpa-output", str(Path(tmp) / "dpa.json")])
            self.assertEqual(code, 2)

    def test_dpa_review_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            dpa_in = Path(tmp) / "dpas.json"
            dpa_out = Path(tmp) / "dpa-review.json"
            dpa_in.write_text(json.dumps([{"id": "dpa-1", "title": "AVV", "clauses": {}}]), encoding="utf-8")
            main(["--input", SAMPLE, "--quiet", "--dpa-input", str(dpa_in), "--dpa-output", str(dpa_out)])
            self.assertEqual(json.loads(dpa_out.read_text())["blocker_count"], 8)


if __name__ == "__main__":
    unittest.main()

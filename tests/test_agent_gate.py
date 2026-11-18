"""The supervised agent is gated by this repository's CI, not by workflows of its own.

GitHub runs workflows, and reads dependabot.yml and CODEOWNERS, only from ``.github`` at
the repository root, so those files under ``supervised-agent/`` never ran. pre-commit uses
the configuration in the directory it is run from, so the agent's
``.pre-commit-config.yaml`` was used only by its own pre-commit workflow, which never ran,
or by someone running pre-commit inside ``supervised-agent/``; nothing documented that,
and the root CI does not run pre-commit. The root CI's agent job runs the agent's full
gate instead (owner decision 2).
"""

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AGENT = ROOT / "supervised-agent"


class AgentGateTest(unittest.TestCase):
    def test_agent_carries_no_workflows_of_its_own(self) -> None:
        self.assertFalse((AGENT / ".github").exists())

    def test_agent_carries_no_pre_commit_config_of_its_own(self) -> None:
        self.assertFalse((AGENT / ".pre-commit-config.yaml").exists())

    def test_root_ci_runs_the_agent_gate(self) -> None:
        ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
        self.assertIn("make -C supervised-agent check", ci)


if __name__ == "__main__":
    unittest.main()

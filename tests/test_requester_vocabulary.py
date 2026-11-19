"""The requester-stage vocabulary of the pilot and the core shared space (ADR 0011).

The pilot's six stage ids are the repository's requester-stage vocabulary. The core
shared space keeps its own ``legal-function-os.shared-space.v1`` words: its ``in_review``
is the pilot's stage, ``blocked`` is a core flag and not a stage, and its two German
next-step sentences are v1 values. These tests pin all of it, so that a change to any of
it is deliberate. The pilot module is read by path: it needs nothing outside the standard
library, and the agent's own dependencies are not installed for the core's tests.
"""

import ast
import importlib.util
import unittest
from pathlib import Path
from types import ModuleType
from typing import Any

from legal_function_os.shared_space import build_shared_space

ROOT = Path(__file__).resolve().parents[1]
PILOT = ROOT / "supervised-agent" / "src" / "pilot"
STAGE_IDS = ("draft", "received", "in_review", "approved", "ready", "closed")
APPROVAL = {"approved_by": "Legal Ops", "note": "Status checked; nothing confidential is shown."}


def _pilot_requester_status() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "pilot_requester_status", PILOT / "requester_status.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _pilot_states() -> tuple[str, ...]:
    """The pilot's ``State`` literal, read from its source without importing pydantic."""

    tree = ast.parse((PILOT / "models.py").read_text(encoding="utf-8"))
    for node in tree.body:
        if (
            isinstance(node, ast.Assign)
            and [getattr(target, "id", None) for target in node.targets] == ["State"]
            and isinstance(node.value, ast.Subscript)
        ):
            states = ast.literal_eval(node.value.slice)
            assert isinstance(states, tuple) and all(isinstance(s, str) for s in states)
            return states
    raise AssertionError("no State literal in supervised-agent/src/pilot/models.py")


def _core_entry(approved: bool = True, **fields: Any) -> dict[str, Any]:
    request = {"id": "REQ-1", "title": "Synthetic NDA review", "type": "nda", **fields}
    approvals = {"REQ-1": APPROVAL} if approved else {}
    space = build_shared_space([request], approvals)
    assert space["schema"] == "legal-function-os.shared-space.v1"
    return space["entries"][0]


class RequesterVocabularyTests(unittest.TestCase):
    pilot: ModuleType

    @classmethod
    def setUpClass(cls) -> None:
        cls.pilot = _pilot_requester_status()

    def pilot_stage_ids(self) -> tuple[str, ...]:
        return tuple(stage for stage, _ in self.pilot.REQUESTER_STAGES)

    def test_the_pilot_stage_ids_are_the_vocabulary_in_order(self) -> None:
        self.assertEqual(self.pilot_stage_ids(), STAGE_IDS)

    def test_every_pilot_state_maps_to_one_of_the_six_stages(self) -> None:
        states = _pilot_states()
        for state in ("closed", "declined", "duplicate"):
            self.assertIn(state, states)
        stages = {state: self.pilot.requester_status(state)["stage"] for state in states}
        # Every stage is reached, and no state reaches anything else.
        self.assertEqual(set(stages.values()), set(STAGE_IDS))
        # Every final state, the two legal sets in triage (ADR 0010) too, is closed.
        for state in ("closed", "declined", "duplicate"):
            self.assertEqual(stages[state], "closed", state)

    def test_the_core_in_review_is_the_pilot_stage(self) -> None:
        status = _core_entry()["status"]
        self.assertEqual(status, "in_review")
        self.assertIn(status, self.pilot_stage_ids())

    def test_blocked_is_a_core_flag_not_a_pilot_stage(self) -> None:
        # The core sets it for an urgent blocker or a missed response SLA.
        for fields in ({"urgency": "blocker"}, {"sla_breached": True}):
            self.assertEqual(_core_entry(**fields)["status"], "blocked", fields)
        self.assertNotIn("blocked", self.pilot_stage_ids())

    def test_the_two_german_sentences_are_v1_values(self) -> None:
        self.assertEqual(
            _core_entry(awaiting_business_input=True)["requester_action"],
            "Bitte offene Informationen nachreichen.",
        )
        self.assertEqual(_core_entry()["requester_action"], "Keine Aktion erforderlich.")
        self.assertIsNone(_core_entry(approved=False)["requester_action"])


if __name__ == "__main__":
    unittest.main()

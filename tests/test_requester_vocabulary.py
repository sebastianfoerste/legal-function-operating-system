"""The requester-stage vocabulary of the pilot and the core shared space (ADR 0011).

The pilot's six stage ids are the repository's requester-stage vocabulary. The core
shared space keeps its own ``legal-function-os.shared-space.v1`` words: its ``in_review``
is the pilot's stage, ``blocked`` is a core flag and not a stage, and its two German
next-step sentences are v1 values. A matter that stays ready for delivery after its
delivery ended is shown "In review", and no stage is added for it (note of 2026-11-23).
An approved matter from whose approval no package can be prepared is shown "In review"
as well (note of 2026-11-24).
These tests pin all of it, so that a change to any of it is deliberate. The pilot module
is read by path: it needs nothing outside the standard library, and the agent's own
dependencies are not installed for the core's tests.
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
        # Each state's own stage, so an approved matter is never shown "Ready for you".
        self.assertEqual(
            stages,
            {
                "intake": "draft",
                "triage": "received",
                "assignment": "received",
                "review": "in_review",
                "revision_requested": "in_review",
                "revised": "in_review",
                "approved": "approved",
                "ready_for_delivery": "ready",
                "closed": "closed",
                "declined": "closed",
                "duplicate": "closed",
            },
        )

    def test_an_ended_delivery_is_shown_in_review_and_adds_no_stage(self) -> None:
        # ADR 0011, note of 2026-11-23. A matter can stay ready for delivery after its
        # delivery ended. Its requester then sees "In review", one of the six stages, and
        # is not told to accept a delivery. No other state reads the answer.
        for state in _pilot_states():
            standing = self.pilot.requester_status(state)
            ended = self.pilot.requester_status(state, delivery_stands=False)
            self.assertEqual(tuple(s["id"] for s in ended["stages"]), STAGE_IDS, state)
            if state != "ready_for_delivery":
                self.assertEqual(ended, standing, state)
                continue
            self.assertEqual((standing["stage"], standing["label"]), ("ready", "Ready for you"))
            self.assertEqual(standing["your_action"], "Accept delivery.")
            self.assertEqual((ended["stage"], ended["label"]), ("in_review", "In review"))
            self.assertEqual(ended["your_action"], "No action needed from you.")
            self.assertFalse(ended["waiting_on_you"])
            self.assertNotIn("accept delivery", ended["explanation"].lower())

    def test_an_approval_that_gives_no_package_is_shown_in_review_and_adds_no_stage(self) -> None:
        # ADR 0011, note of 2026-11-24. A matter can be approved while no package can be
        # prepared from the approval. Its requester then sees "In review", one of the six
        # stages, and is not told that a package is being prepared. No other state reads
        # the answer, and `approved` does not read whether a delivery stands.
        for state in _pilot_states():
            can = self.pilot.requester_status(state)
            cannot = self.pilot.requester_status(state, package_can_be_prepared=False)
            self.assertEqual(tuple(s["id"] for s in cannot["stages"]), STAGE_IDS, state)
            if state != "approved":
                self.assertEqual(cannot, can, state)
                continue
            self.assertEqual((can["stage"], can["label"]), ("approved", "Approved"))
            self.assertIn("being prepared", can["explanation"])
            self.assertEqual(can, self.pilot.requester_status(state, delivery_stands=False))
            self.assertEqual((cannot["stage"], cannot["label"]), ("in_review", "In review"))
            self.assertEqual(cannot["your_action"], "No action needed from you.")
            self.assertFalse(cannot["waiting_on_you"])
            self.assertNotIn("being prepared", cannot["explanation"])
            self.assertNotEqual(
                cannot["explanation"],
                self.pilot.requester_status(
                    "ready_for_delivery", delivery_stands=False
                )["explanation"],
            )

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

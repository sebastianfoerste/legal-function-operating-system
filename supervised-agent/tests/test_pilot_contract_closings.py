"""How a closed pilot matter is reported in ``legal-workflow-controls.v1`` (ADR 0010, amended).

Only a matter whose approved package the requester accepted is reported ``approved``. A
matter closed without delivery is ``rejected``. Everything here is synthetic.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from src.pilot.metrics import control_contract
from src.pilot.parent_bridge import (
    CLOSED_OUTCOME_REVIEW_STATE,
    CONTRACT_REVIEW_STATE,
    contract_review_state,
)
from src.pilot.service import PilotService, Stamp, TransitionBlockedError
from src.pilot.state_machine import STATES
from tests.pilot_support import OWNER, REQUESTER, make_service, revision, run_until, state

REPOSITORY = Path(__file__).resolve().parents[2]
NOTE = "Customer paused the deal; closing without delivery."
REASON = "Outside the pilot charter: the customer asks for uncapped liability."
PAUSE = "Waiting for the signed order form from the sales team."
QUESTION = "Which order form does this draft belong to?"
ROLE = {OWNER: "matter_owner", REQUESTER: "business_requester"}

# Scenario, the step after which the matter is withdrawn, the state it is in then, who
# withdraws, and the scripted time of the withdrawal.
WITHDRAWALS = [
    ("routine", "A05", "assignment", OWNER, "2026-09-07T09:17:00Z"),
    ("routine", "A06", "review", OWNER, "2026-09-07T09:30:00Z"),
    ("routine", "A09", "review", REQUESTER, "2026-09-07T10:30:00Z"),
    ("specialist-revision", "B28", "revision_requested", OWNER, "2026-09-09T11:07:00Z"),
    ("specialist-revision", "B31", "revised", OWNER, "2026-09-09T11:55:00Z"),
    ("specialist-revision", "B37", "revised", REQUESTER, "2026-09-09T13:12:00Z"),
    ("routine", "A11", "approved", OWNER, "2026-09-07T14:05:00Z"),
    ("routine", "A11", "approved", REQUESTER, "2026-09-07T14:05:00Z"),
    ("routine", "A12", "ready_for_delivery", OWNER, "2026-09-07T14:20:00Z"),
    ("routine", "A12", "ready_for_delivery", REQUESTER, "2026-09-07T14:20:00Z"),
]


def _contract(service: PilotService, matter_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
    view = service.view_matter(OWNER, matter_id)
    return view, control_contract(view, service.history(OWNER, matter_id)["events"])


def _standing_final_approvals(view: dict[str, Any]) -> list[dict[str, Any]]:
    """Approvals by a final approver on the current version that nothing has cancelled."""

    return [
        d
        for d in view["decisions"]
        if (d["kind"], d["role"], d["outcome"]) == ("final_approval", "final_approver", "approved")
        and d["invalidated_at"] is None
        and d["version"] == view["version"]["version"]
    ]


def _withdraw(service: PilotService, matter_id: str, actor: str, at: str) -> None:
    service.withdraw(
        actor, matter_id, revision(service, matter_id), note=NOTE, stamp=Stamp(fixture_at=at)
    )


def test_a_closed_matter_is_approved_only_when_its_delivery_was_accepted() -> None:
    assert contract_review_state("closed", "delivered_locally_and_accepted") == "approved"
    # Withdrawn, no outcome recorded, or an outcome this mapping does not know.
    for outcome in ("withdrawn_without_delivery", None, "", "closed_some_new_way"):
        assert contract_review_state("closed", outcome) == "rejected", outcome
    # No state-only entry is left to read a closed matter from.
    assert "closed" not in CONTRACT_REVIEW_STATE
    assert set(CONTRACT_REVIEW_STATE) == set(STATES) - {"closed"}
    assert CLOSED_OUTCOME_REVIEW_STATE == {
        "delivered_locally_and_accepted": "approved",
        "withdrawn_without_delivery": "rejected",
    }
    # Every other state maps as before, whatever outcome text is stored beside it.
    for name, shared in CONTRACT_REVIEW_STATE.items():
        assert contract_review_state(name, None) == shared
        assert contract_review_state(name, "delivered_locally_and_accepted") == shared


@pytest.mark.parametrize(("scenario_id", "step", "before", "actor", "at"), WITHDRAWALS)
def test_a_withdrawn_matter_is_rejected_whatever_state_it_had_reached(
    tmp_path, scenario_id: str, step: str, before: str, actor: str, at: str
) -> None:
    service = make_service(tmp_path)
    matter_id = run_until(service, scenario_id, step)
    assert state(service, matter_id) == before
    approved_before = bool(_standing_final_approvals(service.view_matter(OWNER, matter_id)))
    assert approved_before == (before in {"approved", "ready_for_delivery"})

    _withdraw(service, matter_id, actor, at)
    view, contract = _contract(service, matter_id)
    assert (view["matter"]["state"], view["matter"]["closed_outcome"]) == (
        "closed",
        "withdrawn_without_delivery",
    )
    # The withdrawal cancelled every approval, so none stands and none is reported.
    assert _standing_final_approvals(view) == []
    assert contract["review_state"] == "rejected"
    gate = contract["approval_gate"]
    assert gate["export_allowed"] is False and gate["external_actions_allowed"] is False
    # The note is the withdrawal, not the note of an approval that no longer stands.
    assert gate["review_note"] == (
        f"{actor} [{ROLE[actor]}, simulated role] withdrew the matter: {NOTE}"
    )
    assert "Approved for return" not in json.dumps(gate)
    schema = json.loads(
        (REPOSITORY / "contracts" / "legal-workflow-controls.v1.schema.json").read_text()
    )
    assert contract["review_state"] in schema["properties"]["review_state"]["enum"]
    assert contract["audit_events"][-1]["event_type"] == "matter_withdrawn"

    # A command refused afterwards is logged after the withdrawal; the note does not move.
    with pytest.raises(TransitionBlockedError, match="the matter is closed"):
        service.withdraw(
            actor, matter_id, revision(service, matter_id), note="A second try, refused."
        )
    later = _contract(service, matter_id)[1]
    assert later["audit_events"][-1]["event_type"] == "command_refused"
    assert (later["review_state"], later["approval_gate"]["review_note"]) == (
        "rejected",
        gate["review_note"],
    )


def test_a_withdrawn_matter_a_charter_exclusion_held_is_rejected_not_blocked(tmp_path) -> None:
    service = make_service(tmp_path)
    matter_id = run_until(service, "blocked", "C03")  # held in triage; nobody has claimed it
    assert _contract(service, matter_id)[1]["review_state"] == "blocked"
    # A snooze claims it, so the owner is on the matter and may withdraw it.
    service.snooze(
        OWNER, matter_id, revision(service, matter_id), reason=PAUSE, question=QUESTION,
        stamp=Stamp(fixture_at="2026-09-08T11:30:00Z"),
    )  # fmt: skip
    _withdraw(service, matter_id, OWNER, "2026-09-08T12:00:00Z")
    view, contract = _contract(service, matter_id)
    assert view["version"]["scope_exclusions"]  # the exclusion still holds it
    assert contract["review_state"] == "rejected"
    assert contract["approval_gate"]["export_allowed"] is False


def test_approved_is_reported_only_while_a_final_approval_stands(tmp_path) -> None:
    """The rule itself: no matter is reported approved unless a final approver's approval stands."""

    reported: dict[str, str] = {}

    def check(label: str, service: PilotService, matter_id: str) -> None:
        view, contract = _contract(service, matter_id)
        reported[label] = contract["review_state"]
        if contract["review_state"] == "approved":
            assert _standing_final_approvals(view), label
        if view["matter"]["closed_outcome"] != "delivered_locally_and_accepted" and (
            view["matter"]["state"] in {"closed", "declined", "duplicate"}
        ):
            assert contract["review_state"] == "rejected", label
            assert contract["approval_gate"]["export_allowed"] is False, label

    for index, (scenario_id, step, before, actor, at) in enumerate(WITHDRAWALS):
        open_service = make_service(tmp_path / f"open-{index}")
        check(f"open in {before}", open_service, run_until(open_service, scenario_id, step))
        service = make_service(tmp_path / f"withdrawn-{index}")
        matter_id = run_until(service, scenario_id, step)
        _withdraw(service, matter_id, actor, at)
        check(f"withdrawn from {before} by {actor}", service, matter_id)

    service = make_service(tmp_path / "delivered-and-declined")
    delivered = run_until(service, "routine", "A13")
    check("delivered", service, delivered)
    declined = run_until(service, "blocked", "C03")
    service.decline(OWNER, declined, revision(service, declined), reason=REASON)
    check("declined", service, declined)
    duplicate = make_service(tmp_path / "duplicate")
    original = run_until(duplicate, "routine", "A13")
    copy = run_until(duplicate, "blocked", "C03")
    duplicate.mark_duplicate(
        OWNER, copy, revision(duplicate, copy), original_matter_id=original, reason=REASON
    )
    check("duplicate", duplicate, copy)

    assert reported["delivered"] == "approved"
    assert reported["open in approved"] == reported["open in ready_for_delivery"] == "approved"
    assert {v for k, v in reported.items() if k.startswith("withdrawn")} == {"rejected"}
    assert reported["declined"] == reported["duplicate"] == "rejected"
    # A decline or a duplicate carries no review note; only a withdrawal's reason is reported.
    assert _contract(service, declined)[1]["approval_gate"]["review_note"] is None
    assert _contract(duplicate, copy)[1]["approval_gate"]["review_note"] is None


def test_the_contract_readme_lists_a_closed_matter_by_how_it_closed() -> None:
    readme = (REPOSITORY / "contracts" / "README.md").read_text(encoding="utf-8")
    assert (
        "| Supervised-agent pilot | `approved`, `ready_for_delivery`; `closed` after the "
        "requester accepted delivery | `approved` |"
    ) in readme
    assert (
        "| Supervised-agent pilot | `declined`, `duplicate`; `closed` after a withdrawal "
        "| `rejected` |"
    ) in readme
    assert "`approved`, `ready_for_delivery`, `closed`" not in readme
    assert (
        "| Supervised-agent pilot | any state but `declined`, `duplicate` and `closed` after a "
        "withdrawal, while a charter exclusion or blocked source holds the matter | `blocked` |"
    ) in readme
    # The README says what the value means for a matter nobody rejected in the everyday sense.
    assert (
        "In the pilot, `rejected` means a person closed the matter without delivery and no "
        "approval stands"
    ) in readme

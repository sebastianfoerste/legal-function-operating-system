"""How a closed pilot matter is reported in ``legal-workflow-controls.v1`` (ADR 0010, amended).

Only a matter whose approved package the requester accepted is reported ``approved``. A
matter closed without delivery is ``rejected``. A withdrawal also records a rejected review
decision on the assessment stored in the matter version, so the pilot holds no approved or
exportable assessment for a withdrawn matter. Everything here is synthetic.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from models import verify_audit_chain
from src.export_gate import ExportKind
from src.pilot.api import PilotApi
from src.pilot.metrics import control_contract
from src.pilot.onboarding import SYNTHETIC_ACTORS
from src.pilot.parent_bridge import (
    CLOSED_OUTCOME_REVIEW_STATE,
    CONTRACT_REVIEW_STATE,
    contract_review_state,
)
from src.pilot.scenario_runner import ScenarioRunner
from src.pilot.service import (
    InvalidCommandError,
    PilotService,
    Stamp,
    TransitionBlockedError,
    compute_review_hash,
)
from src.pilot.state_machine import STATES
from tests.pilot_support import (
    APPROVER_LEAD,
    OWNER,
    REQUESTER,
    make_service,
    revision,
    run_until,
    scenario,
    state,
)

REPOSITORY = Path(__file__).resolve().parents[2]
NOTE = "Customer paused the deal; closing without delivery."
REASON = "Outside the pilot charter: the customer asks for uncapped liability."
PAUSE = "Waiting for the signed order form from the sales team."
QUESTION = "Which order form does this draft belong to?"
ROLE = {OWNER: "matter_owner", REQUESTER: "business_requester"}
NAME = {actor.actor_id: actor.display_name for actor in SYNTHETIC_ACTORS}

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
# Withdrawals before a reviewer is on the matter. No review-room view exists for these, so
# the contract cannot be built; the assessment is read from the store. The third matter is
# held by a charter exclusion and a blocked source.
EARLY_WITHDRAWALS = [
    ("routine", "A01", "intake", REQUESTER, "2026-09-07T08:02:00Z"),
    ("routine", "A02", "triage", REQUESTER, "2026-09-07T08:30:00Z"),
    ("blocked", "C02", "triage", REQUESTER, "2026-09-08T10:30:00Z"),
]
# What a review decision writes on an assessment. Nothing else of it may move.
REVIEW_FIELDS = {"review_state", "export_allowed", "review_note", "audit_events"}
EXPORT_KINDS: tuple[ExportKind, ...] = ("internal_review", "delivery_package")


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


def _stored(service: PilotService, matter_id: str) -> dict[str, Any]:
    """What the store holds for the matter's current version, read without a view."""

    with service.store.reading() as connection:
        matter = service._matter(connection, matter_id)
        version = matter["current_version"]
        body, row = service._version(connection, matter_id, version)
        content_hash = service._current_content_hash(body, row)

        def rows(query: str) -> list[tuple[Any, ...]]:
            return [tuple(r) for r in connection.execute(query, (matter_id,))]

        return {
            "state": matter["state"],
            "assessment": body.assessment,
            # Final approvals on the current version that nothing has cancelled.
            "standing_final_approvals": connection.execute(
                "SELECT COUNT(*) FROM decisions WHERE matter_id = ? AND version = ? AND kind = "
                "'final_approval' AND role = 'final_approver' AND outcome = 'approved' AND "
                "invalidated_at IS NULL",
                (matter_id, version),
            ).fetchone()[0],
            # What approvals and manifests are bound to, and the records that carry it.
            "bound": {
                "version": version,
                "recorded_content_hash": row["content_hash"],
                "content_hash": content_hash,
                "assessed_content_hash": body.assessed_content_hash,
                "review_hash": compute_review_hash(
                    content_hash,
                    service._changes(connection, matter_id, version),
                    service._comments(connection, matter_id),
                ),
                "body_but_the_assessment": body.model_dump(mode="json", exclude={"assessment"}),
                "versions": rows(
                    "SELECT version, content_hash, document_sha256, created_at FROM "
                    "matter_versions WHERE matter_id = ? ORDER BY version"
                ),
                "manifests": rows(
                    "SELECT kind, manifest_id, version, content_hash, review_hash, body, "
                    "created_at FROM deliverable_manifests WHERE matter_id = ? ORDER BY manifest_id"
                ),
                "decisions": rows(
                    "SELECT decision_id, version, content_hash, review_hash, kind, actor_id, "
                    "outcome, note, payload, created_at FROM decisions WHERE matter_id = ? "
                    "ORDER BY decision_id"
                ),
            },
            "events": rows(
                "SELECT seq, event_type, event_hash FROM events WHERE matter_id = ? ORDER BY seq"
            ),
            "chain": service.store.verify_chain(connection, matter_id),
        }


def _gate_check(
    service: PilotService, actor: str, matter_id: str, kind: ExportKind
) -> tuple[str, str]:
    """The pilot gate's own check of the stored assessment: its result and what it says."""

    eligibility = service.export_eligibility(actor, matter_id, kind)
    check = next(c for c in eligibility.checks if c.check_id == "assessment_approved")
    # The delivery package needs this check; the internal review draft only reports it.
    assert check.required is (kind == "delivery_package")
    return check.status, check.detail


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


def test_a_matter_an_amendment_brought_under_an_exclusion_is_blocked_until_withdrawn(
    tmp_path,
) -> None:
    # ADR 0011: after triage such a matter stays blocked in the contract until a new version
    # removes the exclusion or the matter is withdrawn, which reports it rejected.
    service = make_service(tmp_path)
    matter_id = run_until(service, "routine", "A06")
    assert _contract(service, matter_id)[1]["review_state"] == "pending_review"
    service.amend_matter(
        OWNER,
        matter_id,
        revision(service, matter_id),
        reason="The customer now asks for uncapped liability in the order form.",
        routing_fields={"uncapped_liability": True},
        stamp=Stamp(fixture_at="2026-09-07T09:40:00Z"),
    )
    view, contract = _contract(service, matter_id)
    assert (view["matter"]["state"], contract["review_state"]) == ("revised", "blocked")
    assert contract["approval_gate"]["export_allowed"] is False

    _withdraw(service, matter_id, OWNER, "2026-09-07T09:50:00Z")
    view, contract = _contract(service, matter_id)
    assert view["version"]["scope_exclusions"]  # the exclusion is still on the version
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


@pytest.mark.parametrize(
    ("scenario_id", "step", "before", "actor", "at"), EARLY_WITHDRAWALS + WITHDRAWALS
)
def test_a_withdrawal_records_a_rejected_review_decision_on_the_stored_assessment(
    tmp_path, scenario_id: str, step: str, before: str, actor: str, at: str
) -> None:
    service = make_service(tmp_path)
    matter_id = run_until(service, scenario_id, step)
    earlier = _stored(service, matter_id)
    assert earlier["state"] == before
    was_approved = before in {"approved", "ready_for_delivery"}
    assert (earlier["assessment"].review_state == "approved") == was_approved
    assert earlier["assessment"].export_allowed is was_approved
    if scenario_id == "blocked":  # a blocker finding does not stand in the decision's way
        assert any(f.severity == "blocker" for f in earlier["assessment"].findings)
    passed = ("pass", "parent assessment is approved with a documented review note")
    for kind in EXPORT_KINDS:
        assert (_gate_check(service, actor, matter_id, kind) == passed) == was_approved

    _withdraw(service, matter_id, actor, at)
    later = _stored(service, matter_id)
    assessment = later["assessment"]
    assert later["state"] == "closed" and later["standing_final_approvals"] == 0
    # Whatever state the matter had reached, the stored assessment is rejected: never
    # approved, never exportable, and its note is the withdrawal with the typed reason.
    assert (assessment.review_state, assessment.export_allowed) == ("rejected", False)
    assert assessment.review_note == (
        f"{NAME[actor]} [{actor}, simulated role]: Matter withdrawn without delivery: {NOTE}"
    )
    assert "Approved for return" not in assessment.review_note
    # One review decision more on the assessment's own chain, which still verifies.
    assert assessment.audit_events[:-1] == earlier["assessment"].audit_events
    decision = assessment.audit_events[-1]
    assert (decision.event_type, decision.details) == (
        "review_decision_applied",
        {"state": "rejected"},
    )
    assert decision.actor == f"{NAME[actor]} [{actor}, simulated role]"
    assert decision.note == f"Matter withdrawn without delivery: {NOTE}"
    assert verify_audit_chain(assessment.audit_events).verified
    assert assessment.model_dump(exclude=REVIEW_FIELDS) == earlier["assessment"].model_dump(
        exclude=REVIEW_FIELDS
    )
    # The pilot's own gate no longer passes its check of the assessment.
    refused = ("fail", "parent assessment is rejected and not approved for export")
    for kind in EXPORT_KINDS:
        assert _gate_check(service, actor, matter_id, kind) == refused
    assert service.export_eligibility(actor, matter_id, "delivery_package").eligible is False
    # Saving the assessment moved nothing an approval or a manifest is bound to: the version,
    # the content hash, the reviewed state, the decision records and the stored manifests.
    assert later["bound"] == earlier["bound"]
    delivery_manifests = [m for m in later["bound"]["manifests"] if m[0] == "delivery_package"]
    assert len(delivery_manifests) == (1 if before == "ready_for_delivery" else 0)
    # The matter's event chain gained the withdrawal and still verifies.
    assert later["events"][:-1] == earlier["events"]
    assert later["events"][-1][1] == "matter_withdrawn" and later["chain"].verified


def test_the_shortest_reason_a_withdrawal_accepts_makes_a_valid_review_decision(tmp_path) -> None:
    # The service accepts a reason of 20 characters, counted after runs of whitespace are
    # collapsed. A review decision needs a note of 20 characters and is given more.
    service = make_service(tmp_path)
    matter_id = run_until(service, "routine", "A11")
    reason = "Paused by   customer\n."
    assert len(" ".join(reason.split())) == 20
    service.withdraw(REQUESTER, matter_id, revision(service, matter_id), note=reason)
    assessment = _stored(service, matter_id)["assessment"]
    assert (assessment.review_state, assessment.export_allowed) == ("rejected", False)
    assert assessment.review_note == (
        f"{NAME[REQUESTER]} [{REQUESTER}, simulated role]: "
        "Matter withdrawn without delivery: Paused by customer ."
    )

    # One character fewer is refused as before, and the refusal writes nothing: the other
    # matter keeps its approval and its approved assessment.
    other = run_until(service, "specialist-revision", "B42")
    before = _stored(service, other)
    assert (before["state"], before["assessment"].review_state) == ("approved", "approved")
    with pytest.raises(InvalidCommandError, match="withdrawal reason must be at least 20"):
        service.withdraw(OWNER, other, revision(service, other), note="Paused by customer.")
    assert _stored(service, other) == before


@pytest.mark.parametrize(
    ("step", "at"), [("A11", "2026-09-07T14:05:00Z"), ("A12", "2026-09-07T14:20:00Z")]
)
def test_the_docx_route_and_the_room_see_no_approval_after_a_withdrawal(
    tmp_path, step: str, at: str
) -> None:
    service = make_service(tmp_path)
    matter_id = run_until(service, "routine", step)
    runner, script = ScenarioRunner(service), scenario("routine")
    # The stateless DOCX route reads the stored assessment. While the approval stands it
    # renders; after the withdrawal it is refused by the same gate.
    assert runner._direct(script, "legacy_docx_render") == ("ok", "", [])
    _withdraw(service, matter_id, OWNER, at)
    outcome, message, _ = runner._direct(script, "legacy_docx_render")
    assert outcome == "export_blocked"
    assert "assessment_approved: parent assessment is rejected and not approved" in message

    # The room's view of the matter, as the API serves it, shows no approval either.
    api = PilotApi(service)
    status, view, _ = api.handle(
        "GET", f"/pilot/api/matters/{matter_id}", {"X-Pilot-Actor": APPROVER_LEAD}
    )
    assert status == 200 and view["matter"]["closed_outcome"] == "withdrawn_without_delivery"
    assert (view["assessment"]["review_state"], view["assessment"]["export_allowed"]) == (
        "rejected",
        False,
    )
    assert "Approved for return" not in view["assessment"]["review_note"]
    checks = {c["check_id"]: c["status"] for c in view["eligibility"]["checks"]}
    assert view["eligibility"]["eligible"] is False
    assert checks["assessment_approved"] == "fail"
    assert (
        checks["required_reviewer_decisions"] == checks["matter_state_permits_delivery"] == "fail"
    )
    # No command is open on a closed matter, an export least of all.
    for command in ("export_internal_review", "prepare_delivery"):
        body = {"command": command, "expected_revision": view["matter"]["revision"], "args": {}}
        status, refused, _ = api.handle(
            "POST", f"/pilot/api/matters/{matter_id}/commands", {"X-Pilot-Actor": OWNER}, body
        )
        assert (status, refused["error"]) == (409, "transition_blocked"), refused
        assert "the matter is closed" in refused["message"]


def test_the_stored_assessment_is_approved_only_while_a_final_approval_stands(tmp_path) -> None:
    """After every closing command, a revision request and an amendment to a new version."""

    seen: dict[str, str] = {}
    count = iter(range(1000))

    def fresh() -> PilotService:
        return make_service(tmp_path / f"store-{next(count)}")

    def check(label: str, service: PilotService, matter_id: str) -> None:
        stored = _stored(service, matter_id)
        assessment = stored["assessment"]
        assert label not in seen, label
        seen[label] = assessment.review_state
        assert assessment.export_allowed == (assessment.review_state == "approved"), label
        if assessment.review_state == "approved":
            assert stored["standing_final_approvals"] == 1, label
            assert stored["state"] in {"approved", "ready_for_delivery", "closed"}, label

    for scenario_id, step, before, actor, at in EARLY_WITHDRAWALS + WITHDRAWALS:
        service = fresh()
        matter_id = run_until(service, scenario_id, step)
        if f"open in {before} at {step}" not in seen:  # two actors withdraw from some steps
            check(f"open in {before} at {step}", service, matter_id)
        _withdraw(service, matter_id, actor, at)
        check(f"withdrawn from {before} at {step} by {actor}", service, matter_id)

    service = fresh()
    check("delivered", service, run_until(service, "routine", "A13"))
    declined = run_until(service, "blocked", "C03")
    service.decline(OWNER, declined, revision(service, declined), reason=REASON)
    check("declined", service, declined)
    service = fresh()
    original = run_until(service, "routine", "A13")
    copy = run_until(service, "blocked", "C03")
    service.mark_duplicate(
        OWNER, copy, revision(service, copy), original_matter_id=original, reason=REASON
    )
    check("duplicate", service, copy)
    service = fresh()
    check("delivered after a revision", service, run_until(service, "specialist-revision", "B45"))

    for step, before in (("A11", "approved"), ("A12", "ready_for_delivery")):
        # A revision request needs an open comment to name.
        service = fresh()
        matter_id = run_until(service, "routine", step)
        change = service.view_matter(OWNER, matter_id)["changes"][0]["id"]
        service.comment(
            APPROVER_LEAD, matter_id, revision(service, matter_id), anchor_kind="change",
            anchor_id=change, body="The wording of this clause needs one more look.",
        )  # fmt: skip
        comment_id = service.view_matter(OWNER, matter_id)["comments"][-1]["comment_id"]
        service.request_revision(
            APPROVER_LEAD, matter_id, revision(service, matter_id), comment_ids=[comment_id],
            note="Please revise the clause before the package is delivered.",
        )  # fmt: skip
        check(f"revision requested from {before}", service, matter_id)

        service = fresh()
        matter_id = run_until(service, "routine", step)
        service.amend_matter(
            OWNER, matter_id, revision(service, matter_id),
            reason="Only the title of the matter was corrected.",
            matter_fields={"title": "Routine MSA review, title corrected"},
        )  # fmt: skip
        check(f"title corrected in {before}", service, matter_id)
        service.amend_matter(
            REQUESTER, matter_id, revision(service, matter_id),
            reason="The customer added personal data to the scope.",
            routing_fields={"personal_data": True},
        )  # fmt: skip
        assert _stored(service, matter_id)["bound"]["version"] == 2
        check(f"amended to a new version from {before}", service, matter_id)
        _withdraw(service, matter_id, OWNER, "2026-09-07T16:00:00Z")
        check(f"withdrawn on the new version after {before}", service, matter_id)

    service = fresh()
    matter_id = run_until(service, "specialist-revision", "B28")
    check("revision requested in review", service, matter_id)

    # The assessment is approved exactly where an approval stands, so the rule is not empty.
    approved = {label for label, value in seen.items() if value == "approved"}
    assert approved == {
        "open in approved at A11",
        "open in ready_for_delivery at A12",
        "delivered",
        "delivered after a revision",
        "title corrected in approved",
        "title corrected in ready_for_delivery",
    }
    assert {v for k, v in seen.items() if k.startswith("withdrawn")} == {"rejected"}
    assert {v for k, v in seen.items() if k.startswith("revision requested")} == {
        "revision_requested"
    }
    assert {v for k, v in seen.items() if k.startswith("amended to a new version")} == {
        "needs_review"
    }
    assert seen["declined"] == seen["duplicate"] == "needs_review"


@pytest.mark.parametrize(
    ("step", "actor", "at"),
    [("A11", OWNER, "2026-09-07T14:05:00Z"), ("A12", REQUESTER, "2026-09-07T14:20:00Z")],
)
def test_a_store_from_before_withdrawals_rejected_the_assessment_is_still_reported_rejected(
    tmp_path, step: str, actor: str, at: str
) -> None:
    # Until 2026-11-20 a withdrawal left the stored assessment as the approval wrote it.
    # Such a store is rebuilt here by putting the approved version body back after the
    # withdrawal. The contract does not read its state or its note from that assessment.
    service = make_service(tmp_path)
    matter_id = run_until(service, "routine", step)
    select = "SELECT body FROM matter_versions WHERE matter_id = ? AND version = 1"
    with service.store.reading() as connection:
        approved_body = connection.execute(select, (matter_id,)).fetchone()["body"]
    _withdraw(service, matter_id, actor, at)
    with service.store.transaction() as connection:
        assert connection.execute(select, (matter_id,)).fetchone()["body"] != approved_body
        connection.execute(
            "UPDATE matter_versions SET body = ? WHERE matter_id = ? AND version = 1",
            (approved_body, matter_id),
        )

    view, contract = _contract(service, matter_id)
    old = view["assessment"]
    assert (old["review_state"], old["export_allowed"]) == ("approved", True)
    assert "Approved for return" in old["review_note"]
    assert contract["review_state"] == "rejected"
    gate = contract["approval_gate"]
    assert gate["export_allowed"] is False and gate["external_actions_allowed"] is False
    assert gate["review_note"] == (
        f"{actor} [{ROLE[actor]}, simulated role] withdrew the matter: {NOTE}"
    )
    assert "Approved for return" not in json.dumps(gate)
    # The gate still refuses the matter, on the cancelled approval and on the closed state.
    failing = {c["check_id"] for c in view["eligibility"]["checks"] if c["status"] == "fail"}
    assert failing == {"required_reviewer_decisions", "matter_state_permits_delivery"}
    assert _standing_final_approvals(view) == []


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

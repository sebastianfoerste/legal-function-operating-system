"""The approved customer package is offered only while its delivery stands.

It stands while the matter is ready for delivery and the evidence ``accept_delivery`` needs
holds, and after the requester accepted that delivery. A withdrawal, a revision request, a
new version, a comment written, resolved or reopened after the package was prepared, or
another final approver in place of the one who approved ends it. The package route then
refuses, the matter view says why, and the stored manifest and its files stay for the audit
trail. A matter that stays ready for delivery after its delivery ended is shown to its
requester as "In review", not as a package to accept. The requester's view lists only the
manifest of the package that may be opened, and their matter list shows the label of their
status in place of the pilot state. The last tests hold the runbook, the API guide and the
capability record to the sentences that describe this. Everything here is synthetic.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from src.pilot.api import PilotApi, encode
from src.pilot.fixtures import build_synthetic_msa
from src.pilot.review_room import REVIEW_ROOM_HTML
from src.pilot.scenario_runner import ScenarioRunner
from src.pilot.service import PilotService
from tests.pilot_support import (
    APPROVER_GC,
    APPROVER_LEAD,
    OTHER_OWNER,
    OWNER,
    REQUESTER,
    SPECIALIST,
    change_id,
    event_types,
    make_service,
    revision,
    run_until,
    scenario,
    state,
)

# The sentences a reader gets, as the route answers them and the room shows them.
NEVER_PREPARED = "no approved delivery package exists for this matter"
WITHDRAWN = (
    "The package prepared earlier is no longer approved: the matter was withdrawn without "
    "delivery."
)
CHANGED = (
    "The package prepared earlier is no longer approved: the matter changed after it was "
    "prepared."
)
NOT_THE_ACCEPTED_ONE = (
    "The package stored for this matter cannot be opened: it is not the package whose "
    "delivery was accepted."
)
READERS = {
    "routine": (REQUESTER, OWNER, APPROVER_LEAD),
    "specialist-revision": (REQUESTER, OWNER, SPECIALIST, APPROVER_GC),
}
REASON = "Customer paused the deal; closing without delivery."
ACCEPTANCE = "Package received and understood by the account team."
APPROVAL = "Both deviations are settled and evidenced; approved for return to the customer."
LATE_NOTE = "A late note on this section, written after the package was prepared."
EARLY_NOTE = "A note on this section, written while the matter was in review."


def _package(api: PilotApi, actor: str, matter: str) -> tuple[int, Any]:
    status, payload, _ = api.handle(
        "GET", f"/pilot/api/matters/{matter}/package", {"X-Pilot-Actor": actor}
    )
    return status, payload


def _view(api: PilotApi, actor: str, matter: str) -> dict[str, Any]:
    status, view, _ = api.handle("GET", f"/pilot/api/matters/{matter}", {"X-Pilot-Actor": actor})
    assert status == 200, view
    return view


def _stored_page(service: PilotService, matter: str) -> str:
    """The package page of the latest stored delivery manifest, read from the export folder."""

    with service.store.reading() as connection:
        row = connection.execute(
            "SELECT version FROM deliverable_manifests WHERE matter_id = ? AND kind = "
            "'delivery_package' ORDER BY manifest_id DESC LIMIT 1",
            (matter,),
        ).fetchone()
    folder = service.export_root / matter / f"v{row['version']}" / "delivery"
    return (folder / "customer-package.html").read_text(encoding="utf-8")


def _stored_manifests(service: PilotService, matter: str) -> list[dict[str, Any]]:
    """Every stored delivery manifest, oldest first, in the words of a matter view."""

    with service.store.reading() as connection:
        rows = connection.execute(
            "SELECT * FROM deliverable_manifests WHERE matter_id = ? AND kind = "
            "'delivery_package' ORDER BY manifest_id",
            (matter,),
        ).fetchall()
    return [
        {
            "manifest_id": row["manifest_id"],
            "version": row["version"],
            "kind": row["kind"],
            "created_at": row["created_at"],
            **json.loads(row["body"]),
        }
        for row in rows
    ]


def _lists_what_stands(service: PilotService, view: dict[str, Any], *, stands: bool) -> None:
    """A requester's view lists the manifest of the package that may be opened, and no other.

    A reviewer's view has no such list. It carries every stored manifest, as the record of
    what was written, whether or not a delivery stands.
    """

    stored = _stored_manifests(service, view["matter"]["matter_id"])
    if view["view"] == "requester_summary":
        assert view["delivery"] == (stored[-1:] if stands else []), view["delivery"]
        assert "manifests" not in view
    else:
        assert "delivery" not in view
        assert [m for m in view["manifests"] if m["kind"] == "delivery_package"] == stored


def _offered(api: PilotApi, matter: str, readers: tuple[str, ...]) -> None:
    """Every reader of the matter gets the stored page, and their view says it may be opened."""

    for actor in readers:
        status, page = _package(api, actor, matter)
        assert status == 200, (actor, page)
        assert page == _stored_page(api.service, matter) and "Customer package:" in page
        view = _view(api, actor, matter)
        assert view["package"] == {"may_open": True, "reason": None}
        _lists_what_stands(api.service, view, stands=True)


def _refused(api: PilotApi, matter: str, readers: tuple[str, ...], reason: str | None) -> None:
    """Every reader is refused with the same sentence their view shows.

    ``reason`` is ``None`` when no package was ever prepared: the view then gives no reason
    and the route answers as it always did for that case.
    """

    for actor in readers:
        status, answer = _package(api, actor, matter)
        assert (status, answer["error"], answer["message"]) == (
            403,
            "permission_denied",
            reason or NEVER_PREPARED,
        ), (actor, answer)
        view = _view(api, actor, matter)
        assert view["package"] == {"may_open": False, "reason": reason}
        _lists_what_stands(api.service, view, stands=False)


def _kept(service: PilotService, matter: str) -> dict[str, Any]:
    """What the audit trail keeps of the packages: the manifest rows and every exported file."""

    with service.store.reading() as connection:
        manifests = [
            tuple(row)
            for row in connection.execute(
                "SELECT * FROM deliverable_manifests WHERE matter_id = ? ORDER BY manifest_id",
                (matter,),
            )
        ]
    root = service.export_root / matter
    files = {
        str(path.relative_to(root)): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }
    return {"manifests": manifests, "files": files}


def _continue(service: PilotService, scenario_id: str, after: str, last: str) -> None:
    """Run the scripted steps that follow ``after``, up to and including ``last``."""

    script = scenario(scenario_id)
    ids = [step.get("id") for step in script["steps"]]
    runner = ScenarioRunner(service)
    for step in script["steps"][ids.index(after) + 1 : ids.index(last) + 1]:
        if not step.get("restart"):
            record = runner.run_step(script, step)
            assert record["passed"], record


def _ready(tmp_path: Path, scenario_id: str = "routine") -> tuple[PilotApi, PilotService, str]:
    service = make_service(tmp_path)
    last = {"routine": "A12", "specialist-revision": "B44"}[scenario_id]
    matter = run_until(service, scenario_id, last)
    assert state(service, matter) == "ready_for_delivery"
    return PilotApi(service), service, matter


def _ready_with_an_open_note(tmp_path: Path) -> tuple[PilotApi, PilotService, str, str]:
    """Ready for delivery, with an open note that was written before the approval.

    A note does not block an approval, so a revision request can name it later without any
    new comment being written first.
    """

    service = make_service(tmp_path)
    matter = run_until(service, "routine", "A06")
    view = service.comment(
        OWNER,
        matter,
        revision(service, matter),
        anchor_kind="deliverable_section",
        anchor_id="accepted_exceptions",
        body=EARLY_NOTE,
    )
    note = view["comments"][-1]["comment_id"]
    _continue(service, "routine", "A06", "A12")
    assert state(service, matter) == "ready_for_delivery"
    return PilotApi(service), service, matter, note


# -- each way a delivery ends -------------------------------------------------------


def _withdraw_as(actor: str) -> Callable[[PilotService, str], None]:
    def end(service: PilotService, matter: str) -> None:
        service.withdraw(actor, matter, revision(service, matter), note=REASON)

    return end


def _comment(service: PilotService, matter: str) -> None:
    service.comment(
        APPROVER_LEAD,
        matter,
        revision(service, matter),
        anchor_kind="deliverable_section",
        anchor_id="accepted_exceptions",
        body=LATE_NOTE,
    )


def _amend(service: PilotService, matter: str) -> None:
    service.amend_matter(
        REQUESTER,
        matter,
        revision(service, matter),
        reason="The customer moved the signature date.",
        facts={"signature_target_date": "2026-12-01"},
    )


def _alter_the_stored_document(service: PilotService, matter: str) -> None:
    # Not a command: someone edits the store. The gate inside the evidence catches it.
    with service.store.transaction() as connection:
        connection.execute(
            "UPDATE matter_versions SET document_blob = ? WHERE matter_id = ?",
            (build_synthetic_msa("specialist"), matter),
        )


def _alter_a_stored_event(service: PilotService, matter: str) -> None:
    # Also a store edit. The version and the reviewed state are as they were when the
    # package was prepared; only the gate's check of the event chain fails.
    with service.store.transaction() as connection:
        connection.execute(
            "UPDATE events SET note = 'Edited later.' WHERE matter_id = ? AND seq = 5", (matter,)
        )


ENDINGS = [
    ("withdrawn by the requester", _withdraw_as(REQUESTER), "closed", 1, WITHDRAWN),
    ("withdrawn by the matter owner", _withdraw_as(OWNER), "closed", 1, WITHDRAWN),
    ("a comment after the package", _comment, "ready_for_delivery", 1, CHANGED),
    ("an amendment that makes a new version", _amend, "revised", 2, CHANGED),
    ("the stored document altered", _alter_the_stored_document, "ready_for_delivery", 1, CHANGED),
    ("a stored event altered", _alter_a_stored_event, "ready_for_delivery", 1, CHANGED),
]


@pytest.mark.parametrize(
    ("end", "state_after", "version_after", "reason"),
    [pytest.param(*case[1:], id=case[0]) for case in ENDINGS],
)
def test_the_package_is_refused_once_its_delivery_has_ended(
    tmp_path, end, state_after: str, version_after: int, reason: str
) -> None:
    api, service, matter = _ready(tmp_path)
    readers = READERS["routine"]
    _offered(api, matter, readers)
    kept = _kept(service, matter)

    end(service, matter)

    row = _view(api, OWNER, matter)["matter"]
    assert (row["state"], row["current_version"]) == (state_after, version_after)
    events = event_types(service, matter)
    _refused(api, matter, readers, reason)
    # The audit trail keeps the manifest and every file of the package as they were, and
    # asking for the package records nothing on the matter.
    assert _kept(service, matter) == kept
    assert event_types(service, matter) == events


def test_a_revision_request_alone_ends_the_delivery(tmp_path) -> None:
    api, service, matter, note = _ready_with_an_open_note(tmp_path)
    readers = READERS["routine"]
    _offered(api, matter, readers)
    kept = _kept(service, matter)

    service.request_revision(
        APPROVER_LEAD,
        matter,
        revision(service, matter),
        comment_ids=[note],
        note="The open note has to be answered before delivery.",
    )

    # No comment and no change decision moved: only the state and the approval did.
    assert state(service, matter) == "revision_requested"
    _refused(api, matter, readers, CHANGED)
    assert _kept(service, matter) == kept


def test_replacing_the_final_approver_ends_the_delivery(tmp_path) -> None:
    # An approval counts only while its author is assigned as final approver. The version
    # and the reviewed state do not move, so only the evidence can tell.
    api, service, matter = _ready(tmp_path)
    _offered(api, matter, READERS["routine"])
    kept = _kept(service, matter)

    service.assign(
        OWNER, matter, revision(service, matter), role="final_approver", assignee_id=APPROVER_GC
    )

    assert state(service, matter) == "ready_for_delivery"
    _refused(api, matter, (REQUESTER, OWNER, APPROVER_GC), CHANGED)
    status, answer = _package(api, APPROVER_LEAD, matter)  # no longer on the matter
    assert (status, answer["message"]) == (403, f"{APPROVER_LEAD} has no access to matter {matter}")
    assert _kept(service, matter) == kept


def test_restoring_an_earlier_version_ends_the_delivery(tmp_path) -> None:
    api, service, matter = _ready(tmp_path, "specialist-revision")
    readers = READERS["specialist-revision"]
    _offered(api, matter, readers)  # the package of version 3
    kept = _kept(service, matter)

    service.restore_version(
        OWNER,
        matter,
        revision(service, matter),
        version=2,
        reason="The earlier signature date was right.",
    )

    row = _view(api, OWNER, matter)["matter"]
    assert (row["state"], row["current_version"]) == ("revised", 4)
    _refused(api, matter, readers, CHANGED)
    assert _kept(service, matter) == kept


def test_while_ready_for_delivery_the_package_opens_exactly_when_acceptance_would_pass(
    tmp_path,
) -> None:
    # The route asks the evidence accept_delivery needs; it has no rule of its own.
    api, service, matter = _ready(tmp_path)

    def acceptance_evidence() -> bool:
        allowed = _view(api, OWNER, matter)["allowed"]
        [accept] = [item for item in allowed if item["command"] == "accept_delivery"]
        [evidence] = [e for e in accept["evidence"] if e["name"] == "delivery_manifest_current"]
        return bool(evidence["ok"])

    assert acceptance_evidence() is True
    _offered(api, matter, READERS["routine"])

    # An edit that is not substantive leaves the version and the reviewed state alone.
    service.amend_matter(
        REQUESTER,
        matter,
        revision(service, matter),
        reason="A clearer title for the matter list.",
        matter_fields={"title": "Synthetic routine MSA review (renamed)"},
    )
    assert "non_substantive_edit" in event_types(service, matter)
    assert acceptance_evidence() is True
    _offered(api, matter, READERS["routine"])

    _comment(service, matter)
    assert acceptance_evidence() is False
    _refused(api, matter, READERS["routine"], CHANGED)
    status, answer, _ = api.handle(
        "POST",
        f"/pilot/api/matters/{matter}/commands",
        {"X-Pilot-Actor": REQUESTER},
        {
            "command": "accept_delivery",
            "expected_revision": revision(service, matter),
            "args": {"note": ACCEPTANCE},
        },
    )
    assert (status, answer["error"]) == (409, "transition_blocked")
    assert [e["name"] for e in answer["evidence"] if not e["ok"]] == ["delivery_manifest_current"]
    assert state(service, matter) == "ready_for_delivery"


def test_a_new_package_opens_only_after_a_new_approval_and_a_new_preparation(tmp_path) -> None:
    api, service, matter, note = _ready_with_an_open_note(tmp_path)
    readers = READERS["routine"]
    first = _stored_page(service, matter)
    _offered(api, matter, readers)

    def step(actor: str, command: str, expected_state: str, **args: Any) -> None:
        service.execute(actor, matter, command, revision(service, matter), args)
        assert state(service, matter) == expected_state

    step(
        APPROVER_LEAD,
        "request_revision",
        "revision_requested",
        comment_ids=[note],
        note="Keep the customer's payment terms; Finance agreed to them.",
    )
    _refused(api, matter, readers, CHANGED)
    # A change decision made after the package was prepared.
    step(
        OWNER,
        "decide_change",
        "revision_requested",
        change_id=change_id(service, matter, "payment-terms"),
        outcome="rejected",
        reason="Finance accepts the customer's payment terms for this deal.",
    )
    _refused(api, matter, readers, CHANGED)
    step(
        OWNER,
        "respond_comment",
        "revision_requested",
        comment_id=note,
        body="Payment terms kept as the customer wrote them.",
    )
    step(OWNER, "submit_revision", "revised", note="Payment terms decision changed as asked.")
    _refused(api, matter, readers, CHANGED)
    step(APPROVER_LEAD, "resume_review", "review")
    _refused(api, matter, readers, CHANGED)
    # Approved again, but the stored package is still the one of the earlier approval.
    step(APPROVER_LEAD, "approve", "approved", note=APPROVAL)
    _refused(api, matter, readers, CHANGED)
    assert _stored_page(service, matter) == first

    step(OWNER, "prepare_delivery", "ready_for_delivery")
    _offered(api, matter, readers)
    second = _stored_page(service, matter)
    assert second != first and _package(api, REQUESTER, matter)[1] == second

    step(REQUESTER, "accept_delivery", "closed", note=ACCEPTANCE)
    _offered(api, matter, readers)
    assert _package(api, REQUESTER, matter)[1] == second


# -- what the requester is told while the matter stays ready for delivery -----------

# Stage, label, explanation, next step and whether the matter waits on the requester.
TOLD_READY = (
    "ready",
    "Ready for you",
    "The approved package is ready. Read it, then accept delivery.",
    "Accept delivery.",
    True,
)
ENDED = (
    "The package prepared earlier is no longer approved, because the matter changed after "
    "it was prepared. Legal has to review the matter again before a package is ready for you."
)
TOLD_ENDED = ("in_review", "In review", ENDED, "No action needed from you.", False)


def _told(api: PilotApi, matter: str) -> tuple[str, str, str, str, bool]:
    """What the requester's view says of the matter, with one stage marked as current."""

    status = _view(api, REQUESTER, matter)["requester_status"]
    assert [s["id"] for s in status["stages"] if s["current"]] == [status["stage"]]
    return (
        status["stage"],
        status["label"],
        status["explanation"],
        status["your_action"],
        status["waiting_on_you"],
    )


def _replace_the_approver(service: PilotService, matter: str) -> None:
    service.assign(
        OWNER, matter, revision(service, matter), role="final_approver", assignee_id=APPROVER_GC
    )


@pytest.mark.parametrize(
    "end",
    [_comment, _replace_the_approver],
    ids=["a comment after the package", "another final approver"],
)
def test_the_requester_is_not_told_to_accept_a_delivery_that_has_ended(tmp_path, end) -> None:
    api, service, matter = _ready(tmp_path)
    assert _view(api, REQUESTER, matter)["package"] == {"may_open": True, "reason": None}
    assert _told(api, matter) == TOLD_READY
    kept = _kept(service, matter)

    end(service, matter)

    # The matter did not move, and the status goes by the same answer as the package line.
    view = _view(api, REQUESTER, matter)
    assert view["matter"]["state"] == "ready_for_delivery"
    assert view["package"] == {"may_open": False, "reason": CHANGED}
    assert _told(api, matter) == TOLD_ENDED
    # Reading the status changed nothing: no state, no manifest, no file and no event.
    events = event_types(service, matter)
    assert _told(api, matter) == TOLD_ENDED
    assert state(service, matter) == "ready_for_delivery"
    assert _kept(service, matter) == kept and event_types(service, matter) == events
    # A reviewer's view has no requester status, as before.
    assert "requester_status" not in _view(api, OWNER, matter)

    # The status says what the workflow does. Acceptance is refused, and the one transition
    # the state leaves open to anyone else is a revision request by a reviewer in legal.
    allowed = {item["command"]: item for item in _view(api, OWNER, matter)["allowed"]}
    assert sorted(allowed) == ["accept_delivery", "request_revision"]
    assert allowed["request_revision"]["roles"] == [
        "matter_owner",
        "specialist_reviewer",
        "final_approver",
    ]
    assert allowed["accept_delivery"]["roles"] == ["business_requester"]
    assert [e["name"] for e in allowed["accept_delivery"]["evidence"] if not e["ok"]] == [
        "delivery_manifest_current"
    ]
    status, answer, _ = api.handle(
        "POST",
        f"/pilot/api/matters/{matter}/commands",
        {"X-Pilot-Actor": REQUESTER},
        {
            "command": "accept_delivery",
            "expected_revision": revision(service, matter),
            "args": {"note": ACCEPTANCE},
        },
    )
    assert (status, answer["error"]) == (409, "transition_blocked")
    assert _told(api, matter) == TOLD_ENDED


def test_the_requester_status_follows_the_delivery_while_the_matter_stays_ready(tmp_path) -> None:
    api, service, matter = _ready(tmp_path)

    # Another final approver ends the delivery. The earlier one, assigned again, restores
    # it: the approval counts again, and the status is the one of a standing delivery.
    _replace_the_approver(service, matter)
    assert _told(api, matter) == TOLD_ENDED
    service.assign(
        OWNER, matter, revision(service, matter), role="final_approver", assignee_id=APPROVER_LEAD
    )
    assert _view(api, REQUESTER, matter)["package"] == {"may_open": True, "reason": None}
    assert _told(api, matter) == TOLD_READY

    # A new comment cannot be taken back. Resolving it leaves the reviewed state changed.
    _comment(service, matter)
    assert _told(api, matter) == TOLD_ENDED
    late = _view(api, OWNER, matter)["comments"][-1]
    assert (late["body"], late["state"]) == (LATE_NOTE, "open")
    service.resolve_comment(
        OWNER,
        matter,
        revision(service, matter),
        comment_id=late["comment_id"],
        resolution="Read and noted; nothing changes in the package.",
    )
    assert state(service, matter) == "ready_for_delivery"
    assert _told(api, matter) == TOLD_ENDED

    # Once a reviewer asks for a revision the state says "In review" by itself, with its
    # ordinary explanation, and whether a delivery stands is no longer asked.
    _comment(service, matter)
    note = _view(api, OWNER, matter)["comments"][-1]["comment_id"]
    service.request_revision(
        APPROVER_LEAD,
        matter,
        revision(service, matter),
        comment_ids=[note],
        note="The late note has to be answered before delivery.",
    )
    assert state(service, matter) == "revision_requested"
    assert _told(api, matter) == (
        "in_review",
        "In review",
        "Reviewers are working on the customer's draft.",
        "No action needed from you.",
        False,
    )


def test_resolving_a_note_ends_the_delivery_and_reopening_it_restores_the_delivery(
    tmp_path,
) -> None:
    # The reviewed state covers the state of every comment, so any change to one after the
    # package was prepared ends the delivery. Here no comment is written and none is
    # reopened: a note that was open when the package was prepared is resolved.
    api, service, matter, note = _ready_with_an_open_note(tmp_path)
    readers = READERS["routine"]
    _offered(api, matter, readers)
    assert _told(api, matter) == TOLD_READY
    kept = _kept(service, matter)
    events = event_types(service, matter)

    # An answer to the note changes no comment's state and ends nothing.
    service.respond_comment(
        OWNER,
        matter,
        revision(service, matter),
        comment_id=note,
        body="An answer to the note, written after the package was prepared.",
    )
    _offered(api, matter, readers)
    assert _told(api, matter) == TOLD_READY

    service.resolve_comment(
        APPROVER_LEAD,
        matter,
        revision(service, matter),
        comment_id=note,
        resolution="Read and noted; nothing changes in the package.",
    )
    assert state(service, matter) == "ready_for_delivery"
    assert event_types(service, matter) == [*events, "comment_response_added", "comment_resolved"]
    _refused(api, matter, readers, CHANGED)
    assert _told(api, matter) == TOLD_ENDED
    assert _kept(service, matter) == kept

    # The way back is the opposite step: reopened, the note is in the state it had when the
    # package was prepared. The delivery stands again, for every reader and in the status.
    service.reopen_comment(
        OWNER,
        matter,
        revision(service, matter),
        comment_id=note,
        reason="The note stays open until the delivery is accepted.",
    )
    assert state(service, matter) == "ready_for_delivery"
    assert event_types(service, matter)[-1] == "comment_reopened"
    _offered(api, matter, readers)
    assert _told(api, matter) == TOLD_READY
    assert _kept(service, matter) == kept

    # It is the delivery the requester can accept, and the accepted package stays open.
    service.accept_delivery(REQUESTER, matter, revision(service, matter), note=ACCEPTANCE)
    row = _view(api, OWNER, matter)["matter"]
    assert (row["state"], row["closed_outcome"]) == ("closed", "delivered_locally_and_accepted")
    _offered(api, matter, readers)


def test_an_open_question_overrides_the_action_after_a_delivery_ended(tmp_path) -> None:
    api, service, matter = _ready(tmp_path, "specialist-revision")
    [question] = _view(api, REQUESTER, matter)["clarifications"]
    assert question["state"] == "resolved"
    assert _told(api, matter) == TOLD_READY

    # The owner reopens the question that was put to the requester. That changes the
    # reviewed state, so the delivery ends, and the requester has a question to answer.
    service.reopen_comment(
        OWNER,
        matter,
        revision(service, matter),
        comment_id=question["comment_id"],
        reason="The answer needs one more detail before delivery.",
    )

    view = _view(api, REQUESTER, matter)
    assert view["matter"]["state"] == "ready_for_delivery"
    assert view["package"] == {"may_open": False, "reason": CHANGED}
    assert [c["state"] for c in view["clarifications"]] == ["open"]
    asked = ("in_review", "In review", ENDED, "Answer the open question below.", True)
    assert _told(api, matter) == asked

    # The requester answers, and the question stays open until the owner resolves it.
    service.respond_comment(
        REQUESTER,
        matter,
        revision(service, matter),
        comment_id=question["comment_id"],
        body="The detail is in section 3 of the order form.",
    )
    assert _told(api, matter) == asked
    # Resolved again, the comments are in the state the approval was given on. The
    # delivery stands again, and so does the status of a standing delivery.
    service.resolve_comment(
        OWNER,
        matter,
        revision(service, matter),
        comment_id=question["comment_id"],
        resolution="Answer read; nothing changes in the package.",
        evidence_refs=["synthetic:order-form-section-3"],
    )
    assert state(service, matter) == "ready_for_delivery"
    assert _view(api, REQUESTER, matter)["package"] == {"may_open": True, "reason": None}
    assert _told(api, matter) == TOLD_READY


def test_the_status_goes_by_the_answer_the_accept_button_goes_by(tmp_path) -> None:
    # Not a command: someone removes the stored manifest. The view then gives no reason,
    # as for a package that was never prepared. The status goes by whether a package may
    # be opened, as the "Accept delivery" button does, so it still offers nothing to accept.
    api, service, matter = _ready(tmp_path)
    with service.store.transaction() as connection:
        connection.execute("DELETE FROM deliverable_manifests WHERE matter_id = ?", (matter,))

    assert state(service, matter) == "ready_for_delivery"
    assert _view(api, REQUESTER, matter)["package"] == {"may_open": False, "reason": None}
    assert _told(api, matter) == TOLD_ENDED


# -- what the requester's view lists as delivered -------------------------------------


@pytest.mark.parametrize(
    ("end", "state_after"),
    [
        pytest.param(_comment, "ready_for_delivery", id="a comment after the package"),
        pytest.param(_replace_the_approver, "ready_for_delivery", id="another final approver"),
        pytest.param(_withdraw_as(OWNER), "closed", id="a withdrawal after the package"),
        pytest.param(_amend, "revised", id="an amendment that makes a new version"),
    ],
)
def test_the_requester_view_lists_no_package_whose_delivery_has_ended(
    tmp_path, end, state_after: str
) -> None:
    # "delivery" used to list every stored delivery manifest, so beside "package" saying
    # that nothing may be opened the requester's view still carried the ended package:
    # its folder, its file names and hashes, and an eligibility that read "eligible".
    api, service, matter = _ready(tmp_path)
    [stored] = _stored_manifests(service, matter)
    assert stored["folder"] == f"{matter}/v1/delivery" and stored["eligibility"]["eligible"]
    view = _view(api, REQUESTER, matter)
    assert view["package"] == {"may_open": True, "reason": None}
    assert view["delivery"] == [stored]
    reviewer = _view(api, OWNER, matter)["manifests"]
    assert reviewer == [stored]

    end(service, matter)

    view = _view(api, REQUESTER, matter)
    assert view["matter"]["state"] == state_after
    assert view["package"]["may_open"] is False and view["package"]["reason"]
    assert view["delivery"] == []
    # Nothing was deleted or rewritten: the manifest is stored as it was, and a reviewer's
    # view carries it as before, under "manifests" and with no "delivery" list.
    assert _stored_manifests(service, matter) == [stored]
    owner = _view(api, OWNER, matter)
    assert owner["manifests"] == reviewer and "delivery" not in owner


def test_the_requester_view_lists_the_package_of_the_delivery_that_stands_now(tmp_path) -> None:
    api, service, matter, note = _ready_with_an_open_note(tmp_path)
    [first] = _stored_manifests(service, matter)

    def listed() -> list[dict[str, Any]]:
        delivery: list[dict[str, Any]] = _view(api, REQUESTER, matter)["delivery"]
        return delivery

    assert listed() == [first]
    # A second package for the same version, after a revision and a new approval. Both
    # manifests are stored, and only the one that may be opened now is listed.
    for actor, command, args in (
        (
            APPROVER_LEAD,
            "request_revision",
            {"comment_ids": [note], "note": "The open note has to be answered first."},
        ),
        (
            OWNER,
            "respond_comment",
            {"comment_id": note, "body": "Answered; nothing changes in the package."},
        ),
        (OWNER, "submit_revision", {"note": "The open note is answered."}),
        (APPROVER_LEAD, "resume_review", {}),
        (APPROVER_LEAD, "approve", {"note": APPROVAL}),
    ):
        service.execute(actor, matter, command, revision(service, matter), args)
        assert listed() == [], command
    service.prepare_delivery(OWNER, matter, revision(service, matter))
    stored = _stored_manifests(service, matter)
    assert [m["manifest_id"] for m in stored] == [first["manifest_id"], first["manifest_id"] + 1]
    assert stored[0] == first and listed() == [stored[1]]
    # The reviewers still see both, as the record of what was written.
    assert _view(api, OWNER, matter)["manifests"] == stored

    # Accepted, the delivery stands for good, and its manifest stays listed.
    service.accept_delivery(REQUESTER, matter, revision(service, matter), note=ACCEPTANCE)
    assert state(service, matter) == "closed" and listed() == [stored[1]]


def test_a_package_prepared_on_an_earlier_version_is_not_listed_after_an_amendment(
    tmp_path,
) -> None:
    # Scenario 2 is delivered on version 3. Its package is listed while that delivery stands
    # and after it is accepted, and not once an amendment has made version 4.
    api, service, matter = _ready(tmp_path, "specialist-revision")
    [stored] = _stored_manifests(service, matter)
    assert stored["version"] == 3
    assert _view(api, REQUESTER, matter)["delivery"] == [stored]

    _amend(service, matter)

    view = _view(api, REQUESTER, matter)
    assert (view["matter"]["state"], view["matter"]["current_version"]) == ("revised", 4)
    assert view["package"] == {"may_open": False, "reason": CHANGED}
    assert view["delivery"] == []
    assert _stored_manifests(service, matter) == [stored]


# -- what the matter list shows a requester -------------------------------------------

# The entry of the list as every role gets it, in this order.
LIST_KEYS = ["matter_id", "title", "state", "current_version", "revision", "closed_outcome"]


def _list(api: PilotApi, actor: str) -> list[dict[str, Any]]:
    status, payload, _ = api.handle("GET", "/pilot/api/matters", {"X-Pilot-Actor": actor})
    assert status == 200, payload
    matters: list[dict[str, Any]] = payload["matters"]
    return matters


def _listed_and_told(api: PilotApi, matter: str) -> tuple[str, str]:
    """The pilot state the list gives for the matter, and the label it gives a requester.

    The label is the one of the status in the requester's view of that matter, always.
    """

    [entry] = [m for m in _list(api, REQUESTER) if m["matter_id"] == matter]
    assert list(entry) == [*LIST_KEYS, "requester_status_label"]
    view = _view(api, REQUESTER, matter)
    assert entry["requester_status_label"] == view["requester_status"]["label"]
    assert {key: entry[key] for key in LIST_KEYS} == {key: view["matter"][key] for key in LIST_KEYS}
    return entry["state"], entry["requester_status_label"]


def _open(api: PilotApi, matter: str) -> None:
    """A draft of scenario 1 under another matter ID, opened by the requester."""

    status, made, _ = api.handle(
        "POST",
        "/pilot/api/matters",
        {"X-Pilot-Actor": REQUESTER},
        {"scenario_id": "routine", "matter_id": matter},
    )
    assert status == 201, made


class _StepClock:
    """A service clock one second later each time it is read, not the computer's.

    The list is ordered by the time each matter was opened, so its order here does not
    depend on the wall clock.
    """

    def __init__(self) -> None:
        self.start, self.reads = datetime(2031, 3, 3, 8, 0, tzinfo=UTC), 0

    def now(self) -> str:
        self.reads += 1
        moment = self.start + timedelta(seconds=self.reads)
        return moment.isoformat(timespec="microseconds").replace("+00:00", "Z")


def _a_room_with_matters_in_many_states(tmp_path: Path) -> tuple[PilotApi, dict[str, str]]:
    """One store, and what the requester's list should say of each matter in it."""

    service = make_service(tmp_path, clock=_StepClock())
    api = PilotApi(service)
    ended = run_until(service, "routine", "A12")
    _comment(service, ended)  # ready for delivery, and the delivery has ended
    accepted = run_until(service, "specialist-revision", "B45")
    held = run_until(service, "blocked", "C02")
    for matter in ("PM-DRAFT", "PM-WITHDRAWN", "PM-DECLINED", "PM-DUPLICATE"):
        _open(api, matter)
    service.withdraw(REQUESTER, "PM-WITHDRAWN", revision(service, "PM-WITHDRAWN"), note=REASON)
    for matter in ("PM-DECLINED", "PM-DUPLICATE"):
        service.submit_intake(REQUESTER, matter, revision(service, matter))
    service.decline(
        OWNER,
        "PM-DECLINED",
        revision(service, "PM-DECLINED"),
        reason="Outside what legal reviews in this pilot.",
    )
    service.mark_duplicate(
        OWNER,
        "PM-DUPLICATE",
        revision(service, "PM-DUPLICATE"),
        original_matter_id=ended,
        reason="The same request as the routine matter, sent twice.",
    )
    return api, {
        ended: "In review",
        accepted: "Closed: delivered locally and accepted",
        held: "Received by legal",
        "PM-DRAFT": "Not yet submitted",
        "PM-WITHDRAWN": "Closed: withdrawn without delivery",
        "PM-DECLINED": "Closed: declined by legal",
        "PM-DUPLICATE": "Closed: duplicate of another matter",
    }


def test_the_matter_list_gives_a_requester_the_label_of_their_status(tmp_path) -> None:
    # The list showed every reader the pilot state. For a requester that put "ready for
    # delivery" beside "Status: In review" once a delivery had ended. Their entry now also
    # carries the label of their status, and "state" stays in it as it always was.
    api, expected = _a_room_with_matters_in_many_states(tmp_path)
    service = api.service
    with service.store.reading() as connection:
        before = list(connection.iterdump())

    entries = _list(api, REQUESTER)

    assert [m["matter_id"] for m in entries] == list(expected)
    assert {m["matter_id"]: m["requester_status_label"] for m in entries} == expected
    states = {matter: _listed_and_told(api, matter)[0] for matter in expected}
    assert states == {
        "PM-ROUTINE-001": "ready_for_delivery",
        "PM-SPECIALIST-002": "closed",
        "PM-BLOCKED-003": "triage",
        "PM-DRAFT": "intake",
        "PM-WITHDRAWN": "closed",
        "PM-DECLINED": "declined",
        "PM-DUPLICATE": "duplicate",
    }
    # Listing reads. It writes no row of any table, and so no event.
    with service.store.reading() as connection:
        assert list(connection.iterdump()) == before


def test_the_matter_list_of_every_other_role_is_as_it_always_was(tmp_path) -> None:
    api, expected = _a_room_with_matters_in_many_states(tmp_path)
    with api.service.store.reading() as connection:
        rows = connection.execute("SELECT * FROM matters ORDER BY created_at, matter_id").fetchall()
    assert [row["matter_id"] for row in rows] == list(expected)
    seen = {
        # The owner is on every matter that left the requester's hands; the drafts are not
        # theirs to see. The triage queue shows the held matter to the second owner too.
        OWNER: ["PM-ROUTINE-001", "PM-SPECIALIST-002", "PM-BLOCKED-003", "PM-DECLINED"]
        + ["PM-DUPLICATE"],
        OTHER_OWNER: ["PM-BLOCKED-003"],
        APPROVER_LEAD: ["PM-ROUTINE-001"],
        APPROVER_GC: ["PM-SPECIALIST-002"],
        SPECIALIST: ["PM-SPECIALIST-002"],
    }
    for actor, matters in seen.items():
        status, payload, _ = api.handle("GET", "/pilot/api/matters", {"X-Pilot-Actor": actor})
        assert status == 200
        as_before = {
            "matters": [
                {key: row[key] for key in LIST_KEYS} for row in rows if row["matter_id"] in matters
            ]
        }
        assert [m["matter_id"] for m in payload["matters"]] == matters, actor
        # Byte for byte, the order of the keys included: no entry gained a key.
        assert encode(payload) == encode(as_before), actor


@pytest.mark.parametrize("scenario_id", ["routine", "specialist-revision", "blocked"])
def test_the_list_and_the_status_agree_at_every_step_of_a_scenario(
    tmp_path, scenario_id: str
) -> None:
    # One helper in the service feeds both, so the two cannot differ. Each scripted step is
    # run, and after each the list entry is compared with the requester's view.
    service = make_service(tmp_path)
    api = PilotApi(service)
    script = scenario(scenario_id)
    runner = ScenarioRunner(service)
    told = []
    for step in script["steps"]:
        if step.get("restart"):
            continue
        record = runner.run_step(script, step)
        assert record["passed"], record
        told.append(_listed_and_told(api, script["matter_id"]))
    assert len(told) >= 10
    finals = {
        "routine": ("closed", "Closed: delivered locally and accepted"),
        "specialist-revision": ("closed", "Closed: delivered locally and accepted"),
        "blocked": ("triage", "Received by legal"),
    }
    assert told[-1] == finals[scenario_id]
    if scenario_id != "blocked":
        # Every stage but the first is passed on the way; the draft is opened complete.
        assert [label for _, label in dict.fromkeys(told)][:2] == [
            "Not yet submitted",
            "Received by legal",
        ]
        assert ("approved", "Approved") in told and ("ready_for_delivery", "Ready for you") in told


@pytest.mark.parametrize(
    "end",
    [_comment, _replace_the_approver],
    ids=["a comment after the approval", "another final approver"],
)
def test_the_list_and_the_status_agree_when_an_approval_no_longer_counts(tmp_path, end) -> None:
    # In "approved" a later comment, or another final approver, leaves `prepare_delivery`
    # refused. What the requester is told then is the business of the status; the list
    # says the same, whatever that is.
    service = make_service(tmp_path)
    matter = run_until(service, "routine", "A11")
    api = PilotApi(service)
    before = _listed_and_told(api, matter)
    assert before == ("approved", "Approved")

    end(service, matter)

    allowed = {item["command"]: item for item in _view(api, OWNER, matter)["allowed"]}
    assert [e["ok"] for e in allowed["prepare_delivery"]["evidence"]] == [False]
    assert _listed_and_told(api, matter)[0] == "approved"


def test_the_list_follows_the_delivery_while_the_matter_stays_ready(tmp_path) -> None:
    api, service, matter = _ready(tmp_path)
    assert _listed_and_told(api, matter) == ("ready_for_delivery", "Ready for you")
    _replace_the_approver(service, matter)
    assert _listed_and_told(api, matter) == ("ready_for_delivery", "In review")
    service.assign(
        OWNER, matter, revision(service, matter), role="final_approver", assignee_id=APPROVER_LEAD
    )
    assert _listed_and_told(api, matter) == ("ready_for_delivery", "Ready for you")
    service.accept_delivery(REQUESTER, matter, revision(service, matter), note=ACCEPTANCE)
    assert _listed_and_told(api, matter) == ("closed", "Closed: delivered locally and accepted")


# -- a delivered and accepted matter ------------------------------------------------


@pytest.mark.parametrize(
    ("scenario_id", "last", "version"),
    [("routine", "A13", 1), ("specialist-revision", "B45", 3)],
)
def test_the_accepted_package_stays_open_after_the_matter_is_closed(
    tmp_path, scenario_id: str, last: str, version: int
) -> None:
    service = make_service(tmp_path)
    matter = run_until(service, scenario_id, last)
    api = PilotApi(service)

    row = _view(api, OWNER, matter)["matter"]
    assert (row["state"], row["closed_outcome"]) == ("closed", "delivered_locally_and_accepted")
    _offered(api, matter, READERS[scenario_id])
    # It is the package of the version the acceptance was recorded on.
    with service.store.reading() as connection:
        accepted = connection.execute(
            "SELECT version, content_hash FROM decisions WHERE matter_id = ? AND "
            "kind = 'acceptance'",
            (matter,),
        ).fetchall()
        manifest = connection.execute(
            "SELECT version, content_hash FROM deliverable_manifests WHERE matter_id = ? "
            "AND kind = 'delivery_package' ORDER BY manifest_id DESC LIMIT 1",
            (matter,),
        ).fetchone()
    assert [tuple(a) for a in accepted] == [tuple(manifest)] and manifest["version"] == version
    folder = service.export_root / matter / f"v{version}" / "delivery"
    assert _package(api, REQUESTER, matter)[1] == (folder / "customer-package.html").read_text(
        encoding="utf-8"
    )


@pytest.mark.parametrize(
    "edit",
    [
        "UPDATE deliverable_manifests SET content_hash = 'not the accepted content' "
        "WHERE matter_id = ?",
        "UPDATE deliverable_manifests SET version = version + 1 WHERE matter_id = ?",
        "DELETE FROM decisions WHERE matter_id = ? AND kind = 'acceptance'",
    ],
    ids=["another content hash", "another version", "no acceptance on record"],
)
def test_a_stored_package_that_is_not_the_accepted_one_is_refused(tmp_path, edit: str) -> None:
    # No command leaves a store like this; someone edited it. The page is then not served.
    service = make_service(tmp_path)
    matter = run_until(service, "routine", "A13")
    api = PilotApi(service)
    _offered(api, matter, READERS["routine"])

    with service.store.transaction() as connection:
        connection.execute(edit, (matter,))

    _refused(api, matter, READERS["routine"], NOT_THE_ACCEPTED_ONE)


# -- no package, and no access ------------------------------------------------------


@pytest.mark.parametrize(
    ("scenario_id", "last", "withdraw", "readers"),
    [
        ("routine", "A06", False, READERS["routine"]),  # in review
        ("routine", "A11", False, READERS["routine"]),  # approved, nothing prepared yet
        ("routine", "A11", True, READERS["routine"]),  # withdrawn before any package
        # An internal review draft was written; that is not a delivery package.
        ("specialist-revision", "B11", False, READERS["specialist-revision"]),
        ("blocked", "C02", False, (REQUESTER, OWNER)),  # in triage, in the owners' queue
    ],
)
def test_a_matter_whose_package_was_never_prepared_gives_no_reason(
    tmp_path, scenario_id: str, last: str, withdraw: bool, readers: tuple[str, ...]
) -> None:
    service = make_service(tmp_path)
    matter = run_until(service, scenario_id, last)
    if withdraw:
        service.withdraw(OWNER, matter, revision(service, matter), note=REASON)

    _refused(PilotApi(service), matter, readers, None)


def test_someone_who_is_not_on_the_matter_learns_nothing_about_its_package(tmp_path) -> None:
    api, service, matter = _ready(tmp_path)

    def answer() -> tuple[int, str, str]:
        status, payload = _package(api, OTHER_OWNER, matter)
        return status, payload["error"], payload["message"]

    refusal = (403, "permission_denied", f"{OTHER_OWNER} has no access to matter {matter}")
    assert answer() == refusal
    service.withdraw(OWNER, matter, revision(service, matter), note=REASON)
    assert answer() == refusal
    status, payload = _package(api, OWNER, "PM-NO-SUCH-MATTER")
    assert (status, payload["error"]) == (404, "not_found")


def test_a_missing_package_file_is_named_and_not_a_server_error(tmp_path) -> None:
    # The records say the delivery stands, but its file is gone from the export folder. The
    # route answers not found and names the file; the view still reports the records.
    api, service, matter = _ready(tmp_path)
    with service.store.reading() as connection:
        body = connection.execute(
            "SELECT body FROM deliverable_manifests WHERE matter_id = ? AND kind = "
            "'delivery_package' ORDER BY manifest_id DESC LIMIT 1",
            (matter,),
        ).fetchone()["body"]
    folder = json.loads(body)["folder"]
    (service.export_root / folder / "customer-package.html").unlink()

    missing = (
        "the package file of this delivery is missing from the export folder: "
        f"{folder}/customer-package.html"
    )
    for actor in READERS["routine"]:
        status, answer = _package(api, actor, matter)
        assert (status, answer["error"], answer["message"]) == (404, "not_found", missing)
        assert _view(api, actor, matter)["package"] == {"may_open": True, "reason": None}
    # Someone not on the matter learns nothing about the file either.
    status, answer = _package(api, OTHER_OWNER, matter)
    assert (status, answer["error"]) == (403, "permission_denied")


# -- the page -----------------------------------------------------------------------


def test_the_room_takes_the_package_line_from_the_service() -> None:
    # One helper draws the link or the sentence for both views, from view.package alone.
    assert REVIEW_ROOM_HTML.count("Open the approved customer package") == 1
    assert REVIEW_ROOM_HTML.count("function packageLine(view, href)") == 1
    assert REVIEW_ROOM_HTML.count('packageLine(view, "') == 2  # requester and reviewer
    assert "view.package.may_open" in REVIEW_ROOM_HTML
    assert 'view.package.reason || "No approved package yet."' in REVIEW_ROOM_HTML
    # The page no longer works it out from the stored manifests.
    assert "view.delivery" not in REVIEW_ROOM_HTML
    assert 'm.kind === "delivery_package"' not in REVIEW_ROOM_HTML
    assert "innerHTML" not in REVIEW_ROOM_HTML


def test_the_room_shows_a_requester_the_status_label_in_the_matter_list() -> None:
    # One pill per entry of the list. It shows the label the entry carries, which only a
    # requester's entry does, and the pilot state where the entry carries none.
    assert REVIEW_ROOM_HTML.count("matter.requester_status_label") == 1
    assert "const label = matter.requester_status_label;" in REVIEW_ROOM_HTML
    assert (
        'h("span", {class: label ? "pill stage" : "pill"}, label || words(matter.state))'
        in REVIEW_ROOM_HTML
    )
    assert REVIEW_ROOM_HTML.count("words(matter.state)") == 1
    # A status label can be longer than the list is wide, so its pill, and no other, wraps.
    assert REVIEW_ROOM_HTML.count("pill stage") == 1
    assert ".pill.stage{white-space:normal;border-radius:12px}" in REVIEW_ROOM_HTML
    assert REVIEW_ROOM_HTML.count("white-space:normal") == 1


def test_the_room_offers_acceptance_only_beside_a_package_that_may_be_opened() -> None:
    # The button follows view.package.may_open, which asks the evidence accept_delivery
    # needs, so the room never offers to accept a delivery that has ended.
    assert REVIEW_ROOM_HTML.count('formButton("Accept delivery"') == 1
    assert (
        'view.matter.state === "ready_for_delivery" && view.package.may_open ? '
        'h("div", null, formButton("Accept delivery"'
    ) in REVIEW_ROOM_HTML


# -- the records --------------------------------------------------------------------

DOCS = Path(__file__).resolve().parents[1] / "docs"
ROW = 'The room shows "The package prepared earlier is no longer approved" where the link was'


def test_the_runbook_says_what_a_requester_is_shown_once_a_delivery_has_ended() -> None:
    # The sentences that describe the behaviour the tests above pin, held to the words
    # those tests compare: the explanation, the next step and the two labels.
    runbook = (DOCS / "pilot" / "RUNBOOK.md").read_text(encoding="utf-8")
    [section_7] = [
        paragraph
        for paragraph in runbook.split("\n\n")
        if paragraph.startswith("A stored manifest alone does not open a package either.")
    ]
    stage, label, explanation, action, _ = TOLD_ENDED
    assert (stage, label, TOLD_READY[1]) == ("in_review", "In review", "Ready for you")
    for sentence in (
        # What ends a delivery, and what does not.
        "A withdrawal, a revision request, an amendment or restore that makes a new version, "
        "a comment written, resolved or reopened after the package was prepared (any change "
        "to the state of a comment), and the assignment of another final approver in place of "
        "the one who approved each end it.",
        "An answer to a comment changes no comment's state and ends nothing.",
        # The stage, the explanation and the next step.
        "The requester's status goes by the same answer.",
        "A matter that stays `ready_for_delivery` after its delivery ended, because a comment "
        "was written, resolved or reopened after the package was prepared or because another "
        f'final approver was assigned, is shown to its requester as "{label}", not as '
        f'"{TOLD_READY[1]}".',
        f'The explanation reads "{explanation}", the next step is "{action}" unless a question '
        'to the requester is open, and the room offers no "Accept delivery" button.',
        "The state itself does not change, and from there a reviewer requests a revision, "
        "because `approve` and `prepare_delivery` are not open from that state.",
        # The matter list and the delivery list.
        "A reviewer's matter list still shows the pilot state, `ready for delivery`.",
        "The requester's matter list shows the label of their status instead, here "
        f'"{label}", so the list and the status say the same in every state.',
        "The requester's view (`GET /pilot/api/matters/{id}`) lists as `delivery` only the "
        "manifest of the package that may be opened now: one manifest while a delivery stands "
        "and after it was accepted, and none once the delivery has ended.",
        "A reviewer's view keeps every stored manifest under `manifests`.",
        # The ways back, and the one change that has none.
        "If the reviewed state the approval was given on comes back, the delivery stands "
        f'again and the status reads "{TOLD_READY[1]}" again.',
        "That happens when a comment is put back into the state it had when the package was "
        "prepared (a reopened comment is resolved again, or a resolved one is reopened) or "
        "when the earlier approver is assigned again.",
        "A comment written after the package was prepared cannot be taken back: resolving it "
        "does not restore the delivery.",
        "A new package opens after a new final approval and a new `prepare_delivery`.",
    ):
        assert sentence in section_7, sentence

    # The troubleshooting row: one row, in full.
    [row] = [line for line in runbook.splitlines() if line.startswith(f"| {ROW} |")]
    assert row == (
        f"| {ROW} | The delivery ended after the package was prepared (section 7). If the "
        "matter is still open, complete the review, obtain a new final approval and run "
        "`prepare_delivery` again. While the matter is still `ready_for_delivery`, its "
        f'requester reads "{label}", in the status and in their matter list; a reviewer starts '
        "with `request_revision`. After the new final approval the requester reads "
        f'"Approved", and "{TOLD_READY[1]}" once the new package is prepared. A withdrawn '
        "matter stays closed. |"
    )
    # The row said "until then", as if the requester read "In review" up to the new package.
    assert 'shows its requester "In review" until then' not in runbook


def test_the_api_guide_says_what_the_views_and_the_list_carry() -> None:
    guide = " ".join((DOCS / "API.md").read_text(encoding="utf-8").split())
    room = guide.split("## Pilot review-room API ", 1)[1].split(" ## ", 1)[0]
    _, label, _, action, _ = TOLD_ENDED
    for sentence in (
        # What ends a delivery, and the three answers of `package`.
        "A withdrawal, a revision request, a new version, a comment written, resolved or "
        "reopened after the package was prepared (any change to the state of a comment) or "
        "another final approver assigned in place of the one who approved ends the delivery.",
        'as `package`: `{"may_open": true, "reason": null}` while the package may be opened, '
        '`{"may_open": false, "reason": null}` when none was ever prepared, and `{"may_open": '
        'false, "reason": "<sentence>"}` when one was prepared and its delivery has ended.',
        "The review room shows the link or the sentence from that field, and offers the "
        'requester "Accept delivery" only while `may_open` is true.',
        # The status.
        "The requester's `requester_status` goes by the same answer: a matter that is "
        "`ready_for_delivery` while `may_open` is false has the stage `in_review` and, unless "
        f'a question to the requester is open, the next step "{action}", not `ready` and '
        f'"{TOLD_READY[3]}".',
        # The delivery list and the manifests.
        "`package` is the answer to whether a package may be opened.",
        "In a requester's view, `delivery` holds the manifest of the package that may be "
        "opened now and nothing else: one manifest while `package.may_open` is true, and an "
        "empty list when no package was prepared or its delivery has ended.",
        "An earlier package of the same matter is not listed.",
        "A reviewer's view has no `delivery`.",
        "Its `manifests` holds every manifest stored for the matter, internal review drafts "
        "and packages whose delivery has ended included, as the record of what was written.",
        # The matter list.
        "`GET /pilot/api/matters` gives each matter as "
        + ", ".join(f"`{key}`" for key in LIST_KEYS[:-1])
        + f" and `{LIST_KEYS[-1]}`.",
        "`state` is the pilot state, for every role.",
        "For a business requester each entry also carries `requester_status_label`, the "
        "`label` of the `requester_status` in their view of that matter, for example "
        f'"{label}" for a matter that is `ready_for_delivery` after its delivery ended and '
        '"Closed: withdrawn without delivery" for a withdrawn one.',
        "The review room shows a requester that label in the list and every other role the "
        "pilot state.",
        "No other role's entry has the key.",
    ):
        assert sentence in room, sentence


def test_the_capability_record_says_when_the_package_is_opened_and_what_is_shown() -> None:
    record = (DOCS / "pilot" / "CAPABILITY_RECORD.md").read_text(encoding="utf-8")
    [row] = [
        line for line in record.splitlines() if line.startswith("| The approved package is opened")
    ]
    capability, modules, tests = (cell.strip() for cell in row.strip("|").split("|"))
    assert capability == (
        "The approved package is opened only while its delivery stands (ready for delivery "
        "with `delivery_manifest_current` passing, or delivered and accepted). The service "
        "decides it once, for the package route, for the review room and for the requester's "
        "status; a stored manifest alone opens nothing. A matter that stays ready for delivery "
        f'after its delivery ended is shown to its requester as "{TOLD_ENDED[1]}", with nothing '
        "to accept, in the status and in their matter list, which shows a requester the label "
        "of the status and not the pilot state. The requester's view lists the manifest of a "
        "package only while that package may be opened"
    )
    assert "`src/pilot/requester_status.py`" in modules and "`src/pilot/service.py`" in modules
    assert "`tests/test_pilot_package_standing.py`" in tests

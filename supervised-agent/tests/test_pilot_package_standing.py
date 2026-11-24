"""The approved customer package is offered only while its delivery stands.

It stands while the matter is ready for delivery and the evidence ``accept_delivery`` needs
holds, and after the requester accepted that delivery. A withdrawal, a revision request, a
new version, a comment written, resolved or reopened after the package was prepared, or
another final approver in place of the one who approved ends it. The package route then
refuses, the matter view says why, and the stored manifest and its files stay for the audit
trail. A matter that stays ready for delivery after its delivery ended is shown to its
requester as "In review", not as a package to accept. The requester's view lists only the
manifest of the package that may be opened, and their matter list shows the label of their
status in place of the pilot state. An approved matter from whose approval no package can
be prepared is shown to its requester as "In review" too, and is not told that a package is
being prepared. The last tests hold the runbook, the API guide and the capability record to
the sentences that describe this. Everything here is synthetic.
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
from src.pilot.service import PilotService, VersionBody
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


# -- a matter whose stored version cannot be read --------------------------------------

# A requester's list builds the status of each matter from its current version. A version
# body the application cannot read is a fault in the store. It is not hidden: the list stops
# with the error that matter's own view gives, no label is invented for the matter and the
# matter is not left out. The error names the matter and the version, and repeats nothing
# of the stored text.
A_KEY_IN_THE_STORE = "A key written into the store by hand"


def _retyped(body: str, **fields: Any) -> str:
    return json.dumps({**json.loads(body), **fields})


def _a_fact_under_a_key_of_its_own(body: str) -> str:
    stored = json.loads(body)
    stored["intake"]["facts"] = {A_KEY_IN_THE_STORE: 5}
    return json.dumps(stored)


ONE_PROBLEM_IN_THE_TEXT = (
    "1 problem(s) in the stored version, the first in the text as a whole (json_invalid)"
)
UNREADABLE = [
    pytest.param(lambda body: "not json", ONE_PROBLEM_IN_THE_TEXT, id="no JSON at all"),
    pytest.param(lambda body: body[:200], ONE_PROBLEM_IN_THE_TEXT, id="JSON cut short"),
    pytest.param(lambda body: "", ONE_PROBLEM_IN_THE_TEXT, id="an empty text"),
    pytest.param(
        lambda body: "{}",
        f"{sum(f.is_required() for f in VersionBody.model_fields.values())} problem(s) in the "
        "stored version, the first in the field version (missing)",
        id="JSON of another shape",
    ),
    pytest.param(
        lambda body: _retyped(body, required_final_tier=7, scope_exclusions="none"),
        "2 problem(s) in the stored version, the first in the field required_final_tier "
        "(string_type)",
        id="two fields of another type",
    ),
    pytest.param(
        _a_fact_under_a_key_of_its_own,
        "1 problem(s) in the stored version, the first in the field intake (string_type)",
        id="a key of the stored text",
    ),
]


def _get(api: PilotApi, actor: str, path: str) -> tuple[int, Any]:
    status, answer, _ = api.handle("GET", path, {"X-Pilot-Actor": actor})
    return status, answer


def _two_matters_in_review(tmp_path: Path) -> tuple[PilotApi, str, str, int]:
    """Two matters of one requester, and the current version of the second."""

    service = make_service(tmp_path, clock=_StepClock())
    api = PilotApi(service)
    good = run_until(service, "routine", "A06")
    bad = run_until(service, "specialist-revision", "B10")
    assert [(m["matter_id"], m["requester_status_label"]) for m in _list(api, REQUESTER)] == [
        (good, "In review"),
        (bad, "In review"),
    ]
    version = _view(api, OWNER, bad)["matter"]["current_version"]
    assert version == 2
    return api, good, bad, version


def _stored_body(service: PilotService, matter: str, version: int) -> str:
    with service.store.reading() as connection:
        row = connection.execute(
            "SELECT body FROM matter_versions WHERE matter_id = ? AND version = ?",
            (matter, version),
        ).fetchone()
    return str(row["body"])


def _store_body(service: PilotService, matter: str, version: int, body: str) -> None:
    with service.store.transaction() as connection:
        connection.execute(
            "UPDATE matter_versions SET body = ? WHERE matter_id = ? AND version = ?",
            (body, matter, version),
        )


@pytest.mark.parametrize(("damage", "problem"), UNREADABLE)
def test_a_version_that_cannot_be_read_stops_the_requesters_list_and_names_the_matter(
    tmp_path, damage: Callable[[str], str], problem: str
) -> None:
    api, good, bad, version = _two_matters_in_review(tmp_path)
    service = api.service
    stored = _stored_body(service, bad, version)
    _store_body(service, bad, version, damage(stored))

    refused = (
        422,
        {
            "error": "invalid_command",
            "message": f"version {version} of matter {bad} cannot be read from the store: {problem}",
        },
    )
    # The matter's own view stops, for its requester and for a reviewer.
    for actor in (REQUESTER, OWNER):
        assert _get(api, actor, f"/pilot/api/matters/{bad}") == refused
    # The requester's list stops with the same error. It has no entry for the matter, so no
    # label was made up for it, and no shorter list either, so the matter was not left out.
    assert _get(api, REQUESTER, "/pilot/api/matters") == refused
    # The error repeats nothing of the stored text: no value, and no key of it.
    told = encode(refused[1]).decode("utf-8")
    for text in (stored[:40], stored[160:200], A_KEY_IN_THE_STORE, "input_value", "pydantic"):
        assert text not in told, text

    # The fault is one matter's. The other one still opens for the requester, and a
    # reviewer's list, which reads no version, gives both matters as they are stored.
    assert _told(api, good)[:2] == ("in_review", "In review")
    assert [(m["matter_id"], m["state"]) for m in _list(api, OWNER)] == [
        (good, "review"),
        (bad, "review"),
    ]
    # With the body as the application wrote it, the list answers again.
    _store_body(service, bad, version, stored)
    assert _listed_and_told(api, bad) == ("review", "In review")


def test_a_matter_without_its_current_version_stops_the_requesters_list_as_its_view(
    tmp_path,
) -> None:
    # The neighbouring fault, where the error always named the matter: the row is gone.
    api, good, bad, version = _two_matters_in_review(tmp_path)
    with api.service.store.transaction() as connection:
        connection.execute("DELETE FROM matter_versions WHERE matter_id = ?", (bad,))
    refused = (404, {"error": "not_found", "message": f"matter {bad} has no version {version}"})
    for actor in (REQUESTER, OWNER):
        assert _get(api, actor, f"/pilot/api/matters/{bad}") == refused
    assert _get(api, REQUESTER, "/pilot/api/matters") == refused
    assert _told(api, good)[:2] == ("in_review", "In review")
    assert [m["matter_id"] for m in _list(api, OWNER)] == [good, bad]


def test_the_history_names_an_earlier_version_that_cannot_be_read(tmp_path) -> None:
    # The view and the list read the current version only. The history reads every version,
    # and names the one it cannot read in the same words.
    api, _, bad, version = _two_matters_in_review(tmp_path)
    _store_body(api.service, bad, version - 1, "not json")
    assert _listed_and_told(api, bad) == ("review", "In review")
    assert _view(api, OWNER, bad)["matter"]["current_version"] == version
    assert _get(api, OWNER, f"/pilot/api/matters/{bad}/history") == (
        422,
        {
            "error": "invalid_command",
            "message": f"version {version - 1} of matter {bad} cannot be read from the store: "
            f"{ONE_PROBLEM_IN_THE_TEXT}",
        },
    )


# -- the other stored rows a requester's status reads ---------------------------------

# A requester's view and matter list read the matter's comments in every state. In
# `approved` and `ready_for_delivery` their status also asks the export gate, which reads
# the proposed changes of the current version and the records of the actors who signed
# off or approved. One of these rows that the application cannot read stops the view and
# the list as an unreadable version does. The error names the matter and the kind of row.
# It names no reviewer and repeats nothing of the stored text, which holds what a
# requester is not shown: the rationale of a change, a comment among reviewers, who
# approved. The validation library's own message quoted that text.
NOT_FOR_THE_REQUESTER = "Words in the store that a requester is not shown"
# The kind of row, how it is found for a matter, and what the error calls it.
A_CHANGE, A_COMMENT = "a proposed change", "a comment"
AN_APPROVER, A_SPECIALIST = "the approver's record", "the specialist's record"
DECIDED = "the record of an actor who decided on matter {matter}"
STORED_ROWS = {
    A_CHANGE: (
        "SELECT rowid FROM changes WHERE matter_id = :matter AND version = (SELECT "
        "current_version FROM matters WHERE matter_id = :matter) ORDER BY position LIMIT 1",
        "changes",
        "a proposed change of version {version} of matter {matter}",
        "change",
    ),
    A_COMMENT: (
        "SELECT rowid FROM comments WHERE matter_id = :matter ORDER BY rowid LIMIT 1",
        "comments",
        "a comment on matter {matter}",
        "comment",
    ),
    AN_APPROVER: (
        f"SELECT rowid FROM actors WHERE actor_id = '{APPROVER_GC}' AND :matter != ''",
        "actors",
        DECIDED,
        "record",
    ),
    A_SPECIALIST: (
        f"SELECT rowid FROM actors WHERE actor_id = '{SPECIALIST}' AND :matter != ''",
        "actors",
        DECIDED,
        "record",
    ),
}
# What is written over the row, and the problem the error gives for it. The retyped field
# holds words of the store as a value, and for a comment and an actor also as a key.
RETYPED = {
    A_CHANGE: ("decision", NOT_FOR_THE_REQUESTER, "literal_error"),
    A_COMMENT: ("body", {NOT_FOR_THE_REQUESTER: 1}, "string_type"),
    AN_APPROVER: ("approval_tier", {NOT_FOR_THE_REQUESTER: 1}, "string_type"),
    A_SPECIALIST: ("specialty", {NOT_FOR_THE_REQUESTER: 1}, "string_type"),
}


def _row(service: PilotService, kind: str, matter: str) -> tuple[int, str]:
    """The row of this kind for the matter: its rowid and the text the application wrote."""

    select, table = STORED_ROWS[kind][:2]
    with service.store.reading() as connection:
        (rowid,) = connection.execute(select, {"matter": matter}).fetchone()
        (body,) = connection.execute(f"SELECT body FROM {table} WHERE rowid = ?", (rowid,))
    return int(rowid), str(body[0])


def _write_row(service: PilotService, kind: str, rowid: int, body: str) -> None:
    with service.store.transaction() as connection:
        connection.execute(
            f"UPDATE {STORED_ROWS[kind][1]} SET body = ? WHERE rowid = ?", (body, rowid)
        )


def _cannot_be_read(kind: str, matter: str, version: int, problem: str) -> tuple[int, Any]:
    _, _, what, noun = STORED_ROWS[kind]
    named = what.format(version=version, matter=matter)
    message = f"{named} cannot be read from the store: {problem.format(noun=noun)}"
    return 422, {"error": "invalid_command", "message": message}


@pytest.mark.parametrize("kind", list(STORED_ROWS))
@pytest.mark.parametrize("cut_short", [True, False], ids=["JSON cut short", "a field retyped"])
def test_another_row_that_cannot_be_read_names_the_matter_and_repeats_nothing(
    tmp_path, kind: str, cut_short: bool
) -> None:
    service = make_service(tmp_path, clock=_StepClock())
    api = PilotApi(service)
    good = run_until(service, "routine", "A06")
    bad = run_until(service, "specialist-revision", "B42")
    assert _listed_and_told(api, bad) == ("approved", "Approved")
    version = _view(api, OWNER, bad)["matter"]["current_version"]
    # The two actors whose records the gate reads for this matter: who signed off, who approved.
    with service.store.reading() as connection:
        decided = connection.execute(
            "SELECT DISTINCT kind, actor_id FROM decisions WHERE matter_id = ? AND kind IN "
            "('specialist_signoff', 'final_approval') ORDER BY kind",
            (bad,),
        ).fetchall()
    assert [tuple(row) for row in decided] == [
        ("final_approval", APPROVER_GC),
        ("specialist_signoff", SPECIALIST),
    ]

    rowid, stored = _row(service, kind, bad)
    if cut_short:
        damaged = stored[: len(stored) * 2 // 3]
        problem = (
            "1 problem(s) in the stored {noun}, the first in the text as a whole (json_invalid)"
        )
    else:
        field, value, error = RETYPED[kind]
        damaged = json.dumps({**json.loads(stored), field: value})
        problem = f"1 problem(s) in the stored {{noun}}, the first in the field {field} ({error})"
    _write_row(service, kind, rowid, damaged)

    refused = _cannot_be_read(kind, bad, version, problem)
    # The requester's view of the matter and their whole list stop with the error, and so
    # does a reviewer's view of the matter: the row is read in one place for all of them.
    assert _get(api, REQUESTER, f"/pilot/api/matters/{bad}") == refused
    assert _get(api, REQUESTER, "/pilot/api/matters") == refused
    assert _get(api, OWNER, f"/pilot/api/matters/{bad}") == refused
    # It names the matter and no reviewer, and repeats nothing of the stored text: not its
    # beginning, not the place where it breaks off, no value and no key.
    told = encode(refused[1]).decode("utf-8")
    assert bad in told
    for text in (
        stored[:30],
        damaged[-30:],
        NOT_FOR_THE_REQUESTER,
        APPROVER_GC,
        SPECIALIST,
        "input_value",
        "pydantic",
    ):
        assert text not in told, text

    # The fault is one matter's. The other one opens, and a reviewer's list is unchanged.
    assert _told(api, good)[:2] == ("in_review", "In review")
    assert [(m["matter_id"], m["state"]) for m in _list(api, OWNER)] == [
        (good, "review"),
        (bad, "approved"),
    ]
    # With the row as the application wrote it, the view and the list answer again.
    _write_row(service, kind, rowid, stored)
    assert _listed_and_told(api, bad) == ("approved", "Approved")


# Which of these rows a requester's view and list read in which state. The comments are
# read in every state. The gate is asked only while the matter is approved, for whether a
# package can be prepared, and while it is ready for delivery, for whether the delivery
# stands. So a damaged change, or a damaged record of the approver or of the specialist who
# signed off, stops a requester there and in no other state.
READ_FOR_THE_REQUESTER = [
    pytest.param("B10", "review", "In review", {A_COMMENT}, id="review"),
    pytest.param("B42", "approved", "Approved", set(STORED_ROWS), id="approved"),
    pytest.param(
        "B44", "ready_for_delivery", "Ready for you", set(STORED_ROWS), id="ready for delivery"
    ),
    pytest.param(
        "B45", "closed", "Closed: delivered locally and accepted", {A_COMMENT}, id="closed"
    ),
]


@pytest.mark.parametrize(("step", "reached", "label", "read"), READ_FOR_THE_REQUESTER)
def test_a_damaged_change_or_decider_stops_the_requester_only_where_the_gate_is_asked(
    tmp_path, step: str, reached: str, label: str, read: set[str]
) -> None:
    service = make_service(tmp_path, clock=_StepClock())
    api = PilotApi(service)
    matter = run_until(service, "specialist-revision", step)
    assert _listed_and_told(api, matter) == (reached, label)
    version = _view(api, OWNER, matter)["matter"]["current_version"]
    problem = "1 problem(s) in the stored {noun}, the first in the text as a whole (json_invalid)"
    for kind in STORED_ROWS:
        rowid, stored = _row(service, kind, matter)
        _write_row(service, kind, rowid, stored[:20])
        refused = _cannot_be_read(kind, matter, version, problem)
        if kind in read:
            assert _get(api, REQUESTER, f"/pilot/api/matters/{matter}") == refused, kind
            assert _get(api, REQUESTER, "/pilot/api/matters") == refused, kind
        else:
            # Not read for the requester here: their view and list answer as before.
            assert _listed_and_told(api, matter) == (reached, label), kind
        _write_row(service, kind, rowid, stored)
    assert _listed_and_told(api, matter) == (reached, label)


def test_an_actors_own_record_that_cannot_be_read_names_the_actor(tmp_path) -> None:
    # Every request reads the record of the actor who makes it. That record is the
    # caller's own, so the error names it, and no matter. A reviewer's list reads no other
    # actor's record and still answers. A reviewer's view of a matter reads the records of
    # the actors assigned to it, and names the one it cannot read: who is assigned to a
    # matter is a reviewer's to see.
    service = make_service(tmp_path, clock=_StepClock())
    api = PilotApi(service)
    matter = run_until(service, "routine", "A06")
    with service.store.transaction() as connection:
        (stored,) = connection.execute(
            "SELECT body FROM actors WHERE actor_id = ?", (REQUESTER,)
        ).fetchone()
        connection.execute(
            "UPDATE actors SET body = ? WHERE actor_id = ?", (stored[:40], REQUESTER)
        )
    refused = (
        422,
        {
            "error": "invalid_command",
            "message": f"the record of actor {REQUESTER} cannot be read from the store: 1 "
            "problem(s) in the stored record, the first in the text as a whole (json_invalid)",
        },
    )
    assert _get(api, REQUESTER, "/pilot/api/matters") == refused
    assert _get(api, REQUESTER, f"/pilot/api/matters/{matter}") == refused
    assert [m["matter_id"] for m in _list(api, OWNER)] == [matter]
    assert _get(api, OWNER, f"/pilot/api/matters/{matter}") == refused


# -- what the requester is told while an approval gives no package --------------------

# An approved matter is with the matter owner, who prepares the package. `prepare_delivery`
# can be refused all the same: the approval no longer counts, or it never allowed a package.
# The requester is then shown "In review", with a sentence that names no cause, and is not
# told that a package is being prepared. The service asks the evidence `prepare_delivery`
# needs and hands the answer to the status; these tests read it over the API.
TOLD_APPROVED = (
    "approved",
    "Approved",
    "The review is approved. The package for the customer is being prepared.",
    "No action needed from you.",
    False,
)
NO_PACKAGE = (
    "The review was approved, but a package for the customer cannot be prepared from that "
    "approval as the matter stands now. Legal has to work on the matter again before a "
    "package is ready for you."
)
TOLD_NO_PACKAGE = ("in_review", "In review", NO_PACKAGE, "No action needed from you.", False)
TOLD_IN_REVIEW = (
    "in_review",
    "In review",
    "Reviewers are working on the customer's draft.",
    "No action needed from you.",
    False,
)
SECTION = {"anchor_kind": "deliverable_section", "anchor_id": "accepted_exceptions"}
# A matter document listed by its hash. The pilot gives the assessment no folder to check it
# in, so it stays "not_checked", and an approval then does not allow export.
ORDER_FORM = {
    "document_id": "order_form",
    "title": "Synthetic order form",
    "kind": "order_form",
    "path": "order-form.txt",
    "sha256": "a" * 64,
    "source_ref": "synthetic:order-form",
}
# The keys of a reviewer's matter view over the API, presence included. No key is added.
REVIEWER_VIEW_KEYS = [
    "actor",
    "allowed",
    "also_open_by",
    "assessment",
    "assignments",
    "audit_chain",
    "changes",
    "comments",
    "decisions",
    "eligibility",
    "external_delivery_allowed",
    "findings",
    "identity_notice",
    "intake",
    "manifests",
    "matter",
    "package",
    "presence_notice",
    "readiness",
    "required_facts",
    "snooze",
    "snooze_limits",
    "source_support",
    "timeline",
    "timing",
    "version",
    "versions",
    "view",
]


def _post(api: PilotApi, actor: str, matter: str, command: str, **args: Any) -> tuple[int, Any]:
    status, answer, _ = api.handle(
        "POST",
        f"/pilot/api/matters/{matter}/commands",
        {"X-Pilot-Actor": actor},
        {"command": command, "expected_revision": revision(api.service, matter), "args": args},
    )
    return status, answer


def _do(api: PilotApi, actor: str, matter: str, command: str, **args: Any) -> dict[str, Any]:
    """Run a command over the API, as the room does. It has to be accepted."""

    status, answer = _post(api, actor, matter, command, **args)
    assert status == 200, (actor, command, answer)
    view: dict[str, Any] = answer
    return view


def _comment_id(api: PilotApi, matter: str, body: str) -> str:
    [found] = [c for c in _view(api, OWNER, matter)["comments"] if c["body"] == body]
    return str(found["comment_id"])


def _a_room(tmp_path: Path) -> tuple[PilotApi, PilotService]:
    # The step clock, so that two readings of a view can be compared byte for byte.
    service = make_service(tmp_path, clock=_StepClock())
    return PilotApi(service), service


def _a_comment_written_after_the_approval(tmp_path: Path) -> tuple[PilotApi, str, str]:
    api, service = _a_room(tmp_path)
    matter = run_until(service, "routine", "A11")
    _do(api, APPROVER_LEAD, matter, "comment", body=LATE_NOTE, **SECTION)
    return api, matter, APPROVER_LEAD


def _a_note_resolved_after_the_approval(tmp_path: Path) -> tuple[PilotApi, str, str]:
    # The note was open when the approval was given. Nothing is written after it.
    api, service = _a_room(tmp_path)
    matter = run_until(service, "routine", "A06")
    _do(api, OWNER, matter, "comment", body=EARLY_NOTE, **SECTION)
    _continue(service, "routine", "A06", "A11")
    _do(
        api,
        APPROVER_LEAD,
        matter,
        "resolve_comment",
        comment_id=_comment_id(api, matter, EARLY_NOTE),
        resolution="Read and noted; nothing changes in the package.",
    )
    return api, matter, APPROVER_LEAD


def _a_note_reopened_after_the_approval(tmp_path: Path) -> tuple[PilotApi, str, str]:
    # The note was resolved when the approval was given.
    api, service = _a_room(tmp_path)
    matter = run_until(service, "routine", "A06")
    _do(api, OWNER, matter, "comment", body=EARLY_NOTE, **SECTION)
    note = _comment_id(api, matter, EARLY_NOTE)
    _do(api, OWNER, matter, "resolve_comment", comment_id=note, resolution="Read and noted.")
    _continue(service, "routine", "A06", "A11")
    _do(api, OWNER, matter, "reopen_comment", comment_id=note, reason="One more look at it.")
    return api, matter, APPROVER_LEAD


def _another_final_approver(tmp_path: Path) -> tuple[PilotApi, str, str]:
    api, service = _a_room(tmp_path)
    matter = run_until(service, "routine", "A11")
    _do(api, OWNER, matter, "assign", role="final_approver", assignee_id=APPROVER_GC)
    return api, matter, APPROVER_GC


def _a_scope_hold_when_the_matter_was_approved(tmp_path: Path) -> tuple[PilotApi, str, str]:
    # After triage the requester changes a routing input, and the new version is outside the
    # pilot charter. `approve` does not ask `pilot_scope_met`, so the matter is approved.
    api, service = _a_room(tmp_path)
    matter = run_until(service, "routine", "A09")
    _do(
        api,
        REQUESTER,
        matter,
        "amend_matter",
        reason="The customer now asks for uncapped liability.",
        routing_fields={"uncapped_liability": True},
    )
    _do(api, OWNER, matter, "resume_review")
    _do(api, OWNER, matter, "assign", role="final_approver", assignee_id=APPROVER_GC)
    _do(api, APPROVER_GC, matter, "approve", note=APPROVAL)
    return api, matter, APPROVER_GC


def _an_unchecked_listed_document(tmp_path: Path) -> tuple[PilotApi, str, str]:
    api, service = _a_room(tmp_path)
    matter = run_until(service, "routine", "A09")
    _do(
        api,
        OWNER,
        matter,
        "amend_matter",
        reason="The order form belongs to the matter file.",
        matter_fields={"documents": [ORDER_FORM]},
    )
    _do(api, OWNER, matter, "resume_review")
    _do(api, APPROVER_LEAD, matter, "approve", note=APPROVAL)
    return api, matter, APPROVER_LEAD


# Each way an approved matter gets no package, and the gate check that then fails.
NO_PACKAGE_CASES = [
    pytest.param(
        _a_comment_written_after_the_approval,
        "required_reviewer_decisions",
        id="a comment written after the approval",
    ),
    pytest.param(
        _a_note_resolved_after_the_approval,
        "required_reviewer_decisions",
        id="a comment resolved after the approval",
    ),
    pytest.param(
        _a_note_reopened_after_the_approval,
        "required_reviewer_decisions",
        id="a comment reopened after the approval",
    ),
    pytest.param(
        _another_final_approver, "required_reviewer_decisions", id="another final approver"
    ),
    pytest.param(
        _a_scope_hold_when_the_matter_was_approved,
        "no_unresolved_blockers",
        id="a pilot scope hold at the approval",
    ),
    pytest.param(
        _an_unchecked_listed_document, "assessment_approved", id="an unchecked listed document"
    ),
]


def _why_no_package_can_be_prepared(api: PilotApi, matter: str) -> str:
    """`prepare_delivery` is refused for the matter owner. The gate's reason, as legal reads it."""

    allowed = {item["command"]: item for item in _view(api, OWNER, matter)["allowed"]}
    assert sorted(allowed) == ["prepare_delivery", "request_revision"]
    [evidence] = allowed["prepare_delivery"]["evidence"]
    assert (evidence["name"], evidence["ok"]) == ("export_gate_passes", False)
    status, answer = _post(api, OWNER, matter, "prepare_delivery")
    assert (status, answer["error"]) == (409, "transition_blocked")
    assert [e["name"] for e in answer["evidence"] if not e["ok"]] == ["export_gate_passes"]
    assert state(api.service, matter) == "approved"
    return str(evidence["detail"])


def _what_only_legal_reads(api: PilotApi, matter: str) -> list[str]:
    """The reviewers, the gate's checks and reasons, the holds and every comment's text."""

    owner = _view(api, OWNER, matter)
    reviewers = [
        actor
        for role, actors in owner["assignments"].items()
        if role != "business_requester"
        for actor in actors
    ]
    names = [a.display_name for a in api.service.list_actors() if a.actor_id in reviewers]
    checks = owner["eligibility"]["checks"]
    failing = [check["detail"] for check in checks if check["status"] != "pass"]
    assert reviewers and len(names) == len(reviewers) and len(checks) == 11 and failing
    return [
        *reviewers,
        *names,
        *(check["check_id"] for check in checks),
        *failing,
        "export_gate_passes",
        "prepare_delivery",
        *owner["version"]["scope_exclusions"],
        *(comment["body"] for comment in owner["comments"]),
    ]


@pytest.mark.parametrize(("case", "check"), NO_PACKAGE_CASES)
def test_the_requester_is_not_told_a_package_is_being_prepared_when_none_can_be(
    tmp_path, case, check: str
) -> None:
    api, matter, _ = case(tmp_path)
    service = api.service
    assert state(service, matter) == "approved"
    assert _why_no_package_can_be_prepared(api, matter).startswith(f"{check}: ")
    with service.store.reading() as connection:
        stored = list(connection.iterdump())

    # The view and the list, read over the API: "In review" in both, and the same in both.
    view = _view(api, REQUESTER, matter)
    assert view["matter"]["state"] == "approved"
    assert view["package"] == {"may_open": False, "reason": None} and view["delivery"] == []
    assert _told(api, matter) == TOLD_NO_PACKAGE
    assert view["requester_status"]["label"] == "In review"
    [entry] = [m for m in _list(api, REQUESTER) if m["matter_id"] == matter]
    assert (entry["state"], entry["requester_status_label"]) == ("approved", "In review")
    assert _listed_and_told(api, matter) == ("approved", "In review")

    # The sentence names no cause, and nothing else in the answers does: no reviewer, no
    # check, no hold reason and no comment text reaches the requester.
    told = (encode(view) + encode({"matters": _list(api, REQUESTER)})).decode("utf-8")
    for text in _what_only_legal_reads(api, matter):
        assert text and text not in told, text

    # Reading the status changed nothing: no row of any table, and so no state and no event.
    with service.store.reading() as connection:
        assert list(connection.iterdump()) == stored
    # A reviewer's view has no requester status, as before, and no key that it did not have.
    owner = _view(api, OWNER, matter)
    assert "requester_status" not in owner and sorted(owner) == REVIEWER_VIEW_KEYS


@pytest.mark.parametrize(("case", "check"), NO_PACKAGE_CASES)
def test_a_reviewers_view_and_list_do_not_go_through_the_requester_status(
    tmp_path, monkeypatch, case, check: str
) -> None:
    api, matter, approver = case(tmp_path)
    service = api.service
    assert _told(api, matter) == TOLD_NO_PACKAGE
    clock = service.clock
    assert isinstance(clock, _StepClock)

    def answers() -> dict[str, tuple[bytes, bytes]]:
        read = {}
        for actor in (OWNER, approver):
            # The same reading of the clock for each view, so that two can be compared.
            clock.reads = 100_000
            view = service.view_matter(actor, matter)
            status, listed, _ = api.handle("GET", "/pilot/api/matters", {"X-Pilot-Actor": actor})
            assert status == 200 and "requester_status" not in view
            read[actor] = (encode(view), encode(listed))
        return read

    before = answers()
    # The list of a reviewer is the six stored columns of each matter, byte for byte.
    with service.store.reading() as connection:
        row = connection.execute("SELECT * FROM matters WHERE matter_id = ?", (matter,)).fetchone()
    as_stored = encode({"matters": [{key: row[key] for key in LIST_KEYS}]})
    assert {listed for _, listed in before.values()} == {as_stored}

    def refuse(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("a reviewer's answer asked for the requester's status")

    # With the requester's status out of reach, every reviewer's answer is the same bytes:
    # nothing a reviewer reads is built from it, so nothing they read moved with it.
    monkeypatch.setattr(PilotService, "_requester_status", refuse)
    monkeypatch.setattr("src.pilot.service.requester_status", refuse)
    assert answers() == before
    # The requester's own view and list do ask for it.
    for read in (
        lambda: service.view_matter(REQUESTER, matter),
        lambda: service.list_matters(REQUESTER),
    ):
        with pytest.raises(AssertionError, match="asked for the requester's status"):
            read()


def test_the_status_reads_approved_again_when_a_package_can_be_prepared_again(tmp_path) -> None:
    # The status follows the evidence. A comment put back into the state it had at the
    # approval, or the earlier approver assigned again, lets `prepare_delivery` pass again.
    api, matter, approver = _a_note_resolved_after_the_approval(tmp_path / "resolved")
    assert _told(api, matter) == TOLD_NO_PACKAGE
    note = _comment_id(api, matter, EARLY_NOTE)
    _do(api, approver, matter, "reopen_comment", comment_id=note, reason="It stays open for now.")
    assert state(api.service, matter) == "approved"
    assert _told(api, matter) == TOLD_APPROVED
    assert _listed_and_told(api, matter) == ("approved", "Approved")
    _do(api, OWNER, matter, "prepare_delivery")
    assert _told(api, matter) == TOLD_READY
    assert _listed_and_told(api, matter) == ("ready_for_delivery", "Ready for you")

    api, matter, approver = _a_note_reopened_after_the_approval(tmp_path / "reopened")
    assert _told(api, matter) == TOLD_NO_PACKAGE
    note = _comment_id(api, matter, EARLY_NOTE)
    _do(api, approver, matter, "resolve_comment", comment_id=note, resolution="Read again.")
    assert _told(api, matter) == TOLD_APPROVED
    assert _listed_and_told(api, matter) == ("approved", "Approved")

    api, matter, _ = _another_final_approver(tmp_path / "approver")
    assert _told(api, matter) == TOLD_NO_PACKAGE
    # The new approver cannot approve from here: `approve` is not open from `approved`.
    status, answer = _post(api, APPROVER_GC, matter, "approve", note=APPROVAL)
    assert (status, answer["error"]) == (409, "transition_blocked")
    _do(api, OWNER, matter, "assign", role="final_approver", assignee_id=APPROVER_LEAD)
    assert _told(api, matter) == TOLD_APPROVED
    assert _listed_and_told(api, matter) == ("approved", "Approved")
    _do(api, OWNER, matter, "prepare_delivery")
    assert _told(api, matter) == TOLD_READY


def test_a_comment_written_after_the_approval_takes_a_new_review_and_approval(tmp_path) -> None:
    api, matter, approver = _a_comment_written_after_the_approval(tmp_path)
    late = _comment_id(api, matter, LATE_NOTE)

    # A new comment cannot be taken back: resolved, it still is not the state approved on.
    _do(api, OWNER, matter, "resolve_comment", comment_id=late, resolution="Read and noted.")
    assert _told(api, matter) == TOLD_NO_PACKAGE
    # Legal moves the matter without the requester. A revision request has to name an open
    # comment, so a reviewer reopens this one (or writes another) and asks for the revision.
    revision = {"comment_ids": [late], "note": "The late note has to be answered before delivery."}
    status, answer = _post(api, approver, matter, "request_revision", **revision)
    assert (status, answer["error"]) == (409, "transition_blocked")
    assert [e["name"] for e in answer["evidence"] if not e["ok"]] == ["revision_reason_recorded"]
    _do(api, OWNER, matter, "reopen_comment", comment_id=late, reason="It has to be answered.")
    assert _told(api, matter) == TOLD_NO_PACKAGE
    _do(api, approver, matter, "request_revision", **revision)
    # From here the state says "In review" by itself, with its ordinary explanation.
    assert state(api.service, matter) == "revision_requested"
    assert _told(api, matter) == TOLD_IN_REVIEW
    _do(api, OWNER, matter, "respond_comment", comment_id=late, body="Answered; no change.")
    _do(api, OWNER, matter, "submit_revision", note="The late note is answered.")
    _do(api, approver, matter, "resume_review")
    assert _told(api, matter) == TOLD_IN_REVIEW
    _do(api, approver, matter, "approve", note=APPROVAL)
    assert state(api.service, matter) == "approved"
    assert _told(api, matter) == TOLD_APPROVED
    assert _listed_and_told(api, matter) == ("approved", "Approved")
    _do(api, OWNER, matter, "prepare_delivery")
    assert _told(api, matter) == TOLD_READY


@pytest.mark.parametrize(
    ("case", "amendment"),
    [
        pytest.param(
            _a_scope_hold_when_the_matter_was_approved,
            {
                "reason": "The customer dropped the request for uncapped liability.",
                "routing_fields": {"uncapped_liability": False},
            },
            id="a pilot scope hold at the approval",
        ),
        pytest.param(
            _an_unchecked_listed_document,
            {
                "reason": "The order form is not part of this review.",
                "matter_fields": {"documents": []},
            },
            id="an unchecked listed document",
        ),
    ],
)
def test_an_approval_that_never_allowed_a_package_gets_one_only_after_an_amendment(
    tmp_path, case, amendment: dict[str, Any]
) -> None:
    # The known limit, pinned as it is. `approve` accepted the matter, the approval is the
    # one that counts, and nothing changed after it. Still no package can be prepared.
    api, matter, approver = case(tmp_path)
    assert _told(api, matter) == TOLD_NO_PACKAGE
    owner = _view(api, OWNER, matter)
    assert owner["matter"]["current_version"] == 2
    assert event_types(api.service, matter)[-1] == "approved"
    approvals = [d for d in owner["decisions"] if d["kind"] == "final_approval"]
    assert (approvals[-1]["version"], approvals[-1]["invalidated_at"]) == (2, None)
    assert owner["assessment"]["review_state"] == "approved"

    # A review and a new approval do not help: the hold, or the document, is still there.
    _do(api, approver, matter, "comment", body=LATE_NOTE, **SECTION)
    late = _comment_id(api, matter, LATE_NOTE)
    _do(
        api,
        approver,
        matter,
        "request_revision",
        comment_ids=[late],
        note="The matter has to be reviewed again before delivery.",
    )
    _do(api, OWNER, matter, "respond_comment", comment_id=late, body="Reviewed; no change.")
    _do(api, OWNER, matter, "submit_revision", note="Reviewed again; nothing changed.")
    _do(api, approver, matter, "resume_review")
    assert _told(api, matter) == TOLD_IN_REVIEW
    _do(api, approver, matter, "approve", note=APPROVAL)
    assert state(api.service, matter) == "approved"
    assert _told(api, matter) == TOLD_NO_PACKAGE
    assert _listed_and_told(api, matter) == ("approved", "In review")

    # The way out is an amendment that makes a version without the hold or the document.
    # The matter owner can make it, so nobody has to wait for the requester.
    _do(api, OWNER, matter, "amend_matter", **amendment)
    assert state(api.service, matter) == "revised"
    assert _view(api, OWNER, matter)["matter"]["current_version"] == 3
    assert _told(api, matter) == TOLD_IN_REVIEW
    _do(api, OWNER, matter, "resume_review")
    _do(api, approver, matter, "approve", note=APPROVAL)
    assert state(api.service, matter) == "approved"
    assert _told(api, matter) == TOLD_APPROVED
    assert _listed_and_told(api, matter) == ("approved", "Approved")
    _do(api, OWNER, matter, "prepare_delivery")
    assert _told(api, matter) == TOLD_READY
    assert _listed_and_told(api, matter) == ("ready_for_delivery", "Ready for you")


@pytest.mark.parametrize(
    ("case", "amendment"),
    [
        pytest.param(
            _a_scope_hold_when_the_matter_was_approved,
            {"routing_fields": {"uncapped_liability": False}},
            id="a pilot scope hold at the approval",
        ),
        pytest.param(
            _an_unchecked_listed_document,
            {"matter_fields": {"documents": []}},
            id="an unchecked listed document",
        ),
    ],
)
def test_the_requester_may_amend_or_withdraw_such_a_matter_as_well(
    tmp_path, case, amendment: dict[str, Any]
) -> None:
    # Nothing is needed from the requester, and nothing is closed to them either: as in
    # every open state they may amend the matter, and they or the matter owner may withdraw it.
    api, matter, _ = case(tmp_path / "amended")
    assert _told(api, matter) == TOLD_NO_PACKAGE
    _do(api, REQUESTER, matter, "amend_matter", reason="Changed by the requester.", **amendment)
    assert state(api.service, matter) == "revised"
    assert _told(api, matter) == TOLD_IN_REVIEW

    for actor in (OWNER, REQUESTER):
        api, matter, _ = case(tmp_path / f"withdrawn-by-{actor}")
        assert _listed_and_told(api, matter) == ("approved", "In review")
        _do(api, actor, matter, "withdraw", note=REASON)
        assert _listed_and_told(api, matter) == ("closed", "Closed: withdrawn without delivery")


def test_an_open_question_overrides_the_action_while_an_approval_gives_no_package(
    tmp_path,
) -> None:
    api, service = _a_room(tmp_path)
    matter = run_until(service, "specialist-revision", "B42")
    assert state(service, matter) == "approved"
    assert _told(api, matter) == TOLD_APPROVED
    [question] = _view(api, REQUESTER, matter)["clarifications"]
    assert question["state"] == "resolved"

    # The owner reopens the question that was put to the requester. An open question blocks
    # the gate and changes the reviewed state, and the requester has a question to answer.
    asked = ("in_review", "In review", NO_PACKAGE, "Answer the open question below.", True)
    for answered_again in (False, True):
        _do(
            api,
            OWNER,
            matter,
            "reopen_comment",
            comment_id=question["comment_id"],
            reason="The answer needs one more detail before delivery.",
        )
        reason = _why_no_package_can_be_prepared(api, matter)
        assert reason.startswith("no_unresolved_blockers: ")
        assert "required_reviewer_decisions" in reason
        assert _told(api, matter) == asked
        assert _listed_and_told(api, matter) == ("approved", "In review")
        if answered_again:
            # The requester answers; the question stays open until its author resolves it.
            _do(
                api,
                REQUESTER,
                matter,
                "respond_comment",
                comment_id=question["comment_id"],
                body="The detail is in section 3 of the order form.",
            )
            assert _told(api, matter) == asked
        # Its author resolves it again, the first time on the answer it already has, so
        # legal can move the matter without the requester. Resolved again, the comments are
        # in the state the approval was given on.
        _do(
            api,
            OWNER,
            matter,
            "resolve_comment",
            comment_id=question["comment_id"],
            resolution="Answer read; nothing changes in the package.",
            evidence_refs=["synthetic:order-form-section-3"],
        )
        assert _told(api, matter) == TOLD_APPROVED
        assert _listed_and_told(api, matter) == ("approved", "Approved")


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
        f'"{TOLD_APPROVED[1]}", if a package can be prepared from it (the row above), and '
        f'"{TOLD_READY[1]}" once the new package is prepared. A withdrawn matter stays closed. |'
    )
    # The row said "until then", as if the requester read "In review" up to the new package.
    assert 'shows its requester "In review" until then' not in runbook


def test_the_runbook_says_what_a_requester_is_shown_while_an_approval_gives_no_package() -> None:
    # The same for an approved matter whose `prepare_delivery` would be refused: the
    # sentences are built from the label, the explanation and the next step that the tests
    # above compare with the API's answers.
    runbook = (DOCS / "pilot" / "RUNBOOK.md").read_text(encoding="utf-8")
    paragraphs = runbook.split("\n\n")
    [section_7] = [
        paragraph
        for paragraph in paragraphs
        if paragraph.startswith("The requester's status also goes by whether a package can be")
    ]
    # It follows the paragraph on a delivery that has ended, in section 7.
    before = paragraphs[paragraphs.index(section_7) - 1]
    assert before.startswith("A stored manifest alone does not open a package either.")
    stage, label, explanation, action, _ = TOLD_NO_PACKAGE
    assert (stage, label, TOLD_APPROVED[1]) == ("in_review", "In review", "Approved")
    for sentence in (
        # The four ways.
        "A matter can be `approved` while `prepare_delivery` would be refused: a comment was "
        "written, resolved or reopened after the approval (any change to the state of a "
        "comment), another final approver was assigned in place of the one who approved, a "
        "pilot scope hold applied when the matter was approved, or a listed matter document is "
        "unchecked.",
        # The stage, the explanation and the next step.
        f'Such a matter is shown to its requester as "{label}", not as "{TOLD_APPROVED[1]}", '
        "in the status and in their matter list.",
        f'The explanation reads "{explanation}", and the next step is "{action}" unless a '
        "question to the requester is open.",
        "The explanation names no cause, and no reviewer, check, hold reason or comment text "
        "is shown to the requester.",
        # The way back, and what stays as it was.
        "The service asks the evidence `prepare_delivery` itself needs (`export_gate_passes`), "
        f'so the status reads "{TOLD_APPROVED[1]}" again as soon as a package can be prepared '
        "again.",
        "The state itself does not change, and a reviewer's view and matter list are "
        "unchanged: their list shows the pilot state, `approved`.",
        "The row for a refused `prepare_delivery` in section 9 says how the matter gets out in "
        "each case.",
    ):
        assert sentence in section_7, sentence

    # The troubleshooting row: one row, in full. It records the known limit as well.
    [row] = [line for line in runbook.splitlines() if line.startswith("| `prepare_delivery` ")]
    assert row == (
        '| `prepare_delivery` refused | Open "Export eligibility" in the review room; each '
        "failing check names its cause. While the matter stays `approved`, its requester reads "
        f'"{label}" and, unless a question to them is open, "{action}", in the status and in '
        "their matter list, and is not told that a package is being prepared (section 7). If a "
        "comment was resolved or reopened after the approval, put it back into the state it had "
        "at the approval (reopen it, or resolve it again). If another final approver was "
        "assigned, the matter owner assigns the earlier approver again. The requester then "
        f'reads "{TOLD_APPROVED[1]}" again. A comment written after the approval cannot be '
        "taken back, and a new approver cannot approve from `approved`: a reviewer runs "
        "`request_revision` on an open comment, the matter owner answers it and runs "
        "`submit_revision`, and after `resume_review` and a new final approval "
        "`prepare_delivery` passes. Known limit: `approve` does not refuse a matter under a "
        "pilot scope hold (`no_unresolved_blockers` names the hold) or with an unchecked listed "
        "matter document (`assessment_approved` fails although the matter is approved), and a "
        "review and a new approval do not help. Such a matter gets a package only after "
        "`amend_matter` makes a version without the excluded input or the listed document, "
        "which the matter owner or the requester may run, followed by `resume_review`, a new "
        "final approval and `prepare_delivery`. The only other way out is to withdraw it. |"
    )


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

    # The second answer the status goes by: whether a package can be prepared.
    stage, label, explanation, action, _ = TOLD_NO_PACKAGE
    for sentence in (
        "`requester_status` also goes by whether a package can be prepared.",
        "A matter that is `approved` while `prepare_delivery` would be refused has the stage "
        f'`{stage}` and the label "{label}", not `{TOLD_APPROVED[0]}` and "{TOLD_APPROVED[1]}".',
        f'Its explanation is "{explanation}" and, unless a question to the requester is open, '
        f'its next step is "{action}".',
        "The service asks the evidence that transition needs (`export_gate_passes`) once, for "
        "the requester's view and for their matter list.",
        "The explanation names no cause, and the requester's view carries none of the gate's "
        "checks or reasons.",
        "A reviewer's view is unchanged: it lists `prepare_delivery` under `allowed` with that "
        "evidence, and the gate's checks under `eligibility`.",
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


def test_the_records_say_what_a_version_that_cannot_be_read_does() -> None:
    # The words the service answers with, as the behaviour test above compares them.
    named = '"version N of matter X cannot be read from the store"'
    # The two sentences of the page, as its script writes them. The browser test reads them
    # on the page (tests/test_review_room_browser.py).
    not_loaded = '"The matter list could not be loaded."'
    nothing_visible = '"No matter is visible to this role."'
    for sentence in (not_loaded, nothing_visible):
        assert REVIEW_ROOM_HTML.count(sentence) == 1, sentence
    runbook = (DOCS / "pilot" / "RUNBOOK.md").read_text(encoding="utf-8")
    [row] = [line for line in runbook.splitlines() if f"answers {named} |" in line]
    assert row == (
        f"| A matter view or a requester's matter list answers {named} | The store holds a "
        "current version of that matter which the application cannot read, so the matter's own "
        "view stops with this error for every reader and the whole matter list of its requester "
        "stops with the same error, because no status is made up for the matter and it is not "
        "left out of the list, while the requester's other matters still answer on their own "
        "route and a reviewer's list, which reads no version, is not affected; preserve the "
        "store file and inform the pilot lead, as for a chain that fails verification. In the "
        f"review room that requester reads {not_loaded} and this error where the list was. "
        "While the fault lasts the room shows them no entry, so they can open none of their "
        "matters from the page, the readable ones included. |"
    )
    # It stands in the troubleshooting table, below the row on the event chain.
    rows = runbook.split("## 9. Recovery and troubleshooting", 1)[1].splitlines()
    assert rows[rows.index(row) - 1].startswith(
        "| Event chain fails verification | Stop condition."
    )

    guide = " ".join((DOCS / "API.md").read_text(encoding="utf-8").split())
    room = guide.split("## Pilot review-room API ", 1)[1].split(" ## ", 1)[0]
    for sentence in (
        "The label is built from each matter's current version.",
        "If the store holds one that cannot be read, a requester's list answers as that "
        f"matter's own view does, with 422 `invalid_command` and {named}, and gives no entries: "
        "no label is made up for the matter and the matter is not left out.",
        f"The review room then shows {not_loaded} and that message where the list was.",
        f"It says {nothing_visible} only for a list that loaded and is empty.",
        "| 422 | `invalid_command` | Unknown command or invalid arguments, or a stored matter "
        "version, comment, proposed change or actor record that cannot be read (the message "
        "names the matter, or the actor whose own record it is, and repeats nothing of the "
        "stored text) |",
    ):
        assert sentence in room, sentence


def test_the_records_say_what_another_row_that_cannot_be_read_does() -> None:
    # What the service calls each row, as the behaviour tests above compare it.
    comment, change, decided = (
        '"' + STORED_ROWS[kind][2].format(version="N", matter="X") + '"'
        for kind in (A_COMMENT, A_CHANGE, AN_APPROVER)
    )
    assert (comment, change, decided) == (
        '"a comment on matter X"',
        '"a proposed change of version N of matter X"',
        '"the record of an actor who decided on matter X"',
    )
    cannot = '"cannot be read from the store"'
    own = '"the record of actor A cannot be read from the store"'
    runbook = (DOCS / "pilot" / "RUNBOOK.md").read_text(encoding="utf-8")
    rows = runbook.split("## 9. Recovery and troubleshooting", 1)[1].splitlines()
    [row] = [line for line in rows if comment in line]
    assert row == (
        f"| A matter view or a requester's matter list answers {comment}, {change} or {decided}, "
        f"followed by {cannot} | The store holds such a row which the application cannot read, "
        "and the view and the list stop as they do for a version that cannot be read (the row "
        "above). For the requester a comment is read in every state, and a proposed change of "
        "the current version or the record of an actor who signed off or approved only while "
        "the matter is `approved` or `ready_for_delivery`, where the requester's status asks "
        "the export gate. The error names the matter and the kind of row, names no reviewer "
        f"and repeats nothing of the stored text. {own} names the record of the actor who made "
        "the request, or in a reviewer's view that of an actor assigned to the matter. Preserve "
        "the store file and inform the pilot lead. |"
    )
    # "The row above" is the one on a version that cannot be read.
    assert rows[rows.index(row) - 1].startswith(
        "| A matter view or a requester's matter list answers "
        '"version N of matter X cannot be read from the store" |'
    )

    guide = " ".join((DOCS / "API.md").read_text(encoding="utf-8").split())
    room = guide.split("## Pilot review-room API ", 1)[1].split(" ## ", 1)[0]
    for sentence in (
        "The status also reads the matter's comments, in every state, and it asks the export "
        "gate while the matter is `approved` or `ready_for_delivery`.",
        "The gate reads the proposed changes of the current version and the records of the "
        "actors who signed off or approved.",
        "If one of these rows cannot be read, the requester's view and list answer in the same "
        f"way, with {comment}, {change} or {decided}, followed by {cannot}.",
        "The message names the matter and the kind of row, says how many problems the stored "
        "text has and in which field the first one is, and repeats nothing of that text; the "
        "third names no actor.",
        f"A request whose own actor record cannot be read answers {own}.",
    ):
        assert sentence in room, sentence

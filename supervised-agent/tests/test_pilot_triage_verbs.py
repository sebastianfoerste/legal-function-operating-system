"""Triage verbs: decline, mark a duplicate and snooze (ADR 0010). Everything is synthetic."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from src.mcp_tools import legal_ops_mcp_manifest
from src.pilot.api import PilotApi
from src.pilot.ledger import matter_ledger
from src.pilot.metrics import build_pilot_metrics, control_contract, to_parent_ledger
from src.pilot.models import Actor, PilotIntake
from src.pilot.parent_bridge import CONTRACT_REVIEW_STATE, parent_module, parent_request
from src.pilot.review_room import REVIEW_ROOM_HTML
from src.pilot.service import (
    InvalidCommandError,
    PermissionDeniedError,
    PilotService,
    Stamp,
    TransitionBlockedError,
)
from src.pilot.snooze import ENDING_EVENTS, SNOOZE_MAX_DAYS, latest_snooze, snooze_windows
from src.pilot.state_machine import TERMINAL_STATES, TRIAGE_CLAIM_COMMANDS
from tests.pilot_support import (
    APPROVER_LEAD,
    OTHER_OWNER,
    OWNER,
    REQUESTER,
    SPECIALIST,
    event_types,
    make_service,
    revision,
    run_until,
    scenario,
    state,
)

REASON = "Outside the pilot charter: the customer asks for uncapped liability."
PAUSE = "Waiting for the signed order form from the sales team."
QUESTION = "Which order form does this draft belong to?"
OTHER_REQUESTER = "syn-requester-other"


class SettableClock:
    def __init__(self, now: str) -> None:
        self.value = now

    def now(self) -> str:
        return self.value


def _failing(error: TransitionBlockedError) -> set[str]:
    return {item["name"] for item in error.evidence if not item["ok"]}


def _detail(error: TransitionBlockedError, name: str) -> str:
    return next(item["detail"] for item in error.evidence if item["name"] == name)


def _open(api: PilotApi, actor: str, matter_id: str) -> None:
    """Open a routine matter from the room on the service clock and submit it."""

    status, made, _ = api.handle(
        "POST",
        "/pilot/api/matters",
        {"X-Pilot-Actor": actor},
        {"scenario_id": "routine", "matter_id": matter_id},
    )
    assert status == 201, made
    api.service.submit_intake(actor, matter_id, made["matter"]["revision"])


def _recorded(
    tmp_path: Path, at: str = "2026-11-02T08:00:00Z"
) -> tuple[PilotService, SettableClock]:
    """A routine matter, PM-OP-1, opened and submitted on the server's clock."""

    clock = SettableClock(at)
    service = make_service(tmp_path, clock=clock)
    _open(PilotApi(service), REQUESTER, "PM-OP-1")
    return service, clock


def _other_requester(service: PilotService) -> None:
    service.register_actor(
        Actor(
            actor_id=OTHER_REQUESTER,
            display_name="Synthetic Requester Z",
            role="business_requester",
            onboarded=True,
        )
    )


def _decisions(service: PilotService, matter_id: str) -> list[dict[str, Any]]:
    with service.store.reading() as connection:
        return [
            dict(row)
            for row in connection.execute(
                "SELECT * FROM decisions WHERE matter_id = ? ORDER BY decision_id", (matter_id,)
            )
        ]


# -- decline ----------------------------------------------------------------------------


def test_an_owner_declines_a_matter_that_cannot_leave_triage(tmp_path) -> None:
    service = make_service(tmp_path)
    matter_id = run_until(service, "blocked", "C03")  # triage refused; nobody has claimed it
    # Withdrawing is still for those on the matter; declining is the owner's way out.
    with pytest.raises(PermissionDeniedError, match="not assigned"):
        service.withdraw(OWNER, matter_id, revision(service, matter_id), note=REASON)
    start = revision(service, matter_id)
    with pytest.raises(TransitionBlockedError) as short:
        service.decline(OWNER, matter_id, start, reason="  Out of scope.  ")
    assert _failing(short.value) == {"closure_reason_recorded"}
    assert revision(service, matter_id) == start and state(service, matter_id) == "triage"
    assert event_types(service, matter_id)[-1] == "command_refused"

    view = service.decline(OWNER, matter_id, start, reason=REASON)
    assert (view["matter"]["state"], view["matter"]["closed_outcome"]) == (
        "declined",
        "declined_by_legal",
    )
    assert view["assignments"]["matter_owner"] == [OWNER]  # declining claimed the matter
    assert event_types(service, matter_id)[-1] == "matter_declined"
    assert view["audit_chain"]["verified"]
    [decision] = _decisions(service, matter_id)
    current = view["version"]
    assert (decision["kind"], decision["outcome"], decision["note"]) == (
        "decline",
        "declined",
        REASON,
    )
    assert (decision["version"], decision["content_hash"]) == (
        current["version"],
        current["content_hash"],
    )
    # The charter exclusions still hold it, but nothing is pending: the contract says rejected.
    history = service.history(OWNER, matter_id)["events"]
    assert view["version"]["scope_exclusions"]
    assert control_contract(view, history)["review_state"] == "rejected"
    timing = view["timing"]
    assert timing["resolution_sla"] == "not_applicable" and timing["response_sla"] != "unmeasured"

    for actor, command, args in (
        (REQUESTER, "withdraw", {"note": "Withdrawing after the decline happened."}),
        (REQUESTER, "amend_matter", {"reason": "Late change.", "facts": {"counterparty": "X"}}),
        (OWNER, "complete_triage", None),
        (OWNER, "snooze", {"reason": PAUSE, "question": QUESTION}),
    ):
        with pytest.raises(TransitionBlockedError, match=r"the matter is closed \(declined\)"):
            service.execute(actor, matter_id, command, revision(service, matter_id), args)

    status = service.view_matter(REQUESTER, matter_id)["requester_status"]
    assert (status["stage"], status["label"]) == ("closed", "Closed: declined by legal")
    assert status["explanation"] == "Legal declined this request. The reason is below."
    assert status["closure"] == {"reason": REASON, "original_matter_id": None}
    assert not status["waiting_on_you"] and status["snooze"] is None


def test_only_an_onboarded_matter_owner_may_use_a_triage_verb(tmp_path) -> None:
    service = make_service(tmp_path)  # the specialist has not onboarded
    matter_id = run_until(service, "routine", "A02")
    service.register_actor(
        Actor(actor_id="syn-owner-new", display_name="Synthetic Owner N", role="matter_owner")
    )
    for actor in (REQUESTER, APPROVER_LEAD, SPECIALIST, "syn-owner-new"):
        for command, args in (
            ("decline", {"reason": REASON}),
            ("mark_duplicate", {"original_matter_id": "PM-X", "reason": REASON}),
            ("snooze", {"reason": PAUSE, "question": QUESTION}),
        ):
            with pytest.raises(PermissionDeniedError):
                service.execute(actor, matter_id, command, revision(service, matter_id), args)
    assert (
        state(service, matter_id) == "triage"
        and "matter_owner" not in service.view_matter(OWNER, matter_id)["assignments"]
    )

    # A snooze claims the matter, as triage does: no other owner may then act on it or see it.
    service.snooze(
        OTHER_OWNER, matter_id, revision(service, matter_id), reason=PAUSE, question=QUESTION
    )
    with pytest.raises(PermissionDeniedError, match="cannot triage"):
        service.decline(OWNER, matter_id, revision(service, matter_id), reason=REASON)
    assert matter_id not in [m["matter_id"] for m in service.list_matters(OWNER)]
    assert TRIAGE_CLAIM_COMMANDS == {"complete_triage", "decline", "mark_duplicate", "snooze"}


def test_after_triage_the_verbs_are_refused_without_saying_the_state_to_outsiders(
    tmp_path,
) -> None:
    service = make_service(tmp_path)
    matter_id = run_until(service, "routine", "A06")  # in review
    with pytest.raises(PermissionDeniedError, match="not assigned"):
        service.decline(OTHER_OWNER, matter_id, revision(service, matter_id), reason=REASON)
    with pytest.raises(PermissionDeniedError, match="not assigned"):
        service.complete_triage(OTHER_OWNER, matter_id, revision(service, matter_id))
    with pytest.raises(TransitionBlockedError, match="not allowed from state review"):
        service.decline(OWNER, matter_id, revision(service, matter_id), reason=REASON)
    with pytest.raises(TransitionBlockedError, match="snooze is allowed in triage only"):
        service.snooze(
            OWNER, matter_id, revision(service, matter_id), reason=PAUSE, question=QUESTION
        )
    assert state(service, matter_id) == "review"


# -- duplicate --------------------------------------------------------------------------


def test_a_duplicate_names_an_original_the_owner_can_see(tmp_path) -> None:
    service = make_service(tmp_path)
    api = PilotApi(service)
    original = run_until(service, "routine", "A13")  # delivered; OWNER is on it
    blocked = run_until(service, "blocked", "C02")  # in triage, unclaimed
    _open(api, REQUESTER, "PM-HIDDEN")
    service.snooze(
        OTHER_OWNER, "PM-HIDDEN", revision(service, "PM-HIDDEN"), reason=PAUSE, question=QUESTION
    )

    def refused(original_id: str, reason: str = REASON) -> TransitionBlockedError:
        with pytest.raises(TransitionBlockedError) as error:
            service.mark_duplicate(
                OWNER,
                blocked,
                revision(service, blocked),
                original_matter_id=original_id,
                reason=reason,
            )
        return error.value

    unknown, hidden = refused("PM-NOPE"), refused("PM-HIDDEN")
    assert _failing(unknown) == _failing(hidden) == {"duplicate_original_visible"}
    # An unknown matter and one the owner may not see get the same answer.
    assert str(unknown).replace("PM-NOPE", "ID") == str(hidden).replace("PM-HIDDEN", "ID")
    assert _detail(unknown, "duplicate_original_visible") == "no matter PM-NOPE is visible to you"
    assert "itself" in _detail(refused(blocked), "duplicate_original_visible")
    assert _failing(refused(original, reason="Same request.")) == {"closure_reason_recorded"}
    assert state(service, blocked) == "triage"

    view = service.mark_duplicate(
        OWNER,
        blocked,
        revision(service, blocked),
        original_matter_id=f" {original} ",
        reason=REASON,
    )
    assert (view["matter"]["state"], view["matter"]["closed_outcome"]) == (
        "duplicate",
        "duplicate_of_another_matter",
    )
    [decision] = _decisions(service, blocked)
    assert (decision["kind"], decision["target_id"], decision["note"]) == (
        "duplicate",
        original,
        REASON,
    )
    history = service.history(OWNER, blocked)["events"]
    assert history[-1]["payload"]["original_matter_id"] == original
    assert control_contract(view, history)["review_state"] == "rejected"

    # A duplicate cannot be an original: name the matter it duplicates instead.
    _open(api, REQUESTER, "PM-OP-2")
    with pytest.raises(TransitionBlockedError) as chained:
        service.mark_duplicate(
            OWNER,
            "PM-OP-2",
            revision(service, "PM-OP-2"),
            original_matter_id=blocked,
            reason=REASON,
        )
    assert _detail(chained.value, "duplicate_original_visible") == (
        f"{blocked} is itself a duplicate; name the matter it duplicates"
    )


def test_the_requester_sees_the_original_only_when_they_asked_for_it_too(tmp_path) -> None:
    service = make_service(tmp_path)
    api = PilotApi(service)
    original = run_until(service, "routine", "A13")
    _other_requester(service)
    _open(api, REQUESTER, "PM-SAME-1")
    _open(api, OTHER_REQUESTER, "PM-SAME-2")
    for matter_id in ("PM-SAME-1", "PM-SAME-2"):
        service.mark_duplicate(
            OWNER,
            matter_id,
            revision(service, matter_id),
            original_matter_id=original,
            reason=REASON,
        )

    own = service.view_matter(REQUESTER, "PM-SAME-1")["requester_status"]
    assert own["label"] == "Closed: duplicate of another matter"
    assert own["closure"] == {"reason": REASON, "original_matter_id": original}
    other = service.view_matter(OTHER_REQUESTER, "PM-SAME-2")
    assert other["requester_status"]["closure"] == {"reason": REASON, "original_matter_id": None}
    assert original not in json.dumps(other)


# -- snooze -----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("args", "message"),
    [
        ({"reason": "Waiting.", "question": QUESTION}, "snooze reason must be at least 20"),
        ({"reason": PAUSE}, "exactly one of"),
        (
            {"reason": PAUSE, "until": "2026-11-03T09:00:00Z", "question": QUESTION},
            "exactly one of",
        ),
        ({"reason": PAUSE, "until": "  ", "question": " "}, "exactly one of"),
        ({"reason": PAUSE, "until": "2026-11-03T09:00:00"}, "with a time zone"),  # naive
        ({"reason": PAUSE, "until": "next Tuesday"}, "with a time zone"),
        ({"reason": PAUSE, "until": "2026-11-02T08:00:00Z"}, "later than now"),
        ({"reason": PAUSE, "until": "2026-11-02T09:00:00+02:00"}, "later than now"),
        ({"reason": PAUSE, "until": "2026-12-02T08:00:01Z"}, f"at most {SNOOZE_MAX_DAYS} days"),
        ({"reason": PAUSE, "question": "Why?"}, "question must be at least 10"),
    ],
)
def test_a_snooze_needs_a_reason_and_one_bound_within_thirty_days(tmp_path, args, message) -> None:
    service, _ = _recorded(tmp_path)
    start = revision(service, "PM-OP-1")
    with pytest.raises(InvalidCommandError, match=message):
        service.execute(OWNER, "PM-OP-1", "snooze", start, args)
    assert revision(service, "PM-OP-1") == start
    assert "matter_snoozed" not in event_types(service, "PM-OP-1")
    assert "matter_owner" not in service.view_matter(OWNER, "PM-OP-1")["assignments"]


def test_a_snooze_may_last_thirty_days_and_is_kept_in_utc(tmp_path) -> None:
    service, clock = _recorded(tmp_path)
    view = service.snooze(
        OWNER,
        "PM-OP-1",
        revision(service, "PM-OP-1"),
        reason=PAUSE,
        until="2026-12-02T09:00:00+01:00",
    )
    assert view["matter"]["state"] == "triage" and view["assignments"]["matter_owner"] == [OWNER]
    snooze = view["snooze"]
    assert (snooze["until"], snooze["since"], snooze["active"]) == (
        "2026-12-02T08:00:00Z",
        "2026-11-02T08:00:00Z",
        True,
    )
    assert view["snooze_limits"] == {
        "max_days": 30,
        "server_now": "2026-11-02T08:00:00Z",
        "latest_until": "2026-12-02T08:00:00Z",
    }
    with pytest.raises(InvalidCommandError, match="already snoozed"):
        service.snooze(
            OWNER, "PM-OP-1", revision(service, "PM-OP-1"), reason=PAUSE, question=QUESTION
        )
    with pytest.raises(InvalidCommandError, match="no snooze question"):
        service.answer_snooze(
            REQUESTER, "PM-OP-1", revision(service, "PM-OP-1"), answer="Order form OF-1."
        )
    clock.value = "2026-12-02T08:00:00Z"  # its time has come: nothing was written
    count = len(event_types(service, "PM-OP-1"))
    ended = service.view_matter(OWNER, "PM-OP-1")["snooze"]
    assert (ended["active"], ended["ended_by"], ended["ended_at"]) == (
        False,
        "time_passed",
        "2026-12-02T08:00:00Z",
    )
    assert len(event_types(service, "PM-OP-1")) == count
    with pytest.raises(InvalidCommandError, match="not snoozed"):
        service.end_snooze(OWNER, "PM-OP-1", revision(service, "PM-OP-1"))


def _snoozed(tmp_path: Path, name: str) -> tuple[PilotService, SettableClock]:
    service, clock = _recorded(tmp_path / name)
    clock.value = "2026-11-02T09:00:00Z"
    service.snooze(OWNER, "PM-OP-1", revision(service, "PM-OP-1"), reason=PAUSE, question=QUESTION)
    clock.value = "2026-11-02T10:00:00Z"
    return service, clock


@pytest.mark.parametrize(
    ("actor", "command", "args", "ended_by"),
    [
        (REQUESTER, "answer_snooze", {"answer": "Order form OF-2026-118."}, "snooze_answered"),
        (OWNER, "end_snooze", None, "snooze_ended"),
        (OWNER, "complete_triage", None, "triage_completed"),
        (OWNER, "decline", {"reason": REASON}, "matter_declined"),
        (
            REQUESTER,
            "withdraw",
            {"note": "The customer signed our paper instead."},
            "matter_withdrawn",
        ),
    ],
)
def test_each_way_a_person_ends_a_snooze(tmp_path, actor, command, args, ended_by) -> None:
    service, _ = _snoozed(tmp_path, command)
    service.execute(actor, "PM-OP-1", command, revision(service, "PM-OP-1"), args)
    snooze = service.view_matter(OWNER, "PM-OP-1")["snooze"]
    assert (snooze["active"], snooze["ended_by"], snooze["ended_at"]) == (
        False,
        ended_by,
        "2026-11-02T10:00:00Z",
    )
    assert ended_by in ENDING_EVENTS
    assert service.view_matter(REQUESTER, "PM-OP-1")["requester_status"]["snooze"] is None


def test_only_the_requester_answers_and_only_the_owning_owner_ends_a_snooze(tmp_path) -> None:
    service, _ = _snoozed(tmp_path, "who")
    start = revision(service, "PM-OP-1")
    with pytest.raises(PermissionDeniedError):
        service.answer_snooze(OWNER, "PM-OP-1", start, answer="Answering for the requester.")
    with pytest.raises(PermissionDeniedError):
        service.end_snooze(REQUESTER, "PM-OP-1", start)
    with pytest.raises(PermissionDeniedError, match="not assigned"):
        service.end_snooze(OTHER_OWNER, "PM-OP-1", start)
    with pytest.raises(InvalidCommandError, match="answer must be at least 10"):
        service.answer_snooze(REQUESTER, "PM-OP-1", start, answer="OF-1")
    assert revision(service, "PM-OP-1") == start
    assert service.view_matter(OWNER, "PM-OP-1")["snooze"]["active"]


def test_the_requester_sees_the_pause_and_answers_its_question(tmp_path) -> None:
    service, _ = _snoozed(tmp_path, "requester")
    view = service.view_matter(REQUESTER, "PM-OP-1")
    status = view["requester_status"]
    assert (status["stage"], status["label"]) == ("received", "Received by legal")
    assert status["explanation"].startswith("Legal paused this request until you answer")
    assert status["your_action"] == "Answer legal's question below." and status["waiting_on_you"]
    assert status["snooze"] == {
        "since": "2026-11-02T09:00:00Z",
        "until": None,
        "question": QUESTION,
        "reason": PAUSE,
    }
    assert OWNER not in json.dumps(view["requester_status"])  # who snoozed is internal

    service.answer_snooze(
        REQUESTER, "PM-OP-1", revision(service, "PM-OP-1"), answer="Order form OF-1, signed."
    )
    status = service.view_matter(REQUESTER, "PM-OP-1")["requester_status"]
    assert status["snooze"] is None and not status["waiting_on_you"]
    assert status["explanation"] == "Legal has the request and is assigning a reviewer."
    room = service.view_matter(OWNER, "PM-OP-1")["snooze"]
    assert room["answer"] == "Order form OF-1, signed."


def test_a_timed_snooze_tells_the_requester_until_when(tmp_path) -> None:
    service, clock = _recorded(tmp_path)
    service.snooze(
        OWNER, "PM-OP-1", revision(service, "PM-OP-1"), reason=PAUSE, until="2026-11-04T08:00:00Z"
    )
    status = service.view_matter(REQUESTER, "PM-OP-1")["requester_status"]
    assert status["explanation"] == (
        "Legal paused this request until 2026-11-04T08:00:00Z. The reason is below."
    )
    assert status["your_action"] == "No action needed from you." and not status["waiting_on_you"]
    clock.value = "2026-11-04T08:00:00Z"
    assert service.view_matter(REQUESTER, "PM-OP-1")["requester_status"]["snooze"] is None


# -- clocks -----------------------------------------------------------------------------


def _event(
    event_type: str, at: str, role: str = "matter_owner", note: str = "", **payload: Any
) -> dict[str, Any]:
    return {
        "event_type": event_type,
        "fixture_at": at,
        "role": role,
        "actor_id": "syn-x",
        "note": note,
        "effort_minutes": None,
        "payload": payload,
    }


def _mapped(events: list[dict[str, Any]], as_of: str | None = None) -> list[tuple[str, str]]:
    return [
        (e["event_type"], e["occurred_at_utc"]) for e in matter_ledger("M", events, as_of=as_of)
    ]


def _tower(events: list[dict[str, Any]], as_of: str) -> dict[str, Any]:
    """The parent reads the mapped ledger: it refuses any order its lifecycle forbids."""

    tower = parent_module("outcome_control_tower")
    config = json.loads(
        parent_module("bundled").bundled_path("outcome_config.json").read_text("utf-8")
    )
    intake = PilotIntake.model_validate(scenario("routine")["intake"])
    entries = matter_ledger("M", events, as_of=as_of)
    ledger = {"schema": tower.LEDGER_SCHEMA, "as_of_utc": as_of, "events": entries}
    [row] = tower.build_outcome_control_tower([parent_request("M", intake)], ledger, config)[
        "requests"
    ]
    return row


SUBMITTED = [
    _event("matter_created", "2026-11-02T08:00:00Z", role="business_requester"),
    _event("intake_submitted", "2026-11-02T08:30:00Z", role="business_requester"),
]


def test_a_snooze_is_legal_s_first_response_and_a_wait_on_the_business() -> None:
    events = [
        *SUBMITTED,
        _event("matter_snoozed", "2026-11-02T09:00:00Z", note=PAUSE, question=QUESTION),
        _event("snooze_answered", "2026-11-03T09:00:00Z", role="business_requester"),
        _event("matter_snoozed", "2026-11-03T10:00:00Z", note=PAUSE, until="2026-11-04T09:00:00Z"),
        _event("triage_completed", "2026-11-05T09:00:00Z"),
        _event("review_started", "2026-11-05T10:00:00Z"),
    ]
    assert _mapped(events, "2026-11-05T10:00:00Z") == [
        ("submitted", "2026-11-02T08:30:00Z"),
        ("acknowledged", "2026-11-02T09:00:00Z"),
        ("assigned", "2026-11-02T09:00:00Z"),
        ("work_started", "2026-11-02T09:00:00Z"),
        ("waiting_on_business", "2026-11-02T09:00:00Z"),
        ("resumed", "2026-11-03T09:00:00Z"),
        ("waiting_on_business", "2026-11-03T10:00:00Z"),
        ("resumed", "2026-11-04T09:00:00Z"),  # its time ran out; no event records that
    ]
    row = _tower(events, "2026-11-05T10:00:00Z")
    assert row["state"] == "resumed" and row["response_sla"] in {"met", "breached"}
    assert row["business_wait_hours"] > 0


def test_a_timed_snooze_never_ends_after_the_ledger_is_read() -> None:
    events = [
        *SUBMITTED,
        _event("matter_snoozed", "2026-11-02T09:00:00Z", note=PAUSE, until="2026-11-04T09:00:00Z"),
    ]
    assert _mapped(events, "2026-11-04T08:59:59Z")[-1] == (
        "waiting_on_business",
        "2026-11-02T09:00:00Z",
    )
    assert _mapped(events, "2026-11-04T09:00:00Z")[-1] == ("resumed", "2026-11-04T09:00:00Z")
    assert _mapped(events)[-1][0] == "waiting_on_business"  # no later event: time unknown
    assert _tower(events, "2026-11-04T08:00:00Z")["state"] == "waiting_on_business"
    assert _tower(events, "2026-11-06T08:00:00Z")["state"] == "resumed"


def test_closing_in_triage_is_a_response_and_ends_a_wait() -> None:
    declined = [*SUBMITTED, _event("matter_declined", "2026-11-02T09:00:00Z")]
    assert _mapped(declined, "2026-11-02T09:00:00Z")[1:] == [
        ("acknowledged", "2026-11-02T09:00:00Z")
    ]
    snoozed = [
        *SUBMITTED,
        _event("matter_snoozed", "2026-11-02T09:00:00Z", note=PAUSE, question=QUESTION),
        _event("matter_marked_duplicate", "2026-11-02T11:00:00Z", original_matter_id="M-0"),
    ]
    assert _mapped(snoozed, "2026-11-02T11:00:00Z")[-1] == ("resumed", "2026-11-02T11:00:00Z")
    assert _tower(snoozed, "2026-11-02T11:00:00Z")["state"] == "resumed"


def test_every_reader_takes_the_snooze_from_one_function() -> None:
    events = [
        *SUBMITTED,
        _event("matter_snoozed", "2026-11-02T09:00:00Z", note=PAUSE, until="2026-11-02T12:00:00Z"),
        _event("snooze_ended", "2026-11-02T13:00:00Z"),  # too late: its time had passed
    ]
    [window] = snooze_windows(events, "fixture_at", "2026-11-02T13:00:00Z")
    assert (window["ended_by"], window["ended_at"]) == ("time_passed", "2026-11-02T12:00:00Z")
    running = latest_snooze(events[:3], "fixture_at", "2026-11-02T11:00:00Z")
    assert running is not None and running["active"]
    assert latest_snooze(SUBMITTED, "fixture_at", None) is None


def test_metrics_and_timing_charge_a_snooze_to_the_requester(tmp_path) -> None:
    service = make_service(tmp_path)
    matter_id = run_until(service, "routine", "A03")  # submitted 08:05, then a refused step
    service.snooze(
        OWNER, matter_id, revision(service, matter_id), reason=PAUSE, question=QUESTION,
        stamp=Stamp(fixture_at="2026-09-07T09:00:00Z", effort_minutes=5),
    )  # fmt: skip
    # The owner ends it a day later: without the snooze, that day is charged to the owner.
    service.end_snooze(
        OWNER,
        matter_id,
        revision(service, matter_id),
        stamp=Stamp(fixture_at="2026-09-08T09:00:00Z"),
    )
    service.complete_triage(
        OWNER,
        matter_id,
        revision(service, matter_id),
        stamp=Stamp(fixture_at="2026-09-08T10:00:00Z"),
    )
    [row] = build_pilot_metrics(service.store)["scripted_human_time"]
    waiting = row["waiting_minutes_by_cause"]
    assert waiting["requester_or_missing_facts"] == 5 + 1440
    assert waiting["matter_owner_availability"] == 55 + 60
    assert sum(waiting.values()) == 5 + 55 + 1440 + 60

    _, ledger = to_parent_ledger(service.store)
    assert [e["event_type"] for e in ledger["events"]] == [
        "submitted",
        "acknowledged",
        "assigned",
        "work_started",
        "waiting_on_business",
        "resumed",
    ]
    timing = service.view_matter(OWNER, matter_id)["timing"]
    assert timing["available"] and timing["clock"] == "scripted"
    assert timing["business_wait_hours"] > 0 and timing["response_sla"] != "unmeasured"


# -- contract, interface and boundaries ---------------------------------------------------


def test_the_new_states_are_final_and_map_to_rejected() -> None:
    assert TERMINAL_STATES == {"closed", "declined", "duplicate"}
    assert CONTRACT_REVIEW_STATE["declined"] == CONTRACT_REVIEW_STATE["duplicate"] == "rejected"


def test_the_triage_verbs_go_through_the_command_route_and_no_mcp_tool(tmp_path) -> None:
    clock = SettableClock("2026-11-02T08:00:00Z")
    api = PilotApi(make_service(tmp_path, clock=clock))
    _open(api, REQUESTER, "PM-OP-1")
    headers = {"X-Pilot-Actor": OWNER}

    def post(command: str, args: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        view = api.handle("GET", "/pilot/api/matters/PM-OP-1", headers, None)[1]
        body = {"command": command, "expected_revision": view["matter"]["revision"], "args": args}
        status, payload, _ = api.handle(
            "POST", "/pilot/api/matters/PM-OP-1/commands", headers, body
        )
        return status, payload

    status, payload = post("snooze", {"reason": PAUSE, "until": "2026-11-09T08:00:00"})
    assert (status, payload["error"]) == (422, "invalid_command")
    status, payload = post("mark_duplicate", {"original_matter_id": "PM-NOPE", "reason": REASON})
    assert status == 409 and payload["evidence"][0]["name"] == "duplicate_original_visible"
    status, payload = post("decline", {"reason": REASON})
    assert status == 200 and payload["matter"]["state"] == "declined"
    # No MCP tool reaches a pilot command.
    names = " ".join(tool["name"] for tool in legal_ops_mcp_manifest()["tools"])
    assert not any(word in names for word in ("decline", "duplicate", "snooze", "triage"))


def test_the_room_asks_for_a_typed_reason_and_suggests_none() -> None:
    assert REVIEW_ROOM_HTML.count("The requester sees this reason.") == 2
    for command in ("decline", "mark_duplicate", "snooze", "answer_snooze", "end_snooze"):
        assert f'command("{command}"' in REVIEW_ROOM_HTML, command
    assert "innerHTML" not in REVIEW_ROOM_HTML
    # The bounds come from the server's clock; the page reads no clock for a snooze.
    assert "limits.server_now" in REVIEW_ROOM_HTML and REVIEW_ROOM_HTML.count("Date.now") == 1

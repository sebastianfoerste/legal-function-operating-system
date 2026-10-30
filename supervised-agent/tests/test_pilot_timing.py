"""Time on a matter in the review room, measured by the parent's outcome control tower."""

from typing import cast

import pytest

import src.pilot.timing as timing_module
from src.pilot.api import PilotApi
from src.pilot.ledger import matter_ledger
from src.pilot.metrics import build_parent_outcome_view
from src.pilot.models import PilotIntake
from src.pilot.scenario_runner import load_scenario, scenario_paths, seed_actors
from src.pilot.service import PermissionDeniedError, PilotService, Stamp
from src.pilot.store import PilotStore
from tests.pilot_support import OWNER, REQUESTER, make_service, revision, run_until


class SettableClock:
    """The service's clock, set by the test: the only clock timing reads."""

    def __init__(self, now: str) -> None:
        self.value = now

    def now(self) -> str:
        return self.value


def _service(tmp_path, clock):
    service = PilotService(
        PilotStore(tmp_path / "pilot.sqlite3"), export_root=tmp_path / "exports", clock=clock
    )
    seed_actors(service)
    return service


def _timing(service, matter_id):
    return service.view_matter(OWNER, matter_id)["timing"]


def _command(api, actor, matter_id, command, args=None):
    headers = {"X-Pilot-Actor": actor}
    view = api.handle("GET", f"/pilot/api/matters/{matter_id}", headers, None)[1]
    body = {"command": command, "expected_revision": view["matter"]["revision"], "args": args or {}}
    status, payload, _ = api.handle(
        "POST", f"/pilot/api/matters/{matter_id}/commands", headers, body
    )
    assert status == 200, payload


def _open_in_room(tmp_path, created, submitted):
    """A routine matter opened from the room on the service clock, submitted later."""

    clock = SettableClock(created)
    service = _service(tmp_path, clock)
    api = PilotApi(service)
    status, made, _ = api.handle(
        "POST",
        "/pilot/api/matters",
        {"X-Pilot-Actor": REQUESTER},
        {"scenario_id": "routine", "matter_id": "PM-OP-1"},
    )
    assert status == 201, made
    clock.value = submitted
    _command(api, REQUESTER, "PM-OP-1", "submit_intake")
    return service, api, clock


# -- the mapping ------------------------------------------------------------------------


def _event(event_type, at, role="matter_owner", **payload):
    return {
        "event_type": event_type,
        "fixture_at": at,
        "role": role,
        "effort_minutes": None,
        "payload": payload,
    }


def _mapped(events):
    return [(e["event_type"], e["occurred_at_utc"]) for e in matter_ledger("M", events)]


def test_the_ledger_starts_at_submission_and_waits_while_any_question_is_open() -> None:
    events = [
        _event("matter_created", "T00", role="business_requester"),
        _event("intake_submitted", "T01", role="business_requester"),
        _event("triage_completed", "T02"),
        _event("review_started", "T03"),
        _event("change_decided", "T04", comment_id="c-1", outcome="clarification_requested"),
        _event("change_decided", "T05", comment_id="c-2", outcome="clarification_requested"),
        _event("comment_response_added", "T06", role="business_requester", comment_id="c-1"),
        _event("comment_response_added", "T07", role="business_requester", comment_id="c-1"),
        _event("comment_response_added", "T08", role="business_requester", comment_id="c-2"),
        _event("comment_reopened", "T09", comment_id="c-1"),
        _event("comment_resolved", "T10", comment_id="c-1"),
        _event("comment_reopened", "T11", comment_id="c-9"),  # not a question to the requester
    ]
    assert _mapped(events) == [
        ("submitted", "T01"),
        ("acknowledged", "T02"),
        ("assigned", "T03"),
        ("work_started", "T03"),
        ("waiting_on_business", "T04"),
        ("resumed", "T08"),  # only once the second question is answered too
        ("waiting_on_business", "T09"),
        ("resumed", "T10"),
    ]


def test_a_draft_not_yet_submitted_has_no_ledger_and_says_so() -> None:
    draft = [_event("matter_created", "2026-11-02T08:00:00Z", role="business_requester")]
    assert _mapped(draft) == []
    routine = next(s for s in map(load_scenario, scenario_paths()) if s["scenario_id"] == "routine")
    intake = PilotIntake.model_validate(routine["intake"])
    timing = timing_module.matter_timing(
        "M", intake, draft, closed=False, withdrawn=False, now="2026-11-02T09:00:00Z"
    )
    assert timing == {
        "clock": "scripted",
        "available": False,
        "reason": "it has not been submitted to legal yet",
    }


# -- rehearsal matters (scripted clock) -------------------------------------------------


def test_closed_rehearsal_matters_match_the_rehearsal_report(tmp_path) -> None:
    service = make_service(tmp_path)
    for path in scenario_paths():
        script = load_scenario(path)
        run_until(service, script["scenario_id"], script["steps"][-1]["id"])
    rows = {row["request_id"]: row for row in build_parent_outcome_view(service.store)["requests"]}
    for matter_id in ("PM-ROUTINE-001", "PM-SPECIALIST-002"):
        timing, row = _timing(service, matter_id), rows[matter_id]
        assert (timing["clock"], timing["available"], timing["open"]) == ("scripted", True, False)
        assert timing["measured_to"] == row["last_event_at_utc"].replace("+00:00", "Z")
        assert (
            timing["business_hours"],
            timing["legal_controlled_hours"],
            timing["business_wait_hours"],
            timing["first_response_business_hours"],
            timing["response_sla"],
            timing["resolution_sla"],
        ) == (
            row["gross_cycle_business_hours"],
            row["legal_controlled_hours"],
            row["business_wait_hours"],
            row["first_response_business_hours"],
            row["response_sla"],
            row["resolution_sla"],
        )
    specialist = _timing(service, "PM-SPECIALIST-002")
    assert (specialist["elapsed_hours"], specialist["business_hours"]) == (48.08, 18.08)
    assert (specialist["legal_controlled_hours"], specialist["business_wait_hours"]) == (
        12.08,
        6.0,
    )
    assert (
        specialist["response_target_business_hours"],
        specialist["resolution_target_business_hours"],
    ) == (8.0, 27.0)


def test_an_open_rehearsal_matter_is_measured_to_its_latest_scripted_step(tmp_path) -> None:
    service = make_service(tmp_path)
    matter_id = run_until(service, "blocked", "C10")  # still in triage; ends with refusals
    timing = _timing(service, matter_id)
    assert (timing["clock"], timing["open"]) == ("scripted", True)
    assert timing["as_of"] == timing["measured_to"] == "2026-09-09T09:05:00Z"
    assert timing["first_response_business_hours"] is None
    # Exactly at the 8-hour target: not past it yet.
    assert (timing["business_hours"], timing["response_target_business_hours"]) == (8.0, 8.0)
    assert timing["response_sla"] == "unmeasured" and timing["resolution_sla"] == "open"


def test_an_unscripted_refusal_neither_picks_the_clock_nor_ends_a_closed_matter(tmp_path) -> None:
    service = make_service(tmp_path)
    matter_id = run_until(service, "routine", "A13")  # delivered and closed
    with pytest.raises(PermissionDeniedError):  # refused, recorded with no scripted time
        service.withdraw("syn-unknown", matter_id, revision(service, matter_id), note="Refused.")
    timing = _timing(service, matter_id)
    assert (timing["clock"], timing["available"], timing["open"]) == ("scripted", True, False)
    assert timing["measured_to"] == "2026-09-07T15:30:00Z"


def test_a_withdrawn_matter_stops_at_its_withdrawal(tmp_path) -> None:
    service = make_service(tmp_path)
    matter_id = run_until(service, "specialist-revision", "B13")
    service.withdraw(
        OWNER, matter_id, revision(service, matter_id),
        note="Customer paused the deal; closing without delivery.",
        stamp=Stamp(fixture_at="2026-09-08T16:00:00Z"),
    )  # fmt: skip
    timing = _timing(service, matter_id)
    assert (timing["open"], timing["measured_to"]) == (False, "2026-09-08T16:00:00Z")
    assert timing["resolution_sla"] == "not_applicable"


# -- matters run in the room (recorded clock) -------------------------------------------


def test_a_matter_opened_in_the_room_runs_on_the_service_clock(tmp_path) -> None:
    # Opened as a draft on Monday; submitted to legal on Wednesday 09:00 in Berlin.
    service, _, clock = _open_in_room(tmp_path, "2026-11-02T08:00:00Z", "2026-11-04T08:00:00Z")
    clock.value = "2026-11-04T10:00:00Z"
    timing = _timing(service, "PM-OP-1")
    assert (timing["clock"], timing["as_of"], timing["open"]) == (
        "recorded",
        "2026-11-04T10:00:00Z",
        True,
    )
    # Legal's time starts at submission, not when the draft was opened two days earlier.
    assert (timing["elapsed_hours"], timing["business_hours"]) == (2.0, 2.0)
    clock.value = "2026-11-05T08:00:00Z"
    timing = _timing(service, "PM-OP-1")
    assert (timing["elapsed_hours"], timing["business_hours"]) == (24.0, 9.0)
    assert "timing" not in service.view_matter(REQUESTER, "PM-OP-1")


def test_an_open_matter_past_its_targets_is_overdue(tmp_path) -> None:
    service, _, clock = _open_in_room(tmp_path, "2026-11-02T08:00:00Z", "2026-11-02T08:00:00Z")
    clock.value = "2026-11-03T15:00:00Z"  # 15 business hours: inside the 16-hour response target
    assert _timing(service, "PM-OP-1")["response_sla"] == "unmeasured"
    clock.value = "2026-11-04T09:00:00Z"  # 19 business hours, nobody has responded
    timing = _timing(service, "PM-OP-1")
    assert (timing["response_sla"], timing["resolution_sla"]) == ("overdue", "open")
    clock.value = "2026-11-09T09:00:00Z"  # 46 business hours against a 45-hour target
    timing = _timing(service, "PM-OP-1")
    assert (timing["response_sla"], timing["resolution_sla"]) == ("overdue", "overdue")


def test_a_matter_withdrawn_in_the_room_stops_at_its_withdrawal(tmp_path) -> None:
    clock = SettableClock("2026-11-02T08:00:00Z")
    service = _service(tmp_path, clock)
    api = PilotApi(service)
    matter_id = run_until(service, "routine", "A06")
    _command(api, OWNER, matter_id, "export_internal_review")  # moves it to recorded time
    clock.value = "2026-11-02T10:00:00Z"
    _command(api, OWNER, matter_id, "withdraw", {"note": "Customer paused; closing it now."})
    clock.value = "2026-11-05T10:00:00Z"
    timing = _timing(service, matter_id)
    assert (timing["clock"], timing["open"], timing["measured_to"]) == (
        "recorded",
        False,
        "2026-11-02T10:00:00Z",
    )
    assert (timing["elapsed_hours"], timing["business_hours"]) == (2.0, 2.0)
    assert timing["resolution_sla"] == "not_applicable"


def test_one_recorded_event_moves_the_whole_matter_to_recorded_time(tmp_path) -> None:
    clock = SettableClock("2026-11-02T08:00:00Z")
    service = _service(tmp_path, clock)
    matter_id = run_until(service, "routine", "A06")  # scripted in September, recorded now
    assert _timing(service, matter_id)["clock"] == "scripted"
    _command(PilotApi(service), OWNER, matter_id, "export_internal_review")  # no scripted time
    clock.value = "2026-11-02T09:00:00Z"
    timing = _timing(service, matter_id)
    # Measured wholly on the server's clock: an hour, not the weeks since the script.
    assert (timing["clock"], timing["elapsed_hours"], timing["business_hours"]) == (
        "recorded",
        1.0,
        1.0,
    )


def test_an_event_committed_while_the_view_is_built_is_measured(tmp_path, monkeypatch) -> None:
    service, _, clock = _open_in_room(tmp_path, "2026-11-02T08:00:00Z", "2026-11-02T08:00:00Z")
    evidence, fired = PilotService._evidence, cast(list[bool], [])

    def triaged_meanwhile(self, ctx, names):  # another request commits mid-view
        if not fired:
            fired.append(True)
            clock.value = "2026-11-02T10:00:00Z"
            self.complete_triage(OWNER, "PM-OP-1", ctx.matter["revision"])
        return evidence(self, ctx, names)

    clock.value = "2026-11-02T09:00:00Z"
    monkeypatch.setattr(PilotService, "_evidence", triaged_meanwhile)
    timing = _timing(service, "PM-OP-1")
    assert fired and timing["available"], timing
    assert (timing["first_response_business_hours"], timing["as_of"]) == (
        2.0,
        "2026-11-02T10:00:00Z",
    )


# -- never stops the room ---------------------------------------------------------------


@pytest.mark.parametrize(
    ("event_type", "stored"),
    [
        ("intake_submitted", "not a time"),
        ("delivery_accepted", "9999-12-31T23:00:00-05:00"),  # overflows the calendar
    ],
)
def test_an_unreadable_time_leaves_timing_out_not_the_room(tmp_path, event_type, stored) -> None:
    service = make_service(tmp_path)
    matter_id = run_until(service, "routine", "A13")
    with service.store.transaction() as connection:
        connection.execute(
            "UPDATE events SET fixture_at = ? WHERE matter_id = ? AND event_type = ?",
            (stored, matter_id, event_type),
        )
    view = service.view_matter(OWNER, matter_id)
    assert view["timing"]["available"] is False and view["timing"]["reason"]
    assert view["audit_chain"]["verified"] is False


def test_timing_reads_no_clock_but_the_services(tmp_path, monkeypatch) -> None:
    class NoSystemClock(timing_module.datetime):
        @classmethod
        def now(cls, tz=None):
            raise AssertionError("timing read the system clock")

        @classmethod
        def utcnow(cls):
            raise AssertionError("timing read the system clock")

    monkeypatch.setattr(timing_module, "datetime", NoSystemClock)
    service, _, clock = _open_in_room(tmp_path, "2026-11-02T08:00:00Z", "2026-11-02T08:00:00Z")
    clock.value = "2026-11-02T11:00:00Z"
    first = _timing(service, "PM-OP-1")
    assert first == _timing(service, "PM-OP-1")
    assert (first["as_of"], first["elapsed_hours"]) == ("2026-11-02T11:00:00Z", 3.0)
    assert set(first) == {
        "clock", "available", "as_of", "measured_to", "open", "elapsed_hours",
        "business_hours", "legal_controlled_hours", "business_wait_hours",
        "first_response_business_hours", "response_target_business_hours", "response_sla",
        "resolution_target_business_hours", "resolution_sla", "calendar",
    }  # fmt: skip

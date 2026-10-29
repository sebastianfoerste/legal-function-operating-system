"""Time on a matter in the review room, measured by the parent's outcome control tower."""

from src.pilot.api import PilotApi
from src.pilot.metrics import build_parent_outcome_view
from src.pilot.scenario_runner import load_scenario, scenario_paths, seed_actors
from src.pilot.service import PilotService, Stamp
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
    assert (specialist["elapsed_hours"], specialist["business_hours"]) == (48.5, 18.5)
    assert (specialist["legal_controlled_hours"], specialist["business_wait_hours"]) == (12.5, 6.0)
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
    assert timing["response_sla"] == "unmeasured" and timing["resolution_sla"] == "open"


def test_a_matter_opened_in_the_room_runs_on_the_service_clock(tmp_path) -> None:
    clock = SettableClock("2026-11-02T08:00:00Z")  # Monday 09:00 in Berlin
    service = _service(tmp_path, clock)
    api = PilotApi(service)
    status, made, _ = api.handle(
        "POST",
        "/pilot/api/matters",
        {"X-Pilot-Actor": REQUESTER},
        {"scenario_id": "routine", "matter_id": "PM-OP-1"},
    )
    assert status == 201, made
    _command(api, REQUESTER, "PM-OP-1", "submit_intake")  # the owner reads it from here on
    clock.value = "2026-11-02T10:00:00Z"
    timing = _timing(service, "PM-OP-1")
    assert (timing["clock"], timing["as_of"], timing["open"]) == (
        "recorded",
        "2026-11-02T10:00:00Z",
        True,
    )
    assert (timing["elapsed_hours"], timing["business_hours"]) == (2.0, 2.0)
    # A day later, the calendar counts only the working hours in between.
    clock.value = "2026-11-03T08:00:00Z"
    timing = _timing(service, "PM-OP-1")
    assert (timing["elapsed_hours"], timing["business_hours"]) == (24.0, 9.0)
    assert "timing" not in service.view_matter(REQUESTER, "PM-OP-1")


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


def test_an_unreadable_time_leaves_timing_out_not_the_room(tmp_path) -> None:
    service = make_service(tmp_path)
    matter_id = run_until(service, "routine", "A13")
    with service.store.transaction() as connection:
        connection.execute(
            "UPDATE events SET fixture_at = 'not a time' WHERE matter_id = ? AND seq = 0",
            (matter_id,),
        )
    view = service.view_matter(OWNER, matter_id)
    assert view["timing"]["available"] is False and view["timing"]["reason"]
    assert view["audit_chain"]["verified"] is False


def test_timing_is_deterministic_for_one_store_and_clock(tmp_path) -> None:
    service = _service(tmp_path, SettableClock("2026-11-02T08:00:00Z"))
    matter_id = run_until(service, "specialist-revision", "B20")
    assert _timing(service, matter_id) == _timing(service, matter_id)

"""Which matters the rehearsal's parent outcome view holds. Everything here is synthetic.

The parent tower measures service events, and legal's clock starts when a request is
submitted to legal. A scripted matter is a request in the view from that submission on,
in every state it reaches afterwards. A draft that was never submitted has no service
event: it is left out, and the matters that did reach legal are still reported. A
submitted matter is never left out. Where its submission carries no scripted time the
ledger has no first event for it, and the view stops with an error that names it.
"""

from __future__ import annotations

from collections.abc import Collection, Iterator
from pathlib import Path

import pytest

from src.pilot.metrics import build_parent_outcome_view, build_pilot_metrics, to_parent_ledger
from src.pilot.scenario_runner import ScenarioRunner
from src.pilot.service import PilotService, Stamp
from src.pilot.state_machine import STATES
from tests.pilot_support import OWNER, REQUESTER, make_service, revision, run_until, scenario, state

NOTE = "Customer paused the deal; closing without delivery."
REASON = "Outside the pilot charter: the customer asks for uncapped liability."


def _draft(service: PilotService) -> str:
    """A scripted draft: created, refused at its first submission, amended, not submitted."""

    matter_id = run_until(service, "specialist-revision", "B03")
    assert state(service, matter_id) == "intake"
    return matter_id


def _withdrawn_draft(service: PilotService) -> str:
    """A scripted draft its requester withdrew before submitting it."""

    matter_id = run_until(service, "blocked", "C01")
    _command(service, REQUESTER, "withdraw", matter_id, "2026-09-08T10:02:00Z", note=NOTE)
    assert state(service, matter_id) == "closed"
    return matter_id


def _command(
    service: PilotService, actor: str, command: str, matter_id: str, at: str, **args: str
) -> None:
    """One command at a scripted time, as a scenario step gives it."""

    service.execute(
        actor, matter_id, command, revision(service, matter_id), args, Stamp(fixture_at=at)
    )


def _rows(service: PilotService) -> list[str]:
    """The requests the parent tower reports, which fails if it refuses the ledger."""

    return [row["request_id"] for row in build_parent_outcome_view(service.store)["requests"]]


def _requests(service: PilotService) -> list[str]:
    """The request list handed to the parent tower, and the requests its events name."""

    requests, ledger = to_parent_ledger(service.store)
    ids = [request["id"] for request in requests]
    # The tower refuses a request without an event and an event without a request.
    assert sorted({event["request_id"] for event in ledger["events"]}) == sorted(ids)
    return ids


@pytest.mark.parametrize(
    "drafts",
    [(_draft,), (_withdrawn_draft,), (_draft, _withdrawn_draft)],
    ids=["draft in intake", "withdrawn in intake", "both"],
)
def test_a_draft_that_never_reached_legal_is_left_out_of_the_parent_view(tmp_path, drafts) -> None:
    service = make_service(tmp_path)
    delivered = run_until(service, "routine", "A13")
    before = build_parent_outcome_view(service.store)
    assert [row["request_id"] for row in before["requests"]] == [delivered]

    left_out = [make(service) for make in drafts]

    # The view still builds, and it is the view of the store without the drafts.
    assert build_parent_outcome_view(service.store) == before
    assert _requests(service) == [delivered]
    # The pilot's own measurement report keeps a row for every matter, drafts included.
    measured = build_pilot_metrics(service.store)["scripted_human_time"]
    assert {row["matter_id"] for row in measured} == {delivered, *left_out}


def _walk(service: PilotService, scenario_id: str) -> Iterator[str]:
    """Run a scenario script one step at a time; give the matter id after each step."""

    script = scenario(scenario_id)
    runner = ScenarioRunner(service)
    for step in script["steps"]:
        if step.get("restart"):
            continue
        record = runner.run_step(script, step)
        assert record["passed"], record
        yield script["matter_id"]


def test_a_submitted_matter_is_listed_in_every_state(tmp_path: Path) -> None:
    listed_in: set[str] = set()

    def check(service: PilotService, matter_id: str, others: tuple[str, ...] = ()) -> None:
        """The matter is a request, with a row in the view, exactly when it left intake."""

        current = state(service, matter_id)
        expected = sorted(others if current == "intake" else [*others, matter_id])
        assert sorted(_requests(service)) == expected, current
        if expected:
            assert sorted(_rows(service)) == expected, current
        if current != "intake":
            listed_in.add(current)

    # The three scripts, checked after every step, refused steps included.
    for scenario_id in ("routine", "specialist-revision", "blocked"):
        service = make_service(tmp_path / scenario_id)
        for matter_id in _walk(service, scenario_id):
            check(service, matter_id)
    # The ways a submitted matter closes without delivery, which no script takes.
    service = make_service(tmp_path / "withdrawn")
    matter_id = run_until(service, "routine", "A02")
    _command(service, REQUESTER, "withdraw", matter_id, "2026-09-07T08:30:00Z", note=NOTE)
    assert state(service, matter_id) == "closed"
    check(service, matter_id)
    service = make_service(tmp_path / "declined")
    matter_id = run_until(service, "routine", "A02")
    _command(service, OWNER, "decline", matter_id, "2026-09-07T09:00:00Z", reason=REASON)
    check(service, matter_id)
    service = make_service(tmp_path / "duplicate")
    original = run_until(service, "routine", "A13")
    matter_id = run_until(service, "blocked", "C03")
    _command(
        service,
        OWNER,
        "mark_duplicate",
        matter_id,
        "2026-09-08T11:30:00Z",
        original_matter_id=original,
        reason=REASON,
    )
    check(service, matter_id, others=(original,))

    assert listed_in == set(STATES) - {"intake"}


def _run(
    service: PilotService,
    scenario_id: str,
    last_step: str,
    untimed: Collection[str] = (),
    matter_id: str | None = None,
) -> str:
    """Run a script up to ``last_step``. The steps named in ``untimed`` carry no scripted time.

    ``matter_id`` runs the script as another matter, so one store can hold it twice.
    """

    script = scenario(scenario_id)
    if matter_id is not None:
        script = {**script, "matter_id": matter_id}
    runner = ScenarioRunner(service)
    for step in script["steps"]:
        if step.get("restart"):
            continue
        if step.get("id") in untimed:
            step = {key: value for key, value in step.items() if key != "at"}
        record = runner.run_step(script, step)
        assert record["passed"], record
        if step.get("id") == last_step:
            return script["matter_id"]
    raise AssertionError(f"scenario {scenario_id} has no step {last_step}")


def _every_step(scenario_id: str) -> set[str]:
    return {step["id"] for step in scenario(scenario_id)["steps"] if "id" in step}


def _refusal(*matter_ids: str) -> str:
    """The error for submitted matters whose submission carries no scripted time."""

    return (
        f"parent ledger has no first event for {', '.join(matter_ids)}: a matter named here "
        "was submitted to legal, but its submission carries no scripted time, and the ledger "
        "starts a request at its scripted submission"
    )


def _scripted_events(service: PilotService, matter_id: str) -> dict[str, list[bool]]:
    """Per event type, whether each of the matter's events carries a scripted time."""

    with service.store.reading() as connection:
        rows = connection.execute(
            "SELECT event_type, fixture_at FROM events WHERE matter_id = ? ORDER BY seq",
            (matter_id,),
        ).fetchall()
    scripted: dict[str, list[bool]] = {}
    for row in rows:
        scripted.setdefault(row["event_type"], []).append(bool(row["fixture_at"]))
    return scripted


@pytest.mark.parametrize(
    ("last_step", "untimed", "reached"),
    [
        # B02 is the refused first submission, B04 the one that reached legal.
        ("B05", {"B02", "B04"}, "assignment"),
        ("B10", {"B04"}, "review"),
        ("B45", {"B04"}, "closed"),
        # No step is scripted: the matter was worked without a script, in a scripted store.
        ("B10", None, "review"),
    ],
    ids=["stopped in assignment", "stopped in review", "delivered", "no step scripted"],
)
def test_a_submitted_matter_without_a_scripted_submission_stops_the_view(
    tmp_path: Path, last_step: str, untimed: set[str] | None, reached: str
) -> None:
    service = make_service(tmp_path)
    delivered = run_until(service, "routine", "A13")
    assert _rows(service) == [delivered]

    steps = _every_step("specialist-revision") if untimed is None else untimed
    matter_id = _run(service, "specialist-revision", last_step, steps)

    # Legal received the matter, and only the scripted time of that step is missing.
    assert state(service, matter_id) == reached
    scripted = _scripted_events(service, matter_id)
    assert scripted["intake_submitted"] == [False]
    others = [
        flag for name, flags in scripted.items() if name != "intake_submitted" for flag in flags
    ]
    assert any(others) is (untimed is not None)
    # It is not left out without a sign: the ledger and the view both stop and name it.
    for build in (to_parent_ledger, build_parent_outcome_view):
        with pytest.raises(ValueError) as refused:
            build(service.store)
        assert str(refused.value) == _refusal(matter_id)
    # The pilot's own measurement report still has a row for it.
    measured = build_pilot_metrics(service.store)["operational_time"]
    assert sorted(row["matter_id"] for row in measured) == sorted([delivered, matter_id])


def test_the_refusal_names_every_such_matter_and_no_other(tmp_path: Path) -> None:
    service = make_service(tmp_path)
    delivered = run_until(service, "routine", "A13")
    first = _run(service, "specialist-revision", "B05", {"B04"})
    second = _run(service, "blocked", "C03", {"C02"})
    draft = _run(service, "blocked", "C01", matter_id="PM-DRAFT-004")
    assert [state(service, m) for m in (delivered, first, second, draft)] == [
        "closed",
        "assignment",
        "triage",
        "intake",
    ]

    with pytest.raises(ValueError) as refused:
        build_parent_outcome_view(service.store)

    # Both are named, in the order the store lists them, which goes by its own clock.
    # The delivered matter, whose every step is scripted, and the draft are not named.
    assert str(refused.value) in {_refusal(first, second), _refusal(second, first)}
    assert delivered not in str(refused.value)
    assert draft not in str(refused.value)


def test_a_draft_is_left_out_whatever_its_events_carry(tmp_path: Path) -> None:
    """A draft has no submission, so no missing scripted time can stop the view for it."""

    service = make_service(tmp_path)
    delivered = run_until(service, "routine", "A13")
    before = build_parent_outcome_view(service.store)

    # Created and refused at its first submission, with no scripted time on any step.
    draft = _run(service, "specialist-revision", "B03", _every_step("specialist-revision"))
    assert state(service, draft) == "intake"
    scripted = _scripted_events(service, draft)
    assert "intake_submitted" not in scripted
    assert not any(flag for flags in scripted.values() for flag in flags)

    assert build_parent_outcome_view(service.store) == before
    assert _requests(service) == [delivered]

    # The same draft with every step scripted but the refused submission.
    other = make_service(tmp_path / "refused")
    delivered = run_until(other, "routine", "A13")
    before = build_parent_outcome_view(other.store)
    draft = _run(other, "specialist-revision", "B03", {"B02"})
    assert _scripted_events(other, draft)["command_refused"] == [False]
    assert build_parent_outcome_view(other.store) == before
    assert _requests(other) == [delivered]


def test_the_capability_record_says_which_matters_the_parent_ledger_holds() -> None:
    # The sentences that describe the behaviour the tests above pin: when a matter enters
    # the ledger, that a draft is not in the view, and that a submitted matter is never
    # left out, because the ledger stops with an error that names it.
    record = Path(__file__).resolve().parents[1] / "docs" / "pilot" / "CAPABILITY_RECORD.md"
    [row] = [
        line
        for line in record.read_text(encoding="utf-8").splitlines()
        if line.startswith("| `legal-function-os.service-event-ledger.v1`")
    ]
    for sentence in (
        "A matter enters the ledger when it is submitted to legal, at the scripted time of "
        "that submission.",
        "A draft that was never submitted (no `intake_submitted` event) is not in the parent "
        "outcome view.",
        "A submitted matter is never left out: if its submission carries no scripted time, "
        "the ledger has no first event for it, and `metrics.to_parent_ledger` stops with an "
        "error that names the matter instead of building the view without it.",
    ):
        assert sentence in row, sentence

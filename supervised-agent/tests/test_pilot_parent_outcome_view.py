"""Which matters the rehearsal's parent outcome view holds. Everything here is synthetic.

The parent tower measures service events, and legal's clock starts when a request is
submitted to legal. A scripted matter is a request in the view from that submission on,
in every state it reaches afterwards. A draft that was never submitted has no service
event: it is left out, and the matters that did reach legal are still reported.
"""

from __future__ import annotations

from collections.abc import Iterator
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

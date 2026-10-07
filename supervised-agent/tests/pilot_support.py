"""Shared helpers for the pilot tests. Everything here is synthetic."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from src.pilot.scenario_runner import (
    ScenarioRunner,
    all_task_ids,
    load_scenario,
    scenario_paths,
    seed_actors,
)
from src.pilot.service import PilotService
from src.pilot.store import PilotStore

OWNER = "syn-owner-legalops"
OTHER_OWNER = "syn-owner-second"
REQUESTER = "syn-requester-revops"
SPECIALIST = "syn-specialist-privacy"
APPROVER_LEAD = "syn-approver-lead"
APPROVER_GC = "syn-approver-gc"


def make_service(tmp_path: Path, *, onboard_specialist: bool = False) -> PilotService:
    service = PilotService(PilotStore(tmp_path / "pilot.sqlite3"), export_root=tmp_path / "exports")
    seed_actors(service)
    if onboard_specialist:
        service.complete_onboarding(SPECIALIST, all_task_ids("specialist_reviewer"))
    return service


def scenario(scenario_id: str) -> dict[str, Any]:
    return next(s for s in map(load_scenario, scenario_paths()) if s["scenario_id"] == scenario_id)


def run_until(service: PilotService, scenario_id: str, last_step: str) -> str:
    """Run a scenario script up to and including ``last_step``; return the matter id."""

    script = scenario(scenario_id)
    runner = ScenarioRunner(service)
    for step in script["steps"]:
        if step.get("restart"):
            continue
        record = runner.run_step(script, step)
        assert record["passed"], record
        if step.get("id") == last_step:
            return script["matter_id"]
    raise AssertionError(f"scenario {scenario_id} has no step {last_step}")


def revision(service: PilotService, matter_id: str) -> int:
    with service.store.reading() as connection:
        return int(service._matter(connection, matter_id)["revision"])


def state(service: PilotService, matter_id: str) -> str:
    with service.store.reading() as connection:
        return str(service._matter(connection, matter_id)["state"])


def change_id(service: PilotService, matter_id: str, rule_id: str) -> str:
    with service.store.reading() as connection:
        matter = service._matter(connection, matter_id)
        changes = service._changes(connection, matter_id, matter["current_version"])
    return next(change.id for change in changes if change.rule_id == rule_id)


def event_types(service: PilotService, matter_id: str) -> list[str]:
    with service.store.reading() as connection:
        rows = connection.execute(
            "SELECT event_type FROM events WHERE matter_id = ? ORDER BY seq", (matter_id,)
        ).fetchall()
    return [row["event_type"] for row in rows]

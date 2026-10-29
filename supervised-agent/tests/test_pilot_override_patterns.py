"""Playbook override patterns: rules reviewers keep departing from, as proposals only."""

import hashlib

from src.pilot.metrics import (
    OVERRIDE_THRESHOLD,
    _render_overrides,
    build_pilot_metrics,
    override_patterns,
    render_metrics_markdown,
)
from src.pilot.scenario_runner import ScenarioRunner, load_scenario, scenario_paths
from tests.pilot_support import make_service, run_until

PLAYBOOK = scenario_paths()[0].parents[1] / "playbook" / "saas-msa-deviation-playbook.v1.json"


def _record(matter, rule="payment-terms", outcome="rejected", at="2026-09-01T09:00:00Z"):
    return {
        "matter_id": matter,
        "rule_id": rule,
        "topic": "Payment terms",
        "outcome": outcome,
        "reason": f"Reason recorded on {matter}.",
        "decided_by": "syn-owner-legalops",
        "at": at,
    }


def _run_all(tmp_path):
    service = make_service(tmp_path)
    for path in scenario_paths():
        script = load_scenario(path)
        last = [step["id"] for step in script["steps"] if not step.get("restart")][-1]
        run_until(service, script["scenario_id"], last)
    return service


def _specialist_with(tmp_path, after: str, extra: dict):
    """Run the specialist scenario to its end with one extra decision after step ``after``."""

    service = make_service(tmp_path)
    script = next(
        s for s in map(load_scenario, scenario_paths()) if s["scenario_id"] == "specialist-revision"
    )
    runner = ScenarioRunner(service)
    for step in script["steps"]:
        if step.get("restart"):
            continue
        assert runner.run_step(script, step)["passed"], step["id"]
        if step.get("id") == after:
            record = runner.run_step(
                script,
                {
                    "id": "BX",
                    "actor": "syn-owner-legalops",
                    "command": "decide_change",
                    "expect": "ok",
                    **extra,
                },
            )
            assert record["passed"], record
    return build_pilot_metrics(service.store)["playbook_override_patterns"]


def test_a_rule_overridden_in_five_matters_becomes_a_proposal() -> None:
    four = override_patterns([_record(f"PM-{i}") for i in range(OVERRIDE_THRESHOLD - 1)])
    assert four["proposals"] == [] and four["rules"][0]["flagged"] is False
    five = override_patterns([_record(f"PM-{i}") for i in range(OVERRIDE_THRESHOLD)])
    [rule] = five["rules"]
    assert five["proposals"] == ["payment-terms"] and rule["flagged"]
    assert rule["rejected"] == 5 and "kept the counterparty's wording" in rule["suggestion"]
    assert [r["matter_id"] for r in rule["reasons"]] == [f"PM-{i}" for i in range(5)]


def test_the_window_ends_at_the_latest_decision_not_at_report_time() -> None:
    records = [_record(f"PM-{i}", at="2026-09-01T09:00:00Z") for i in range(4)]
    records.append(_record("PM-OLD", at="2025-08-31T09:00:00Z"))  # 366 days earlier
    result = override_patterns(records)
    assert result["as_of"] == "2026-09-01T09:00:00Z"
    assert result["rules"][0]["overrides_in_window"] == 4 and result["proposals"] == []
    records[-1]["at"] = "2025-09-02T09:00:00Z"  # inside the 365 days
    assert override_patterns(records)["proposals"] == ["payment-terms"]


def test_direction_decides_the_suggestion_and_order_is_stable() -> None:
    mixed = [_record(f"PM-{i}", outcome="amended" if i % 2 else "rejected") for i in range(5)]
    amended = [_record(f"PM-A{i}", rule="audit-right", outcome="amended") for i in range(6)]
    result = override_patterns(mixed + amended + [_record("PM-X", rule="roadmap", at=None)])
    assert [r["rule_id"] for r in result["rules"]] == ["audit-right", "payment-terms"]
    assert "rewrote the proposed wording" in result["rules"][0]["suggestion"]
    assert "Clarify the rule" in result["rules"][1]["suggestion"]
    assert result["undated_overrides"] == 1
    assert override_patterns(list(reversed(mixed + amended))) == override_patterns(mixed + amended)


def test_no_overrides_gives_an_empty_report() -> None:
    result = override_patterns([])
    assert (result["as_of"], result["rules"], result["proposals"]) == (None, [], [])
    assert "No change departed" in "\n".join(_render_overrides(result))


def test_the_rehearsal_scenarios_report_their_two_overrides(tmp_path) -> None:
    service = _run_all(tmp_path)
    patterns = build_pilot_metrics(service.store)["playbook_override_patterns"]
    summary = {r["rule_id"]: (r["rejected"], r["amended"], r["matters"]) for r in patterns["rules"]}
    assert summary == {
        "liability-cap": (0, 1, ["PM-SPECIALIST-002"]),
        "payment-terms": (1, 0, ["PM-SPECIALIST-002"]),
    }
    # Timed on the scripted clock: B26 (liability cap amended) is the latest override.
    assert patterns["proposals"] == [] and patterns["as_of"] == "2026-09-09T09:30:00Z"
    assert all(r["reasons"][0]["reason"] for r in patterns["rules"])
    assert "## Playbook override patterns" in render_metrics_markdown(
        build_pilot_metrics(service.store)
    )


def test_open_matters_do_not_count(tmp_path) -> None:
    service = make_service(tmp_path)
    run_until(service, "specialist-revision", "B13")  # payment terms rejected, still in review
    assert build_pilot_metrics(service.store)["playbook_override_patterns"]["rules"] == []


def test_the_report_is_deterministic_and_changes_nothing(tmp_path) -> None:
    playbook_before = hashlib.sha256(PLAYBOOK.read_bytes()).hexdigest()
    service = _run_all(tmp_path)

    def dump() -> str:
        with service.store.reading() as connection:
            return "\n".join(connection.iterdump())

    before = dump()
    first = build_pilot_metrics(service.store)["playbook_override_patterns"]
    second = build_pilot_metrics(service.store)["playbook_override_patterns"]
    assert first == second
    assert dump() == before
    assert hashlib.sha256(PLAYBOOK.read_bytes()).hexdigest() == playbook_before


def test_a_proposal_is_rendered_with_the_reviewers_reasons() -> None:
    lines = "\n".join(_render_overrides(override_patterns([_record(f"PM-{i}") for i in range(5)])))
    assert "### Proposal: review `payment-terms` (Payment terms)" in lines
    assert "- PM-0 (rejected): Reason recorded on PM-0." in lines
    assert "Nothing here changes the playbook" in lines


def test_a_rejection_later_reversed_is_not_an_override(tmp_path) -> None:
    accept = {
        "change_rule": "payment-terms",
        "outcome": "accepted",
        "source_support_confirmed": True,
    }
    patterns = _specialist_with(tmp_path, "B13", {"args": accept, "at": "2026-09-08T11:42:00Z"})
    assert [r["rule_id"] for r in patterns["rules"]] == ["liability-cap"]


def test_a_rejection_recorded_again_counts_once_with_its_latest_reason(tmp_path) -> None:
    again = {
        "change_rule": "payment-terms",
        "outcome": "rejected",
        "reason": "Corrected: Finance confirmed ninety day terms in writing for this customer.",
    }
    patterns = _specialist_with(tmp_path, "B13", {"args": again, "at": "2026-09-08T11:43:00Z"})
    rule = next(r for r in patterns["rules"] if r["rule_id"] == "payment-terms")
    assert (rule["overrides_in_window"], rule["rejected"], rule["matters"]) == (
        1,
        1,
        ["PM-SPECIALIST-002"],
    )
    assert rule["reasons"][0]["reason"].startswith("Corrected:")


def test_an_override_is_timed_by_its_latest_decision(tmp_path) -> None:
    again = {
        "change_rule": "payment-terms",
        "outcome": "rejected",
        "reason": "Recorded again after the liability cap was settled with Finance.",
    }
    patterns = _specialist_with(tmp_path, "B26", {"args": again, "at": "2026-09-09T09:40:00Z"})
    assert patterns["as_of"] == "2026-09-09T09:40:00Z"

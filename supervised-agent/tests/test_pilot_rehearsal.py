import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from src.pilot.cli import DOCUMENT_FIXTURES, SCENARIO_DOCS
from src.pilot.fixtures import build_synthetic_msa
from src.pilot.metrics import build_parent_outcome_view, build_pilot_metrics, to_parent_ledger
from src.pilot.onboarding import ONBOARDING_TASKS
from src.pilot.parent_bridge import CONTRACT_REVIEW_STATE, route, tier_covers
from src.pilot.scenario_runner import (
    load_scenario,
    render_scenario_markdown,
    scenario_paths,
    segments,
)
from src.pilot.state_machine import EVIDENCE, STATES, TRANSITIONS
from tests.pilot_support import make_service, run_until, scenario

ROOT = Path(__file__).resolve().parents[1]
REPOSITORY = ROOT.parent
PILOT_DOCS = ROOT / "docs" / "pilot"
SNAPSHOT = ROOT / "examples" / "pilot" / "rehearsal-2026-10-06"


def _validate(schema: dict[str, Any], value: Any, path: str = "$") -> list[str]:
    """Check a value against the subset of JSON Schema the shared contract uses."""

    problems: list[str] = []
    if "const" in schema and value != schema["const"]:
        problems.append(f"{path}: expected {schema['const']!r}")
    if "enum" in schema and value not in schema["enum"]:
        problems.append(f"{path}: {value!r} not allowed")
    expected = schema.get("type")
    names = {
        "object": dict,
        "array": list,
        "string": str,
        "boolean": bool,
        "integer": int,
        "null": type(None),
    }
    if expected:
        kinds = expected if isinstance(expected, list) else [expected]
        if not any(isinstance(value, names[kind]) for kind in kinds):
            return [*problems, f"{path}: wrong type"]
    if isinstance(value, dict) and schema.get("type") == "object":
        properties = schema.get("properties", {})
        problems += [
            f"{path}: missing {key}" for key in schema.get("required", []) if key not in value
        ]
        if schema.get("additionalProperties") is False:
            problems += [f"{path}: unexpected {key}" for key in value if key not in properties]
        for key, item in value.items():
            if key in properties:
                problems += _validate(properties[key], item, f"{path}.{key}")
    if isinstance(value, list) and "items" in schema:
        for index, item in enumerate(value):
            problems += _validate(schema["items"], item, f"{path}[{index}]")
    return problems


@pytest.fixture(scope="module")
def rehearsal(tmp_path_factory) -> Path:
    """One full rehearsal, each segment in its own process, verified in a final process."""

    folder = tmp_path_factory.mktemp("rehearsal")
    result = subprocess.run(
        [sys.executable, "-m", "src.pilot.cli", "rehearse", "--db", str(folder / "pilot.sqlite3"), "--out", str(folder / "out")],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=180,
    )  # fmt: skip
    assert result.returncode == 0, result.stdout + result.stderr
    return folder / "out"


def test_end_to_end_rehearsal_survives_restarts(rehearsal) -> None:
    report = json.loads((rehearsal / "rehearsal-report.json").read_text())
    assert (
        report["result"] == "passed"
        and report["readiness_statement"] == "ready for a supervised trial"
    )
    assert "no practitioner took part" in report["participants"]
    assert all(check["passed"] for check in report["checks"]), report["checks"]
    by_scenario: dict[str, set[int]] = {}
    for step in report["steps"]:
        by_scenario.setdefault(step["scenario"], set()).add(step["pid"])
    assert {name: len(pids) for name, pids in by_scenario.items()} == {
        "routine": 2,
        "specialist-revision": 4,
        "blocked": 2,
    }
    assert report["verified_in_process"] not in set().union(*by_scenario.values())

    outcomes = {step["id"]: step["outcome"] for step in report["steps"]}
    assert outcomes["B28"] == "ok" and outcomes["B31"] == "ok"  # a matter went through a revision
    assert {outcomes[s] for s in ("C03", "C09")} == {
        "transition_blocked"
    }  # blocked before and after restart
    names = {check["check"] for check in report["checks"]}
    assert "PM-BLOCKED-003: blocked matter produced no export of any kind" in names
    assert "PM-SPECIALIST-002: package is for the approved version and reviewed state" in names
    exports = sorted(
        p.relative_to(rehearsal / "exports").as_posix()
        for p in (rehearsal / "exports").rglob("manifest.json")
    )
    assert exports == [
        "PM-ROUTINE-001/v1/delivery/manifest.json",
        "PM-SPECIALIST-002/v2/internal-review/manifest.json",
        "PM-SPECIALIST-002/v3/delivery/manifest.json",
    ]


def test_rehearsal_metrics_separate_scripted_time_from_execution_time(rehearsal) -> None:
    metrics = json.loads((rehearsal / "pilot-metrics.json").read_text())
    assert metrics["data_basis"] == "synthetic_scripted_rehearsal"
    assert "not pilot outcomes" in metrics["interpretation"]
    assert metrics["baseline_comparison"].startswith("not performed")
    assert metrics["measurement_plan"]["defined_before_results"] is True
    rows = {row["matter_id"]: row for row in metrics["scripted_human_time"]}
    specialist = rows["PM-SPECIALIST-002"]
    assert specialist["intake_completeness"]["missing_at_first_submission"] == ["business_owner"]
    assert specialist["assignment_minutes"] == 125.0
    assert specialist["effort_minutes"] == {"intake": 45, "review": 210, "correction": 45}
    assert (
        specialist["revision_count"],
        specialist["reopened_issues"],
        specialist["versions"],
    ) == (1, 1, 3)
    assert specialist["waiting_on_clarification_minutes"] == 1260.0
    assert specialist["total_minutes_to_accepted_deliverable"] == 2910.0
    assert rows["PM-ROUTINE-001"]["total_minutes_to_accepted_deliverable"] == 450.0
    blocked = rows["PM-BLOCKED-003"]
    assert (
        blocked["total_minutes_to_accepted_deliverable"] is None
        and blocked["refused_commands"] == 6
    )
    waiting = specialist["waiting_minutes_by_cause"]
    assert set(waiting) == {
        "requester_or_missing_facts",
        "matter_owner_availability",
        "specialist_availability",
        "approver_availability",
        "requester_acceptance",
    }
    assert sum(waiting.values()) == specialist["total_minutes_to_accepted_deliverable"]
    operational = {row["matter_id"]: row for row in metrics["operational_time"]}
    assert all(0 < row["software_execution_ms"] < 5000 for row in operational.values())
    assert set(operational["PM-ROUTINE-001"]) == {
        "matter_id",
        "software_execution_ms",
        "refused_commands",
        "audit_chain_verified",
    }


def test_shared_control_contract_export_matches_the_schema(rehearsal) -> None:
    schema = json.loads(
        (REPOSITORY / "contracts" / "legal-workflow-controls.v1.schema.json").read_text()
    )
    contracts = json.loads((rehearsal / "shared-control-contract.json").read_text())
    assert set(contracts) == {"PM-ROUTINE-001", "PM-SPECIALIST-002", "PM-BLOCKED-003"}
    for matter_id, contract in contracts.items():
        assert _validate(schema, contract) == [], matter_id
    assert contracts["PM-BLOCKED-003"]["review_state"] == "blocked"
    assert contracts["PM-BLOCKED-003"]["approval_gate"]["export_allowed"] is False
    assert contracts["PM-ROUTINE-001"]["review_state"] == "approved"
    assert set(CONTRACT_REVIEW_STATE) == set(STATES)
    assert set(CONTRACT_REVIEW_STATE.values()) <= set(schema["properties"]["review_state"]["enum"])


def test_parent_rules_route_the_pilot_and_parent_tower_reads_its_events(tmp_path) -> None:
    service = make_service(tmp_path)
    run_until(service, "routine", "A13")
    run_until(service, "specialist-revision", "B45")
    run_until(service, "blocked", "C10")

    requests, ledger = to_parent_ledger(service.store)
    assert ledger["schema"] == "legal-function-os.service-event-ledger.v1"
    assert [r["id"] for r in requests] == ["PM-ROUTINE-001", "PM-SPECIALIST-002", "PM-BLOCKED-003"]
    kinds = [e["event_type"] for e in ledger["events"] if e["request_id"] == "PM-SPECIALIST-002"]
    assert kinds == [
        "submitted",
        "acknowledged",
        "assigned",
        "work_started",
        "waiting_on_business",
        "resumed",
        "approval_requested",
        "approved",
        "completed",
    ]
    tower = build_parent_outcome_view(service.store)  # the parent validates the ledger itself
    assert tower["schema"] == "legal-function-os.outcome-control-tower.v1"
    assert len(tower["requests"]) == 3 and tower["external_action_allowed"] is False

    from src.pilot.models import PilotIntake

    routing = route("PM-X", PilotIntake.model_validate(scenario("specialist-revision")["intake"]))
    assert (routing.risk, routing.queue, routing.approval_chain[-1]) == (
        "MEDIUM",
        "Commercial",
        "General Counsel",
    )
    assert tier_covers("General Counsel", "Legal Ops Lead") and not tier_covers(
        "Reviewer", "Legal Ops Lead"
    )
    assert build_pilot_metrics(service.store)["data_basis"] == "synthetic_scripted_rehearsal"


# -- documents and fixtures stay in step with the code ---------------------------------


def test_runbook_documents_every_transition_and_evidence_item() -> None:
    runbook = (PILOT_DOCS / "RUNBOOK.md").read_text()
    for t in TRANSITIONS:
        row = f"| {t.source} | {t.target} | {t.command} | {', '.join(t.roles)} | {', '.join(t.evidence)} |"
        assert row in runbook, row
    for name, meaning in EVIDENCE.items():
        assert f"| `{name}` | {meaning} |" in runbook, name


def test_onboarding_document_lists_every_task_the_software_checks() -> None:
    onboarding = (PILOT_DOCS / "ONBOARDING.md").read_text()
    for tasks in ONBOARDING_TASKS.values():
        for task_id, text in tasks:
            assert f"| `{task_id}` | {text} |" in onboarding, task_id


def test_scenario_scripts_and_document_fixtures_are_regenerable() -> None:
    paths = scenario_paths()
    assert [p.name for p in paths] == [
        "01-routine.json",
        "02-specialist-revision.json",
        "03-blocked.json",
    ]
    for path in paths:
        script = load_scenario(path)
        assert script["synthetic"] is True and len(segments(script)) >= 2
        assert script["intake"]["matter"]["source_refs"][0].startswith("synthetic:")
        generated = render_scenario_markdown(script, path.name)
        assert (SCENARIO_DOCS / f"{path.stem}.md").read_text() == generated
        committed = (DOCUMENT_FIXTURES / script["document_name"]).read_bytes()
        assert committed == build_synthetic_msa(script["document_variant"])


def test_pilot_documents_exist_and_make_no_practitioner_claim() -> None:
    for name in (
        "PILOT_CHARTER.md",
        "ONBOARDING.md",
        "RUNBOOK.md",
        "IDENTITY_CONTROLS.md",
        "CAPABILITY_RECORD.md",
        "RETROSPECTIVE.md",
        "CASE_STUDY.md",
    ):
        text = (PILOT_DOCS / name).read_text()
        assert "—" not in text and len(text) > 1500, name
    charter = (PILOT_DOCS / "PILOT_CHARTER.md").read_text()
    for heading in (
        "User and business problem",
        "Eligible matters",
        "Exclusions",
        "Roles and responsibilities",
        "Baseline and measurement",
        "Acceptance criteria",
        "Stop conditions",
    ):
        assert heading in charter
    case_study = (PILOT_DOCS / "CASE_STUDY.md").read_text()
    assert "ready for a supervised trial" in case_study.lower() and "No practitioner" in case_study


def test_committed_rehearsal_snapshot_is_a_passed_run_without_local_paths() -> None:
    report = json.loads((SNAPSHOT / "rehearsal-report.json").read_text())
    assert report["result"] == "passed" and len(report["steps"]) == 68
    for path in SNAPSHOT.rglob("*"):
        if path.is_file() and path.suffix in {".json", ".md", ".html"}:
            text = path.read_text()
            assert "/Users/" not in text and "/tmp/" not in text, path
    for delivery in SNAPSHOT.glob("exports/*/v*/delivery"):
        assert (delivery / "customer-package.html").is_file() and (
            delivery / "reviewed-document.docx"
        ).is_file()

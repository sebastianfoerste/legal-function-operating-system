"""Command line for the local pilot: seed, rehearse, measure, serve."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from src.docx_redline import list_tracked_changes, read_paragraph_texts
from src.pilot.fixtures import build_synthetic_msa
from src.pilot.metrics import (
    build_parent_outcome_view,
    build_pilot_metrics,
    control_contract,
    render_metrics_markdown,
)
from src.pilot.scenario_runner import (
    ScenarioRunner,
    load_scenario,
    render_scenario_markdown,
    scenario_paths,
    seed_actors,
    segments,
)
from src.pilot.service import PilotService
from src.pilot.store import PilotStore

DEFAULT_DB = Path(".pilot") / "pilot.sqlite3"
_ROOT = Path(__file__).resolve().parents[2]
SCENARIO_DOCS = _ROOT / "docs" / "pilot" / "scenarios"
DOCUMENT_FIXTURES = _ROOT / "examples" / "pilot" / "documents"


def _service(db: Path) -> PilotService:
    return PilotService(PilotStore(db))


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def cmd_seed(args: argparse.Namespace) -> int:
    seed_actors(_service(args.db))
    print(f"seeded synthetic actors in {args.db}")
    return 0


def cmd_run_segment(args: argparse.Namespace) -> int:
    """Run one slice of a scenario in this process (used by ``rehearse``)."""

    scenario = load_scenario(args.scenario)
    records = ScenarioRunner(_service(args.db)).run(scenario, args.start, args.end)
    _write_json(args.report, records)
    return 0


def _verify(
    service: PilotService, scenarios: list[dict[str, Any]], steps: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """End-of-rehearsal checks, run in a fresh process against the stored state."""

    checks: list[dict[str, Any]] = []

    def check(name: str, ok: bool, detail: str) -> None:
        checks.append({"check": name, "passed": bool(ok), "detail": detail})

    failed = [s["id"] for s in steps if not s["passed"]]
    check(
        "every scripted step had its expected outcome",
        not failed,
        f"{len(steps)} steps; failed: {failed or 'none'}",
    )
    for scenario in scenarios:
        matter_id, expected = scenario["matter_id"], scenario["expected_final"]
        pids = {s["pid"] for s in steps if s["scenario"] == scenario["scenario_id"]}
        check(
            f"{matter_id}: steps ran in more than one process",
            len(pids) > 1,
            f"{len(pids)} processes",
        )
        with service.store.reading() as connection:
            matter = dict(service._matter(connection, matter_id))
            chain = service.store.verify_chain(connection, matter_id)
            manifests = [
                dict(r)
                for r in connection.execute(
                    "SELECT * FROM deliverable_manifests WHERE matter_id = ? ORDER BY manifest_id",
                    (matter_id,),
                )
            ]
            approvals = [
                dict(r)
                for r in connection.execute(
                    "SELECT * FROM decisions WHERE matter_id = ? AND kind = 'final_approval'",
                    (matter_id,),
                )
            ]
            refused = connection.execute(
                "SELECT COUNT(*) FROM events WHERE matter_id = ? AND event_type = 'command_refused'",
                (matter_id,),
            ).fetchone()[0]
            versions = connection.execute(
                "SELECT COUNT(*) FROM matter_versions WHERE matter_id = ?", (matter_id,)
            ).fetchone()[0]
            source = bytes(
                service._version(connection, matter_id, matter["current_version"])[1][
                    "document_blob"
                ]
            )
        deliveries = [m for m in manifests if m["kind"] == "delivery_package"]
        check(
            f"{matter_id}: final state",
            matter["state"] == expected["state"],
            f"{matter['state']} (expected {expected['state']})",
        )
        check(
            f"{matter_id}: final version, earlier versions kept",
            matter["current_version"] == expected["version"] == versions,
            f"current v{matter['current_version']}, {versions} stored",
        )
        check(
            f"{matter_id}: closing outcome",
            matter["closed_outcome"] == expected["closed_outcome"],
            str(matter["closed_outcome"]),
        )
        check(
            f"{matter_id}: event chain intact",
            chain.verified,
            f"{chain.event_count} events, {chain.reason}",
        )
        check(
            f"{matter_id}: delivery package count",
            len(deliveries) == expected["delivery_packages"],
            f"{len(deliveries)} (expected {expected['delivery_packages']})",
        )
        if expected["delivery_packages"] == 0:
            check(
                f"{matter_id}: blocked matter produced no export of any kind",
                not manifests,
                f"{len(manifests)} manifests, {refused} refused commands on record",
            )
            check(
                f"{matter_id}: no approval was ever recorded",
                not approvals,
                f"{len(approvals)} approvals",
            )
            continue
        valid = [a for a in approvals if a["invalidated_at"] is None]
        for delivery in deliveries:
            body = json.loads(delivery["body"])
            bound = any(
                a["version"] == delivery["version"] and a["review_hash"] == delivery["review_hash"]
                for a in valid
            )
            check(
                f"{matter_id}: package is for the approved version and reviewed state",
                bound and delivery["version"] == matter["current_version"],
                f"package v{delivery['version']}, current v{matter['current_version']}",
            )
            folder = service.export_root / body["folder"]
            intact = all(
                (folder / f["name"]).is_file()
                and hashlib.sha256((folder / f["name"]).read_bytes()).hexdigest() == f["sha256"]
                for f in body["files"]
            )
            check(f"{matter_id}: package files match the stored manifest", intact, body["folder"])
            reviewed = (folder / "reviewed-document.docx").read_bytes()
            check(
                f"{matter_id}: rejecting every tracked change restores the customer draft",
                read_paragraph_texts(reviewed, "rejected")
                == read_paragraph_texts(source, "accepted"),
                f"{len(list_tracked_changes(reviewed))} tracked changes",
            )
    return checks


def cmd_verify(args: argparse.Namespace) -> int:
    service = _service(args.db)
    scenarios = [load_scenario(path) for path in scenario_paths()]
    steps = json.loads((args.out / "rehearsal-steps.json").read_text(encoding="utf-8"))
    checks = _verify(service, scenarios, steps)
    metrics = build_pilot_metrics(service.store)
    _write_json(args.out / "pilot-metrics.json", metrics)
    (args.out / "pilot-metrics.md").write_text(render_metrics_markdown(metrics), encoding="utf-8")
    tower = build_parent_outcome_view(service.store)
    _write_json(args.out / "parent-outcome-view.json", tower)
    contracts = {}
    for scenario in scenarios:
        owner = "syn-owner-legalops"
        with service.store.reading() as connection:
            assigned = service._assigned(connection, scenario["matter_id"])
            events = [
                dict(r)
                for r in connection.execute(
                    "SELECT * FROM events WHERE matter_id = ? ORDER BY seq",
                    (scenario["matter_id"],),
                )
            ]
        reader = next(iter(assigned.get("matter_owner", [])), owner)
        contracts[scenario["matter_id"]] = control_contract(
            service.view_matter(reader, scenario["matter_id"]), events
        )
    _write_json(args.out / "shared-control-contract.json", contracts)
    passed = all(c["passed"] for c in checks)
    report = {
        "schema": "legal-ops-agent.pilot-rehearsal.v1",
        "result": "passed" if passed else "failed",
        "participants": "synthetic actors only; no practitioner took part",
        "readiness_statement": "ready for a supervised trial" if passed else "not ready",
        "verified_in_process": os.getpid(),
        "checks": checks,
        "steps": steps,
    }
    _write_json(args.out / "rehearsal-report.json", report)
    lines = [
        "# End-to-end rehearsal report",
        "",
        f"- Result: **{report['result']}**",
        f"- Participants: {report['participants']}",
        f"- Status: {report['readiness_statement']}",
        "",
        "## Checks after the final restart",
        "",
        "| Check | Result | Detail |",
        "| --- | --- | --- |",
    ]
    lines += [
        f"| {c['check']} | {'pass' if c['passed'] else 'FAIL'} | {c['detail']} |" for c in checks
    ]
    lines += [
        "",
        "## Steps",
        "",
        "| Step | Process | Actor | Command | Expected | Outcome | State after | Version |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    lines += [
        f"| {s['id']} | {s['pid']} | {s['actor'] or 'library caller'} | {s['command']} | {s['expect']} | {s['outcome']}{'' if s['passed'] else ' (UNEXPECTED)'} | {s['state_after']} | {s['version_after']} |"
        for s in steps
    ]
    (args.out / "rehearsal-report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(
        f"rehearsal {report['result']}: {sum(c['passed'] for c in checks)}/{len(checks)} checks, {len(steps)} steps -> {args.out}"
    )
    return 0 if passed else 1


def cmd_rehearse(args: argparse.Namespace) -> int:
    """Run all three scenarios, starting a new process at every restart marker."""

    if args.db.exists():
        print(f"refusing to rehearse into an existing store: {args.db}", file=sys.stderr)
        return 2
    args.out.mkdir(parents=True, exist_ok=True)
    base = [sys.executable, "-m", "src.pilot.cli"]
    env = {**os.environ, "PILOT_EXPORT_ROOT": str(args.out / "exports")}
    subprocess.run([*base, "seed", "--db", str(args.db)], check=True, env=env)
    steps: list[dict[str, Any]] = []
    for path in scenario_paths():
        scenario = load_scenario(path)
        for start, end in segments(scenario):
            report = args.out / "segment.json"
            subprocess.run(
                [
                    *base,
                    "run-segment",
                    "--db",
                    str(args.db),
                    "--scenario",
                    str(path),
                    "--start",
                    str(start),
                    "--end",
                    str(end),
                    "--report",
                    str(report),
                ],
                check=True,
                env=env,
            )
            steps += [
                {**record, "scenario": scenario["scenario_id"]}
                for record in json.loads(report.read_text(encoding="utf-8"))
            ]
            report.unlink()
    _write_json(args.out / "rehearsal-steps.json", steps)
    return subprocess.run(
        [*base, "verify", "--db", str(args.db), "--out", str(args.out)], env=env
    ).returncode


def cmd_scenario_docs(args: argparse.Namespace) -> int:
    """Regenerate the facilitator scripts and the synthetic DOCX fixtures."""

    for path in scenario_paths():
        scenario = load_scenario(path)
        target = SCENARIO_DOCS / f"{path.stem}.md"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(render_scenario_markdown(scenario, path.name), encoding="utf-8")
        document = DOCUMENT_FIXTURES / scenario["document_name"]
        document.parent.mkdir(parents=True, exist_ok=True)
        document.write_bytes(build_synthetic_msa(scenario["document_variant"]))
        print(f"wrote {target} and {document}")
    return 0


def cmd_metrics(args: argparse.Namespace) -> int:
    print(render_metrics_markdown(build_pilot_metrics(_service(args.db).store)))
    return 0


def cmd_serve(args: argparse.Namespace) -> int:
    os.environ["PILOT_DB"] = str(args.db)
    from runtime_agent.app import run

    run()
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Supervised pilot workflow (synthetic, local).")
    commands = parser.add_subparsers(dest="command", required=True)

    def add(name: str, handler, text: str) -> argparse.ArgumentParser:
        sub = commands.add_parser(name, help=text)
        sub.add_argument("--db", type=Path, default=DEFAULT_DB, help="SQLite store path.")
        sub.set_defaults(handler=handler)
        return sub

    add("seed", cmd_seed, "Register the synthetic actors.")
    segment = add("run-segment", cmd_run_segment, "Run one slice of a scenario (internal).")
    segment.add_argument("--scenario", type=Path, required=True)
    segment.add_argument("--start", type=int, required=True)
    segment.add_argument("--end", type=int, required=True)
    segment.add_argument("--report", type=Path, required=True)
    rehearse = add("rehearse", cmd_rehearse, "Run the end-to-end rehearsal with restarts.")
    rehearse.add_argument("--out", type=Path, required=True, help="Folder for reports and exports.")
    verify = add("verify", cmd_verify, "Verify a rehearsed store and write the reports.")
    verify.add_argument("--out", type=Path, required=True)
    add("metrics", cmd_metrics, "Print the measurement report.")
    add("scenario-docs", cmd_scenario_docs, "Regenerate facilitator scripts and DOCX fixtures.")
    add("serve", cmd_serve, "Serve the review room on 127.0.0.1.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.handler(args))


if __name__ == "__main__":
    raise SystemExit(main())

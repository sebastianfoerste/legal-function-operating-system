"""Run a scenario script through the application layer and check each outcome."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any

from models import ReviewDecision
from src.export_gate import ExportBlockedError, ExportContext, require_export_eligibility
from src.legal_ops import apply_review_decision
from src.pilot.fixtures import build_synthetic_msa
from src.pilot.models import PilotIntake
from src.pilot.onboarding import ONBOARDING_TASKS, SYNTHETIC_ACTORS
from src.pilot.service import PilotError, PilotService, Stamp, TransitionBlockedError

SCENARIO_DIR = Path(__file__).resolve().parents[2] / "examples" / "pilot" / "scenarios"
# Scenario 2 shows the readiness check refusing a reviewer who has not onboarded.
ONBOARDED_BY_SCENARIO = frozenset({"syn-specialist-privacy"})


def scenario_paths() -> list[Path]:
    return sorted(SCENARIO_DIR.glob("0*.json"))


def load_scenario(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def all_task_ids(role: str) -> list[str]:
    return [task_id for task_id, _ in ONBOARDING_TASKS[role]]  # type: ignore[index]


def seed_actors(service: PilotService) -> None:
    """Register the synthetic participants and onboard all but the scripted exception."""

    for actor in SYNTHETIC_ACTORS:
        service.register_actor(actor)
        if actor.actor_id not in ONBOARDED_BY_SCENARIO:
            service.complete_onboarding(actor.actor_id, all_task_ids(actor.role))


def segments(scenario: dict[str, Any]) -> list[tuple[int, int]]:
    """Step ranges between restart markers."""

    bounds: list[tuple[int, int]] = []
    start = 0
    for index, step in enumerate(scenario["steps"]):
        if step.get("restart"):
            bounds.append((start, index))
            start = index + 1
    bounds.append((start, len(scenario["steps"])))
    return bounds


class ScenarioRunner:
    def __init__(self, service: PilotService) -> None:
        self.service = service

    # -- lookups ------------------------------------------------------------------

    def _matter_row(self, matter_id: str) -> dict[str, Any] | None:
        with self.service.store.reading() as connection:
            row = connection.execute(
                "SELECT * FROM matters WHERE matter_id = ?", (matter_id,)
            ).fetchone()
            return dict(row) if row else None

    def _resolve(self, matter_id: str, args: dict[str, Any]) -> dict[str, Any]:
        """Replace readable references in a script with stored identifiers."""

        resolved = dict(args)
        with self.service.store.reading() as connection:
            matter = self.service._matter(connection, matter_id)
            changes = self.service._changes(connection, matter_id, matter["current_version"])
            comments = self.service._comments(connection, matter_id)

        def comment_id(matcher: dict[str, str]) -> str:
            for comment in reversed(comments):
                if matcher.get("kind") not in {None, comment.kind}:
                    continue
                if matcher.get("body_contains", "") not in comment.body:
                    continue
                return comment.comment_id
            raise LookupError(f"no comment matches {matcher}")

        if "change_rule" in resolved:
            rule = resolved.pop("change_rule")
            resolved["change_id"] = next(c.id for c in changes if c.rule_id == rule)
        if "comment" in resolved:
            resolved["comment_id"] = comment_id(resolved.pop("comment"))
        if "comments" in resolved:
            resolved["comment_ids"] = [comment_id(m) for m in resolved.pop("comments")]
        return resolved

    # -- execution ----------------------------------------------------------------

    def _call(self, call) -> tuple[str, str, list[str]]:
        try:
            call()
        except TransitionBlockedError as error:
            failing = [item["name"] for item in error.evidence if not item["ok"]]
            return error.code, str(error), failing
        except PilotError as error:
            return error.code, str(error), []
        except ExportBlockedError as error:
            return "export_blocked", str(error), []
        return "ok", "", []

    def _direct(self, scenario: dict[str, Any], name: str) -> tuple[str, str, list[str]]:
        """Attempts to obtain an export without going through the workflow."""

        matter_id = scenario["matter_id"]
        with self.service.store.reading() as connection:
            matter = self.service._matter(connection, matter_id)
            body, row = self.service._version(connection, matter_id, matter["current_version"])
            changes = self.service._changes(connection, matter_id, matter["current_version"])
        forged = apply_review_decision(
            body.assessment,
            ReviewDecision(
                reviewer="Unverified Caller",
                state="approved",
                note="Forged approval supplied by a caller outside the workflow.",
            ),
        )
        if name == "stateless_delivery_gate":
            digest = hashlib.sha256(row["document_blob"]).hexdigest()
            context = ExportContext(
                kind="delivery_package",
                assessment=forged,
                change_set_assessment_id=forged.assessment_id,
                recorded_document_sha256=digest,
                actual_document_sha256=digest,
                change_decisions={change.id: "accepted" for change in changes},
            )
            return self._call(lambda: require_export_eligibility(context))
        if name == "legacy_docx_render":
            from src.collaboration_workspace import (
                build_change_set,
                decide_change,
                render_annotated_docx,
            )

            with tempfile.TemporaryDirectory() as folder:
                source = Path(folder) / "source.docx"
                source.write_bytes(row["document_blob"])
                try:
                    change_set = build_change_set(body.assessment, source)
                    for change in list(change_set.changes):
                        change_set = decide_change(change_set, change.id, "accepted")
                    render_annotated_docx(
                        change_set, source, Path(folder) / "out.docx", assessment=body.assessment
                    )
                except ValueError as error:
                    # ExportBlockedError is a ValueError; so is the source-boundary refusal.
                    return "export_blocked", str(error), []
            return "ok", "", []
        raise ValueError(f"unknown direct step {name}")

    def run_step(self, scenario: dict[str, Any], step: dict[str, Any]) -> dict[str, Any]:
        matter_id = scenario["matter_id"]
        stamp = Stamp(step.get("at"), step.get("effort_minutes"))
        record: dict[str, Any] = {
            "id": step.get("id"),
            "say": step.get("say", ""),
            "actor": step.get("actor"),
            "command": step.get("command") or step.get("direct") or "onboard",
            "expect": step.get("expect", "ok"),
            "pid": os.getpid(),
        }
        failing: list[str] = []
        if "onboard" in step:
            actor = next(a for a in self.service.list_actors() if a.actor_id == step["onboard"])
            record["actor"] = actor.actor_id
            outcome, message, failing = self._call(
                lambda: self.service.complete_onboarding(actor.actor_id, all_task_ids(actor.role))
            )
        elif "direct" in step:
            outcome, message, failing = self._direct(scenario, step["direct"])
        elif step["command"] == "create_matter":
            outcome, message, failing = self._call(
                lambda: self.service.create_matter(
                    step["actor"],
                    PilotIntake.model_validate(scenario["intake"]),
                    scenario["document_name"],
                    build_synthetic_msa(scenario["document_variant"]),
                    matter_id=matter_id,
                    stamp=stamp,
                )
            )
        else:
            row = self._matter_row(matter_id)
            revision = row["revision"] if row else 0
            args = self._resolve(matter_id, step.get("args", {}))
            outcome, message, failing = self._call(
                lambda: self.service.execute(
                    step["actor"], matter_id, step["command"], revision, args, stamp
                )
            )
            second = step.get("conflicting")
            if second:
                # Submitted against the revision loaded before the first write landed.
                second_args = self._resolve(matter_id, second.get("args", {}))
                code, text, _ = self._call(
                    lambda: self.service.execute(
                        second["actor"], matter_id, second["command"], revision, second_args, stamp
                    )
                )
                record["conflicting"] = {
                    "actor": second["actor"],
                    "command": second["command"],
                    "expect": second["expect"],
                    "outcome": code,
                    "message": text,
                    "passed": code == second["expect"],
                }
        row = self._matter_row(matter_id)
        expected_evidence = step.get("expect_evidence", [])
        record.update(
            {
                "outcome": outcome,
                "message": message,
                "failing_evidence": failing,
                "state_after": row["state"] if row else None,
                "version_after": row["current_version"] if row else None,
                "revision_after": row["revision"] if row else None,
                "passed": outcome == record["expect"]
                and set(expected_evidence) <= set(failing)
                and record.get("conflicting", {}).get("passed", True),
            }
        )
        return record

    def run(
        self, scenario: dict[str, Any], start: int = 0, end: int | None = None
    ) -> list[dict[str, Any]]:
        steps = scenario["steps"][start:end]
        return [self.run_step(scenario, step) for step in steps if not step.get("restart")]


_RESULT = {
    "ok": "succeeds",
    "transition_blocked": "refused: evidence missing or not allowed in this state",
    "permission_denied": "refused: role or assignment",
    "stale_submission": "refused: stale submission",
    "export_blocked": "refused by the export gate",
}


def render_scenario_markdown(scenario: dict[str, Any], source_name: str) -> str:
    """Facilitator script for a walkthrough, generated from the scenario file."""

    names = {actor.actor_id: actor.display_name for actor in SYNTHETIC_ACTORS}
    final = scenario["expected_final"]
    lines = [
        f"# {scenario['title']}",
        "",
        f"> Synthetic identities and data. Generated from `examples/pilot/scenarios/{source_name}`. "
        "Edit that file, then run `python -m src.pilot.cli scenario-docs`.",
        "",
        scenario["purpose"],
        "",
        f"- Matter: `{scenario['matter_id']}`",
        f"- Customer draft: `examples/pilot/documents/{scenario['document_name']}`",
        f"- Parent routing inputs: value band `{scenario['intake']['value_band']}`, personal data "
        f"`{scenario['intake'].get('personal_data', False)}`, uncapped liability "
        f"`{scenario['intake'].get('uncapped_liability', False)}`",
        f"- Recorded decision authority: `{scenario['intake']['decision_authority'] or 'none'}`",
        "",
        "## Facilitator script",
        "",
        "Scripted times are fixture timestamps used to demonstrate measurement. They are not "
        "observations.",
        "",
        "| Step | Scripted time (UTC) | Who | Action | Expected result | What happens |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for step in scenario["steps"]:
        if step.get("restart"):
            lines.append(
                f"| restart |  | Facilitator | stop and restart the process |  | {step['say']} |"
            )
            continue
        if "onboard" in step:
            who, action = names[step["onboard"]], "complete onboarding tasks"
        elif "direct" in step:
            who, action = "Caller outside the workflow", step["direct"].replace("_", " ")
        else:
            who, action = names[step["actor"]], step["command"].replace("_", " ")
        result = _RESULT[step.get("expect", "ok")]
        if step.get("expect_evidence"):
            result += " (" + ", ".join(step["expect_evidence"]) + ")"
        if step.get("conflicting"):
            second = step["conflicting"]
            action += f"; at the same revision {names[second['actor']]} sends {second['command']}"
            result += "; the second request is " + _RESULT[second["expect"]]
        lines.append(
            f"| {step['id']} | {step.get('at', '')} | {who} | {action} | {result} | {step['say']} |"
        )
    lines += [
        "",
        "## Expected end state",
        "",
        f"- State: `{final['state']}`",
        f"- Matter version: {final['version']}",
        f"- Delivery packages written: {final['delivery_packages']}",
        f"- Closing outcome: `{final['closed_outcome']}`",
        "",
    ]
    return "\n".join(lines)

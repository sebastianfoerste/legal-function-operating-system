"""HTTP-shaped entry point for the review room, free of sockets.

``PilotApi.handle`` takes a method, path, headers and JSON body and returns a
status and payload. The runtime server is a thin adapter around it, and tests call
it directly, so the same permission, staleness and gate checks apply whether a
request comes from the interface or from a script.
"""

from __future__ import annotations

import base64
import binascii
import json
from typing import Any

from pydantic import ValidationError

from src.export_gate import ExportBlockedError
from src.pilot.fixtures import build_synthetic_msa
from src.pilot.models import PilotIntake
from src.pilot.onboarding import ONBOARDING_TASKS
from src.pilot.review_room import REVIEW_ROOM_HTML
from src.pilot.scenario_runner import load_scenario, scenario_paths
from src.pilot.service import (
    IDENTITY_NOTICE,
    PermissionDeniedError,
    PilotError,
    PilotService,
    StaleSubmissionError,
    Stamp,
    TransitionBlockedError,
)

ACTOR_HEADER = "x-pilot-actor"
Response = tuple[int, Any, str]
JSON = "application/json; charset=utf-8"
HTML = "text/html; charset=utf-8"


def _error(status: int, code: str, message: str, **extra: Any) -> Response:
    return status, {"error": code, "message": message, **extra}, JSON


class PilotApi:
    def __init__(self, service: PilotService) -> None:
        self.service = service

    def handle(
        self, method: str, path: str, headers: dict[str, str], body: dict[str, Any] | None = None
    ) -> Response:
        parts = [part for part in path.split("?")[0].strip("/").split("/") if part]
        actor_id = {key.lower(): value for key, value in headers.items()}.get(ACTOR_HEADER, "")
        try:
            return self._route(method.upper(), parts, actor_id.strip(), body or {})
        except StaleSubmissionError as error:
            return _error(
                error.status, error.code, str(error), current_revision=error.current_revision
            )
        except TransitionBlockedError as error:
            return _error(error.status, error.code, str(error), evidence=error.evidence)
        except ExportBlockedError as error:
            checks = [check.model_dump() for check in error.eligibility.checks]
            return _error(409, "export_blocked", str(error), checks=checks)
        except PilotError as error:
            return _error(error.status, error.code, str(error))
        except ValidationError as error:
            return _error(422, "invalid_command", str(error))

    def _route(
        self, method: str, parts: list[str], actor_id: str, body: dict[str, Any]
    ) -> Response:
        if parts == ["pilot"] and method == "GET":
            return 200, REVIEW_ROOM_HTML, HTML
        if parts[:2] != ["pilot", "api"]:
            return _error(404, "not_found", "unknown pilot route")
        rest = parts[2:]
        if rest == ["actors"] and method == "GET":
            # Public on purpose: this list is a role picker, not a login.
            return (
                200,
                {
                    "identity_notice": IDENTITY_NOTICE,
                    "actors": [actor.model_dump() for actor in self.service.list_actors()],
                    "onboarding_tasks": {
                        role: [{"id": i, "task": t} for i, t in tasks]
                        for role, tasks in ONBOARDING_TASKS.items()
                    },
                    "scenarios": [
                        {"scenario_id": s["scenario_id"], "title": s["title"]}
                        for s in map(load_scenario, scenario_paths())
                    ],
                },
                JSON,
            )
        if not actor_id:
            return _error(
                401, "actor_required", f"send the {ACTOR_HEADER} header. {IDENTITY_NOTICE}"
            )
        if rest == ["matters"] and method == "GET":
            return 200, {"matters": self.service.list_matters(actor_id)}, JSON
        if rest == ["matters"] and method == "POST":
            return 201, self._create(actor_id, body), JSON
        if len(rest) >= 2 and rest[0] == "matters":
            matter_id = rest[1]
            tail = rest[2:]
            if not tail and method == "GET":
                return 200, self.service.view_matter(actor_id, matter_id), JSON
            if tail == ["history"] and method == "GET":
                return 200, self.service.history(actor_id, matter_id), JSON
            if tail == ["package"] and method == "GET":
                return 200, self._package(actor_id, matter_id), HTML
            if tail == ["commands"] and method == "POST":
                return 200, self._command(actor_id, matter_id, body), JSON
        return _error(404, "not_found", "unknown pilot route")

    def _create(self, actor_id: str, body: dict[str, Any]) -> dict[str, Any]:
        """Open a matter from a synthetic scenario fixture or from a supplied intake."""

        scenario_id = body.get("scenario_id")
        if scenario_id:
            scenario = next(
                (
                    s
                    for s in map(load_scenario, scenario_paths())
                    if s["scenario_id"] == scenario_id
                ),
                None,
            )
            if scenario is None:
                raise PilotError(f"unknown scenario {scenario_id}")
            intake = PilotIntake.model_validate(scenario["intake"])
            name, document = (
                scenario["document_name"],
                build_synthetic_msa(scenario["document_variant"]),
            )
        else:
            intake = PilotIntake.model_validate(body.get("intake"))
            name = str(body.get("document_name") or "customer-draft.docx")
            try:
                document = base64.b64decode(str(body.get("document_base64") or ""), validate=True)
            except (binascii.Error, ValueError) as error:
                raise PilotError("document_base64 is not valid base64") from error
        return self.service.create_matter(
            actor_id,
            intake,
            name,
            document,
            matter_id=body.get("matter_id") or None,
            stamp=Stamp(effort_minutes=_effort(body)),
        )

    def _command(self, actor_id: str, matter_id: str, body: dict[str, Any]) -> dict[str, Any]:
        command = body.get("command")
        revision = body.get("expected_revision")
        args = body.get("args") or {}
        if (
            not isinstance(command, str)
            or not isinstance(revision, int)
            or not isinstance(args, dict)
        ):
            raise PilotError("a command needs: command, expected_revision (integer) and args")
        # Scripted fixture time is never accepted from the interface.
        return self.service.execute(
            actor_id, matter_id, command, revision, args, Stamp(effort_minutes=_effort(body))
        )

    def _package(self, actor_id: str, matter_id: str) -> str:
        """The approved customer package, served only from a stored delivery manifest."""

        view = self.service.view_matter(actor_id, matter_id)
        manifests = view.get("delivery") or [
            m for m in view.get("manifests", []) if m["kind"] == "delivery_package"
        ]
        if not manifests:
            raise PermissionDeniedError("no approved delivery package exists for this matter")
        latest = manifests[-1]
        folder = self.service.export_root / latest["folder"]
        return (folder / "customer-package.html").read_text(encoding="utf-8")


def _effort(body: dict[str, Any]) -> int | None:
    minutes = body.get("effort_minutes")
    return minutes if isinstance(minutes, int) and 0 <= minutes <= 24 * 60 else None


def encode(payload: Any) -> bytes:
    if isinstance(payload, str):
        return payload.encode("utf-8")
    return json.dumps(payload, indent=2, default=str).encode("utf-8")

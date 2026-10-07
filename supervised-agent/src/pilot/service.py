"""Application layer for the pilot workflow.

Every review-room action, CLI step and scenario step goes through
``PilotService``. Each command runs in one database transaction: load the matter,
compare the caller's ``expected_revision``, check the simulated role and the
assignment, evaluate the evidence the state machine demands, write, append a
hash-chained event and bump the revision.
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import time
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, ValidationError

from models import LegalOpsAssessment, ReviewDecision
from src.docx_redline import DocumentIndex, UnsupportedDocumentError, index_docx
from src.export_gate import (
    ExportBlockedError,
    ExportContext,
    ExportEligibility,
    ExportKind,
    RequiredDecision,
    StatefulContext,
    evaluate_export_eligibility,
)
from src.legal_ops import apply_review_decision, assess_matter
from src.pilot import deliverable
from src.pilot.models import (
    DELIVERABLE_SECTIONS,
    REQUIRED_FACTS,
    SYSTEM_ACTOR_ID,
    Actor,
    Comment,
    CommentResponse,
    Finding,
    ParentRouting,
    PilotIntake,
    Role,
)
from src.pilot.onboarding import missing_tasks
from src.pilot.parent_bridge import (
    pilot_scope_exclusions,
    required_approval_tier,
    route,
    tier_covers,
)
from src.pilot.policy import is_substantive_change
from src.pilot.state_machine import (
    EVIDENCE,
    REASSESSMENT_SOURCES,
    WITHDRAWAL_ROLES,
    allowed_commands,
    find_transition,
)
from src.pilot.store import Clock, PilotStore, SystemClock, canonical
from src.playbook import DocumentChange, Playbook, load_playbook, propose_changes
from src.source_verification import verify_source_ref, verify_source_refs

IDENTITY_NOTICE = (
    "Simulated local roles. Selecting an actor is not authentication; do not use for "
    "practitioner work until the identity controls in docs/pilot/IDENTITY_CONTROLS.md exist."
)
REVIEW_ROLES: tuple[Role, ...] = ("matter_owner", "specialist_reviewer", "final_approver")
COMMENT_STATES = frozenset(
    {"review", "revision_requested", "revised", "approved", "ready_for_delivery"}
)
DECISION_STATES = frozenset({"review", "revision_requested"})


class PilotError(Exception):
    status = 400
    code = "pilot_error"


class NotFoundError(PilotError):
    status, code = 404, "not_found"


class PermissionDeniedError(PilotError):
    status, code = 403, "permission_denied"


class InvalidCommandError(PilotError):
    status, code = 422, "invalid_command"


class StaleSubmissionError(PilotError):
    status, code = 409, "stale_submission"

    def __init__(self, expected: int, current: int) -> None:
        self.current_revision = current
        super().__init__(
            f"stale submission: the matter is at revision {current}, the request was made "
            f"against revision {expected}; reload and resubmit"
        )


class TransitionBlockedError(PilotError):
    status, code = 409, "transition_blocked"

    def __init__(self, command: str, evidence: list[dict[str, Any]]) -> None:
        self.evidence = evidence
        missing = [f"{item['name']}: {item['detail']}" for item in evidence if not item["ok"]]
        super().__init__(f"{command} refused; missing evidence: " + "; ".join(missing))


@dataclass(frozen=True)
class Stamp:
    """Scenario-supplied measurement data, kept apart from operational time.

    ``fixture_at`` is a deterministic scripted timestamp; ``effort_minutes`` is the
    declared human effort for the step. Neither is ever read from a clock.
    """

    fixture_at: str | None = None
    effort_minutes: int | None = None


class StoredChange(DocumentChange):
    specialist_role: str | None = None
    decided_by: str | None = None
    decided_at: str | None = None
    source_support_confirmed_by: str | None = None
    carried_from_version: int | None = None


class VersionBody(BaseModel):
    version: int
    reason: str
    created_by: str
    intake: PilotIntake
    playbook: Playbook
    playbook_hash: str
    assessment: LegalOpsAssessment
    assessed_content_hash: str
    routing: ParentRouting
    required_final_tier: str
    required_specialties: list[str]
    scope_exclusions: list[str]
    coverage_problems: list[str]
    document_readable: bool
    document_problem: str | None = None
    missing_facts: list[str] = Field(default_factory=list)


@dataclass
class _Ctx:
    connection: sqlite3.Connection
    actor: Actor
    matter: sqlite3.Row
    body: VersionBody
    version_row: sqlite3.Row
    stamp: Stamp
    now: str
    new_state: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def matter_id(self) -> str:
        return str(self.matter["matter_id"])

    @property
    def version(self) -> int:
        return int(self.matter["current_version"])


def compute_content_hash(intake: PilotIntake, playbook_hash: str, document_sha256: str) -> str:
    payload = canonical(
        {
            "intake": intake.model_dump(mode="json"),
            "playbook_hash": playbook_hash,
            "document_sha256": document_sha256,
        }
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def compute_review_hash(
    content_hash: str, changes: list[StoredChange], comments: list[Comment]
) -> str:
    payload = canonical(
        {
            "content_hash": content_hash,
            "changes": sorted((c.id, c.decision, c.final_text) for c in changes),
            "comments": sorted((c.comment_id, c.state, c.severity) for c in comments),
        }
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _require_text(value: str | None, minimum: int, label: str) -> str:
    text = " ".join((value or "").split())
    if len(text) < minimum:
        raise InvalidCommandError(f"{label} must be at least {minimum} characters")
    return text


def _check_evidence_refs(refs: list[str]) -> list[str]:
    cleaned = [ref.strip() for ref in refs if ref.strip()]
    blocked = [r.source_ref for r in verify_source_refs(cleaned) if r.status == "blocker"]
    if cleaned and blocked:
        raise InvalidCommandError(
            f"blocked evidence reference cannot be recorded: {', '.join(blocked)}"
        )
    return cleaned


class PilotService:
    def __init__(
        self,
        store: PilotStore,
        *,
        clock: Clock | None = None,
        export_root: Path | None = None,
    ) -> None:
        self.store = store
        self.clock = clock or SystemClock()
        configured = os.environ.get("PILOT_EXPORT_ROOT")
        self.export_root = export_root or (
            Path(configured) if configured else store.path.parent / "exports"
        )

    # ------------------------------------------------------------------ actors

    def register_actor(self, actor: Actor) -> Actor:
        with self.store.transaction() as connection:
            connection.execute(
                "INSERT INTO actors (actor_id, body) VALUES (?, ?) "
                "ON CONFLICT(actor_id) DO UPDATE SET body = excluded.body",
                (actor.actor_id, actor.model_dump_json()),
            )
        return actor

    def complete_onboarding(self, actor_id: str, completed_tasks: list[str]) -> Actor:
        """Mark an actor ready once every onboarding task of the role is acknowledged."""

        with self.store.transaction() as connection:
            actor = self._actor(connection, actor_id)
            missing = missing_tasks(actor.role, completed_tasks)
            if missing:
                raise InvalidCommandError(f"onboarding tasks still open: {', '.join(missing)}")
            actor = actor.model_copy(update={"onboarded": True})
            connection.execute(
                "UPDATE actors SET body = ? WHERE actor_id = ?",
                (actor.model_dump_json(), actor_id),
            )
        return actor

    def list_actors(self) -> list[Actor]:
        with self.store.reading() as connection:
            rows = connection.execute("SELECT body FROM actors ORDER BY actor_id").fetchall()
        return [Actor.model_validate_json(row["body"]) for row in rows]

    @staticmethod
    def _actor(connection: sqlite3.Connection, actor_id: str) -> Actor:
        row = connection.execute(
            "SELECT body FROM actors WHERE actor_id = ?", (actor_id,)
        ).fetchone()
        if row is None:
            raise PermissionDeniedError(
                f"unknown actor {actor_id!r}: a supplied name is not an identity"
            )
        return Actor.model_validate_json(row["body"])

    # ------------------------------------------------------------- loading

    @staticmethod
    def _matter(connection: sqlite3.Connection, matter_id: str) -> sqlite3.Row:
        row = connection.execute(
            "SELECT * FROM matters WHERE matter_id = ?", (matter_id,)
        ).fetchone()
        if row is None:
            raise NotFoundError(f"unknown matter {matter_id}")
        return row

    @staticmethod
    def _version(
        connection: sqlite3.Connection, matter_id: str, version: int
    ) -> tuple[VersionBody, sqlite3.Row]:
        row = connection.execute(
            "SELECT * FROM matter_versions WHERE matter_id = ? AND version = ?",
            (matter_id, version),
        ).fetchone()
        if row is None:
            raise NotFoundError(f"matter {matter_id} has no version {version}")
        return VersionBody.model_validate_json(row["body"]), row

    @staticmethod
    def _assigned(connection: sqlite3.Connection, matter_id: str) -> dict[str, list[str]]:
        assigned: dict[str, list[str]] = {}
        for row in connection.execute(
            "SELECT role, actor_id FROM assignments WHERE matter_id = ? ORDER BY assigned_at, actor_id",
            (matter_id,),
        ):
            assigned.setdefault(row["role"], []).append(row["actor_id"])
        return assigned

    @staticmethod
    def _changes(
        connection: sqlite3.Connection, matter_id: str, version: int
    ) -> list[StoredChange]:
        rows = connection.execute(
            "SELECT body FROM changes WHERE matter_id = ? AND version = ? ORDER BY position",
            (matter_id, version),
        ).fetchall()
        return [StoredChange.model_validate_json(row["body"]) for row in rows]

    @staticmethod
    def _findings(connection: sqlite3.Connection, matter_id: str, version: int) -> list[Finding]:
        rows = connection.execute(
            "SELECT body FROM findings WHERE matter_id = ? AND version = ? ORDER BY finding_key",
            (matter_id, version),
        ).fetchall()
        return [Finding.model_validate_json(row["body"]) for row in rows]

    @staticmethod
    def _comments(connection: sqlite3.Connection, matter_id: str) -> list[Comment]:
        rows = connection.execute(
            "SELECT body FROM comments WHERE matter_id = ? ORDER BY rowid", (matter_id,)
        ).fetchall()
        return [Comment.model_validate_json(row["body"]) for row in rows]

    @staticmethod
    def _save_comment(connection: sqlite3.Connection, comment: Comment) -> None:
        connection.execute(
            "INSERT INTO comments (comment_id, matter_id, body) VALUES (?, ?, ?) "
            "ON CONFLICT(comment_id) DO UPDATE SET body = excluded.body",
            (comment.comment_id, comment.matter_id, comment.model_dump_json()),
        )

    @staticmethod
    def _save_change(
        connection: sqlite3.Connection, matter_id: str, version: int, change: StoredChange
    ) -> None:
        connection.execute(
            "UPDATE changes SET body = ? WHERE matter_id = ? AND version = ? AND change_id = ?",
            (change.model_dump_json(), matter_id, version, change.id),
        )

    def _save_body(self, ctx: _Ctx) -> None:
        ctx.connection.execute(
            "UPDATE matter_versions SET body = ? WHERE matter_id = ? AND version = ?",
            (ctx.body.model_dump_json(), ctx.matter_id, ctx.version),
        )

    def _current_content_hash(self, body: VersionBody, row: sqlite3.Row) -> str:
        """Recompute the content hash from what is stored now, not what was recorded."""

        document_sha256 = hashlib.sha256(row["document_blob"]).hexdigest()
        return compute_content_hash(body.intake, body.playbook.content_hash(), document_sha256)

    def _review_hash(self, ctx: _Ctx) -> str:
        return compute_review_hash(
            self._current_content_hash(ctx.body, ctx.version_row),
            self._changes(ctx.connection, ctx.matter_id, ctx.version),
            self._comments(ctx.connection, ctx.matter_id),
        )

    # --------------------------------------------------------- access control

    def _require_access(self, ctx: _Ctx, roles: tuple[Role, ...]) -> None:
        """Role check plus per-matter assignment check. Role alone grants nothing."""

        actor = ctx.actor
        if actor.role not in roles:
            raise PermissionDeniedError(
                f"{actor.actor_id} holds the simulated role {actor.role}; this action needs "
                f"one of: {', '.join(roles)}"
            )
        assigned = self._assigned(ctx.connection, ctx.matter_id)
        if actor.actor_id not in assigned.get(actor.role, []):
            raise PermissionDeniedError(
                f"{actor.actor_id} is not assigned to matter {ctx.matter_id} as {actor.role}"
            )

    def _can_read(self, connection: sqlite3.Connection, actor: Actor, matter: sqlite3.Row) -> bool:
        assigned = self._assigned(connection, matter["matter_id"])
        if actor.actor_id in assigned.get(actor.role, []):
            return True
        # The triage queue: an unclaimed matter is visible to onboarded matter owners.
        return (
            actor.role == "matter_owner"
            and actor.onboarded
            and matter["state"] == "triage"
            and not assigned.get("matter_owner")
        )

    # ------------------------------------------------------------- versions

    def _build_version(
        self,
        connection: sqlite3.Connection,
        *,
        matter_id: str,
        version: int,
        intake: PilotIntake,
        document_name: str,
        document: bytes,
        playbook: Playbook,
        created_by: str,
        reason: str,
        now: str,
    ) -> tuple[VersionBody, float]:
        """Assess, route and propose changes for one immutable matter version."""

        started = time.perf_counter()
        assessment = assess_matter(intake.matter)
        routing = route(matter_id, intake)
        blocked_sources = [s for s in assessment.source_verifications if s.status == "blocker"]
        index: DocumentIndex | None = None
        document_problem: str | None = None
        try:
            index = index_docx(document)
        except UnsupportedDocumentError as error:
            document_problem = str(error)
        changes: list[DocumentChange] = []
        findings = [
            Finding(
                key=f"asm-{item.category}",
                origin="assessment",
                category=item.category,
                severity=item.severity,
                summary=item.summary,
                evidence=item.evidence,
                recommended_action=item.recommended_action,
            )
            for item in assessment.findings
        ]
        problems: list[str] = []
        specialties: set[str] = set()
        if blocked_sources:
            # Existing rule: blocked source prefixes stop document processing.
            problems.append("document processing withheld: a blocked source reference is present")
        elif index is not None:
            proposal = propose_changes(index, playbook)
            changes, problems = proposal.changes, proposal.problems
            for deviation in proposal.deviations:
                if deviation.specialist_role:
                    specialties.add(deviation.specialist_role)
                findings.append(
                    Finding(
                        key=deviation.key,
                        origin="playbook",
                        category=deviation.category,
                        severity=deviation.severity,
                        summary=deviation.summary,
                        evidence=deviation.evidence,
                        recommended_action=(
                            f"Standard: {deviation.standard_position} "
                            f"Fallback: {deviation.fallback_position}"
                        ),
                        locator=deviation.locator,
                        change_id=deviation.change_id,
                        specialist_role=deviation.specialist_role,
                    )
                )
        playbook_hash = playbook.content_hash()
        document_sha256 = hashlib.sha256(document).hexdigest()
        content_hash = compute_content_hash(intake, playbook_hash, document_sha256)
        body = VersionBody(
            version=version,
            reason=reason,
            created_by=created_by,
            intake=intake,
            playbook=playbook,
            playbook_hash=playbook_hash,
            assessment=assessment,
            assessed_content_hash=content_hash,
            routing=routing,
            required_final_tier=required_approval_tier(routing),
            required_specialties=sorted(specialties),
            scope_exclusions=pilot_scope_exclusions(routing, intake),
            coverage_problems=problems,
            document_readable=index is not None,
            document_problem=document_problem,
            missing_facts=[key for key in REQUIRED_FACTS if not intake.facts.get(key, "").strip()],
        )
        system_ms = round((time.perf_counter() - started) * 1000, 3)
        connection.execute(
            "INSERT INTO matter_versions (matter_id, version, content_hash, document_name, "
            "document_sha256, document_blob, body, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                matter_id,
                version,
                content_hash,
                document_name,
                document_sha256,
                document,
                body.model_dump_json(),
                now,
            ),
        )
        for finding in findings:
            connection.execute(
                "INSERT INTO findings (matter_id, version, finding_key, body) VALUES (?, ?, ?, ?)",
                (matter_id, version, finding.key, finding.model_dump_json()),
            )
        previous = (
            {c.id: c for c in self._changes(connection, matter_id, version - 1)}
            if version > 1
            else {}
        )
        for position, change in enumerate(changes):
            rule = playbook.rule(change.rule_id or "")
            stored = StoredChange(
                **change.model_dump(), specialist_role=rule.specialist_role if rule else None
            )
            earlier = previous.get(stored.id)
            # A decision survives regeneration only when the clause, the proposal and
            # the original wording are all unchanged. Sign-offs never survive.
            if (
                earlier is not None
                and earlier.decision in {"accepted", "rejected", "amended"}
                and earlier.original_text == stored.original_text
                and earlier.proposed_text == stored.proposed_text
            ):
                stored = earlier.model_copy(
                    update={
                        "anchor": stored.anchor,
                        "locator": stored.locator,
                        "source_refs": stored.source_refs,
                        "carried_from_version": earlier.carried_from_version or version - 1,
                    }
                )
            connection.execute(
                "INSERT INTO changes (matter_id, version, change_id, position, body) "
                "VALUES (?, ?, ?, ?, ?)",
                (matter_id, version, stored.id, position, stored.model_dump_json()),
            )
        self._carry_comments(
            connection, matter_id, version, findings, changes, index, problems, now
        )
        return body, system_ms

    def _carry_comments(
        self,
        connection: sqlite3.Connection,
        matter_id: str,
        version: int,
        findings: list[Finding],
        changes: list[DocumentChange],
        index: DocumentIndex | None,
        problems: list[str],
        now: str,
    ) -> None:
        """Keep every comment across regeneration and record coverage gaps.

        A comment whose anchor no longer exists is marked orphaned. It is never
        deleted and never resolved automatically, so an open critical comment keeps
        blocking until a person resolves it.
        """

        anchors = {
            "finding": {finding.key for finding in findings},
            "change": {change.id for change in changes},
            "deliverable_section": set(DELIVERABLE_SECTIONS),
            "source_span": {f"para:{p.text_hash}" for p in (index.paragraphs if index else ())}
            | {f"coverage:{hashlib.sha256(p.encode()).hexdigest()[:12]}" for p in problems},
        }
        existing = {c.comment_id: c for c in self._comments(connection, matter_id)}
        for comment in existing.values():
            status = "current" if comment.anchor_id in anchors[comment.anchor_kind] else "orphaned"
            if status != comment.anchor_status:
                self._save_comment(connection, comment.model_copy(update={"anchor_status": status}))
        for problem in problems:
            digest = hashlib.sha256(problem.encode()).hexdigest()[:12]
            comment_id = f"cov-{digest}"
            if comment_id in existing:
                continue
            self._save_comment(
                connection,
                Comment(
                    comment_id=comment_id,
                    matter_id=matter_id,
                    kind="coverage_gap",
                    anchor_kind="source_span",
                    anchor_id=f"coverage:{digest}",
                    anchor_excerpt=problem,
                    created_on_version=version,
                    author_id=SYSTEM_ACTOR_ID,
                    author_role="system",
                    severity="critical",
                    body=(
                        f"{problem}. Record how this content was reviewed by a person "
                        "before the matter is approved."
                    ),
                    created_at=now,
                ),
            )

    # ---------------------------------------------------------------- evidence

    def _evidence(self, ctx: _Ctx, names: tuple[str, ...]) -> list[dict[str, Any]]:
        results = []
        for name in names:
            ok, detail = getattr(self, f"_ev_{name}")(ctx)
            results.append(
                {"name": name, "ok": ok, "detail": detail, "requirement": EVIDENCE[name]}
            )
        return results

    def _ev_intake_complete(self, ctx: _Ctx) -> tuple[bool, str]:
        problems = [f"missing fact: {key}" for key in ctx.body.missing_facts]
        if not ctx.body.intake.instructions.strip():
            problems.append("missing instructions")
        if not ctx.body.document_readable:
            problems.append(f"source document unreadable: {ctx.body.document_problem}")
        return (not problems, "; ".join(problems) or "all required intake fields present")

    def _ev_assessment_current(self, ctx: _Ctx) -> tuple[bool, str]:
        current = self._current_content_hash(ctx.body, ctx.version_row)
        if ctx.body.assessed_content_hash != current:
            return False, "stored matter content differs from the assessed content; reassess"
        return True, f"assessment {ctx.body.assessment.assessment_id} covers version {ctx.version}"

    def _ev_sources_usable(self, ctx: _Ctx) -> tuple[bool, str]:
        unusable = [
            f"{s.source_ref.split(':', 1)[0]}: ({s.status})"
            for s in ctx.body.assessment.source_verifications
            if s.status != "pass"
        ]
        return (not unusable, "; ".join(unusable) or "all source references pass the boundary")

    def _ev_pilot_scope_met(self, ctx: _Ctx) -> tuple[bool, str]:
        exclusions = ctx.body.scope_exclusions
        return (not exclusions, "; ".join(exclusions) or "inside the pilot charter")

    def _ev_decision_authority_agreed(self, ctx: _Ctx) -> tuple[bool, str]:
        held, required = ctx.body.intake.decision_authority, ctx.body.required_final_tier
        if not held:
            return False, f"no decision authority recorded; the matter needs {required}"
        if not tier_covers(held, required):
            return False, f"recorded authority {held} does not cover the required {required}"
        return True, f"decision authority {held} covers {required}"

    def _ev_reviewers_available(self, ctx: _Ctx) -> tuple[bool, str]:
        assigned = self._assigned(ctx.connection, ctx.matter_id)
        actors = {
            actor_id: self._actor(ctx.connection, actor_id)
            for ids in assigned.values()
            for actor_id in ids
        }
        problems: list[str] = []
        for role in ("matter_owner", "final_approver"):
            if not assigned.get(role):
                problems.append(f"no {role} assigned")
        approvers = [actors[a] for a in assigned.get("final_approver", [])]
        if approvers and not any(
            tier_covers(a.approval_tier, ctx.body.required_final_tier) for a in approvers
        ):
            problems.append(
                f"assigned final approver does not hold tier {ctx.body.required_final_tier}"
            )
        specialists = [actors[a] for a in assigned.get("specialist_reviewer", [])]
        for specialty in ctx.body.required_specialties:
            if not any(s.specialty == specialty for s in specialists):
                problems.append(f"no specialist reviewer for {specialty}")
        for actor in actors.values():
            if not actor.onboarded:
                problems.append(f"{actor.actor_id} has not completed onboarding")
            if not actor.available:
                problems.append(f"{actor.actor_id} is marked unavailable")
        return (not problems, "; ".join(problems) or "all required reviewers assigned and ready")

    def _ev_revision_reason_recorded(self, ctx: _Ctx) -> tuple[bool, str]:
        comment_ids = ctx.extra.get("comment_ids") or []
        open_ids = {
            c.comment_id for c in self._comments(ctx.connection, ctx.matter_id) if c.state == "open"
        }
        unknown = [c for c in comment_ids if c not in open_ids]
        if not comment_ids:
            return False, "a revision request must name at least one open comment"
        if unknown:
            return False, f"not an open comment on this matter: {', '.join(unknown)}"
        return True, f"{len(comment_ids)} open comment(s) named"

    def _ev_revision_addressed(self, ctx: _Ctx) -> tuple[bool, str]:
        request = ctx.connection.execute(
            "SELECT payload, created_at FROM decisions WHERE matter_id = ? AND kind = "
            "'revision_request' ORDER BY decision_id DESC LIMIT 1",
            (ctx.matter_id,),
        ).fetchone()
        if request is None:
            return False, "no revision request on record"
        named = set(json.loads(request["payload"]).get("comment_ids", []))
        owners = set(self._assigned(ctx.connection, ctx.matter_id).get("matter_owner", []))
        pending = [
            c.comment_id
            for c in self._comments(ctx.connection, ctx.matter_id)
            if c.comment_id in named
            and c.state == "open"
            and not any(
                r.author_id in owners and r.created_at >= request["created_at"] for r in c.responses
            )
        ]
        return (
            not pending,
            (
                f"no matter-owner response yet on: {', '.join(pending)}"
                if pending
                else "every named comment has a matter-owner response"
            ),
        )

    def _ev_changes_decided(self, ctx: _Ctx) -> tuple[bool, str]:
        undecided = [
            c.id
            for c in self._changes(ctx.connection, ctx.matter_id, ctx.version)
            if c.decision not in {"accepted", "rejected", "amended"}
        ]
        return (not undecided, f"undecided: {', '.join(undecided)}" if undecided else "all decided")

    def _ev_no_open_blockers(self, ctx: _Ctx) -> tuple[bool, str]:
        blocking = [
            f"{c.comment_id} ({c.kind}, {c.anchor_status})"
            for c in self._comments(ctx.connection, ctx.matter_id)
            if c.blocking
        ]
        return (not blocking, "open: " + ", ".join(blocking) if blocking else "none open")

    def _ev_specialist_signoffs_current(self, ctx: _Ctx) -> tuple[bool, str]:
        missing = [
            d.requirement
            for d in self._required_decisions(ctx)
            if d.requirement.startswith("specialist_signoff")
            and (
                d.actor_id is None
                or d.invalidated
                or d.version != ctx.version
                or d.content_hash != self._current_content_hash(ctx.body, ctx.version_row)
            )
        ]
        return (
            not missing,
            "missing or stale: " + ", ".join(missing) if missing else "all current",
        )

    def _ev_approver_authorised(self, ctx: _Ctx) -> tuple[bool, str]:
        actor, required = ctx.actor, ctx.body.required_final_tier
        if not tier_covers(actor.approval_tier, required):
            return False, f"{actor.actor_id} holds tier {actor.approval_tier}, {required} required"
        assigned = self._assigned(ctx.connection, ctx.matter_id)
        others = set(assigned.get("business_requester", [])) | set(assigned.get("matter_owner", []))
        if actor.actor_id in others:
            return False, "the approver is also requester or matter owner on this matter"
        deciders = {c.decided_by for c in self._changes(ctx.connection, ctx.matter_id, ctx.version)}
        if actor.actor_id in deciders:
            return False, "the approver decided a change on this matter"
        return True, f"{actor.actor_id} holds tier {actor.approval_tier}"

    def _ev_export_gate_passes(self, ctx: _Ctx) -> tuple[bool, str]:
        eligibility = self._eligibility(ctx, "delivery_package")
        return (eligibility.eligible, "; ".join(eligibility.reasons()) or "eligible")

    def _ev_delivery_manifest_current(self, ctx: _Ctx) -> tuple[bool, str]:
        manifest = ctx.connection.execute(
            "SELECT * FROM deliverable_manifests WHERE matter_id = ? AND kind = "
            "'delivery_package' ORDER BY manifest_id DESC LIMIT 1",
            (ctx.matter_id,),
        ).fetchone()
        if manifest is None:
            return False, "no delivery package has been prepared"
        if manifest["version"] != ctx.version or manifest["review_hash"] != self._review_hash(ctx):
            return False, "the delivery package was prepared for an earlier reviewed state"
        eligibility = self._eligibility(ctx, "delivery_package")
        if not eligibility.eligible:
            return False, "; ".join(eligibility.reasons())
        return True, f"delivery manifest {manifest['manifest_id']} matches version {ctx.version}"

    def _ev_acceptance_recorded(self, ctx: _Ctx) -> tuple[bool, str]:
        note = " ".join(str(ctx.extra.get("note") or "").split())
        return (
            len(note) >= 20,
            "acceptance note recorded" if len(note) >= 20 else "note too short",
        )

    # ------------------------------------------------------------- eligibility

    def _required_decisions(self, ctx: _Ctx) -> list[RequiredDecision]:
        assigned = self._assigned(ctx.connection, ctx.matter_id)
        rows = ctx.connection.execute(
            "SELECT * FROM decisions WHERE matter_id = ? AND kind IN "
            "('specialist_signoff', 'final_approval') ORDER BY decision_id DESC",
            (ctx.matter_id,),
        ).fetchall()

        def latest(kind: str, accept) -> sqlite3.Row | None:
            for row in rows:
                if row["kind"] != kind:
                    continue
                actor = self._actor(ctx.connection, row["actor_id"])
                # A decision only counts while its author is still assigned in that role.
                if actor.actor_id in assigned.get(actor.role, []) and accept(actor):
                    return row
            return None

        def as_required(requirement: str, row: sqlite3.Row | None, binds: bool) -> RequiredDecision:
            if row is None:
                return RequiredDecision(requirement=requirement, binds_review_hash=binds)
            return RequiredDecision(
                requirement=requirement,
                binds_review_hash=binds,
                actor_id=row["actor_id"],
                version=row["version"],
                content_hash=row["content_hash"],
                review_hash=row["review_hash"],
                invalidated=row["invalidated_at"] is not None,
            )

        required = [
            as_required(
                f"specialist_signoff:{specialty}",
                latest("specialist_signoff", lambda a, s=specialty: a.specialty == s),
                False,
            )
            for specialty in ctx.body.required_specialties
        ]
        tier = ctx.body.required_final_tier
        required.append(
            as_required(
                f"final_approval:{tier}",
                latest("final_approval", lambda a: tier_covers(a.approval_tier, tier)),
                True,
            )
        )
        return required

    def _eligibility(self, ctx: _Ctx, kind: ExportKind) -> ExportEligibility:
        """Build the gate context from stored data and run the single check."""

        body, row = ctx.body, ctx.version_row
        comments = self._comments(ctx.connection, ctx.matter_id)
        changes = self._changes(ctx.connection, ctx.matter_id, ctx.version)
        open_items = [
            f"{c.kind} {c.comment_id} on {c.anchor_kind} {c.anchor_id} ({c.anchor_status})"
            for c in comments
            if c.blocking
        ]
        open_items += [f"hold: {reason}" for reason in body.scope_exclusions]
        open_items += [
            f"hold: source {s.source_ref.split(':', 1)[0]}: requires review"
            for s in body.assessment.source_verifications
            if s.status == "warning"
        ]
        current_hash = self._current_content_hash(body, row)
        context = ExportContext(
            kind=kind,
            assessment=body.assessment,
            change_set_assessment_id=body.assessment.assessment_id,
            recorded_document_sha256=row["document_sha256"],
            actual_document_sha256=hashlib.sha256(row["document_blob"]).hexdigest(),
            change_decisions={c.id: c.decision for c in changes},
            stateful=StatefulContext(
                matter_id=ctx.matter_id,
                matter_state=ctx.matter["state"],
                current_version=ctx.version,
                current_content_hash=current_hash,
                assessment_version=body.version,
                assessment_content_hash=body.assessed_content_hash,
                current_review_hash=compute_review_hash(current_hash, changes, comments),
                open_blocking_items=open_items,
                required_decisions=self._required_decisions(ctx),
                matter_chain=self.store.verify_chain(ctx.connection, ctx.matter_id),
            ),
        )
        return evaluate_export_eligibility(context)

    def export_eligibility(
        self, actor_id: str, matter_id: str, kind: ExportKind
    ) -> ExportEligibility:
        with self.store.reading() as connection:
            ctx = self._context(connection, actor_id, matter_id, Stamp())
            if not self._can_read(connection, ctx.actor, ctx.matter):
                raise PermissionDeniedError(f"{actor_id} has no access to matter {matter_id}")
            return self._eligibility(ctx, kind)

    # ------------------------------------------------------- command plumbing

    def _context(
        self, connection: sqlite3.Connection, actor_id: str, matter_id: str, stamp: Stamp
    ) -> _Ctx:
        actor = self._actor(connection, actor_id)
        matter = self._matter(connection, matter_id)
        body, row = self._version(connection, matter_id, matter["current_version"])
        return _Ctx(connection, actor, matter, body, row, stamp, self.clock.now())

    def _event(
        self,
        ctx: _Ctx,
        event_type: str,
        note: str,
        payload: dict[str, Any] | None = None,
        system_ms: float | None = None,
    ) -> None:
        self.store.append_event(
            ctx.connection,
            matter_id=ctx.matter_id,
            event_type=event_type,
            actor_id=ctx.actor.actor_id,
            role=ctx.actor.role,
            note=note,
            occurred_at=ctx.now,
            payload={"version": ctx.version, **(payload or {})},
            fixture_at=ctx.stamp.fixture_at,
            effort_minutes=ctx.stamp.effort_minutes,
            system_ms=system_ms,
        )

    def _decision(
        self,
        ctx: _Ctx,
        kind: str,
        outcome: str,
        note: str,
        *,
        target_id: str | None = None,
        payload: dict[str, Any] | None = None,
        bind_review: bool = False,
    ) -> None:
        ctx.connection.execute(
            "INSERT INTO decisions (matter_id, version, content_hash, review_hash, kind, target_id, "
            "actor_id, role, outcome, note, payload, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                ctx.matter_id,
                ctx.version,
                self._current_content_hash(ctx.body, ctx.version_row),
                self._review_hash(ctx) if bind_review else None,
                kind,
                target_id,
                ctx.actor.actor_id,
                ctx.actor.role,
                outcome,
                note,
                canonical(payload or {}),
                ctx.now,
            ),
        )

    def _invalidate(self, ctx: _Ctx, kinds: tuple[str, ...], reason: str) -> int:
        marks = ",".join("?" for _ in kinds)
        cursor = ctx.connection.execute(
            f"UPDATE decisions SET invalidated_at = ?, invalidated_reason = ? WHERE matter_id = ? "
            f"AND invalidated_at IS NULL AND kind IN ({marks})",
            (ctx.now, reason, ctx.matter_id, *kinds),
        )
        return cursor.rowcount

    def _transition(self, ctx: _Ctx, command: str) -> str:
        transition = find_transition(ctx.matter["state"], command)
        if transition is None:
            raise TransitionBlockedError(
                command,
                [
                    {
                        "name": "state",
                        "ok": False,
                        "detail": f"{command} is not allowed from state {ctx.matter['state']}",
                    }
                ],
            )
        if command != "complete_triage":
            self._require_access(ctx, transition.roles)
        else:
            owners = self._assigned(ctx.connection, ctx.matter_id).get("matter_owner", [])
            claimable = not owners or ctx.actor.actor_id in owners
            if ctx.actor.role != "matter_owner" or not ctx.actor.onboarded or not claimable:
                raise PermissionDeniedError(
                    f"{ctx.actor.actor_id} cannot triage matter {ctx.matter_id}: only an "
                    "onboarded matter owner may claim an unassigned matter"
                )
        ctx.new_state = transition.target
        evidence = self._evidence(ctx, transition.evidence)
        if not all(item["ok"] for item in evidence):
            raise TransitionBlockedError(command, evidence)
        return transition.target

    def _execute(
        self,
        actor_id: str,
        matter_id: str,
        expected_revision: int,
        command: str,
        handler,
        stamp: Stamp | None,
    ) -> dict[str, Any]:
        try:
            with self.store.transaction() as connection:
                ctx = self._context(connection, actor_id, matter_id, stamp or Stamp())
                if ctx.matter["state"] == "closed":
                    raise TransitionBlockedError(
                        command, [{"name": "state", "ok": False, "detail": "the matter is closed"}]
                    )
                assigned = self._assigned(connection, matter_id)
                on_matter = any(ctx.actor.actor_id in ids for ids in assigned.values())
                # Claiming an unassigned matter at triage is the only action open to
                # someone who is not yet on the matter.
                if not on_matter and command != "complete_triage":
                    raise PermissionDeniedError(
                        f"{ctx.actor.actor_id} is not assigned to matter {matter_id}"
                    )
                if ctx.matter["revision"] != expected_revision:
                    raise StaleSubmissionError(expected_revision, ctx.matter["revision"])
                handler(ctx)
                connection.execute(
                    "UPDATE matters SET revision = revision + 1, updated_at = ?, state = ?, "
                    "current_version = ?, closed_outcome = ? WHERE matter_id = ?",
                    (
                        ctx.now,
                        ctx.new_state or ctx.matter["state"],
                        ctx.extra.get("current_version", ctx.version),
                        ctx.extra.get("closed_outcome", ctx.matter["closed_outcome"]),
                        matter_id,
                    ),
                )
        except (TransitionBlockedError, PermissionDeniedError, ExportBlockedError) as error:
            self._record_refusal(actor_id, matter_id, command, error, stamp or Stamp())
            raise
        return self.view_matter(actor_id, matter_id)

    def _record_refusal(
        self, actor_id: str, matter_id: str, command: str, error: Exception, stamp: Stamp
    ) -> None:
        """Log a refused command on the matter's chain without changing the matter."""

        with self.store.transaction() as connection:
            if (
                connection.execute(
                    "SELECT 1 FROM matters WHERE matter_id = ?", (matter_id,)
                ).fetchone()
                is None
            ):
                return
            known = connection.execute(
                "SELECT body FROM actors WHERE actor_id = ?", (actor_id,)
            ).fetchone()
            role = Actor.model_validate_json(known["body"]).role if known else "unverified"
            self.store.append_event(
                connection,
                matter_id=matter_id,
                event_type="command_refused",
                actor_id=actor_id[:80],
                role=role,
                note=str(error)[:500],
                occurred_at=self.clock.now(),
                payload={"command": command, "error": type(error).__name__},
                fixture_at=stamp.fixture_at,
            )

    # ---------------------------------------------------------------- commands

    def create_matter(
        self,
        actor_id: str,
        intake: PilotIntake,
        document_name: str,
        document: bytes,
        *,
        matter_id: str | None = None,
        playbook: Playbook | None = None,
        stamp: Stamp | None = None,
    ) -> dict[str, Any]:
        stamp = stamp or Stamp()
        with self.store.transaction() as connection:
            actor = self._actor(connection, actor_id)
            if actor.role != "business_requester":
                raise PermissionDeniedError("only a business requester may open a matter")
            now = self.clock.now()
            digest = hashlib.sha256((intake.matter.title + now).encode()).hexdigest()[:8]
            matter_id = matter_id or f"PM-{digest.upper()}"
            if connection.execute(
                "SELECT 1 FROM matters WHERE matter_id = ?", (matter_id,)
            ).fetchone():
                raise InvalidCommandError(f"matter {matter_id} already exists")
            connection.execute(
                "INSERT INTO matters (matter_id, title, state, current_version, revision, "
                "created_at, updated_at) VALUES (?, ?, 'intake', 1, 1, ?, ?)",
                (matter_id, intake.matter.title, now, now),
            )
            connection.execute(
                "INSERT INTO assignments (matter_id, role, actor_id, assigned_by, assigned_at) "
                "VALUES (?, 'business_requester', ?, ?, ?)",
                (matter_id, actor_id, actor_id, now),
            )
            body, system_ms = self._build_version(
                connection,
                matter_id=matter_id,
                version=1,
                intake=intake,
                document_name=document_name,
                document=document,
                playbook=playbook or load_playbook(),
                created_by=actor_id,
                reason="initial intake",
                now=now,
            )
            self.store.append_event(
                connection,
                matter_id=matter_id,
                event_type="matter_created",
                actor_id=actor_id,
                role=actor.role,
                note="Matter opened; assessment, parent routing and playbook proposals generated.",
                occurred_at=now,
                payload={
                    "version": 1,
                    "required_facts": len(REQUIRED_FACTS),
                    "missing_facts": body.missing_facts,
                },
                fixture_at=stamp.fixture_at,
                effort_minutes=stamp.effort_minutes,
                system_ms=system_ms,
            )
        return self.view_matter(actor_id, matter_id)

    def submit_intake(self, actor_id, matter_id, expected_revision, *, stamp=None):
        def handler(ctx: _Ctx) -> None:
            self._transition(ctx, "submit_intake")
            self._event(ctx, "intake_submitted", "Intake submitted for triage.")

        return self._execute(
            actor_id, matter_id, expected_revision, "submit_intake", handler, stamp
        )

    def complete_triage(self, actor_id, matter_id, expected_revision, *, stamp=None):
        def handler(ctx: _Ctx) -> None:
            self._transition(ctx, "complete_triage")
            ctx.connection.execute(
                "INSERT OR IGNORE INTO assignments VALUES (?, 'matter_owner', ?, ?, ?)",
                (ctx.matter_id, ctx.actor.actor_id, ctx.actor.actor_id, ctx.now),
            )
            self._event(
                ctx,
                "triage_completed",
                "Triage confirmed; matter owner claimed the matter.",
                {
                    "queue": ctx.body.routing.queue,
                    "required_final_tier": ctx.body.required_final_tier,
                    "required_specialties": ctx.body.required_specialties,
                },
            )

        return self._execute(
            actor_id, matter_id, expected_revision, "complete_triage", handler, stamp
        )

    def assign(self, actor_id, matter_id, expected_revision, *, role, assignee_id, stamp=None):
        def handler(ctx: _Ctx) -> None:
            self._require_access(ctx, ("matter_owner",))
            if ctx.matter["state"] in {"intake", "triage"}:
                raise InvalidCommandError("reviewers are assigned after triage")
            if role not in {"specialist_reviewer", "final_approver"}:
                raise InvalidCommandError(
                    "only specialist reviewers and final approvers are assigned"
                )
            assignee = self._actor(ctx.connection, assignee_id)
            if assignee.role != role:
                raise InvalidCommandError(f"{assignee_id} holds role {assignee.role}, not {role}")
            if role == "final_approver":
                ctx.connection.execute(
                    "DELETE FROM assignments WHERE matter_id = ? AND role = 'final_approver'",
                    (ctx.matter_id,),
                )
            ctx.connection.execute(
                "INSERT OR IGNORE INTO assignments VALUES (?, ?, ?, ?, ?)",
                (ctx.matter_id, role, assignee_id, ctx.actor.actor_id, ctx.now),
            )
            self._event(
                ctx,
                "reviewer_assigned",
                f"{assignee_id} assigned as {role}.",
                {"role": role, "assignee": assignee_id},
            )

        return self._execute(actor_id, matter_id, expected_revision, "assign", handler, stamp)

    def start_review(self, actor_id, matter_id, expected_revision, *, stamp=None):
        def handler(ctx: _Ctx) -> None:
            self._transition(ctx, "start_review")
            self._event(ctx, "review_started", "Readiness check passed; review opened.")

        return self._execute(actor_id, matter_id, expected_revision, "start_review", handler, stamp)

    def comment(
        self,
        actor_id,
        matter_id,
        expected_revision,
        *,
        anchor_kind,
        anchor_id,
        body,
        severity="note",
        stamp=None,
    ):
        def handler(ctx: _Ctx) -> None:
            self._require_access(ctx, REVIEW_ROLES)
            if ctx.matter["state"] not in COMMENT_STATES:
                raise InvalidCommandError(f"comments are not open in state {ctx.matter['state']}")
            excerpt = self._anchor_excerpt(ctx, anchor_kind, anchor_id)
            sequence = len(self._comments(ctx.connection, ctx.matter_id)) + 1
            comment = Comment(
                comment_id=f"c-{sequence:03d}",
                matter_id=ctx.matter_id,
                anchor_kind=anchor_kind,
                anchor_id=anchor_id,
                anchor_excerpt=excerpt,
                created_on_version=ctx.version,
                author_id=ctx.actor.actor_id,
                author_role=ctx.actor.role,
                severity=severity,
                body=_require_text(body, 10, "comment body"),
                created_at=ctx.now,
            )
            self._save_comment(ctx.connection, comment)
            self._event(
                ctx,
                "comment_added",
                f"{severity} comment on {anchor_kind} {anchor_id}.",
                {"comment_id": comment.comment_id, "severity": severity},
            )

        try:
            return self._execute(actor_id, matter_id, expected_revision, "comment", handler, stamp)
        except ValidationError as error:
            raise InvalidCommandError(str(error)) from error

    def _anchor_excerpt(self, ctx: _Ctx, anchor_kind: str, anchor_id: str) -> str:
        """A comment must point at something that exists in the current version."""

        if anchor_kind == "finding":
            match = next(
                (
                    f
                    for f in self._findings(ctx.connection, ctx.matter_id, ctx.version)
                    if f.key == anchor_id
                ),
                None,
            )
            if match:
                return match.summary
        elif anchor_kind == "change":
            change = next(
                (
                    c
                    for c in self._changes(ctx.connection, ctx.matter_id, ctx.version)
                    if c.id == anchor_id
                ),
                None,
            )
            if change:
                return f"{change.original_text} -> {change.final_text}"
        elif anchor_kind == "deliverable_section" and anchor_id in DELIVERABLE_SECTIONS:
            return anchor_id.replace("_", " ")
        elif anchor_kind == "source_span" and ctx.body.document_readable:
            index = index_docx(ctx.version_row["document_blob"])
            paragraph = next(
                (p for p in index.paragraphs if f"para:{p.text_hash}" == anchor_id), None
            )
            if paragraph:
                return paragraph.text
        raise InvalidCommandError(
            f"comment anchor {anchor_kind}:{anchor_id} does not exist in version {ctx.version}"
        )

    def _comment_for(self, ctx: _Ctx, comment_id: str) -> Comment:
        comment = next(
            (
                c
                for c in self._comments(ctx.connection, ctx.matter_id)
                if c.comment_id == comment_id
            ),
            None,
        )
        if comment is None:
            raise NotFoundError(f"matter {ctx.matter_id} has no comment {comment_id}")
        return comment

    def respond_comment(
        self,
        actor_id,
        matter_id,
        expected_revision,
        *,
        comment_id,
        body,
        evidence_refs=(),
        stamp=None,
    ):
        def handler(ctx: _Ctx) -> None:
            comment = self._comment_for(ctx, comment_id)
            roles: tuple[Role, ...] = REVIEW_ROLES
            if comment.addressed_to == "business_requester":
                roles = (*REVIEW_ROLES, "business_requester")
            self._require_access(ctx, roles)
            comment.responses.append(
                CommentResponse(
                    author_id=ctx.actor.actor_id,
                    author_role=ctx.actor.role,
                    body=_require_text(body, 10, "response"),
                    evidence_refs=_check_evidence_refs(list(evidence_refs)),
                    created_at=ctx.now,
                )
            )
            self._save_comment(ctx.connection, comment)
            self._event(
                ctx,
                "comment_response_added",
                f"Response on {comment_id}.",
                {"comment_id": comment_id, "kind": comment.kind},
            )

        return self._execute(
            actor_id, matter_id, expected_revision, "respond_comment", handler, stamp
        )

    def resolve_comment(
        self,
        actor_id,
        matter_id,
        expected_revision,
        *,
        comment_id,
        resolution,
        evidence_refs=(),
        stamp=None,
    ):
        def handler(ctx: _Ctx) -> None:
            self._require_access(ctx, REVIEW_ROLES)
            comment = self._comment_for(ctx, comment_id)
            if comment.state != "open":
                raise InvalidCommandError(f"comment {comment_id} is not open")
            refs = _check_evidence_refs(list(evidence_refs))
            actor = ctx.actor
            if comment.kind == "coverage_gap":
                allowed = actor.role in {"matter_owner", "final_approver"}
            elif comment.kind == "clarification":
                allowed = actor.actor_id == comment.author_id
                if not any(r.author_role == comment.addressed_to for r in comment.responses):
                    raise InvalidCommandError(
                        "the clarification has no answer from its addressee yet"
                    )
            elif comment.severity == "critical":
                # The person whose work is criticised cannot close the criticism.
                allowed = actor.actor_id == comment.author_id or actor.role == "final_approver"
            else:
                allowed = True
            if not allowed:
                raise PermissionDeniedError(
                    f"{actor.actor_id} may not resolve {comment.kind} {comment_id}"
                )
            if comment.blocking and not refs:
                raise InvalidCommandError(
                    "resolving a blocking comment requires supporting evidence"
                )
            comment.state = "resolved"
            comment.resolution = _require_text(resolution, 10, "resolution")
            comment.resolution_evidence = refs
            comment.resolved_by, comment.resolved_at = actor.actor_id, ctx.now
            self._save_comment(ctx.connection, comment)
            self._event(
                ctx,
                "comment_resolved",
                f"{comment_id} resolved.",
                {"comment_id": comment_id, "kind": comment.kind, "evidence_refs": refs},
            )

        return self._execute(
            actor_id, matter_id, expected_revision, "resolve_comment", handler, stamp
        )

    def reopen_comment(
        self, actor_id, matter_id, expected_revision, *, comment_id, reason, stamp=None
    ):
        def handler(ctx: _Ctx) -> None:
            self._require_access(ctx, REVIEW_ROLES)
            comment = self._comment_for(ctx, comment_id)
            if comment.state != "resolved":
                raise InvalidCommandError(f"comment {comment_id} is not resolved")
            comment.state, comment.reopen_count = "open", comment.reopen_count + 1
            comment.responses.append(
                CommentResponse(
                    author_id=ctx.actor.actor_id,
                    author_role=ctx.actor.role,
                    body="Reopened: " + _require_text(reason, 10, "reopen reason"),
                    created_at=ctx.now,
                )
            )
            self._save_comment(ctx.connection, comment)
            self._event(
                ctx, "comment_reopened", f"{comment_id} reopened.", {"comment_id": comment_id}
            )

        return self._execute(
            actor_id, matter_id, expected_revision, "reopen_comment", handler, stamp
        )

    def decide_change(
        self,
        actor_id,
        matter_id,
        expected_revision,
        *,
        change_id,
        outcome,
        reason="",
        amended_text=None,
        source_support_confirmed=False,
        stamp=None,
    ):
        def handler(ctx: _Ctx) -> None:
            self._require_access(ctx, ("matter_owner", "specialist_reviewer"))
            if ctx.matter["state"] not in DECISION_STATES:
                raise InvalidCommandError(
                    f"changes cannot be decided in state {ctx.matter['state']}"
                )
            changes = self._changes(ctx.connection, ctx.matter_id, ctx.version)
            change = next((c for c in changes if c.id == change_id), None)
            if change is None:
                raise NotFoundError(f"version {ctx.version} has no change {change_id}")
            actor = ctx.actor
            # Specialist clauses are decided by that specialist, all others by the owner.
            if change.specialist_role and actor.specialty != change.specialist_role:
                raise PermissionDeniedError(
                    f"{change_id} needs a decision from {change.specialist_role}"
                )
            if not change.specialist_role and actor.role != "matter_owner":
                raise PermissionDeniedError(f"{change_id} is decided by the matter owner")
            previous = {
                "decision": change.decision,
                "amended_text": change.amended_text,
                "reason": change.decision_reason,
            }
            text = " ".join((reason or "").split())
            if outcome == "accepted":
                change.amended_text = None
            elif outcome == "rejected":
                text = _require_text(reason, 20, "reason for keeping the counterparty wording")
                change.amended_text = None
            elif outcome == "amended":
                text = _require_text(reason, 20, "reason for the amended wording")
                wording = " ".join((amended_text or "").split())
                if not wording or wording == change.proposed_text:
                    raise InvalidCommandError(
                        "an amendment needs wording that differs from the proposal"
                    )
                change.amended_text = wording
            elif outcome == "clarification_requested":
                text = _require_text(reason, 10, "clarification question")
            else:
                raise InvalidCommandError(
                    "outcome must be accepted, rejected, amended or clarification_requested"
                )
            if outcome in {"accepted", "amended"} and not source_support_confirmed:
                raise InvalidCommandError(
                    "confirm that you checked the cited source supports the wording; the "
                    "automated checks do not establish that"
                )
            change.decision, change.decision_reason = outcome, text or None
            change.decided_by, change.decided_at = actor.actor_id, ctx.now
            change.source_support_confirmed_by = (
                actor.actor_id if source_support_confirmed else None
            )
            change.carried_from_version = None
            self._save_change(ctx.connection, ctx.matter_id, ctx.version, change)
            self._decision(
                ctx,
                "change_decision",
                outcome,
                text or "accepted as proposed",
                target_id=change_id,
                payload={
                    "previous": previous,
                    "original_text": change.original_text,
                    "proposed_text": change.proposed_text,
                    "amended_text": change.amended_text,
                    "source_support_confirmed": bool(source_support_confirmed),
                },
            )
            payload: dict[str, Any] = {"change_id": change_id, "outcome": outcome}
            if outcome == "clarification_requested":
                sequence = len(self._comments(ctx.connection, ctx.matter_id)) + 1
                clarification = Comment(
                    comment_id=f"c-{sequence:03d}",
                    matter_id=ctx.matter_id,
                    kind="clarification",
                    anchor_kind="change",
                    anchor_id=change_id,
                    anchor_excerpt=f"{change.original_text} -> {change.proposed_text}",
                    created_on_version=ctx.version,
                    author_id=actor.actor_id,
                    author_role=actor.role,
                    addressed_to="business_requester",
                    severity="major",
                    body=text,
                    created_at=ctx.now,
                )
                self._save_comment(ctx.connection, clarification)
                payload["comment_id"] = clarification.comment_id
            self._event(ctx, "change_decided", f"{change_id}: {outcome}.", payload)

        return self._execute(
            actor_id, matter_id, expected_revision, "decide_change", handler, stamp
        )

    def specialist_signoff(self, actor_id, matter_id, expected_revision, *, note, stamp=None):
        def handler(ctx: _Ctx) -> None:
            self._require_access(ctx, ("specialist_reviewer",))
            if ctx.matter["state"] != "review":
                raise InvalidCommandError("a specialist signs off while the matter is in review")
            text = _require_text(note, 20, "sign-off note")
            pending = [
                c.id
                for c in self._changes(ctx.connection, ctx.matter_id, ctx.version)
                if c.specialist_role == ctx.actor.specialty
                and c.decision not in {"accepted", "rejected", "amended"}
            ]
            if pending:
                raise InvalidCommandError(f"undecided specialist changes: {', '.join(pending)}")
            self._decision(
                ctx,
                "specialist_signoff",
                "signed_off",
                text,
                payload={"specialty": ctx.actor.specialty},
            )
            self._event(
                ctx,
                "specialist_signed_off",
                f"{ctx.actor.specialty} sign-off on version {ctx.version}.",
            )

        return self._execute(
            actor_id, matter_id, expected_revision, "specialist_signoff", handler, stamp
        )

    def request_revision(
        self, actor_id, matter_id, expected_revision, *, comment_ids, note, stamp=None
    ):
        def handler(ctx: _Ctx) -> None:
            ctx.extra["comment_ids"] = list(comment_ids)
            text = _require_text(note, 20, "revision reason")
            self._transition(ctx, "request_revision")
            withdrawn = self._invalidate(
                ctx, ("final_approval",), f"revision requested by {ctx.actor.actor_id}"
            )
            ctx.body.assessment = apply_review_decision(
                ctx.body.assessment,
                ReviewDecision(
                    reviewer=ctx.actor.display_name, state="revision_requested", note=text
                ),
            )
            self._save_body(ctx)
            self._decision(
                ctx,
                "revision_request",
                "revision_requested",
                text,
                payload={"comment_ids": list(comment_ids)},
            )
            self._event(
                ctx,
                "revision_requested",
                text,
                {"comment_ids": list(comment_ids), "approvals_withdrawn": withdrawn},
            )

        return self._execute(
            actor_id, matter_id, expected_revision, "request_revision", handler, stamp
        )

    def submit_revision(self, actor_id, matter_id, expected_revision, *, note, stamp=None):
        def handler(ctx: _Ctx) -> None:
            text = _require_text(note, 20, "revision note")
            self._transition(ctx, "submit_revision")
            self._event(ctx, "revision_submitted", text)

        return self._execute(
            actor_id, matter_id, expected_revision, "submit_revision", handler, stamp
        )

    def resume_review(self, actor_id, matter_id, expected_revision, *, stamp=None):
        def handler(ctx: _Ctx) -> None:
            self._transition(ctx, "resume_review")
            self._event(ctx, "review_resumed", "Review resumed on the revised matter.")

        return self._execute(
            actor_id, matter_id, expected_revision, "resume_review", handler, stamp
        )

    def approve(self, actor_id, matter_id, expected_revision, *, note, stamp=None):
        def handler(ctx: _Ctx) -> None:
            text = _require_text(note, 30, "approval note")
            self._transition(ctx, "approve")
            # The parent assessment and the pilot decision are approved in one step,
            # so neither can be approved without the other.
            ctx.body.assessment = apply_review_decision(
                ctx.body.assessment,
                ReviewDecision(
                    reviewer=f"{ctx.actor.display_name} [{ctx.actor.actor_id}, simulated role]",
                    state="approved",
                    note=text,
                ),
            )
            self._save_body(ctx)
            self._decision(
                ctx,
                "final_approval",
                "approved",
                text,
                payload={"tier": ctx.actor.approval_tier},
                bind_review=True,
            )
            self._event(
                ctx,
                "approved",
                f"Final approval on version {ctx.version}.",
                {"tier": ctx.actor.approval_tier},
            )

        return self._execute(actor_id, matter_id, expected_revision, "approve", handler, stamp)

    def amend_matter(
        self,
        actor_id,
        matter_id,
        expected_revision,
        *,
        reason,
        facts=None,
        instructions=None,
        matter_fields=None,
        routing_fields=None,
        decision_authority=None,
        document_name=None,
        document=None,
        playbook=None,
        stamp=None,
    ):
        """Change matter content. A substantive change creates a new version."""

        def handler(ctx: _Ctx) -> None:
            self._require_access(ctx, ("business_requester", "matter_owner"))
            playbook_changed = (
                playbook is not None and playbook.content_hash() != ctx.body.playbook_hash
            )
            if playbook_changed and ctx.actor.role != "matter_owner":
                raise PermissionDeniedError("only the matter owner may change the playbook")
            text = _require_text(reason, 10, "amendment reason")
            old = ctx.body.intake
            data = old.model_dump(mode="json")
            edits: list[tuple[str, str, str]] = []
            for key, value in (facts or {}).items():
                edits.append((f"fact:{key}", old.facts.get(key, ""), str(value)))
                data["facts"][key] = str(value)
            if instructions is not None:
                edits.append(("instructions", old.instructions, instructions))
                data["instructions"] = instructions
            if decision_authority is not None:
                edits.append(("decision_authority", old.decision_authority, decision_authority))
                data["decision_authority"] = decision_authority
            for key, value in (matter_fields or {}).items():
                name = "source_refs" if key == "source_refs" else f"matter:{key}"
                edits.append((name, canonical(data["matter"].get(key)), canonical(value)))
                data["matter"][key] = value
            for key, value in (routing_fields or {}).items():
                if key not in {
                    "value_band",
                    "personal_data",
                    "non_eea_transfer",
                    "uncapped_liability",
                }:
                    raise InvalidCommandError(f"unknown routing field {key}")
                edits.append((f"routing:{key}", canonical(data[key]), canonical(value)))
                data[key] = value
            new_document = (
                document if document is not None else bytes(ctx.version_row["document_blob"])
            )
            if document is not None:
                edits.append(
                    (
                        "document",
                        ctx.version_row["document_sha256"],
                        hashlib.sha256(document).hexdigest(),
                    )
                )
            new_playbook = playbook or ctx.body.playbook
            if playbook is not None:
                edits.append(("playbook", ctx.body.playbook_hash, playbook.content_hash()))
            try:
                new_intake = PilotIntake.model_validate(data)
            except ValidationError as error:
                raise InvalidCommandError(str(error)) from error
            changed = [(name, before, after) for name, before, after in edits if before != after]
            substantive = [
                name
                for name, before, after in changed
                if is_substantive_change(name, before, after)
            ]
            if not changed:
                raise InvalidCommandError("the amendment changes nothing")
            if not substantive:
                # Recorded in the event log; the reviewed version stays untouched.
                if new_intake.matter.title != old.matter.title:
                    ctx.connection.execute(
                        "UPDATE matters SET title = ? WHERE matter_id = ?",
                        (new_intake.matter.title, ctx.matter_id),
                    )
                self._event(
                    ctx,
                    "non_substantive_edit",
                    text,
                    {"fields": [{"field": n, "before": b, "after": a} for n, b, a in changed]},
                )
                return
            invalidated = self._invalidate(
                ctx,
                ("specialist_signoff", "final_approval"),
                f"substantive change to {', '.join(substantive)} created version {ctx.version + 1}",
            )
            new_version = ctx.version + 1
            _, system_ms = self._build_version(
                ctx.connection,
                matter_id=ctx.matter_id,
                version=new_version,
                intake=new_intake,
                document_name=document_name or ctx.version_row["document_name"],
                document=new_document,
                playbook=new_playbook,
                created_by=ctx.actor.actor_id,
                reason=text,
                now=ctx.now,
            )
            ctx.connection.execute(
                "UPDATE matters SET title = ? WHERE matter_id = ?",
                (new_intake.matter.title, ctx.matter_id),
            )
            if ctx.matter["state"] in REASSESSMENT_SOURCES:
                ctx.new_state = "revised"
            ctx.extra["current_version"] = new_version
            self._event(
                ctx,
                "matter_amended",
                text,
                {
                    "new_version": new_version,
                    "substantive_fields": substantive,
                    "decisions_invalidated": invalidated,
                    "reassessed": True,
                },
                system_ms=system_ms,
            )

        return self._execute(actor_id, matter_id, expected_revision, "amend_matter", handler, stamp)

    def restore_version(
        self, actor_id, matter_id, expected_revision, *, version, reason, stamp=None
    ):
        """Recover an earlier version by copying it forward as a new version."""

        with self.store.reading() as connection:
            body, row = self._version(connection, matter_id, version)
        return self.amend_matter(
            actor_id,
            matter_id,
            expected_revision,
            reason=f"restore version {version}: {reason}",
            facts=body.intake.facts,
            instructions=body.intake.instructions,
            decision_authority=body.intake.decision_authority,
            matter_fields=body.intake.matter.model_dump(mode="json"),
            routing_fields={
                key: getattr(body.intake, key)
                for key in ("value_band", "personal_data", "non_eea_transfer", "uncapped_liability")
            },
            playbook=body.playbook,
            document_name=row["document_name"],
            document=bytes(row["document_blob"]),
            stamp=stamp,
        )

    def export_internal_review(self, actor_id, matter_id, expected_revision, *, stamp=None):
        def handler(ctx: _Ctx) -> None:
            self._require_access(ctx, REVIEW_ROLES)
            eligibility = self._eligibility(ctx, "internal_review")
            if not eligibility.eligible:
                raise ExportBlockedError(eligibility)
            started = time.perf_counter()
            manifest = deliverable.write_internal_review_export(
                self._package_data(ctx, eligibility),
                self.export_root / ctx.matter_id / f"v{ctx.version}" / "internal-review",
            )
            self._store_manifest(ctx, "internal_review", manifest)
            self._event(
                ctx,
                "internal_review_exported",
                "Internal review draft written locally.",
                {"files": [f["name"] for f in manifest["files"]]},
                system_ms=round((time.perf_counter() - started) * 1000, 3),
            )

        return self._execute(
            actor_id, matter_id, expected_revision, "export_internal_review", handler, stamp
        )

    def prepare_delivery(self, actor_id, matter_id, expected_revision, *, stamp=None):
        def handler(ctx: _Ctx) -> None:
            self._transition(ctx, "prepare_delivery")
            eligibility = self._eligibility(ctx, "delivery_package")
            if not eligibility.eligible:
                raise ExportBlockedError(eligibility)
            started = time.perf_counter()
            manifest = deliverable.write_delivery_package(
                self._package_data(ctx, eligibility),
                self.export_root / ctx.matter_id / f"v{ctx.version}" / "delivery",
            )
            self._store_manifest(ctx, "delivery_package", manifest)
            self._event(
                ctx,
                "delivery_package_prepared",
                "Approved delivery package written locally; nothing was sent.",
                {"files": [f["name"] for f in manifest["files"]]},
                system_ms=round((time.perf_counter() - started) * 1000, 3),
            )

        return self._execute(
            actor_id, matter_id, expected_revision, "prepare_delivery", handler, stamp
        )

    def accept_delivery(self, actor_id, matter_id, expected_revision, *, note, stamp=None):
        def handler(ctx: _Ctx) -> None:
            ctx.extra["note"] = note
            self._transition(ctx, "accept_delivery")
            ctx.extra["closed_outcome"] = "delivered_locally_and_accepted"
            self._decision(ctx, "acceptance", "accepted", " ".join(note.split()))
            self._event(ctx, "delivery_accepted", "Requester accepted the local delivery package.")

        return self._execute(
            actor_id, matter_id, expected_revision, "accept_delivery", handler, stamp
        )

    def withdraw(self, actor_id, matter_id, expected_revision, *, note, stamp=None):
        def handler(ctx: _Ctx) -> None:
            self._require_access(ctx, WITHDRAWAL_ROLES)
            text = _require_text(note, 20, "withdrawal reason")
            self._invalidate(ctx, ("specialist_signoff", "final_approval"), "matter withdrawn")
            ctx.new_state, ctx.extra["closed_outcome"] = "closed", "withdrawn_without_delivery"
            self._event(ctx, "matter_withdrawn", text)

        return self._execute(actor_id, matter_id, expected_revision, "withdraw", handler, stamp)

    COMMANDS = (
        "submit_intake",
        "complete_triage",
        "assign",
        "start_review",
        "comment",
        "respond_comment",
        "resolve_comment",
        "reopen_comment",
        "decide_change",
        "specialist_signoff",
        "request_revision",
        "submit_revision",
        "resume_review",
        "approve",
        "amend_matter",
        "restore_version",
        "export_internal_review",
        "prepare_delivery",
        "accept_delivery",
        "withdraw",
    )

    def execute(
        self,
        actor_id: str,
        matter_id: str,
        command: str,
        expected_revision: int,
        args: dict[str, Any] | None = None,
        stamp: Stamp | None = None,
    ) -> dict[str, Any]:
        """Dispatch a named command; the entry point for the API and scenario scripts."""

        if command not in self.COMMANDS:
            raise InvalidCommandError(f"unknown command {command}")
        try:
            return getattr(self, command)(
                actor_id, matter_id, expected_revision, stamp=stamp, **(args or {})
            )
        except TypeError as error:
            raise InvalidCommandError(f"invalid arguments for {command}: {error}") from error

    # ------------------------------------------------------------ deliverables

    def _store_manifest(self, ctx: _Ctx, kind: str, manifest: dict[str, Any]) -> None:
        ctx.connection.execute(
            "INSERT INTO deliverable_manifests (matter_id, version, kind, content_hash, review_hash, "
            "body, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                ctx.matter_id,
                ctx.version,
                kind,
                self._current_content_hash(ctx.body, ctx.version_row),
                self._review_hash(ctx),
                json.dumps(manifest, sort_keys=True),
                ctx.now,
            ),
        )

    def _obligations(
        self, ctx: _Ctx, changes: list[StoredChange], names: dict[str, str]
    ) -> list[dict[str, str]]:
        assigned = self._assigned(ctx.connection, ctx.matter_id)
        actors = {a: self._actor(ctx.connection, a) for ids in assigned.values() for a in ids}
        owner = next(iter(assigned.get("matter_owner", [])), "")

        def responsible(role_label: str) -> str:
            specialist = next(
                (a.actor_id for a in actors.values() if a.specialty == role_label), owner
            )
            return names.get(specialist, "unassigned")

        try:
            signature = date.fromisoformat(ctx.body.intake.facts.get("signature_target_date", ""))
        except ValueError:
            signature = None

        def due(days_before: int) -> str:
            return (signature - timedelta(days=days_before)).isoformat() if signature else "not set"

        rows: list[dict[str, str]] = []
        for change in changes:
            rule = ctx.body.playbook.rule(change.rule_id or "")
            if (
                rule is None
                or not rule.exception_obligation
                or change.decision not in {"rejected", "amended"}
            ):
                continue
            rows.append(
                {
                    "obligation": rule.exception_obligation,
                    "arises_from": f"{rule.topic} ({'exception accepted' if change.decision == 'rejected' else 'fallback wording agreed'})",
                    "owner_role": rule.obligation_owner_role,
                    "owner": responsible(rule.obligation_owner_role),
                    "due": due(rule.obligation_due_days_before_signature),
                }
            )
        for commitment in ctx.body.assessment.customer_commitments:
            rows.append(
                {
                    "obligation": f"Record and track the customer commitment: {commitment.commitment}",
                    "arises_from": "Intake commitment register",
                    "owner_role": commitment.owner_role,
                    "owner": responsible(commitment.owner_role),
                    "due": due(0),
                }
            )
        return rows

    def _package_data(self, ctx: _Ctx, eligibility: ExportEligibility) -> deliverable.PackageData:
        changes = self._changes(ctx.connection, ctx.matter_id, ctx.version)
        names = {
            a.actor_id: f"{a.display_name} ({a.actor_id})"
            for a in self.list_actors_in(ctx.connection)
        }
        decisions = [
            dict(row)
            for row in ctx.connection.execute(
                "SELECT * FROM decisions WHERE matter_id = ? ORDER BY decision_id", (ctx.matter_id,)
            )
        ]
        return deliverable.PackageData(
            matter_id=ctx.matter_id,
            title=ctx.body.intake.matter.title,
            state=ctx.new_state or ctx.matter["state"],
            version=ctx.version,
            content_hash=self._current_content_hash(ctx.body, ctx.version_row),
            review_hash=self._review_hash(ctx),
            document_name=ctx.version_row["document_name"],
            document=bytes(ctx.version_row["document_blob"]),
            intake=ctx.body.intake,
            routing=ctx.body.routing,
            playbook_ref=f"{ctx.body.playbook.playbook_id}@v{ctx.body.playbook.version}",
            playbook_hash=ctx.body.playbook_hash,
            findings=self._findings(ctx.connection, ctx.matter_id, ctx.version),
            changes=changes,
            comments=self._comments(ctx.connection, ctx.matter_id),
            decisions=decisions,
            obligations=self._obligations(ctx, changes, names),
            source_support=[self._source_support(ctx, change) for change in changes],
            eligibility=eligibility,
            chain_root=self.store.verify_chain(ctx.connection, ctx.matter_id).chain_root_hash or "",
            actor_names=names,
            generated_at=ctx.now,
        )

    def list_actors_in(self, connection: sqlite3.Connection) -> list[Actor]:
        return [
            Actor.model_validate_json(r["body"])
            for r in connection.execute("SELECT body FROM actors")
        ]

    # ---------------------------------------------------------- source support

    def _source_support(self, ctx: _Ctx, change: StoredChange) -> dict[str, Any]:
        """Report three separate things: whether the reference is allowed, whether the
        quoted text is really at that place in that source version, and whether a
        person confirmed that the source supports the wording."""

        rule = ctx.body.playbook.rule(change.rule_id or "")
        sources: list[dict[str, Any]] = []
        for ref in change.source_refs:
            allow = verify_source_ref(ref)
            entry: dict[str, Any] = {
                "source_ref": ref,
                "allowlist_check": {
                    "status": allow.status,
                    "category": allow.category,
                    "reason": allow.reason,
                    "establishes": "the reference uses a permitted source prefix; nothing about its content",
                },
            }
            if ref.startswith(ctx.body.playbook.playbook_id):
                quoted = rule is not None and (
                    change.operation == "delete_paragraph"
                    or rule.standard_text == change.proposed_text
                )
                entry["source_version"] = {
                    "playbook": ctx.body.playbook.playbook_id,
                    "version": ctx.body.playbook.version,
                    "sha256": ctx.body.playbook_hash,
                }
                entry["quote_check"] = {
                    "method": "exact text comparison with the playbook rule",
                    "status": "quote_found" if quoted else "quote_not_found",
                    "establishes": "the proposed wording is the wording of this playbook rule in this playbook version",
                }
            else:
                found = False
                if ctx.body.document_readable and change.anchor is not None:
                    index = index_docx(ctx.version_row["document_blob"])
                    paragraph = next(
                        (
                            p
                            for p in index.paragraphs
                            if p.text_hash == change.anchor.paragraph_hash
                        ),
                        None,
                    )
                    found = paragraph is not None and change.original_text in paragraph.text
                entry["source_version"] = {
                    "document": ctx.version_row["document_name"],
                    "matter_version": ctx.version,
                    "sha256": ctx.version_row["document_sha256"],
                }
                entry["quote_check"] = {
                    "method": "exact text match at the recorded locator",
                    "status": "quote_found" if found else "quote_not_found",
                    "establishes": "the quoted counterparty wording is present at that locator in this document version",
                }
            sources.append(entry)
        amended = change.decision == "amended"
        return {
            "change_id": change.id,
            "proposition": change.rationale,
            "sources": sources,
            "wording_origin": (
                "reviewer-authored amendment; not playbook text"
                if amended
                else "playbook standard text"
            ),
            "human_review": {
                "required": True,
                "question": "Does the cited source support this wording for this matter?",
                "status": (
                    "confirmed"
                    if change.source_support_confirmed_by
                    else "not_applicable" if change.decision == "rejected" else "pending"
                ),
                "confirmed_by": change.source_support_confirmed_by,
            },
            "not_verified_by_software": "whether the playbook position is legally correct or suitable for this customer",
        }

    # -------------------------------------------------------------------- views

    def list_matters(self, actor_id: str) -> list[dict[str, Any]]:
        with self.store.reading() as connection:
            actor = self._actor(connection, actor_id)
            rows = connection.execute(
                "SELECT * FROM matters ORDER BY created_at, matter_id"
            ).fetchall()
            return [
                {
                    key: row[key]
                    for key in (
                        "matter_id",
                        "title",
                        "state",
                        "current_version",
                        "revision",
                        "closed_outcome",
                    )
                }
                for row in rows
                if self._can_read(connection, actor, row)
            ]

    def view_matter(self, actor_id: str, matter_id: str) -> dict[str, Any]:
        with self.store.reading() as connection:
            ctx = self._context(connection, actor_id, matter_id, Stamp())
            if not self._can_read(connection, ctx.actor, ctx.matter):
                raise PermissionDeniedError(f"{actor_id} has no access to matter {matter_id}")
            matter = {key: ctx.matter[key] for key in ctx.matter.keys()}
            comments = self._comments(connection, matter_id)
            manifests = [
                {
                    "manifest_id": r["manifest_id"],
                    "version": r["version"],
                    "kind": r["kind"],
                    "created_at": r["created_at"],
                    **json.loads(r["body"]),
                }
                for r in connection.execute(
                    "SELECT * FROM deliverable_manifests WHERE matter_id = ? ORDER BY manifest_id",
                    (matter_id,),
                )
            ]
            base: dict[str, Any] = {
                "identity_notice": IDENTITY_NOTICE,
                "actor": ctx.actor.model_dump(),
                "matter": matter,
                "intake": ctx.body.intake.model_dump(mode="json"),
                "external_delivery_allowed": False,
            }
            if ctx.actor.role == "business_requester":
                # Requesters see status, questions addressed to them and the approved package.
                base["clarifications"] = [
                    c.model_dump() for c in comments if c.addressed_to == "business_requester"
                ]
                base["delivery"] = [m for m in manifests if m["kind"] == "delivery_package"]
                base["view"] = "requester_summary"
                return base
            changes = self._changes(connection, matter_id, ctx.version)
            assigned = self._assigned(connection, matter_id)
            allowed = []
            # Evidence that depends on the caller's input, or on who the caller is, is only
            # meaningful when that caller attempts the command.
            skipped = {"revision_reason_recorded", "acceptance_recorded"}
            if ctx.actor.role != "final_approver":
                skipped.add("approver_authorised")
            for transition in allowed_commands(ctx.matter["state"]):
                probe = _Ctx(
                    connection,
                    ctx.actor,
                    ctx.matter,
                    ctx.body,
                    ctx.version_row,
                    Stamp(),
                    ctx.now,
                    new_state=transition.target,
                )
                names = tuple(n for n in transition.evidence if n not in skipped)
                allowed.append(
                    {
                        "command": transition.command,
                        "target": transition.target,
                        "roles": list(transition.roles),
                        "evidence": self._evidence(probe, names),
                    }
                )
            base.update(
                {
                    "view": "review_room",
                    "version": {
                        "version": ctx.version,
                        "content_hash": self._current_content_hash(ctx.body, ctx.version_row),
                        "review_hash": self._review_hash(ctx),
                        "document": {
                            "name": ctx.version_row["document_name"],
                            "sha256": ctx.version_row["document_sha256"],
                        },
                        "playbook": {
                            "id": ctx.body.playbook.playbook_id,
                            "version": ctx.body.playbook.version,
                            "sha256": ctx.body.playbook_hash,
                        },
                        "routing": ctx.body.routing.model_dump(),
                        "required_final_tier": ctx.body.required_final_tier,
                        "required_specialties": ctx.body.required_specialties,
                        "scope_exclusions": ctx.body.scope_exclusions,
                        "missing_facts": ctx.body.missing_facts,
                    },
                    "assessment": ctx.body.assessment.model_dump(mode="json"),
                    "readiness": self._evidence(
                        ctx,
                        (
                            "intake_complete",
                            "sources_usable",
                            "reviewers_available",
                            "decision_authority_agreed",
                        ),
                    ),
                    "findings": [
                        f.model_dump() for f in self._findings(connection, matter_id, ctx.version)
                    ],
                    "changes": [c.model_dump() for c in changes],
                    "source_support": [self._source_support(ctx, c) for c in changes],
                    "comments": [{**c.model_dump(), "blocking": c.blocking} for c in comments],
                    "assignments": assigned,
                    "decisions": [
                        dict(r)
                        for r in connection.execute(
                            "SELECT decision_id, version, kind, target_id, actor_id, role, outcome, note, created_at, invalidated_at, invalidated_reason FROM decisions WHERE matter_id = ? ORDER BY decision_id",
                            (matter_id,),
                        )
                    ],
                    "allowed": allowed,
                    "eligibility": self._eligibility(ctx, "delivery_package").model_dump(
                        by_alias=True
                    ),
                    "manifests": manifests,
                    "versions": [
                        dict(r)
                        for r in connection.execute(
                            "SELECT version, content_hash, document_name, document_sha256, created_at FROM matter_versions WHERE matter_id = ? ORDER BY version",
                            (matter_id,),
                        )
                    ],
                    "audit_chain": self.store.verify_chain(connection, matter_id).model_dump(),
                }
            )
            return base

    def history(self, actor_id: str, matter_id: str) -> dict[str, Any]:
        """Every version, decision and event of a matter, for recovery and audit."""

        with self.store.reading() as connection:
            ctx = self._context(connection, actor_id, matter_id, Stamp())
            if ctx.actor.role == "business_requester" or not self._can_read(
                connection, ctx.actor, ctx.matter
            ):
                raise PermissionDeniedError(
                    f"{actor_id} has no access to the history of {matter_id}"
                )
            versions = []
            for row in connection.execute(
                "SELECT * FROM matter_versions WHERE matter_id = ? ORDER BY version", (matter_id,)
            ):
                body = VersionBody.model_validate_json(row["body"])
                versions.append(
                    {
                        "version": row["version"],
                        "created_at": row["created_at"],
                        "created_by": body.created_by,
                        "reason": body.reason,
                        "content_hash": row["content_hash"],
                        "document_name": row["document_name"],
                        "document_sha256": row["document_sha256"],
                        "facts": body.intake.facts,
                        "instructions": body.intake.instructions,
                        "changes": [
                            c.model_dump()
                            for c in self._changes(connection, matter_id, row["version"])
                        ],
                    }
                )
            events = [
                {
                    **{k: r[k] for k in r.keys() if k != "payload"},
                    "payload": json.loads(r["payload"]),
                }
                for r in connection.execute(
                    "SELECT * FROM events WHERE matter_id = ? ORDER BY seq", (matter_id,)
                )
            ]
            return {
                "matter_id": matter_id,
                "versions": versions,
                "events": events,
                "audit_chain": self.store.verify_chain(connection, matter_id).model_dump(),
            }

    def version_document(self, actor_id: str, matter_id: str, version: int) -> bytes:
        with self.store.reading() as connection:
            ctx = self._context(connection, actor_id, matter_id, Stamp())
            if ctx.actor.role == "business_requester" or not self._can_read(
                connection, ctx.actor, ctx.matter
            ):
                raise PermissionDeniedError(f"{actor_id} has no access to documents of {matter_id}")
            return bytes(self._version(connection, matter_id, version)[1]["document_blob"])

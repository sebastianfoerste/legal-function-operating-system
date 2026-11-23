import hashlib
import json
import re
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from src.docx_redline import index_docx, list_tracked_changes, read_paragraph_texts
from src.export_gate import ExportBlockedError
from src.pilot import cli as pilot_cli
from src.pilot import deliverable
from src.pilot.design_tokens import PRINT_CSS, TOKENS_CSS
from src.pilot.fixtures import build_synthetic_msa
from src.pilot.models import Actor
from src.pilot.onboarding import SYNTHETIC_ACTORS
from src.pilot.scenario_runner import ScenarioRunner, all_task_ids, seed_actors
from src.pilot.service import (
    InvalidCommandError,
    NotFoundError,
    PermissionDeniedError,
    PilotService,
    StaleSubmissionError,
    Stamp,
    TransitionBlockedError,
)
from src.pilot.store import PilotStore
from src.playbook import Playbook, load_playbook
from tests.pilot_support import (
    APPROVER_GC,
    APPROVER_LEAD,
    OTHER_OWNER,
    OWNER,
    REQUESTER,
    SPECIALIST,
    change_id,
    event_types,
    make_service,
    revision,
    run_until,
    scenario,
    state,
)

APPROVAL = "All deviations decided and evidenced; approving the reviewed draft."
OWNER_LABEL = (
    "Simulated local role: Synthetic Matter Owner B (Commercial Counsel) (syn-owner-legalops)"
)
SPECIALIST_LABEL = (
    "Simulated local role: Synthetic Specialist C (Privacy Counsel) (syn-specialist-privacy)"
)
PROPOSAL_LABEL = "Playbook proposal, no reviewer decision yet"
DRAFT_PREFIX = "DRAFT, not approved. "
RUNBOOK = Path(__file__).resolve().parents[1] / "docs" / "pilot" / "RUNBOOK.md"
# What is written to a version after it exists (RUNBOOK section 5): a review decision on
# its assessment and the decision on a proposed change. Nothing else of a version moves.
REVIEW_DECISION_FIELDS = {"review_state", "review_note", "export_allowed", "audit_events"}
CHANGE_DECISION_FIELDS = {
    "decision",
    "decision_reason",
    "amended_text",
    "decided_by",
    "decided_at",
    "source_support_confirmed_by",
    "carried_from_version",
}


class FixedClock:
    def __init__(self, now: str) -> None:
        self.value = now

    def now(self) -> str:
        return self.value


class TickingClock:
    """Moves on a minute at every reading, so no two recorded times share a second."""

    def __init__(self) -> None:
        self.value = datetime(2026, 9, 7, 8, 0, tzinfo=UTC)

    def now(self) -> str:
        self.value += timedelta(minutes=1)
        return self.value.isoformat(timespec="microseconds").replace("+00:00", "Z")


def _failing(error: TransitionBlockedError) -> set[str]:
    return {item["name"] for item in error.evidence if not item["ok"]}


def _reasons(service: PilotService, actor: str, matter_id: str) -> str:
    return " | ".join(service.export_eligibility(actor, matter_id, "delivery_package").reasons())


# -- persistence -------------------------------------------------------------------


def test_review_actions_survive_a_new_store_and_service_instance(tmp_path) -> None:
    service = make_service(tmp_path)
    matter_id = run_until(service, "routine", "A09")
    before = service.view_matter(OWNER, matter_id)

    reopened = PilotService(
        PilotStore(tmp_path / "pilot.sqlite3"), export_root=tmp_path / "exports"
    )
    after = reopened.view_matter(OWNER, matter_id)
    assert after["matter"] == before["matter"]
    assert [c["decision"] for c in after["changes"]] == ["accepted", "accepted"]
    assert after["audit_chain"]["verified"]

    reopened.approve(APPROVER_LEAD, matter_id, after["matter"]["revision"], note=APPROVAL)
    assert state(reopened, matter_id) == "approved"


def test_operational_and_fixture_timestamps_are_kept_apart(tmp_path) -> None:
    service = make_service(tmp_path)
    matter_id = run_until(service, "routine", "A02")
    events = service.history(OWNER, matter_id)["events"]
    created = events[0]
    assert created["fixture_at"] == "2026-09-07T08:00:00Z"
    assert created["occurred_at"] != created["fixture_at"] and created["occurred_at"].endswith("Z")
    assert created["system_ms"] > 0 and created["effort_minutes"] == 12


# -- permissions -------------------------------------------------------------------


def test_unauthorised_decisions_are_refused_and_recorded(tmp_path) -> None:
    service = make_service(tmp_path)
    matter_id = run_until(service, "specialist-revision", "B17")
    start = revision(service, matter_id)
    privacy_change = change_id(service, matter_id, "subprocessors")
    audit_change = change_id(service, matter_id, "audit-right")
    accept = {"outcome": "accepted", "source_support_confirmed": True}

    with pytest.raises(PermissionDeniedError, match="not an identity"):
        service.approve("General Counsel", matter_id, start, note=APPROVAL)
    with pytest.raises(PermissionDeniedError, match="simulated role business_requester"):
        service.decide_change(REQUESTER, matter_id, start, change_id=audit_change, **accept)
    with pytest.raises(PermissionDeniedError, match="needs a decision from Privacy Counsel"):
        service.decide_change(OWNER, matter_id, start, change_id=privacy_change, **accept)
    with pytest.raises(PermissionDeniedError, match="decided by the matter owner"):
        service.decide_change(SPECIALIST, matter_id, start, change_id=audit_change, **accept)
    with pytest.raises(PermissionDeniedError, match="not assigned"):
        service.approve(APPROVER_LEAD, matter_id, start, note=APPROVAL)
    with pytest.raises(PermissionDeniedError, match="not assigned"):
        service.comment(
            OTHER_OWNER,
            matter_id,
            start,
            anchor_kind="change",
            anchor_id=audit_change,
            body="Looks fine to me.",
        )

    assert revision(service, matter_id) == start
    assert event_types(service, matter_id).count("command_refused") >= 6
    assert service.view_matter(OWNER, matter_id)["audit_chain"]["verified"]


def test_cross_matter_access_is_denied(tmp_path) -> None:
    service = make_service(tmp_path)
    routine = run_until(service, "routine", "A06")
    specialist = run_until(service, "specialist-revision", "B10")
    service.register_actor(
        Actor(
            actor_id="syn-requester-other",
            display_name="Synthetic Requester Z",
            role="business_requester",
            onboarded=True,
        )
    )

    # APPROVER_LEAD is on the routine matter only; APPROVER_GC on the specialist matter only.
    for actor, foreign in (
        (APPROVER_LEAD, specialist),
        (APPROVER_GC, routine),
        (OTHER_OWNER, routine),
    ):
        with pytest.raises(PermissionDeniedError, match="no access"):
            service.view_matter(actor, foreign)
        with pytest.raises(PermissionDeniedError):
            service.history(actor, foreign)
        with pytest.raises(PermissionDeniedError):
            service.export_eligibility(actor, foreign, "delivery_package")
        with pytest.raises(PermissionDeniedError):
            service.version_document(actor, foreign, 1)
    assert service.list_matters("syn-requester-other") == []
    assert [m["matter_id"] for m in service.list_matters(APPROVER_LEAD)] == [routine]
    with pytest.raises(PermissionDeniedError):
        service.view_matter("syn-requester-other", routine)


def test_requester_sees_status_and_questions_only(tmp_path) -> None:
    service = make_service(tmp_path)
    matter_id = run_until(service, "specialist-revision", "B21")
    view = service.view_matter(REQUESTER, matter_id)
    assert view["view"] == "requester_summary"
    assert not {"comments", "changes", "findings", "decisions", "eligibility"} & set(view)
    assert [c["kind"] for c in view["clarifications"]] == ["clarification"]
    with pytest.raises(PermissionDeniedError):
        service.history(REQUESTER, matter_id)


def test_readiness_needs_onboarded_reviewers_and_agreed_authority(tmp_path) -> None:
    service = make_service(tmp_path)
    matter_id = run_until(service, "specialist-revision", "B07")
    with pytest.raises(TransitionBlockedError) as blocked:
        service.start_review(OWNER, matter_id, revision(service, matter_id))
    assert "has not completed onboarding" in str(blocked.value)
    with pytest.raises(InvalidCommandError, match="onboarding tasks still open: spec-2, spec-3"):
        service.complete_onboarding(SPECIALIST, ["spec-1"])

    # A lower-tier approver cannot stand in for the tier the parent approval matrix requires.
    service.assign(
        OWNER,
        matter_id,
        revision(service, matter_id),
        role="final_approver",
        assignee_id=APPROVER_LEAD,
    )
    with pytest.raises(TransitionBlockedError, match="does not hold tier General Counsel"):
        service.start_review(OWNER, matter_id, revision(service, matter_id))


FINAL_APPROVAL = (
    "All comments resolved and exceptions evidenced; approving version 3 of the reviewed draft."
)


@pytest.mark.parametrize(
    ("approver", "promote", "refusal"),
    [
        (APPROVER_LEAD, False, "General Counsel required"),
        (REQUESTER, True, "the approver is also requester or matter owner on this matter"),
        (SPECIALIST, True, "the approver decided a change on this matter"),
    ],
    ids=["tier too low", "requester", "decided a change"],
)
def test_final_approval_refuses_tier_requester_or_change_decider(
    tmp_path, approver: str, promote: bool, refusal: str
) -> None:
    # The separation rules compare actor ids. Giving the requester or the specialist the
    # approver role and the General Counsel tier does not let either approve; nor does the
    # Legal Ops Lead, whose tier is too low.
    service = make_service(tmp_path)
    matter_id = run_until(service, "specialist-revision", "B41")
    if promote:
        # No command can change a registered actor (register_actor refuses it), so the
        # promotion is written straight into the store (the direct database access of
        # control 10), as the matter-owner test below writes its assignment.
        current = next(actor for actor in service.list_actors() if actor.actor_id == approver)
        promoted = current.model_copy(
            update={"role": "final_approver", "approval_tier": "General Counsel"}
        )
        with service.store.transaction() as connection:
            connection.execute(
                "UPDATE actors SET body = ? WHERE actor_id = ?",
                (promoted.model_dump_json(), approver),
            )
    service.assign(
        OWNER,
        matter_id,
        revision(service, matter_id),
        role="final_approver",
        assignee_id=approver,
    )
    start = revision(service, matter_id)
    refusals = event_types(service, matter_id).count("command_refused")

    with pytest.raises(TransitionBlockedError) as blocked:
        service.approve(approver, matter_id, start, note=FINAL_APPROVAL)
    assert _failing(blocked.value) == {"approver_authorised"}
    [item] = [entry for entry in blocked.value.evidence if entry["name"] == "approver_authorised"]
    assert refusal in item["detail"]
    assert item["requirement"].endswith("and decided none of the changes.")
    assert revision(service, matter_id) == start and state(service, matter_id) == "review"
    assert event_types(service, matter_id).count("command_refused") == refusals + 1
    assert service.view_matter(OWNER, matter_id)["audit_chain"]["verified"]


def test_final_approval_refuses_an_approver_who_is_also_matter_owner(tmp_path) -> None:
    # No command can produce this state: only the matter owner assigns the final approver,
    # one actor ID holds one role, and a matter has one owner, who claimed it at triage. The
    # owner half of the check is defence in depth, so this test reaches it by writing the
    # assignment row straight into the store (the direct database access of control 10).
    service = make_service(tmp_path)
    matter_id = run_until(service, "specialist-revision", "B41")
    with service.store.transaction() as connection:
        connection.execute(
            "INSERT INTO assignments (matter_id, role, actor_id, assigned_by, assigned_at) "
            "VALUES (?, 'matter_owner', ?, ?, ?)",
            (matter_id, APPROVER_GC, OWNER, "2026-01-01T00:00:00Z"),
        )
    start = revision(service, matter_id)
    refusals = event_types(service, matter_id).count("command_refused")

    with pytest.raises(TransitionBlockedError) as blocked:
        service.approve(APPROVER_GC, matter_id, start, note=FINAL_APPROVAL)
    assert _failing(blocked.value) == {"approver_authorised"}
    [item] = [entry for entry in blocked.value.evidence if entry["name"] == "approver_authorised"]
    assert item["detail"] == "the approver is also requester or matter owner on this matter"
    assert revision(service, matter_id) == start and state(service, matter_id) == "review"
    assert event_types(service, matter_id).count("command_refused") == refusals + 1
    assert service.view_matter(OWNER, matter_id)["audit_chain"]["verified"]


def test_the_assigned_general_counsel_approves_where_the_others_were_refused(tmp_path) -> None:
    service = make_service(tmp_path)
    matter_id = run_until(service, "specialist-revision", "B41")
    service.approve(APPROVER_GC, matter_id, revision(service, matter_id), note=FINAL_APPROVAL)
    assert state(service, matter_id) == "approved"


# -- registered actors ------------------------------------------------------------------

# Every field of an actor that registration could change, and a different value for it.
# onboarded changes only through complete_onboarding; actor_id names the actor; synthetic is
# always true.
ACTOR_CHANGES: dict[str, Any] = {
    "display_name": "Synthetic Approver E (Legal Ops Lead)",
    "role": "matter_owner",
    "specialty": "Privacy Counsel",
    "approval_tier": "Legal Ops Lead",
    "available": False,
}


def _actor_rows(service: PilotService) -> list[tuple[str, str]]:
    with service.store.reading() as connection:
        rows = connection.execute("SELECT actor_id, body FROM actors ORDER BY actor_id")
        return [(row["actor_id"], row["body"]) for row in rows]


def test_the_refusal_covers_every_field_of_an_actor() -> None:
    assert set(ACTOR_CHANGES) == set(Actor.model_fields) - {"actor_id", "onboarded", "synthetic"}


def test_registering_an_actor_again_changes_nothing_and_keeps_its_onboarding(tmp_path) -> None:
    service = make_service(tmp_path, onboard_specialist=True)
    before = _actor_rows(service)
    # The seed list registers everyone as not onboarded; the store says they all are.
    for actor in SYNTHETIC_ACTORS:
        assert not actor.onboarded
        assert service.register_actor(actor).onboarded
    seed_actors(service)  # what `pilot seed` runs on an existing store
    assert _actor_rows(service) == before
    assert all(actor.onboarded for actor in service.list_actors())

    # Nor does registering again onboard anyone: that is complete_onboarding's job.
    fresh = make_service(tmp_path / "fresh")
    specialist = next(actor for actor in SYNTHETIC_ACTORS if actor.actor_id == SPECIALIST)
    assert not fresh.register_actor(specialist.model_copy(update={"onboarded": True})).onboarded
    assert not next(a for a in fresh.list_actors() if a.actor_id == SPECIALIST).onboarded


@pytest.mark.parametrize(
    ("update", "named"),
    [
        *(({field: value}, field) for field, value in ACTOR_CHANGES.items()),
        ({"role": "matter_owner", "approval_tier": None}, "approval_tier, role"),
    ],
    ids=[*ACTOR_CHANGES, "two fields"],
)
def test_a_registered_actor_cannot_be_changed(tmp_path, update: dict[str, Any], named: str) -> None:
    service = make_service(tmp_path)
    before = _actor_rows(service)
    stored = next(actor for actor in service.list_actors() if actor.actor_id == APPROVER_GC)
    with pytest.raises(InvalidCommandError) as refused:
        service.register_actor(stored.model_copy(update=update))
    assert str(refused.value) == (
        f"{APPROVER_GC} is already registered; its {named} cannot change. "
        "Register a new synthetic actor ID instead"
    )
    assert _actor_rows(service) == before


def test_pilot_seed_keeps_onboarding_and_reports_an_actor_it_cannot_change(
    tmp_path, capsys
) -> None:
    db = tmp_path / "pilot.sqlite3"
    assert pilot_cli.main(["seed", "--db", str(db)]) == 0
    service = PilotService(PilotStore(db))
    service.complete_onboarding(SPECIALIST, all_task_ids("specialist_reviewer"))
    before = _actor_rows(service)
    assert pilot_cli.main(["seed", "--db", str(db)]) == 0  # seeding again resets nothing
    assert _actor_rows(service) == before

    # A store whose approver differs from the seed list (written directly, control 10).
    stored = next(actor for actor in service.list_actors() if actor.actor_id == APPROVER_GC)
    with service.store.transaction() as connection:
        connection.execute(
            "UPDATE actors SET body = ? WHERE actor_id = ?",
            (
                stored.model_copy(update={"approval_tier": "Legal Ops Lead"}).model_dump_json(),
                APPROVER_GC,
            ),
        )
    changed = _actor_rows(service)
    capsys.readouterr()
    assert pilot_cli.main(["seed", "--db", str(db)]) == 2
    assert capsys.readouterr().err == (
        f"refusing to seed {db}: {APPROVER_GC} is already registered; its approval_tier "
        "cannot change. Register a new synthetic actor ID instead\n"
    )
    assert _actor_rows(service) == changed


def test_a_recorded_approval_keeps_counting_because_its_approver_cannot_change(
    tmp_path,
) -> None:
    # The export gate reads each decision's author as stored now. Re-registering the General
    # Counsel with a lower tier used to make this approval stop counting, with no event.
    service = make_service(tmp_path)
    matter_id = run_until(service, "specialist-revision", "B41")
    service.approve(APPROVER_GC, matter_id, revision(service, matter_id), note=FINAL_APPROVAL)
    before = service.export_eligibility(OWNER, matter_id, "delivery_package")
    events = event_types(service, matter_id)
    stored = next(actor for actor in service.list_actors() if actor.actor_id == APPROVER_GC)
    with pytest.raises(InvalidCommandError, match="its approval_tier cannot change"):
        service.register_actor(stored.model_copy(update={"approval_tier": "Legal Ops Lead"}))
    assert service.export_eligibility(OWNER, matter_id, "delivery_package") == before
    assert before.eligible and event_types(service, matter_id) == events


@pytest.mark.parametrize("blank", ["\u200b", "\u2060", "\u034f", "\u3164"])
def test_a_clarification_question_counts_only_what_the_requester_sees(tmp_path, blank) -> None:
    # The requester is told "Answer the open question below.", so a question that reads
    # empty would ask nothing.
    service = make_service(tmp_path)
    matter_id = run_until(service, "routine", "A06")
    loaded = revision(service, matter_id)
    target = change_id(service, matter_id, "audit-right")
    ask = {"change_id": target, "outcome": "clarification_requested"}
    with pytest.raises(InvalidCommandError, match="question must be at least 10 visible"):
        service.decide_change(OWNER, matter_id, loaded, reason=blank * 10, **ask)
    with pytest.raises(InvalidCommandError, match="question must be at least 10 visible"):
        service.decide_change(OWNER, matter_id, loaded, reason="Which?" + blank * 10, **ask)
    assert revision(service, matter_id) == loaded
    service.decide_change(OWNER, matter_id, loaded, reason="Which plan?" + blank, **ask)
    change = next(c for c in service.view_matter(OWNER, matter_id)["changes"] if c["id"] == target)
    assert change["decision"] == "clarification_requested"


# -- stale submissions and conflicting edits -----------------------------------------


def test_stale_submission_is_refused_and_overwrites_nothing(tmp_path) -> None:
    service = make_service(tmp_path)
    matter_id = run_until(service, "routine", "A06")
    loaded = revision(service, matter_id)
    target = change_id(service, matter_id, "audit-right")
    service.decide_change(
        OWNER,
        matter_id,
        loaded,
        change_id=target,
        outcome="accepted",
        source_support_confirmed=True,
    )

    with pytest.raises(StaleSubmissionError) as stale:
        service.decide_change(
            OWNER, matter_id, loaded, change_id=target, outcome="rejected",
            reason="Keeping the customer wording after all, on reflection.",
        )  # fmt: skip
    assert stale.value.current_revision == loaded + 1
    change = next(c for c in service.view_matter(OWNER, matter_id)["changes"] if c["id"] == target)
    assert change["decision"] == "accepted"


def test_amended_wording_a_word_document_cannot_hold_is_refused(tmp_path) -> None:
    # JSON can carry "\u0001"; written into the redline it would make the document malformed,
    # and the delivery package would fail only after the final approval was recorded.
    service = make_service(tmp_path)
    matter_id = run_until(service, "routine", "A07")
    target = change_id(service, matter_id, "payment-terms")
    start, events = revision(service, matter_id), event_types(service, matter_id)
    for wording in ("forty-five (45) days\x01", "forty-five (45) days\ufffe", "\ud800 days"):
        with pytest.raises(InvalidCommandError, match="a Word document cannot hold"):
            service.decide_change(
                OWNER, matter_id, start, change_id=target, outcome="amended",
                reason="Finance agreed forty-five days for this account.",
                amended_text=wording, source_support_confirmed=True,
            )  # fmt: skip
    # Refused as an invalid command, like other invalid wording: nothing is recorded.
    assert revision(service, matter_id) == start and event_types(service, matter_id) == events
    change = next(c for c in service.view_matter(OWNER, matter_id)["changes"] if c["id"] == target)
    assert change["decision"] == "pending" and change["amended_text"] is None


def test_concurrent_writers_only_one_wins(tmp_path) -> None:
    service = make_service(tmp_path)
    matter_id = run_until(service, "routine", "A06")
    loaded = revision(service, matter_id)
    target = change_id(service, matter_id, "payment-terms")
    outcomes: list[str] = []
    barrier = threading.Barrier(8)

    def writer(number: int) -> None:
        local = PilotService(
            PilotStore(tmp_path / "pilot.sqlite3"), export_root=tmp_path / "exports"
        )
        barrier.wait()
        try:
            local.decide_change(
                OWNER, matter_id, loaded, change_id=target, outcome="rejected",
                reason=f"Writer {number} keeps the customer wording for this deal.",
            )  # fmt: skip
            outcomes.append("ok")
        except StaleSubmissionError:
            outcomes.append("stale")

    threads = [threading.Thread(target=writer, args=(n,)) for n in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert sorted(outcomes) == ["ok"] + ["stale"] * 7
    assert revision(service, matter_id) == loaded + 1
    assert service.view_matter(OWNER, matter_id)["audit_chain"]["verified"]


# -- version binding ---------------------------------------------------------------


def test_fact_change_invalidates_signoff_and_blocks_stale_approval(tmp_path) -> None:
    service = make_service(tmp_path)
    matter_id = run_until(service, "specialist-revision", "B36")
    before = service.view_matter(OWNER, matter_id)
    assert before["matter"]["current_version"] == 2

    service.amend_matter(
        REQUESTER, matter_id, revision(service, matter_id),
        reason="Customer moved the signature date.", facts={"signature_target_date": "2026-10-15"},
    )  # fmt: skip
    after = service.view_matter(OWNER, matter_id)
    assert after["matter"]["state"] == "revised" and after["matter"]["current_version"] == 3
    assert after["version"]["content_hash"] != before["version"]["content_hash"]
    assert after["assessment"]["review_state"] == "needs_review"  # reassessed
    signoff = next(d for d in after["decisions"] if d["kind"] == "specialist_signoff")
    assert signoff["invalidated_at"] and "signature_target_date" in signoff["invalidated_reason"]
    assert {c["decision"] for c in after["changes"]} == {"accepted", "rejected", "amended"}
    assert {c["carried_from_version"] for c in after["changes"]} == {2}

    with pytest.raises(TransitionBlockedError, match="not allowed from state revised"):
        service.approve(APPROVER_GC, matter_id, revision(service, matter_id), note=APPROVAL)
    service.resume_review(OWNER, matter_id, revision(service, matter_id))
    with pytest.raises(TransitionBlockedError) as blocked:
        service.approve(APPROVER_GC, matter_id, revision(service, matter_id), note=APPROVAL)
    assert _failing(blocked.value) == {"specialist_signoffs_current"}
    assert "specialist_signoff:Privacy Counsel was invalidated" in _reasons(
        service, OWNER, matter_id
    )

    # Earlier versions remain readable, byte for byte.
    history = service.history(OWNER, matter_id)
    assert [v["version"] for v in history["versions"]] == [1, 2, 3]
    assert history["versions"][1]["facts"]["signature_target_date"] == "2026-09-30"
    assert service.version_document(OWNER, matter_id, 1) == build_synthetic_msa("specialist")


def test_approval_is_bound_to_the_reviewed_state(tmp_path) -> None:
    service = make_service(tmp_path)
    matter_id = run_until(service, "routine", "A11")
    assert service.export_eligibility(OWNER, matter_id, "delivery_package").eligible

    # A comment after approval changes the reviewed state: the approval no longer covers it.
    service.comment(
        APPROVER_LEAD, matter_id, revision(service, matter_id), anchor_kind="deliverable_section",
        anchor_id="executive_summary", body="Add the renewal date to the summary.", severity="note",
    )  # fmt: skip
    assert "predates a later change decision or comment" in _reasons(service, OWNER, matter_id)
    with pytest.raises(TransitionBlockedError) as blocked:
        service.prepare_delivery(OWNER, matter_id, revision(service, matter_id))
    assert _failing(blocked.value) == {"export_gate_passes"}
    assert state(service, matter_id) == "approved"
    assert service.view_matter(OWNER, matter_id)["manifests"] == []


def test_decision_changed_behind_the_application_layer_stales_the_approval(tmp_path) -> None:
    service = make_service(tmp_path)
    matter_id = run_until(service, "routine", "A11")
    target = change_id(service, matter_id, "audit-right")
    with service.store.transaction() as connection:
        row = connection.execute(
            "SELECT body FROM changes WHERE matter_id = ? AND change_id = ?", (matter_id, target)
        ).fetchone()
        body = {**json.loads(row["body"]), "decision": "rejected"}
        connection.execute(
            "UPDATE changes SET body = ? WHERE matter_id = ? AND change_id = ?",
            (json.dumps(body), matter_id, target),
        )
    assert "final_approval:Reviewer predates a later change decision" in _reasons(
        service, OWNER, matter_id
    )
    with pytest.raises(TransitionBlockedError):
        service.prepare_delivery(OWNER, matter_id, revision(service, matter_id))


def test_new_source_document_creates_a_version_and_resets_affected_decisions(tmp_path) -> None:
    service = make_service(tmp_path)
    matter_id = run_until(service, "routine", "A11")
    service.amend_matter(
        REQUESTER, matter_id, revision(service, matter_id), reason="Customer sent a new draft.",
        document_name="customer-draft-2.docx", document=build_synthetic_msa("specialist"),
    )  # fmt: skip
    view = service.view_matter(OWNER, matter_id)
    assert view["matter"]["state"] == "revised" and view["matter"]["current_version"] == 2
    decisions = {c["rule_id"]: (c["decision"], c["carried_from_version"]) for c in view["changes"]}
    # Clauses that are textually unchanged keep their decision; new deviations start pending.
    assert decisions["payment-terms"] == ("accepted", 1) and decisions["audit-right"] == (
        "accepted",
        1,
    )
    assert decisions["liability-cap"] == ("pending", None)
    assert view["version"]["required_specialties"] == ["Privacy Counsel"]
    approval = next(d for d in view["decisions"] if d["kind"] == "final_approval")
    assert approval["invalidated_at"] and "document" in approval["invalidated_reason"]
    reasons = _reasons(service, OWNER, matter_id)
    assert "assessment_approved" in reasons and "changes_decided" in reasons
    assert service.version_document(OWNER, matter_id, 1) == build_synthetic_msa("routine")


def test_playbook_change_invalidates_approval_and_resets_the_changed_rule(tmp_path) -> None:
    service = make_service(tmp_path)
    matter_id = run_until(service, "routine", "A11")
    current = load_playbook().model_dump(by_alias=True)
    current["version"] = 2
    for rule in current["rules"]:
        if rule["rule_id"] == "payment-terms":
            rule["standard_text"] = "fourteen (14) days"
    updated = Playbook.model_validate(current)

    with pytest.raises(
        PermissionDeniedError, match="only the matter owner may change the playbook"
    ):
        service.amend_matter(
            REQUESTER,
            matter_id,
            revision(service, matter_id),
            reason="New playbook.",
            playbook=updated,
        )
    service.amend_matter(
        OWNER,
        matter_id,
        revision(service, matter_id),
        reason="Playbook version 2 issued.",
        playbook=updated,
    )
    view = service.view_matter(OWNER, matter_id)
    assert view["version"]["playbook"]["version"] == 2 and view["matter"]["state"] == "revised"
    decisions = {c["rule_id"]: c["decision"] for c in view["changes"]}
    assert decisions == {"payment-terms": "pending", "audit-right": "accepted"}
    assert all(d["invalidated_at"] for d in view["decisions"] if d["kind"] == "final_approval")


def test_whitespace_only_edit_is_logged_without_a_new_version(tmp_path) -> None:
    service = make_service(tmp_path)
    matter_id = run_until(service, "routine", "A11")
    with service.store.reading() as connection:
        matter = service._matter(connection, matter_id)
        instructions = service._version(connection, matter_id, matter["current_version"])[
            0
        ].intake.instructions
    service.amend_matter(
        REQUESTER, matter_id, revision(service, matter_id), reason="Tidy spacing only.",
        instructions="  " + instructions.replace(" ", "  ").upper(),
    )  # fmt: skip
    view = service.view_matter(OWNER, matter_id)
    assert view["matter"]["current_version"] == 1 and view["matter"]["state"] == "approved"
    assert view["eligibility"]["eligible"]
    assert "non_substantive_edit" in event_types(service, matter_id)
    with pytest.raises(InvalidCommandError, match="changes nothing"):
        service.amend_matter(
            REQUESTER, matter_id, revision(service, matter_id), reason="No change at all.", facts={}
        )


def test_restore_copies_an_earlier_version_forward(tmp_path) -> None:
    service = make_service(tmp_path)
    matter_id = run_until(service, "routine", "A06")
    first = service.view_matter(OWNER, matter_id)["version"]["content_hash"]
    service.amend_matter(
        REQUESTER, matter_id, revision(service, matter_id), reason="Wrong counterparty entered.",
        facts={"counterparty": "Someone Else AG (fictitious)"},
    )  # fmt: skip
    service.restore_version(
        OWNER,
        matter_id,
        revision(service, matter_id),
        version=1,
        reason="The first entry was right.",
    )
    view = service.view_matter(OWNER, matter_id)
    assert view["matter"]["current_version"] == 3 and len(view["versions"]) == 3
    assert view["version"]["content_hash"] == first
    assert view["versions"][1]["content_hash"] != first  # version 2 is still there


def _versions_as_stored(service: PilotService, matter_id: str) -> dict[int, dict[str, Any]]:
    """Every version of the matter as the store holds it, split into what a review decision
    or a change decision may write and everything else."""

    stored: dict[int, dict[str, Any]] = {}
    with service.store.reading() as connection:
        versions = connection.execute(
            "SELECT * FROM matter_versions WHERE matter_id = ? ORDER BY version", (matter_id,)
        ).fetchall()
        for row in versions:
            key = (matter_id, row["version"])
            body = json.loads(row["body"])
            assessment = body.pop("assessment")
            changes = {
                r["change_id"]: (r["position"], json.loads(r["body"]))
                for r in connection.execute(
                    "SELECT * FROM changes WHERE matter_id = ? AND version = ?", key
                )
            }
            findings = connection.execute(
                "SELECT finding_key, body FROM findings WHERE matter_id = ? AND version = ? "
                "ORDER BY finding_key",
                key,
            ).fetchall()
            stored[row["version"]] = {
                "fixed": {
                    # The content hash, the document name, digest and bytes, the time.
                    "row": {name: row[name] for name in row.keys() if name != "body"},
                    # The intake, the playbook, the routing decision and what follows from them.
                    "body": body,
                    "assessment": {
                        k: v for k, v in assessment.items() if k not in REVIEW_DECISION_FIELDS
                    },
                    "findings": [tuple(finding) for finding in findings],
                    "proposals": {
                        change: (
                            position,
                            {k: v for k, v in data.items() if k not in CHANGE_DECISION_FIELDS},
                        )
                        for change, (position, data) in changes.items()
                    },
                },
                "review_decision": {k: assessment[k] for k in REVIEW_DECISION_FIELDS},
                "change_decisions": {
                    change: {k: data[k] for k in CHANGE_DECISION_FIELDS}
                    for change, (_, data) in changes.items()
                },
            }
    return stored


def test_a_version_takes_only_review_decisions_and_change_decisions_after_it_exists(
    tmp_path,
) -> None:
    # Both delivered scenarios, step by step, and a withdrawal in place of the last step
    # of each. The runbook names the commands found here.
    service = make_service(tmp_path)
    runner = ScenarioRunner(service)
    wrote: dict[str, set[str]] = {"review_decision": set(), "change_decisions": set()}

    def compare(before: dict[int, dict[str, Any]], matter_id: str, command: str) -> None:
        current = max(before)  # the current version when the command arrived
        after = _versions_as_stored(service, matter_id)
        for version, was in before.items():
            now = after[version]
            assert now["fixed"] == was["fixed"], (command, version)
            for part in wrote:
                if now[part] != was[part]:
                    # Only the current version is written, never one that was replaced.
                    assert version == current, (command, version, part)
                    wrote[part].add(command)

    for scenario_id, last in (("routine", "A12"), ("specialist-revision", "B44")):
        script = scenario(scenario_id)
        matter_id = script["matter_id"]
        before: dict[int, dict[str, Any]] = {}
        for step in script["steps"]:
            if step.get("restart"):
                continue
            record = runner.run_step(script, step)
            assert record["passed"], record
            if before:
                compare(before, matter_id, record["command"])
            before = _versions_as_stored(service, matter_id)
            if step.get("id") == last:
                break
        service.withdraw(
            OWNER, matter_id, revision(service, matter_id), note="Deal stopped before delivery."
        )
        compare(before, matter_id, "withdraw")
        assert len(before) == {"routine": 1, "specialist-revision": 3}[scenario_id]

    assert wrote == {
        "review_decision": {"approve", "request_revision", "withdraw"},
        "change_decisions": {"decide_change"},
    }
    [paragraph] = [
        p
        for p in RUNBOOK.read_text(encoding="utf-8").split("\n\n")
        if p.startswith("A matter version holds")
    ]
    assert "immutable" not in paragraph
    for command in sorted(wrote["review_decision"] | wrote["change_decisions"]):
        assert f"`{command}`" in paragraph, command


# -- tampering ---------------------------------------------------------------------


def test_altered_document_or_event_is_caught_by_the_gate(tmp_path) -> None:
    service = make_service(tmp_path)
    matter_id = run_until(service, "routine", "A11")
    with service.store.transaction() as connection:
        connection.execute(
            "UPDATE matter_versions SET document_blob = ? WHERE matter_id = ?",
            (build_synthetic_msa("specialist"), matter_id),
        )
    reasons = _reasons(service, OWNER, matter_id)
    assert "document_hash_matches" in reasons and "assessment_bound_to_version" in reasons

    with service.store.transaction() as connection:
        connection.execute(
            "UPDATE matter_versions SET document_blob = ? WHERE matter_id = ?",
            (build_synthetic_msa("routine"), matter_id),
        )
        connection.execute(
            "UPDATE events SET note = 'Final approval by the Board.' WHERE matter_id = ? AND event_type = 'approved'",
            (matter_id,),
        )
    assert "audit_chain_verified: matter event chain: event_hash mismatch" in _reasons(
        service, OWNER, matter_id
    )
    with pytest.raises(TransitionBlockedError):
        service.prepare_delivery(OWNER, matter_id, revision(service, matter_id))


# -- comments and blockers -----------------------------------------------------------


def test_comment_must_be_tied_to_something_that_exists(tmp_path) -> None:
    service = make_service(tmp_path)
    matter_id = run_until(service, "routine", "A06")
    with pytest.raises(InvalidCommandError, match="does not exist in version 1"):
        service.comment(
            OWNER,
            matter_id,
            revision(service, matter_id),
            anchor_kind="change",
            anchor_id="chg-nope",
            body="A comment on nothing.",
        )
    with pytest.raises(InvalidCommandError, match="blocked evidence reference"):
        target = change_id(service, matter_id, "audit-right")
        service.comment(
            OWNER,
            matter_id,
            revision(service, matter_id),
            anchor_kind="change",
            anchor_id=target,
            body="Check the audit scope.",
        )
        service.respond_comment(
            OWNER, matter_id, revision(service, matter_id), comment_id="c-001",
            body="See the customer's own memo.", evidence_refs=["confidential:customer-memo"],
        )  # fmt: skip
    paragraph_anchor = next(
        f"para:{p.text_hash}"
        for p in index_docx(build_synthetic_msa("routine")).paragraphs
        if "governed by the laws" in p.text
    )
    view = service.comment(
        OWNER, matter_id, revision(service, matter_id), anchor_kind="source_span",
        anchor_id=paragraph_anchor, body="Governing law is as expected.",
    )  # fmt: skip
    assert view["comments"][-1]["anchor_excerpt"].endswith("governed by the laws of Germany.")


def test_open_critical_comment_survives_regeneration_and_keeps_blocking(tmp_path) -> None:
    service = make_service(tmp_path)
    matter_id = run_until(service, "specialist-revision", "B26")
    roadmap = change_id(service, matter_id, "roadmap-commitment")
    service.comment(
        APPROVER_GC, matter_id, revision(service, matter_id), anchor_kind="change", anchor_id=roadmap,
        body="Product leadership must confirm that no date was promised orally.", severity="critical",
    )  # fmt: skip
    comment_id = service.view_matter(OWNER, matter_id)["comments"][-1]["comment_id"]

    # The customer sends a draft without the roadmap clause: the change disappears.
    service.amend_matter(
        REQUESTER, matter_id, revision(service, matter_id), reason="Customer dropped the roadmap clause.",
        document_name="customer-draft-2.docx", document=build_synthetic_msa("routine"),
    )  # fmt: skip
    view = service.view_matter(OWNER, matter_id)
    assert roadmap not in {c["id"] for c in view["changes"]}
    comment = next(c for c in view["comments"] if c["comment_id"] == comment_id)
    assert (comment["state"], comment["anchor_status"], comment["blocking"]) == (
        "open",
        "orphaned",
        True,
    )
    assert f"comment {comment_id}" in _reasons(service, OWNER, matter_id)

    service.resume_review(OWNER, matter_id, revision(service, matter_id))
    with pytest.raises(TransitionBlockedError) as blocked:
        service.approve(APPROVER_GC, matter_id, revision(service, matter_id), note=APPROVAL)
    assert "no_open_blockers" in _failing(blocked.value)
    # The criticised party cannot close it; resolving it needs evidence.
    with pytest.raises(PermissionDeniedError):
        service.resolve_comment(
            OWNER,
            matter_id,
            revision(service, matter_id),
            comment_id=comment_id,
            resolution="No longer relevant.",
            evidence_refs=["synthetic:x"],
        )
    with pytest.raises(InvalidCommandError, match="requires supporting evidence"):
        service.resolve_comment(
            APPROVER_GC,
            matter_id,
            revision(service, matter_id),
            comment_id=comment_id,
            resolution="Clause withdrawn by the customer.",
        )


def test_original_proposed_and_amended_wording_are_all_kept(tmp_path) -> None:
    service = make_service(tmp_path)
    matter_id = run_until(service, "specialist-revision", "B26")
    target = change_id(service, matter_id, "liability-cap")
    view = service.view_matter(OWNER, matter_id)
    change = next(c for c in view["changes"] if c["id"] == target)
    assert change["original_text"] == "three hundred percent (300%)"
    assert change["proposed_text"] == "one hundred percent (100%)"
    assert (
        change["amended_text"] == "two hundred percent (200%)" and change["decision"] == "amended"
    )
    assert "Fallback position" in change["decision_reason"]
    history = [d for d in view["decisions"] if d["target_id"] == target]
    assert [d["outcome"] for d in history] == ["clarification_requested", "amended"]
    support = next(s for s in view["source_support"] if s["change_id"] == target)
    assert support["wording_origin"].startswith("reviewer-authored amendment")
    assert [s["quote_check"]["status"] for s in support["sources"]] == [
        "quote_found",
        "quote_found",
    ]
    assert support["human_review"] == {
        "required": True,
        "question": "Does the cited source support this wording for this matter?",
        "status": "confirmed",
        "confirmed_by": OWNER,
    }
    with pytest.raises(InvalidCommandError, match="confirm that you checked the cited source"):
        service.decide_change(
            OWNER, matter_id, revision(service, matter_id), change_id=target, outcome="accepted"
        )


# -- the blocked matter ---------------------------------------------------------------


def test_no_actor_and_no_command_moves_the_blocked_matter(tmp_path) -> None:
    service = make_service(tmp_path)
    matter_id = run_until(service, "blocked", "C02")
    arguments: dict[str, dict[str, Any]] = {
        "assign": {"role": "final_approver", "assignee_id": APPROVER_GC},
        "comment": {
            "anchor_kind": "deliverable_section",
            "anchor_id": "executive_summary",
            "body": "Please just approve this.",
        },
        "respond_comment": {"comment_id": "c-001", "body": "Responding to move things on."},
        "resolve_comment": {
            "comment_id": "c-001",
            "resolution": "Resolved to unblock.",
            "evidence_refs": ["synthetic:x"],
        },
        "reopen_comment": {"comment_id": "c-001", "reason": "Reopening this one."},
        "decide_change": {
            "change_id": "chg-any",
            "outcome": "accepted",
            "source_support_confirmed": True,
        },
        "specialist_signoff": {"note": "No objection from privacy on this matter."},
        "request_revision": {"comment_ids": ["c-001"], "note": "Revise and resubmit this matter."},
        "submit_revision": {"note": "Revised as requested by review."},
        "approve": {"note": APPROVAL},
        "accept_delivery": {"note": "Accepting the package as delivered."},
        "answer_snooze": {"answer": "Answering a question nobody asked."},
    }
    # Legitimate ways to fix, pause or close it, each tested on this matter elsewhere.
    skipped = {"amend_matter", "restore_version", "withdraw", "decline", "mark_duplicate", "snooze"}
    actors = [a.actor_id for a in service.list_actors()]
    attempts = 0
    for command in service.COMMANDS:
        if command in skipped:
            continue
        for actor in actors:
            with pytest.raises(
                (
                    PermissionDeniedError,
                    TransitionBlockedError,
                    InvalidCommandError,
                    NotFoundError,
                    ExportBlockedError,
                )
            ):
                service.execute(
                    actor, matter_id, command, revision(service, matter_id), arguments.get(command)
                )
            attempts += 1
    assert attempts == 19 * len(actors)  # 17, and answering or ending a snooze that is not there
    assert state(service, matter_id) == "triage"
    with service.store.reading() as connection:
        for table in ("deliverable_manifests", "decisions"):
            count = connection.execute(
                f"SELECT COUNT(*) FROM {table} WHERE matter_id = ?", (matter_id,)
            ).fetchone()[
                0
            ]  # noqa: S608
            assert count == 0, table
    assert not (tmp_path / "exports").exists()
    view = service.view_matter(OWNER, matter_id)
    assert view["changes"] == []  # document processing was withheld
    assert {c["name"] for c in view["allowed"][0]["evidence"] if not c["ok"]} == {
        "sources_usable",
        "pilot_scope_met",
        "decision_authority_agreed",
    }
    assert "confidential" in json.dumps(
        view["allowed"]
    ) and "internal-pricing-memo" not in json.dumps(view["allowed"])


def test_blocked_matter_can_be_fixed_only_by_a_substantive_new_version(tmp_path) -> None:
    service = make_service(tmp_path)
    matter_id = run_until(service, "blocked", "C03")
    service.amend_matter(
        REQUESTER, matter_id, revision(service, matter_id), reason="Remove the restricted source and the uncapped request.",
        matter_fields={"source_refs": ["synthetic:customer-draft-msa-blocked"]},
        routing_fields={"uncapped_liability": False}, decision_authority="General Counsel",
    )  # fmt: skip
    view = service.complete_triage(OWNER, matter_id, revision(service, matter_id))
    assert view["matter"]["state"] == "assignment" and view["matter"]["current_version"] == 2
    assert len(view["changes"]) == 5


# -- exports -----------------------------------------------------------------------


def test_internal_review_export_is_a_separate_marked_draft(tmp_path) -> None:
    service = make_service(tmp_path)
    matter_id = run_until(service, "specialist-revision", "B11")
    view = service.view_matter(OWNER, matter_id)
    assert [m["kind"] for m in view["manifests"]] == ["internal_review"]
    folder = tmp_path / "exports" / matter_id / "v2" / "internal-review"
    assert sorted(p.name for p in folder.iterdir()) == [
        "draft-redline.docx",
        "internal-review.md",
        "manifest.json",
    ]
    text = (folder / "internal-review.md").read_text()
    assert text.splitlines()[2].startswith("> INTERNAL REVIEW DRAFT. Not approved.")
    assert "Not yet decided" in text
    assert "a change not yet decided is marked as a playbook proposal" in text
    with service.store.reading() as connection:
        proposed_at = service._version(connection, matter_id, 2)[1]["created_at"]
    tracked = list_tracked_changes((folder / "draft-redline.docx").read_bytes())
    assert tracked and {(c.author, c.date) for c in tracked} == {
        (DRAFT_PREFIX + PROPOSAL_LABEL, proposed_at[:19] + "Z")
    }
    assert view["matter"]["state"] == "review" and not view["eligibility"]["eligible"]
    assert not (tmp_path / "exports" / matter_id / "v2" / "delivery").exists()
    with pytest.raises(PermissionDeniedError):
        service.export_internal_review(REQUESTER, matter_id, revision(service, matter_id))


def test_delivery_package_contents_and_document_integrity(tmp_path) -> None:
    service = make_service(tmp_path)
    matter_id = run_until(service, "specialist-revision", "B44")
    folder = tmp_path / "exports" / matter_id / "v3" / "delivery"
    manifest = json.loads((folder / "manifest.json").read_text())
    assert manifest["kind"] == "delivery_package" and manifest["matter_version"] == 3
    assert manifest["external_delivery"] == "disabled" and manifest["eligibility"]["eligible"]
    for entry in manifest["files"]:
        assert hashlib.sha256((folder / entry["name"]).read_bytes()).hexdigest() == entry["sha256"]

    package = (folder / "customer-package.md").read_text()
    for heading in (
        "## 1. Executive summary",
        "## 2. Issue and deviation list",
        "## 3. Reviewed document",
        "## 4. Accepted exceptions",
        "## 5. Outstanding obligations",
        "## 6. Approval record",
        "## Verification performed and remaining human review",
    ):
        assert heading in package
    assert "Synthetic data." in package and "simulated local role" in package
    assert "2026-10-14" in package  # deadline derived from the amended signature date
    html = (folder / "customer-package.html").read_text()
    assert "http://" not in html and "https://" not in html and "<script" not in html

    source = build_synthetic_msa("specialist")
    reviewed = (folder / "reviewed-document.docx").read_bytes()
    assert read_paragraph_texts(reviewed, "rejected") == read_paragraph_texts(source, "accepted")
    accepted = "\n".join(read_paragraph_texts(reviewed, "accepted"))
    assert "two hundred percent (200%)" in accepted  # amended wording
    assert "ninety (90) days" in accepted  # accepted exception: customer wording stays
    issues = json.loads((folder / "issue-list.json").read_text())
    assert len(issues["issues"]) == 7 and len(issues["obligations"]) == 4
    assert all(o["owner"] != "unassigned" and o["due"] != "not set" for o in issues["obligations"])


def test_package_page_uses_shared_tokens_and_prints_the_notice_on_every_page(
    tmp_path, monkeypatch
) -> None:
    seen: list[deliverable.PackageData] = []
    render = deliverable.render_html

    def spy(data: deliverable.PackageData, *, draft: bool) -> str:
        seen.append(data)
        return render(data, draft=draft)

    monkeypatch.setattr(deliverable, "render_html", spy)
    service = make_service(tmp_path)
    matter_id = run_until(service, "specialist-revision", "B44")
    folder = tmp_path / "exports" / matter_id / "v3" / "delivery"
    page = (folder / "customer-package.html").read_text()
    style = page.split("<style>", 1)[1].split("</style>", 1)[0]
    assert style.startswith(TOKENS_CSS) and PRINT_CSS in style
    own, page_rules = style[len(TOKENS_CSS) :].split(PRINT_CSS, 1)
    assert not re.search(r"#[0-9a-fA-F]{3,6}\b", own)
    # D3: the notice and page number at the foot of every printed page, each numbered
    # section on a new page, in the light palette (the margin box cannot read tokens).
    assert page_rules.startswith("@page{")
    foot = (
        '@bottom-center{content:"'
        + deliverable.SYNTHETIC_NOTICE
        + ' Page " counter(page) " of " counter(pages);'
    )
    assert foot in page_rules
    colour = re.search(r"color:(#[0-9a-f]{6})\}", page_rules)
    assert colour and f"--muted:{colour.group(1)};" in TOKENS_CSS.split("@media", 1)[0]
    assert "section+section{break-before:page}" in page_rules
    assert "<meta name='viewport' content='width=device-width, initial-scale=1'>" in page
    body = page.split("<body>", 1)[1]
    assert body.startswith("<main>") and body.rstrip().endswith("</main></body></html>")
    # Every cell is labelled with its column header, for the stacked phone layout.
    tables = re.findall(r"<table>.*?</table>", page)
    assert tables
    for table in tables:
        headers = re.findall(r"<th>(.*?)</th>", table)
        for row in re.findall(r"<tbody>.*?</tbody>", table)[0].split("<tr>")[1:]:
            assert re.findall(r"<td data-label='(.*?)'>", row) == headers[: row.count("<td")]
            assert row.count("<td") == row.count("<td data-label=") == len(headers)
    assert "<script" not in page and "http://" not in page and "https://" not in page

    draft = render(seen[-1], draft=True)
    assert '@bottom-center{content:"' + deliverable.DRAFT_NOTICE + ' Page "' in draft
    assert deliverable.SYNTHETIC_NOTICE not in draft.split("</style>", 1)[0]


def test_css_string_escapes_quotes_and_refuses_line_breaks() -> None:
    assert deliverable._css_string('Say "no" \\ </style>') == 'Say \\"no\\" \\\\ \\3c /style>'
    with pytest.raises(ValueError):
        deliverable._css_string("two\nlines")
    with pytest.raises(ValueError):  # CSS treats a form feed as a line break too
        deliverable._css_string("form\ffeed")


def test_reviewed_document_names_the_deciding_role_and_decision_time(tmp_path) -> None:
    service = make_service(tmp_path, clock=TickingClock())
    matter_id = run_until(service, "specialist-revision", "B44")
    with service.store.reading() as connection:
        changes = service._changes(connection, matter_id, 3)
    decided = [c for c in changes if c.decision in {"accepted", "amended"}]
    labels = {OWNER: OWNER_LABEL, SPECIALIST: SPECIALIST_LABEL}
    expected = {c.id: (labels[str(c.decided_by)], str(c.decided_at)[:19] + "Z") for c in decided}
    assert len({date for _, date in expected.values()}) == len(decided) == 6
    folder = tmp_path / "exports" / matter_id / "v3" / "delivery"
    manifest = json.loads((folder / "manifest.json").read_text())
    reviewed = (folder / "reviewed-document.docx").read_bytes()
    tracked = list_tracked_changes(reviewed)
    assert {(c.author, c.date) for c in tracked} == set(expected.values())
    assert manifest["generated_at_utc"][:19] + "Z" not in {c.date for c in tracked}
    for change in decided:  # each inserted wording carries its own decision's mark
        if change.operation != "delete_paragraph":
            insertion = next(
                t for t in tracked if t.kind == "insertion" and t.text == change.final_text
            )
            assert (insertion.author, insertion.date) == expected[change.id]
    subprocessors = next(c for c in tracked if "Supplier may engage the subprocessors" in c.text)
    assert subprocessors.author == SPECIALIST_LABEL
    assert all(c.author.startswith("Simulated local role: ") for c in tracked)
    assert not any("Approved" in c.author or "DRAFT" in c.author for c in tracked)
    # Payment terms were rejected: the customer's wording stays and nothing is tracked there.
    assert not any(c.text == "thirty (30) days" or "ninety (90) days" in c.text for c in tracked)
    source = build_synthetic_msa("specialist")
    assert read_paragraph_texts(reviewed, "rejected") == read_paragraph_texts(source, "accepted")
    assert "two hundred percent (200%)" in "\n".join(read_paragraph_texts(reviewed, "accepted"))
    package = (folder / "customer-package.md").read_text()
    assert "Each tracked change names the simulated local role that decided it" in package
    assert "These names are not authenticated identities." in package


def test_draft_redline_names_deciders_and_does_not_depend_on_export_time(tmp_path) -> None:
    service = make_service(tmp_path)
    matter_id = run_until(service, "specialist-revision", "B19")
    folder = tmp_path / "exports" / matter_id / "v2" / "internal-review"
    service.export_internal_review(OWNER, matter_id, revision(service, matter_id))
    draft = (folder / "draft-redline.docx").read_bytes()
    summary = (folder / "internal-review.md").read_bytes()
    assert {c.author for c in list_tracked_changes(draft)} == {
        DRAFT_PREFIX + OWNER_LABEL,
        DRAFT_PREFIX + SPECIALIST_LABEL,
        DRAFT_PREFIX + PROPOSAL_LABEL,  # the liability cap waits for clarification
    }

    later = PilotService(
        service.store,
        clock=FixedClock("2030-01-01T00:00:00.000000Z"),
        export_root=tmp_path / "exports",
    )
    later.export_internal_review(OWNER, matter_id, revision(later, matter_id))
    assert (folder / "draft-redline.docx").read_bytes() == draft
    assert (folder / "internal-review.md").read_bytes() != summary


def test_package_writer_refuses_data_that_did_not_pass_the_delivery_gate(tmp_path) -> None:
    service = make_service(tmp_path)
    matter_id = run_until(service, "routine", "A09")
    with service.store.reading() as connection:
        ctx = service._context(connection, OWNER, matter_id, Stamp())
        draft = service._package_data(ctx, service._eligibility(ctx, "internal_review"))
        unapproved = service._package_data(ctx, service._eligibility(ctx, "delivery_package"))
    for data in (draft, unapproved):
        with pytest.raises(ExportBlockedError):
            deliverable.write_delivery_package(data, tmp_path / "rogue")
    assert not (tmp_path / "rogue").exists()


def test_closed_matter_accepts_no_further_commands(tmp_path) -> None:
    service = make_service(tmp_path)
    matter_id = run_until(service, "routine", "A13")
    for actor, command, args in (
        (OWNER, "prepare_delivery", None),
        (
            REQUESTER,
            "amend_matter",
            {"reason": "Late change after closing.", "facts": {"counterparty": "X"}},
        ),
        (APPROVER_LEAD, "approve", {"note": APPROVAL}),
    ):
        with pytest.raises(TransitionBlockedError, match="the matter is closed"):
            service.execute(actor, matter_id, command, revision(service, matter_id), args)
    assert (
        service.view_matter(OWNER, matter_id)["matter"]["closed_outcome"]
        == "delivered_locally_and_accepted"
    )

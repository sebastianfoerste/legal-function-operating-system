"""Onboarding tasks per role and the synthetic pilot participants."""

from __future__ import annotations

from src.pilot.models import Actor, Role

ONBOARDING_TASKS: dict[Role, tuple[tuple[str, str], ...]] = {
    "business_requester": (
        ("req-1", "Read the pilot charter: eligible matters, exclusions and stop conditions."),
        (
            "req-2",
            "Submit one practice intake with every required fact and the customer draft as DOCX.",
        ),
        (
            "req-3",
            "Confirm with the sponsor which approval tier may accept exceptions for your deals.",
        ),
        (
            "req-4",
            "Know that you answer clarification requests and accept the final package; you do not see internal review comments.",
        ),
    ),
    "matter_owner": (
        ("own-1", "Read the pilot charter and the runbook, including the stop conditions."),
        (
            "own-2",
            "Walk through triage: parent routing decision, pilot scope, source boundary, decision authority.",
        ),
        (
            "own-3",
            "Practise accept, reject, amend and clarify on a synthetic change, including the source-support confirmation.",
        ),
        ("own-4", "Practise a revision cycle and a stale-submission reload."),
        (
            "own-5",
            "Prepare one internal review export and one delivery package and verify the package against the store.",
        ),
    ),
    "specialist_reviewer": (
        ("spec-1", "Read the playbook rules in your specialty and their fallback positions."),
        (
            "spec-2",
            "Know that your sign-off is bound to one matter version and lapses when the matter changes.",
        ),
        ("spec-3", "Practise deciding a specialist change and recording a sign-off note."),
    ),
    "final_approver": (
        ("app-1", "Read the pilot charter and the export eligibility checks."),
        ("app-2", "Know that approval is bound to the exact reviewed version and reviewed state."),
        ("app-3", "Practise raising a critical comment, requesting a revision and approving."),
        (
            "app-4",
            "Confirm you will not approve a matter you requested, own or decided changes on.",
        ),
    ),
}

SYNTHETIC_ACTORS: tuple[Actor, ...] = (
    Actor(
        actor_id="syn-requester-revops",
        display_name="Synthetic Requester A (Revenue Operations)",
        role="business_requester",
    ),
    Actor(
        actor_id="syn-owner-legalops",
        display_name="Synthetic Matter Owner B (Commercial Counsel)",
        role="matter_owner",
    ),
    Actor(
        actor_id="syn-owner-second",
        display_name="Synthetic Matter Owner F (Commercial Counsel)",
        role="matter_owner",
    ),
    Actor(
        actor_id="syn-specialist-privacy",
        display_name="Synthetic Specialist C (Privacy Counsel)",
        role="specialist_reviewer",
        specialty="Privacy Counsel",
    ),
    Actor(
        actor_id="syn-approver-lead",
        display_name="Synthetic Approver D (Legal Ops Lead)",
        role="final_approver",
        approval_tier="Legal Ops Lead",
    ),
    Actor(
        actor_id="syn-approver-gc",
        display_name="Synthetic Approver E (General Counsel)",
        role="final_approver",
        approval_tier="General Counsel",
    ),
)


def missing_tasks(role: Role, completed: list[str]) -> list[str]:
    return [task_id for task_id, _ in ONBOARDING_TASKS[role] if task_id not in completed]

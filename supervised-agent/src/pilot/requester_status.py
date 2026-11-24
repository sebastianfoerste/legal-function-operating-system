"""Plain-language matter status for the business requester.

A derived view over the pilot states. It adds no state and no clock: the workflow, its
permissions and its event log are unchanged. Internal detail (risk, queue, approval
tier, playbook positions, internal comments) is never part of it. Two things a person
in legal typed for the requester are shown as written: the reason for a running snooze
(and its question, if any), and the reason legal closed the request in triage
(ADR 0010).

Each state has one stage, with two exceptions that the service decides and hands in. A
matter can stay ``ready_for_delivery`` after its delivery ended: a comment written,
resolved or reopened after the package was prepared (any change to the state of a
comment), or another final approver in place of the one who approved, leaves no approved
package to accept. The requester is then shown "In review", because legal has to act
before a package can be offered again (ADR 0011, note of 2026-11-23).

A matter can also be ``approved`` while ``prepare_delivery`` would be refused, so that no
package can be prepared from the approval as the matter stands. The approval may no
longer count (a comment written, resolved or reopened after it, or another final
approver), or it may never have allowed a package (a pilot scope hold applied when it was
given, or a listed matter document is unchecked). The requester is then shown "In review"
as well, and is not told that a package is being prepared. The explanation names no
cause: the causes differ, some of them are internal to legal, and the sentence is true in
every one (ADR 0011, note of 2026-11-24).

The service puts the facts together in one place, ``PilotService._requester_status``,
for the requester's matter view and for their matter list. The list shows the label of
this status, so it cannot show a requester a pilot state that the status contradicts.
"""

from __future__ import annotations

from typing import Any

# The stages a requester sees, in order. Several pilot states share one stage.
REQUESTER_STAGES = (
    ("draft", "Not yet submitted"),
    ("received", "Received by legal"),
    ("in_review", "In review"),
    ("approved", "Approved"),
    ("ready", "Ready for you"),
    ("closed", "Closed"),
)

_STAGE_OF_STATE = {
    "intake": "draft",
    "triage": "received",
    "assignment": "received",
    "review": "in_review",
    "revision_requested": "in_review",
    "revised": "in_review",
    "approved": "approved",
    "ready_for_delivery": "ready",
    "closed": "closed",
    "declined": "closed",
    "duplicate": "closed",
}

_EXPLANATION = {
    "draft": "Legal has not received this request yet. Submit it once the required facts are complete.",
    "received": "Legal has the request and is assigning a reviewer.",
    "in_review": "Reviewers are working on the customer's draft.",
    "approved": "The review is approved. The package for the customer is being prepared.",
    "ready": "The approved package is ready. Read it, then accept delivery.",
    "closed": "This request is closed.",
}
# Ready for delivery, but the delivery no longer stands. No stage is added: the matter is
# with legal again, which is what "In review" says. The first sentence is the reason the
# room shows where the package link was (``service.PACKAGE_CHANGED``), in other words.
_DELIVERY_ENDED = (
    "The package prepared earlier is no longer approved, because the matter changed after "
    "it was prepared. Legal has to review the matter again before a package is ready for you."
)
# Approved, but ``prepare_delivery`` would be refused. No stage is added here either: the
# matter is with legal again. The sentence names no cause, on purpose. A comment or an
# approver may have changed after the approval, or the approval may never have allowed a
# package, and the sentence has to be true of each. No reviewer, check, hold or comment is
# named to the requester.
_NO_PACKAGE_FROM_APPROVAL = (
    "The review was approved, but a package for the customer cannot be prepared from that "
    "approval as the matter stands now. Legal has to work on the matter again before a "
    "package is ready for you."
)
# A request legal closed in triage says so, whatever outcome text is stored.
_CLOSED_IN_TRIAGE = {
    "declined": ("Closed: declined by legal", "Legal declined this request. The reason is below."),
    "duplicate": (
        "Closed: duplicate of another matter",
        "Legal closed this request as a duplicate of another matter. The reason is below.",
    ),
}

WITHHELD = (
    "Internal review comments, risk rating, approval tier and negotiation positions "
    "are not shown here."
)


def requester_status(
    state: str,
    *,
    closed_outcome: str | None = None,
    open_questions: int = 0,
    snooze: dict[str, Any] | None = None,
    closure: dict[str, Any] | None = None,
    delivery_stands: bool = True,
    package_can_be_prepared: bool = True,
) -> dict[str, Any]:
    """Map a pilot state to the requester's stage, explanation and next action.

    ``snooze`` is the running snooze from ``snooze.latest_snooze``, if any; ``closure``
    is the reason legal recorded when it declined the request or marked it a duplicate.
    ``delivery_stands`` says whether the delivery package may be opened now. The service
    decides that once (``PilotService._standing_package``) and this function does not
    work it out again. It is read only for ``ready_for_delivery``: a matter in that state
    whose delivery has ended is shown "In review", and is not told that an approved
    package is ready or to accept delivery. Every other state ignores it.

    ``package_can_be_prepared`` says whether ``prepare_delivery`` would pass now. The
    service decides that too (``PilotService._requester_status`` asks the evidence the
    transition itself asks) and this function does not work it out again. It is read only
    for ``approved``: a matter in that state from whose approval no package can be
    prepared is shown "In review", and is not told that a package is being prepared.
    Every other state ignores it.
    """

    ended = state == "ready_for_delivery" and not delivery_stands
    no_package = state == "approved" and not package_can_be_prepared
    stage = "in_review" if ended or no_package else _STAGE_OF_STATE[state]
    label = dict(REQUESTER_STAGES)[stage]
    explanation = (
        _DELIVERY_ENDED
        if ended
        else _NO_PACKAGE_FROM_APPROVAL if no_package else _EXPLANATION[stage]
    )
    if stage == "closed" and closed_outcome:
        label = f"Closed: {closed_outcome.replace('_', ' ')}"
    if state in _CLOSED_IN_TRIAGE:
        label, explanation = _CLOSED_IN_TRIAGE[state]
    if stage == "draft":
        action = "Complete the required facts, then submit."
    elif stage == "ready":
        action = "Accept delivery."
    else:
        action = "No action needed from you."
    # An open question addressed to the requester is the one thing that can need
    # them mid-review, so it overrides the stage's default action.
    if open_questions and stage != "closed":
        action = (
            "Answer the open question below."
            if open_questions == 1
            else f"Answer the {open_questions} open questions below."
        )
    paused = None
    if snooze and stage == "received":
        paused = {key: snooze.get(key) for key in ("since", "until", "question", "reason")}
        explanation = (
            f"Legal paused this request until {paused['until']}. The reason is below."
            if paused["until"]
            else "Legal paused this request until you answer its question. The reason is below."
        )
        if paused["question"]:
            action = "Answer legal's question below."
    return {
        "stage": stage,
        "label": label,
        "explanation": explanation,
        "your_action": action,
        "waiting_on_you": stage != "closed"
        and (
            bool(open_questions)
            or stage in {"draft", "ready"}
            or bool(paused and paused["question"])
        ),
        "stages": [
            {"id": sid, "label": slabel, "current": sid == stage}
            for sid, slabel in REQUESTER_STAGES
        ],
        "snooze": paused,
        "closure": closure if stage == "closed" else None,
        "withheld": WITHHELD,
    }

"""Plain-language matter status for the business requester.

A derived view over the nine pilot states. It adds no state and no clock: the
workflow, its permissions and its event log are unchanged. Internal detail (risk,
queue, approval tier, playbook positions, internal comments) is never part of it.
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
}

_EXPLANATION = {
    "draft": "Legal has not received this request yet. Submit it once the required facts are complete.",
    "received": "Legal has the request and is assigning a reviewer.",
    "in_review": "Reviewers are working on the customer's draft.",
    "approved": "The review is approved. The package for the customer is being prepared.",
    "ready": "The approved package is ready. Read it, then accept delivery.",
    "closed": "This request is closed.",
}

WITHHELD = (
    "Internal review comments, risk rating, approval tier and negotiation positions "
    "are not shown here."
)


def requester_status(
    state: str, *, closed_outcome: str | None = None, open_questions: int = 0
) -> dict[str, Any]:
    """Map a pilot state to the requester's stage, explanation and next action."""

    stage = _STAGE_OF_STATE[state]
    label = dict(REQUESTER_STAGES)[stage]
    explanation = _EXPLANATION[stage]
    if stage == "closed" and closed_outcome:
        label = f"Closed: {closed_outcome.replace('_', ' ')}"
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
    return {
        "stage": stage,
        "label": label,
        "explanation": explanation,
        "your_action": action,
        "waiting_on_you": stage != "closed"
        and (bool(open_questions) or stage in {"draft", "ready"}),
        "stages": [
            {"id": sid, "label": slabel, "current": sid == stage}
            for sid, slabel in REQUESTER_STAGES
        ],
        "withheld": WITHHELD,
    }

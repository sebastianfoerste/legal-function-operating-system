"""Required facts before submission, requester status and playbook positions in the room."""

import pytest

from src.pilot.api import PilotApi
from src.pilot.models import REQUIRED_FACTS, required_fact_checklist
from src.pilot.requester_status import REQUESTER_STAGES, requester_status
from src.pilot.review_room import REVIEW_ROOM_HTML
from src.pilot.state_machine import STATES, TRANSITIONS
from tests.pilot_support import OWNER, REQUESTER, make_service, run_until


def _call(api, method, path, actor=None, body=None):
    headers = {"X-Pilot-Actor": actor} if actor else {}
    status, payload, _ = api.handle(method, "/pilot/api" + path, headers, body)
    return status, payload


def _command(api, actor, matter_id, command, args=None):
    revision = _call(api, "GET", f"/matters/{matter_id}", actor)[1]["matter"]["revision"]
    body = {"command": command, "expected_revision": revision, "args": args or {}}
    return _call(api, "POST", f"/matters/{matter_id}/commands", actor, body)


def test_checklist_uses_the_same_blank_test_as_the_intake_gate() -> None:
    items = required_fact_checklist({"counterparty": "Example SE", "business_owner": "  "})
    assert [i["key"] for i in items] == list(REQUIRED_FACTS)
    assert [i["present"] for i in items] == [True, False, False, False, False]
    assert all(i["label"] for i in items)


def test_scenarios_show_their_missing_fact_before_a_matter_exists(tmp_path) -> None:
    api = PilotApi(make_service(tmp_path))
    scenarios = {s["scenario_id"]: s for s in _call(api, "GET", "/actors")[1]["scenarios"]}
    missing = [
        f["key"] for f in scenarios["specialist-revision"]["required_facts"] if not f["present"]
    ]
    assert missing == ["business_owner"]
    assert all(f["present"] for f in scenarios["routine"]["required_facts"])


def test_facts_completed_on_the_form_make_the_first_version_submittable(tmp_path) -> None:
    api = PilotApi(make_service(tmp_path))
    body = {
        "scenario_id": "specialist-revision",
        "matter_id": "PM-FORM-1",
        "facts": {"business_owner": "Synthetic Account Executive G"},
    }
    status, view = _call(api, "POST", "/matters", REQUESTER, body)
    assert status == 201 and all(f["present"] for f in view["required_facts"])
    status, view = _command(api, REQUESTER, "PM-FORM-1", "submit_intake")
    # Rehearsal step B02 needed an amendment and a second version; the form avoids both.
    assert status == 200 and view["matter"]["state"] == "triage"
    assert view["matter"]["current_version"] == 1


def test_without_the_form_the_gate_still_refuses_the_missing_fact(tmp_path) -> None:
    api = PilotApi(make_service(tmp_path))
    _call(
        api,
        "POST",
        "/matters",
        REQUESTER,
        {"scenario_id": "specialist-revision", "matter_id": "PM-FORM-2"},
    )
    status, payload = _command(api, REQUESTER, "PM-FORM-2", "submit_intake")
    assert status == 409 and "missing fact: business_owner" in payload["message"]


@pytest.mark.parametrize(
    "facts",
    [{"risk": "low"}, {"business_owner": 7}, ["business_owner"]],
)
def test_the_form_may_only_supply_required_facts_as_text(tmp_path, facts) -> None:
    api = PilotApi(make_service(tmp_path))
    body = {"scenario_id": "routine", "matter_id": "PM-FORM-3", "facts": facts}
    status, payload = _call(api, "POST", "/matters", REQUESTER, body)
    assert (status, payload["error"]) == (400, "pilot_error")


def test_every_pilot_state_has_one_requester_stage() -> None:
    states = {t.target for t in TRANSITIONS} | {"intake"}
    stage_ids = [stage for stage, _ in REQUESTER_STAGES]
    for name in states:
        status = requester_status(name)
        assert status["stage"] in stage_ids
        assert [s["current"] for s in status["stages"]].count(True) == 1


def test_requester_status_names_the_next_step_and_what_is_withheld() -> None:
    assert requester_status("intake")["waiting_on_you"]
    assert requester_status("review")["your_action"] == "No action needed from you."
    assert requester_status("review", open_questions=2)["your_action"].startswith("Answer the 2")
    closed = requester_status(
        "closed", closed_outcome="withdrawn_without_delivery", open_questions=1
    )
    assert closed["label"] == "Closed: withdrawn without delivery" and not closed["waiting_on_you"]
    assert "negotiation positions" in requester_status("review")["withheld"]


READY = "The approved package is ready. Read it, then accept delivery."
DELIVERY_ENDED = (
    "The package prepared earlier is no longer approved, because the matter changed after "
    "it was prepared. Legal has to review the matter again before a package is ready for you."
)
SNOOZE = {
    "since": "2026-11-02T08:00:00Z",
    "until": None,
    "question": "Who signs?",
    "reason": "Open",
}
CLOSURE = {"reason": "Outside the pilot charter.", "original_matter_id": None}


def test_a_standing_delivery_is_ready_for_the_requester_as_before() -> None:
    ready = requester_status("ready_for_delivery")
    assert (ready["stage"], ready["label"], ready["explanation"]) == (
        "ready",
        "Ready for you",
        READY,
    )
    assert ready["your_action"] == "Accept delivery." and ready["waiting_on_you"]
    # Saying that the delivery stands changes nothing: it is what the function assumed.
    assert requester_status("ready_for_delivery", delivery_stands=True) == ready
    asked = requester_status("ready_for_delivery", open_questions=1, delivery_stands=True)
    assert asked == requester_status("ready_for_delivery", open_questions=1)
    assert (asked["stage"], asked["your_action"]) == ("ready", "Answer the open question below.")


def test_an_ended_delivery_in_ready_for_delivery_is_shown_in_review() -> None:
    # The matter stayed ready for delivery, but a later comment or another final approver
    # ended the delivery. No approved package is ready and there is nothing to accept.
    status = requester_status("ready_for_delivery", delivery_stands=False)
    assert (status["stage"], status["label"]) == ("in_review", "In review")
    assert status["explanation"] == DELIVERY_ENDED
    assert status["your_action"] == "No action needed from you."
    assert not status["waiting_on_you"]
    # One of the six stages is current, and the list is the six stages as they are.
    assert [(s["id"], s["label"]) for s in status["stages"]] == list(REQUESTER_STAGES)
    assert [s["id"] for s in status["stages"] if s["current"]] == ["in_review"]
    assert (status["snooze"], status["closure"]) == (None, None)
    # Everything else is what "In review" gives a matter in review.
    in_review = requester_status("review")
    assert {**status, "explanation": in_review["explanation"]} == in_review

    # An open question to the requester still overrides the action.
    one = requester_status("ready_for_delivery", open_questions=1, delivery_stands=False)
    assert (one["stage"], one["explanation"]) == ("in_review", DELIVERY_ENDED)
    assert one["your_action"] == "Answer the open question below." and one["waiting_on_you"]
    two = requester_status("ready_for_delivery", open_questions=2, delivery_stands=False)
    assert two["your_action"] == "Answer the 2 open questions below." and two["waiting_on_you"]


@pytest.mark.parametrize("state", [s for s in STATES if s != "ready_for_delivery"])
def test_every_other_state_ignores_whether_a_delivery_stands(state: str) -> None:
    for given in (
        {},
        {"open_questions": 1},
        {"closed_outcome": "withdrawn_without_delivery"},
        {"closed_outcome": "delivered_locally_and_accepted", "open_questions": 2},
        {"snooze": SNOOZE},
        {"closure": CLOSURE},
    ):
        expected = requester_status(state, **given)
        for stands in (True, False):
            assert requester_status(state, delivery_stands=stands, **given) == expected, given
        assert expected["explanation"] != DELIVERY_ENDED


def test_requester_view_carries_status_but_no_internal_detail(tmp_path) -> None:
    api = PilotApi(make_service(tmp_path))
    matter = run_until(api.service, "routine", "A06")
    status, view = _call(api, "GET", f"/matters/{matter}", REQUESTER)
    assert status == 200 and view["requester_status"]["stage"] == "in_review"
    assert not {"changes", "findings", "version", "comments"} & set(view)
    owner = _call(api, "GET", f"/matters/{matter}", OWNER)[1]
    fallback = owner["changes"][0]["playbook_position"]["fallback_position"]
    assert fallback and fallback not in str(view)


def test_each_change_shows_the_playbook_wording_it_was_measured_against(tmp_path) -> None:
    service = make_service(tmp_path)
    api = PilotApi(service)
    matter = run_until(service, "routine", "A06")
    view = _call(api, "GET", f"/matters/{matter}", OWNER)[1]
    for change in view["changes"]:
        position = change["playbook_position"]
        assert position["rule_id"] == change["rule_id"]
        assert position["standard_position"] and position["fallback_position"]


def test_review_room_takes_decisions_in_labelled_inline_forms() -> None:
    assert "window.prompt" not in REVIEW_ROOM_HTML and "window.confirm" not in REVIEW_ROOM_HTML
    assert 'aria-live="polite"' in REVIEW_ROOM_HTML and 'aria-label="Matters"' in REVIEW_ROOM_HTML
    for control in ("assignee", "anchor", "severity", "comment-body", "actor", "effort"):
        assert f'for: "{control}"' in REVIEW_ROOM_HTML or f'for="{control}"' in REVIEW_ROOM_HTML
    assert (
        "There is a problem" in REVIEW_ROOM_HTML
        and "Evidence cited in this thread" in REVIEW_ROOM_HTML
    )
    assert "/*TOKENS*/" not in REVIEW_ROOM_HTML and "--on-accent" in REVIEW_ROOM_HTML


def test_review_room_guards_the_cases_the_browser_test_covers() -> None:
    # Static counterparts of tests/test_review_room_browser.py, for runs without a browser.
    assert "table.changes tr[hidden]{display:none}" in REVIEW_ROOM_HTML
    assert "a revision request must name an open comment" in REVIEW_ROOM_HTML
    assert "(focusable || target).focus()" in REVIEW_ROOM_HTML
    assert "No matter was opened" in REVIEW_ROOM_HTML

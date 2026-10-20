"""Required facts before submission, requester status and playbook positions in the room."""

import pytest

from src.pilot.api import PilotApi
from src.pilot.models import REQUIRED_FACTS, required_fact_checklist
from src.pilot.requester_status import REQUESTER_STAGES, requester_status
from src.pilot.state_machine import TRANSITIONS
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

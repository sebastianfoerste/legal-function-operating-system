import base64
import json
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

from src.pilot.api import PilotApi
from src.pilot.fixtures import build_synthetic_msa
from src.pilot.review_room import REVIEW_ROOM_HTML
from tests.pilot_support import (
    APPROVER_GC,
    APPROVER_LEAD,
    OTHER_OWNER,
    OWNER,
    REQUESTER,
    make_service,
    run_until,
    scenario,
)

NOTE = "Both deviations revert to the standard position; approved for return to the customer."


def _api(tmp_path) -> PilotApi:
    return PilotApi(make_service(tmp_path))


def _call(api, method, path, actor=None, body=None):
    headers = {"X-Pilot-Actor": actor} if actor else {}
    status, payload, _ = api.handle(method, "/pilot/api" + path, headers, body)
    return status, payload


def _command(api, actor, matter_id, command, args=None, revision=None):
    if revision is None:
        revision = _call(api, "GET", f"/matters/{matter_id}", actor)[1]["matter"]["revision"]
    body = {"command": command, "expected_revision": revision, "args": args or {}}
    return _call(api, "POST", f"/matters/{matter_id}/commands", actor, body)


def test_every_data_route_needs_an_actor_and_the_actor_list_says_what_it_is(tmp_path) -> None:
    api = _api(tmp_path)
    status, payload = _call(api, "GET", "/actors")
    assert status == 200 and "not authentication" in payload["identity_notice"]
    assert all(actor["synthetic"] for actor in payload["actors"])
    assert set(payload["onboarding_tasks"]) == {
        "business_requester",
        "matter_owner",
        "specialist_reviewer",
        "final_approver",
    }
    for method, path in (
        ("GET", "/matters"),
        ("GET", "/matters/PM-X"),
        ("POST", "/matters/PM-X/commands"),
    ):
        status, payload = _call(api, method, path)
        assert (status, payload["error"]) == (401, "actor_required")
    status, payload = _call(api, "GET", "/matters", "Head of Legal")
    assert (status, payload["error"]) == (403, "permission_denied")


def test_complete_journey_through_the_api(tmp_path) -> None:
    api = _api(tmp_path)
    status, view = _call(
        api, "POST", "/matters", REQUESTER, {"scenario_id": "routine", "matter_id": "PM-API-1"}
    )
    assert status == 201 and view["matter"]["state"] == "intake"
    matter = "PM-API-1"
    assert _command(api, REQUESTER, matter, "submit_intake")[0] == 200
    assert _command(api, OWNER, matter, "complete_triage")[0] == 200
    assert (
        _command(
            api, OWNER, matter, "assign", {"role": "final_approver", "assignee_id": APPROVER_LEAD}
        )[0]
        == 200
    )
    status, view = _command(api, OWNER, matter, "start_review")
    assert status == 200 and view["view"] == "review_room" and len(view["changes"]) == 2
    for change in view["changes"]:
        status, _ = _command(
            api, OWNER, matter, "decide_change",
            {"change_id": change["id"], "outcome": "accepted", "source_support_confirmed": True},
        )  # fmt: skip
        assert status == 200
    assert _command(api, APPROVER_LEAD, matter, "approve", {"note": NOTE})[0] == 200
    status, view = _command(api, OWNER, matter, "prepare_delivery")
    assert status == 200 and view["matter"]["state"] == "ready_for_delivery"

    status, page, content_type = api.handle(
        "GET", f"/pilot/api/matters/{matter}/package", {"X-Pilot-Actor": REQUESTER}
    )
    assert status == 200 and content_type.startswith("text/html") and "Customer package:" in page
    status, view = _command(
        api,
        REQUESTER,
        matter,
        "accept_delivery",
        {"note": "Received and understood by the account team."},
    )
    assert status == 200 and view["matter"]["state"] == "closed"
    status, history = _call(api, "GET", f"/matters/{matter}/history", OWNER)
    assert status == 200 and history["audit_chain"]["verified"]


def test_stale_and_out_of_sequence_requests_get_explicit_answers(tmp_path) -> None:
    api = _api(tmp_path)
    matter = run_until(api.service, "routine", "A06")
    loaded = _call(api, "GET", f"/matters/{matter}", OWNER)[1]
    change = loaded["changes"][0]["id"]
    accept = {"change_id": change, "outcome": "accepted", "source_support_confirmed": True}
    assert (
        _command(api, OWNER, matter, "decide_change", accept, loaded["matter"]["revision"])[0]
        == 200
    )

    status, payload = _command(
        api, OWNER, matter, "decide_change", accept, loaded["matter"]["revision"]
    )
    assert (status, payload["error"]) == (409, "stale_submission")
    assert payload["current_revision"] == loaded["matter"]["revision"] + 1

    # Skipping the screen sequence: ask for the package, then for delivery, before approval.
    status, payload = _call(api, "GET", f"/matters/{matter}/package", OWNER)
    assert (status, payload["error"]) == (403, "permission_denied")
    status, payload = _command(api, OWNER, matter, "prepare_delivery")
    assert (status, payload["error"]) == (409, "transition_blocked")
    status, payload = _command(api, APPROVER_LEAD, matter, "approve", {"note": NOTE})
    assert (status, payload["error"]) == (409, "transition_blocked")
    assert {e["name"] for e in payload["evidence"] if not e["ok"]} == {"changes_decided"}

    for actor in (OTHER_OWNER, APPROVER_GC):
        status, payload = _command(api, actor, matter, "export_internal_review", revision=1)
        assert (status, payload["error"]) == (403, "permission_denied")
    status, payload = _command(api, OWNER, matter, "grant_myself_approval")
    assert (status, payload["error"]) == (422, "invalid_command")
    status, payload = _call(
        api, "POST", f"/matters/{matter}/commands", OWNER, {"command": "approve"}
    )
    assert status == 400


def test_interface_cannot_set_scripted_time_or_spoof_another_actor(tmp_path) -> None:
    api = _api(tmp_path)
    matter = run_until(api.service, "routine", "A06")
    view = _call(api, "GET", f"/matters/{matter}", OWNER)[1]
    body = {
        "command": "comment",
        "expected_revision": view["matter"]["revision"],
        "effort_minutes": 7,
        "fixture_at": "2020-01-01T00:00:00Z",
        "actor_id": APPROVER_LEAD,
        "args": {
            "anchor_kind": "finding",
            "anchor_id": view["findings"][0]["key"],
            "body": "Recorded by the owner.",
        },
    }
    assert _call(api, "POST", f"/matters/{matter}/commands", OWNER, body)[0] == 200
    event = _call(api, "GET", f"/matters/{matter}/history", OWNER)[1]["events"][-1]
    assert (event["actor_id"], event["fixture_at"], event["effort_minutes"]) == (OWNER, None, 7)


def test_matter_can_be_opened_from_a_supplied_intake_and_document(tmp_path) -> None:
    api = _api(tmp_path)
    body = {
        "intake": scenario("routine")["intake"],
        "document_name": "upload.docx",
        "document_base64": base64.b64encode(build_synthetic_msa("routine")).decode(),
        "matter_id": "PM-API-2",
    }
    status, view = _call(api, "POST", "/matters", REQUESTER, body)
    assert status == 201 and view["matter"]["matter_id"] == "PM-API-2"
    assert _call(api, "POST", "/matters", OWNER, body)[0] == 403  # only a requester opens a matter
    body["document_base64"] = "not base64!"
    assert _call(api, "POST", "/matters", REQUESTER, {**body, "matter_id": "PM-API-3"})[0] == 400
    body["intake"] = {**body["intake"], "value_band": "enormous"}
    assert _call(api, "POST", "/matters", REQUESTER, {**body, "matter_id": "PM-API-4"})[0] == 422


def test_review_room_page_is_self_contained_and_labels_simulated_roles() -> None:
    assert "http://" not in REVIEW_ROOM_HTML and "https://" not in REVIEW_ROOM_HTML
    assert "Simulated local role" in REVIEW_ROOM_HTML
    assert "is not authentication" in REVIEW_ROOM_HTML
    assert "expected_revision" in REVIEW_ROOM_HTML and "stale_submission" in REVIEW_ROOM_HTML
    assert "innerHTML" not in REVIEW_ROOM_HTML  # reviewer text is never parsed as markup


def test_runtime_server_serves_the_review_room(tmp_path, monkeypatch) -> None:
    import runtime_agent.app as app

    monkeypatch.setenv("PILOT_DB", str(tmp_path / "pilot.sqlite3"))
    monkeypatch.setenv("PILOT_EXPORT_ROOT", str(tmp_path / "exports"))
    monkeypatch.setattr(app, "_pilot_api", None)
    try:
        server = ThreadingHTTPServer(("127.0.0.1", 0), app.RuntimeHandler)
    except PermissionError:
        pytest.skip("this environment does not permit binding a local port")
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        with urllib.request.urlopen(f"{base}/pilot", timeout=5) as response:
            assert "Pilot review room" in response.read().decode()
        with urllib.request.urlopen(f"{base}/pilot/api/actors", timeout=5) as response:
            assert len(json.load(response)["actors"]) == 6
        request = urllib.request.Request(
            f"{base}/pilot/api/matters",
            data=json.dumps({"scenario_id": "routine", "matter_id": "PM-HTTP-1"}).encode(),
            headers={"Content-Type": "application/json", "X-Pilot-Actor": REQUESTER},
        )
        with urllib.request.urlopen(request, timeout=5) as response:
            assert response.status == 201
        with pytest.raises(urllib.error.HTTPError) as refused:
            urllib.request.urlopen(f"{base}/pilot/api/matters", timeout=5)
        assert refused.value.code == 401
        with urllib.request.urlopen(f"{base}/health", timeout=5) as response:
            assert json.load(response)["status"] == "ok"
    finally:
        server.shutdown()
        server.server_close()

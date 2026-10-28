"""Presence: who else has a matter open, in memory only, labelled as simulated roles."""

from src.pilot.api import PilotApi
from src.pilot.presence import PRESENCE_NOTICE, PresenceBoard
from src.pilot.review_room import REVIEW_ROOM_HTML
from tests.pilot_support import (
    APPROVER_GC,
    APPROVER_LEAD,
    OWNER,
    REQUESTER,
    make_service,
    run_until,
)


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def _call(api, method, path, actor=None, body=None):
    headers = {"X-Pilot-Actor": actor} if actor else {}
    status, payload, _ = api.handle(method, "/pilot/api" + path, headers, body)
    return status, payload


def _setup(tmp_path):
    clock = FakeClock()
    service = make_service(tmp_path)
    matter = run_until(service, "routine", "A06")  # in review; owner and approver lead assigned
    return PilotApi(service, PresenceBoard(window_seconds=120, clock=clock)), matter, clock


def test_board_shows_others_within_the_window_in_a_stable_order() -> None:
    clock = FakeClock()
    board = PresenceBoard(window_seconds=120, clock=clock)
    board.seen("PM-1", "syn-b", "Synthetic B", "final_approver", 4)
    board.seen("PM-1", "syn-a", "Synthetic A", "specialist_reviewer", 5)
    board.seen("PM-1", "syn-me", "Me", "matter_owner", 5)
    board.seen("PM-2", "syn-c", "Synthetic C", "final_approver", 1)
    clock.now += 30
    others = board.others("PM-1", "syn-me", current_revision=5)
    assert [o["actor_id"] for o in others] == ["syn-a", "syn-b"]
    assert [(o["seconds_ago"], o["behind"]) for o in others] == [(30, False), (30, True)]
    clock.now += 91
    assert board.others("PM-1", "syn-me", current_revision=5) == []


def test_reviewers_see_each_other_with_the_simulated_role_notice(tmp_path) -> None:
    api, matter, clock = _setup(tmp_path)
    status, view = _call(api, "GET", f"/matters/{matter}", APPROVER_LEAD)
    assert status == 200 and view["also_open_by"] == []
    clock.now += 40
    status, view = _call(api, "GET", f"/matters/{matter}", OWNER)
    assert view["presence_notice"] == PRESENCE_NOTICE and "not authentication" in PRESENCE_NOTICE
    [other] = view["also_open_by"]
    assert (other["actor_id"], other["seconds_ago"], other["behind"]) == (APPROVER_LEAD, 40, False)
    assert other["revision"] == view["matter"]["revision"]


def test_requesters_are_neither_shown_nor_recorded(tmp_path) -> None:
    api, matter, _ = _setup(tmp_path)
    status, view = _call(api, "GET", f"/matters/{matter}", REQUESTER)
    assert status == 200 and "also_open_by" not in view and "presence_notice" not in view
    assert _call(api, "GET", f"/matters/{matter}", OWNER)[1]["also_open_by"] == []
    status, payload = _call(api, "POST", f"/matters/{matter}/presence", REQUESTER, {"revision": 1})
    assert (status, payload["error"]) == (403, "permission_denied")


def test_check_in_refreshes_presence_and_reports_a_newer_revision(tmp_path) -> None:
    api, matter, clock = _setup(tmp_path)
    loaded = _call(api, "GET", f"/matters/{matter}", APPROVER_LEAD)[1]["matter"]["revision"]
    owner_view = _call(api, "GET", f"/matters/{matter}", OWNER)[1]
    # The owner writes a comment; the approver's open room checks in with its old revision.
    body = {
        "command": "comment",
        "expected_revision": owner_view["matter"]["revision"],
        "args": {
            "anchor_kind": "finding",
            "anchor_id": owner_view["findings"][0]["key"],
            "body": "Checked against the playbook.",
        },
    }
    assert _call(api, "POST", f"/matters/{matter}/commands", OWNER, body)[0] == 200
    clock.now += 100
    status, payload = _call(
        api, "POST", f"/matters/{matter}/presence", APPROVER_LEAD, {"revision": loaded}
    )
    assert status == 200 and payload["current_revision"] == loaded + 1
    [owner] = payload["also_open_by"]
    assert (owner["actor_id"], owner["revision"], owner["behind"]) == (OWNER, loaded + 1, False)
    # 100 s after the owner's last write, the owner is still inside the window; at 121 s not.
    clock.now += 21
    payload = _call(
        api, "POST", f"/matters/{matter}/presence", APPROVER_LEAD, {"revision": loaded}
    )[1]
    assert payload["also_open_by"] == []
    # The owner now sees the approver on an older revision.
    [approver] = _call(api, "GET", f"/matters/{matter}", OWNER)[1]["also_open_by"]
    assert (approver["revision"], approver["behind"]) == (loaded, True)


def test_check_in_needs_access_and_a_real_revision(tmp_path) -> None:
    api, matter, _ = _setup(tmp_path)
    current = _call(api, "GET", f"/matters/{matter}", OWNER)[1]["matter"]["revision"]
    path = f"/matters/{matter}/presence"
    assert _call(api, "POST", path, None, {"revision": current})[0] == 401
    assert _call(api, "POST", path, APPROVER_GC, {"revision": current})[0] == 403  # not assigned
    assert _call(api, "POST", path, "Head of Legal", {"revision": current})[0] == 403
    for revision in (None, "1", True, -1, current + 1):
        status, payload = _call(api, "POST", path, OWNER, {"revision": revision})
        assert (status, payload["error"]) == (400, "pilot_error"), revision


def test_others_on_your_own_revision_are_not_marked_older_after_the_matter_moves(tmp_path) -> None:
    api, matter, clock = _setup(tmp_path)
    loaded = _call(api, "GET", f"/matters/{matter}", APPROVER_LEAD)[1]["matter"]["revision"]
    owner_view = _call(api, "GET", f"/matters/{matter}", OWNER)[1]
    # A third reviewer has the same revision open as the approver.
    api.presence.seen(matter, "syn-third", "Synthetic Reviewer T", "specialist_reviewer", loaded)
    body = {
        "command": "comment",
        "expected_revision": owner_view["matter"]["revision"],
        "args": {
            "anchor_kind": "finding",
            "anchor_id": owner_view["findings"][0]["key"],
            "body": "Checked against the playbook.",
        },
    }
    assert _call(api, "POST", f"/matters/{matter}/commands", OWNER, body)[0] == 200
    clock.now += 5
    payload = _call(
        api, "POST", f"/matters/{matter}/presence", APPROVER_LEAD, {"revision": loaded}
    )[1]
    assert payload["current_revision"] == loaded + 1  # the approver is behind ...
    flags = {o["actor_id"]: (o["revision"], o["behind"]) for o in payload["also_open_by"]}
    # ... but nobody is older than the approver: the third reviewer is on the same revision.
    assert flags == {OWNER: (loaded + 1, False), "syn-third": (loaded, False)}


def test_expired_entries_are_dropped_for_every_matter() -> None:
    clock = FakeClock()
    board = PresenceBoard(window_seconds=120, clock=clock)
    board.seen("PM-1", "syn-a", "Synthetic A", "matter_owner", 1)
    board.seen("PM-2", "syn-b", "Synthetic B", "final_approver", 1)
    clock.now += 121
    # Reading one matter, or noting someone on another, clears every expired entry.
    board.seen("PM-3", "syn-c", "Synthetic C", "matter_owner", 1)
    assert set(board._seen) == {"PM-3"}
    clock.now += 121
    assert board.others("PM-3", "syn-z", current_revision=1) == []
    assert board._seen == {}


def test_presence_leaves_the_store_and_event_log_untouched(tmp_path) -> None:
    api, matter, clock = _setup(tmp_path)

    def dump() -> str:
        with api.service.store.reading() as connection:
            return "\n".join(connection.iterdump())

    before, history = dump(), _call(api, "GET", f"/matters/{matter}/history", OWNER)[1]
    for actor in (OWNER, APPROVER_LEAD, OWNER):
        clock.now += 5
        current = _call(api, "GET", f"/matters/{matter}", actor)[1]["matter"]["revision"]
        assert (
            _call(api, "POST", f"/matters/{matter}/presence", actor, {"revision": current})[0]
            == 200
        )
    # Refused check-ins write nothing either: a requester, and a reviewer not on the matter.
    assert _call(api, "POST", f"/matters/{matter}/presence", REQUESTER, {"revision": 1})[0] == 403
    assert _call(api, "POST", f"/matters/{matter}/presence", APPROVER_GC, {"revision": 1})[0] == 403
    assert dump() == before
    after = _call(api, "GET", f"/matters/{matter}/history", OWNER)[1]
    assert after == history and after["audit_chain"]["verified"]


def test_review_room_labels_presence_as_simulated_and_holds_no_clock_in_live_text() -> None:
    assert "Also open in the last two minutes (simulated local role, not authentication)" in (
        REVIEW_ROOM_HTML
    )
    assert "seconds_ago" not in REVIEW_ROOM_HTML  # the live region must not change every poll
    assert ".stale{position:sticky" in REVIEW_ROOM_HTML
    assert "Reload the matter" in REVIEW_ROOM_HTML
    assert "innerHTML" not in REVIEW_ROOM_HTML
    assert "http://" not in REVIEW_ROOM_HTML and "https://" not in REVIEW_ROOM_HTML

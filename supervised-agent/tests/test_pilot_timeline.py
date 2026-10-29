"""Audit-chain timeline: every event, in chain order, grouped by version and classified."""

import re
from collections import Counter
from pathlib import Path

import pytest

from src.pilot.service import PermissionDeniedError
from src.pilot.timeline import EVENT_CLASSES, LEGEND, event_class
from tests.pilot_support import OWNER, REQUESTER, make_service, revision, run_until

SERVICE_SOURCE = Path(__file__).parents[1] / "src" / "pilot" / "service.py"


def _events(timeline):
    return [e for g in timeline["groups"] for e in g["events"]]


def _states(timeline):
    return {e["seq"]: e["chain"] for e in _events(timeline)}


def _delivered(tmp_path, scenario_id="routine", last="A13"):
    service = make_service(tmp_path)
    return service, run_until(service, scenario_id, last)


def _tamper(service, sql, matter_id, seq):
    with service.store.transaction() as connection:
        connection.execute(sql, (matter_id, seq))


def test_the_rehearsal_reads_as_one_chain_grouped_by_version(tmp_path) -> None:
    service, matter_id = _delivered(tmp_path, "specialist-revision", "B45")
    timeline = service.view_matter(OWNER, matter_id)["timeline"]
    history = service.history(OWNER, matter_id)["events"]

    assert timeline["chain"]["verified"] and timeline["chain"]["event_count"] == len(history)
    assert [e["seq"] for e in _events(timeline)] == list(range(len(history)))
    assert [g["version"] for g in timeline["groups"]] == [1, 2, 3]
    assert set(_states(timeline).values()) == {"verified"}
    first = timeline["groups"][0]["events"]
    # The refused submission has no version of its own: it belongs to version 1, and the
    # amendment that made version 2 is the last event of version 1.
    assert [(e["event_type"], e["class"]) for e in first] == [
        ("matter_created", "command"),
        ("command_refused", "refusal"),
        ("matter_amended", "command"),
    ]
    # The approval refused straight after the amendment that made version 3 is in version 3.
    second, third = timeline["groups"][1]["events"], timeline["groups"][2]["events"]
    assert (second[-1]["event_type"], third[0]["event_type"]) == (
        "matter_amended",
        "command_refused",
    )
    last = {e["event_type"]: e["class"] for e in third}
    assert (last["approved"], last["delivery_package_prepared"]) == ("decision", "export")
    assert all(e["hash_prefix"] == e["event_hash"][:12] for e in _events(timeline))


def test_the_legend_counts_every_event_once(tmp_path) -> None:
    service, matter_id = _delivered(tmp_path, "specialist-revision", "B45")
    timeline = service.view_matter(OWNER, matter_id)["timeline"]
    expected = Counter(
        event_class(e["event_type"]) for e in service.history(OWNER, matter_id)["events"]
    )
    legend = {item["class"]: item["count"] for item in timeline["legend"]}
    assert [item["class"] for item in timeline["legend"]] == [
        "command",
        "refusal",
        "decision",
        "export",
    ]
    assert legend == {key: expected[key] for key in legend}
    assert legend["refusal"] >= 1 and legend["export"] == 2


def test_every_event_type_the_service_writes_is_classified_on_purpose() -> None:
    source = SERVICE_SOURCE.read_text()
    written = set(re.findall(r'_event\(\s*(?:ctx,\s*)?"([a-z_]+)"', source))
    written |= set(re.findall(r'event_type="([a-z_]+)"', source))
    assert "change_decided" in written and "command_refused" in written
    assert written - set(EVENT_CLASSES) == set()
    assert set(EVENT_CLASSES.values()) == {key for key, _, _ in LEGEND}


def test_a_tampered_event_is_the_first_bad_event(tmp_path) -> None:
    service, matter_id = _delivered(tmp_path)
    _tamper(
        service,
        "UPDATE events SET note = 'Edited later.' WHERE matter_id = ? AND seq = ?",
        matter_id,
        5,
    )
    timeline = service.view_matter(OWNER, matter_id)["timeline"]
    assert timeline["chain"]["broken_at_seq"] == 5
    assert "event_hash mismatch at seq 5" in timeline["chain"]["reason"]
    states = _states(timeline)
    assert {s for seq, s in states.items() if seq < 5} == {"verified"}
    assert states[5] == "first_bad"
    assert {s for seq, s in states.items() if seq > 5} == {"unverified"}


def test_a_deleted_event_marks_the_one_after_the_gap(tmp_path) -> None:
    service, matter_id = _delivered(tmp_path)
    _tamper(service, "DELETE FROM events WHERE matter_id = ? AND seq = ?", matter_id, 4)
    timeline = service.view_matter(OWNER, matter_id)["timeline"]
    assert timeline["chain"]["reason"] == "sequence gap at seq 5"
    assert _states(timeline)[5] == "first_bad" and 4 not in _states(timeline)


def test_an_unreadable_payload_breaks_the_chain_not_the_view(tmp_path) -> None:
    service, matter_id = _delivered(tmp_path)
    _tamper(
        service,
        "UPDATE events SET payload = '{not json' WHERE matter_id = ? AND seq = ?",
        matter_id,
        3,
    )
    timeline = service.view_matter(OWNER, matter_id)["timeline"]
    assert timeline["chain"]["reason"] == "unreadable payload at seq 3"
    bad = next(e for e in _events(timeline) if e["seq"] == 3)
    assert bad["chain"] == "first_bad" and bad["payload"] is None
    history = service.history(OWNER, matter_id)
    assert history["events"][3]["payload"] is None and not history["audit_chain"]["verified"]


def test_decisions_set_aside_stay_with_their_version(tmp_path) -> None:
    service = make_service(tmp_path)
    matter_id = run_until(service, "specialist-revision", "B36")
    service.amend_matter(
        REQUESTER, matter_id, revision(service, matter_id),
        reason="Customer moved the signature date.", facts={"signature_target_date": "2026-10-15"},
    )  # fmt: skip
    view = service.view_matter(OWNER, matter_id)
    groups = {g["version"]: g for g in view["timeline"]["groups"]}
    [signoff] = groups[2]["set_aside"]
    assert signoff["kind"] == "specialist_signoff" and "version 3" in signoff["invalidated_reason"]
    # Version 3 has no event yet; it is still shown with its hashes.
    assert (
        groups[3]["events"] == [] and groups[3]["content_hash"] == view["version"]["content_hash"]
    )
    assert groups[2]["events"][-1]["event_type"] == "matter_amended"


def test_requesters_never_get_the_timeline(tmp_path) -> None:
    service, matter_id = _delivered(tmp_path)
    assert "timeline" not in service.view_matter(REQUESTER, matter_id)
    with pytest.raises(PermissionDeniedError):
        service.history(REQUESTER, matter_id)


def test_the_timeline_is_deterministic_and_reads_only(tmp_path) -> None:
    service, matter_id = _delivered(tmp_path)

    def dump() -> str:
        with service.store.reading() as connection:
            return "\n".join(connection.iterdump())

    before = dump()
    first = service.view_matter(OWNER, matter_id)["timeline"]
    assert service.view_matter(OWNER, matter_id)["timeline"] == first
    assert dump() == before

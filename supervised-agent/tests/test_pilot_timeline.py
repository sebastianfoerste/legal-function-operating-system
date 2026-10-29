"""Audit-chain timeline: every event, in chain order, grouped by version and classified."""

import ast
import json
from pathlib import Path

import pytest

from models import compute_audit_event_hash
from src.pilot.metrics import build_pilot_metrics, render_metrics_markdown
from src.pilot.service import PermissionDeniedError, PilotService, Stamp
from src.pilot.store import _event_body
from src.pilot.timeline import EVENT_CLASSES, LEGEND, event_class
from tests.pilot_support import OWNER, REQUESTER, make_service, revision, run_until

PILOT_SOURCE = Path(__file__).parents[1] / "src" / "pilot"


def _events(timeline):
    return [e for g in timeline["groups"] for e in g["events"]]


def _states(timeline):
    return {e["seq"]: e["chain"] for e in _events(timeline)}


def _delivered(tmp_path, scenario_id="routine", last="A13"):
    service = make_service(tmp_path)
    return service, run_until(service, scenario_id, last)


def _tamper(service, sql, *params):
    with service.store.transaction() as connection:
        connection.execute(sql, params)


def _timeline(service, matter_id):
    view = service.view_matter(OWNER, matter_id)
    json.dumps(view)  # whatever is stored, the view must still serialise
    return view["timeline"]


# -- the intact rehearsal -------------------------------------------------------------


def test_the_rehearsal_reads_as_one_chain_grouped_by_version(tmp_path) -> None:
    service, matter_id = _delivered(tmp_path, "specialist-revision", "B45")
    timeline = _timeline(service, matter_id)
    history = service.history(OWNER, matter_id)["events"]

    assert timeline["chain"]["verified"] and timeline["chain"]["event_count"] == len(history)
    assert timeline["chain"]["first_unverified_index"] is None
    assert [e["seq"] for e in _events(timeline)] == list(range(len(history)))
    assert [g["version"] for g in timeline["groups"]] == [1, 2, 3]
    assert set(_states(timeline).values()) == {"verified"}
    # Each event shows what the chain stores for it.
    keys = ("seq", "event_type", "actor_id", "role", "note", "occurred_at", "fixture_at")
    keys += ("prev_hash", "event_hash", "payload")
    for event, row in zip(_events(timeline), history, strict=True):
        assert {k: event[k] for k in keys} == {k: row[k] for k in keys}
        assert event["hash_prefix"] == row["event_hash"][:12]
        assert event["class"] == event_class(row["event_type"])
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


def test_the_legend_counts_every_event_once(tmp_path) -> None:
    service, matter_id = _delivered(tmp_path, "specialist-revision", "B45")
    timeline = _timeline(service, matter_id)
    legend = {item["class"]: item["count"] for item in timeline["legend"]}
    assert [item["class"] for item in timeline["legend"]] == [
        "command",
        "refusal",
        "decision",
        "export",
    ]
    assert legend == {"command": 21, "refusal": 7, "decision": 13, "export": 2}


def _written_event_types() -> set[str]:
    """Every event type a pilot module writes, read from the code itself."""

    written = set()
    for path in sorted(PILOT_SOURCE.rglob("*.py")):
        for node in ast.walk(ast.parse(path.read_text())):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                continue
            if node.func.attr == "_event":
                value = node.args[1] if len(node.args) > 1 else None
            elif node.func.attr == "append_event":
                value = next((k.value for k in node.keywords if k.arg == "event_type"), None)
            else:
                continue
            if isinstance(value, ast.Name) and value.id == "event_type":
                continue  # _event passing its own argument on to append_event
            where = f"{path.name}:{node.lineno}"
            assert isinstance(value, ast.Constant) and isinstance(value.value, str), where
            written.add(value.value)
    return written


def test_every_event_type_the_service_writes_is_classified_on_purpose() -> None:
    assert _written_event_types() == set(EVENT_CLASSES)
    assert {t: c for t, c in EVENT_CLASSES.items() if c != "command"} == {
        "command_refused": "refusal",
        "change_decided": "decision",
        "specialist_signed_off": "decision",
        "revision_requested": "decision",
        "approved": "decision",
        "delivery_accepted": "decision",
        "internal_review_exported": "export",
        "delivery_package_prepared": "export",
    }
    assert set(EVENT_CLASSES.values()) == {key for key, _, _ in LEGEND}
    assert event_class("not_a_known_type") == "command"  # a tampered type still renders


# -- broken chains ----------------------------------------------------------------------


def test_an_edited_event_is_the_first_bad_event(tmp_path) -> None:
    service, matter_id = _delivered(tmp_path)
    _tamper(
        service,
        "UPDATE events SET note = 'Edited later.' WHERE matter_id = ? AND seq = 5",
        matter_id,
    )
    timeline = _timeline(service, matter_id)
    chain = timeline["chain"]
    assert (chain["broken_at_seq"], chain["reason"]) == (5, "event_hash mismatch at seq 5")
    assert chain["explanation"] == (
        "Positions 0 to 4 are verified. "
        "The event at position 5 and every later event are not verified."
    )
    assert chain["first_unverified_index"] == 5 and chain["verified_events"] == 5
    states = _states(timeline)
    assert {s for seq, s in states.items() if seq < 5} == {"verified"}
    assert states[5] == "first_bad"
    assert {s for seq, s in states.items() if seq > 5} == {"unverified"}


@pytest.mark.parametrize(
    ("deleted", "explanation", "first"),
    [
        (
            4,
            "Positions 0 to 3 are verified. Position 4 is missing. "
            "The event at position 5 and every later event are not verified.",
            5,
        ),
        (
            0,
            "No event is verified. Position 0 is missing. "
            "The event at position 1 and every later event are not verified.",
            1,
        ),
    ],
)
def test_a_deleted_event_is_named_missing_never_verified(
    tmp_path, deleted, explanation, first
) -> None:
    service, matter_id = _delivered(tmp_path)
    _tamper(service, "DELETE FROM events WHERE matter_id = ? AND seq = ?", matter_id, deleted)
    timeline = _timeline(service, matter_id)
    assert timeline["chain"]["reason"] == f"sequence gap at seq {first}"
    assert timeline["chain"]["explanation"] == explanation
    states = _states(timeline)
    assert deleted not in states and states[first] == "first_bad"
    assert [s for seq, s in states.items() if s == "verified"] == ["verified"] * deleted


def test_an_event_moved_out_of_sequence_verifies_nothing_after_it(tmp_path) -> None:
    service, matter_id = _delivered(tmp_path)
    _tamper(service, "UPDATE events SET seq = -1 WHERE matter_id = ? AND seq = 5", matter_id)
    chain = _timeline(service, matter_id)["chain"]
    assert chain["explanation"] == (
        "No event is verified. The event stored at position -1 is out of sequence. "
        "The event at position -1 and every later event are not verified."
    )


def test_a_rewritten_and_rehashed_event_is_not_vouched_for(tmp_path) -> None:
    service, matter_id = _delivered(tmp_path)
    with service.store.transaction() as connection:
        row = dict(
            connection.execute(
                "SELECT * FROM events WHERE matter_id = ? AND seq = 5", (matter_id,)
            ).fetchone()
        )
        row["note"] = "Rewritten later, with its hash recomputed."
        digest = compute_audit_event_hash(
            row["seq"],
            row["prev_hash"],
            row["event_type"],
            row["actor_id"],
            _event_body(row),
            row["occurred_at"],
        )
        connection.execute(
            "UPDATE events SET note = ?, event_hash = ? WHERE matter_id = ? AND seq = 5",
            (row["note"], digest, matter_id),
        )
    timeline = _timeline(service, matter_id)
    assert timeline["chain"]["reason"] == "prev_hash mismatch at seq 6"
    assert timeline["chain"]["explanation"] == (
        "Positions 0 to 4 are verified. Position 6 does not link to position 5, so one of "
        "the two was changed after it was recorded. "
        "The event at position 5 and every later event are not verified."
    )
    states = _states(timeline)
    assert (states[4], states[5], states[6], states[7]) == (
        "verified",
        "suspect",
        "first_bad",
        "unverified",
    )
    assert timeline["chain"]["first_unverified_index"] == 5


@pytest.mark.parametrize("seq", [3, 11])
def test_a_seq_that_is_not_a_number_still_opens_the_matter(tmp_path, seq) -> None:
    service, matter_id = _delivered(tmp_path)
    _tamper(service, "UPDATE events SET seq = 'x' WHERE matter_id = ? AND seq = ?", matter_id, seq)
    timeline = _timeline(service, matter_id)
    events = _events(timeline)
    assert events[-1]["seq"] == "x" and events[-1]["chain"] != "verified"
    assert [e["chain"] for e in events[:seq]] == ["verified"] * seq
    assert events[seq]["chain"] == "first_bad"
    assert service.history(OWNER, matter_id)["audit_chain"]["verified"] is False


@pytest.mark.parametrize(
    ("stored", "reason", "parsed", "history_payload"),
    [
        ("{not json", "unreadable payload at seq 3", False, None),
        ('["tampered"]', "event_hash mismatch at seq 3", True, ["tampered"]),
        ("[" * 20000 + "]" * 20000, "unreadable payload at seq 3", False, None),
    ],
)
def test_a_tampered_payload_breaks_the_chain_not_the_view(
    tmp_path, stored, reason, parsed, history_payload
) -> None:
    service, matter_id = _delivered(tmp_path)
    _tamper(
        service, "UPDATE events SET payload = ? WHERE matter_id = ? AND seq = 3", stored, matter_id
    )
    timeline = _timeline(service, matter_id)
    assert timeline["chain"]["reason"] == reason
    bad = _events(timeline)[3]
    assert (bad["chain"], bad["payload"], bad["payload_readable"]) == ("first_bad", None, parsed)
    assert bad["payload_text"] == stored[:2000]
    history = service.history(OWNER, matter_id)
    json.dumps(history)
    assert history["events"][3]["payload"] == history_payload
    assert history["events"][3].get("payload_raw") == (None if parsed else stored)
    assert history["audit_chain"]["reason"] == reason


def test_bytes_in_a_text_column_are_shown_not_raised(tmp_path) -> None:
    service, matter_id = _delivered(tmp_path)
    _tamper(
        service, "UPDATE events SET note = X'6869ff' WHERE matter_id = ? AND seq = 2", matter_id
    )
    timeline = _timeline(service, matter_id)
    assert timeline["chain"]["reason"] == "unreadable event data at seq 2"
    assert _events(timeline)[2]["note"] == "hi�"
    json.dumps(service.history(OWNER, matter_id))


def test_the_status_covers_exactly_the_events_shown(tmp_path, monkeypatch) -> None:
    service, matter_id = _delivered(tmp_path)
    eligibility = PilotService._eligibility

    def written_meanwhile(self, ctx, kind):  # another request commits while the view is built
        self._record_refusal(OWNER, matter_id, "approve", PermissionDeniedError("late"), Stamp())
        return eligibility(self, ctx, kind)

    monkeypatch.setattr(PilotService, "_eligibility", written_meanwhile)
    timeline = _timeline(service, matter_id)
    assert timeline["chain"]["event_count"] == len(_events(timeline)) == 12
    assert sum(item["count"] for item in timeline["legend"]) == 12


def test_the_measurement_report_survives_a_tampered_payload(tmp_path) -> None:
    service, matter_id = _delivered(tmp_path)
    _tamper(
        service, "UPDATE events SET payload = '{bad' WHERE matter_id = ? AND seq = 3", matter_id
    )
    _tamper(
        service, "UPDATE events SET payload = '[1,2]' WHERE matter_id = ? AND seq = 4", matter_id
    )
    metrics = build_pilot_metrics(service.store)
    [row] = [r for r in metrics["operational_time"] if r["matter_id"] == matter_id]
    assert row["audit_chain_verified"] is False
    assert render_metrics_markdown(metrics)


# -- versions and decisions ------------------------------------------------------------


def _amended_after_signoff(tmp_path):
    service = make_service(tmp_path)
    matter_id = run_until(service, "specialist-revision", "B36")
    service.amend_matter(
        REQUESTER, matter_id, revision(service, matter_id),
        reason="Customer moved the signature date.", facts={"signature_target_date": "2026-10-15"},
    )  # fmt: skip
    return service, matter_id


def test_decisions_set_aside_stay_with_their_version(tmp_path) -> None:
    service, matter_id = _amended_after_signoff(tmp_path)
    view = service.view_matter(OWNER, matter_id)
    groups = {g["version"]: g for g in view["timeline"]["groups"]}
    [signoff] = groups[2]["set_aside"]
    assert signoff["kind"] == "specialist_signoff" and "version 3" in signoff["invalidated_reason"]
    # Version 3 has no event yet; it is still shown with its hashes.
    assert (
        groups[3]["events"] == [] and groups[3]["content_hash"] == view["version"]["content_hash"]
    )
    assert groups[2]["events"][-1]["event_type"] == "matter_amended"


def test_set_aside_decisions_go_on_the_longest_run_of_their_version(tmp_path) -> None:
    service, matter_id = _amended_after_signoff(tmp_path)
    _tamper(
        service,
        "UPDATE events SET payload = json_set(payload, '$.version', 2) "
        "WHERE matter_id = ? AND seq = 1",
        matter_id,
    )
    runs = [g for g in _timeline(service, matter_id)["groups"] if g["version"] == 2]
    assert [len(g["events"]) for g in runs] == [1, 33]
    assert (runs[0]["set_aside"], len(runs[1]["set_aside"])) == ([], 1)


# -- who sees it ------------------------------------------------------------------------


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
    first = _timeline(service, matter_id)
    assert _timeline(service, matter_id) == first
    assert dump() == before

"""Observed legal-service outcomes over a synthetic request event ledger."""

from __future__ import annotations

import html
import json
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from legal_function_os.capacity_simulator import _effort_points
from legal_function_os.rules import decide

LEDGER_SCHEMA = "legal-function-os.service-event-ledger.v1"
CONFIG_SCHEMA = "legal-function-os.outcome-config.v1"
OUTPUT_SCHEMA = "legal-function-os.outcome-control-tower.v1"

EVENT_TYPES = {
    "submitted",
    "acknowledged",
    "assigned",
    "work_started",
    "waiting_on_business",
    "resumed",
    "approval_requested",
    "approved",
    "completed",
    "reopened",
    "external_counsel_referred",
}
STATE_EVENTS = EVENT_TYPES - {"external_counsel_referred"}
ALLOWED_TRANSITIONS = {
    None: {"submitted"},
    "submitted": {"acknowledged"},
    "acknowledged": {"assigned"},
    "assigned": {"work_started"},
    "work_started": {"waiting_on_business", "approval_requested", "completed"},
    "waiting_on_business": {"resumed"},
    "resumed": {"work_started", "waiting_on_business", "approval_requested", "completed"},
    "approval_requested": {"approved", "waiting_on_business"},
    "approved": {"completed"},
    "completed": {"reopened"},
    "reopened": {"work_started", "waiting_on_business"},
}


def _parse_utc(value: str, field: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{field} must include a timezone")
    return parsed


@dataclass(frozen=True)
class ServiceCalendar:
    timezone: str
    workday_start: str
    workday_end: str
    working_weekdays: tuple[int, ...]
    excluded_dates: frozenset[date]

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "ServiceCalendar":
        timezone = str(payload.get("timezone", "Europe/Berlin"))
        try:
            ZoneInfo(timezone)
        except Exception as exc:
            raise ValueError(f"unknown calendar timezone: {timezone}") from exc
        start = str(payload.get("workday_start", "09:00"))
        end = str(payload.get("workday_end", "18:00"))
        try:
            start_time = time.fromisoformat(start)
            end_time = time.fromisoformat(end)
        except ValueError as exc:
            raise ValueError("workday_start and workday_end must use HH:MM") from exc
        if end_time <= start_time:
            raise ValueError("workday_end must be after workday_start")
        weekdays = tuple(int(day) for day in payload.get("working_weekdays", [0, 1, 2, 3, 4]))
        if not weekdays or any(day < 0 or day > 6 for day in weekdays):
            raise ValueError("working_weekdays must contain values from 0 to 6")
        try:
            excluded = frozenset(date.fromisoformat(str(item)) for item in payload.get("excluded_dates", []))
        except ValueError as exc:
            raise ValueError("excluded_dates must contain ISO dates") from exc
        return cls(timezone, start, end, weekdays, excluded)

    @property
    def minutes_per_day(self) -> int:
        start = datetime.combine(date.min, time.fromisoformat(self.workday_start))
        end = datetime.combine(date.min, time.fromisoformat(self.workday_end))
        return int((end - start).total_seconds() // 60)

    def business_minutes(self, start: datetime, end: datetime) -> int:
        if end < start:
            raise ValueError("business-time interval ends before it starts")
        zone = ZoneInfo(self.timezone)
        local_start = start.astimezone(zone)
        local_end = end.astimezone(zone)
        current = local_start.date()
        total_seconds = 0.0
        while current <= local_end.date():
            if current.weekday() in self.working_weekdays and current not in self.excluded_dates:
                day_start = datetime.combine(
                    current, time.fromisoformat(self.workday_start), tzinfo=zone
                )
                day_end = datetime.combine(
                    current, time.fromisoformat(self.workday_end), tzinfo=zone
                )
                overlap_start = max(local_start, day_start)
                overlap_end = min(local_end, day_end)
                if overlap_end > overlap_start:
                    total_seconds += (overlap_end - overlap_start).total_seconds()
            current += timedelta(days=1)
        return int(total_seconds // 60)


def _validate_inputs(
    requests: list[dict[str, Any]],
    ledger: dict[str, Any],
    config: dict[str, Any],
) -> tuple[datetime, ServiceCalendar, dict[str, list[dict[str, Any]]]]:
    if not isinstance(ledger, dict) or not isinstance(config, dict):
        raise ValueError("event ledger and outcome config must be JSON objects")
    if ledger.get("schema") != LEDGER_SCHEMA:
        raise ValueError(f"event ledger schema must be {LEDGER_SCHEMA}")
    if config.get("schema") != CONFIG_SCHEMA:
        raise ValueError(f"outcome config schema must be {CONFIG_SCHEMA}")
    as_of = _parse_utc(str(ledger.get("as_of_utc", "")), "as_of_utc")
    calendar = ServiceCalendar.from_dict(dict(config.get("calendar", {})))
    if any(not request.get("id") for request in requests):
        raise ValueError("every request requires an ID")
    request_ids = {str(request["id"]) for request in requests}
    if len(request_ids) != len(requests):
        raise ValueError("requests must have unique IDs")
    events = ledger.get("events")
    if not isinstance(events, list) or not events:
        raise ValueError("event ledger must contain at least one event")

    seen_ids: set[str] = set()
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    last_timestamp: dict[str, datetime] = {}
    for raw in events:
        if not isinstance(raw, dict):
            raise ValueError("every event must be an object")
        event_id = str(raw.get("event_id", ""))
        request_id = str(raw.get("request_id", ""))
        event_type = str(raw.get("event_type", ""))
        if not event_id:
            raise ValueError("every event requires event_id")
        if event_id in seen_ids:
            raise ValueError(f"duplicate event_id: {event_id}")
        seen_ids.add(event_id)
        if request_id not in request_ids:
            raise ValueError(f"event {event_id} references unknown request {request_id}")
        if event_type not in EVENT_TYPES:
            raise ValueError(f"event {event_id} has unsupported event_type {event_type}")
        occurred_at = _parse_utc(str(raw.get("occurred_at_utc", "")), f"{event_id}.occurred_at_utc")
        if occurred_at > as_of:
            raise ValueError(f"event {event_id} occurs after as_of_utc")
        if request_id in last_timestamp and occurred_at < last_timestamp[request_id]:
            raise ValueError(
                f"event {event_id} is out of chronological order for {request_id}"
            )
        last_timestamp[request_id] = occurred_at
        effort_minutes = raw.get("effort_minutes", 0)
        if not isinstance(effort_minutes, int) or effort_minutes < 0:
            raise ValueError(f"event {event_id} effort_minutes must be a non-negative integer")
        event = dict(raw)
        event["_occurred_at"] = occurred_at
        grouped[request_id].append(event)

    missing = sorted(request_ids - set(grouped))
    if missing:
        raise ValueError(f"event ledger is missing requests: {', '.join(missing)}")

    for request_id, request_events in grouped.items():
        request_events.sort(key=lambda event: (event["_occurred_at"], event["event_id"]))
        state: str | None = None
        waiting = False
        for event in request_events:
            event_type = str(event["event_type"])
            if event_type == "external_counsel_referred":
                if state in {None, "submitted", "acknowledged", "completed"}:
                    raise ValueError(
                        f"{request_id} external counsel referral is invalid while state is {state}"
                    )
                continue
            allowed = ALLOWED_TRANSITIONS.get(state, set())
            if event_type not in allowed:
                raise ValueError(
                    f"{request_id} invalid transition {state or 'start'} -> {event_type}"
                )
            if event_type == "waiting_on_business":
                if waiting:
                    raise ValueError(f"{request_id} already has an active business wait")
                waiting = True
            elif event_type == "resumed":
                if not waiting:
                    raise ValueError(f"{request_id} cannot resume without an active business wait")
                waiting = False
            state = event_type
        if waiting and state != "waiting_on_business":
            raise ValueError(f"{request_id} has an inconsistent waiting state")
    return as_of, calendar, grouped


def _hours(minutes: int) -> float:
    return round(minutes / 60, 2)


def _money(value: float) -> float:
    return round(value, 2)


def build_outcome_control_tower(
    requests: list[dict[str, Any]],
    ledger: dict[str, Any],
    config: dict[str, Any],
) -> dict[str, Any]:
    """Build a deterministic outcome and value-control snapshot."""

    as_of, calendar, grouped = _validate_inputs(requests, ledger, config)
    value = dict(config.get("value_assumptions", {}))
    role_rates = {str(role): float(rate) for role, rate in value.get("internal_role_hourly_cost_eur", {}).items()}
    default_role = str(value.get("default_internal_role", "Legal Counsel"))
    if default_role not in role_rates or any(rate < 0 for rate in role_rates.values()):
        raise ValueError("value assumptions require non-negative rates including default_internal_role")
    external_rate = float(value.get("external_reference_hourly_rate_eur", 0))
    baseline_minutes = {
        str(request_type): int(minutes)
        for request_type, minutes in value.get("baseline_effort_minutes_by_request_type", {}).items()
    }
    if external_rate < 0 or any(minutes < 0 for minutes in baseline_minutes.values()):
        raise ValueError("value assumptions must be non-negative")
    stalled_after = int(config.get("stalled_after_business_hours", 16))
    if stalled_after < 1:
        raise ValueError("stalled_after_business_hours must be positive")

    request_rows: list[dict[str, Any]] = []
    queue_effort: dict[str, dict[str, float]] = defaultdict(
        lambda: {"requests": 0, "planned_points": 0, "observed_minutes": 0}
    )
    completed_count = 0
    response_hits = 0
    resolved_hits = 0
    response_measured = 0
    resolution_measured = 0
    total_internal_cost = 0.0
    total_efficiency_value = 0.0
    total_spend_avoidance = 0.0
    reopen_total = 0

    for request in sorted(requests, key=lambda item: str(item["id"])):
        request_id = str(request["id"])
        events = grouped[request_id]
        decision = decide(request)
        state_events = [event for event in events if event["event_type"] in STATE_EVENTS]
        first_by_type: dict[str, dict[str, Any]] = {}
        for event in state_events:
            first_by_type.setdefault(str(event["event_type"]), event)
        submitted = first_by_type["submitted"]["_occurred_at"]
        final_state = str(state_events[-1]["event_type"])
        completed_events = [event for event in state_events if event["event_type"] == "completed"]
        is_complete = final_state == "completed"
        endpoint = completed_events[-1]["_occurred_at"] if is_complete else as_of
        gross_minutes = calendar.business_minutes(submitted, endpoint)

        wait_minutes = 0
        wait_start: datetime | None = None
        approval_minutes = 0
        approval_start: datetime | None = None
        for event in state_events:
            event_type = str(event["event_type"])
            occurred_at = event["_occurred_at"]
            if event_type == "waiting_on_business":
                wait_start = occurred_at
            elif event_type == "resumed" and wait_start is not None:
                wait_minutes += calendar.business_minutes(wait_start, occurred_at)
                wait_start = None
            if event_type == "approval_requested":
                approval_start = occurred_at
            elif event_type == "approved" and approval_start is not None:
                approval_minutes += calendar.business_minutes(approval_start, occurred_at)
                approval_start = None
        if wait_start is not None:
            wait_minutes += calendar.business_minutes(wait_start, endpoint)
        if approval_start is not None:
            approval_minutes += calendar.business_minutes(approval_start, endpoint)
        controlled_minutes = max(0, gross_minutes - wait_minutes)

        acknowledgement = first_by_type.get("acknowledged")
        response_minutes = (
            calendar.business_minutes(submitted, acknowledgement["_occurred_at"])
            if acknowledgement
            else None
        )
        response_target = decision.sla_response_hours * 60
        resolution_target = decision.sla_resolution_days * calendar.minutes_per_day
        response_status = "unmeasured"
        if response_minutes is not None:
            response_measured += 1
            response_status = "met" if response_minutes <= response_target else "breached"
            response_hits += response_status == "met"
        resolution_status = "open"
        if is_complete:
            resolution_measured += 1
            resolution_status = "met" if controlled_minutes <= resolution_target else "breached"
            resolved_hits += resolution_status == "met"
            completed_count += 1

        effort_minutes = sum(int(event.get("effort_minutes", 0)) for event in events)
        internal_cost = 0.0
        for event in events:
            minutes = int(event.get("effort_minutes", 0))
            role = str(event.get("actor_role", default_role))
            internal_cost += minutes / 60 * role_rates.get(role, role_rates[default_role])
        baseline = baseline_minutes.get(str(request.get("type")), effort_minutes)
        avoided_minutes = max(0, baseline - effort_minutes)
        efficiency_value = avoided_minutes / 60 * role_rates[default_role]
        spend_avoidance = 0.0
        if decision.external_counsel == "in-house":
            spend_avoidance = max(0.0, effort_minutes / 60 * external_rate - internal_cost)

        planned_points = _effort_points(decision, request)
        queue = queue_effort[decision.queue]
        queue["requests"] += 1
        queue["planned_points"] += planned_points
        queue["observed_minutes"] += effort_minutes

        reopen_count = sum(event["event_type"] == "reopened" for event in events)
        reopen_total += reopen_count
        last_event = state_events[-1]["_occurred_at"]
        inactive_minutes = (
            0 if is_complete else calendar.business_minutes(last_event, as_of)
        )
        stalled = final_state != "completed" and inactive_minutes >= stalled_after * 60
        total_internal_cost += internal_cost
        total_efficiency_value += efficiency_value
        total_spend_avoidance += spend_avoidance

        request_rows.append(
            {
                "request_id": request_id,
                "title": decision.title,
                "request_type": decision.type,
                "queue": decision.queue,
                "priority": decision.priority,
                "risk": decision.risk,
                "state": final_state,
                "submitted_at_utc": submitted.isoformat(),
                "last_event_at_utc": last_event.isoformat(),
                "first_response_business_hours": (
                    _hours(response_minutes) if response_minutes is not None else None
                ),
                "gross_cycle_business_hours": _hours(gross_minutes),
                "business_wait_hours": _hours(wait_minutes),
                "legal_controlled_hours": _hours(controlled_minutes),
                "approval_dwell_hours": _hours(approval_minutes),
                "inactive_business_hours": _hours(inactive_minutes),
                "response_sla": response_status,
                "resolution_sla": resolution_status,
                "reopen_count": reopen_count,
                "stalled": stalled,
                "planned_effort_points": planned_points,
                "observed_effort_minutes": effort_minutes,
                "value_proxy": {
                    "baseline_effort_minutes": baseline,
                    "estimated_minutes_avoided": avoided_minutes,
                    "estimated_internal_cost_eur": _money(internal_cost),
                    "estimated_labour_efficiency_value_eur": _money(efficiency_value),
                    "estimated_external_spend_avoidance_eur": _money(spend_avoidance),
                },
                "timeline": [
                    {
                        key: value
                        for key, value in event.items()
                        if not key.startswith("_")
                    }
                    for event in events
                ],
            }
        )

    queue_rows = []
    for queue_name, row in sorted(queue_effort.items()):
        observed = int(row["observed_minutes"])
        points = int(row["planned_points"])
        queue_rows.append(
            {
                "queue": queue_name,
                "requests": int(row["requests"]),
                "planned_effort_points": points,
                "observed_effort_minutes": observed,
                "observed_minutes_per_point": round(observed / points, 2) if points else None,
                "open_requests": sum(
                    item["queue"] == queue_name and item["state"] != "completed"
                    for item in request_rows
                ),
                "stalled_requests": sum(
                    item["queue"] == queue_name and item["stalled"] for item in request_rows
                ),
            }
        )

    stalled_rows = [row for row in request_rows if row["stalled"]]
    stalled_rows.sort(
        key=lambda row: (-float(row["inactive_business_hours"]), str(row["request_id"]))
    )
    bottlenecks = sorted(
        queue_rows,
        key=lambda row: (
            -int(row["stalled_requests"]),
            -int(row["open_requests"]),
            -int(row["observed_effort_minutes"]),
            str(row["queue"]),
        ),
    )
    state_counts = Counter(row["state"] for row in request_rows)
    return {
        "schema": OUTPUT_SCHEMA,
        "generated_at_utc": as_of.isoformat(),
        "source": {
            "ledger_schema": LEDGER_SCHEMA,
            "config_schema": CONFIG_SCHEMA,
            "request_count": len(requests),
            "event_count": len(ledger["events"]),
        },
        "calendar": {
            **asdict(calendar),
            "working_weekdays": list(calendar.working_weekdays),
            "excluded_dates": sorted(item.isoformat() for item in calendar.excluded_dates),
        },
        "executive_summary": {
            "requests": len(request_rows),
            "completed_requests": completed_count,
            "open_requests": len(request_rows) - completed_count,
            "stalled_requests": len(stalled_rows),
            "throughput_rate": round(completed_count / len(request_rows), 3),
            "reopen_count": reopen_total,
            "response_sla_attainment": (
                round(response_hits / response_measured, 3) if response_measured else None
            ),
            "resolution_sla_attainment": (
                round(resolved_hits / resolution_measured, 3)
                if resolution_measured
                else None
            ),
            "states": dict(sorted(state_counts.items())),
            "binding_queue": bottlenecks[0]["queue"] if bottlenecks else None,
        },
        "value_proxy": {
            "assumption_notice": (
                "All monetary figures are assumption-based management proxies over "
                "synthetic effort records. They are not realised savings or accounting conclusions."
            ),
            "assumptions": value,
            "estimated_internal_cost_eur": _money(total_internal_cost),
            "estimated_labour_efficiency_value_eur": _money(total_efficiency_value),
            "estimated_external_spend_avoidance_eur": _money(total_spend_avoidance),
        },
        "queue_calibration": queue_rows,
        "bottlenecks": bottlenecks,
        "action_queue": [
            {
                "request_id": row["request_id"],
                "title": row["title"],
                "queue": row["queue"],
                "state": row["state"],
                "inactive_business_hours": row["inactive_business_hours"],
                "recommended_action": (
                    "Confirm the next business input and owner."
                    if row["state"] == "waiting_on_business"
                    else "Review ownership, priority, and the next controlled step."
                ),
            }
            for row in stalled_rows
        ],
        "requests": request_rows,
        "review_gate": (
            "A human legal-operations owner must validate event completeness, calendar settings, "
            "effort records, value assumptions, and every staffing or external-counsel decision."
        ),
        "external_action_allowed": False,
    }


def render_outcome_markdown(tower: dict[str, Any]) -> str:
    summary = tower["executive_summary"]
    value = tower["value_proxy"]
    lines = [
        "# Legal Function Outcome Control Tower",
        "",
        f"**Observed at: {tower['generated_at_utc']}**",
        "",
        "## Executive outcome",
        "",
        f"- Requests: {summary['requests']}",
        f"- Completed: {summary['completed_requests']}",
        f"- Open: {summary['open_requests']}",
        f"- Stalled: {summary['stalled_requests']}",
        f"- Response SLA attainment: {summary['response_sla_attainment'] * 100:.1f}%",
        f"- Resolution SLA attainment: {summary['resolution_sla_attainment'] * 100:.1f}%",
        f"- Binding queue: {summary['binding_queue']}",
        "",
        "## Queue calibration",
        "",
        "| Queue | Requests | Open | Stalled | Planned points | Observed minutes | Minutes per point |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in tower["queue_calibration"]:
        per_point = "n/a" if row["observed_minutes_per_point"] is None else f"{row['observed_minutes_per_point']:.2f}"
        lines.append(
            f"| {row['queue']} | {row['requests']} | {row['open_requests']} "
            f"| {row['stalled_requests']} | {row['planned_effort_points']} "
            f"| {row['observed_effort_minutes']} | {per_point} |"
        )
    lines.extend(
        [
            "",
            "## Value proxies",
            "",
            value["assumption_notice"],
            "",
            f"- Estimated internal cost: EUR {value['estimated_internal_cost_eur']:.2f}",
            (
                "- Estimated labour-efficiency value: "
                f"EUR {value['estimated_labour_efficiency_value_eur']:.2f}"
            ),
            (
                "- Estimated external-spend avoidance: "
                f"EUR {value['estimated_external_spend_avoidance_eur']:.2f}"
            ),
            "",
            "## Stalled action queue",
            "",
        ]
    )
    if not tower["action_queue"]:
        lines.append("No request meets the configured stalled threshold.")
    else:
        for item in tower["action_queue"]:
            lines.append(
                f"- `{item['request_id']}` ({item['queue']}, {item['state']}, "
                f"{item['inactive_business_hours']:.2f}h): {item['recommended_action']}"
            )
    lines.extend(
        [
            "",
            "## Request outcomes",
            "",
            "| Request | Queue | State | Gross h | Business wait h | Legal-controlled h | Response SLA | Resolution SLA |",
            "| --- | --- | --- | ---: | ---: | ---: | --- | --- |",
        ]
    )
    for row in tower["requests"]:
        lines.append(
            f"| {row['request_id']} | {row['queue']} | {row['state']} "
            f"| {row['gross_cycle_business_hours']:.2f} | {row['business_wait_hours']:.2f} "
            f"| {row['legal_controlled_hours']:.2f} | {row['response_sla']} "
            f"| {row['resolution_sla']} |"
        )
    lines.extend(["", "## Review gate", "", tower["review_gate"], ""])
    return "\n".join(lines)


def render_outcome_html(tower: dict[str, Any]) -> str:
    summary = tower["executive_summary"]
    queue_rows = "".join(
        "<tr>"
        f"<td>{html.escape(str(row['queue']))}</td>"
        f"<td>{row['requests']}</td><td>{row['open_requests']}</td>"
        f"<td>{row['stalled_requests']}</td><td>{row['planned_effort_points']}</td>"
        f"<td>{row['observed_effort_minutes']}</td>"
        f"<td>{row['observed_minutes_per_point'] if row['observed_minutes_per_point'] is not None else 'n/a'}</td>"
        "</tr>"
        for row in tower["queue_calibration"]
    )
    actions = "".join(
        "<li>"
        f"<strong>{html.escape(str(item['request_id']))}</strong> "
        f"{html.escape(str(item['title']))}<br>"
        f"<span>{html.escape(str(item['queue']))} · {html.escape(str(item['state']))} · "
        f"{item['inactive_business_hours']:.2f} business hours inactive</span><br>"
        f"{html.escape(str(item['recommended_action']))}</li>"
        for item in tower["action_queue"]
    ) or "<li>No request meets the stalled threshold.</li>"
    request_rows = "".join(
        "<tr>"
        f"<td>{html.escape(str(row['request_id']))}</td>"
        f"<td>{html.escape(str(row['queue']))}</td>"
        f"<td>{html.escape(str(row['state']))}</td>"
        f"<td>{row['gross_cycle_business_hours']:.2f}</td>"
        f"<td>{row['business_wait_hours']:.2f}</td>"
        f"<td>{row['legal_controlled_hours']:.2f}</td>"
        f"<td>{html.escape(str(row['response_sla']))}</td>"
        f"<td>{html.escape(str(row['resolution_sla']))}</td>"
        "</tr>"
        for row in tower["requests"]
    )
    value = tower["value_proxy"]
    embedded = html.escape(json.dumps(tower, indent=2, ensure_ascii=False))
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Legal Function Outcome Control Tower</title>
<style>
:root {{ color-scheme: light; --ink:#17202a; --muted:#5c6773; --line:#dfe5ea; --panel:#f7f9fa; --accent:#134e4a; }}
* {{ box-sizing:border-box; }}
body {{ margin:0; font:15px/1.5 Inter, ui-sans-serif, system-ui, sans-serif; color:var(--ink); background:#eef2f3; }}
main {{ max-width:1180px; margin:0 auto; padding:42px 24px 64px; }}
h1 {{ margin:0; font:700 35px/1.15 Georgia, serif; }}
h2 {{ margin:34px 0 14px; font-size:19px; }}
.eyebrow {{ color:var(--accent); font-weight:700; letter-spacing:.08em; text-transform:uppercase; font-size:12px; }}
.muted {{ color:var(--muted); }}
.metrics {{ display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:12px; margin:24px 0; }}
.metric, section {{ background:white; border:1px solid var(--line); border-radius:10px; box-shadow:0 8px 24px rgba(20,40,50,.05); }}
.metric {{ padding:18px; }}
.metric strong {{ display:block; font-size:28px; }}
.metric span {{ color:var(--muted); }}
section {{ padding:22px; margin-top:18px; overflow:auto; }}
table {{ width:100%; border-collapse:collapse; min-width:760px; }}
th, td {{ padding:10px 9px; border-bottom:1px solid var(--line); text-align:left; }}
th {{ color:var(--muted); font-size:12px; text-transform:uppercase; letter-spacing:.04em; }}
ul {{ padding-left:20px; }}
li {{ margin:12px 0; }}
code {{ background:var(--panel); padding:2px 5px; border-radius:4px; }}
details {{ margin-top:24px; }}
@media (max-width:760px) {{ .metrics {{ grid-template-columns:repeat(2,1fr); }} }}
</style>
</head>
<body>
<main>
<p class="eyebrow">Observed legal service delivery · synthetic demonstration</p>
<h1>Legal Function Outcome Control Tower</h1>
<p class="muted">Snapshot {html.escape(str(tower['generated_at_utc']))}. Local reviewer artifact with no external actions.</p>
<div class="metrics">
<div class="metric"><strong>{summary['completed_requests']}/{summary['requests']}</strong><span>completed requests</span></div>
<div class="metric"><strong>{summary['response_sla_attainment'] * 100:.1f}%</strong><span>response SLA attainment</span></div>
<div class="metric"><strong>{summary['stalled_requests']}</strong><span>stalled requests</span></div>
<div class="metric"><strong>{html.escape(str(summary['binding_queue']))}</strong><span>binding queue</span></div>
</div>
<section><h2>Stalled action queue</h2><ul>{actions}</ul></section>
<section><h2>Queue calibration</h2><table><thead><tr><th>Queue</th><th>Requests</th><th>Open</th><th>Stalled</th><th>Planned points</th><th>Observed minutes</th><th>Minutes / point</th></tr></thead><tbody>{queue_rows}</tbody></table></section>
<section><h2>Value proxies</h2><p>{html.escape(str(value['assumption_notice']))}</p>
<p><strong>EUR {value['estimated_labour_efficiency_value_eur']:.2f}</strong> estimated labour-efficiency value · <strong>EUR {value['estimated_external_spend_avoidance_eur']:.2f}</strong> estimated external-spend avoidance</p></section>
<section><h2>Request outcomes</h2><table><thead><tr><th>Request</th><th>Queue</th><th>State</th><th>Gross h</th><th>Business wait h</th><th>Controlled h</th><th>Response SLA</th><th>Resolution SLA</th></tr></thead><tbody>{request_rows}</tbody></table></section>
<section><h2>Review gate</h2><p>{html.escape(str(tower['review_gate']))}</p></section>
<details><summary>Machine-readable snapshot</summary><pre>{embedded}</pre></details>
</main>
</body>
</html>
"""


def write_outcome_artifacts(tower: dict[str, Any], output_dir: Path) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "json": output_dir / "legal-outcome-control-tower.json",
        "markdown": output_dir / "legal-outcome-control-tower.md",
        "html": output_dir / "legal-outcome-control-tower.html",
    }
    paths["json"].write_text(
        json.dumps(tower, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    paths["markdown"].write_text(render_outcome_markdown(tower), encoding="utf-8")
    paths["html"].write_text(render_outcome_html(tower), encoding="utf-8")
    return paths

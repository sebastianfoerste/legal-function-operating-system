"""The ``legal-function-os init`` interview: a few questions that write a policy file.

Every question shows the current answer in brackets, and Enter keeps it, so
pressing Enter throughout writes the bundled default values under your team's
name. The answers are checked as they are given: a value band must be one of the
bands you listed, the approval tiers must rise in order, and service levels must
be whole numbers. The thresholds you choose are your legal team's judgement; the
defaults are illustrative.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace

from legal_function_os.policy import PRIORITIES, Policy, SlaTarget, Threshold, default_policy

Ask = Callable[[str], str]
Say = Callable[[str], None]

DEFAULT_NAME = "Our legal team"
DESCRIPTION = (
    "Written by legal-function-os init. The thresholds, queues and service levels are "
    "this team's legal judgement: review them before relying on the output."
)
# Tries per question before the interview gives up, so a script feeding the wrong
# answers fails instead of looping forever.
MAX_TRIES = 3


class InterviewError(ValueError):
    """The interview could not be completed (repeated invalid answers)."""


def _question(
    ask: Ask, say: Say, prompt: str, default: str | None, parse: Callable[[str], object]
) -> object:
    shown = f" [{default}]" if default is not None else ""
    for _ in range(MAX_TRIES):
        answer = ask(f"{prompt}{shown}: ").strip()
        if not answer:
            if default is None:
                say("  An answer is required.")
                continue
            answer = default
        try:
            return parse(answer)
        except ValueError as exc:
            say(f"  {exc}")
    raise InterviewError(f"no usable answer to: {prompt}")


def _bands(answer: str) -> tuple[str, ...]:
    bands = tuple(part.strip() for part in answer.split(",") if part.strip())
    if len(bands) < 2:
        raise ValueError("List at least two value bands, lowest first, separated by commas.")
    if len(set(bands)) != len(bands):
        raise ValueError("Each value band may appear only once.")
    return bands


def _band_in(bands: tuple[str, ...], at_least: str | None = None, at_most: str | None = None):
    def parse(answer: str) -> str:
        if answer not in bands:
            raise ValueError(f"Choose one of: {', '.join(bands)}.")
        if at_least is not None and bands.index(answer) < bands.index(at_least):
            raise ValueError(
                f"Choose {at_least} or a higher band: a tier cannot start below the one before it."
            )
        if at_most is not None and bands.index(answer) > bands.index(at_most):
            raise ValueError(f"Choose {at_most} or a lower band.")
        return answer

    return parse


def _queue(answer: str) -> str:
    return answer


def _routing_changes(current: dict[str, str]):
    def parse(answer: str) -> dict[str, str]:
        if answer == "keep":
            return dict(current)
        routing = dict(current)
        for change in answer.split(","):
            if not change.strip():
                continue
            request_type, separator, queue = change.partition("=")
            request_type, queue = request_type.strip(), queue.strip()
            if not separator or not request_type:
                raise ValueError("Write each change as type=Queue, for example dpa=Privacy.")
            if queue:
                routing[request_type] = queue
            else:
                routing.pop(request_type, None)
        if not routing:
            raise ValueError("Keep at least one request type in the routing table.")
        return routing

    return parse


def _sla(answer: str) -> SlaTarget:
    parts = [part.strip() for part in answer.replace("/", ",").split(",")]
    if len(parts) != 2 or not all(part.isdigit() and int(part) > 0 for part in parts):
        raise ValueError(
            "Give two whole numbers above 0: response hours, resolution days (e.g. 8, 3)."
        )
    return SlaTarget(int(parts[0]), int(parts[1]))


def _default_band(bands: tuple[str, ...], band: str) -> str | None:
    """Offer the bundled threshold as the default only if the band still exists."""

    return band if band in bands else None


def _threshold(base: Threshold, bands_changed: bool, band: str, template: str) -> Threshold:
    """Keep the bundled sentence when the threshold is unchanged; otherwise describe the band."""

    if not bands_changed and band == base.value_band:
        return base
    return Threshold(band, template.format(band=band))


def run_interview(ask: Ask, say: Say, base: Policy | None = None) -> Policy:
    """Ask the questions and return the policy they describe."""

    base = base or default_policy()
    say("Answer each question, or press Enter to keep the value in brackets.")
    say("The defaults are illustrative; the thresholds you set are your legal judgement.")
    say("")
    name = str(_question(ask, say, "1. Whose policy is this (team or company name)", DEFAULT_NAME, _queue))

    say("")
    say("Value bands sort requests by contract or claim value. A request without a")
    say("value_band is in the first band.")
    bands = _question(
        ask,
        say,
        "2. Value bands, lowest first, separated by commas",
        ", ".join(base.value_bands),
        _bands,
    )
    assert isinstance(bands, tuple)
    changed = bands != base.value_bands

    say("")
    say("Approval tiers. Every request starts with a Reviewer; each tier below is added")
    say("from the value band you choose, and each starts at or above the one before.")
    lead = str(
        _question(
            ask,
            say,
            "3. Legal Ops Lead signs off from value band",
            _default_band(bands, base.legal_ops_lead_from),
            _band_in(bands),
        )
    )
    counsel = str(
        _question(
            ask,
            say,
            "4. General Counsel signs off from value band (also on every high-risk request; "
            "requests from this band are at least medium risk)",
            _default_band(bands, base.general_counsel_from),
            _band_in(bands, at_least=lead),
        )
    )
    board = str(
        _question(
            ask,
            say,
            "5. A request is high risk and needs a board note and a board-awareness "
            "escalation from value band",
            _default_band(bands, base.board_note_from),
            _band_in(bands, at_least=counsel),
        )
    )
    dispute = str(
        _question(
            ask,
            say,
            "6. A dispute is high risk, flagged for board attention and sent to external "
            "litigation counsel from value band",
            _default_band(bands, base.dispute_counsel_from),
            _band_in(bands),
        )
    )

    say("")
    say("Queues by request type:")
    for request_type, queue in base.routing.items():
        say(f"  {request_type} = {queue}")
    routing = _question(
        ask,
        say,
        "7. Changes as type=Queue separated by commas (a new type adds a row, type= removes "
        "one), or Enter to keep",
        "keep",
        _routing_changes(dict(base.routing)),
    )
    assert isinstance(routing, dict)
    unknown_queue = str(
        _question(
            ask,
            say,
            "8. Queue for a request whose type is not in the table (flagged for manual triage)",
            base.unknown_type_queue,
            _queue,
        )
    )
    transfer_queue = str(
        _question(
            ask,
            say,
            "9. Queue for any request with a non-EEA data transfer",
            base.non_eea_transfer_queue,
            _queue,
        )
    )

    say("")
    say("Service levels: business hours to respond and business days to resolve, by priority.")
    sla: dict[str, SlaTarget] = {}
    for number, priority in enumerate(PRIORITIES, start=10):
        current = base.sla[priority]
        target = _question(
            ask,
            say,
            f"{number}. {priority}: response hours, resolution days",
            f"{current.response_hours}, {current.resolution_days}",
            _sla,
        )
        assert isinstance(target, SlaTarget)
        sla[priority] = target

    return replace(
        base,
        name=name,
        description=DESCRIPTION,
        value_bands=bands,
        routing=routing,
        unknown_type_queue=unknown_queue,
        non_eea_transfer_queue=transfer_queue,
        sla=sla,
        legal_ops_lead_from=lead,
        general_counsel_from=counsel,
        board_note_from=board,
        high_risk_from=_threshold(
            base.high_risk_from, changed, board, "Contract value in band {band} or above."
        ),
        medium_risk_from=_threshold(
            base.medium_risk_from, changed, counsel, "Contract value in band {band} or above."
        ),
        dispute_high_risk_from=_threshold(
            base.dispute_high_risk_from, changed, dispute, "Dispute in value band {band} or above."
        ),
        dispute_counsel_from=dispute,
        board_awareness_from=_threshold(
            base.board_awareness_from,
            changed,
            board,
            "Value in band {band} or above: add to board awareness list.",
        ),
        dispute_board_attention_from=dispute,
        source="legal-function-os init",
    )

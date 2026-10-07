"""Review policy decisions that belong to the legal function, kept in one place."""

from __future__ import annotations

# Fields whose every change alters what was reviewed or who must approve it.
_ALWAYS_SUBSTANTIVE = ("document", "playbook", "routing:", "decision_authority", "source_refs")
_NEVER_SUBSTANTIVE = ("matter:title",)


def _normalise(value: str) -> str:
    return " ".join(value.split()).casefold()


def is_substantive_change(field: str, before: str, after: str) -> bool:
    """Decide whether an edit invalidates approvals and triggers reassessment.

    ``field`` names what changed: ``document``, ``playbook``, ``instructions``,
    ``decision_authority``, ``source_refs``, ``fact:<key>``, ``matter:<field>`` or
    ``routing:<field>``. ``before`` and ``after`` are the old and new values (digests
    for the document and the playbook).

    Default policy: a change to the document, the playbook, a routing input, the
    decision authority or the source references is always substantive. Free-text
    facts, instructions and matter fields are substantive unless they differ only
    in whitespace or letter case. The matter title is a label and never substantive.
    """

    # TODO(human): this default is deliberately conservative. Decide as the legal owner
    # whether some fields should invalidate only the approvals they affect, for example
    # whether a changed `fact:signature_target_date` needs a fresh privacy sign-off.
    if before == after or field in _NEVER_SUBSTANTIVE:
        return False
    if field.startswith(_ALWAYS_SUBSTANTIVE):
        return True
    return _normalise(before) != _normalise(after)

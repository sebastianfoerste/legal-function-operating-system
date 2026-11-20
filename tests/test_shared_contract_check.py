"""``make contract-check`` stops when the pilot's mapping onto the shared contract drifts.

``scripts/check_shared_contracts.py`` reads the pilot's source as text. A closed pilot
matter is reported by how it closed: only a matter whose delivery the requester accepted
is ``approved`` in ``legal-workflow-controls.v1``, and a withdrawn one is ``rejected``
(ADR 0010, amended on 2026-11-20). These tests change the text the check reads and expect
it to refuse; the repository's files are only read.

The check does not run the pilot. What ``contract_review_state`` returns is pinned by
``supervised-agent/tests/test_pilot_contract_closings.py``; here the function's text is
changed, and the check has to notice that it no longer begins with the closed branch.
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import unittest
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parents[1]
PILOT = ROOT / "supervised-agent" / "src" / "pilot"
SCHEMA = ROOT / "contracts" / "legal-workflow-controls.v1.schema.json"
LOOKUP = '        return CLOSED_OUTCOME_REVIEW_STATE.get(closed_outcome or "", "rejected")\n'
NOT_BY_OUTCOME = (
    "pilot does not decide a closed matter from its closing outcome, rejected unless mapped: "
    "contract_review_state"
)


def _script(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


check = _script("check_shared_contracts")


class PilotMappingCheckTest(unittest.TestCase):
    def setUp(self) -> None:
        schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
        self.allowed = set(schema["properties"]["review_state"]["enum"])
        self.texts = {
            "bridge": (PILOT / "parent_bridge.py").read_text(encoding="utf-8"),
            "machine": (PILOT / "state_machine.py").read_text(encoding="utf-8"),
            "service": (PILOT / "service.py").read_text(encoding="utf-8"),
        }

    def _changed(self, name: str, old: str, new: str) -> dict[str, str]:
        """The texts the check reads, with ``old`` replaced in one of them."""

        self.assertIn(old, self.texts[name])
        return {**self.texts, name: self.texts[name].replace(old, new)}

    def _refusal(self, texts: dict[str, str]) -> str:
        with self.assertRaises(SystemExit) as raised:
            check.check_pilot_mapping(**texts, allowed=self.allowed)
        return str(raised.exception)

    def test_the_repository_passes(self) -> None:
        check.check_pilot_mapping(**self.texts, allowed=self.allowed)
        printed = io.StringIO()
        with contextlib.redirect_stdout(printed):
            self.assertEqual(check.main(), 0)
        self.assertEqual(printed.getvalue(), "shared legal workflow control contract passed\n")

    def test_only_a_delivered_and_accepted_matter_closes_approved(self) -> None:
        self.assertNotIn("closed", check.PILOT_STATE_MAP)
        self.assertEqual(
            check.PILOT_CLOSED_OUTCOME_MAP,
            {
                "delivered_locally_and_accepted": "approved",
                "withdrawn_without_delivery": "rejected",
            },
        )

    def test_a_closed_matter_mapped_by_its_state_alone_is_refused(self) -> None:
        entry = '    "declined": "rejected",\n'
        for shared in sorted(self.allowed):
            with self.subTest(shared):
                texts = self._changed("bridge", entry, f'    "closed": "{shared}",\n{entry}')
                self.assertEqual(
                    self._refusal(texts),
                    "pilot maps a closed matter by its state alone, not by how it closed",
                )

    def test_a_function_that_does_not_begin_with_the_closed_branch_is_refused(self) -> None:
        # The tables are untouched in each case; only what the function does with them changes.
        branch = '    if state == "closed":\n' + LOOKUP
        changes = {
            "every closed matter approved": (LOOKUP, '        return "approved"\n'),
            "an unknown outcome approved": (LOOKUP, LOOKUP.replace('"rejected"', '"approved"')),
            "an unknown outcome raises": (
                LOOKUP,
                "        return CLOSED_OUTCOME_REVIEW_STATE[closed_outcome]\n",
            ),
            "read from the state table": (
                LOOKUP,
                '        return CONTRACT_REVIEW_STATE.get(state, "approved")\n',
            ),
            "an earlier return": (
                branch,
                '    if closed_outcome is None:\n        return "approved"\n' + branch,
            ),
            "no closed branch": (branch, ""),
            "the function renamed": ("def contract_review_state(", "def review_state_for("),
        }
        for name, (old, new) in changes.items():
            with self.subTest(name):
                self.assertEqual(self.texts["bridge"].count(old), 1)
                self.assertEqual(self._refusal(self._changed("bridge", old, new)), NOT_BY_OUTCOME)

    def test_the_closed_branch_is_read_past_the_docstring_and_comments(self) -> None:
        # The check reads the function's code lines, so words around them change nothing.
        source = (
            "def other() -> None:\n    return None\n\n\n"
            "def contract_review_state(state: str, closed_outcome: str | None) -> str:\n"
            '    """A docstring that says return "approved" changes nothing."""\n\n'
            "    # Nor does a comment.\n"
            '    if state == "closed":\n' + LOOKUP + "    return CONTRACT_REVIEW_STATE[state]\n"
            "\n\nAFTER = 1\n"
        )
        self.assertEqual(
            check.function_code_lines(source, "contract_review_state"),
            [*check.PILOT_CLOSED_BRANCH, "return CONTRACT_REVIEW_STATE[state]"],
        )
        self.assertEqual(check.function_code_lines(source, "other"), ["return None"])
        self.assertEqual(check.function_code_lines(source, "review_state"), [])
        self.assertEqual(
            check.function_code_lines(self.texts["bridge"], "contract_review_state")[:2],
            check.PILOT_CLOSED_BRANCH,
        )

    def test_a_closing_outcome_mapped_to_another_value_is_refused(self) -> None:
        for outcome, mapped in check.PILOT_CLOSED_OUTCOME_MAP.items():
            for other in sorted(self.allowed - {mapped}):
                with self.subTest(outcome=outcome, other=other):
                    texts = self._changed(
                        "bridge", f'"{outcome}": "{mapped}"', f'"{outcome}": "{other}"'
                    )
                    self.assertEqual(
                        self._refusal(texts),
                        f"pilot closing outcome mapping is missing or changed: {outcome}",
                    )

    def test_a_closing_outcome_the_service_does_not_record_is_refused(self) -> None:
        for outcome in check.PILOT_CLOSED_OUTCOME_MAP:
            with self.subTest(outcome):
                texts = self._changed("service", f'"{outcome}"', '"closed_some_other_way"')
                self.assertEqual(
                    self._refusal(texts),
                    f"pilot closing outcome is missing from the service: {outcome}",
                )

    def test_a_state_machine_without_the_closed_state_is_refused(self) -> None:
        texts = self._changed("machine", '"closed"', '"shut"')
        self.assertEqual(
            self._refusal(texts), "pilot state is missing from the state machine: closed"
        )


if __name__ == "__main__":
    unittest.main()

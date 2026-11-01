"""Approval matrix: the rules' approval chain for every value band and risk level."""

from __future__ import annotations

import contextlib
import io
import json
import re
import tempfile
import unittest
from dataclasses import replace
from html.parser import HTMLParser
from pathlib import Path
from unittest import mock

from legal_function_os import approval_matrix
from legal_function_os.approval_matrix import (
    RISK_FIELDS,
    RISKS,
    build_approval_matrix,
    render_approval_html,
    render_approval_markdown,
)
from legal_function_os.cli import main as cli_main
from legal_function_os.policy import Policy, Threshold, default_policy, render_policy_json
from legal_function_os.rules import approval_chain, assess_risk, decide

ROOT = Path(__file__).resolve().parents[1]
SAMPLE = ROOT / "src" / "legal_function_os" / "data" / "sample_requests.json"


def _requests() -> list[dict]:
    return json.loads(SAMPLE.read_text(encoding="utf-8"))


def _cells(matrix: dict) -> dict:
    return {
        (row["value_band"], cell["risk"]): cell for row in matrix["rows"] for cell in row["cells"]
    }


def _unreachable(matrix: dict) -> dict:
    return {
        key: cell["unreachable_reason"]
        for key, cell in _cells(matrix).items()
        if not cell["reachable"]
    }


def _run(argv: list[str]) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = cli_main(argv)
    return code, out.getvalue(), err.getvalue()


def _rename_bands(policy: Policy, names: dict[str, str]) -> Policy:
    """``policy`` with its value bands renamed, every threshold following its band."""

    def threshold(value: Threshold) -> Threshold:
        return replace(value, value_band=names[value.value_band])

    return replace(
        policy,
        value_bands=tuple(names[band] for band in policy.value_bands),
        legal_ops_lead_from=names[policy.legal_ops_lead_from],
        general_counsel_from=names[policy.general_counsel_from],
        board_note_from=names[policy.board_note_from],
        high_risk_from=threshold(policy.high_risk_from),
        medium_risk_from=threshold(policy.medium_risk_from),
        dispute_high_risk_from=threshold(policy.dispute_high_risk_from),
        dispute_counsel_from=names[policy.dispute_counsel_from],
        board_awareness_from=threshold(policy.board_awareness_from),
        dispute_board_attention_from=names[policy.dispute_board_attention_from],
    )


def _spread_policy() -> Policy:
    """Eight bands with every approval and risk threshold on a band of its own, so a
    ladder or cell that reads the wrong threshold shows."""

    bands = ("none", *(f"tier-{n}" for n in range(1, 8)))
    return replace(
        default_policy(),
        name="Spread test policy",
        value_bands=bands,
        legal_ops_lead_from="tier-1",
        general_counsel_from="tier-3",
        board_note_from="tier-6",
        medium_risk_from=Threshold("tier-2", "Medium from tier 2."),
        dispute_high_risk_from=Threshold("tier-4", "Dispute high from tier 4."),
        high_risk_from=Threshold("tier-5", "High from tier 5."),
        dispute_counsel_from="tier-4",
        board_awareness_from=Threshold("tier-6", "Board awareness from tier 6."),
        dispute_board_attention_from="tier-5",
        elevated_types=("corporate",),
    )


class _Cells(HTMLParser):
    """The body cells of each table on a page: tag, attributes and text."""

    def __init__(self) -> None:
        super().__init__()
        self.tables: list[list[dict]] = []
        self._cell: dict | None = None
        self._body = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "table":
            self.tables.append([])
        elif tag == "tbody":
            self._body = True
        elif tag in ("td", "th") and self._body:
            self._cell = {"tag": tag, "attrs": dict(attrs), "text": ""}
            self.tables[-1].append(self._cell)

    def handle_endtag(self, tag: str) -> None:
        if tag == "tbody":
            self._body = False
        elif tag in ("td", "th"):
            self._cell = None

    def handle_data(self, data: str) -> None:
        if self._cell is not None:
            self._cell["text"] += data


def _page_cells(page: str) -> list[list[dict]]:
    parser = _Cells()
    parser.feed(page)
    return parser.tables


class ApprovalMatrixTests(unittest.TestCase):
    def setUp(self) -> None:
        self.policy = default_policy()
        self.matrix = build_approval_matrix(_requests(), self.policy)

    def test_every_cell_is_the_rules_chain_and_starts_with_a_human(self) -> None:
        cells = _cells(self.matrix)
        self.assertEqual(len(cells), len(self.policy.value_bands) * len(RISKS))
        for (band, risk), cell in cells.items():
            if cell["reachable"]:
                self.assertEqual(
                    cell["approval_chain"],
                    approval_chain({"value_band": band}, risk, self.policy),
                )
                self.assertEqual(cell["approval_chain"][0], "Reviewer")
            else:
                self.assertEqual((cell["approval_chain"], cell["requests"]), ([], []))

    def test_only_unreachable_combinations_are_marked(self) -> None:
        self.assertEqual(
            _unreachable(self.matrix),
            {
                ("250k-1m", "LOW"): "Every request in this band is at least MEDIUM risk.",
                (">1m", "LOW"): "Every request in this band is HIGH risk.",
                (">1m", "MEDIUM"): "Every request in this band is HIGH risk.",
            },
        )

    def test_reachability_follows_a_policy_with_other_thresholds(self) -> None:
        policy = _spread_policy()
        matrix = build_approval_matrix([], policy)
        medium = "Every request in this band is at least MEDIUM risk."
        high = "Every request in this band is HIGH risk."
        self.assertEqual(
            _unreachable(matrix),
            {
                ("tier-2", "LOW"): medium,
                ("tier-3", "LOW"): medium,
                ("tier-4", "LOW"): medium,
                **{(band, risk): high for band in policy.value_bands[5:] for risk in ("LOW", "MEDIUM")},
            },
        )

    def test_reachability_covers_every_field_assess_risk_reads(self) -> None:
        read: set[str] = set()

        class Recording(dict):
            def get(self, key, default=None):
                read.add(key)
                return super().get(key, default)

            def __getitem__(self, key):
                read.add(key)
                return super().__getitem__(key)

            def __contains__(self, key):
                read.add(key)
                return super().__contains__(key)

        for policy in (self.policy, _spread_policy()):
            inputs = approval_matrix._risk_inputs(policy)
            # The enumeration varies exactly the guarded fields, every combination once.
            self.assertTrue(all(list(item) == list(RISK_FIELDS) for item in inputs))
            types = {item["type"] for item in inputs}
            self.assertEqual(types, {None, *policy.elevated_types, "dispute"})
            self.assertEqual(len(inputs), len(policy.value_bands) * 2**3 * len(types))
            self.assertEqual(len({tuple(item.values()) for item in inputs}), len(inputs))

            read.clear()
            for request in inputs:
                assess_risk(Recording(request), policy)
            self.assertEqual(read, set(RISK_FIELDS))

    def test_a_blank_elevated_type_hides_no_reachable_cell(self) -> None:
        policy = replace(default_policy(), elevated_types=("", "corporate", "  "))
        matrix = build_approval_matrix(_requests(), policy)
        self.assertEqual(_unreachable(matrix), _unreachable(self.matrix))
        self.assertTrue(_cells(matrix)[("none", "LOW")]["reachable"])
        medium = next(step for step in matrix["risk_ladder"] if step["risk"] == "MEDIUM")
        self.assertEqual(medium["any_of"][-1], "Request type (no type), corporate, (no type)")

    def test_a_cell_holding_a_request_is_never_marked_unreachable(self) -> None:
        # Even if the enumeration missed a combination, a placed request shows its cell.
        with mock.patch.object(approval_matrix, "assess_risk", return_value=("LOW", [])):
            matrix = build_approval_matrix(_requests(), self.policy)
        cells = _cells(matrix)
        for request in _requests():
            decision = decide(request, self.policy)
            cell = cells[(request["value_band"], decision.risk)]
            self.assertTrue(cell["reachable"], decision.request_id)
            self.assertEqual(cell["approval_chain"], decision.approval_chain)
            self.assertIsNone(cell["unreachable_reason"])

    def test_the_ladders_say_what_the_rules_do(self) -> None:
        for policy in (self.policy, _spread_policy()):
            with self.subTest(policy=policy.name):
                self._check_ladders(policy)

    def _check_ladders(self, policy: Policy) -> None:
        matrix = build_approval_matrix([], policy)
        bands = policy.value_bands
        lowest = bands[0]
        self.assertEqual(
            matrix["approval_ladder"],
            [
                {"when": "Every request", "adds": "Reviewer"},
                {"when": f'Value band "{policy.legal_ops_lead_from}" or above', "adds": "Legal Ops Lead"},
                {
                    "when": f'Value band "{policy.general_counsel_from}" or above, or HIGH risk',
                    "adds": "General Counsel",
                },
                {"when": f'Value band "{policy.board_note_from}" or above', "adds": "Board note"},
            ],
        )
        for role, threshold in (
            ("Legal Ops Lead", policy.legal_ops_lead_from),
            ("General Counsel", policy.general_counsel_from),
            ("Board note", policy.board_note_from),
        ):
            self.assertIn(role, approval_chain({"value_band": threshold}, "LOW", policy))
            index = bands.index(threshold)
            if index:
                below = bands[index - 1]
                self.assertNotIn(role, approval_chain({"value_band": below}, "LOW", policy))
        self.assertIn("General Counsel", approval_chain({"value_band": lowest}, "HIGH", policy))

        self.assertEqual(
            matrix["risk_ladder"],
            [
                {
                    "risk": "HIGH",
                    "any_of": [
                        "Personal data transferred outside the EEA",
                        f'Value band "{policy.high_risk_from.value_band}" or above',
                        "Uncapped liability",
                        f'A dispute at value band "{policy.dispute_high_risk_from.value_band}" or above',
                    ],
                },
                {
                    "risk": "MEDIUM",
                    "any_of": [
                        f'Value band "{policy.medium_risk_from.value_band}" or above',
                        "Personal data processed",
                        "Request type " + ", ".join(policy.elevated_types),
                    ],
                },
                {"risk": "LOW", "any_of": []},
            ],
        )
        plain = {"value_band": lowest, "type": None}
        high_band = policy.high_risk_from.value_band
        dispute_band = policy.dispute_high_risk_from.value_band
        high = [
            {**plain, "personal_data": True, "non_eea_transfer": True},
            {**plain, "value_band": high_band},
            {**plain, "uncapped_liability": True},
            {**plain, "type": "dispute", "value_band": dispute_band},
        ]
        # One band below each band threshold, the condition no longer applies.
        not_high = [
            {**plain, **extra, "value_band": bands[bands.index(band) - 1]}
            for band, extra in ((high_band, {}), (dispute_band, {"type": "dispute"}))
            if bands.index(band)
        ]
        medium = [
            {**plain, "value_band": policy.medium_risk_from.value_band},
            {**plain, "personal_data": True},
            *({**plain, "type": t} for t in policy.elevated_types),
        ]
        for request in high:
            self.assertEqual(assess_risk(request, policy)[0], "HIGH", request)
        for request in not_high:
            self.assertNotEqual(assess_risk(request, policy)[0], "HIGH", request)
        for request in medium:
            self.assertEqual(assess_risk(request, policy)[0], "MEDIUM", request)
        self.assertEqual(assess_risk(plain, policy)[0], "LOW")

    def test_each_portfolio_request_sits_in_the_cell_its_decision_names(self) -> None:
        names = {"none": "none", "<50k": "tier-1", "50k-250k": "tier-3", "250k-1m": "tier-4", ">1m": "tier-7"}
        spread = [{**r, "value_band": names[r["value_band"]]} for r in _requests()]
        for policy, requests in ((self.policy, _requests()), (_spread_policy(), spread)):
            with self.subTest(policy=policy.name):
                cells = _cells(build_approval_matrix(requests, policy))
                placed = [rid for cell in cells.values() for rid in cell["requests"]]
                self.assertEqual(sorted(placed), sorted(r["id"] for r in requests))
                for request in requests:
                    decision = decide(request, policy)
                    cell = cells[(request.get("value_band") or policy.value_bands[0], decision.risk)]
                    self.assertIn(decision.request_id, cell["requests"])
                    self.assertTrue(cell["reachable"])
                    self.assertEqual(cell["approval_chain"], decision.approval_chain)

    def test_a_request_without_a_value_band_counts_in_the_lowest_band(self) -> None:
        request = {**_requests()[2], "id": "REQ-NO-BAND"}
        del request["value_band"]
        matrix = build_approval_matrix([request], self.policy)
        [item] = matrix["requests"]
        self.assertEqual(item["value_band"], self.policy.value_bands[0])
        self.assertIn("REQ-NO-BAND", _cells(matrix)[(item["value_band"], item["risk"])]["requests"])

    def test_the_matrix_follows_the_policy(self) -> None:
        policy = replace(default_policy(), general_counsel_from="50k-250k", elevated_types=())
        matrix = build_approval_matrix([], policy)
        cell = _cells(matrix)[("50k-250k", "LOW")]
        self.assertEqual(cell["approval_chain"], ["Reviewer", "Legal Ops Lead", "General Counsel"])
        ladder = {step["adds"]: step["when"] for step in matrix["approval_ladder"]}
        self.assertTrue(ladder["General Counsel"].startswith('Value band "50k-250k"'))
        medium = next(step for step in matrix["risk_ladder"] if step["risk"] == "MEDIUM")
        self.assertEqual(len(medium["any_of"]), 2)
        # Without elevated types, LOW stays reachable in every band below medium_from.
        self.assertEqual(set(_unreachable(matrix)), set(_unreachable(self.matrix)))
        self.assertEqual(matrix["requests"], [])
        self.assertIn("No request was given.", render_approval_markdown(matrix))

    def test_markdown_gives_each_reason_and_keeps_each_line_whole(self) -> None:
        markdown = render_approval_markdown(self.matrix)
        page = render_approval_html(self.matrix)
        for reason in set(_unreachable(self.matrix).values()):
            self.assertIn(f"Not reachable. {reason}", markdown)
            self.assertIn(reason, page)
        row = next(line for line in markdown.splitlines() if line.startswith("| >1m |"))
        self.assertEqual(
            row,
            "| >1m | Not reachable. Every request in this band is HIGH risk. "
            "| Not reachable. Every request in this band is HIGH risk. "
            "| Reviewer → Legal Ops Lead → General Counsel → Board note (REQ-1001, REQ-1005) |",
        )

        broken = "50k-\r\n250k"
        policy = _rename_bands(
            replace(default_policy(), name="Acme\n# Not a heading"),
            {"none": "none", "<50k": "<50k", "50k-250k": broken, "250k-1m": "250k-1m", ">1m": ">1m"},
        )
        markdown = render_approval_markdown(build_approval_matrix([], policy))
        self.assertNotIn("\r", markdown)
        self.assertEqual([line for line in markdown.splitlines() if line.startswith("# ")], ["# Approval matrix"])
        self.assertIn("Policy: Acme # Not a heading. ", markdown)
        self.assertIn('- Value band "50k- 250k" or above: Legal Ops Lead', markdown.splitlines())
        self.assertTrue(any(line.startswith("| 50k- 250k | ") for line in markdown.splitlines()))
        for line in markdown.splitlines():
            if line.startswith("| "):
                self.assertEqual(line.replace("\\|", "").count("|"), 5, line)

    def test_rendering_is_deterministic_escaped_and_self_contained(self) -> None:
        policy = replace(default_policy(), name='Policy <script>alert(1)</script> | "x"')
        requests = _requests()
        requests[0]["title"] = "MSA | <b>bold</b>"
        matrix = build_approval_matrix(requests, policy)
        page = render_approval_html(matrix)
        self.assertEqual(page, render_approval_html(build_approval_matrix(requests, policy)))
        self.assertNotIn("<script", page)
        self.assertNotIn("<b>bold</b>", page)
        for forbidden in ("http://", "https://", "<link"):
            self.assertNotIn(forbidden, page)
        markdown = render_approval_markdown(matrix)
        row = next(line for line in markdown.splitlines() if line.startswith("| REQ-1001 "))
        self.assertEqual(row.replace("\\|", "").count("|"), 6)

    def test_the_page_states_its_limits_and_labels_every_cell(self) -> None:
        page = render_approval_html(self.matrix)
        self.assertIn("Nothing here is legal advice.", page)
        self.assertIn("the matrix approves nothing", page)
        # A placed request is said to land in a cell; ✓ means pass elsewhere in the project.
        self.assertNotIn("✓", page)
        self.assertIn(
            '2 portfolio requests land here: <span class="token nowrap">REQ-1001</span>, '
            '<span class="token nowrap">REQ-1005</span>',
            page,
        )
        self.assertIn('1 portfolio request lands here: <span class="token nowrap">REQ-1008</span>', page)
        self.assertIn('<td data-label="Request"><span class="token nowrap">REQ-1001</span></td>', page)

        matrix_cells, portfolio_cells = _page_cells(page)
        labels = ["Value band", *(f"{risk} risk" for risk in RISKS)]
        self.assertEqual(len(matrix_cells), len(self.matrix["rows"]) * len(labels))
        matched = {rid for cell in _cells(self.matrix).values() for rid in cell["requests"]}
        for index, cell in enumerate(matrix_cells):
            self.assertEqual(cell["attrs"].get("data-label"), labels[index % len(labels)])
            holds = "land" in cell["text"]
            self.assertEqual(cell["attrs"].get("class") == "matched", holds, cell)
            if holds:
                matched -= set(re.findall(r"REQ-\d+", cell["text"]))
        self.assertEqual(matched, set())
        columns = ["Request", "Title", "Value band", "Risk", "Approval chain"]
        self.assertEqual(len(portfolio_cells), len(self.matrix["requests"]) * len(columns))
        for index, cell in enumerate(portfolio_cells):
            self.assertEqual(cell["attrs"].get("data-label"), columns[index % len(columns)])

    def test_long_band_names_and_request_ids_can_wrap(self) -> None:
        long_band = "Above EUR 1,000,000 including multi-year framework agreements"
        long_id = "REQ-2026-COMMERCIAL-FRAMEWORK-AGREEMENT-0001"
        policy = _rename_bands(
            default_policy(),
            {"none": "none", "<50k": "<50k", "50k-250k": "50k-250k", "250k-1m": "250k-1m", ">1m": long_band},
        )
        requests = [{**r, "value_band": long_band} for r in _requests()[:2]]
        requests[0]["id"] = long_id
        page = render_approval_html(build_approval_matrix(requests, policy))
        # Short text stays whole above the phone layout; long text can wrap anywhere.
        self.assertIn('<span class="token nowrap">50k-250k</span>', page)
        self.assertIn('<span class="token nowrap">REQ-1002</span>', page)
        self.assertEqual(page.count(f'<span class="token">{long_band}</span>'), 3)
        self.assertEqual(page.count(f'<span class="token">{long_id}</span>'), 2)
        style = page[page.index("<style>") : page.index("</style>")]
        self.assertIn(".token { display:inline-block; max-width:100%; overflow-wrap:anywhere; }", style)
        row_header = re.search(r'th\[scope="row"\] \{([^}]*)\}', style)
        assert row_header is not None
        self.assertNotIn("nowrap", row_header.group(1))
        narrow = style[style.index("@media (max-width:640px)") :]
        self.assertIn(".nowrap { white-space:normal; }", narrow)
        self.assertNotIn('class="nowrap" data-label="Value band"', page)

    def test_the_cli_prints_and_writes_the_committed_matrix(self) -> None:
        code, stdout, _ = _run(["approval-matrix", "--format", "json"])
        self.assertEqual(code, 0)
        self.assertEqual(
            stdout, (ROOT / "examples" / "approval-matrix.json").read_text(encoding="utf-8")
        )
        for argv in (["approval-matrix", "--out"], ["--quiet", "--approval-matrix-output"]):
            with tempfile.TemporaryDirectory() as tmp:
                self.assertEqual(_run([*argv, tmp])[0], 0)
                self.assertEqual(
                    sorted(path.name for path in Path(tmp).glob("approval-matrix.*")),
                    ["approval-matrix.html", "approval-matrix.json", "approval-matrix.md"],
                )

    def test_the_cli_shows_a_custom_policy_without_requests(self) -> None:
        names = {"none": "none", "<50k": "under-50k", "50k-250k": "50k-to-250k", "250k-1m": "250k-to-1m", ">1m": "over-1m"}
        policy = replace(_rename_bands(default_policy(), names), name="Renamed bands")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "policy.json"
            path.write_text(render_policy_json(policy), encoding="utf-8")
            code, stdout, stderr = _run(["approval-matrix", "--policy", str(path), "--format", "json"])
            self.assertEqual(code, 0, stderr)
            self.assertIn("no --input given, so no request is placed", stderr)
            matrix = json.loads(stdout)
            self.assertEqual(matrix["policy"], "Renamed bands")
            self.assertEqual([row["value_band"] for row in matrix["rows"]], list(policy.value_bands))
            self.assertEqual(matrix["requests"], [])

            requests = Path(tmp) / "requests.json"
            renamed = [{**r, "value_band": names[r["value_band"]]} for r in _requests()]
            requests.write_text(json.dumps(renamed), encoding="utf-8")
            argv = ["approval-matrix", "--policy", str(path), "--input", str(requests), "--format", "json"]
            code, stdout, stderr = _run(argv)
            self.assertEqual(code, 0, stderr)
            self.assertNotIn("no --input given", stderr)
            self.assertEqual(len(json.loads(stdout)["requests"]), len(renamed))

            # The bundled sample requests are still checked against the default policy.
            code, stdout, stderr = _run(["approval-matrix", "--format", "json"])
            self.assertEqual(len(json.loads(stdout)["requests"]), len(_requests()))


if __name__ == "__main__":
    unittest.main()

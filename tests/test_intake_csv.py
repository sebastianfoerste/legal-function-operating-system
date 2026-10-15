"""A request log kept in a spreadsheet can be passed to --input as CSV."""

from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from legal_function_os.board_pack import build_board_pack
from legal_function_os.cli import main as cli_main
from legal_function_os.intake import InputError, load_requests
from legal_function_os.intake_csv import CsvFormatError, parse_csv
from legal_function_os.validation import validate_requests

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "examples" / "requests-template.csv"
SAMPLE = ROOT / "src" / "legal_function_os" / "data" / "sample_requests.json"


def run_cli(argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = cli_main(argv)
    return code, out.getvalue(), err.getvalue()


class TemplateTest(unittest.TestCase):
    def test_template_holds_the_bundled_requests(self):
        loaded = load_requests(str(TEMPLATE))
        sample = json.loads(SAMPLE.read_text(encoding="utf-8"))
        self.assertEqual(loaded.requests, sample)
        self.assertEqual(loaded.labels[0], "row 2")
        self.assertEqual(loaded.notes, [])

    def test_template_gives_the_same_board_pack_as_the_json(self):
        from_csv = build_board_pack(load_requests(str(TEMPLATE)).requests, period="Q")
        from_json = build_board_pack(json.loads(SAMPLE.read_text(encoding="utf-8")), period="Q")
        self.assertEqual(from_csv.to_dict(), from_json.to_dict())

    def test_cli_reads_the_template(self):
        code, stdout, stderr = run_cli(["--input", str(TEMPLATE)])
        self.assertEqual((code, stderr), (0, ""))
        self.assertIn("**8** legal requests handled", stdout)


class CellsTest(unittest.TestCase):
    def test_headers_are_matched_like_field_names(self):
        table = parse_csv(
            "Request ID,Title,Request type,Value band,personalData,Non-EEA transfer,Requester\n"
            "REQ-1,MSA,commercial_contract,>1m,yes,,sales\n"
        )
        self.assertEqual(
            table.requests,
            [
                {
                    "id": "REQ-1",
                    "title": "MSA",
                    "type": "commercial_contract",
                    "value_band": ">1m",
                    "personal_data": True,
                    "requested_by": "sales",
                }
            ],
        )

    def test_yes_no_answers_become_booleans(self):
        answers = {
            "yes": True, "Ja": True, "WAHR": True, "x": True, "1": True, "TRUE": True,
            "no": False, "nein": False, "FALSCH": False, "0": False, "false": False,
        }
        for answer, expected in answers.items():
            with self.subTest(answer=answer):
                table = parse_csv(f"id,title,uncapped_liability\nREQ-1,MSA,{answer}\n")
                self.assertIs(table.requests[0]["uncapped_liability"], expected)

    def test_other_answers_are_left_for_validation(self):
        table = parse_csv("id,title,personal_data\nREQ-1,MSA,maybe\n")
        self.assertEqual(table.requests[0]["personal_data"], "maybe")
        [issue] = validate_requests(table.requests).errors
        self.assertEqual(issue.describe(lambda index: table.labels[index]).split(": ")[:3], [
            "error", "row 2 (REQ-1)", "personal_data"
        ])

    def test_empty_cells_take_the_default(self):
        table = parse_csv("id,title,type,value_band,urgency\nREQ-1,MSA,,  ,\n")
        self.assertEqual(table.requests, [{"id": "REQ-1", "title": "MSA"}])

    def test_auxiliary_columns_keep_their_json_types(self):
        table = parse_csv(
            'id,title,awaiting_business_input,facts\nREQ-1,MSA,no,"Term: 36 months\nCap: 12 months fees"\n'
        )
        request = table.requests[0]
        self.assertIs(request["awaiting_business_input"], False)
        self.assertEqual(request["facts"], ["Term: 36 months", "Cap: 12 months fees"])

    def test_quoted_delimiters_stay_in_the_cell(self):
        table = parse_csv('id,title,counterparty\nREQ-1,"MSA, renewal","Globex, Inc."\n')
        self.assertEqual(table.requests[0]["counterparty"], "Globex, Inc.")


class DialectsTest(unittest.TestCase):
    def test_semicolon_and_tab_delimiters(self):
        for delimiter in (";", "\t"):
            with self.subTest(delimiter=repr(delimiter)):
                text = delimiter.join(("id", "title", "value_band")) + "\n"
                text += delimiter.join(("REQ-1", "MSA, renewal", "250k-1m")) + "\n"
                self.assertEqual(
                    parse_csv(text).requests,
                    [{"id": "REQ-1", "title": "MSA, renewal", "value_band": "250k-1m"}],
                )

    def test_windows_code_page_and_byte_order_mark(self):
        with tempfile.TemporaryDirectory() as tmp:
            legacy = Path(tmp) / "legacy.csv"
            legacy.write_bytes("id;title\nREQ-1;Gesellschaftervereinbarung Müller\n".encode("cp1252"))
            loaded = load_requests(str(legacy))
            self.assertEqual(loaded.requests[0]["title"], "Gesellschaftervereinbarung Müller")
            self.assertIn("read as Windows-1252", loaded.notes[0])

            bom = Path(tmp) / "bom.csv"
            bom.write_bytes("id,title\nREQ-1,MSA\n".encode("utf-8-sig"))
            loaded = load_requests(str(bom))
            self.assertEqual((loaded.requests, loaded.notes), ([{"id": "REQ-1", "title": "MSA"}], []))

            # Excel's "Unicode Text" export: UTF-16 with a byte order mark, tab-separated.
            unicode_text = Path(tmp) / "unicode.tsv"
            unicode_text.write_bytes("id\ttitle\r\nREQ-1\tAVV Müller\r\n".encode("utf-16"))
            loaded = load_requests(str(unicode_text))
            self.assertEqual((loaded.requests, loaded.notes), ([{"id": "REQ-1", "title": "AVV Müller"}], []))

    def test_blank_rows_are_skipped_and_rows_keep_spreadsheet_numbers(self):
        table = parse_csv("id,title\nREQ-1,MSA\n,\n\nREQ-2,NDA\n")
        self.assertEqual([request["id"] for request in table.requests], ["REQ-1", "REQ-2"])
        self.assertEqual(table.labels, ["row 2", "row 5"])


class ProblemsTest(unittest.TestCase):
    def test_capitalised_value_band_is_rejected_with_the_row(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "requests.csv"
            source.write_text("id,title,value_band\nREQ-1,MSA,>1m\nREQ-2,Big MSA,>1M\n", encoding="utf-8")
            out_dir = Path(tmp) / "out"
            code, stdout, stderr = run_cli(["--input", str(source), "--out", str(out_dir)])
            self.assertEqual(code, 2)
            self.assertFalse(out_dir.exists())
        self.assertEqual(stdout, "")
        self.assertIn("error: row 3 (REQ-2): value_band: '>1M' is not a value band (did you mean '>1m'?)", stderr)

    def test_misspelled_column_is_rejected_once_not_per_row(self):
        rows = "".join(f"REQ-{n},MSA {n},yes\n" for n in range(1, 51))
        with self.assertRaisesRegex(
            CsvFormatError,
            r"column 3 is headed 'Uncapped liabilty', which is not a request field "
            r"\(did you mean 'uncapped_liability'\?\)",
        ):
            parse_csv("id,title,Uncapped liabilty\n" + rows)

    def test_unknown_columns_are_noted_and_own_columns_are_not(self):
        table = parse_csv("id,title,Notes,Value band (EUR),x_owner\nREQ-1,MSA,call back,>1m,Ana\n")
        [note] = table.notes
        self.assertIn("'Notes', 'Value band (EUR)'", note)
        self.assertNotIn("x_owner", note)
        self.assertEqual(table.requests[0]["x_owner"], "Ana")

    def test_table_shape_errors(self):
        cases = {
            "": "first row must name the columns",
            "\nid,title\n": "first row must name the columns",
            " , \nREQ-1,MSA\n": "first row must name the columns",
            "id,ID\nREQ-1,REQ-2\n": "columns 1 and 2 both hold 'id'",
            "id,title\nREQ-1,MSA,extra\n": "row 2 has 3 cells but the header names 2 columns",
            "id,,title\nREQ-1,stray,MSA\n": "row 2 has a value in column 2, which has no header",
        }
        for text, message in cases.items():
            with self.subTest(text=text):
                with self.assertRaisesRegex(CsvFormatError, message):
                    parse_csv(text)

    def test_cli_reports_an_unusable_table_and_a_workbook(self):
        with tempfile.TemporaryDirectory() as tmp:
            broken = Path(tmp) / "broken.csv"
            broken.write_text("id,id\nREQ-1,REQ-2\n", encoding="utf-8")
            code, _, stderr = run_cli(["--input", str(broken)])
            self.assertEqual(code, 2)
            self.assertIn("is not a usable request table: columns 1 and 2", stderr)
            with self.assertRaisesRegex(InputError, "save the sheet as CSV"):
                load_requests(str(Path(tmp) / "requests.xlsx"))
            code, _, stderr = run_cli(["--input", str(Path(tmp) / "missing.csv")])
            self.assertEqual(code, 2)
            self.assertIn("cannot read", stderr)


if __name__ == "__main__":
    unittest.main()

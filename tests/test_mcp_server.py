import importlib.util
import json
import unittest
from importlib import resources

from legal_function_os import mcp_server
from legal_function_os.rules import decide


def _data(name):
    return json.loads(resources.files("legal_function_os.data").joinpath(name).read_text(encoding="utf-8"))


class ToolFunctionTests(unittest.TestCase):
    def test_triage_matches_rules(self):
        requests = _data("sample_requests.json")
        out = mcp_server.triage_requests(requests)
        self.assertEqual(out["decisions"], [decide(r).to_dict() for r in requests])

    def test_bad_input_is_rejected_not_decided(self):
        with self.assertRaises(mcp_server.InputRejected):
            mcp_server.triage_requests([{"id": "R1", "type": "nda", "value_band": ">1M"}])
        with self.assertRaises(mcp_server.InputRejected):
            mcp_server.board_pack({"not": "a list"})  # type: ignore[arg-type]

    def test_board_pack(self):
        pack = mcp_server.board_pack(_data("sample_requests.json"), period="Q3")
        self.assertEqual(pack["period"], "Q3")
        self.assertIn("decisions", pack)

    def test_dpa_review(self):
        self.assertIsInstance(mcp_server.dpa_review(_data("dpa_documents.json")), dict)
        with self.assertRaises(mcp_server.InputRejected):
            mcp_server.dpa_review("nope")  # type: ignore[arg-type]

    def test_schema(self):
        self.assertIn("properties", mcp_server.legal_request_schema())


@unittest.skipUnless(importlib.util.find_spec("mcp"), "mcp extra not installed")
class ServerTests(unittest.TestCase):
    def test_tools_registered_read_only(self):
        import asyncio

        tools = asyncio.run(mcp_server.build_server().list_tools())
        names = {t.name for t in tools}
        self.assertEqual(names, {f.__name__ for f in mcp_server.TOOLS})
        self.assertTrue(all(t.annotations.readOnlyHint for t in tools))


if __name__ == "__main__":
    unittest.main()

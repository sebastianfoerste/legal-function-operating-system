import importlib.util
import inspect
import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr
from importlib import resources
from pathlib import Path

from legal_function_os import mcp_server
from legal_function_os.policy import default_policy
from legal_function_os.rules import decide


def _data(name):
    return json.loads(resources.files("legal_function_os.data").joinpath(name).read_text(encoding="utf-8"))


def _custom_policy():
    """The bundled policy with one queue renamed, so its effect is visible in a decision."""

    policy = default_policy().to_dict()
    policy["name"] = "Custom test policy"
    policy["routing"]["by_type"]["commercial_contract"] = "Custom Queue"
    return policy


def _queue(out, request_type="commercial_contract"):
    return next(decision["queue"] for decision in out["decisions"] if decision["type"] == request_type)


class ToolFunctionTests(unittest.TestCase):
    def tearDown(self):
        mcp_server.set_server_policy(None)

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

    def test_no_tool_takes_a_path(self):
        # The model calling the server must not choose what the process reads.
        for tool in mcp_server.TOOLS:
            for name in inspect.signature(tool).parameters:
                self.assertNotIn("path", name.lower(), f"{tool.__name__} takes {name}")
                self.assertNotIn("file", name.lower(), f"{tool.__name__} takes {name}")
        self.assertNotIn("policy_path", Path(mcp_server.__file__).read_text(encoding="utf-8"))

    def test_inline_policy_is_applied(self):
        requests = _data("sample_requests.json")
        self.assertEqual(_queue(mcp_server.triage_requests(requests)), "Commercial")
        self.assertEqual(_queue(mcp_server.triage_requests(requests, policy=_custom_policy())), "Custom Queue")
        pack = mcp_server.board_pack(requests, period="Q3", policy=_custom_policy())
        self.assertEqual(_queue(pack), "Custom Queue")

    def test_invalid_inline_policy_is_rejected(self):
        requests = _data("sample_requests.json")
        with self.assertRaises(mcp_server.InputRejected) as rejected:
            mcp_server.triage_requests(requests, policy={"schema": "not-a-policy", "name": "x"})
        self.assertIn("policy", str(rejected.exception))
        with self.assertRaises(mcp_server.InputRejected):
            mcp_server.board_pack(requests, policy="not an object")  # type: ignore[arg-type]
        broken = _custom_policy()
        broken["sla"] = "later"
        with self.assertRaises(mcp_server.InputRejected):
            mcp_server.triage_requests(requests, policy=broken)

    def test_policy_option_is_honoured(self):
        requests = _data("sample_requests.json")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "policy.json"
            path.write_text(json.dumps(_custom_policy()), encoding="utf-8")
            args = mcp_server.configure(["--policy", str(path)])
            self.assertEqual(args.policy, str(path))
            self.assertEqual(_queue(mcp_server.triage_requests(requests)), "Custom Queue")
            self.assertEqual(_queue(mcp_server.board_pack(requests)), "Custom Queue")
            # An inline policy still takes precedence over the server's policy.
            self.assertEqual(_queue(mcp_server.triage_requests(requests, policy=default_policy().to_dict())), "Commercial")
            mcp_server.set_server_policy(None)
            self.assertEqual(_queue(mcp_server.triage_requests(requests)), "Commercial")

            bad = Path(tmp) / "bad.json"
            bad.write_text("{", encoding="utf-8")
            stderr = io.StringIO()
            with redirect_stderr(stderr), self.assertRaises(SystemExit) as exited:
                mcp_server.configure(["--policy", str(bad)])
            self.assertEqual(exited.exception.code, 2)
            self.assertIn("not valid JSON", stderr.getvalue())
            self.assertIn("The server was not started.", stderr.getvalue())

    def test_without_options_the_bundled_policy_applies(self):
        self.assertIsNone(mcp_server.configure([]).policy)
        self.assertEqual(_queue(mcp_server.triage_requests(_data("sample_requests.json"))), "Commercial")


@unittest.skipUnless(importlib.util.find_spec("mcp"), "mcp extra not installed")
class ServerTests(unittest.TestCase):
    def test_tools_registered_read_only(self):
        import asyncio

        tools = asyncio.run(mcp_server.build_server().list_tools())
        names = {t.name for t in tools}
        self.assertEqual(names, {f.__name__ for f in mcp_server.TOOLS})
        self.assertTrue(all(t.annotations.readOnlyHint for t in tools))

    def test_tool_schemas_take_policy_objects_not_paths(self):
        import asyncio

        tools = {t.name: t for t in asyncio.run(mcp_server.build_server().list_tools())}
        for tool in tools.values():
            for name in tool.inputSchema.get("properties", {}):
                self.assertNotIn("path", name.lower(), f"{tool.name} exposes {name}")
        for name in ("triage_requests", "board_pack"):
            self.assertIn("policy", tools[name].inputSchema["properties"])
        self.assertNotIn("policy", tools["dpa_review"].inputSchema.get("properties", {}))


if __name__ == "__main__":
    unittest.main()

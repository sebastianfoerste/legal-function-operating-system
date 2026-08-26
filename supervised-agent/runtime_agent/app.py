from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import urlparse

from src.mcp_tools import legal_ops_mcp_manifest, run_tool

SERVICE_NAME = "legal_ops_agent_runtime"


class RuntimeHandler(BaseHTTPRequestHandler):
    server_version = "LegalOpsAgentRuntime/1.0"

    def _write_json(self, status_code: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, indent=2).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json_body(self) -> Any:
        content_length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(content_length) if content_length > 0 else b"{}"
        try:
            return json.loads(body.decode("utf-8"))
        except json.JSONDecodeError:
            return None

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path == "/health":
            self._write_json(
                200,
                {
                    "status": "ok",
                    "service_name": SERVICE_NAME,
                    "external_processing": "disabled_by_default",
                },
            )
            return

        if parsed.path == "/mcp/manifest":
            self._write_json(200, legal_ops_mcp_manifest())
            return

        self._write_json(404, {"error": "not_found"})

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        payload = self._read_json_body()
        if not isinstance(payload, dict):
            self._write_json(400, {"error": "invalid_json"})
            return

        if parsed.path == "/tools/call":
            tool_name = payload.get("name")
            arguments = payload.get("arguments", {})
            if not isinstance(tool_name, str) or not isinstance(arguments, dict):
                self._write_json(400, {"error": "invalid_tool_call"})
                return
            try:
                self._write_json(200, run_tool(tool_name, arguments))
            except (KeyError, ValueError) as exc:
                self._write_json(400, {"error": str(exc)})
            return

        self._write_json(404, {"error": "not_found"})


def run() -> None:
    host = os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv("PORT", "18085"))
    server = ThreadingHTTPServer((host, port), RuntimeHandler)
    print(f"legal_ops_agent runtime listening on {host}:{port}")
    server.serve_forever()


if __name__ == "__main__":
    run()

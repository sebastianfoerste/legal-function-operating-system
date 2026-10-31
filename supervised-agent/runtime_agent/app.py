from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse, urlsplit

from src.mcp_tools import legal_ops_mcp_manifest, run_tool
from src.pilot.api import PilotApi, encode
from src.pilot.scenario_runner import seed_actors
from src.pilot.service import PilotService
from src.pilot.store import PilotStore

SERVICE_NAME = "legal_ops_agent_runtime"
DEFAULT_PILOT_DB = Path(".pilot") / "pilot.sqlite3"
# Requests are small JSON commands; anything larger is refused before it is read.
MAX_BODY_BYTES = 1 << 20
# The host names a request may address. The runtime is a local server, so a
# request whose Host header names anything else (a DNS-rebinding page, a stray
# proxy) is refused. ALLOWED_HOSTS, a comma-separated list, replaces the default.
ALLOWED_HOSTS_ENV = "ALLOWED_HOSTS"
DEFAULT_ALLOWED_HOSTS = ("127.0.0.1", "localhost", "::1")
_pilot_api: PilotApi | None = None


def pilot_api() -> PilotApi:
    """The review-room API over the local store named by PILOT_DB."""

    global _pilot_api
    if _pilot_api is None:
        service = PilotService(PilotStore(Path(os.getenv("PILOT_DB", str(DEFAULT_PILOT_DB)))))
        if not service.list_actors():
            seed_actors(service)
        _pilot_api = PilotApi(service)
    return _pilot_api


def allowed_hosts() -> tuple[str, ...]:
    """Host names a request may name: the loopback names, or ALLOWED_HOSTS when set."""

    configured = os.getenv(ALLOWED_HOSTS_ENV, "")
    names = tuple(name.strip().lower() for name in configured.split(",") if name.strip())
    return names or DEFAULT_ALLOWED_HOSTS


class RuntimeHandler(BaseHTTPRequestHandler):
    server_version = "LegalOpsAgentRuntime/1.0"

    def _write_json(self, status_code: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, indent=2).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _refuse(self, status_code: int, error: str) -> None:
        """Answer with an error and close the connection; the body, if any, is not read."""

        self.close_connection = True
        self._write_json(status_code, {"error": error})

    def _host_allowed(self) -> bool:
        """Whether the Host header names this server: an allowed name and, if given, the bound port."""

        header = self.headers.get("Host")
        if not header:
            return False
        try:
            parts = urlsplit(f"//{header.strip()}")
            hostname, port = parts.hostname, parts.port
        except ValueError:
            return False
        if hostname is None or hostname.lower() not in allowed_hosts():
            return False
        address = self.server.server_address  # (host, port, ...) for TCP; a path for Unix sockets
        bound_port = address[1] if isinstance(address, tuple) else None
        return port is None or port == bound_port

    def _content_length(self) -> int | None:
        """The declared body length, or None when the header is not a non-negative integer."""

        raw = self.headers.get("Content-Length", "0").strip()
        if not raw.isdigit():
            return None
        return int(raw)

    def _read_json_body(self, content_length: int) -> Any:
        body = self.rfile.read(content_length) if content_length > 0 else b"{}"
        try:
            return json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return None

    def _pilot(self, method: str, body: dict[str, Any] | None = None) -> None:
        status, payload, content_type = pilot_api().handle(
            method, urlparse(self.path).path, dict(self.headers.items()), body
        )
        data = encode(payload)
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:  # noqa: N802
        if not self._host_allowed():
            self._refuse(403, "host_not_allowed")
            return
        parsed = urlparse(self.path)
        if parsed.path == "/pilot" or parsed.path.startswith("/pilot/"):
            self._pilot("GET")
            return
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
        if not self._host_allowed():
            self._refuse(403, "host_not_allowed")
            return
        media_type = self.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
        if media_type != "application/json":
            self._refuse(415, "unsupported_media_type")
            return
        content_length = self._content_length()
        if content_length is None:
            self._refuse(400, "invalid_content_length")
            return
        if content_length > MAX_BODY_BYTES:
            self._refuse(413, "payload_too_large")
            return
        parsed = urlparse(self.path)
        payload = self._read_json_body(content_length)
        if not isinstance(payload, dict):
            self._write_json(400, {"error": "invalid_json"})
            return

        if parsed.path.startswith("/pilot/"):
            self._pilot("POST", payload)
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

"""The local runtime: loopback only, its own Host and Origin, no framing, JSON-only POSTs.

Every request here goes to a server bound on 127.0.0.1 with a synthetic store. These
checks decide which requests the local server answers. They are not authentication.
"""

from __future__ import annotations

import http.client
import ipaddress
import json
import re
import socket
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

import runtime_agent.app as app
from runtime_agent.app import DEFAULT_ALLOWED_HOSTS, MAX_BODY_BYTES, SERVICE_NAME, allowed_hosts
from src.mcp_tools import legal_ops_mcp_manifest, run_tool
from tests.pilot_support import OWNER, REQUESTER, run_until

AGENT_ROOT = Path(__file__).resolve().parents[1]


def test_runtime_service_name_is_legal_ops_scoped():
    assert SERVICE_NAME == "legal_ops_agent_runtime"


JSON = {"Content-Type": "application/json"}
LOOPBACK = object()  # sentinel: "send this server's own loopback Host header"


@pytest.fixture
def server(tmp_path, monkeypatch):
    monkeypatch.setenv("PILOT_DB", str(tmp_path / "pilot.sqlite3"))
    monkeypatch.setenv("PILOT_EXPORT_ROOT", str(tmp_path / "exports"))
    monkeypatch.delenv(app.ALLOWED_HOSTS_ENV, raising=False)
    monkeypatch.setattr(app, "_pilot_api", None)
    try:
        httpd = ThreadingHTTPServer(("127.0.0.1", 0), app.RuntimeHandler)
    except PermissionError:
        pytest.skip("this environment does not permit binding a local port")
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield httpd
    httpd.shutdown()
    httpd.server_close()


def _raw(httpd, method, path, *, host=LOOPBACK, headers=None, body=None, declared_length=None):
    """One raw request over 127.0.0.1 with full control of the Host and length headers.

    ``host`` defaults to this server's loopback name and port; ``None`` sends no Host header.
    Returns the status, the response headers (names lowercased) and the body bytes.
    """

    port = httpd.server_address[1]
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    connection.putrequest(method, path, skip_host=True, skip_accept_encoding=True)
    if host is LOOPBACK:
        host = f"127.0.0.1:{port}"
    if host is not None:
        connection.putheader("Host", host)
    for name, value in (headers or {}).items():
        connection.putheader(name, value)
    if declared_length is not None:
        connection.putheader("Content-Length", declared_length)
    elif body is not None:
        connection.putheader("Content-Length", str(len(body)))
    connection.endheaders()
    if body is not None and declared_length is None:
        connection.send(body)
    try:
        response = connection.getresponse()
        data = response.read()
        return response.status, {k.lower(): v for k, v in response.getheaders()}, data
    finally:
        connection.close()


def _request(httpd, method, path, **kwargs):
    """Like ``_raw``, with the body decoded as JSON."""

    status, _, data = _raw(httpd, method, path, **kwargs)
    return status, (json.loads(data) if data else None)


def test_loopback_hosts_are_served(server):
    port = server.server_address[1]
    for host in (
        f"127.0.0.1:{port}",
        f"localhost:{port}",
        f"[::1]:{port}",
        "localhost",
        "LOCALHOST",
    ):
        status, payload = _request(server, "GET", "/health", host=host)
        assert (status, payload["status"]) == (200, "ok"), host
        assert payload["external_processing"] == "none", host


def test_foreign_or_missing_host_is_refused(server):
    port = server.server_address[1]
    for host in (
        "evil.example",
        f"evil.example:{port}",
        f"127.0.0.1:{port + 1}",
        "127.0.0.1:notaport",
        "[::1",
    ):
        status, payload = _request(server, "GET", "/health", host=host)
        assert (status, payload) == (403, {"error": "host_not_allowed"}), host
    status, payload = _request(server, "GET", "/health", host=None)
    assert (status, payload) == (403, {"error": "host_not_allowed"})
    status, payload = _request(
        server,
        "POST",
        "/tools/call",
        host=f"evil.example:{port}",
        headers=JSON,
        body=b'{"name": "x"}',
    )
    assert (status, payload) == (403, {"error": "host_not_allowed"})


def test_allowed_hosts_can_be_configured(server, monkeypatch):
    port = server.server_address[1]
    assert allowed_hosts() == DEFAULT_ALLOWED_HOSTS
    monkeypatch.setenv(app.ALLOWED_HOSTS_ENV, "runtime.internal, Review.Example")
    assert allowed_hosts() == ("runtime.internal", "review.example")
    for host in (f"runtime.internal:{port}", f"review.example:{port}"):
        status, _ = _request(server, "GET", "/health", host=host)
        assert status == 200, host
    # The list replaces the default; it does not extend it.
    status, _ = _request(server, "GET", "/health", host=f"127.0.0.1:{port}")
    assert status == 403


def test_post_needs_a_json_content_type(server):
    body = b'{"name": 7}'
    status, payload = _request(
        server, "POST", "/tools/call", headers={"Content-Type": "text/plain"}, body=body
    )
    assert (status, payload) == (415, {"error": "unsupported_media_type"})
    status, payload = _request(server, "POST", "/tools/call", body=body)
    assert (status, payload) == (415, {"error": "unsupported_media_type"})
    for content_type in ("application/json", "application/json; charset=utf-8", "Application/JSON"):
        status, payload = _request(
            server, "POST", "/tools/call", headers={"Content-Type": content_type}, body=body
        )
        assert (status, payload) == (400, {"error": "invalid_tool_call"}), content_type


def test_oversized_body_is_refused_before_it_is_read(server):
    status, payload = _request(
        server, "POST", "/tools/call", headers=JSON, declared_length=str(MAX_BODY_BYTES + 1)
    )
    assert (status, payload) == (413, {"error": "payload_too_large"})
    within = json.dumps({"name": "x", "arguments": {"pad": "y" * 2048}}).encode()
    assert len(within) <= MAX_BODY_BYTES
    status, _ = _request(server, "POST", "/tools/call", headers=JSON, body=within)
    assert status == 400  # read in full; refused by the tool registry, not by size


def test_non_integer_content_length_is_a_bad_request(server):
    for declared in ("twelve", "-1", "1e3", "12 13", ""):
        status, payload = _request(
            server, "POST", "/tools/call", headers=JSON, declared_length=declared
        )
        assert (status, payload) == (400, {"error": "invalid_content_length"}), declared


def test_pilot_and_tool_posts_still_work_over_loopback(server):
    status, payload = _request(server, "GET", "/pilot/api/actors")
    assert status == 200 and len(payload["actors"]) == 6
    status, payload = _request(
        server, "POST", "/tools/call", headers=JSON, body=b'{"name": "nope"}'
    )
    assert status == 400 and "error" in payload
    status, payload = _request(server, "POST", "/tools/call", headers=JSON, body=b"not json")
    assert (status, payload) == (400, {"error": "invalid_json"})


def test_the_tool_endpoints_answer_as_the_readme_says(server):
    # README, "MCP surface": the tools are reached over this server, at GET /mcp/manifest
    # and POST /tools/call. The README's own example call is sent here as it is written.
    readme = (AGENT_ROOT / "README.md").read_text(encoding="utf-8")
    surface = readme.split("\n## MCP surface\n", 1)[1].split("\n## ", 1)[0]
    routes = re.findall(r"http://127\.0\.0\.1:18085(/[a-z/]+)", surface)
    assert sorted(set(routes)) == ["/mcp/manifest", "/tools/call"]
    [example] = re.findall(r"-d '(\{.+?\})' \\\n", surface)
    call = json.loads(example)
    assert call == {"name": "legal.sources.list", "arguments": {}}

    status, headers, data = _raw(server, "GET", "/mcp/manifest")
    assert status == 200 and headers["content-type"] == "application/json; charset=utf-8"
    manifest = json.loads(data)
    assert manifest == legal_ops_mcp_manifest()
    assert call["name"] in [tool["name"] for tool in manifest["tools"]]

    status, payload = _request(server, "POST", "/tools/call", headers=JSON, body=example.encode())
    assert (status, payload) == (200, run_tool(call["name"], call["arguments"]))
    assert payload["external_processing"] == "none"

    # Each endpoint answers one method only.
    status, payload = _request(server, "POST", "/mcp/manifest", headers=JSON, body=b"{}")
    assert (status, payload) == (404, {"error": "not_found"})
    status, payload = _request(server, "GET", "/tools/call")
    assert (status, payload) == (404, {"error": "not_found"})


def test_run_listens_where_the_readme_says_unless_host_or_port_say_otherwise(monkeypatch, capsys):
    readme = (AGENT_ROOT / "README.md").read_text(encoding="utf-8")
    surface = " ".join(readme.split("\n## MCP surface\n", 1)[1].split("\n## ", 1)[0].split())
    assert "It listens on `127.0.0.1:18085` unless `HOST` or `PORT` say otherwise" in surface

    class Listening:
        def serve_forever(self):
            return None

    asked = []
    monkeypatch.setattr(
        app, "build_server", lambda host, port: asked.append((host, port)) or Listening()
    )
    monkeypatch.delenv("HOST", raising=False)
    monkeypatch.delenv("PORT", raising=False)
    app.run()
    monkeypatch.setenv("HOST", "localhost")
    monkeypatch.setenv("PORT", "18090")
    app.run()
    assert asked == [("127.0.0.1", 18085), ("localhost", 18090)]
    assert "listening on 127.0.0.1:18085" in capsys.readouterr().out


# -- listening address -------------------------------------------------------------


def _no_listen(*args, **kwargs):
    raise AssertionError(f"tried to listen on {args[0]!r}")


@pytest.mark.parametrize("host", ["0.0.0.0", "0", "192.0.2.10", ""])
def test_server_refuses_a_non_loopback_address(host, monkeypatch):
    monkeypatch.setattr(app, "ThreadingHTTPServer", _no_listen)  # refused before any bind
    with pytest.raises(SystemExit, match="loopback|cannot listen"):
        app.build_server(host, 0)


def test_server_checks_the_address_it_bound(monkeypatch):
    # A name that resolved to loopback but was bound elsewhere is closed before it listens.
    loopback = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 0))]
    monkeypatch.setattr(app.socket, "getaddrinfo", lambda *args, **kwargs: loopback)

    def bind_elsewhere(self):
        self.server_address = ("0.0.0.0", 0)  # nothing is bound; only the address is faked

    def activate(self):
        raise AssertionError("listened on an address that is not loopback")

    closed = []
    close = ThreadingHTTPServer.server_close
    monkeypatch.setattr(ThreadingHTTPServer, "server_bind", bind_elsewhere)
    monkeypatch.setattr(ThreadingHTTPServer, "server_activate", activate)
    monkeypatch.setattr(
        ThreadingHTTPServer, "server_close", lambda self: (closed.append(True), close(self))
    )
    with pytest.raises(SystemExit, match="loopback"):
        app.build_server("rebound.example", 0)
    assert closed == [True]


def test_server_listens_on_loopback(monkeypatch):
    monkeypatch.delenv(app.ALLOWED_HOSTS_ENV, raising=False)
    for host in ("127.0.0.1", "localhost"):
        try:
            httpd = app.build_server(host, 0)
        except PermissionError:
            pytest.skip("this environment does not permit binding a local port")
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        try:
            assert ipaddress.ip_address(httpd.server_address[0]).is_loopback, host
            status, payload = _request(httpd, "GET", "/health")
            assert (status, payload["status"]) == (200, "ok"), host
        finally:
            httpd.shutdown()
            httpd.server_close()


def test_run_refuses_a_host_from_the_environment(monkeypatch):
    monkeypatch.setattr(app, "ThreadingHTTPServer", _no_listen)
    monkeypatch.setenv("HOST", "0.0.0.0")
    monkeypatch.setenv("PORT", "0")
    with pytest.raises(SystemExit, match="loopback"):
        app.run()


# -- origin ------------------------------------------------------------------------


def _open(server, matter_id, *, host=LOOPBACK, origin=None):
    headers = {**JSON, "X-Pilot-Actor": REQUESTER}
    if origin is not None:
        headers["Origin"] = origin
    body = json.dumps({"scenario_id": "routine", "matter_id": matter_id}).encode()
    return _request(server, "POST", "/pilot/api/matters", host=host, headers=headers, body=body)


def test_foreign_origin_is_refused(server):
    port = server.server_address[1]
    for origin in (
        "http://evil.example",
        f"http://127.0.0.1:{port + 1}",
        f"http://localhost:{port}",  # the Host header says 127.0.0.1
        "null",
        f"http://127.0.0.1:{port}/x",
        f"https://127.0.0.1:{port}",
        f"http://user@127.0.0.1:{port}",
        "not a url",
        "",
    ):
        status, payload = _open(server, "PM-ORIGIN-1", origin=origin)
        assert (status, payload) == (403, {"error": "origin_not_allowed"}), origin
    status, payload = _request(
        server,
        "GET",
        "/pilot/api/matters",
        headers={"X-Pilot-Actor": REQUESTER, "Origin": "http://evil.example"},
    )
    assert (status, payload) == (403, {"error": "origin_not_allowed"})
    status, payload = _request(
        server, "GET", "/pilot/api/matters", headers={"X-Pilot-Actor": REQUESTER}
    )
    assert status == 200 and payload["matters"] == []


def test_own_origin_or_none_is_served(server):
    port = server.server_address[1]
    assert _open(server, "PM-ORIGIN-2", origin=f"http://127.0.0.1:{port}")[0] == 201
    assert _open(server, "PM-ORIGIN-3")[0] == 201  # curl, scripts and tests send no Origin
    host = f"localhost:{port}"
    assert _open(server, "PM-ORIGIN-4", host=host, origin=f"http://{host}")[0] == 201


# -- response headers --------------------------------------------------------------


def test_every_response_refuses_framing_and_allows_no_cross_origin_reads(server):
    port = server.server_address[1]
    preflight = {
        "Origin": "http://evil.example",
        "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "content-type,x-pilot-actor",
    }
    responses = {
        "room": _raw(server, "GET", "/pilot"),
        "actors": _raw(server, "GET", "/pilot/api/actors"),
        "health": _raw(server, "GET", "/health"),
        "missing": _raw(server, "GET", "/nope"),
        "foreign host": _raw(server, "GET", "/health", host=f"evil.example:{port}"),
        "bad tool": _raw(server, "POST", "/tools/call", headers=JSON, body=b'{"name": 7}'),
        "preflight": _raw(server, "OPTIONS", "/pilot/api/matters", headers=preflight),
    }
    assert [status for status, _, _ in responses.values()] == [200, 200, 200, 404, 403, 400, 501]
    for name, (_, headers, _) in responses.items():
        assert headers["x-frame-options"] == "DENY", name
        assert "frame-ancestors 'none'" in headers["content-security-policy"], name
        assert headers["x-content-type-options"] == "nosniff", name
        assert headers["referrer-policy"] == "no-referrer", name
        assert headers["cross-origin-resource-policy"] == "same-origin", name
        assert not [h for h in headers if h.startswith("access-control-")], name


# -- access log --------------------------------------------------------------------


def test_presence_check_ins_are_not_logged(server, capsys):
    matter = run_until(app.pilot_api().service, "routine", "A06")
    owner = {"X-Pilot-Actor": OWNER}
    status, view = _request(server, "GET", f"/pilot/api/matters/{matter}", headers=owner)
    assert status == 200
    body = json.dumps({"revision": view["matter"]["revision"]}).encode()
    for path in (f"/pilot/api/matters/{matter}/presence", f"/pilot/api/matters/{matter}/presence/"):
        status, _ = _request(server, "POST", path, headers={**JSON, **owner}, body=body)
        assert status == 200, path
    refused = {**JSON, "X-Pilot-Actor": REQUESTER}  # a requester's check-in is refused
    path = f"/pilot/api/matters/{matter}/presence"
    assert _request(server, "POST", path, headers=refused, body=body)[0] == 403
    # The matter's other routes are logged, a command included.
    base = f"/pilot/api/matters/{matter}"
    history, commands = f"{base}/history", f"{base}/commands"
    assert _request(server, "GET", history, headers=owner)[0] == 200
    assert _request(server, "POST", commands, headers={**JSON, **owner}, body=b"{}")[0] == 400

    logged = capsys.readouterr().err
    assert "presence" not in logged
    assert f'"GET /pilot/api/matters/{matter} HTTP/1.1" 200' in logged
    assert f'"GET {history} HTTP/1.1" 200' in logged
    assert f'"POST {commands} HTTP/1.1" 400' in logged


def test_requests_to_a_presence_path_that_are_not_check_ins_are_logged(server, capsys):
    # Only a check-in the review-room API received is left out. A request refused before
    # routing (another Host or Origin, another media type) or a GET records no presence.
    port = server.server_address[1]
    path = "/pilot/api/matters/PM-LOG-1/presence"
    owner = {**JSON, "X-Pilot-Actor": OWNER}
    body = b'{"revision": 1}'
    foreign_host = _request(
        server, "POST", path, host=f"evil.example:{port}", headers=owner, body=body
    )
    assert foreign_host == (403, {"error": "host_not_allowed"})
    foreign_origin = {**owner, "Origin": "http://evil.example"}
    assert _request(server, "POST", path, headers=foreign_origin, body=body)[0] == 403
    text = {**owner, "Content-Type": "text/plain"}
    assert _request(server, "POST", path, headers=text, body=body)[0] == 415
    assert _request(server, "GET", path, headers={"X-Pilot-Actor": OWNER})[0] == 404

    logged = capsys.readouterr().err
    assert logged.count(f'"POST {path} HTTP/1.1" 403') == 2
    assert logged.count(f'"POST {path} HTTP/1.1" 415') == 1
    assert logged.count(f'"GET {path} HTTP/1.1" 404') == 1

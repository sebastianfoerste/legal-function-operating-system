"""The local runtime: loopback-only Host names, JSON-only POSTs and a bounded body.

Every request here goes to a server bound on 127.0.0.1 with a synthetic store.
"""

from __future__ import annotations

import http.client
import json
import threading
from http.server import ThreadingHTTPServer

import pytest

import runtime_agent.app as app
from runtime_agent.app import DEFAULT_ALLOWED_HOSTS, MAX_BODY_BYTES, SERVICE_NAME, allowed_hosts


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


def _request(httpd, method, path, *, host=LOOPBACK, headers=None, body=None, declared_length=None):
    """One raw request over 127.0.0.1 with full control of the Host and length headers.

    ``host`` defaults to this server's loopback name and port; ``None`` sends no Host header.
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
        return response.status, (json.loads(data) if data else None)
    finally:
        connection.close()


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

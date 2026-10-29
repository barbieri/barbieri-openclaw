"""Real TLS transport for one-click unsubscribe (no http.client mocks)."""

import ssl
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import one_click_unsubscribe as unsubscribe_http
import pytest
from one_click_unsubscribe import post_one_click

_HOST = "unsubscribe.integration.invalid"


class _IntegrationHandler(BaseHTTPRequestHandler):
    redirect_sent = False
    posts: list[tuple[str, bytes]] = []

    def log_message(self, _format, *_args) -> None:
        return

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length)
        _IntegrationHandler.posts.append((self.path, body))
        if self.path == "/one-click" and not _IntegrationHandler.redirect_sent:
            _IntegrationHandler.redirect_sent = True
            self.send_response(302)
            location = f"https://{_HOST}:{self.server.server_port}/final"
            self.send_header("Location", location)
            self.end_headers()
            return
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"ok")


@pytest.fixture
def tls_one_click_server(tmp_path):
    cert = tmp_path / "cert.pem"
    key = tmp_path / "key.pem"
    subprocess.run(
        [
            "openssl",
            "req",
            "-x509",
            "-newkey",
            "rsa:2048",
            "-keyout",
            str(key),
            "-out",
            str(cert),
            "-days",
            "1",
            "-nodes",
            "-subj",
            f"/CN={_HOST}",
        ],
        check=True,
        capture_output=True,
    )
    _IntegrationHandler.redirect_sent = False
    _IntegrationHandler.posts.clear()
    httpd = HTTPServer(("127.0.0.1", 0), _IntegrationHandler)
    port = httpd.server_address[1]
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(certfile=str(cert), keyfile=str(key))
    httpd.socket = context.wrap_socket(httpd.socket, server_side=True)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield port, cert
    finally:
        httpd.shutdown()
        thread.join(timeout=5)


@pytest.fixture
def pinned_loopback_transport(tls_one_click_server, monkeypatch):
    port, cert = tls_one_click_server
    trust = ssl.create_default_context()
    trust.load_verify_locations(cafile=str(cert))

    def resolve_test_host(host: str) -> str:
        if host == _HOST:
            return "127.0.0.1"
        raise unsubscribe_http.UnsubscribeTransportError()

    monkeypatch.setattr(unsubscribe_http, "_resolve_connect_ip", resolve_test_host)
    monkeypatch.setattr(unsubscribe_http.ssl, "create_default_context", lambda: trust)
    monkeypatch.setattr(unsubscribe_http, "_port_allowed", lambda candidate: candidate == port)
    yield port


def test_post_one_click_live_tls_with_redirect_hop(pinned_loopback_transport):
    port = pinned_loopback_transport
    post_one_click(f"https://{_HOST}:{port}/one-click")
    paths = [path for path, _body in _IntegrationHandler.posts]
    assert paths == ["/one-click", "/final"]
    assert all(body == b"List-Unsubscribe=One-Click" for _path, body in _IntegrationHandler.posts)

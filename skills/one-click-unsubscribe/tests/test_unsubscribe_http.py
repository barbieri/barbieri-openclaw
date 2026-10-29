import socket
from unittest.mock import patch

import pytest
from one_click_unsubscribe import (
    UnsubscribeTransportError,
    post_one_click,
    validate_endpoint_host,
)


def test_private_ip_literal_is_rejected():
    with pytest.raises(UnsubscribeTransportError):
        validate_endpoint_host("127.0.0.1")
    with pytest.raises(UnsubscribeTransportError):
        validate_endpoint_host("10.0.0.5")


def test_hostname_resolving_to_loopback_is_rejected():
    def fake_getaddrinfo(host, *_args, **_kwargs):
        if host == "evil.example.invalid":
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 0))]
        raise OSError("unknown host")

    with (
        patch("one_click_unsubscribe.socket.getaddrinfo", fake_getaddrinfo),
        pytest.raises(UnsubscribeTransportError),
    ):
        validate_endpoint_host("evil.example.invalid")


def test_redirect_to_internal_target_is_rejected(monkeypatch):
    calls = []

    class FakeResponse:
        def __init__(self, status, headers=None):
            self.status = status
            self.headers = headers or {}

        def getheader(self, name, default=None):
            return self.headers.get(name, default)

    def fake_post_once(hostname, connect_ip, port, path):
        calls.append((hostname, connect_ip, path))
        if len(calls) == 1:
            return FakeResponse(302, {"Location": "https://127.0.0.1/one-click"})
        return FakeResponse(200)

    def fake_getaddrinfo(host, *_args, **_kwargs):
        if host == "unsubscribe.example.invalid":
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))]
        raise OSError("unknown host")

    monkeypatch.setattr(
        "one_click_unsubscribe._post_once",
        fake_post_once,
    )
    monkeypatch.setattr(
        "one_click_unsubscribe.socket.getaddrinfo",
        fake_getaddrinfo,
    )
    with pytest.raises(UnsubscribeTransportError):
        post_one_click("https://unsubscribe.example.invalid/one-click")


def test_too_many_redirects(monkeypatch):
    class FakeResponse:
        status = 302

        def getheader(self, _name, default=None):
            return "https://unsubscribe.example.invalid/next"

    def fake_getaddrinfo(host, *_args, **_kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))]

    monkeypatch.setattr(
        "one_click_unsubscribe._post_once",
        lambda *_args, **_kwargs: FakeResponse(),
    )
    monkeypatch.setattr(
        "one_click_unsubscribe.socket.getaddrinfo",
        fake_getaddrinfo,
    )
    with pytest.raises(UnsubscribeTransportError, match="too many redirects"):
        post_one_click("https://unsubscribe.example.invalid/one-click")


@pytest.mark.parametrize(
    "location",
    [
        "https://public.example.invalid:99999/",
        "https://public.example.invalid:abc/",
        "https://[invalid/",
    ],
)
def test_malformed_redirect_is_a_transport_failure(monkeypatch, location):
    class Response:
        status = 302

        def getheader(self, _name):
            return location

    monkeypatch.setattr(
        "one_click_unsubscribe.socket.getaddrinfo",
        lambda *_args, **_kwargs: [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))
        ],
    )
    monkeypatch.setattr(
        "one_click_unsubscribe._post_once",
        lambda *_args: Response(),
    )
    with pytest.raises(UnsubscribeTransportError):
        post_one_click("https://unsubscribe.example.invalid/one-click")

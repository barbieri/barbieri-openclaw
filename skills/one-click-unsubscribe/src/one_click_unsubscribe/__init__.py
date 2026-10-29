"""SSRF-safe HTTPS POST for RFC 8058 one-click unsubscribe."""

import http.client
import ipaddress
import json
import socket
import ssl
import sys
import urllib.error
from argparse import ArgumentParser
from collections.abc import Sequence
from pathlib import Path
from urllib.parse import urljoin, urlsplit

_UNSUBSCRIBE_TIMEOUT = 15
_MAX_REDIRECTS = 5
_BODY = b"List-Unsubscribe=One-Click"
_HEADERS = {"List-Unsubscribe": "One-Click", "Content-Type": "application/x-www-form-urlencoded"}
_MAX_URL_FILE_BYTES = 16 * 1024


class _ArgumentError(Exception):
    pass


class _ArgumentParser(ArgumentParser):
    def error(self, _message: str) -> None:
        raise _ArgumentError


class UnsubscribeTransportError(OSError):
    """Unsubscribe endpoint failed validation or transport."""


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    """Connect to a validated IP while preserving TLS SNI for the original hostname."""

    def __init__(
        self,
        server_hostname: str,
        connect_ip: str,
        port: int,
        *,
        timeout: float,
        context: ssl.SSLContext,
    ) -> None:
        self._connect_ip = connect_ip
        self._server_hostname = server_hostname
        super().__init__(connect_ip, port, timeout=timeout, context=context)

    def connect(self) -> None:
        sock = socket.create_connection(
            (self._connect_ip, self.port),
            self.timeout,
            self.source_address,
        )
        if self._tunnel_host:
            self._tunnel()
        self.sock = self._context.wrap_socket(sock, server_hostname=self._server_hostname)


def _normalize_ip(address: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address:
    ip = ipaddress.ip_address(address)
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        return ip.ipv4_mapped
    return ip


def _blocked_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast:
        return True
    if ip.is_reserved or ip.is_unspecified:
        return True
    return bool(
        isinstance(ip, ipaddress.IPv4Address) and ip in ipaddress.ip_network("100.64.0.0/10")
    )


def _resolve_connect_ip(hostname: str) -> str:
    if not hostname or hostname.lower() == "localhost":
        raise UnsubscribeTransportError("blocked hostname")
    try:
        literal = _normalize_ip(hostname)
        if _blocked_ip(literal):
            raise UnsubscribeTransportError("blocked address")
        return str(literal)
    except ValueError:
        pass
    validated: list[str] = []
    try:
        for _family, _, _, _, sockaddr in socket.getaddrinfo(
            hostname, None, type=socket.SOCK_STREAM
        ):
            ip = _normalize_ip(sockaddr[0])
            if _blocked_ip(ip):
                raise UnsubscribeTransportError("blocked resolved address")
            validated.append(sockaddr[0])
    except OSError as error:
        raise UnsubscribeTransportError("DNS resolution failed") from error
    if not validated:
        raise UnsubscribeTransportError("DNS resolution failed")
    return validated[0]


def _port_allowed(port: int | None) -> bool:
    return port in {None, 443}


def _validate_https_url(url: str) -> tuple[str, str, int, str]:
    try:
        parsed = urlsplit(url)
        port = parsed.port
    except ValueError as error:
        raise UnsubscribeTransportError("invalid unsubscribe URL") from error
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.fragment
        or not _port_allowed(port)
        or any(c.isspace() or ord(c) < 32 for c in url)
        or "." not in parsed.hostname
    ):
        raise UnsubscribeTransportError("invalid unsubscribe URL")
    connect_ip = _resolve_connect_ip(parsed.hostname)
    port = port or 443
    path = parsed.path or "/"
    if parsed.query:
        path = f"{path}?{parsed.query}"
    return parsed.hostname, connect_ip, port, path


def _read_response(connection: http.client.HTTPConnection) -> http.client.HTTPResponse:
    return connection.getresponse()


def _post_once(hostname: str, connect_ip: str, port: int, path: str) -> http.client.HTTPResponse:
    context = ssl.create_default_context()
    connection = _PinnedHTTPSConnection(
        hostname,
        connect_ip,
        port,
        timeout=_UNSUBSCRIBE_TIMEOUT,
        context=context,
    )
    try:
        connection.request("POST", path, body=_BODY, headers={**_HEADERS, "Host": hostname})
        return _read_response(connection)
    finally:
        connection.close()


def validate_endpoint_host(hostname: str) -> None:
    _resolve_connect_ip(hostname)


def post_one_click(url: str) -> None:
    """POST one-click unsubscribe with DNS pinning and manual redirect handling."""
    current = url
    for _ in range(_MAX_REDIRECTS + 1):
        hostname, connect_ip, port, path = _validate_https_url(current)
        response = _post_once(hostname, connect_ip, port, path)
        if 300 <= response.status < 400:
            location = response.getheader("Location")
            if not location or not isinstance(location, str):
                raise UnsubscribeTransportError("redirect without location")
            try:
                current = urljoin(current, location.strip())
            except ValueError as error:
                raise UnsubscribeTransportError("invalid redirect URL") from error
            continue
        if response.status >= 400:
            raise urllib.error.HTTPError(
                current, response.status, "unsubscribe failed", response.headers, None
            )
        return
    raise UnsubscribeTransportError("too many redirects")


def main(argv: Sequence[str] | None = None) -> int:
    """Validate or POST one RFC 8058 endpoint without exposing its URL."""

    def report(status: str, *, error: str | None = None) -> int:
        result = {"status": status}
        if error is not None:
            result["error"] = error
        print(json.dumps(result, sort_keys=True))
        return 1 if status == "failed" else 0

    parser = _ArgumentParser(description="Validate or execute an RFC 8058 one-click unsubscribe.")
    parser.add_argument(
        "--url-file",
        default="-",
        help="Read one URL from this file, or stdin when omitted",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="POST the one-click request; without this flag, only validate",
    )
    try:
        args = parser.parse_args(argv)
    except _ArgumentError:
        return report("failed", error="Invalid command-line arguments")
    except SystemExit as error:
        return int(error.code)

    try:
        if args.url_file == "-":
            source = sys.stdin.buffer
            content = source.read(_MAX_URL_FILE_BYTES + 1)
        else:
            with Path(args.url_file).open("rb") as source:
                content = source.read(_MAX_URL_FILE_BYTES + 1)
        if len(content) > _MAX_URL_FILE_BYTES:
            return report("failed", error="URL input exceeds 16 KiB")
        url = content.decode("utf-8").strip()
        if not url or "\n" in url or "\r" in url:
            return report("failed", error="Input must contain exactly one URL")
        if args.execute:
            post_one_click(url)
            return report("unsubscribed")
        _validate_https_url(url)
        return report("dry_run")
    except Exception:
        return report("failed", error="URL validation or unsubscribe request failed")


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import socket
from urllib.parse import urlsplit


def validate_proxy_url(value: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError("proxy URL must be a non-empty HTTP URL")
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError as exc:
        raise ValueError("invalid proxy URL") from exc
    if (parsed.scheme.lower() != "http" or not parsed.hostname or port is None
            or not 1 <= port <= 65535 or parsed.username is not None
            or parsed.password is not None or parsed.path or parsed.query or parsed.fragment
            or any(char.isspace() for char in value)):
        raise ValueError("proxy URL must be http://host:port without credentials or a path")
    try:
        value.encode("ascii")
    except UnicodeEncodeError as exc:
        raise ValueError("proxy URL must use an ASCII hostname") from exc
    return value


def proxy_environment(proxy_url: str) -> dict[str, str]:
    url = validate_proxy_url(proxy_url)
    return {"http_proxy": url, "https_proxy": url, "HTTP_PROXY": url, "HTTPS_PROXY": url,
            "no_proxy": "localhost,127.0.0.1,::1", "NO_PROXY": "localhost,127.0.0.1,::1"}


def check_proxy_connection(proxy_url: str, timeout: float = 3.0) -> bool:
    parsed = urlsplit(validate_proxy_url(proxy_url))
    try:
        with socket.create_connection((parsed.hostname, parsed.port), timeout=timeout):
            return True
    except OSError:
        return False

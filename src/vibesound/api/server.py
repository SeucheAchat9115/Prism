"""Development-server helper with safe loopback defaults."""

from __future__ import annotations

import ipaddress
import socket
from collections.abc import Callable
from pathlib import Path

import uvicorn

from vibesound.api.app import create_app
from vibesound.application import ApplicationService


def run_server(
    project_path: Path | str,
    *,
    host: str = "127.0.0.1",
    port: int = 8765,
    started: Callable[[str, int], None] | None = None,
) -> None:
    """Serve one project locally and close its backend when the server exits."""

    if not _is_loopback_host(host):
        raise ValueError("The Phase 5.5 service may bind only to a loopback address")
    service = ApplicationService(project_path)
    listener: socket.socket | None = None
    try:
        family = socket.AF_INET6 if _ip_version(host) == 6 else socket.AF_INET
        listener = socket.create_server((host, port), family=family)
        actual_port = int(listener.getsockname()[1])
        server = uvicorn.Server(uvicorn.Config(create_app(service), host=host, port=actual_port))
        if started is not None:
            started(host, actual_port)
        server.run(sockets=[listener])
    finally:
        if listener is not None:
            listener.close()
        service.close()


def _is_loopback_host(host: str) -> bool:
    if host.casefold() == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _ip_version(host: str) -> int:
    if host.casefold() == "localhost":
        return 4
    return ipaddress.ip_address(host).version

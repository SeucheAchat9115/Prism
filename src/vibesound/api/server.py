"""Development-server helper with safe loopback defaults."""

from __future__ import annotations

import ipaddress
from pathlib import Path

import uvicorn

from vibesound.api.app import create_app
from vibesound.application import ApplicationService


def run_server(
    project_path: Path | str,
    *,
    host: str = "127.0.0.1",
    port: int = 8765,
) -> None:
    """Serve one project locally and close its backend when the server exits."""

    if not _is_loopback_host(host):
        raise ValueError("The Phase 5.5 service may bind only to a loopback address")
    service = ApplicationService(project_path)
    try:
        uvicorn.run(create_app(service), host=host, port=port)
    finally:
        service.close()


def _is_loopback_host(host: str) -> bool:
    if host.casefold() == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False

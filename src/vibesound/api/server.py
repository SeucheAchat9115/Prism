"""Development-server helper with safe loopback defaults."""

from __future__ import annotations

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

    service = ApplicationService(project_path)
    try:
        uvicorn.run(create_app(service), host=host, port=port)
    finally:
        service.close()

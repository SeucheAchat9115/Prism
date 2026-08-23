from __future__ import annotations

from pathlib import Path

import pytest

from vibesound.api import server


def test_server_rejects_non_loopback_and_closes_service(monkeypatch, tmp_path: Path) -> None:
    closed = False
    served: dict[str, object] = {}

    class StubService:
        def __init__(self, path) -> None:
            served["path"] = path

        def close(self) -> None:
            nonlocal closed
            closed = True

    monkeypatch.setattr(server, "ApplicationService", StubService)
    monkeypatch.setattr(server, "create_app", lambda service: service)
    monkeypatch.setattr(
        server.uvicorn,
        "run",
        lambda app, host, port: served.update(app=app, host=host, port=port),
    )

    with pytest.raises(ValueError, match="loopback"):
        server.run_server(tmp_path / "demo.vibesound", host="0.0.0.0")
    server.run_server(tmp_path / "demo.vibesound", host="localhost", port=9000)

    assert served["host"] == "localhost"
    assert served["port"] == 9000
    assert closed
    assert server._is_loopback_host("127.0.0.1")
    assert server._is_loopback_host("::1")
    assert not server._is_loopback_host("not-an-address")

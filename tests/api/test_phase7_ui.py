from __future__ import annotations

import importlib.resources
from pathlib import Path

from application._helpers import make_archive_fixture
from fastapi.testclient import TestClient

from vibesound.api import create_app
from vibesound.application import ApplicationService
from vibesound.audio import FakeAudioBackend


def test_packaged_browser_session_has_security_headers_and_capability(tmp_path: Path) -> None:
    project_path, *_ = make_archive_fixture(tmp_path)
    service = ApplicationService(project_path, backend_factory=FakeAudioBackend)
    try:
        client = TestClient(create_app(service))
        page = client.get("/")
        script = client.get("/assets/app.js")
        styles = client.get("/assets/styles.css")
        capabilities = client.get("/api/v1/capabilities")

        assert page.status_code == 200
        assert page.headers["content-type"].startswith("text/html")
        assert 'src="/assets/app.js"' in page.text
        assert "VibeSound Session" in page.text
        assert script.status_code == 200
        assert script.headers["content-type"].startswith(
            ("text/javascript", "application/javascript")
        )
        assert styles.status_code == 200
        assert styles.headers["content-type"].startswith("text/css")
        for response in (page, script, styles):
            assert response.headers["cache-control"] == "no-store"
            assert response.headers["x-content-type-options"] == "nosniff"
            assert response.headers["referrer-policy"] == "no-referrer"
            policy = response.headers["content-security-policy"]
            assert "default-src 'self'" in policy
            assert "frame-ancestors 'none'" in policy
            assert "object-src 'none'" in policy
        assert capabilities.json()["ui"] == {"browser_session": True, "path": "/"}
    finally:
        service.close()


def test_browser_assets_are_package_resources() -> None:
    root = importlib.resources.files("vibesound.web")

    assert root.joinpath("index.html").is_file()
    assert root.joinpath("assets", "app.js").is_file()
    assert root.joinpath("assets", "api.js").is_file()
    assert root.joinpath("assets", "styles.css").is_file()

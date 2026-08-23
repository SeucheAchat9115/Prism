"""Verify that the clean installed wheel contains and serves its browser assets."""

from __future__ import annotations

import gc
from pathlib import Path
from tempfile import TemporaryDirectory

from fastapi.testclient import TestClient

from prism.api import create_app
from prism.application import ApplicationService
from prism.audio import FakeAudioBackend
from prism.demo import ensure_demo

# Windows releases NumPy-backed cache mappings when this interpreter exits.
with TemporaryDirectory(ignore_cleanup_errors=True) as temporary:
    working = Path(temporary) / "wheel-ui.prism-work"
    ensure_demo(working)
    service = ApplicationService(working, backend_factory=FakeAudioBackend)
    try:
        client = TestClient(create_app(service))
        page = client.get("/")
        script = client.get("/assets/app.js")
        capabilities = client.get("/api/v1/capabilities")
        assert page.status_code == 200 and "Prism Session" in page.text
        assert script.status_code == 200 and "connectEvents" in script.text
        assert capabilities.json()["ui"] == {"browser_session": True, "path": "/"}
    finally:
        service.close()
    del client
    del service
    gc.collect()

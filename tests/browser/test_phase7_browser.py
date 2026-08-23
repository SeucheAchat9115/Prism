from __future__ import annotations

import json
import socket
import time
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from threading import Thread
from typing import Any

import pytest
import uvicorn
from playwright.sync_api import Page, expect
from typer.testing import CliRunner

from vibesound.api import create_app
from vibesound.application import ApplicationService
from vibesound.audio import FakeAudioBackend
from vibesound.cli import app as cli_app
from vibesound.demo import demo_ids, ensure_demo

pytestmark = pytest.mark.browser


@dataclass(frozen=True)
class BrowserServer:
    url: str
    working: Path
    service: ApplicationService
    project: Any


@pytest.fixture
def browser_server(tmp_path: Path) -> Iterator[BrowserServer]:
    working = tmp_path / "phase7-browser.vibesound-work"
    project = ensure_demo(working)
    service = ApplicationService(working, backend_factory=FakeAudioBackend)
    listener = socket.create_server(("127.0.0.1", 0))
    port = int(listener.getsockname()[1])
    server = uvicorn.Server(
        uvicorn.Config(
            create_app(service),
            host="127.0.0.1",
            port=port,
            log_level="warning",
            lifespan="off",
        )
    )
    thread = Thread(target=server.run, kwargs={"sockets": [listener]}, daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while not server.started and thread.is_alive() and time.monotonic() < deadline:
        time.sleep(0.01)
    if not server.started:
        server.should_exit = True
        thread.join(timeout=2)
        listener.close()
        service.close()
        raise RuntimeError("The browser test server did not start")
    try:
        yield BrowserServer(f"http://127.0.0.1:{port}", working, service, project)
    finally:
        server.should_exit = True
        thread.join(timeout=5)
        listener.close()
        service.close()


def open_session(page: Page, server: BrowserServer) -> None:
    page.goto(server.url)
    expect(page.locator("#boot-screen")).to_be_hidden(timeout=10_000)
    expect(page.get_by_test_id("socket-status")).to_contain_text("Live")


def test_session_controls_mixer_render_and_errors(
    page: Page,
    browser_server: BrowserServer,
) -> None:
    ids = demo_ids(browser_server.project.project_id)
    open_session(page, browser_server)

    expect(page.locator("#project-name")).to_have_text("VibeSound demo")
    expect(page.get_by_test_id("session-grid").locator(".slot-button")).to_have_count(2)
    expect(page.get_by_test_id("validation-content")).to_contain_text("checks passed")

    kick = page.get_by_test_id(f"slot-{ids['drums']}-{ids['verse']}")
    kick.click()
    expect(kick).to_have_attribute("data-state", "active")
    page.get_by_test_id(f"stop-track-{ids['drums']}").click()
    expect(kick).to_have_attribute("data-state", "idle")

    page.get_by_test_id("transport-play").click()
    expect(page.locator("#transport-mode")).to_have_attribute("data-state", "playing")
    page.get_by_test_id("transport-pause").click()
    expect(page.locator("#transport-mode")).to_have_attribute("data-state", "paused")

    gain = page.get_by_test_id(f"mixer-{ids['drums']}-gain_db")
    gain.fill("-12")
    gain.dispatch_event("change")
    expect(page.locator("#saving-state")).to_have_text("Synced")
    expect(gain).to_have_value("-12")
    assert browser_server.service.get_project().tracks[0].mixer.gain_db == -12.0

    page.get_by_test_id("render-scene").select_option(str(ids["verse"]))
    page.locator("#render-bars").fill("1")
    page.locator("#render-output").fill("browser-e2e.wav")
    page.get_by_test_id("render-submit").click()
    expect(page.get_by_test_id("render-status")).to_have_attribute(
        "data-state", "completed", timeout=30_000
    )
    expect(page.get_by_test_id("render-status")).to_contain_text("SHA-256")
    assert (browser_server.working / "exports" / "browser-e2e.wav").is_file()

    page.locator("#render-output").fill("../escape.wav")
    page.get_by_test_id("render-submit").click()
    expect(page.locator(".toast.error")).to_contain_text("escapes the project export root")


def test_cli_changes_reconcile_without_reload(
    page: Page,
    browser_server: BrowserServer,
    tmp_path: Path,
) -> None:
    ids = demo_ids(browser_server.project.project_id)
    open_session(page, browser_server)
    original_revision = browser_server.service.get_project().revision.number
    operations = tmp_path / "browser-cli-operations.json"
    operations.write_text(
        json.dumps([{"op": "mixer.update", "track_id": str(ids["synth"]), "muted": True}]),
        encoding="utf-8",
    )

    result = CliRunner().invoke(
        cli_app,
        [
            "transaction",
            "commit",
            str(browser_server.working),
            str(operations),
            "--url",
            browser_server.url,
            "--json",
        ],
    )

    assert result.exit_code == 0, result.stdout
    expect(page.get_by_test_id("revision")).to_have_text(f"REV {original_revision + 1}")
    expect(page.get_by_test_id(f"mixer-{ids['synth']}-muted")).to_have_attribute(
        "aria-pressed", "true"
    )


def test_stale_mixer_retry_and_true_conflict(page: Page, browser_server: BrowserServer) -> None:
    ids = demo_ids(browser_server.project.project_id)
    open_session(page, browser_server)
    project_id = str(browser_server.project.project_id)
    gain_test_id = f"mixer-{ids['drums']}-gain_db"

    unrelated = {
        "base_revision": browser_server.service.get_project().revision.number,
        "operations": [{"op": "project.rename", "name": "Auto retry demo"}],
    }
    page.evaluate(
        """async ({path, request, testId}) => {
          await fetch(path, {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify(request),
          });
          const control = document.querySelector(`[data-testid="${testId}"]`);
          control.value = "-6";
          control.dispatchEvent(new Event("change", {bubbles: true}));
        }""",
        {
            "path": f"/api/v1/projects/{project_id}/transactions",
            "request": unrelated,
            "testId": gain_test_id,
        },
    )
    expect(page.get_by_test_id("conflict-dialog")).to_be_hidden()
    expect(page.get_by_test_id(gain_test_id)).to_have_value("-6")

    current = browser_server.service.get_project()
    conflicting = {
        "base_revision": current.revision.number,
        "operations": [
            {
                "op": "mixer.update",
                "track_id": str(ids["drums"]),
                "gain_db": -3,
            }
        ],
    }
    page.evaluate(
        """async ({path, request, testId}) => {
          await fetch(path, {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify(request),
          });
          const control = document.querySelector(`[data-testid="${testId}"]`);
          control.value = "-9";
          control.dispatchEvent(new Event("change", {bubbles: true}));
        }""",
        {
            "path": f"/api/v1/projects/{project_id}/transactions",
            "request": conflicting,
            "testId": gain_test_id,
        },
    )

    dialog = page.get_by_test_id("conflict-dialog")
    expect(dialog).to_be_visible()
    expect(page.locator("#conflict-latest")).to_have_text("-3.0 dB")
    expect(page.locator("#conflict-mine")).to_have_text("-9.0 dB")
    page.get_by_test_id("conflict-mine-button").click()
    expect(dialog).to_be_hidden()
    expect(page.get_by_test_id(gain_test_id)).to_have_value("-9")
    drums = next(
        track
        for track in browser_server.service.get_project().tracks
        if track.id == ids["drums"]
    )
    assert drums.mixer.gain_db == -9.0

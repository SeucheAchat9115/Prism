# Phase 7 browser session

Phase 7 adds a focused desktop/laptop session view to the loopback VibeSound
service. It is a packaged HTML, CSS, and vanilla JavaScript client of the same
versioned API used by the CLI; it does not add a second state owner or require a
Node build.

## Start a session

Create or reopen the redistributable synthetic demo, bind the service, and ask
the system browser to open the actual bound URL:

```powershell
vibesound demo demo.vibesound-work --open
```

For an existing working project:

```powershell
vibesound serve demo.vibesound-work --open
```

The browser request is opt-in. Without `--open`, navigate to the URL printed by
the command, normally `http://127.0.0.1:8765/`. The service remains a foreground
process and stops with Ctrl+C. A failed system-browser request is a nonfatal
warning: the URL stays available for manual opening.

`--dry-run --open` reports `open_requested: true` and
`browser_opened: false` without launching anything. `demo --no-serve --open` is
rejected because there would be no local page to open.

The opt-in manual example wraps the same lifecycle:

```powershell
uv run python examples/11_browser_session.py
```

## Included workflow

The dark studio surface exposes:

- the project name, persisted revision, WebSocket state, audio state, and
  layered validation result;
- play, pause, stop, reset, frame position, tempo, meter, and quantization;
- an order-stable scene-by-track grid with empty, queued, active, and idle slot
  states plus per-track stop controls;
- gain, pan, mute, and solo for every track;
- a scene render form with a one-to-64-bar duration and project-local output
  path; and
- a compact realtime activity feed and understandable API errors.

The render form always previews before submitting. It launches the selected
scene at frame zero in an offline job, independent of the live transport. The
completed card reports the state, project-local path, and SHA-256 digest; Phase
7 does not expose a browser download route.

Structural authoring, audio upload, arrangement editing, mobile-first layout,
authentication, remote access, and render downloads remain outside Phase 7.

## Synchronization and edit safety

Startup reads readiness, opens the event stream, and fetches project, runtime,
validation, and job state together. Project and runtime revisions must agree;
the client retries a moving snapshot up to three times before showing a startup
error. Events received during this window are buffered.

The WebSocket reconnects with capped exponential backoff and performs a full
resync after reconnection. A `project.changed` event refreshes persisted and
runtime state, so CLI transactions appear without a page reload. Transport,
clip, audio, and job events update the narrower parts of the interface.

Each mixer gesture commits one typed `mixer.update` operation with a unique
idempotency key. If its base revision is stale, the browser fetches the latest
project:

1. If the desired value is already present, the edit is complete.
2. If only unrelated fields changed, it retries once at the latest revision
   with the same idempotency key.
3. If that mixer field changed too, a blocking chooser displays **Latest** and
   **Mine**. Keeping latest discards the local edit; applying mine explicitly
   commits against the newest revision. Another concurrent field change prompts
   again.

The same reconciliation runs after an unknown network outcome, preventing a
blind duplicate or silent overwrite.

## Local security boundary

The UI is available at `/`, and package-owned assets are under `/assets/`.
They are sent with `Cache-Control: no-store`, content-type sniffing disabled, a
no-referrer policy, and a content security policy that permits only local
scripts, styles, data images, API requests, and the local WebSocket. There are
no CDN or third-party browser dependencies.

Existing host and same-origin checks cover UI requests as well as API traffic.
VibeSound still binds only to loopback addresses; the browser surface is not a
remote deployment boundary and has no authentication.

## Browser and test contract

Modern Chromium is the blocking support target (current Chrome and Edge). The
layout is keyboard accessible, horizontally scrollable for wide sessions, and
respects reduced-motion preferences.

Normal device-free coverage excludes the separately marked browser suite:

```powershell
uv run pytest -m "not audio_device and not browser" --cov
```

Run the browser acceptance tests after installing Chromium:

```powershell
uv run python -m playwright install chromium
uv run pytest -m browser --browser chromium --tracing=retain-on-failure
```

CI installs Chromium with its operating-system dependencies in a dedicated
Ubuntu job, retains traces for failures, and requires that job before clean
wheel acceptance. The wheel smoke test verifies that `/` and its assets are
present in the installed package.

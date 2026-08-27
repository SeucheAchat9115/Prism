# Level 6 — perform and mix in the browser

Goal: use Prism as a small session instrument while proving that browser, CLI,
and WebSocket activity remain synchronized.

## 1. Open the existing song

If the service is already running, open `http://127.0.0.1:8765/`. Otherwise, in
**Terminal A**:

```powershell
$SongProject = Join-Path (Get-Location) "prism-tutorial.prism-work"
uv run prism serve $SongProject --open
```

The page is packaged with Prism; there is no Node build or remote CDN.

## 2. Watch authoritative activity

In **Terminal C**:

```powershell
$SongProject = Join-Path (Get-Location) "prism-tutorial.prism-work"
uv run prism events watch $SongProject --count 20 --timeout 120 --json
```

The stream prints JSONL events such as `clip.scheduled`, `clip.launched`,
`transport.changed`, and `project.changed`.

## 3. Perform in the page

In the browser:

1. Confirm the green connection indicator and expected project name.
2. Click Reset.
3. Click the non-empty cells in the Intro row: Hi-Hat and Pad.
4. Click Play and listen.
5. At the next bar, click the Verse cells: Kick, Snare, Hi-Hat, and Bass.
6. At another bar, click all six Chorus cells.
7. Move Bass and Pad gain sliders and adjust their pan controls.
8. Toggle Lead mute, listen to the difference, then unmute it.
9. Click Stop.

Accepted clicks can be quantized to a future frame. The activity panel and
Terminal C show when they are scheduled and when they actually launch.

## 4. Change state from the CLI while watching the page

In **Terminal B**:

```powershell
$SongProject = Join-Path (Get-Location) "prism-tutorial.prism-work"
uv run prism transport reset $SongProject --json
uv run prism session launch $SongProject --track Kick --scene Chorus --json
uv run prism session launch $SongProject --track Bass --scene Chorus --json
uv run prism transport play $SongProject --json
```

The corresponding browser cells and transport state update from events. Stop:

```powershell
uv run prism transport stop $SongProject --json
```

## 5. Render from the browser

Use the render panel:

1. Select the Chorus scene.
2. Enter `4` bars and `browser-performance.wav` as the output name.
3. Click **Preview & render**. Prism validates the request first, submits it,
   and then shows job progress; wait for `completed`.
4. Confirm the same job from Terminal B:

```powershell
uv run prism job list $SongProject --json
```

The browser render starts the selected scene at frame zero; it does not capture
the earlier live performance. It also does not download files. Open the
job-reported path from PowerShell when you want to listen.

Checkpoint: you have used the human UI as a client while the CLI and event
stream independently confirmed the same service-owned state.

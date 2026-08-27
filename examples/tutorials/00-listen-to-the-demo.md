# Level 0 — listen to the demo

Goal: open an existing Prism project, make its drum and synth tracks audible,
play them live, render two bars, and listen to the exported WAV.

## 1. Start the supplied demo

In **Terminal A**:

```powershell
$DemoProject = Join-Path (Get-Location) "prism-listening-demo.prism-work"
uv run prism demo $DemoProject --open
```

Keep the command running. It prints the loopback URL and opens the session UI.
The initial synth track is muted on purpose so the mixer state is visible.

In **Terminal B**, recreate the same variable and prove that the command is
connected to the intended project:

```powershell
$DemoProject = Join-Path (Get-Location) "prism-listening-demo.prism-work"
uv run prism server status $DemoProject --json
uv run prism server capabilities $DemoProject --json
uv run prism project validate $DemoProject --json
```

Each envelope should contain `"ok":true`.

## 2. Check whether live audio is available

```powershell
$Devices = uv run prism audio devices $DemoProject --json | ConvertFrom-Json
$Devices.data.devices | Format-Table index,name,host_api,max_output_channels
```

If a device is listed but Prism did not select the desired one, preview and
then perform an explicit restart. Replace `3` with the displayed index:

```powershell
uv run prism audio restart $DemoProject --device 3 --dry-run --json
uv run prism audio restart $DemoProject --device 3 --json
```

If no device is listed, continue anyway. The render in step 5 is device-free.

## 3. Unmute the synth safely

Resolve the synth track instead of guessing its UUID:

```powershell
$SynthTrack = (uv run prism entity resolve $DemoProject track Synth --json | ConvertFrom-Json).data.id
$Unmute = @(
  @{ op = "mixer.update"; track_id = $SynthTrack; muted = $false }
)
ConvertTo-Json -InputObject $Unmute -Depth 8 | Set-Content -Encoding utf8 demo-unmute.json
uv run prism transaction preview $DemoProject demo-unmute.json --json
uv run prism transaction commit $DemoProject demo-unmute.json --idempotency-key demo-unmute-v1 --json
```

Preview must report `committed:false`; commit advances the project revision.

## 4. Load and play the Verse scene

Reset first, schedule both slots at frame zero, then start transport:

```powershell
uv run prism transport reset $DemoProject --json
uv run prism session launch $DemoProject --track Drums --scene Verse --json
uv run prism session launch $DemoProject --track Synth --scene Verse --json
uv run prism transport play $DemoProject --json
```

You should hear the drum and decaying synth loops. Inspect what actually became
active:

```powershell
uv run prism project state $DemoProject --json
```

Stop cleanly:

```powershell
uv run prism transport stop $DemoProject --json
```

In the browser you can repeat the same workflow by clicking the Verse cells,
the Synth mute button, and Play. The browser and CLI control the same service.

## 5. Render and listen without relying on the device

```powershell
$VerseScene = (uv run prism entity resolve $DemoProject scene Verse --json | ConvertFrom-Json).data.id
$RenderCommands = @(
  @{ frame = 0; operation = "launch_scene"; scene_id = $VerseScene }
)
ConvertTo-Json -InputObject $RenderCommands -Depth 8 | Set-Content -Encoding utf8 demo-render.json
uv run prism render $DemoProject --bars 2 --commands demo-render.json --output demo-verse.wav --dry-run --json
$Render = uv run prism render $DemoProject --bars 2 --commands demo-render.json --output demo-verse.wav --idempotency-key demo-verse-v1 --json | ConvertFrom-Json
$Render.data.output_path
Start-Process $Render.data.output_path
```

Checkpoint: you have loaded a project, controlled real or device-free playback,
changed a mixer value transactionally, rendered a WAV, and listened to it.

Stop Terminal A with Ctrl+C before Level 1.

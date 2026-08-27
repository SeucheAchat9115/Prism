# Level 7 — add an optional VST3 effect

Goal: apply a licensed, user-installed VST3 effect to one track in an offline
render. The built-in Prism synth remains the instrument source.

Important boundaries:

- VST3 binaries are never included with Prism or copied into the project.
- Search paths do not grant trust.
- Trust is explicit and tied to the exact binary SHA-256.
- Phase 9 supports effects, not VST instruments.
- Live playback remains dry; the effect is heard only in offline renders.

## 1. Install the optional host

Stop the foreground service with Ctrl+C, then:

```powershell
uv sync --locked --extra dev --extra plugins
```

## 2. Discover and trust exactly one effect

Replace the example paths with a VST3 effect already installed and licensed on
your machine:

```powershell
$PluginRoot = "C:\Program Files\Common Files\VST3"
$PluginPath = "C:\Program Files\Common Files\VST3\YourEffect.vst3"
uv run prism plugin path-add $PluginRoot --json
uv run prism plugin trust $PluginPath --json
$Registry = uv run prism plugin scan --json | ConvertFrom-Json
$Registry.data.plugins | Format-Table registry_id,name,manufacturer,available,error
```

Choose an `available:true` effect and copy its registry UUID:

```powershell
$RegistryId = "REPLACE-WITH-REGISTRY-UUID"
```

Trust only the plugin you intend to execute. A future binary change invalidates
this approval.

## 3. Restart the song service and attach the effect

In **Terminal A**:

```powershell
$SongProject = Join-Path (Get-Location) "prism-tutorial.prism-work"
uv run prism serve $SongProject --open
```

In **Terminal B**, repeat `$SongProject` and `$RegistryId`, then attach to Pad:

```powershell
$SongProject = Join-Path (Get-Location) "prism-tutorial.prism-work"
$RegistryId = "REPLACE-WITH-REGISTRY-UUID"
uv run prism plugin compatibility $SongProject --json
uv run prism plugin attach $SongProject --track Pad --registry-id $RegistryId --dry-run --json
$Attached = uv run prism plugin attach $SongProject --track Pad --registry-id $RegistryId --idempotency-key tutorial-pad-effect-v1 --json | ConvertFrom-Json
$InstanceId = $Attached.data.created_ids.plugin_instances[0]
$InstanceId
```

## 4. Inspect and adjust normalized parameters

```powershell
$Parameters = uv run prism plugin parameters $SongProject $InstanceId --json | ConvertFrom-Json
$Parameters.data.parameters | Format-Table id,name,raw_value,value
```

Pick a parameter ID and set a normalized value from `0.0` through `1.0`:

```powershell
$ParameterId = "REPLACE-WITH-PARAMETER-ID"
uv run prism plugin set $SongProject $InstanceId $ParameterId 0.65 --dry-run --json
uv run prism plugin set $SongProject $InstanceId $ParameterId 0.65 --idempotency-key tutorial-effect-param-v1 --json
uv run prism plugin state-save $SongProject $InstanceId --json
uv run prism plugin worker-status $SongProject --json
```

## 5. Render and compare

Reuse `mini-song-render.json` from Level 3:

```powershell
uv run prism render $SongProject --bars 8 --commands mini-song-render.json --output effected-mini-song.wav --dry-run --json
$Effected = uv run prism render $SongProject --bars 8 --commands mini-song-render.json --output effected-mini-song.wav --idempotency-key effected-mini-song-v1 --json | ConvertFrom-Json
Start-Process $Effected.data.output_path
```

Live transport still plays the dry Pad. The rendered file follows clip gain →
VST3 effect → track mixer → stereo mix.

## 6. Recover or remove safely

```powershell
uv run prism plugin worker-restart $SongProject --json
uv run prism plugin compatibility $SongProject --json
uv run prism plugin remove $SongProject $InstanceId --dry-run --json
```

Commit removal only when you actually want it:

```powershell
uv run prism plugin remove $SongProject $InstanceId --idempotency-key remove-pad-effect-v1 --json
```

The complete opt-in automated companion is:

```powershell
uv run python examples/13_vst3_effect.py --plugin $PluginPath
```

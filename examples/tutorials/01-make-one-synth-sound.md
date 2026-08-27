# Level 1 — make one native synth sound

Goal: create an empty project, generate a lead loop with Prism’s built-in synth,
turn it into a clip, load it into a scene, play it, and render it.

## 1. Create and serve a blank song

In **Terminal A**:

```powershell
$SongProject = Join-Path (Get-Location) "prism-tutorial.prism-work"
uv run prism project init $SongProject --name "My Prism Tutorial Song" --tempo 120 --sample-rate 44100 --json
uv run prism serve $SongProject --open
```

Leave the service running. In **Terminal B**:

```powershell
$SongProject = Join-Path (Get-Location) "prism-tutorial.prism-work"
uv run prism synth presets --json
```

The catalog contains three percussion presets and three melodic presets.

## 2. Preview a lead sound

The sequence has eight equal steps. Notes use scientific pitch notation; `-`
is a rest and `+` joins chord notes.

```powershell
uv run prism synth generate $SongProject `
  --preset lead `
  --sequence "C4,E4,G4,Bb4,G4,E4,D4,-" `
  --bars 2 `
  --name first-lead.wav `
  --waveform triangle `
  --attack-ms 12 `
  --release-ms 180 `
  --cutoff-hz 3200 `
  --dry-run --json
```

Dry-run synthesizes and validates the exact WAV, previews the asset transaction,
then discards staging. It does not change the project.

## 3. Generate and import the asset

```powershell
$Lead = uv run prism synth generate $SongProject `
  --preset lead `
  --sequence "C4,E4,G4,Bb4,G4,E4,D4,-" `
  --bars 2 `
  --name first-lead.wav `
  --waveform triangle `
  --attack-ms 12 `
  --release-ms 180 `
  --cutoff-hz 3200 `
  --idempotency-key tutorial-first-lead-v1 `
  --json | ConvertFrom-Json
$LeadAsset = $Lead.data.asset_id
$LeadAsset
```

The returned UUID identifies an immutable WAV asset inside the working project.

## 4. Create the track, scene, clip, and slot

```powershell
$LeadTrack = [guid]::NewGuid().ToString()
$JamScene = [guid]::NewGuid().ToString()
$LeadClip = [guid]::NewGuid().ToString()
$Structure = @(
  @{ op = "track.create"; track_id = $LeadTrack; name = "Lead"; order = 0 },
  @{ op = "scene.create"; scene_id = $JamScene; name = "Jam"; order = 0 },
  @{ op = "clip.create"; clip_id = $LeadClip; name = "First Lead"; asset_id = $LeadAsset; loop = $true },
  @{ op = "slot.assign"; track_id = $LeadTrack; scene_id = $JamScene; clip_id = $LeadClip },
  @{ op = "mixer.update"; track_id = $LeadTrack; gain_db = -9.0; pan = 0.15 }
)
ConvertTo-Json -InputObject $Structure -Depth 8 | Set-Content -Encoding utf8 first-lead-structure.json
uv run prism transaction preview $SongProject first-lead-structure.json --json
uv run prism transaction commit $SongProject first-lead-structure.json --idempotency-key first-lead-structure-v1 --json
uv run prism project validate $SongProject --json
```

An asset is source audio. A clip adds playback behavior. A slot places that clip
at one track/scene cell.

## 5. Load, play, and stop the sound

```powershell
uv run prism transport reset $SongProject --json
uv run prism session launch $SongProject --track Lead --scene Jam --json
uv run prism transport play $SongProject --json
uv run prism project state $SongProject --json
```

Listen for the melody, then stop:

```powershell
uv run prism transport stop $SongProject --json
```

## 6. Render and listen in the default player

```powershell
$JamScene = (uv run prism entity resolve $SongProject scene Jam --json | ConvertFrom-Json).data.id
$Commands = @(@{ frame = 0; operation = "launch_scene"; scene_id = $JamScene })
ConvertTo-Json -InputObject $Commands -Depth 8 | Set-Content -Encoding utf8 first-lead-render.json
$Render = uv run prism render $SongProject --bars 2 --commands first-lead-render.json --output first-lead.wav --idempotency-key first-lead-render-v1 --json | ConvertFrom-Json
Start-Process $Render.data.output_path
```

Checkpoint: `prism-tutorial.prism-work` contains one playable native synth
track. Leave Terminal A running for Level 2.

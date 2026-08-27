# Level 2 — build a short drum loop

Goal: continue the Level 1 project, synthesize kick, snare, and hi-hat assets,
put each sound on its own track, and play a synchronized groove.

In **Terminal B**:

```powershell
$SongProject = Join-Path (Get-Location) "prism-tutorial.prism-work"
uv run prism server status $SongProject --json
```

## 1. Program the three patterns

Each pattern has sixteen steps across one 4/4 bar. `x` triggers a hit and `-`
is a rest.

```powershell
$Kick = uv run prism synth generate $SongProject --preset kick --sequence "x,-,-,-,x,-,-,-,x,-,-,-,x,-,-,-" --bars 1 --name kick-loop.wav --idempotency-key tutorial-kick-v1 --json | ConvertFrom-Json
$Snare = uv run prism synth generate $SongProject --preset snare --sequence "-,-,-,-,x,-,-,-,-,-,-,-,x,-,-,-" --bars 1 --name snare-loop.wav --seed 11 --idempotency-key tutorial-snare-v1 --json | ConvertFrom-Json
$Hat = uv run prism synth generate $SongProject --preset hihat --sequence "x,-,x,-,x,-,x,-,x,-,x,-,x,-,x,-" --bars 1 --name hihat-loop.wav --gain-db -8 --seed 17 --idempotency-key tutorial-hihat-v1 --json | ConvertFrom-Json
$Kick.data.asset_id
$Snare.data.asset_id
$Hat.data.asset_id
```

Change one `-` to `x` and use a new idempotency key whenever you want a pattern
variation.

## 2. Add the drum tracks and Groove scene

```powershell
$KickTrack = [guid]::NewGuid().ToString()
$SnareTrack = [guid]::NewGuid().ToString()
$HatTrack = [guid]::NewGuid().ToString()
$GrooveScene = [guid]::NewGuid().ToString()
$KickClip = [guid]::NewGuid().ToString()
$SnareClip = [guid]::NewGuid().ToString()
$HatClip = [guid]::NewGuid().ToString()
$DrumStructure = @(
  @{ op = "track.create"; track_id = $KickTrack; name = "Kick"; order = 1 },
  @{ op = "track.create"; track_id = $SnareTrack; name = "Snare"; order = 2 },
  @{ op = "track.create"; track_id = $HatTrack; name = "Hi-Hat"; order = 3 },
  @{ op = "scene.create"; scene_id = $GrooveScene; name = "Groove"; order = 1 },
  @{ op = "clip.create"; clip_id = $KickClip; name = "Kick Loop"; asset_id = $Kick.data.asset_id; loop = $true },
  @{ op = "clip.create"; clip_id = $SnareClip; name = "Snare Loop"; asset_id = $Snare.data.asset_id; loop = $true },
  @{ op = "clip.create"; clip_id = $HatClip; name = "Hi-Hat Loop"; asset_id = $Hat.data.asset_id; loop = $true },
  @{ op = "slot.assign"; track_id = $KickTrack; scene_id = $GrooveScene; clip_id = $KickClip },
  @{ op = "slot.assign"; track_id = $SnareTrack; scene_id = $GrooveScene; clip_id = $SnareClip },
  @{ op = "slot.assign"; track_id = $HatTrack; scene_id = $GrooveScene; clip_id = $HatClip },
  @{ op = "mixer.update"; track_id = $KickTrack; gain_db = -3.0; pan = 0.0 },
  @{ op = "mixer.update"; track_id = $SnareTrack; gain_db = -7.0; pan = 0.0 },
  @{ op = "mixer.update"; track_id = $HatTrack; gain_db = -12.0; pan = 0.25 }
)
ConvertTo-Json -InputObject $DrumStructure -Depth 8 | Set-Content -Encoding utf8 drum-structure.json
uv run prism transaction preview $SongProject drum-structure.json --json
uv run prism transaction commit $SongProject drum-structure.json --idempotency-key drum-structure-v1 --json
uv run prism project validate $SongProject --json
```

## 3. Load all three loops at the same frame

Schedule while transport is reset, then play:

```powershell
uv run prism transport reset $SongProject --json
uv run prism session launch $SongProject --track Kick --scene Groove --json
uv run prism session launch $SongProject --track Snare --scene Groove --json
uv run prism session launch $SongProject --track Hi-Hat --scene Groove --json
uv run prism transport play $SongProject --json
uv run prism project state $SongProject --json
```

Listen for a four-on-the-floor kick, backbeat snare, and eighth-note hats. Stop:

```powershell
uv run prism transport stop $SongProject --json
```

## 4. Render the drum loop

```powershell
$GrooveScene = (uv run prism entity resolve $SongProject scene Groove --json | ConvertFrom-Json).data.id
$Commands = @(@{ frame = 0; operation = "launch_scene"; scene_id = $GrooveScene })
ConvertTo-Json -InputObject $Commands -Depth 8 | Set-Content -Encoding utf8 drum-render.json
$DrumRender = uv run prism render $SongProject --bars 4 --commands drum-render.json --output drum-loop.wav --idempotency-key drum-loop-render-v1 --json | ConvertFrom-Json
Start-Process $DrumRender.data.output_path
```

Checkpoint: the project has four tracks—three drums plus the Level 1 lead—and
two scenes. Leave Terminal A running for Level 3.

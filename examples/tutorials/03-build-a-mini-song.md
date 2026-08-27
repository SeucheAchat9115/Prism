# Level 3 — build a multi-track mini-song

Goal: continue the same project, add native bass and pad sounds, organize four
song sections, perform the Chorus live, render an eight-bar arrangement, and
export a portable `.prism` project.

```powershell
$SongProject = Join-Path (Get-Location) "prism-tutorial.prism-work"
uv run prism server status $SongProject --json
```

## 1. Create bass and pad assets

The bass uses single notes. The pad uses `+` to form chords.

```powershell
$Bass = uv run prism synth generate $SongProject `
  --preset bass `
  --sequence "C2,-,C2,Eb2,G1,-,Bb1,-" `
  --bars 2 `
  --name bass-verse.wav `
  --waveform saw `
  --cutoff-hz 780 `
  --release-ms 120 `
  --idempotency-key tutorial-bass-v1 `
  --json | ConvertFrom-Json

$Pad = uv run prism synth generate $SongProject `
  --preset pad `
  --sequence "C3+Eb3+G3,-,Ab2+C3+Eb3,-" `
  --bars 2 `
  --name pad-chords.wav `
  --waveform triangle `
  --attack-ms 260 `
  --release-ms 520 `
  --gain-db -8 `
  --idempotency-key tutorial-pad-v1 `
  --json | ConvertFrom-Json
```

## 2. Resolve the material from Levels 1–2

Names are human-friendly selectors; the project stores stable UUIDs.

```powershell
$LeadTrack = (uv run prism entity resolve $SongProject track Lead --json | ConvertFrom-Json).data.id
$KickTrack = (uv run prism entity resolve $SongProject track Kick --json | ConvertFrom-Json).data.id
$SnareTrack = (uv run prism entity resolve $SongProject track Snare --json | ConvertFrom-Json).data.id
$HatTrack = (uv run prism entity resolve $SongProject track Hi-Hat --json | ConvertFrom-Json).data.id
$LeadClip = (uv run prism entity resolve $SongProject clip "First Lead" --json | ConvertFrom-Json).data.id
$KickClip = (uv run prism entity resolve $SongProject clip "Kick Loop" --json | ConvertFrom-Json).data.id
$SnareClip = (uv run prism entity resolve $SongProject clip "Snare Loop" --json | ConvertFrom-Json).data.id
$HatClip = (uv run prism entity resolve $SongProject clip "Hi-Hat Loop" --json | ConvertFrom-Json).data.id
```

## 3. Add tracks, scenes, clips, and assignments

```powershell
$BassTrack = [guid]::NewGuid().ToString()
$PadTrack = [guid]::NewGuid().ToString()
$BassClip = [guid]::NewGuid().ToString()
$PadClip = [guid]::NewGuid().ToString()
$Intro = [guid]::NewGuid().ToString()
$Verse = [guid]::NewGuid().ToString()
$Chorus = [guid]::NewGuid().ToString()
$Outro = [guid]::NewGuid().ToString()

$SongStructure = @(
  @{ op = "track.create"; track_id = $BassTrack; name = "Bass"; order = 4 },
  @{ op = "track.create"; track_id = $PadTrack; name = "Pad"; order = 5 },
  @{ op = "scene.create"; scene_id = $Intro; name = "Intro"; order = 2 },
  @{ op = "scene.create"; scene_id = $Verse; name = "Verse"; order = 3 },
  @{ op = "scene.create"; scene_id = $Chorus; name = "Chorus"; order = 4 },
  @{ op = "scene.create"; scene_id = $Outro; name = "Outro"; order = 5 },
  @{ op = "clip.create"; clip_id = $BassClip; name = "Bass Verse"; asset_id = $Bass.data.asset_id; loop = $true },
  @{ op = "clip.create"; clip_id = $PadClip; name = "Pad Chords"; asset_id = $Pad.data.asset_id; loop = $true },

  @{ op = "slot.assign"; track_id = $HatTrack; scene_id = $Intro; clip_id = $HatClip },
  @{ op = "slot.assign"; track_id = $PadTrack; scene_id = $Intro; clip_id = $PadClip },

  @{ op = "slot.assign"; track_id = $KickTrack; scene_id = $Verse; clip_id = $KickClip },
  @{ op = "slot.assign"; track_id = $SnareTrack; scene_id = $Verse; clip_id = $SnareClip },
  @{ op = "slot.assign"; track_id = $HatTrack; scene_id = $Verse; clip_id = $HatClip },
  @{ op = "slot.assign"; track_id = $BassTrack; scene_id = $Verse; clip_id = $BassClip },

  @{ op = "slot.assign"; track_id = $KickTrack; scene_id = $Chorus; clip_id = $KickClip },
  @{ op = "slot.assign"; track_id = $SnareTrack; scene_id = $Chorus; clip_id = $SnareClip },
  @{ op = "slot.assign"; track_id = $HatTrack; scene_id = $Chorus; clip_id = $HatClip },
  @{ op = "slot.assign"; track_id = $BassTrack; scene_id = $Chorus; clip_id = $BassClip },
  @{ op = "slot.assign"; track_id = $PadTrack; scene_id = $Chorus; clip_id = $PadClip },
  @{ op = "slot.assign"; track_id = $LeadTrack; scene_id = $Chorus; clip_id = $LeadClip },

  @{ op = "slot.assign"; track_id = $KickTrack; scene_id = $Outro; clip_id = $KickClip },
  @{ op = "slot.assign"; track_id = $HatTrack; scene_id = $Outro; clip_id = $HatClip },
  @{ op = "slot.assign"; track_id = $PadTrack; scene_id = $Outro; clip_id = $PadClip },

  @{ op = "mixer.update"; track_id = $BassTrack; gain_db = -7.0; pan = -0.12 },
  @{ op = "mixer.update"; track_id = $PadTrack; gain_db = -10.0; pan = -0.25 },
  @{ op = "mixer.update"; track_id = $LeadTrack; gain_db = -9.0; pan = 0.30 }
)
ConvertTo-Json -InputObject $SongStructure -Depth 10 | Set-Content -Encoding utf8 mini-song-structure.json
uv run prism transaction preview $SongProject mini-song-structure.json --json
uv run prism transaction commit $SongProject mini-song-structure.json --idempotency-key mini-song-structure-v1 --json
uv run prism project validate $SongProject --json
```

The same clip may appear in several scene slots. Launching another scene changes
which track/scene cells are active; no audio bytes are duplicated.

## 4. Perform the Chorus live

```powershell
uv run prism transport reset $SongProject --json
uv run prism session launch $SongProject --track Kick --scene Chorus --json
uv run prism session launch $SongProject --track Snare --scene Chorus --json
uv run prism session launch $SongProject --track Hi-Hat --scene Chorus --json
uv run prism session launch $SongProject --track Bass --scene Chorus --json
uv run prism session launch $SongProject --track Pad --scene Chorus --json
uv run prism session launch $SongProject --track Lead --scene Chorus --json
uv run prism transport play $SongProject --json
```

Listen, inspect, and stop:

```powershell
uv run prism project state $SongProject --json
uv run prism transport stop $SongProject --json
```

## 5. Render an eight-bar arrangement

This project is 44.1 kHz, 120 BPM, and 4/4, so one bar is 88,200 frames. Each
section below lasts two bars.

```powershell
$Intro = (uv run prism entity resolve $SongProject scene Intro --json | ConvertFrom-Json).data.id
$Verse = (uv run prism entity resolve $SongProject scene Verse --json | ConvertFrom-Json).data.id
$Chorus = (uv run prism entity resolve $SongProject scene Chorus --json | ConvertFrom-Json).data.id
$Outro = (uv run prism entity resolve $SongProject scene Outro --json | ConvertFrom-Json).data.id
$TwoBars = 176400
$Arrangement = @(
  @{ frame = 0; operation = "launch_scene"; scene_id = $Intro },
  @{ frame = $TwoBars; operation = "stop_all" },
  @{ frame = $TwoBars; operation = "launch_scene"; scene_id = $Verse },
  @{ frame = (2 * $TwoBars); operation = "stop_all" },
  @{ frame = (2 * $TwoBars); operation = "launch_scene"; scene_id = $Chorus },
  @{ frame = (3 * $TwoBars); operation = "stop_all" },
  @{ frame = (3 * $TwoBars); operation = "launch_scene"; scene_id = $Outro },
  @{ frame = (4 * $TwoBars); operation = "stop_all" }
)
ConvertTo-Json -InputObject $Arrangement -Depth 8 | Set-Content -Encoding utf8 mini-song-render.json
uv run prism render $SongProject --bars 8 --commands mini-song-render.json --output mini-song.wav --dry-run --json
$Mix = uv run prism render $SongProject --bars 8 --commands mini-song-render.json --output mini-song.wav --idempotency-key mini-song-render-v1 --json | ConvertFrom-Json
$Mix.data.output_path
Start-Process $Mix.data.output_path
```

## 6. Export and validate a portable project

```powershell
$Export = uv run prism project export $SongProject --output mini-song.prism --json | ConvertFrom-Json
$Portable = $Export.data.output_path
uv run prism project show $Portable --portable --json
uv run prism project validate $Portable --portable --json
```

Checkpoint: you have a six-track session, four song sections, an eight-bar WAV,
and a self-contained portable Prism archive.

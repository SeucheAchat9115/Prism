# Level 4 — shape, mix, and edit safely

Goal: design a new synth timbre, swap it into the song without editing
`project.json`, preview mixer changes, observe events, and deliberately verify
stale-revision protection.

```powershell
$SongProject = Join-Path (Get-Location) "prism-tutorial.prism-work"
uv run prism server status $SongProject --json
```

## 1. Generate a contrasting lead patch

```powershell
$BrightLead = uv run prism synth generate $SongProject `
  --preset lead `
  --sequence "G4,Bb4,C5,-,G4,F4,Eb4,-" `
  --bars 2 `
  --name bright-lead.wav `
  --waveform saw `
  --attack-ms 3 `
  --decay-ms 70 `
  --sustain 0.55 `
  --release-ms 90 `
  --cutoff-hz 5000 `
  --gate 0.72 `
  --gain-db -8 `
  --idempotency-key bright-lead-v1 `
  --json | ConvertFrom-Json
```

`waveform`, ADSR, cutoff, and gate are melodic controls. Percussion presets use
their dedicated deterministic drum engines and reject these options.

## 2. Replace the Lead clip’s source through a typed operation

```powershell
$LeadClip = (uv run prism entity resolve $SongProject clip "First Lead" --json | ConvertFrom-Json).data.id
$SwapLead = @(
  @{ op = "clip.update"; clip_id = $LeadClip; asset_id = $BrightLead.data.asset_id; name = "Bright Lead" }
)
ConvertTo-Json -InputObject $SwapLead -Depth 8 | Set-Content -Encoding utf8 swap-lead.json
uv run prism transaction preview $SongProject swap-lead.json --json
uv run prism transaction commit $SongProject swap-lead.json --idempotency-key swap-lead-v1 --json
```

The old asset still exists until an explicit cascade-reviewed deletion. The
project never mutates audio files in place.

## 3. Preview a mix adjustment

```powershell
$BassTrack = (uv run prism entity resolve $SongProject track Bass --json | ConvertFrom-Json).data.id
$PadTrack = (uv run prism entity resolve $SongProject track Pad --json | ConvertFrom-Json).data.id
$LeadTrack = (uv run prism entity resolve $SongProject track Lead --json | ConvertFrom-Json).data.id
$MixChange = @(
  @{ op = "mixer.update"; track_id = $BassTrack; gain_db = -5.5; pan = -0.18 },
  @{ op = "mixer.update"; track_id = $PadTrack; gain_db = -12.0; pan = -0.35 },
  @{ op = "mixer.update"; track_id = $LeadTrack; gain_db = -10.0; pan = 0.35 }
)
ConvertTo-Json -InputObject $MixChange -Depth 8 | Set-Content -Encoding utf8 mix-change.json
uv run prism transaction commit $SongProject mix-change.json --dry-run --json
uv run prism transaction commit $SongProject mix-change.json --idempotency-key mix-change-v1 --json
uv run prism project state $SongProject --json
```

`--dry-run` calls the server’s preview contract; it is not a local guess.

## 4. Prove stale edits cannot overwrite newer work

Create a request that incorrectly claims the project is still at revision 0:

```powershell
$StaleRequest = @{
  base_revision = 0
  operations = @(@{ op = "project.rename"; name = "This must not commit" })
}
ConvertTo-Json -InputObject $StaleRequest -Depth 8 | Set-Content -Encoding utf8 stale-edit.json
uv run prism transaction commit $SongProject stale-edit.json --json
$LASTEXITCODE
```

The command exits with conflict status `4` and reports `stale_revision`. Confirm
that the project name did not change:

```powershell
uv run prism project show $SongProject --json
uv run prism project validate $SongProject --json
```

## 5. Watch changes as events

In **Terminal C**:

```powershell
$SongProject = Join-Path (Get-Location) "prism-tutorial.prism-work"
uv run prism events watch $SongProject --count 5 --timeout 60 --json
```

While it waits, run a reversible mixer change in Terminal B:

```powershell
$LeadTrack = (uv run prism entity resolve $SongProject track Lead --json | ConvertFrom-Json).data.id
$Nudge = @(@{ op = "mixer.update"; track_id = $LeadTrack; gain_db = -9.5 })
ConvertTo-Json -InputObject $Nudge -Depth 8 | Set-Content -Encoding utf8 lead-nudge.json
uv run prism transaction commit $SongProject lead-nudge.json --idempotency-key lead-nudge-v1 --json
```

Checkpoint: you can distinguish immutable assets, mutable clip references,
transaction previews, idempotent commits, runtime mixer refreshes, and stale
write rejection.

# Phase 10.1 — native synthesis and progressive tutorials

Phase 10.1 adds a device-free native sound source and a beginner-to-advanced
learning path. It does not add MIDI clips or external plugin instruments.

## Product outcome

A new user can now start with no audio files and no third-party plugins, create
drums and pitched sounds, place them in session clips, hear them through live
playback when a device is available, render them without hardware, and export a
portable project. The guided path is under
[`examples/tutorials/`](../examples/tutorials/README.md).

## Native synthesis boundary

The native synth generates deterministic mono PCM WAV assets. Once imported,
they use the existing project and engine contracts:

```text
NativeSynthSpec
  → deterministic WAV bytes
  → bounded staged upload
  → previewed/revisioned asset.import transaction
  → AudioClip + ClipSlot transaction
  → live PortAudio or device-free runtime
  → offline stereo render
```

This design gives generated material exactly the same validation, hashing,
copying, cache, playback, render, and portable-export behavior as imported WAV
audio. It avoids introducing a second clip engine before MIDI and instrument
state have proper project models.

The built-in synth is not a `PluginInstance`. It needs no search path, binary
trust, worker, Pedalboard installation, or opaque state. VST3 remains
user-installed, effect-only, one per track, and offline-render-only.

## Presets and sequence language

| Preset | Kind | Default character |
| --- | --- | --- |
| `kick` | Percussion | Pitch-swept electronic kick |
| `snare` | Percussion | Seeded noise plus a tonal body |
| `hihat` | Percussion | Short high-passed seeded noise |
| `bass` | Melodic | Filtered saw bass |
| `lead` | Melodic | Bright square lead |
| `pad` | Melodic | Soft triangle pad |

Percussion sequences contain `x` and `-`. Melodic sequences contain scientific
pitch tokens such as `C4`, rests as `-`, and chords joined with `+`, such as
`C3+E3+G3`. Steps are distributed evenly over `bars` using the project tempo,
meter numerator, and sample rate.

Melodic presets expose optional waveform, attack, decay, sustain, release,
cutoff, gate, and gain controls. Percussion generation is seeded and rejects
melodic-only controls. Output is limited to 120 seconds per request and 32 bars
before the existing staged-asset resource policy is applied.

## CLI

```powershell
uv run prism synth presets --json
uv run prism synth generate song.prism-work `
  --preset bass `
  --sequence "C2,-,C2,Eb2,G1,-,Bb1,-" `
  --bars 2 `
  --name bass.wav `
  --waveform saw `
  --cutoff-hz 800 `
  --dry-run --json
uv run prism synth generate song.prism-work `
  --preset bass `
  --sequence "C2,-,C2,Eb2,G1,-,Bb1,-" `
  --bars 2 `
  --name bass.wav `
  --waveform saw `
  --cutoff-hz 800 `
  --idempotency-key bass-v1 --json
```

Generation creates only an asset. Track, scene, clip, slot, and mixer intent
remain explicit typed transactions.

## Typed Python client

```python
from prism.api import PrismClient
from prism.application import SynthAssetRequest
from prism.synthesis import NativeSynthSpec

with PrismClient() as client:
    ready = client.readiness()
    request = SynthAssetRequest(
        base_revision=ready.revision,
        filename="pad.wav",
        spec=NativeSynthSpec(
            preset="pad",
            sequence=["C3+E3+G3", "-", "F3+A3+C4", "-"],
            bars=2,
        ),
        idempotency_key="pad-v1",
    )
    preview = client.generate_synth_asset(ready.project_id, request, preview=True)
    if not preview.ok:
        raise RuntimeError(preview.transaction.errors)
    result = client.generate_synth_asset(ready.project_id, request)
```

## HTTP and discovery

- `GET /api/v1/synth/presets`
- `POST /api/v1/projects/{project_id}/synth-assets?preview=false`
- `GET /api/v1/capabilities` exposes `native_synth`.
- `GET /api/v1/schemas` exposes `synth_asset_request`.

`SynthAssetRequest` includes the current `base_revision`, a plain `.wav`
filename, a strict `NativeSynthSpec`, an optional caller-supplied `asset_id`, and
an optional idempotency key. `SynthAssetResult` returns the asset UUID, exact
frames/rate/duration/hash, normalized spec, preview status, and complete
`TransactionResult`.

An idempotency-key-derived upload/asset UUID plus a synth-spec digest in the
operation ID ensures that retrying identical intent replays safely while using
the same key for different sound bytes returns `idempotency_conflict`.

Successful commits publish the ordinary `project.changed` event and then
`synth.asset.generated` with asset ID, filename, preset, and SHA-256.

## Tutorial curriculum

The Markdown tutorials are the primary human examples:

1. Listen to the demo and verify real/device-free audio.
2. Generate and play one native lead.
3. Build synchronized kick, snare, and hi-hat tracks.
4. Add bass and pad tracks and render an eight-bar four-scene mini-song.
5. Shape patches, mix, preview, and prove stale-write rejection.
6. Control the same project with `PrismClient` and events.
7. Perform in the packaged browser.
8. Optionally attach a user-installed VST3 effect for offline rendering.
9. Use the toolbox map for loading, diagnostics, and interface selection.

[`examples/14_native_synth_song.py`](../examples/14_native_synth_song.py) is the
device-free automated companion. It creates six assets/tracks, four scenes, an
eight-bar arrangement, validates the project, and reports the rendered peak and
SHA-256.

## Verification

The ordinary source gate covers:

- note parsing, sequence and preset validation;
- deterministic, finite, decodable loop-aligned WAV output;
- all six presets and melodic sound controls;
- preview, commit, event, replay, and idempotency-conflict behavior;
- live-source compatibility through ordinary clips and offline rendering;
- API discovery/schema/routes and typed client parity;
- CLI presets, dry-run, generation, and stable invalid-input envelopes;
- the full device-free mini-song example and tutorial file/index integrity.

Real audio output and third-party VST3 behavior remain opt-in environment tests.

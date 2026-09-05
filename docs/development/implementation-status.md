# Implementation status

## Task 01/35 — protect source audio and make stem exports recoverable

Status: implemented on the task branch; verification is recorded below.

### Completed scope

- Stem export destinations reject project-local symlink components before path
  resolution and reject output containers that overlap source audio, scripts,
  `vst.json`, VST state/preset files, or other registered project files.
- Existing `tracks`, `buses`, and other unrelated WAV files are no longer
  treated as stale by filename. Legacy output trees are preserved; child
  symlinks in the legacy stem trees are rejected before writing.
- Each stem export is rendered into a fresh staging directory under
  `.prism-stems/generations/`. A generation is published by a same-filesystem
  directory rename, followed by an atomic replacement of the small JSON
  ownership manifest. The implementation does not claim that the collection of
  WAV files is one atomic multi-file transaction.
- The manifest records the generation number, completed generation directory,
  and SHA-256 ownership record for every generated WAV. Cleanup after a
  successful export removes only unchanged files recorded by the previous
  manifest. Missing, modified, renamed, producer-added, and unrelated files
  remain recoverable.
- `StemRenderResult.directory` now identifies the completed versioned
  generation, and `StemRenderResult.generation` exposes its monotonic manifest
  generation number. The requested output path remains the producer-facing
  container.

### Compatibility decisions

- Normal single-file `Project.render()` output remains in its existing path and
  behavior. Stem consumers should use the returned `StemRenderResult.directory`
  instead of assuming that WAVs are directly under the requested container.
- A prior export using the old direct `tracks`/`buses` layout is not swept or
  migrated automatically. This avoids deleting producer files that have no
  ownership record; a new export creates a managed generation alongside it.
- The completion manifest is `.prism-stems/manifest.json`; its schema version
  is `1`. Older generation directories remain as recoverable containers; their
  unchanged owned WAVs are cleaned after a successful replacement, while
  modified or added producer files remain accessible.

### Verification

- Focused render and regression tests cover source-byte preservation, unrelated
  WAVs, renamed/removed owned stems, modified generated files, producer-added
  files, child symlink escapes, failure during a middle stem write, manifest
  stability on failure, and repeated successful export.
- `uv run pytest --cov --cov-report=term-missing`: 162 passed, 3 skipped
  (the existing real-VST qualification tests are skipped without their plugin
  environment), 87.59% total coverage.
- `uv run mypy src/prism`: passed.
- `uv run ruff check .`: passed.
- `uv run --extra docs mkdocs build --strict`: passed.

### Concrete limitations

- The implementation protects against symlink races only for the paths it
  validates before publication; it does not provide a cross-process lock for
  two simultaneous exports to the same container.
- A failed publication after the new generation directory is renamed can leave
  an unreferenced completed generation for manual recovery. The previous
  manifest remains current in that case.
- Hardware/plugin qualification and the separate real-VST workflow are not
  changed by this task.

## Task 02/35 — unify musical time and correct non-quarter-note meters

Status: Done; [PR #16](https://github.com/SeucheAchat9115/Prism/pull/16) is open and
hosted CI is pending.

Implementation branch: `task-02/unify-musical-time`  
Implementation commit: `5b2629f4d855ca5c7ae9470fdf722b6d8be2545c`

### Completed scope

- Added `prism.timing` as the shared constant-tempo timing boundary. The
  canonical internal beat is one quarter note, and a written `N/D` meter spans
  `N * 4 / D` quarter notes per bar.
- Project validation, audio arrangement placement, native synth timing, stock
  tempo-synced effects, plugin event scheduling, automation, VST MIDI payloads,
  and MIDI export now use the same timing definition. Absolute bar and
  quarter-note positions become integer sample-frame boundaries only at the
  scheduling boundary; MIDI remains explicitly quantized in ticks.
- Corrected 3/4, 6/8, and 7/8 audio durations and MIDI end ticks while retaining
  ordinary 4/4 timing. Producer-facing `Note` and controller positions are
  documented as quarter-note beats from the clip start.
- Added the explicit `timing_compatibility` mode. `quarter_note_v1` is the
  default; `legacy_numerator_v0` preserves the earlier numerator-as-quarter-
  notes behavior for migration. The mode is never inferred from
  `prism_version`, and the resolved mode and quarter-notes-per-bar value are
  included in project configuration.

### Compatibility decisions

- Existing public `beats_per_bar` and `beat_unit` arguments remain the written
  numerator and denominator. Existing 4/4 projects therefore retain their
  intended timing and serialized configuration schema version.
- Non-4/4 projects authored against the old duration convention can set
  `timing_compatibility="legacy_numerator_v0"` explicitly. Projects moving to
  canonical timing should review explicit note/controller values; compact step
  notation is re-spaced over the canonical clip span automatically. No timing
  convention is guessed from a version label.
- No MIDI import API exists in the current repository; the shared boundary is
  ready for a later import adapter, while this task changes the existing MIDI
  export and VST MIDI adapters only.

### Verification

- `uv run pytest --cov --cov-report=term-missing`: **180 passed, 3 skipped**;
  total coverage **87.87%**. The skips are the existing real-VST qualification
  tests without their hardware/plugin environment.
- `uv run mypy src/prism`: passed.
- `uv run ruff check .`: passed.
- `uv run --extra docs mkdocs build --strict`: passed.
- Focused timing regressions cover 4/4, 3/4, 6/8, and 7/8 audio/MIDI timing,
  quarter-note note placement, all four meters' automation boundaries,
  fractional tempo, long-sequence rounding drift, explicit compatibility, and
  invalid meter/tempo errors.

### Concrete limitations

- The implementation supports the current constant tempo and constant meter
  only. `TimingMap` keeps the conversion seam available for future tempo maps;
  tempo changes are not yet accepted by `Project`.
- MIDI import is not implemented by this task and remains a later roadmap item.
- Hosted CI and the separate real-VST workflow are not yet checked for this
  unpublished branch; hardware/plugin qualification is not represented by the
  local skips.

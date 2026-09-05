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

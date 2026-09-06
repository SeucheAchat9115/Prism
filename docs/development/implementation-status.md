# Implementation status

## September 6, 2026 — agentic roadmap revision

Planning/documentation change only. Tasks A01–A05 are Planned; no new runtime
capability is claimed. Delivery order is 01–14 → A01–A03 → 15–18 → A04–A05 → 19–35.
Original audit IDs and historical test results below are retained. Tasks 17, 18,
22, 25, 32 and 35 now depend explicitly on the relevant agent contracts.
The task suffix /35 in historical entries refers to the original audit plan.


## Task 01/35 — protect source audio and make stem exports recoverable

Status: Done; [PR #13](https://github.com/SeucheAchat9115/Prism/pull/13) merged
September 5, 2026. Historical implementation verification is recorded below.

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

Status: Done; [PR #16](https://github.com/SeucheAchat9115/Prism/pull/16) merged
September 5, 2026. Verification below records the original implementation handoff.

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
- At the original handoff, hosted CI and the separate real-VST workflow had
  not yet been checked. The PR has since merged; local skips do not establish
  hardware/plugin qualification.

## Task 03/35 — make VST instrument configuration explicitly track-owned

Status: Done; [PR #29](https://github.com/SeucheAchat9115/Prism/pull/29) is open.
Done describes implementation completion, not merge state. The final PR head and
hosted check results are recorded below; separate hardware/plugin qualification
remains a separate concern.

Implementation branch: `task-03/track-owned-vst-configuration`  
Implementation commit: `c7ac39d072b0e774a914313b3afc8d7de6f665cd`
The final status-only follow-up is tracked in the PR commit history.

### Completed scope

- MIDI tracks now retain one immutable instrument specification, including the
  complete `VST3` alias, relative state or preset path, and normalized parameter
  map. Later clips may omit `instrument` or repeat an equivalent declaration;
  conflicting aliases, states, presets, or parameter maps fail with an
  actionable `ProjectError` before a render can start.
- Instrument plugins expose a deterministic stable instance ID derived from the
  owning track. Resolved project configuration records that ID and the effective
  relative VST3 specification without machine-specific plugin paths. The
  configuration schema is now version `8`.
- Deliberate `Track.instrument(...)` replacement updates every MIDI clip and
  preserves the track instance ID. Existing automation is rebound by parameter
  name when compatible; replacements that would orphan a lane or exceed a new
  native parameter range are rejected atomically.
- Native instruments retain the existing first-clip syntax and replacement API.
  VST3 patch changes are intentionally not implemented as hidden per-clip
  instances: use automation for timed parameter changes and separate tracks for
  simultaneous patches.
- Added the track-owned VST3 guide section, reference members, and runnable
  tutorial level 22.

### Compatibility decisions

- `Track.midi(..., instrument=None)` keeps the existing default Uniwave behavior
  on a new track and reuses the existing track-owned instrument on later clips.
  Passing `VST3(...)` on the first clip remains the supported explicit syntax.
- `Track.instrument(...)` is the explicit whole-track replacement operation.
  Compatible automation is rebound in the project's lane collection by
  parameter name; callers must re-read that collection after replacement because
  `AutomationLane` remains immutable.
- The separate real-VST workflow and hardware/plugin qualification are unchanged.
  Continuous one-instance arrangement rendering remains task 05.

### Verification

- Focused VST tests: **16 passed** locally, including equal declaration reuse,
  alias/state/preset/parameter conflicts, stable configuration, replacement,
  automation rebinding, and atomic orphan rejection.
- `uv run --extra dev pytest --cov --cov-report=term-missing`: **191 passed, 3 skipped**;
  total coverage **87.91%**. The skips are the existing real-VST qualification
  tests without their plugin environment.
- `uv run --extra dev mypy src/prism`: passed.
- `uv run --extra dev ruff check .`: passed.
- `uv run --extra docs mkdocs build --strict`: passed.
- Hosted PR CI, Documentation, CodeQL, and VST3 integration passed on the
  implementation and final status-only PR heads; the VST3 workflow's Ubuntu and
  Windows real-VST3 jobs passed. Local skips do not establish hardware/plugin
  qualification beyond that hosted workflow.

### Concrete limitations

- A VST3 parameter name not present in the authored parameter map is still
  accepted for automation because the installed plugin is the authority for its
  exposed controls; hardware/plugin inspection remains outside this task.
- The current renderer still creates worker renders per arrangement placement;
  the track-owned identity is groundwork for task 05 and does not claim its
  continuous-instance behavior.

## Task 04/35 — compile arrangement notes and expressive controls once

Status: In progress; PR pending. Done describes implementation completion, not
PR merge state. The task is being verified on branch
`task-04/compiled-arrangement-events`.

### Completed scope

- Added `prism.arrangement.compile_track_events` and
  `Project.compile_track_events`, producing one deterministic per-track stream
  with stable note IDs, absolute quarter-note/sample positions, explicit
  note-on/note-off events, controller points/curves, and concrete repeated or
  section-scoped clip boundaries.
- Shared the compiled stream with native arrangement rendering, the VST3 MIDI
  adapter, and standard MIDI export. The old independent MIDI arrangement
  walker is no longer used for export.
- Defined equal-time ordering as note-off, clip end/start and controller reset,
  authored controller values, then note-on. Same-pitch overlaps keep separate
  stable note identities; an old note-off therefore precedes a same-time
  retrigger without collapsing voices.
- Added explicit `linear` and `hold` curve modes for pitch bend and modulation.
  Native audio evaluates the declared curve directly. MIDI resamples it at no
  more than 24 ticks between authored points/boundaries before applying its
  14-bit pitch-bend or 7-bit modulation quantization.
- Added the declared effective `pitch_bend_range` in semitones. The default
  `2.0` is an explicit migration default; Prism does not claim to configure a
  VST patch's bend range or assume that all patches use the same range.
- Added `Project.controller_boundary` with `reset` (default), `retain`, and
  explicit `legacy` behavior. Reset prevents controller state leaking from a
  bent clip into an unbent following clip; retain and legacy are documented
  compatibility choices. Configuration schema is now version `9`.
- Kept VST placement renders scoped and derived from the shared stream so task
  05 can own the later one-continuous-instance change. Track/clip gain behavior
  remains unchanged for this task.

### Compatibility decisions

- Existing `pitch_bend` values remain musical semitones and existing projects
  default to an effective ±2-semitone range. Authors with another patch range
  must pass `pitch_bend_range` explicitly; this value is not sent as an
  invented RPN or VST-specific range command.
- Existing controller points remain linear by default. `hold` is opt-in per
  controller through `pitch_bend_curve` or `modulation_curve`.
- `controller_boundary="reset"` is the new deterministic default for all
  compiled consumers. `retain` chases the current value into isolated VST
  placement input; `legacy` omits synthetic reset events for migrations that
  require the older MIDI state behavior.
- The public low-level VST MIDI helper still accepts its prior notes/point
  arguments. New render paths pass `CompiledTrackEvents`; the separate
  continuous VST instance optimization remains task 05.

### Verification

- Focused regressions cover stable identities, scoped/repeated placements,
  exact-boundary events, same-pitch note-off-before-retrigger ordering,
  linear/hold sampling, reset/retain policy, declared bend range, native
  bent-then-unbent behavior, and compiled VST MIDI reset input.
- Full required local gates and exact counts will be recorded after the final
  implementation pass. Real-VST qualification remains the separate workflow.

### Concrete limitations

- MIDI remains a quantized representation. The documented 24-tick sampling
  bound and MIDI value resolution are tolerances, not an audible-quality claim.
- A VST3 patch's actual pitch-bend range is external plugin/patch knowledge;
  Prism records and applies the author's declared effective range but cannot
  infer or force a vendor-specific range mechanism.
- VST placement renders still instantiate/process per concrete placement;
  continuous state across the whole track is intentionally task 05.

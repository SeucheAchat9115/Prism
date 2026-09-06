# Implementation status

## September 6, 2026 — agentic roadmap revision

Planning/documentation change only. Tasks A01–A05 are Planned; no new runtime
capability is claimed. Delivery order is 01–14 → A01–A03 → 15–18 → A04–A05 → 19–35.
Original audit IDs and historical test results below are retained. Tasks 17, 18,
22, 25, 32 and 35 now depend explicitly on the relevant agent contracts.
The task suffix /35 in historical entries refers to the original audit plan.


## Task 07/35 — fix native voice lifetime and remove accidental song-length limits

Status: Done; [PR #33](https://github.com/SeucheAchat9115/Prism/pull/33) is open.
Done describes implementation completion, not pull-request merge state.

Implementation branch: `task-07/native-voice-lifetime`  
Implementation commit: `e24842bde50a67fa7c4cb070ac4fc6f8ee952c95`

### Completed scope

- Uniwave release automation is sampled at the note-off frame. The sampled
  value determines the active voice's complete release; later automation does
  not resize that release, while later notes use the updated value.
- Native arrangement rendering keeps the authored clip span separate from the
  absolute compiled event stream and explicit output frame range. A 257-bar
  arrangement is no longer rejected as a 257-bar `NativeSynthSpec` clip.
- Authored clips retain the documented 1–256 bar limit. Explicit native render
  ranges are validated before allocation, including finite automation arrays
  and a resource guard for absurd frame counts.

### Compatibility decisions

- `NativeSynthSpec.bars` remains the authored clip span and continues to reject
  values above 256. Arrangement callers must pass `frame_count` plus absolute
  events rather than putting song length into `bars`.
- A native voice is truncated at the explicit output frame range. Callers must
  request `tail_seconds` when a release should continue after the final
  arrangement bar; no implicit output extension is added.
- Release automation is note-off sampled rather than continuously changing an
  active release. This preserves deterministic allocation and makes a constant
  automated release equivalent to its static envelope.

### Verification

- Focused task-07 checks pass, covering constant automated release, note-off
  increases/decreases, zero release, sustained notes, explicit-range
  truncation, invalid ranges/non-finite automation, 257-bar native melodic and
  drum arrangements, a larger scheduling-only arrangement, and a 257-bar
  external-instrument arrangement.
- `uv run --extra dev pytest --cov --cov-report=term-missing`: **219 passed,
  3 skipped**, total coverage **87.79%**. The skips are the existing real-VST
  qualification tests without their plugin-path environment variables.
- `uv run --extra dev mypy src/prism`: passed; 35 source files checked.
- `uv run --extra dev ruff check .`: passed.
- `uv run --extra docs mkdocs build --strict`: passed in the reconstructed
  checkout; hosted Documentation workflow **#112** also passed on the full
  repository asset set.
- Hosted CI **#145**, VST3 integration **#83**, and CodeQL **#68** passed. The
  separate real-VST workflow remains unchanged; offline tests and mocks do not
  establish third-party/plugin qualification.

### Concrete limitations

- The explicit native frame-range guard is 100,000,000 frames; this is a
  resource-protection limit, not a 256-bar song limit. Larger projects should
  render bounded ranges in a later range-rendering workflow.
- The release policy is sampled at note-off; automation changes after note-off
  intentionally do not affect an already active voice.


## Task 06/35 — preserve sample and audio releases across arrangement boundaries

Status: Done; [PR #32](https://github.com/SeucheAchat9115/Prism/pull/32) is open.
The implementation is on `task-06/preserve-audio-releases`. Done describes
implementation completion, not pull-request merge state.

### Completed scope

- Sample, one-shot audio, looping audio, and native percussion are resolved into
  one absolute `_ScheduledVoice` timeline per non-MIDI track before track,
  bus, send, and master effects run. The schedule includes prepared source,
  frame endpoints, looping, gain, fade-out, and policy metadata so a future
  block renderer can reuse it without a second placement algorithm.
- Natural sample/audio releases continue through placement and section
  boundaries, including a following inactive section, and are retained when
  `tail_seconds` provides output frames. `AudioClip.loop` repeats a source only
  inside one placement; `ClipPlacement.repeat` creates another placement in an
  active section.
- Native percussion now renders its intended synthesized envelope beyond a
  pattern step by default. It is deliberately truncated only by `cut`, or by
  the explicit `legacy` compatibility policy; `choke` ends earlier voices at
  later triggers.
- Track, bus, master, and stem rendering continue to consume the same aligned
  total-frame buffers after scheduling. Fade-out is applied at the actual
  natural or deliberate cut endpoint.

### Compatibility decisions

- New projects default to `audio_release_policy="natural"`. A placement can
  override the project with `release_policy="natural"`, `"cut"`, or
  `"choke"`; `audio_release_policy="legacy"` restores the former
  placement/section boundary behavior and native pattern-step truncation.
- The policy is explicit and serialized in configuration schema 11. Prism does
  not infer compatibility from `prism_version`; projects needing byte-stable
  pre-task-06 output must declare the legacy policy.

### Verification

- Focused render regressions pass for late triggers, inactive-section
  transitions, overlap/choke behavior, one-shots, source looping versus
  placement repeat, trim/fades, percussion envelopes, explicit cuts, and
  aligned master/stems.
- `uv run --extra dev pytest --cov --cov-report=term-missing`: 210 passed,
  3 skipped, coverage 87.77%.
- `uv run --extra dev mypy src/prism`: passed; 35 source files checked.
- `uv run --extra dev ruff check .`: passed.
- `uv run --extra docs mkdocs build --strict`: the local connector-reconstructed
  tree lacked the unchanged binary `docs/assets/prism-logo.jpg`, but the
  published Documentation workflow #108 passed its strict build on the full
  repository tree.
- Published CI workflow #141, VST3 integration workflow #79, and CodeQL
  workflow #64 all passed. The separate real-VST qualification workflow remains
  distinct from offline test mocks.
- The separate real-VST workflow is unchanged; this task does not claim
  third-party/plugin qualification.

### Concrete limitations

- A natural voice cannot be audible beyond the requested output frame count;
  callers must request enough `tail_seconds` for the source or effect to finish.
- `choke` is track-scoped: a later scheduled voice on that track ends an earlier
  choke-policy voice. Cross-track sidechain/choke groups remain future work.


## Task 05/35 — render each VST instrument track through one continuous instance

Status: Done; [PR #31](https://github.com/SeucheAchat9115/Prism/pull/31) is open.
Done describes implementation completion, not pull-request merge state. The
separate hosted checks and real-plugin qualification remain recorded evidence.

Implementation branch: `task-05/continuous-vst-instance`  
Implementation commit: `f2ca3004f9b3be15019dc71724ad6eb94d1b72cd`  
Verification/status commit: `798a7d97e5d42e5204bb3d44ec9ce3920de1b0a9`

### Completed scope

- `_arrange_midi_track()` now sends the complete compiled per-track event stream
  to one isolated VST worker call. Leading silence, section/placement
  boundaries, overlapping notes, retained controllers, global automation, and
  the requested export tail remain in one continuous plugin render.
- The worker still loads state or preset, applies parameter overrides, loads
  automation, and then renders one instrument graph. Track insert effects remain
  after the completed instrument buffer.
- Master and stem export continue to consume the same `_render_buffers()` track
  result within one stem generation, so a VST instrument is not instantiated
  again for the stem master.
- Added focused regressions for long arrangements, monophonic/legato overlap,
  equal-time ordering, leading silence, controller continuity, global
  automation timing, tail frames, worker render-call count, and stem/master
  reuse.

### Compatibility decisions

- VST MIDI clips on one track must use one common `gain_db`. Prism applies that
  value once after the instrument and before track insert effects. It does not
  convert dB to MIDI velocity or multiply a whole track once per placement.
- Independently scaled VST clip gains are rejected even when note intervals look
  separate, because plugin voices and release/internal-effect tails may overlap.
  The migration is to normalize clip gains, normally to `0.0`, then use the new
  explicit `Track.output_gain(...)` shared dB lane or separate tracks.
- `Track.output_gain(...)` is a whole-track post-instrument envelope; it is not
  a voice-level mechanism and cannot reproduce independent overlapping clip
  levels. The resolved project configuration schema is now version `10`.

### Verification

- Focused continuous-VST regressions pass locally, including the compiled stream
  and host automation request checks.
- `uv run --extra dev pytest --cov --cov-report=term-missing`: **202 passed,
  3 skipped**, total coverage **88.32%**. The skips are the existing real-VST
  qualification tests without their plugin-path environment variables.
- `uv run --extra dev mypy src/prism`: passed; 35 source files checked.
- `uv run --extra dev ruff check .`: passed.
- `uv run --extra docs mkdocs build --strict`: passed.
- The separate real-VST workflow remains unchanged; local tests without an
  installed plugin do not establish third-party/plugin qualification.

### Concrete limitations

- A VST's internal voice/effect implementation remains external behavior; Prism
  preserves one continuous instance and rejects unsupported independent clip
  gain semantics but cannot infer a vendor's voice-level gain capability.
- Real Surge XT/plugin qualification remains in the separate VST3 workflow.


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

Status: Done; [PR #30](https://github.com/SeucheAchat9115/Prism/pull/30) is open.
Done describes implementation completion, not PR merge state. The final PR head
and hosted checks remain separate from the implementation decision.

Implementation branch: `task-04/compiled-arrangement-events`
Implementation commit: `2b8909c68924b37a0558c6b64e86e13bb4d9e2b0`

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

- Focused arrangement regressions: **5 passed** in
  `tests/test_arrangement.py`, covering modulation, curves, overlaps, exact
  boundaries, repeated/scoped clips, controller chase/reset, native reset
  behavior, and VST/export expression agreement.
- `uv run --extra dev pytest --cov --cov-report=term-missing`: **196 passed,
  3 skipped**, total coverage **87.82%**. The skips are the existing real-VST
  qualification tests without their plugin environment.
- `uv run --extra dev mypy src/prism`: passed; 35 source files checked.
- `uv run --extra dev ruff check .`: passed.
- `uv run --extra docs mkdocs build --strict`: passed after restoring the
  unchanged `docs/assets/prism-logo.jpg` already present on current `main` in
  the local task-03 seed; that base asset is not part of this PR.
- The separate real-VST workflow remains unchanged and is still the path for
  third-party/plugin qualification.

### Concrete limitations

- MIDI remains a quantized representation. The documented 24-tick sampling
  bound and MIDI value resolution are tolerances, not an audible-quality claim.
- A VST3 patch's actual pitch-bend range is external plugin/patch knowledge;
  Prism records and applies the author's declared effective range but cannot
  infer or force a vendor-specific range mechanism.
- VST placement renders still instantiate/process per concrete placement;
  continuous state across the whole track is intentionally task 05.
- Standard MIDI channel note messages do not carry Prism's stable per-note IDs;
  a receiving device may apply its own same-pitch voice-stealing policy.

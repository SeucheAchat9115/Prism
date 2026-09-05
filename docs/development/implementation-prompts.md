# Implementation prompts

[Ordered task index](implementation-tasks.md)

These 35 prompts turn the September 2026 Prism audit into implementation work. Each fenced block is self-contained: copy the entire block for the next agent. They include the repository, historical audit context, dependencies, implementation scope, acceptance criteria and handoff requirements. The agents do not need this conversation or access to the original report.

Run them in numerical order. Give the next agent the entire numbered block plus the previous agent's branch/commit and handoff. Integrate or explicitly pass forward that completed work before starting the next; do not start every agent from an unchanged main branch. An ordinary task may require several focused commits. Prompt numbers define delivery stages, not estimates of equal effort. Especially for the audio engine and recording work, completion means the acceptance criteria work end to end.

The original audit found working native exports and passing Surge XT smoke tests on Windows/Linux, but did not establish Serum compatibility or live hardware latency. The prompts preserve that distinction and require agents to recheck current code. Fixes that change existing sound/timing need explicit compatibility and migration decisions. Technical API names proposed below are illustrative unless preceding tasks have established them; subsequent agents should reuse the implemented names.

| Prompts | Intended result |
| --- | --- |
| 1–10 | Safe files, correct musical timing/voices, reliable VST instances and stronger plugin verification |
| 11–15 | Clear exports/stems, reproducibility, build/CLI contract and efficient preview preparation |
| 16–18 | Audible playback, Python edit-save-hear, and a visual transport |
| 19–22 | Stateful streaming, native DSP, continuous VST hosting and a live song graph |
| 23–30 | Performance MIDI, richer routing/arrangement, editing, mastering, synthesis and project sharing |
| 31–35 | Recording/takes, listening formats, platform qualification and full production acceptance |

Each agent must use the GitHub connector for remote repository communication and finish by opening or updating a pull request containing its changes, with exact test evidence. Integration into the next task is deliberate; these prompts do not ask agents to publish releases or automatically merge their work. If you only want the first useful live-editing experience, prompts 1–18 reach background-rendered preview; prompts 19–22 add continuous live processing, and 31–32 add recording/takes.

<a id="task-01"></a>

## 01. Protect source audio and make stem exports recoverable

```text
Implementation task 01/35: Protect source audio and make stem exports recoverable

Repository: https://github.com/SeucheAchat9115/Prism
Repository workflow: Use the GitHub connector for all remote repository communication: reading
repository files, branches, pull requests, review feedback and CI results, and publishing commits,
branches and pull requests. Local file editing, builds, tests and local Git operations are allowed;
do not use shell git fetch/pull/push/clone, gh, curl or direct HTTP clients to contact GitHub.
Discover the connector tools available in your session. If connector access is unavailable or an
operation is blocked, preserve the local work and report the exact blocker; do not silently switch
to another remote transport.

Prism is a script-first Python music-production project. Preserve readable Python authoring and a
lightweight headless offline path while extending production and live workflows.
Audit baseline: 434f538242009e373b62da74c5d527b6bd9120eb, 2026-09-05. This is historical evidence,
not the branch to reset to. Work from the latest integrated implementation that contains the
required preceding tasks. Read AGENTS.md and inspect current code before editing; recheck whether an
audited defect is already fixed. Source paths below refer to the baseline and may have moved.
Implement this task completely, with code rather than only a plan or stubs. Preserve unrelated work,
use a dedicated branch/worktree, and make routine design decisions from the repository and these
requirements. Do not implement later tasks opportunistically. If a prerequisite is absent, resolve
its supplied branch/commit or report the precise dependency rather than inventing an incompatible
substitute.

Required preceding tasks: none; begin with the latest repository state. All earlier integrated
changes must remain present.
Where to start: src/prism/render.py: render_stems, _remove_stale_stems;
src/prism/project/builder.py: _output_path, _output_directory; tests/test_render.py.

Context and why: The audited stem exporter could delete sounds/tracks/original-take.wav when
render_stems("sounds") was used. A source named sounds/tracks/01-vocal.wav could also be overwritten
by a generated stem. The parent directory is checked, but individual destinations and broad WAV
cleanup are not protected.

Implement source protection for every resolved output and cleanup candidate, including child
directories and symlinks. Reject destinations that collide with source assets, scripts, states, or
other protected project files. Never classify an unrelated WAV as stale merely because its name is
not in the current export.

Introduce a minimal versioned export-ownership manifest. Only remove files recorded as generated by
the previous successful export, and preserve files the producer modified or added. Build a new
export generation in a staging directory and publish its completion manifest only after every file
succeeds. Choose a recoverable publication method that works on Windows and Linux; do not claim a
multi-file transaction is atomic unless it actually is. Preserve the previous valid generation on
failure and report the completed generation path clearly.

Acceptance: Temporary fixtures reproduce both historical source collisions and now receive safe
errors with unchanged source bytes. Unrelated WAVs survive cleanup. Tests cover rename/removal of an
owned stem, modified generated files, child symlinks escaping the project, failure during a middle
stem write, and successful repeated export. Do not run destructive cases against real producer
recordings. Update the stem tutorial with output-directory ownership semantics.

Verification and handoff: Add focused behavioral/regression tests for the described risks. Run
relevant tests plus the repository's required CI/type/lint/docs gates; at the audit baseline these
include pytest --cov, mypy src/prism, ruff check ., and mkdocs build --strict in the appropriate uv
extras. Preserve the separate real-VST workflow. Do not weaken gates, delete assertions, or equate
mocks with hardware/plugin qualification. Update the guide and runnable tutorial as required by
AGENTS.md. Read and update docs/development/implementation-status.md (create it if absent) with this
task number, completed scope, implemented API/compatibility decisions, verification and concrete
limitations. Use the GitHub connector to publish scoped verified changes on a dedicated branch and
finally open a pull request containing your changes. If an open PR already covers this task, update
that PR instead of creating a duplicate. Target main unless the supplied prerequisite work requires
an explicitly documented stacked PR. Include the task number, problem, implemented behavior,
compatibility decisions, exact verification results and remaining limitations in the PR description.
Check the published diff and CI results; fix failures caused by your changes and report pending or
blocked checks accurately. Return the PR URL, branch, final commit SHA and a concise handoff. A local
commit alone is not the final deliverable. Do not force-push or auto-merge. The next agent must be
able to start from this result.
```

<a id="task-02"></a>

## 02. Unify musical time and correct non-quarter-note meters

```text
Implementation task 02/35: Unify musical time and correct non-quarter-note meters

Repository: https://github.com/SeucheAchat9115/Prism
Repository workflow: Use the GitHub connector for all remote repository communication: reading
repository files, branches, pull requests, review feedback and CI results, and publishing commits,
branches and pull requests. Local file editing, builds, tests and local Git operations are allowed;
do not use shell git fetch/pull/push/clone, gh, curl or direct HTTP clients to contact GitHub.
Discover the connector tools available in your session. If connector access is unavailable or an
operation is blocked, preserve the local work and report the exact blocker; do not silently switch
to another remote transport.

Prism is a script-first Python music-production project. Preserve readable Python authoring and a
lightweight headless offline path while extending production and live workflows.
Audit baseline: 434f538242009e373b62da74c5d527b6bd9120eb, 2026-09-05. This is historical evidence,
not the branch to reset to. Work from the latest integrated implementation that contains the
required preceding tasks. Read AGENTS.md and inspect current code before editing; recheck whether an
audited defect is already fixed. Source paths below refer to the baseline and may have moved.
Implement this task completely, with code rather than only a plan or stubs. Preserve unrelated work,
use a dedicated branch/worktree, and make routine design decisions from the repository and these
requirements. Do not implement later tasks opportunistically. If a prerequisite is absent, resolve
its supplied branch/commit or report the precise dependency rather than inventing an incompatible
substitute.

Required preceding tasks: 1. All earlier integrated changes must remain present.
Where to start: src/prism/project/builder.py: Project.frames_per_bar, validate; src/prism/midi.py;
src/prism/render.py; src/prism/music.py.

Context and why: beat_unit affects MIDI time-signature metadata but not duration or ticks per bar.
One configured 6/8 bar at a quarter-note tempo of 120 BPM currently lasts three seconds instead of
1.5 seconds. Audio, automation, and MIDI need one timing definition before more scheduling features
are added.

Create a small shared timing module used by arrangement placement, validation, MIDI import/export
adapters, plugin event scheduling, and automation. Define the canonical internal beat as one quarter
note. Meter numerator N and denominator D imply N * 4 / D quarter notes per bar. Document how
producer-facing Note positions relate to this definition. If compatibility requires supporting the
earlier convention, expose an explicit versioned compatibility mode; never infer it from an
arbitrary prism_version label.

Convert absolute musical positions to integer sample frames at the boundary instead of repeatedly
accumulating rounded bar durations. Keep MIDI tick quantization explicit and independent from sample
scheduling. Initially support the existing constant tempo and constant meter; design the interface
so later tempo maps can replace the conversion without another coordinate system.

Acceptance: Audio durations, MIDI meter/end ticks, note placement, and automation agree for 4/4,
3/4, 6/8, and 7/8. Include fractional tempos and long sequences that expose accumulated rounding
drift. Existing ordinary 4/4 projects retain their intended timing. Document migration for
non-quarter-note projects and test error messages for invalid meter/tempo input.

Verification and handoff: Add focused behavioral/regression tests for the described risks. Run
relevant tests plus the repository's required CI/type/lint/docs gates; at the audit baseline these
include pytest --cov, mypy src/prism, ruff check ., and mkdocs build --strict in the appropriate uv
extras. Preserve the separate real-VST workflow. Do not weaken gates, delete assertions, or equate
mocks with hardware/plugin qualification. Update the guide and runnable tutorial as required by
AGENTS.md. Read and update docs/development/implementation-status.md (create it if absent) with this
task number, completed scope, implemented API/compatibility decisions, verification and concrete
limitations. Use the GitHub connector to publish scoped verified changes on a dedicated branch and
finally open a pull request containing your changes. If an open PR already covers this task, update
that PR instead of creating a duplicate. Target main unless the supplied prerequisite work requires
an explicitly documented stacked PR. Include the task number, problem, implemented behavior,
compatibility decisions, exact verification results and remaining limitations in the PR description.
Check the published diff and CI results; fix failures caused by your changes and report pending or
blocked checks accurately. Return the PR URL, branch, final commit SHA and a concise handoff. A local
commit alone is not the final deliverable. Do not force-push or auto-merge. The next agent must be
able to start from this result.
```

<a id="task-03"></a>

## 03. Make VST instrument configuration explicitly track-owned

```text
Implementation task 03/35: Make VST instrument configuration explicitly track-owned

Repository: https://github.com/SeucheAchat9115/Prism
Repository workflow: Use the GitHub connector for all remote repository communication: reading
repository files, branches, pull requests, review feedback and CI results, and publishing commits,
branches and pull requests. Local file editing, builds, tests and local Git operations are allowed;
do not use shell git fetch/pull/push/clone, gh, curl or direct HTTP clients to contact GitHub.
Discover the connector tools available in your session. If connector access is unavailable or an
operation is blocked, preserve the local work and report the exact blocker; do not silently switch
to another remote transport.

Prism is a script-first Python music-production project. Preserve readable Python authoring and a
lightweight headless offline path while extending production and live workflows.
Audit baseline: 434f538242009e373b62da74c5d527b6bd9120eb, 2026-09-05. This is historical evidence,
not the branch to reset to. Work from the latest integrated implementation that contains the
required preceding tasks. Read AGENTS.md and inspect current code before editing; recheck whether an
audited defect is already fixed. Source paths below refer to the baseline and may have moved.
Implement this task completely, with code rather than only a plan or stubs. Preserve unrelated work,
use a dedicated branch/worktree, and make routine design decisions from the repository and these
requirements. Do not implement later tasks opportunistically. If a prerequisite is absent, resolve
its supplied branch/commit or report the precise dependency rather than inventing an incompatible
substitute.

Required preceding tasks: 2. All earlier integrated changes must remain present.
Where to start: src/prism/project/builder.py: Track.midi, _add_clip, _set_melodic_instrument;
src/prism/vst.py: VST3; tests/test_vst.py.

Context and why: Two clips on one track can specify the same VST alias with parameters Cutoff=0.2
and Cutoff=0.8, yet both use the first specification. Later state/preset/parameter declarations are
silently discarded. Producers must be able to trust the settings in their script.

Store the complete instrument specification once per track, with a stable instance identity.
Additional clips may reuse it, but incompatible aliases, states, presets, or parameter maps must
produce an actionable validation error. Keep supported first-clip instrument syntax convenient. A
deliberate track.instrument(...) replacement should update all dependent clips consistently and
either remap compatible automation or reject orphaned automation clearly.

Do not implement per-clip VST preset switching by secretly creating extra instances. Explain that
timed parameter changes use automation and simultaneously different patches use explicitly separate
tracks/instances. Reuse existing immutable configuration objects where possible and ensure resolved
configuration includes the effective specification without machine-specific absolute paths.

Acceptance: Conflicting 0.2/0.8 declarations fail before rendering, identical declarations are
accepted, and state/preset conflicts are covered. Replacing the instrument produces the requested
patch throughout the track, with a clear automation policy. Native and external instruments retain a
coherent public interface. Add a tutorial showing a reusable track-owned VST configuration.

Verification and handoff: Add focused behavioral/regression tests for the described risks. Run
relevant tests plus the repository's required CI/type/lint/docs gates; at the audit baseline these
include pytest --cov, mypy src/prism, ruff check ., and mkdocs build --strict in the appropriate uv
extras. Preserve the separate real-VST workflow. Do not weaken gates, delete assertions, or equate
mocks with hardware/plugin qualification. Update the guide and runnable tutorial as required by
AGENTS.md. Read and update docs/development/implementation-status.md (create it if absent) with this
task number, completed scope, implemented API/compatibility decisions, verification and concrete
limitations. Use the GitHub connector to publish scoped verified changes on a dedicated branch and
finally open a pull request containing your changes. If an open PR already covers this task, update
that PR instead of creating a duplicate. Target main unless the supplied prerequisite work requires
an explicitly documented stacked PR. Include the task number, problem, implemented behavior,
compatibility decisions, exact verification results and remaining limitations in the PR description.
Check the published diff and CI results; fix failures caused by your changes and report pending or
blocked checks accurately. Return the PR URL, branch, final commit SHA and a concise handoff. A local
commit alone is not the final deliverable. Do not force-push or auto-merge. The next agent must be
able to start from this result.
```

<a id="task-04"></a>

## 04. Compile arrangement notes and expressive controls once

```text
Implementation task 04/35: Compile arrangement notes and expressive controls once

Repository: https://github.com/SeucheAchat9115/Prism
Repository workflow: Use the GitHub connector for all remote repository communication: reading
repository files, branches, pull requests, review feedback and CI results, and publishing commits,
branches and pull requests. Local file editing, builds, tests and local Git operations are allowed;
do not use shell git fetch/pull/push/clone, gh, curl or direct HTTP clients to contact GitHub.
Discover the connector tools available in your session. If connector access is unavailable or an
operation is blocked, preserve the local work and report the exact blocker; do not silently switch
to another remote transport.

Prism is a script-first Python music-production project. Preserve readable Python authoring and a
lightweight headless offline path while extending production and live workflows.
Audit baseline: 434f538242009e373b62da74c5d527b6bd9120eb, 2026-09-05. This is historical evidence,
not the branch to reset to. Work from the latest integrated implementation that contains the
required preceding tasks. Read AGENTS.md and inspect current code before editing; recheck whether an
audited defect is already fixed. Source paths below refer to the baseline and may have moved.
Implement this task completely, with code rather than only a plan or stubs. Preserve unrelated work,
use a dedicated branch/worktree, and make routine design decisions from the repository and these
requirements. Do not implement later tasks opportunistically. If a prerequisite is absent, resolve
its supplied branch/commit or report the precise dependency rather than inventing an incompatible
substitute.

Required preceding tasks: 2, 3. All earlier integrated changes must remain present.
Where to start: src/prism/render.py: _arrange_midi_track; src/prism/midi.py:
_midi_expression_events; src/prism/vst_host.py: _midi_file; src/prism/synthesis/engine.py;
src/prism/stock_plugins/uniwave.py.

Context and why: Native synthesis interpolates control points, but MIDI serializers emit isolated
controller events. Exported pitch bend can remain active into a following clip that has no bend
data. Separate arrangement walkers also make MIDI and rendered audio diverge.

Introduce a compiled per-track musical event stream containing stable note identities, absolute
musical/sample positions, note-on/off, controller events or curves, and explicit clip boundaries.
Use it in the native renderer, VST MIDI adapter, and MIDI exporter. Define note-off ordering at
equal timestamps, overlap handling for the same pitch, and repeated/scoped clip behavior.

Make hold versus interpolated controller curves explicit. Define whether clip boundaries retain or
reset controller values and preserve an explicit legacy mode when required. Resample continuous
curves to MIDI with documented timing/value tolerances instead of pretending a few MIDI events are a
continuous ramp. Represent pitch bend in musical units plus a declared effective bend range; do not
assume every VST patch uses +/-2 semitones or accepts the same range-setting mechanism. Provide
controller chase/reset helpers that future transport code can reuse.

Acceptance: A bent first clip followed by an unbent clip has the same intended pitch in native
audio, VST event input, and exported MIDI. Test modulation, overlapping notes, repeated clips,
events exactly on boundaries, and note-off before retrigger. Numeric/event tests should establish
agreement; use real-plugin tests where available without treating native and third-party timbres as
equal.

Verification and handoff: Add focused behavioral/regression tests for the described risks. Run
relevant tests plus the repository's required CI/type/lint/docs gates; at the audit baseline these
include pytest --cov, mypy src/prism, ruff check ., and mkdocs build --strict in the appropriate uv
extras. Preserve the separate real-VST workflow. Do not weaken gates, delete assertions, or equate
mocks with hardware/plugin qualification. Update the guide and runnable tutorial as required by
AGENTS.md. Read and update docs/development/implementation-status.md (create it if absent) with this
task number, completed scope, implemented API/compatibility decisions, verification and concrete
limitations. Use the GitHub connector to publish scoped verified changes on a dedicated branch and
finally open a pull request containing your changes. If an open PR already covers this task, update
that PR instead of creating a duplicate. Target main unless the supplied prerequisite work requires
an explicitly documented stacked PR. Include the task number, problem, implemented behavior,
compatibility decisions, exact verification results and remaining limitations in the PR description.
Check the published diff and CI results; fix failures caused by your changes and report pending or
blocked checks accurately. Return the PR URL, branch, final commit SHA and a concise handoff. A local
commit alone is not the final deliverable. Do not force-push or auto-merge. The next agent must be
able to start from this result.
```

<a id="task-05"></a>

## 05. Render each VST instrument track through one continuous instance

```text
Implementation task 05/35: Render each VST instrument track through one continuous instance

Repository: https://github.com/SeucheAchat9115/Prism
Repository workflow: Use the GitHub connector for all remote repository communication: reading
repository files, branches, pull requests, review feedback and CI results, and publishing commits,
branches and pull requests. Local file editing, builds, tests and local Git operations are allowed;
do not use shell git fetch/pull/push/clone, gh, curl or direct HTTP clients to contact GitHub.
Discover the connector tools available in your session. If connector access is unavailable or an
operation is blocked, preserve the local work and report the exact blocker; do not silently switch
to another remote transport.

Prism is a script-first Python music-production project. Preserve readable Python authoring and a
lightweight headless offline path while extending production and live workflows.
Audit baseline: 434f538242009e373b62da74c5d527b6bd9120eb, 2026-09-05. This is historical evidence,
not the branch to reset to. Work from the latest integrated implementation that contains the
required preceding tasks. Read AGENTS.md and inspect current code before editing; recheck whether an
audited defect is already fixed. Source paths below refer to the baseline and may have moved.
Implement this task completely, with code rather than only a plan or stubs. Preserve unrelated work,
use a dedicated branch/worktree, and make routine design decisions from the repository and these
requirements. Do not implement later tasks opportunistically. If a prerequisite is absent, resolve
its supplied branch/commit or report the precise dependency rather than inventing an incompatible
substitute.

Required preceding tasks: 3, 4. All earlier integrated changes must remain present.
Where to start: src/prism/render.py: _arrange_midi_track; src/prism/vst_host.py:
render_vst3_instrument; src/prism/vst_worker.py.

Context and why: The current section/placement loop creates independent full-song VST renders and
sums them. Two sections therefore load the instrument twice. Separate instances change monophonic
voice allocation, legato, internal effects, and nonlinear behavior, besides wasting time.

Send the compiled event stream for the complete track to one worker and one VST instance per offline
render. Process leading silence, all sections, and the tail through that instance continuously.
Track insert effects remain after the instrument. Retain process isolation and state -> parameter
override -> automation loading order.

Resolve clip loudness semantics explicitly: a shared polyphonic VST cannot generally apply
independent post-instrument gains to overlapping voices. Require compatible VST clip-gain
declarations or an explicit shared output-gain lane. Reject independently scaled overlaps, including
release/internal-effect tails, unless a correct voice-level mechanism exists. Non-overlapping note
intervals alone do not prove plugin voices or tails are independent. Provide a clear migration from
differing clip gains; do not silently turn decibels into MIDI velocity or multiply the whole track
once per clip.

Acceptance: Multiple placements use one instrument instantiation and one continuous track render.
Add a monophonic/legato fixture spanning clip and section boundaries, overlapping notes, internal
effect tails, and controller continuity. Confirm global automation timing and leading silence. Test
one long arrangement and inspect render-call count without relying on elapsed time alone.
Demonstrate that master and stem export share the same rendered instance within an export
generation.

Verification and handoff: Add focused behavioral/regression tests for the described risks. Run
relevant tests plus the repository's required CI/type/lint/docs gates; at the audit baseline these
include pytest --cov, mypy src/prism, ruff check ., and mkdocs build --strict in the appropriate uv
extras. Preserve the separate real-VST workflow. Do not weaken gates, delete assertions, or equate
mocks with hardware/plugin qualification. Update the guide and runnable tutorial as required by
AGENTS.md. Read and update docs/development/implementation-status.md (create it if absent) with this
task number, completed scope, implemented API/compatibility decisions, verification and concrete
limitations. Use the GitHub connector to publish scoped verified changes on a dedicated branch and
finally open a pull request containing your changes. If an open PR already covers this task, update
that PR instead of creating a duplicate. Target main unless the supplied prerequisite work requires
an explicitly documented stacked PR. Include the task number, problem, implemented behavior,
compatibility decisions, exact verification results and remaining limitations in the PR description.
Check the published diff and CI results; fix failures caused by your changes and report pending or
blocked checks accurately. Return the PR URL, branch, final commit SHA and a concise handoff. A local
commit alone is not the final deliverable. Do not force-push or auto-merge. The next agent must be
able to start from this result.
```

<a id="task-06"></a>

## 06. Preserve sample and audio releases across arrangement boundaries

```text
Implementation task 06/35: Preserve sample and audio releases across arrangement boundaries

Repository: https://github.com/SeucheAchat9115/Prism
Repository workflow: Use the GitHub connector for all remote repository communication: reading
repository files, branches, pull requests, review feedback and CI results, and publishing commits,
branches and pull requests. Local file editing, builds, tests and local Git operations are allowed;
do not use shell git fetch/pull/push/clone, gh, curl or direct HTTP clients to contact GitHub.
Discover the connector tools available in your session. If connector access is unavailable or an
operation is blocked, preserve the local work and report the exact blocker; do not silently switch
to another remote transport.

Prism is a script-first Python music-production project. Preserve readable Python authoring and a
lightweight headless offline path while extending production and live workflows.
Audit baseline: 434f538242009e373b62da74c5d527b6bd9120eb, 2026-09-05. This is historical evidence,
not the branch to reset to. Work from the latest integrated implementation that contains the
required preceding tasks. Read AGENTS.md and inspect current code before editing; recheck whether an
audited defect is already fixed. Source paths below refer to the baseline and may have moved.
Implement this task completely, with code rather than only a plan or stubs. Preserve unrelated work,
use a dedicated branch/worktree, and make routine design decisions from the repository and these
requirements. Do not implement later tasks opportunistically. If a prerequisite is absent, resolve
its supplied branch/commit or report the precise dependency rather than inventing an incompatible
substitute.

Required preceding tasks: 2, 4. All earlier integrated changes must remain present.
Where to start: src/prism/render.py: _clip_buffer, _render_buffers, _prepare_audio;
src/prism/project/builder.py: SampleClip, AudioClip, DrumClip; tests/test_render.py.

Context and why: Samples are fitted into clip buffers before arrangement and export-tail handling. A
one-second sample triggered at 1.5 seconds in a two-second arrangement loses its last half-second
even when tail_seconds=1. Added tail time cannot restore discarded source audio.

Schedule sample/audio voices against the arrangement timeline and total output duration. Preserve
the prepared source after a trigger until its actual endpoint, unless an explicit cut/choke policy
ends it. Distinguish source looping from repeating a clip placement: loop=False and repeat=False
must be understandable and documented. Define behavior for a track becoming inactive in the next
section and for deliberate arrangement cuts. Apply track/bus/master effects after correctly
scheduled source voices.

Add an explicit policy for natural tails versus cut-at-boundary behavior, with compatibility
handling for existing projects. Ensure fade-out is applied at the actual intended endpoint. Review
native percussion truncation at pattern steps and either preserve its intended synthesized envelope
or make choking explicit.

Acceptance: The historical late-trigger fixture retains its audible final half-second with
sufficient export tail. Test overlap between repeated hits, transition to an inactive section,
one-shot audio, source looping, trim/fades, and explicit choke/cut modes. Master and all stems
remain frame-aligned. Future block rendering must be able to reuse the voice schedule rather than
introducing another placement algorithm.

Verification and handoff: Add focused behavioral/regression tests for the described risks. Run
relevant tests plus the repository's required CI/type/lint/docs gates; at the audit baseline these
include pytest --cov, mypy src/prism, ruff check ., and mkdocs build --strict in the appropriate uv
extras. Preserve the separate real-VST workflow. Do not weaken gates, delete assertions, or equate
mocks with hardware/plugin qualification. Update the guide and runnable tutorial as required by
AGENTS.md. Read and update docs/development/implementation-status.md (create it if absent) with this
task number, completed scope, implemented API/compatibility decisions, verification and concrete
limitations. Use the GitHub connector to publish scoped verified changes on a dedicated branch and
finally open a pull request containing your changes. If an open PR already covers this task, update
that PR instead of creating a duplicate. Target main unless the supplied prerequisite work requires
an explicitly documented stacked PR. Include the task number, problem, implemented behavior,
compatibility decisions, exact verification results and remaining limitations in the PR description.
Check the published diff and CI results; fix failures caused by your changes and report pending or
blocked checks accurately. Return the PR URL, branch, final commit SHA and a concise handoff. A local
commit alone is not the final deliverable. Do not force-push or auto-merge. The next agent must be
able to start from this result.
```

<a id="task-07"></a>

## 07. Fix native voice lifetime and remove accidental song-length limits

```text
Implementation task 07/35: Fix native voice lifetime and remove accidental song-length limits

Repository: https://github.com/SeucheAchat9115/Prism
Repository workflow: Use the GitHub connector for all remote repository communication: reading
repository files, branches, pull requests, review feedback and CI results, and publishing commits,
branches and pull requests. Local file editing, builds, tests and local Git operations are allowed;
do not use shell git fetch/pull/push/clone, gh, curl or direct HTTP clients to contact GitHub.
Discover the connector tools available in your session. If connector access is unavailable or an
operation is blocked, preserve the local work and report the exact blocker; do not silently switch
to another remote transport.

Prism is a script-first Python music-production project. Preserve readable Python authoring and a
lightweight headless offline path while extending production and live workflows.
Audit baseline: 434f538242009e373b62da74c5d527b6bd9120eb, 2026-09-05. This is historical evidence,
not the branch to reset to. Work from the latest integrated implementation that contains the
required preceding tasks. Read AGENTS.md and inspect current code before editing; recheck whether an
audited defect is already fixed. Source paths below refer to the baseline and may have moved.
Implement this task completely, with code rather than only a plan or stubs. Preserve unrelated work,
use a dedicated branch/worktree, and make routine design decisions from the repository and these
requirements. Do not implement later tasks opportunistically. If a prerequisite is absent, resolve
its supplied branch/commit or report the precise dependency rather than inventing an incompatible
substitute.

Required preceding tasks: 2, 4, 6. All earlier integrated changes must remain present.
Where to start: src/prism/stock_plugins/uniwave.py: render, _envelope; src/prism/synthesis/types.py:
NativeSynthSpec; src/prism/synthesis/engine.py; src/prism/render.py.

Context and why: Uniwave allocates a voice using static release_ms even when automation increases
release. A 100 ms release automated to 1000 ms was silent after half a second while the directly
configured one-second release remained audible. Separately, a 256-bar section plus a one-bar ending
passes Project.validate() and fails in NativeSynthSpec because the entire arrangement is treated as
a clip.

Separate arrangement duration, clip validation limits, and individual voice lifetime. Size offline
voice output from the effective envelope or retain a voice until it actually finishes. Specify
whether release automation is sampled at note-off or continuously changes an active release, and
implement that rule consistently. Do not allocate absurd buffers for invalid inputs; validate limits
and non-finite values early.

Let long arrangements render using explicit frame/event ranges. Retain sensible limits on authored
clip inputs only where justified and documented. Remove the accidental propagation of total song
bars into a clip-only validator.

Acceptance: Constant automated release matches the equivalent static envelope within the documented
tolerance. Test release increases/decreases near note-off, zero release, sustained notes, and
render-tail truncation policy. A 257-bar native arrangement validates and renders; add a larger
scheduling test without expensive minutes of DSP. Validate native drum, melodic, and
external-instrument paths separately.

Verification and handoff: Add focused behavioral/regression tests for the described risks. Run
relevant tests plus the repository's required CI/type/lint/docs gates; at the audit baseline these
include pytest --cov, mypy src/prism, ruff check ., and mkdocs build --strict in the appropriate uv
extras. Preserve the separate real-VST workflow. Do not weaken gates, delete assertions, or equate
mocks with hardware/plugin qualification. Update the guide and runnable tutorial as required by
AGENTS.md. Read and update docs/development/implementation-status.md (create it if absent) with this
task number, completed scope, implemented API/compatibility decisions, verification and concrete
limitations. Use the GitHub connector to publish scoped verified changes on a dedicated branch and
finally open a pull request containing your changes. If an open PR already covers this task, update
that PR instead of creating a duplicate. Target main unless the supplied prerequisite work requires
an explicitly documented stacked PR. Include the task number, problem, implemented behavior,
compatibility decisions, exact verification results and remaining limitations in the PR description.
Check the published diff and CI results; fix failures caused by your changes and report pending or
blocked checks accurately. Return the PR URL, branch, final commit SHA and a concise handoff. A local
commit alone is not the final deliverable. Do not force-push or auto-merge. The next agent must be
able to start from this result.
```

<a id="task-08"></a>

## 08. Define parameter automation boundaries and canonical targets

```text
Implementation task 08/35: Define parameter automation boundaries and canonical targets

Repository: https://github.com/SeucheAchat9115/Prism
Repository workflow: Use the GitHub connector for all remote repository communication: reading
repository files, branches, pull requests, review feedback and CI results, and publishing commits,
branches and pull requests. Local file editing, builds, tests and local Git operations are allowed;
do not use shell git fetch/pull/push/clone, gh, curl or direct HTTP clients to contact GitHub.
Discover the connector tools available in your session. If connector access is unavailable or an
operation is blocked, preserve the local work and report the exact blocker; do not silently switch
to another remote transport.

Prism is a script-first Python music-production project. Preserve readable Python authoring and a
lightweight headless offline path while extending production and live workflows.
Audit baseline: 434f538242009e373b62da74c5d527b6bd9120eb, 2026-09-05. This is historical evidence,
not the branch to reset to. Work from the latest integrated implementation that contains the
required preceding tasks. Read AGENTS.md and inspect current code before editing; recheck whether an
audited defect is already fixed. Source paths below refer to the baseline and may have moved.
Implement this task completely, with code rather than only a plan or stubs. Preserve unrelated work,
use a dedicated branch/worktree, and make routine design decisions from the repository and these
requirements. Do not implement later tasks opportunistically. If a prerequisite is absent, resolve
its supplied branch/commit or report the precise dependency rather than inventing an incompatible
substitute.

Required preceding tasks: 2, 3, 4, 7. All earlier integrated changes must remain present.
Where to start: src/prism/effects.py: parameter_values; src/prism/plugins.py: automation_points;
src/prism/project/builder.py: automation; src/prism/vst_worker.py: parameter resolution.

Context and why: A gain effect configured at -12 dB with its first automation point at bar 0.5/value
0 dB already uses 0 dB at bar zero. Names and indexed VST selectors may also refer to the same
physical parameter without a shared identity. These ambiguities will become harder to fix after
adding live controls.

Define a documented pre-first-point policy. Prefer an explicit initial/base-value hold until
automation begins, while preserving older behavior through a declared compatibility policy rather
than silently changing existing songs. Define last-value, hold, linear, and boundary semantics in
the compiled parameter-envelope representation. Keep smoothing for discontinuous live controls
distinct from an authored hold curve.

Canonicalize VST parameter targets against inspected metadata so name and index aliases cannot
produce competing lanes for one parameter. Validate duplicate/unknown/ambiguous selectors before
expensive audio work. Keep named selectors readable, but store stable instance and parameter
identities in the compiled model. Avoid turning every constant parameter into a full-song array.

Acceptance: Test before/at/after first and last points, simultaneous point boundaries,
renamed/indexed selectors, duplicate physical targets, and replaced plugin instances. Native and VST
adapters consume equivalent timing. Document existing-project migration and provide a simple
volume/filter automation example that can run as a tutorial test.

Verification and handoff: Add focused behavioral/regression tests for the described risks. Run
relevant tests plus the repository's required CI/type/lint/docs gates; at the audit baseline these
include pytest --cov, mypy src/prism, ruff check ., and mkdocs build --strict in the appropriate uv
extras. Preserve the separate real-VST workflow. Do not weaken gates, delete assertions, or equate
mocks with hardware/plugin qualification. Update the guide and runnable tutorial as required by
AGENTS.md. Read and update docs/development/implementation-status.md (create it if absent) with this
task number, completed scope, implemented API/compatibility decisions, verification and concrete
limitations. Use the GitHub connector to publish scoped verified changes on a dedicated branch and
finally open a pull request containing your changes. If an open PR already covers this task, update
that PR instead of creating a duplicate. Target main unless the supplied prerequisite work requires
an explicitly documented stacked PR. Include the task number, problem, implemented behavior,
compatibility decisions, exact verification results and remaining limitations in the PR description.
Check the published diff and CI results; fix failures caused by your changes and report pending or
blocked checks accurately. Return the PR URL, branch, final commit SHA and a concise handoff. A local
commit alone is not the final deliverable. Do not force-push or auto-merge. The next agent must be
able to start from this result.
```

<a id="task-09"></a>

## 09. Harden VST workers, cancellation, diagnostics, and state saving

```text
Implementation task 09/35: Harden VST workers, cancellation, diagnostics, and state saving

Repository: https://github.com/SeucheAchat9115/Prism
Repository workflow: Use the GitHub connector for all remote repository communication: reading
repository files, branches, pull requests, review feedback and CI results, and publishing commits,
branches and pull requests. Local file editing, builds, tests and local Git operations are allowed;
do not use shell git fetch/pull/push/clone, gh, curl or direct HTTP clients to contact GitHub.
Discover the connector tools available in your session. If connector access is unavailable or an
operation is blocked, preserve the local work and report the exact blocker; do not silently switch
to another remote transport.

Prism is a script-first Python music-production project. Preserve readable Python authoring and a
lightweight headless offline path while extending production and live workflows.
Audit baseline: 434f538242009e373b62da74c5d527b6bd9120eb, 2026-09-05. This is historical evidence,
not the branch to reset to. Work from the latest integrated implementation that contains the
required preceding tasks. Read AGENTS.md and inspect current code before editing; recheck whether an
audited defect is already fixed. Source paths below refer to the baseline and may have moved.
Implement this task completely, with code rather than only a plan or stubs. Preserve unrelated work,
use a dedicated branch/worktree, and make routine design decisions from the repository and these
requirements. Do not implement later tasks opportunistically. If a prerequisite is absent, resolve
its supplied branch/commit or report the precise dependency rather than inventing an incompatible
substitute.

Required preceding tasks: 3, 5, 8. All earlier integrated changes must remain present.
Where to start: src/prism/vst_host.py: _run_worker, edit_vst3; src/prism/vst_worker.py;
src/prism/vst.py; tests/test_vst_worker.py.

Context and why: Process isolation catches plugin crashes, but subprocess.run() has no deadline. A
hanging plugin can leave rendering blocked indefinitely. Editor saves write directly over the state
file. Render block size is hard-coded to 512 samples.

Add action-aware deadlines and cancellation for inspection, loading, and offline rendering.
Interactive editing needs its own explicit close/cancel policy rather than a short rendering
timeout. On cancellation terminate the worker process tree, collect bounded diagnostic output, and
identify the plugin alias, track, operation, and last successful stage. Keep normal errors readable
for non-developers and provide structured diagnostic details for developers.

Save plugin state to a temporary file in the same project area, check the backend result and
readable output, then replace the previous state. Keep a usable previous state on failure. Expose
validated render block size through backend configuration and record it in results/manifests.
Separate backend capability information from assumptions about plugin support.

Acceptance: Use controlled workers that hang, crash, return malformed/non-finite/incorrect-shape
audio, flood logs, and fail mid-save. Tests establish prompt cancellation and cleanup without orphan
processes, preserving the previous state. Ordinary success, missing host dependencies, and
user-closing the editor still work. Do not claim a fake worker establishes actual plugin
compatibility.

Verification and handoff: Add focused behavioral/regression tests for the described risks. Run
relevant tests plus the repository's required CI/type/lint/docs gates; at the audit baseline these
include pytest --cov, mypy src/prism, ruff check ., and mkdocs build --strict in the appropriate uv
extras. Preserve the separate real-VST workflow. Do not weaken gates, delete assertions, or equate
mocks with hardware/plugin qualification. Update the guide and runnable tutorial as required by
AGENTS.md. Read and update docs/development/implementation-status.md (create it if absent) with this
task number, completed scope, implemented API/compatibility decisions, verification and concrete
limitations. Use the GitHub connector to publish scoped verified changes on a dedicated branch and
finally open a pull request containing your changes. If an open PR already covers this task, update
that PR instead of creating a duplicate. Target main unless the supplied prerequisite work requires
an explicitly documented stacked PR. Include the task number, problem, implemented behavior,
compatibility decisions, exact verification results and remaining limitations in the PR description.
Check the published diff and CI results; fix failures caused by your changes and report pending or
blocked checks accurately. Return the PR URL, branch, final commit SHA and a concise handoff. A local
commit alone is not the final deliverable. Do not force-push or auto-merge. The next agent must be
able to start from this result.
```

<a id="task-10"></a>

## 10. Strengthen real VST tests and verify latency compensation

```text
Implementation task 10/35: Strengthen real VST tests and verify latency compensation

Repository: https://github.com/SeucheAchat9115/Prism
Repository workflow: Use the GitHub connector for all remote repository communication: reading
repository files, branches, pull requests, review feedback and CI results, and publishing commits,
branches and pull requests. Local file editing, builds, tests and local Git operations are allowed;
do not use shell git fetch/pull/push/clone, gh, curl or direct HTTP clients to contact GitHub.
Discover the connector tools available in your session. If connector access is unavailable or an
operation is blocked, preserve the local work and report the exact blocker; do not silently switch
to another remote transport.

Prism is a script-first Python music-production project. Preserve readable Python authoring and a
lightweight headless offline path while extending production and live workflows.
Audit baseline: 434f538242009e373b62da74c5d527b6bd9120eb, 2026-09-05. This is historical evidence,
not the branch to reset to. Work from the latest integrated implementation that contains the
required preceding tasks. Read AGENTS.md and inspect current code before editing; recheck whether an
audited defect is already fixed. Source paths below refer to the baseline and may have moved.
Implement this task completely, with code rather than only a plan or stubs. Preserve unrelated work,
use a dedicated branch/worktree, and make routine design decisions from the repository and these
requirements. Do not implement later tasks opportunistically. If a prerequisite is absent, resolve
its supplied branch/commit or report the precise dependency rather than inventing an incompatible
substitute.

Required preceding tasks: 4, 5, 9. All earlier integrated changes must remain present.
Where to start: .github/workflows/vst-ci.yml; tests/test_real_vst.py; tests/test_vst_worker.py;
src/prism/vst_worker.py; src/prism/vst_host.py.

Context and why: Main at the audit baseline had three passing Surge XT tests on Windows and Linux,
including a non-silent WAV. This is useful but does not establish correct effect processing or
latency. The real effect assertions can pass for unchanged input, and a constant fake output cannot
test temporal alignment.

Add a small controlled VST3 fixture instrument/effect, built reproducibly from a pinned supported
framework/SDK, for deterministic gain, delay, MIDI response, state round trips, and channel-layout
cases. Inspect licensing/build requirements from primary upstream sources before choosing
dependencies. Keep the existing Surge workflow separate from the portable suite and pin downloaded
plugin checksums as well as versions.

Verify the actual pinned host's latency behavior to avoid double compensation. Query/reconcile
latency after state/parameters and graph preparation; define behavior when it changes. Test impulses
and known events through nonzero latency, serial effects, parallel dry/wet paths, and automation.
Fix demonstrated alignment defects in the host adapter. Strengthen instrument assertions with onset,
RMS, audible duration and tails, and effect assertions with a configured measurable change from
bypass.

Acceptance: Real fixture and Surge tests run on Windows and Linux; portable tests still run without
installed plugins. Save small WAV/JSON diagnostics on audio-test failure. Add state/preset/parameter
precedence and cancellation cases. Report exactly which plugin/platform combinations were exercised.
Do not use Serum credentials or claim commercial-plugin coverage without a legitimately installed
test environment.

Verification and handoff: Add focused behavioral/regression tests for the described risks. Run
relevant tests plus the repository's required CI/type/lint/docs gates; at the audit baseline these
include pytest --cov, mypy src/prism, ruff check ., and mkdocs build --strict in the appropriate uv
extras. Preserve the separate real-VST workflow. Do not weaken gates, delete assertions, or equate
mocks with hardware/plugin qualification. Update the guide and runnable tutorial as required by
AGENTS.md. Read and update docs/development/implementation-status.md (create it if absent) with this
task number, completed scope, implemented API/compatibility decisions, verification and concrete
limitations. Use the GitHub connector to publish scoped verified changes on a dedicated branch and
finally open a pull request containing your changes. If an open PR already covers this task, update
that PR instead of creating a duplicate. Target main unless the supplied prerequisite work requires
an explicitly documented stacked PR. Include the task number, problem, implemented behavior,
compatibility decisions, exact verification results and remaining limitations in the PR description.
Check the published diff and CI results; fix failures caused by your changes and report pending or
blocked checks accurately. Return the PR URL, branch, final commit SHA and a concise handoff. A local
commit alone is not the final deliverable. Do not force-push or auto-merge. The next agent must be
able to start from this result.
```

<a id="task-11"></a>

## 11. Add explicit export profiles, clipping policy, and dither

```text
Implementation task 11/35: Add explicit export profiles, clipping policy, and dither

Repository: https://github.com/SeucheAchat9115/Prism
Repository workflow: Use the GitHub connector for all remote repository communication: reading
repository files, branches, pull requests, review feedback and CI results, and publishing commits,
branches and pull requests. Local file editing, builds, tests and local Git operations are allowed;
do not use shell git fetch/pull/push/clone, gh, curl or direct HTTP clients to contact GitHub.
Discover the connector tools available in your session. If connector access is unavailable or an
operation is blocked, preserve the local work and report the exact blocker; do not silently switch
to another remote transport.

Prism is a script-first Python music-production project. Preserve readable Python authoring and a
lightweight headless offline path while extending production and live workflows.
Audit baseline: 434f538242009e373b62da74c5d527b6bd9120eb, 2026-09-05. This is historical evidence,
not the branch to reset to. Work from the latest integrated implementation that contains the
required preceding tasks. Read AGENTS.md and inspect current code before editing; recheck whether an
audited defect is already fixed. Source paths below refer to the baseline and may have moved.
Implement this task completely, with code rather than only a plan or stubs. Preserve unrelated work,
use a dedicated branch/worktree, and make routine design decisions from the repository and these
requirements. Do not implement later tasks opportunistically. If a prerequisite is absent, resolve
its supplied branch/commit or report the precise dependency rather than inventing an incompatible
substitute.

Required preceding tasks: 1, 2, 6, 7, 8. All earlier integrated changes must remain present.
Where to start: src/prism/render.py: _ExportSettings, _prepare_export, _write_wav, RenderResult;
src/prism/project/builder.py: render; docs/guides/rendering-and-export.md.

Context and why: Existing PCM-16, PCM-24, and float-32 WAV output works, including mono/stereo and
soxr conversion. Fixed-point output silently clips, and the reported peak hides the pre-clipping
overshoot. normalize=True only attenuates master peaks above -1 dBFS; it is not loudness
normalization.

Create typed, serializable export settings/profiles that preserve current keyword APIs through a
compatibility adapter. Keep internal render rate separate from delivery rate. Add explicit clipping
policies such as error/warn/clip, pre-quantization peak and clipped-sample diagnostics, and clearly
named normalization modes and targets. Define gain/normalization order and measure delivery overload
after resampling/downmixing. Do not claim loudness normalization until an actual loudness
implementation exists.

Add optional seeded TPDF dither for final integer quantization. Apply it once at the final quantizer
with an explicit policy for stems and repeated exports; never dither float exports. Retain float
headroom and deterministic native export when the same settings and seed are used. Avoid introducing
new double-rounding or precision loss in the writer.

Acceptance: Verify storage subtype and sample values for all existing formats, rates and layouts. A
1.5-amplitude fixture reports overload before clipping; float preserves it. Test silence, NaN/Inf
rejection, normalization behavior, deterministic dither, low-level quantization error, and
resampling overshoot. Update results/API documentation and executable listening/master/stem profile
examples.

Verification and handoff: Add focused behavioral/regression tests for the described risks. Run
relevant tests plus the repository's required CI/type/lint/docs gates; at the audit baseline these
include pytest --cov, mypy src/prism, ruff check ., and mkdocs build --strict in the appropriate uv
extras. Preserve the separate real-VST workflow. Do not weaken gates, delete assertions, or equate
mocks with hardware/plugin qualification. Update the guide and runnable tutorial as required by
AGENTS.md. Read and update docs/development/implementation-status.md (create it if absent) with this
task number, completed scope, implemented API/compatibility decisions, verification and concrete
limitations. Use the GitHub connector to publish scoped verified changes on a dedicated branch and
finally open a pull request containing your changes. If an open PR already covers this task, update
that PR instead of creating a duplicate. Target main unless the supplied prerequisite work requires
an explicitly documented stacked PR. Include the task number, problem, implemented behavior,
compatibility decisions, exact verification results and remaining limitations in the PR description.
Check the published diff and CI results; fix failures caused by your changes and report pending or
blocked checks accurately. Return the PR URL, branch, final commit SHA and a concise handoff. A local
commit alone is not the final deliverable. Do not force-push or auto-merge. The next agent must be
able to start from this result.
```

<a id="task-12"></a>

## 12. Make stem delivery modes and reconstruction guarantees explicit

```text
Implementation task 12/35: Make stem delivery modes and reconstruction guarantees explicit

Repository: https://github.com/SeucheAchat9115/Prism
Repository workflow: Use the GitHub connector for all remote repository communication: reading
repository files, branches, pull requests, review feedback and CI results, and publishing commits,
branches and pull requests. Local file editing, builds, tests and local Git operations are allowed;
do not use shell git fetch/pull/push/clone, gh, curl or direct HTTP clients to contact GitHub.
Discover the connector tools available in your session. If connector access is unavailable or an
operation is blocked, preserve the local work and report the exact blocker; do not silently switch
to another remote transport.

Prism is a script-first Python music-production project. Preserve readable Python authoring and a
lightweight headless offline path while extending production and live workflows.
Audit baseline: 434f538242009e373b62da74c5d527b6bd9120eb, 2026-09-05. This is historical evidence,
not the branch to reset to. Work from the latest integrated implementation that contains the
required preceding tasks. Read AGENTS.md and inspect current code before editing; recheck whether an
audited defect is already fixed. Source paths below refer to the baseline and may have moved.
Implement this task completely, with code rather than only a plan or stubs. Preserve unrelated work,
use a dedicated branch/worktree, and make routine design decisions from the repository and these
requirements. Do not implement later tasks opportunistically. If a prerequisite is absent, resolve
its supplied branch/commit or report the precise dependency rather than inventing an incompatible
substitute.

Required preceding tasks: 1, 5, 11. All earlier integrated changes must remain present.
Where to start: src/prism/render.py: render_stems, _RenderedProject; src/prism/project/builder.py:
buses, sends; tests/test_mixer.py; docs/tutorial/17-render-stems.md.

Context and why: Current exports include every track tap, bus/return tap, and master. Importing a
track and its group-bus stem together doubles that material. This behavior is documented, but the
API does not help producers choose a valid delivery set.

Retain an explicitly named channel-taps/debug mode for existing behavior. Add a production mode
exporting only signals that feed the master: ungrouped track outputs plus top-level group and return
outputs. Provide optional dry/source or pre-insert taps only with explicit stage labels. Include
routing-stage and master-processing metadata in the ownership/delivery manifest.

Define the reconstruction target as a specific pre-master signal, including whether a common master
gain is included. Do not normalize stems independently. Do not promise that processing stems
separately through a nonlinear master compressor reproduces the mastered mix. Supply the final
master reference from the same render generation so nondeterministic VSTs are not rerun separately
for each file.

Acceptance: A simple group export sums to the documented pre-master target without doubling. Cover
ungrouped tracks, groups, sends/returns, mute, gain/pan, effect tails and normalization. A
nonlinear-master test confirms the documented limitation rather than manufacturing a false equality.
All files share start, rate, channels and frame count, and preserve the file-safety guarantees from
task 1.

Verification and handoff: Add focused behavioral/regression tests for the described risks. Run
relevant tests plus the repository's required CI/type/lint/docs gates; at the audit baseline these
include pytest --cov, mypy src/prism, ruff check ., and mkdocs build --strict in the appropriate uv
extras. Preserve the separate real-VST workflow. Do not weaken gates, delete assertions, or equate
mocks with hardware/plugin qualification. Update the guide and runnable tutorial as required by
AGENTS.md. Read and update docs/development/implementation-status.md (create it if absent) with this
task number, completed scope, implemented API/compatibility decisions, verification and concrete
limitations. Use the GitHub connector to publish scoped verified changes on a dedicated branch and
finally open a pull request containing your changes. If an open PR already covers this task, update
that PR instead of creating a duplicate. Target main unless the supplied prerequisite work requires
an explicitly documented stacked PR. Include the task number, problem, implemented behavior,
compatibility decisions, exact verification results and remaining limitations in the PR description.
Check the published diff and CI results; fix failures caused by your changes and report pending or
blocked checks accurately. Return the PR URL, branch, final commit SHA and a concise handoff. A local
commit alone is not the final deliverable. Do not force-push or auto-merge. The next agent must be
able to start from this result.
```

<a id="task-13"></a>

## 13. Add project fingerprints, render manifests, and version compatibility

```text
Implementation task 13/35: Add project fingerprints, render manifests, and version compatibility

Repository: https://github.com/SeucheAchat9115/Prism
Repository workflow: Use the GitHub connector for all remote repository communication: reading
repository files, branches, pull requests, review feedback and CI results, and publishing commits,
branches and pull requests. Local file editing, builds, tests and local Git operations are allowed;
do not use shell git fetch/pull/push/clone, gh, curl or direct HTTP clients to contact GitHub.
Discover the connector tools available in your session. If connector access is unavailable or an
operation is blocked, preserve the local work and report the exact blocker; do not silently switch
to another remote transport.

Prism is a script-first Python music-production project. Preserve readable Python authoring and a
lightweight headless offline path while extending production and live workflows.
Audit baseline: 434f538242009e373b62da74c5d527b6bd9120eb, 2026-09-05. This is historical evidence,
not the branch to reset to. Work from the latest integrated implementation that contains the
required preceding tasks. Read AGENTS.md and inspect current code before editing; recheck whether an
audited defect is already fixed. Source paths below refer to the baseline and may have moved.
Implement this task completely, with code rather than only a plan or stubs. Preserve unrelated work,
use a dedicated branch/worktree, and make routine design decisions from the repository and these
requirements. Do not implement later tasks opportunistically. If a prerequisite is absent, resolve
its supplied branch/commit or report the precise dependency rather than inventing an incompatible
substitute.

Required preceding tasks: 3, 9, 11, 12. All earlier integrated changes must remain present.
Where to start: src/prism/project/builder.py: configuration, _version; src/prism/vst.py;
src/prism/render.py: results; src/prism/version.py; pyproject.toml.

Context and why: prism_version is currently a label rather than an enforced compatibility contract.
Configuration records sample/state paths without their content hashes. Changing a recording or patch
can therefore leave the same configuration while changing the sound; future caches would be unsafe.

Introduce versioned project/render schemas and a portable content fingerprint. Record effective
script/configuration, source audio and plugin-state/preset hashes, actual installed
Prism/backend/DSP versions, VST binary identity, seeds, internal/delivery settings, and stem routing
mode. Avoid absolute machine paths in portable identity. Hash files once per verified render
generation, using a safe change-detection cache rather than repeatedly reading large plugin bundles.

Distinguish a requested project compatibility version from the actual runtime version. Provide
validation and explicit migrations for supported older semantics from preceding tasks. Unsupported
future schemas must fail clearly; a version string alone must not claim reproducibility. Define
deterministic versus externally reproducible VST output and prepare cache keys that later
preview/freeze tasks can reuse.

Acceptance: A source/state/plugin/settings change invalidates the relevant fingerprint; moving an
otherwise identical project preserves portable identity. Manifest outputs correspond to the exact
successful export generation and include checksums. Test schema migration, unsupported versions,
missing assets, and deterministic versus external backend metadata. Document what must accompany a
project when shared.

Verification and handoff: Add focused behavioral/regression tests for the described risks. Run
relevant tests plus the repository's required CI/type/lint/docs gates; at the audit baseline these
include pytest --cov, mypy src/prism, ruff check ., and mkdocs build --strict in the appropriate uv
extras. Preserve the separate real-VST workflow. Do not weaken gates, delete assertions, or equate
mocks with hardware/plugin qualification. Update the guide and runnable tutorial as required by
AGENTS.md. Read and update docs/development/implementation-status.md (create it if absent) with this
task number, completed scope, implemented API/compatibility decisions, verification and concrete
limitations. Use the GitHub connector to publish scoped verified changes on a dedicated branch and
finally open a pull request containing your changes. If an open PR already covers this task, update
that PR instead of creating a duplicate. Target main unless the supplied prerequisite work requires
an explicitly documented stacked PR. Include the task number, problem, implemented behavior,
compatibility decisions, exact verification results and remaining limitations in the PR description.
Check the published diff and CI results; fix failures caused by your changes and report pending or
blocked checks accurately. Return the PR URL, branch, final commit SHA and a concise handoff. A local
commit alone is not the final deliverable. Do not force-push or auto-merge. The next agent must be
able to start from this result.
```

<a id="task-14"></a>

## 14. Create a public project build contract and executable CLI tutorials

```text
Implementation task 14/35: Create a public project build contract and executable CLI tutorials

Repository: https://github.com/SeucheAchat9115/Prism
Repository workflow: Use the GitHub connector for all remote repository communication: reading
repository files, branches, pull requests, review feedback and CI results, and publishing commits,
branches and pull requests. Local file editing, builds, tests and local Git operations are allowed;
do not use shell git fetch/pull/push/clone, gh, curl or direct HTTP clients to contact GitHub.
Discover the connector tools available in your session. If connector access is unavailable or an
operation is blocked, preserve the local work and report the exact blocker; do not silently switch
to another remote transport.

Prism is a script-first Python music-production project. Preserve readable Python authoring and a
lightweight headless offline path while extending production and live workflows.
Audit baseline: 434f538242009e373b62da74c5d527b6bd9120eb, 2026-09-05. This is historical evidence,
not the branch to reset to. Work from the latest integrated implementation that contains the
required preceding tasks. Read AGENTS.md and inspect current code before editing; recheck whether an
audited defect is already fixed. Source paths below refer to the baseline and may have moved.
Implement this task completely, with code rather than only a plan or stubs. Preserve unrelated work,
use a dedicated branch/worktree, and make routine design decisions from the repository and these
requirements. Do not implement later tasks opportunistically. If a prerequisite is absent, resolve
its supplied branch/commit or report the precise dependency rather than inventing an incompatible
substitute.

Required preceding tasks: 2, 3, 11, 13. All earlier integrated changes must remain present.
Where to start: src/prism/project/builder.py: Project.__init__, _project_script; src/prism/cli.py;
docs/getting-started; docs/guides/mixing-and-automation.md; tests/test_cli.py;
.github/workflows/docs.yml.

Context and why: Inferring a project root from the caller filename makes notebooks, editors, and
future watch mode fragile. Starter scripts build and render together. The mixing guide also uses
delay_beats even though the delay accepts time_beats; a successful documentation build did not catch
that error.

Add an explicit supported project-root/path API and a documented build() contract returning a
Project without rendering as a side effect. Keep legacy main.py scripts working for their original
direct-execution workflow. New scaffolds should put exports behind the Python main guard. Add prism
render for the new build contract with profile/output selection, and prism doctor for dependency,
project, plugin and asset diagnostics.

Be explicit that building user Python executes user code; do not market a subprocess as a security
sandbox. Metadata-only inventory/doctor operations should avoid executing main.py unless the user
invokes a build validation. Detect old top-level-export scripts in preview workflows and provide a
concrete migration instruction rather than silently rewriting arbitrary Python.

Fix the delay guide to use time_beats. Add a maintainable executable-snippet/tutorial harness that
creates temporary project assets and exercises relevant documented workflows, rather than attempting
to execute every explanatory code fragment blindly.

Acceptance: Clean scaffolds build without output side effects and render through both supported
entry points. Explicit roots work from a different cwd and a notebook-style caller. Doctor reports
missing optional hosts without breaking native projects. CI exercises the corrected guide and
representative tutorials; packaging and strict docs builds remain healthy.

Verification and handoff: Add focused behavioral/regression tests for the described risks. Run
relevant tests plus the repository's required CI/type/lint/docs gates; at the audit baseline these
include pytest --cov, mypy src/prism, ruff check ., and mkdocs build --strict in the appropriate uv
extras. Preserve the separate real-VST workflow. Do not weaken gates, delete assertions, or equate
mocks with hardware/plugin qualification. Update the guide and runnable tutorial as required by
AGENTS.md. Read and update docs/development/implementation-status.md (create it if absent) with this
task number, completed scope, implemented API/compatibility decisions, verification and concrete
limitations. Use the GitHub connector to publish scoped verified changes on a dedicated branch and
finally open a pull request containing your changes. If an open PR already covers this task, update
that PR instead of creating a duplicate. Target main unless the supplied prerequisite work requires
an explicitly documented stacked PR. Include the task number, problem, implemented behavior,
compatibility decisions, exact verification results and remaining limitations in the PR description.
Check the published diff and CI results; fix failures caused by your changes and report pending or
blocked checks accurately. Return the PR URL, branch, final commit SHA and a concise handoff. A local
commit alone is not the final deliverable. Do not force-push or auto-merge. The next agent must be
able to start from this result.
```

<a id="task-15"></a>

## 15. Implement range rendering, bounded caches, and optional automatic tails

```text
Implementation task 15/35: Implement range rendering, bounded caches, and optional automatic tails

Repository: https://github.com/SeucheAchat9115/Prism
Repository workflow: Use the GitHub connector for all remote repository communication: reading
repository files, branches, pull requests, review feedback and CI results, and publishing commits,
branches and pull requests. Local file editing, builds, tests and local Git operations are allowed;
do not use shell git fetch/pull/push/clone, gh, curl or direct HTTP clients to contact GitHub.
Discover the connector tools available in your session. If connector access is unavailable or an
operation is blocked, preserve the local work and report the exact blocker; do not silently switch
to another remote transport.

Prism is a script-first Python music-production project. Preserve readable Python authoring and a
lightweight headless offline path while extending production and live workflows.
Audit baseline: 434f538242009e373b62da74c5d527b6bd9120eb, 2026-09-05. This is historical evidence,
not the branch to reset to. Work from the latest integrated implementation that contains the
required preceding tasks. Read AGENTS.md and inspect current code before editing; recheck whether an
audited defect is already fixed. Source paths below refer to the baseline and may have moved.
Implement this task completely, with code rather than only a plan or stubs. Preserve unrelated work,
use a dedicated branch/worktree, and make routine design decisions from the repository and these
requirements. Do not implement later tasks opportunistically. If a prerequisite is absent, resolve
its supplied branch/commit or report the precise dependency rather than inventing an incompatible
substitute.

Required preceding tasks: 4, 6, 7, 11, 13, 14. All earlier integrated changes must remain present.
Where to start: src/prism/render.py; compiled event/timing modules from earlier tasks; export
settings; project fingerprints; tests/test_render.py.

Context and why: Producers need to audition a selected section and hear small edits without
repeatedly rebuilding a whole song. Cropping the arrangement before processing can lose sustained
notes, controller state, and effect history.

Add render ranges using musical and explicit time bounds, with documented start/end, pre-roll/chase,
and tail policy. Establish correctness first by rendering the required history and slicing the
result; optimize only where processor state proves a shorter path equivalent. Preserve a shared
origin for exported stems and report absolute range metadata.

Implement bounded content-addressed caches for decoded/prepared sources and valid intermediate
renders using task 13 fingerprints. Include upstream routing, automation, plugin state and backend
settings in invalidation. Do not assume all VSTs are deterministic; make cached/frozen external
output an explicit policy and allow forcing a fresh render. Add eviction and cancellation hooks for
later watch mode.

Add an optional bounded automatic-tail policy with a documented level threshold, hold interval and
maximum duration. Periodic/delayed effects can become quiet and later sound again: never claim a
naive first-silence check guarantees a complete tail. Use declared tails where trustworthy,
otherwise retain explicit/max-duration behavior.

Acceptance: Range output matches the corresponding full-render region with active notes, automation
and effects. Cache hits preserve outputs; relevant edits invalidate; unrelated edits retain safe
hits; eviction bounds disk/memory. Test delayed echoes, long release, empty/silent ranges and
maximum-tail termination.

Verification and handoff: Add focused behavioral/regression tests for the described risks. Run
relevant tests plus the repository's required CI/type/lint/docs gates; at the audit baseline these
include pytest --cov, mypy src/prism, ruff check ., and mkdocs build --strict in the appropriate uv
extras. Preserve the separate real-VST workflow. Do not weaken gates, delete assertions, or equate
mocks with hardware/plugin qualification. Update the guide and runnable tutorial as required by
AGENTS.md. Read and update docs/development/implementation-status.md (create it if absent) with this
task number, completed scope, implemented API/compatibility decisions, verification and concrete
limitations. Use the GitHub connector to publish scoped verified changes on a dedicated branch and
finally open a pull request containing your changes. If an open PR already covers this task, update
that PR instead of creating a duplicate. Target main unless the supplied prerequisite work requires
an explicitly documented stacked PR. Include the task number, problem, implemented behavior,
compatibility decisions, exact verification results and remaining limitations in the PR description.
Check the published diff and CI results; fix failures caused by your changes and report pending or
blocked checks accurately. Return the PR URL, branch, final commit SHA and a concise handoff. A local
commit alone is not the final deliverable. Do not force-push or auto-merge. The next agent must be
able to start from this result.
```

<a id="task-16"></a>

## 16. Add audible playback and transport for rendered audio

```text
Implementation task 16/35: Add audible playback and transport for rendered audio

Repository: https://github.com/SeucheAchat9115/Prism
Repository workflow: Use the GitHub connector for all remote repository communication: reading
repository files, branches, pull requests, review feedback and CI results, and publishing commits,
branches and pull requests. Local file editing, builds, tests and local Git operations are allowed;
do not use shell git fetch/pull/push/clone, gh, curl or direct HTTP clients to contact GitHub.
Discover the connector tools available in your session. If connector access is unavailable or an
operation is blocked, preserve the local work and report the exact blocker; do not silently switch
to another remote transport.

Prism is a script-first Python music-production project. Preserve readable Python authoring and a
lightweight headless offline path while extending production and live workflows.
Audit baseline: 434f538242009e373b62da74c5d527b6bd9120eb, 2026-09-05. This is historical evidence,
not the branch to reset to. Work from the latest integrated implementation that contains the
required preceding tasks. Read AGENTS.md and inspect current code before editing; recheck whether an
audited defect is already fixed. Source paths below refer to the baseline and may have moved.
Implement this task completely, with code rather than only a plan or stubs. Preserve unrelated work,
use a dedicated branch/worktree, and make routine design decisions from the repository and these
requirements. Do not implement later tasks opportunistically. If a prerequisite is absent, resolve
its supplied branch/commit or report the precise dependency rather than inventing an incompatible
substitute.

Required preceding tasks: 11, 14, 15. All earlier integrated changes must remain present.
Where to start: src/prism/cli.py; render/build interfaces from earlier tasks; new
audio-device/transport modules; pyproject.toml optional dependencies.

Context and why: Prism currently requires opening a rendered WAV in another application. A useful
first interactive feature is a reliable player for already rendered audio; this does not require
pretending the offline synth engine is a real-time host.

Implement prism play for a buildable project or completed render, with play/pause/stop, seek,
musical loop range, device selection, and a clear current position. Keep playback/device
dependencies optional so headless offline rendering remains lightweight. Use a tested output backend
and isolate device handling behind an adapter that can be exercised without hardware.

Keep device callbacks restricted to bounded audio delivery. Build/render, filesystem access, UI work
and large allocations belong elsewhere. A Python-facing library can be an initial adapter if its
actual constraints are documented; do not claim hard real-time guarantees. Report underruns, device
removal and unsupported format/channel combinations. Define loop crossfades and pause/seek behavior
without changing exported audio.

Acceptance: A producer runs one command and hears the completed song on an available supported
device. Headless tests verify cursor/sample agreement, stop/seek/loop boundaries, channel/rate
negotiation, error recovery and clean shutdown. Add a manual Windows/Linux device checklist and
report whether it was run. Help text must distinguish rendered-buffer playback from live instrument
processing.

Verification and handoff: Add focused behavioral/regression tests for the described risks. Run
relevant tests plus the repository's required CI/type/lint/docs gates; at the audit baseline these
include pytest --cov, mypy src/prism, ruff check ., and mkdocs build --strict in the appropriate uv
extras. Preserve the separate real-VST workflow. Do not weaken gates, delete assertions, or equate
mocks with hardware/plugin qualification. Update the guide and runnable tutorial as required by
AGENTS.md. Read and update docs/development/implementation-status.md (create it if absent) with this
task number, completed scope, implemented API/compatibility decisions, verification and concrete
limitations. Use the GitHub connector to publish scoped verified changes on a dedicated branch and
finally open a pull request containing your changes. If an open PR already covers this task, update
that PR instead of creating a duplicate. Target main unless the supplied prerequisite work requires
an explicitly documented stacked PR. Include the task number, problem, implemented behavior,
compatibility decisions, exact verification results and remaining limitations in the PR description.
Check the published diff and CI results; fix failures caused by your changes and report pending or
blocked checks accurately. Return the PR URL, branch, final commit SHA and a concise handoff. A local
commit alone is not the final deliverable. Do not force-push or auto-merge. The next agent must be
able to start from this result.
```

<a id="task-17"></a>

## 17. Reload edited Python while the previous song keeps playing

```text
Implementation task 17/35: Reload edited Python while the previous song keeps playing

Repository: https://github.com/SeucheAchat9115/Prism
Repository workflow: Use the GitHub connector for all remote repository communication: reading
repository files, branches, pull requests, review feedback and CI results, and publishing commits,
branches and pull requests. Local file editing, builds, tests and local Git operations are allowed;
do not use shell git fetch/pull/push/clone, gh, curl or direct HTTP clients to contact GitHub.
Discover the connector tools available in your session. If connector access is unavailable or an
operation is blocked, preserve the local work and report the exact blocker; do not silently switch
to another remote transport.

Prism is a script-first Python music-production project. Preserve readable Python authoring and a
lightweight headless offline path while extending production and live workflows.
Audit baseline: 434f538242009e373b62da74c5d527b6bd9120eb, 2026-09-05. This is historical evidence,
not the branch to reset to. Work from the latest integrated implementation that contains the
required preceding tasks. Read AGENTS.md and inspect current code before editing; recheck whether an
audited defect is already fixed. Source paths below refer to the baseline and may have moved.
Implement this task completely, with code rather than only a plan or stubs. Preserve unrelated work,
use a dedicated branch/worktree, and make routine design decisions from the repository and these
requirements. Do not implement later tasks opportunistically. If a prerequisite is absent, resolve
its supplied branch/commit or report the precise dependency rather than inventing an incompatible
substitute.

Required preceding tasks: 13, 14, 15, 16. All earlier integrated changes must remain present.
Where to start: build contract, cache and playback/transport modules from tasks 13-16;
src/prism/cli.py; project source/asset dependency tracking.

Context and why: The requested workflow is to edit a Python song and hear the change without
repeatedly opening WAVs. The safest first version renders a new candidate in the background while
continuing to play the last valid buffer.

Implement prism play main.py --watch using the established build contract. Watch scripts/modules and
relevant sample/state/config dependencies, debounce edits, and exclude generated
renders/cache/export directories. Execute builds in isolated worker processes with cancellation and
bounded output; newest successful build wins. Reuse content-based caches and selected-range
rendering.

Publish a candidate only when build, validation and render succeed. Swap audio at a configurable
loop/bar boundary using a short click-resistant crossfade, with a defined policy when tempo, loop
length or arrangement length changes. Keep the transport stable during syntax errors, plugin errors
and slow builds. Display which source revision is currently audible and which is building so users
are not misled by stale audio.

Acceptance: End-to-end tests cover successful edits, syntax errors, plugin failure, rapid
consecutive saves, obsolete builds completing late, state/sample edits, and watcher feedback loops.
A bad edit leaves previous playback running; shutdown cancels all workers. A tutorial demonstrates
edit-save-hear and explains its build/render delay. This task does not claim that the existing
state-only VST editor is now audible.

Verification and handoff: Add focused behavioral/regression tests for the described risks. Run
relevant tests plus the repository's required CI/type/lint/docs gates; at the audit baseline these
include pytest --cov, mypy src/prism, ruff check ., and mkdocs build --strict in the appropriate uv
extras. Preserve the separate real-VST workflow. Do not weaken gates, delete assertions, or equate
mocks with hardware/plugin qualification. Update the guide and runnable tutorial as required by
AGENTS.md. Read and update docs/development/implementation-status.md (create it if absent) with this
task number, completed scope, implemented API/compatibility decisions, verification and concrete
limitations. Use the GitHub connector to publish scoped verified changes on a dedicated branch and
finally open a pull request containing your changes. If an open PR already covers this task, update
that PR instead of creating a duplicate. Target main unless the supplied prerequisite work requires
an explicitly documented stacked PR. Include the task number, problem, implemented behavior,
compatibility decisions, exact verification results and remaining limitations in the PR description.
Check the published diff and CI results; fix failures caused by your changes and report pending or
blocked checks accurately. Return the PR URL, branch, final commit SHA and a concise handoff. A local
commit alone is not the final deliverable. Do not force-push or auto-merge. The next agent must be
able to start from this result.
```

<a id="task-18"></a>

## 18. Provide a compact visual transport and live playback inspection

```text
Implementation task 18/35: Provide a compact visual transport and live playback inspection

Repository: https://github.com/SeucheAchat9115/Prism
Repository workflow: Use the GitHub connector for all remote repository communication: reading
repository files, branches, pull requests, review feedback and CI results, and publishing commits,
branches and pull requests. Local file editing, builds, tests and local Git operations are allowed;
do not use shell git fetch/pull/push/clone, gh, curl or direct HTTP clients to contact GitHub.
Discover the connector tools available in your session. If connector access is unavailable or an
operation is blocked, preserve the local work and report the exact blocker; do not silently switch
to another remote transport.

Prism is a script-first Python music-production project. Preserve readable Python authoring and a
lightweight headless offline path while extending production and live workflows.
Audit baseline: 434f538242009e373b62da74c5d527b6bd9120eb, 2026-09-05. This is historical evidence,
not the branch to reset to. Work from the latest integrated implementation that contains the
required preceding tasks. Read AGENTS.md and inspect current code before editing; recheck whether an
audited defect is already fixed. Source paths below refer to the baseline and may have moved.
Implement this task completely, with code rather than only a plan or stubs. Preserve unrelated work,
use a dedicated branch/worktree, and make routine design decisions from the repository and these
requirements. Do not implement later tasks opportunistically. If a prerequisite is absent, resolve
its supplied branch/commit or report the precise dependency rather than inventing an incompatible
substitute.

Required preceding tasks: 16, 17. All earlier integrated changes must remain present.
Where to start: transport/watch state and event APIs; new local companion UI; CLI launcher and
packaging; documentation.

Context and why: The user wants to see what the Python script is playing. A compact companion view
can expose arrangement state without replacing Python authoring with a full graphical DAW editor.

Build a local transport view with play/pause/stop, loop selection, section/track timeline, waveform,
audible playhead, meters, and build/error status. Show active notes when the compiled event stream
can reliably identify them. Drive the view from the actual audio transport clock and applied project
revision, not a free-running browser timer or the last edited file.

Choose a small maintainable UI stack compatible with the repository's packaging and supported
Windows/Linux workflows. Keep offline CLI use independent from it. Decimate waveform and meter data
off the audio path; bound update rates. If using a local web view, bind its control service to
loopback and protect control messages; do not silently publish a remote service. Preserve
accessibility, keyboard controls and readable error messages.

Acceptance: Scrubbing, looping, pausing and source changes keep sound, playhead, waveform and active
revision consistent. Long songs use bounded display memory. Test transport/UI contracts and run a
real visual smoke check. Provide a runnable tutorial with a native project and explain that a visual
playhead is available even before genuine live synthesis is implemented.

Verification and handoff: Add focused behavioral/regression tests for the described risks. Run
relevant tests plus the repository's required CI/type/lint/docs gates; at the audit baseline these
include pytest --cov, mypy src/prism, ruff check ., and mkdocs build --strict in the appropriate uv
extras. Preserve the separate real-VST workflow. Do not weaken gates, delete assertions, or equate
mocks with hardware/plugin qualification. Update the guide and runnable tutorial as required by
AGENTS.md. Read and update docs/development/implementation-status.md (create it if absent) with this
task number, completed scope, implemented API/compatibility decisions, verification and concrete
limitations. Use the GitHub connector to publish scoped verified changes on a dedicated branch and
finally open a pull request containing your changes. If an open PR already covers this task, update
that PR instead of creating a duplicate. Target main unless the supplied prerequisite work requires
an explicitly documented stacked PR. Include the task number, problem, implemented behavior,
compatibility decisions, exact verification results and remaining limitations in the PR description.
Check the published diff and CI results; fix failures caused by your changes and report pending or
blocked checks accurately. Return the PR URL, branch, final commit SHA and a concise handoff. A local
commit alone is not the final deliverable. Do not force-push or auto-merge. The next agent must be
able to start from this result.
```

<a id="task-19"></a>

## 19. Introduce stateful processors and a streaming offline renderer

```text
Implementation task 19/35: Introduce stateful processors and a streaming offline renderer

Repository: https://github.com/SeucheAchat9115/Prism
Repository workflow: Use the GitHub connector for all remote repository communication: reading
repository files, branches, pull requests, review feedback and CI results, and publishing commits,
branches and pull requests. Local file editing, builds, tests and local Git operations are allowed;
do not use shell git fetch/pull/push/clone, gh, curl or direct HTTP clients to contact GitHub.
Discover the connector tools available in your session. If connector access is unavailable or an
operation is blocked, preserve the local work and report the exact blocker; do not silently switch
to another remote transport.

Prism is a script-first Python music-production project. Preserve readable Python authoring and a
lightweight headless offline path while extending production and live workflows.
Audit baseline: 434f538242009e373b62da74c5d527b6bd9120eb, 2026-09-05. This is historical evidence,
not the branch to reset to. Work from the latest integrated implementation that contains the
required preceding tasks. Read AGENTS.md and inspect current code before editing; recheck whether an
audited defect is already fixed. Source paths below refer to the baseline and may have moved.
Implement this task completely, with code rather than only a plan or stubs. Preserve unrelated work,
use a dedicated branch/worktree, and make routine design decisions from the repository and these
requirements. Do not implement later tasks opportunistically. If a prerequisite is absent, resolve
its supplied branch/commit or report the precise dependency rather than inventing an incompatible
substitute.

Required preceding tasks: 4, 5, 6, 7, 8, 12, 15. All earlier integrated changes must remain present.
Where to start: src/prism/effects.py; src/prism/stock_plugins; src/prism/synthesis;
src/prism/render.py; compiled musical model; plugin registry.

Context and why: The current renderer retains full float64 song buffers, and effects allocate/reset
state on each call. Thirty-two five-minute stereo track buffers at 48 kHz alone occupy about 6.9
GiB. Calling these functions repeatedly on small blocks would reset filters, delay lines and
envelopes.

Define processor lifecycle contracts for prepare(sample rate, maximum block, layout),
process(events/automation/audio), reset/seek policy, latency and tail reporting. Implement stateful
stock effects, sample voices and native synth voice scheduling. Keep authored configuration separate
from mutable playback state. Pass constants as scalars and automation as bounded block segments
rather than full-song arrays.

Add streaming offline graph execution and block WAV writing. Allocate/reuse working buffers and
release intermediates when only a master is requested. Stem taps must be captured during the same
graph pass. Explicitly distinguish streaming processors from the existing batch-only VST adapter:
keep the latter as a declared offline fallback, rendered once per track, until continuous hosting is
implemented in tasks 21-22. Never restart a VST per block to fake streaming. Keep the previous
renderer as a temporary reference only while proving parity; do not leave two permanently divergent
musical compilers. This task establishes stateful streaming correctness, not a hard real-time claim.

Acceptance: Whole-buffer and varying-block-size outputs agree within justified tolerances for all
stock processors, note overlaps, section/loop boundaries and tails. Delays/reverb/synth envelopes
continue across blocks. Five-minute/32-track native streaming graphs demonstrate bounded working
memory without brittle wall-clock CI thresholds. Report batch-VST fallback memory separately instead
of extending that claim to it. Repeated deterministic offline renders remain reproducible.

Verification and handoff: Add focused behavioral/regression tests for the described risks. Run
relevant tests plus the repository's required CI/type/lint/docs gates; at the audit baseline these
include pytest --cov, mypy src/prism, ruff check ., and mkdocs build --strict in the appropriate uv
extras. Preserve the separate real-VST workflow. Do not weaken gates, delete assertions, or equate
mocks with hardware/plugin qualification. Update the guide and runnable tutorial as required by
AGENTS.md. Read and update docs/development/implementation-status.md (create it if absent) with this
task number, completed scope, implemented API/compatibility decisions, verification and concrete
limitations. Use the GitHub connector to publish scoped verified changes on a dedicated branch and
finally open a pull request containing your changes. If an open PR already covers this task, update
that PR instead of creating a duplicate. Target main unless the supplied prerequisite work requires
an explicitly documented stacked PR. Include the task number, problem, implemented behavior,
compatibility decisions, exact verification results and remaining limitations in the PR description.
Check the published diff and CI results; fix failures caused by your changes and report pending or
blocked checks accurately. Return the PR URL, branch, final commit SHA and a concise handoff. A local
commit alone is not the final deliverable. Do not force-push or auto-merge. The next agent must be
able to start from this result.
```

<a id="task-20"></a>

## 20. Move DSP hot paths behind a native processing boundary

```text
Implementation task 20/35: Move DSP hot paths behind a native processing boundary

Repository: https://github.com/SeucheAchat9115/Prism
Repository workflow: Use the GitHub connector for all remote repository communication: reading
repository files, branches, pull requests, review feedback and CI results, and publishing commits,
branches and pull requests. Local file editing, builds, tests and local Git operations are allowed;
do not use shell git fetch/pull/push/clone, gh, curl or direct HTTP clients to contact GitHub.
Discover the connector tools available in your session. If connector access is unavailable or an
operation is blocked, preserve the local work and report the exact blocker; do not silently switch
to another remote transport.

Prism is a script-first Python music-production project. Preserve readable Python authoring and a
lightweight headless offline path while extending production and live workflows.
Audit baseline: 434f538242009e373b62da74c5d527b6bd9120eb, 2026-09-05. This is historical evidence,
not the branch to reset to. Work from the latest integrated implementation that contains the
required preceding tasks. Read AGENTS.md and inspect current code before editing; recheck whether an
audited defect is already fixed. Source paths below refer to the baseline and may have moved.
Implement this task completely, with code rather than only a plan or stubs. Preserve unrelated work,
use a dedicated branch/worktree, and make routine design decisions from the repository and these
requirements. Do not implement later tasks opportunistically. If a prerequisite is absent, resolve
its supplied branch/commit or report the precise dependency rather than inventing an incompatible
substitute.

Required preceding tasks: 19. All earlier integrated changes must remain present.
Where to start: stateful processor contracts from task 19; stock effect and synthesis kernels;
native-extension build configuration; portable DSP parity tests.

Context and why: Stateful Python processing improves memory behavior but cannot by itself provide
reliable short audio deadlines. A future device callback must not enter arbitrary Python, acquire
the GIL, allocate large arrays, or perform unbounded per-sample Python loops.

Choose a maintainable native extension strategy consistent with the repository and existing
dependencies; document the decision and build requirements. Implement the existing stock DSP and
voice/sampling hot paths behind the processor contract, with preallocated bounded buffers and event
storage. Keep the Python API for project construction, configuration and diagnostics. Retain an
offline fallback where useful, clearly separate from the native live path.

Cover oscillators/envelopes, sample playback, gain/pan, filters, delay, reverb, compressor and other
existing stock effects. Keep sound semantics compatible with task 19; sound-quality redesign belongs
to the later synthesis task. Validate denormal handling, finite outputs, stereo layout and
event-boundary behavior. Package native artifacts reproducibly for the supported Python/platform
matrix without forcing compiler setup on ordinary offline users when wheels are available.

Acceptance: Native versus reference DSP parity tests cover dynamic automation and multiple block
sizes. Instrumented tests establish no Python callback/GIL work, filesystem access, locks or heap
growth in the audio processing path after preparation. Build and install checks pass on
Windows/Linux. Report measured throughput and worst observed block timing separately from any
guarantee about end-to-end hardware latency.

Verification and handoff: Add focused behavioral/regression tests for the described risks. Run
relevant tests plus the repository's required CI/type/lint/docs gates; at the audit baseline these
include pytest --cov, mypy src/prism, ruff check ., and mkdocs build --strict in the appropriate uv
extras. Preserve the separate real-VST workflow. Do not weaken gates, delete assertions, or equate
mocks with hardware/plugin qualification. Update the guide and runnable tutorial as required by
AGENTS.md. Read and update docs/development/implementation-status.md (create it if absent) with this
task number, completed scope, implemented API/compatibility decisions, verification and concrete
limitations. Use the GitHub connector to publish scoped verified changes on a dedicated branch and
finally open a pull request containing your changes. If an open PR already covers this task, update
that PR instead of creating a duplicate. Target main unless the supplied prerequisite work requires
an explicitly documented stacked PR. Include the task number, problem, implemented behavior,
compatibility decisions, exact verification results and remaining limitations in the PR description.
Check the published diff and CI results; fix failures caused by your changes and report pending or
blocked checks accurately. Return the PR URL, branch, final commit SHA and a concise handoff. A local
commit alone is not the final deliverable. Do not force-push or auto-merge. The next agent must be
able to start from this result.
```

<a id="task-21"></a>

## 21. Implement a continuous native VST3 host and device proof

```text
Implementation task 21/35: Implement a continuous native VST3 host and device proof

Repository: https://github.com/SeucheAchat9115/Prism
Repository workflow: Use the GitHub connector for all remote repository communication: reading
repository files, branches, pull requests, review feedback and CI results, and publishing commits,
branches and pull requests. Local file editing, builds, tests and local Git operations are allowed;
do not use shell git fetch/pull/push/clone, gh, curl or direct HTTP clients to contact GitHub.
Discover the connector tools available in your session. If connector access is unavailable or an
operation is blocked, preserve the local work and report the exact blocker; do not silently switch
to another remote transport.

Prism is a script-first Python music-production project. Preserve readable Python authoring and a
lightweight headless offline path while extending production and live workflows.
Audit baseline: 434f538242009e373b62da74c5d527b6bd9120eb, 2026-09-05. This is historical evidence,
not the branch to reset to. Work from the latest integrated implementation that contains the
required preceding tasks. Read AGENTS.md and inspect current code before editing; recheck whether an
audited defect is already fixed. Source paths below refer to the baseline and may have moved.
Implement this task completely, with code rather than only a plan or stubs. Preserve unrelated work,
use a dedicated branch/worktree, and make routine design decisions from the repository and these
requirements. Do not implement later tasks opportunistically. If a prerequisite is absent, resolve
its supplied branch/commit or report the precise dependency rather than inventing an incompatible
substitute.

Required preceding tasks: 3, 9, 10, 19, 20. All earlier integrated changes must remain present.
Where to start: existing VST registry/state interfaces; native processor contract; new continuous
host/device adapter; fixture plugin from task 10.

Context and why: Existing DawDreamer orchestration renders batches through temporary files and
subprocesses. The plugin editor processes silence without device output. Genuine audible patch
editing requires one persistent VST instance connected to a continuous audio device.

Verify current primary-source APIs and threading/lifecycle contracts for the pinned host and
candidate native frameworks. Reuse existing capabilities only if they genuinely support continuous
processing; otherwise implement a narrow native VST3 host adapter, for example using an appropriate
pinned JUCE-based integration. Deliver a working vertical slice rather than an architecture document
alone: load one registered VST3, open its editor on the required UI thread, route that same instance
to a device, and feed a scheduled test phrase.

Support state/preset loading, parameter changes, explicit processing mode, sample rate/block size,
channel negotiation, latency reporting, editor close, stop/panic and shutdown. Preserve crash
isolation in a persistent host process. Define native audio/command IPC using bounded shared buffers
or another measured nonblocking mechanism, not a subprocess invocation for every block.

Acceptance: A headless harness processes the controlled fixture continuously and proves
parameter/state/MIDI behavior and restart handling. On available hardware, moving the editor
controls changes the audible test phrase from the same instance. State exactly which
hardware/plugin/platform checks were possible. Exported state reopens correctly. Do not label
repeated offline render calls as completed live hosting.

Verification and handoff: Add focused behavioral/regression tests for the described risks. Run
relevant tests plus the repository's required CI/type/lint/docs gates; at the audit baseline these
include pytest --cov, mypy src/prism, ruff check ., and mkdocs build --strict in the appropriate uv
extras. Preserve the separate real-VST workflow. Do not weaken gates, delete assertions, or equate
mocks with hardware/plugin qualification. Update the guide and runnable tutorial as required by
AGENTS.md. Read and update docs/development/implementation-status.md (create it if absent) with this
task number, completed scope, implemented API/compatibility decisions, verification and concrete
limitations. Use the GitHub connector to publish scoped verified changes on a dedicated branch and
finally open a pull request containing your changes. If an open PR already covers this task, update
that PR instead of creating a duplicate. Target main unless the supplied prerequisite work requires
an explicitly documented stacked PR. Include the task number, problem, implemented behavior,
compatibility decisions, exact verification results and remaining limitations in the PR description.
Check the published diff and CI results; fix failures caused by your changes and report pending or
blocked checks accurately. Return the PR URL, branch, final commit SHA and a concise handoff. A local
commit alone is not the final deliverable. Do not force-push or auto-merge. The next agent must be
able to start from this result.
```

<a id="task-22"></a>

## 22. Integrate the persistent live graph and safe project updates

```text
Implementation task 22/35: Integrate the persistent live graph and safe project updates

Repository: https://github.com/SeucheAchat9115/Prism
Repository workflow: Use the GitHub connector for all remote repository communication: reading
repository files, branches, pull requests, review feedback and CI results, and publishing commits,
branches and pull requests. Local file editing, builds, tests and local Git operations are allowed;
do not use shell git fetch/pull/push/clone, gh, curl or direct HTTP clients to contact GitHub.
Discover the connector tools available in your session. If connector access is unavailable or an
operation is blocked, preserve the local work and report the exact blocker; do not silently switch
to another remote transport.

Prism is a script-first Python music-production project. Preserve readable Python authoring and a
lightweight headless offline path while extending production and live workflows.
Audit baseline: 434f538242009e373b62da74c5d527b6bd9120eb, 2026-09-05. This is historical evidence,
not the branch to reset to. Work from the latest integrated implementation that contains the
required preceding tasks. Read AGENTS.md and inspect current code before editing; recheck whether an
audited defect is already fixed. Source paths below refer to the baseline and may have moved.
Implement this task completely, with code rather than only a plan or stubs. Preserve unrelated work,
use a dedicated branch/worktree, and make routine design decisions from the repository and these
requirements. Do not implement later tasks opportunistically. If a prerequisite is absent, resolve
its supplied branch/commit or report the precise dependency rather than inventing an incompatible
substitute.

Required preceding tasks: 17, 18, 19, 20, 21. All earlier integrated changes must remain present.
Where to start: compiled model, native processors, persistent VST host, transport and companion UI
from preceding tasks.

Context and why: Single-plugin audio is not yet a live song engine. Prism needs native instruments,
samples, inserts, buses, master processing and VSTs to share transport time while code and UI
changes occur safely.

Integrate one continuous graph for existing routing with stable track/plugin IDs and the shared
sample clock. Schedule notes and automation inside blocks, preserve filter/voice/effect state,
compensate latency across parallel paths, and account for any IPC buffering. Expose capabilities and
latency so unsupported processors cannot silently degrade the contract.

Route small parameter changes to the existing instance with explicit smoothing/timestamps. Compile
topology or code changes off the audio thread, retain compatible instance state, and switch a fully
prepared graph at a defined boundary. Define note-off/chase and effect pre-roll/reset behavior for
stop, panic, seek and loops. The VST editor must affect the currently audible graph. Show actual
applied revision, CPU load, underruns and device status in the UI.

Acceptance: A mixed native/sample/VST song plays continuously, survives valid and invalid code
edits, and updates knobs audibly. Test repeated stop/seek/loop, long tails, plugin crash/hang and
device removal. Offline and live capture agree within deterministic or documented external-plugin
tolerances. Test 64/128/256/512-frame scheduling and deadline failure behavior. Do not equate block
duration with measured round-trip latency.

Verification and handoff: Add focused behavioral/regression tests for the described risks. Run
relevant tests plus the repository's required CI/type/lint/docs gates; at the audit baseline these
include pytest --cov, mypy src/prism, ruff check ., and mkdocs build --strict in the appropriate uv
extras. Preserve the separate real-VST workflow. Do not weaken gates, delete assertions, or equate
mocks with hardware/plugin qualification. Update the guide and runnable tutorial as required by
AGENTS.md. Read and update docs/development/implementation-status.md (create it if absent) with this
task number, completed scope, implemented API/compatibility decisions, verification and concrete
limitations. Use the GitHub connector to publish scoped verified changes on a dedicated branch and
finally open a pull request containing your changes. If an open PR already covers this task, update
that PR instead of creating a duplicate. Target main unless the supplied prerequisite work requires
an explicitly documented stacked PR. Include the task number, problem, implemented behavior,
compatibility decisions, exact verification results and remaining limitations in the PR description.
Check the published diff and CI results; fix failures caused by your changes and report pending or
blocked checks accurately. Return the PR URL, branch, final commit SHA and a concise handoff. A local
commit alone is not the final deliverable. Do not force-push or auto-merge. The next agent must be
able to start from this result.
```

<a id="task-23"></a>

## 23. Add live MIDI devices, performance controls, and MIDI recording

```text
Implementation task 23/35: Add live MIDI devices, performance controls, and MIDI recording

Repository: https://github.com/SeucheAchat9115/Prism
Repository workflow: Use the GitHub connector for all remote repository communication: reading
repository files, branches, pull requests, review feedback and CI results, and publishing commits,
branches and pull requests. Local file editing, builds, tests and local Git operations are allowed;
do not use shell git fetch/pull/push/clone, gh, curl or direct HTTP clients to contact GitHub.
Discover the connector tools available in your session. If connector access is unavailable or an
operation is blocked, preserve the local work and report the exact blocker; do not silently switch
to another remote transport.

Prism is a script-first Python music-production project. Preserve readable Python authoring and a
lightweight headless offline path while extending production and live workflows.
Audit baseline: 434f538242009e373b62da74c5d527b6bd9120eb, 2026-09-05. This is historical evidence,
not the branch to reset to. Work from the latest integrated implementation that contains the
required preceding tasks. Read AGENTS.md and inspect current code before editing; recheck whether an
audited defect is already fixed. Source paths below refer to the baseline and may have moved.
Implement this task completely, with code rather than only a plan or stubs. Preserve unrelated work,
use a dedicated branch/worktree, and make routine design decisions from the repository and these
requirements. Do not implement later tasks opportunistically. If a prerequisite is absent, resolve
its supplied branch/commit or report the precise dependency rather than inventing an incompatible
substitute.

Required preceding tasks: 4, 18, 22. All earlier integrated changes must remain present.
Where to start: compiled musical/control model; transport/device adapters; persistent host; project
serialization; new MIDI I/O modules.

Context and why: Authored MIDI and exported files do not let a producer play a keyboard, use
sustain, capture a performance, or map a controller to a synth knob.

Add MIDI device enumeration/selection, timestamped input, channel filtering, note handling, sustain
and general CC, modulation/pitch bend, aftertouch, and safe stop/panic. Define
per-plugin/native-instrument capability mapping instead of claiming every synth responds to every
controller. Support MIDI learn for stable parameter targets, controller pickup/relative encoders
where applicable, and serializable mappings.

Record MIDI into editable project clips with a defined transport origin, latency policy,
quantization option and preservation of raw timing. Provide metronome/count-in support through the
common transport rather than an unrelated timer. Add external MIDI output with explicit
latency/scheduling metadata. Implement MPE only where the event model and host can preserve
per-note/channel semantics; otherwise expose a clear capability limitation and document the
extension point.

Acceptance: Loopback/virtual-device tests exercise overlapping notes, sustain release, channel
separation, bend-range handling, hotplug, MIDI learn and panic with no stuck notes. Recorded clips
replay their notes and controllers correctly and export through the common MIDI path. Demonstrate
live playing with a real device where available; report hardware checks separately from virtual
tests.

Verification and handoff: Add focused behavioral/regression tests for the described risks. Run
relevant tests plus the repository's required CI/type/lint/docs gates; at the audit baseline these
include pytest --cov, mypy src/prism, ruff check ., and mkdocs build --strict in the appropriate uv
extras. Preserve the separate real-VST workflow. Do not weaken gates, delete assertions, or equate
mocks with hardware/plugin qualification. Update the guide and runnable tutorial as required by
AGENTS.md. Read and update docs/development/implementation-status.md (create it if absent) with this
task number, completed scope, implemented API/compatibility decisions, verification and concrete
limitations. Use the GitHub connector to publish scoped verified changes on a dedicated branch and
finally open a pull request containing your changes. If an open PR already covers this task, update
that PR instead of creating a duplicate. Target main unless the supplied prerequisite work requires
an explicitly documented stacked PR. Include the task number, problem, implemented behavior,
compatibility decisions, exact verification results and remaining limitations in the PR description.
Check the published diff and CI results; fix failures caused by your changes and report pending or
blocked checks accurately. Return the PR URL, branch, final commit SHA and a concise handoff. A local
commit alone is not the final deliverable. Do not force-push or auto-merge. The next agent must be
able to start from this result.
```

<a id="task-24"></a>

## 24. Expand routing, sidechains, multi-output plugins, and mixer controls

```text
Implementation task 24/35: Expand routing, sidechains, multi-output plugins, and mixer controls

Repository: https://github.com/SeucheAchat9115/Prism
Repository workflow: Use the GitHub connector for all remote repository communication: reading
repository files, branches, pull requests, review feedback and CI results, and publishing commits,
branches and pull requests. Local file editing, builds, tests and local Git operations are allowed;
do not use shell git fetch/pull/push/clone, gh, curl or direct HTTP clients to contact GitHub.
Discover the connector tools available in your session. If connector access is unavailable or an
operation is blocked, preserve the local work and report the exact blocker; do not silently switch
to another remote transport.

Prism is a script-first Python music-production project. Preserve readable Python authoring and a
lightweight headless offline path while extending production and live workflows.
Audit baseline: 434f538242009e373b62da74c5d527b6bd9120eb, 2026-09-05. This is historical evidence,
not the branch to reset to. Work from the latest integrated implementation that contains the
required preceding tasks. Read AGENTS.md and inspect current code before editing; recheck whether an
audited defect is already fixed. Source paths below refer to the baseline and may have moved.
Implement this task completely, with code rather than only a plan or stubs. Preserve unrelated work,
use a dedicated branch/worktree, and make routine design decisions from the repository and these
requirements. Do not implement later tasks opportunistically. If a prerequisite is absent, resolve
its supplied branch/commit or report the precise dependency rather than inventing an incompatible
substitute.

Required preceding tasks: 8, 10, 12, 19, 22. All earlier integrated changes must remain present.
Where to start: src/prism/project/builder.py: Track, Bus, Send; compiled graph; native/VST bus
adapters; stem modes; companion mixer UI.

Context and why: Prism has one-level buses and post-fader sends, but producers need group
hierarchies, sidechain compression, multi-output instruments, solo, and automated mixer controls.

Replace special-case routing with an explicit validated directed graph of typed audio ports. Add
bus-to-bus/group routing, pre/post-fader sends, stable selectable main outputs, sidechain inputs and
named outputs from multi-output VSTs. Negotiate layouts against actual plugin capabilities and
reject unsupported configurations early. Reject feedback cycles unless a separately designed
delayed-feedback feature exists; do not accidentally create zero-delay loops.

Add consistent mute/solo/solo-safe behavior, gain/pan/send-level automation and clear mono-pan
versus stereo-balance rules. Reuse the parameter-envelope system and update graph latency
compensation. Keep old track/bus/send syntax as a compatibility adapter. Extend production stem
selection to top-level master inputs without duplicate paths, and expose routing/meters in the
existing companion UI.

Acceptance: Test nested groups, pre/post sends, group mute/solo, return solo-safe, automation, and
invalid cycles. Controlled VST fixtures establish sidechain action and separately routed outputs;
unsupported plugins fail clearly. Offline/live graphs and stems agree on routing, latency and
levels. Add producer examples for kick-driven bass ducking and a multi-output instrument.

Verification and handoff: Add focused behavioral/regression tests for the described risks. Run
relevant tests plus the repository's required CI/type/lint/docs gates; at the audit baseline these
include pytest --cov, mypy src/prism, ruff check ., and mkdocs build --strict in the appropriate uv
extras. Preserve the separate real-VST workflow. Do not weaken gates, delete assertions, or equate
mocks with hardware/plugin qualification. Update the guide and runnable tutorial as required by
AGENTS.md. Read and update docs/development/implementation-status.md (create it if absent) with this
task number, completed scope, implemented API/compatibility decisions, verification and concrete
limitations. Use the GitHub connector to publish scoped verified changes on a dedicated branch and
finally open a pull request containing your changes. If an open PR already covers this task, update
that PR instead of creating a duplicate. Target main unless the supplied prerequisite work requires
an explicitly documented stacked PR. Include the task number, problem, implemented behavior,
compatibility decisions, exact verification results and remaining limitations in the PR description.
Check the published diff and CI results; fix failures caused by your changes and report pending or
blocked checks accurately. Return the PR URL, branch, final commit SHA and a concise handoff. A local
commit alone is not the final deliverable. Do not force-push or auto-merge. The next agent must be
able to start from this result.
```

<a id="task-25"></a>

## 25. Add tempo maps, meter changes, and reusable musical structures

```text
Implementation task 25/35: Add tempo maps, meter changes, and reusable musical structures

Repository: https://github.com/SeucheAchat9115/Prism
Repository workflow: Use the GitHub connector for all remote repository communication: reading
repository files, branches, pull requests, review feedback and CI results, and publishing commits,
branches and pull requests. Local file editing, builds, tests and local Git operations are allowed;
do not use shell git fetch/pull/push/clone, gh, curl or direct HTTP clients to contact GitHub.
Discover the connector tools available in your session. If connector access is unavailable or an
operation is blocked, preserve the local work and report the exact blocker; do not silently switch
to another remote transport.

Prism is a script-first Python music-production project. Preserve readable Python authoring and a
lightweight headless offline path while extending production and live workflows.
Audit baseline: 434f538242009e373b62da74c5d527b6bd9120eb, 2026-09-05. This is historical evidence,
not the branch to reset to. Work from the latest integrated implementation that contains the
required preceding tasks. Read AGENTS.md and inspect current code before editing; recheck whether an
audited defect is already fixed. Source paths below refer to the baseline and may have moved.
Implement this task completely, with code rather than only a plan or stubs. Preserve unrelated work,
use a dedicated branch/worktree, and make routine design decisions from the repository and these
requirements. Do not implement later tasks opportunistically. If a prerequisite is absent, resolve
its supplied branch/commit or report the precise dependency rather than inventing an incompatible
substitute.

Required preceding tasks: 2, 4, 14, 19, 22. All earlier integrated changes must remain present.
Where to start: shared timing and compiled arrangement modules; Project/Section/Clip authoring APIs;
MIDI exporter; native/VST transport context.

Context and why: The initial timing fix establishes a correct constant-tempo clock, but full
arrangements benefit from tempo/meter changes, named reusable sections, markers, and pattern
transformations.

Extend the timing model to explicit tempo and meter maps with tested beat-to-time and inverse
conversion. Define supported tempo interpolation (such as step and linear ramps), legal meter-change
boundaries, and interpretation of authored bar positions when meter changes. Deliver consistent
audio scheduling, MIDI tempo/signature events, automation positions, playhead mapping and host
transport context.

Add reusable section/pattern definitions and separate arrangement instances with stable identities.
Support deliberate repetition, transposition, velocity scaling and deterministic variation without
mutating shared originals. Add arrangement markers and clarify clip-scoped versus global automation.
Avoid making the compiler infer meter from visual bar separators in notation.

Acceptance: Test tempo ramps, meter transitions, seek/loop across changes, long arrangements and
round-trip time conversion within defined tolerances. Exported MIDI tempo events and audio note
onsets agree; provide known fixtures for the later MIDI import task. Reusing one pattern in several
sections does not leak edits or stochastic state between instances. Legacy constant-tempo projects
remain compatible and a complete tutorial demonstrates a reusable verse/chorus arrangement.

Verification and handoff: Add focused behavioral/regression tests for the described risks. Run
relevant tests plus the repository's required CI/type/lint/docs gates; at the audit baseline these
include pytest --cov, mypy src/prism, ruff check ., and mkdocs build --strict in the appropriate uv
extras. Preserve the separate real-VST workflow. Do not weaken gates, delete assertions, or equate
mocks with hardware/plugin qualification. Update the guide and runnable tutorial as required by
AGENTS.md. Read and update docs/development/implementation-status.md (create it if absent) with this
task number, completed scope, implemented API/compatibility decisions, verification and concrete
limitations. Use the GitHub connector to publish scoped verified changes on a dedicated branch and
finally open a pull request containing your changes. If an open PR already covers this task, update
that PR instead of creating a duplicate. Target main unless the supplied prerequisite work requires
an explicitly documented stacked PR. Include the task number, problem, implemented behavior,
compatibility decisions, exact verification results and remaining limitations in the PR description.
Check the published diff and CI results; fix failures caused by your changes and report pending or
blocked checks accurately. Return the PR URL, branch, final commit SHA and a concise handoff. A local
commit alone is not the final deliverable. Do not force-push or auto-merge. The next agent must be
able to start from this result.
```

<a id="task-26"></a>

## 26. Implement MIDI import and reliable larger-session interchange

```text
Implementation task 26/35: Implement MIDI import and reliable larger-session interchange

Repository: https://github.com/SeucheAchat9115/Prism
Repository workflow: Use the GitHub connector for all remote repository communication: reading
repository files, branches, pull requests, review feedback and CI results, and publishing commits,
branches and pull requests. Local file editing, builds, tests and local Git operations are allowed;
do not use shell git fetch/pull/push/clone, gh, curl or direct HTTP clients to contact GitHub.
Discover the connector tools available in your session. If connector access is unavailable or an
operation is blocked, preserve the local work and report the exact blocker; do not silently switch
to another remote transport.

Prism is a script-first Python music-production project. Preserve readable Python authoring and a
lightweight headless offline path while extending production and live workflows.
Audit baseline: 434f538242009e373b62da74c5d527b6bd9120eb, 2026-09-05. This is historical evidence,
not the branch to reset to. Work from the latest integrated implementation that contains the
required preceding tasks. Read AGENTS.md and inspect current code before editing; recheck whether an
audited defect is already fixed. Source paths below refer to the baseline and may have moved.
Implement this task completely, with code rather than only a plan or stubs. Preserve unrelated work,
use a dedicated branch/worktree, and make routine design decisions from the repository and these
requirements. Do not implement later tasks opportunistically. If a prerequisite is absent, resolve
its supplied branch/commit or report the precise dependency rather than inventing an incompatible
substitute.

Required preceding tasks: 4, 13, 23, 25. All earlier integrated changes must remain present.
Where to start: src/prism/midi.py; compiled event/timing model; Project MIDI clip API; export
profiles/manifests.

Context and why: Prism can export notes but cannot import MIDI, and its single-file channel
assignment limits melodic tracks to 15. Producers need to bring in performances and exchange larger
arrangements without losing tempo, expression or track structure.

Implement Standard MIDI File import with tempo/meter maps, track names, note pairs, velocities,
supported controllers, program/bank metadata and clear source timing. Handle running status,
overlapping same-pitch notes, malformed events and unsupported messages without silently corrupting
music. Preserve unhandled metadata where practical and report losses.

Add selectable merged, per-track, and explicitly port-aware export strategies rather than silently
reusing channels for unrelated controller state. Preserve the current simple format-1 path. Provide
an explicit instrument mapping step; a MIDI file does not contain VST audio, licenses or complete
patch state. Bind imported project paths and assets through the public root/build contract.

Acceptance: Round-trip fixtures preserve musical note/control timing and tempo/meter maps within
declared MIDI quantization. Test more than 15 melodic tracks, percussion channels, multiple ports,
sustain/aftertouch and empty tracks. Compare imported playback with a known event timeline and
validate serialized files independently. Document exactly which information MIDI interchange cannot
preserve.

Verification and handoff: Add focused behavioral/regression tests for the described risks. Run
relevant tests plus the repository's required CI/type/lint/docs gates; at the audit baseline these
include pytest --cov, mypy src/prism, ruff check ., and mkdocs build --strict in the appropriate uv
extras. Preserve the separate real-VST workflow. Do not weaken gates, delete assertions, or equate
mocks with hardware/plugin qualification. Update the guide and runnable tutorial as required by
AGENTS.md. Read and update docs/development/implementation-status.md (create it if absent) with this
task number, completed scope, implemented API/compatibility decisions, verification and concrete
limitations. Use the GitHub connector to publish scoped verified changes on a dedicated branch and
finally open a pull request containing your changes. If an open PR already covers this task, update
that PR instead of creating a duplicate. Target main unless the supplied prerequisite work requires
an explicitly documented stacked PR. Include the task number, problem, implemented behavior,
compatibility decisions, exact verification results and remaining limitations in the PR description.
Check the published diff and CI results; fix failures caused by your changes and report pending or
blocked checks accurately. Return the PR URL, branch, final commit SHA and a concise handoff. A local
commit alone is not the final deliverable. Do not force-push or auto-merge. The next agent must be
able to start from this result.
```

<a id="task-27"></a>

## 27. Implement proper time stretching and non-destructive audio edits

```text
Implementation task 27/35: Implement proper time stretching and non-destructive audio edits

Repository: https://github.com/SeucheAchat9115/Prism
Repository workflow: Use the GitHub connector for all remote repository communication: reading
repository files, branches, pull requests, review feedback and CI results, and publishing commits,
branches and pull requests. Local file editing, builds, tests and local Git operations are allowed;
do not use shell git fetch/pull/push/clone, gh, curl or direct HTTP clients to contact GitHub.
Discover the connector tools available in your session. If connector access is unavailable or an
operation is blocked, preserve the local work and report the exact blocker; do not silently switch
to another remote transport.

Prism is a script-first Python music-production project. Preserve readable Python authoring and a
lightweight headless offline path while extending production and live workflows.
Audit baseline: 434f538242009e373b62da74c5d527b6bd9120eb, 2026-09-05. This is historical evidence,
not the branch to reset to. Work from the latest integrated implementation that contains the
required preceding tasks. Read AGENTS.md and inspect current code before editing; recheck whether an
audited defect is already fixed. Source paths below refer to the baseline and may have moved.
Implement this task completely, with code rather than only a plan or stubs. Preserve unrelated work,
use a dedicated branch/worktree, and make routine design decisions from the repository and these
requirements. Do not implement later tasks opportunistically. If a prerequisite is absent, resolve
its supplied branch/commit or report the precise dependency rather than inventing an incompatible
substitute.

Required preceding tasks: 2, 6, 13, 15, 19, 25. All earlier integrated changes must remain present.
Where to start: src/prism/render.py: _prepare_audio, _time_resize; AudioClip/SampleClip models;
source fingerprints/cache; native sample processor; companion waveform view.

Context and why: Linear resizing changes speed and pitch together, and subsequent stretch can undo
transpose. Audio production also needs slices, crossfades and edits that do not modify original
recordings.

Separate source playback-rate changes, pitch-preserving duration changes, and independent pitch
shifting in the public API. Keep legacy tape-speed behavior explicitly selectable. Evaluate a
suitable maintained backend such as Rubber Band using primary documentation and actual fixtures;
handle its latency, variable input/output frame relationship and flush/tail behavior correctly. Keep
optional dependencies clearly packaged and fail with useful instructions when unavailable.

Represent trim, reverse, fades, pitch/time operations, transient slices and crossfades as
non-destructive edit descriptions referencing source content. Add explicit warp markers or beat
alignment for loops. Preserve source files and fingerprint prepared results. For live use, prepare
expensive warps in the background or use a verified streaming mode; never run offline stretching in
the audio callback.

Acceptance: Stretching a 440 Hz tone to twice its length keeps 440 Hz in preserve-pitch mode;
combining +12 semitones with that duration yields 880 Hz. Test exact output length, stereo
coherence, transients, vocals, extreme allowed ratios, and edit order. Slice/crossfade operations
avoid unintended gaps/clicks and leave source hashes unchanged. Provide sound examples and disclose
quality tradeoffs rather than relying only on frequency tests.

Verification and handoff: Add focused behavioral/regression tests for the described risks. Run
relevant tests plus the repository's required CI/type/lint/docs gates; at the audit baseline these
include pytest --cov, mypy src/prism, ruff check ., and mkdocs build --strict in the appropriate uv
extras. Preserve the separate real-VST workflow. Do not weaken gates, delete assertions, or equate
mocks with hardware/plugin qualification. Update the guide and runnable tutorial as required by
AGENTS.md. Read and update docs/development/implementation-status.md (create it if absent) with this
task number, completed scope, implemented API/compatibility decisions, verification and concrete
limitations. Use the GitHub connector to publish scoped verified changes on a dedicated branch and
finally open a pull request containing your changes. If an open PR already covers this task, update
that PR instead of creating a duplicate. Target main unless the supplied prerequisite work requires
an explicitly documented stacked PR. Include the task number, problem, implemented behavior,
compatibility decisions, exact verification results and remaining limitations in the PR description.
Check the published diff and CI results; fix failures caused by your changes and report pending or
blocked checks accurately. Return the PR URL, branch, final commit SHA and a concise handoff. A local
commit alone is not the final deliverable. Do not force-push or auto-merge. The next agent must be
able to start from this result.
```

<a id="task-28"></a>

## 28. Add essential mixing processors and trustworthy loudness meters

```text
Implementation task 28/35: Add essential mixing processors and trustworthy loudness meters

Repository: https://github.com/SeucheAchat9115/Prism
Repository workflow: Use the GitHub connector for all remote repository communication: reading
repository files, branches, pull requests, review feedback and CI results, and publishing commits,
branches and pull requests. Local file editing, builds, tests and local Git operations are allowed;
do not use shell git fetch/pull/push/clone, gh, curl or direct HTTP clients to contact GitHub.
Discover the connector tools available in your session. If connector access is unavailable or an
operation is blocked, preserve the local work and report the exact blocker; do not silently switch
to another remote transport.

Prism is a script-first Python music-production project. Preserve readable Python authoring and a
lightweight headless offline path while extending production and live workflows.
Audit baseline: 434f538242009e373b62da74c5d527b6bd9120eb, 2026-09-05. This is historical evidence,
not the branch to reset to. Work from the latest integrated implementation that contains the
required preceding tasks. Read AGENTS.md and inspect current code before editing; recheck whether an
audited defect is already fixed. Source paths below refer to the baseline and may have moved.
Implement this task completely, with code rather than only a plan or stubs. Preserve unrelated work,
use a dedicated branch/worktree, and make routine design decisions from the repository and these
requirements. Do not implement later tasks opportunistically. If a prerequisite is absent, resolve
its supplied branch/commit or report the precise dependency rather than inventing an incompatible
substitute.

Required preceding tasks: 11, 19, 20, 22, 24. All earlier integrated changes must remain present.
Where to start: stock plugin registry and native processor adapters; export analysis/results; mixer
UI; processor tests.

Context and why: Basic filtering and compression are useful, but producers also need a parametric
EQ, high-pass filtering, a limiter, stereo utility and meaningful peak/loudness analysis. A
compressor or peak attenuation is not a true-peak limiter or LUFS normalization.

Implement a usable parametric EQ with high/low-pass and bell/shelf bands, stereo
gain/balance/width/mono/polarity utility, and a clearly specified limiter. Use the stateful/native
processor contracts, report lookahead latency, and keep live versus offline quality modes explicit.
Provide readable parameter units/ranges and automation smoothing where appropriate.

Add sample peak, RMS, integrated/short-term loudness and true-peak analysis using a verified
standard implementation or established test vectors. Check current primary specifications when
choosing BS.1770/EBU-related behavior and distinguish the measurement standard from any delivery
target. Analyze final delivery-rate audio and add optional loudness-target export with measured peak
constraints; never silently compress the mix to meet a target.

Acceptance: Frequency/impulse tests verify EQ bands and stability, routing tests verify stereo
utilities, and reference vectors establish loudness/true-peak accuracy. Limiter tests cover
impulses, intersample peaks, oversampling, stereo linking, latency and tails. UI meters agree with
export analysis within their documented windowing. Provide practical producer tutorials and
meaningful defaults without claiming every track should use one universal LUFS target.

Verification and handoff: Add focused behavioral/regression tests for the described risks. Run
relevant tests plus the repository's required CI/type/lint/docs gates; at the audit baseline these
include pytest --cov, mypy src/prism, ruff check ., and mkdocs build --strict in the appropriate uv
extras. Preserve the separate real-VST workflow. Do not weaken gates, delete assertions, or equate
mocks with hardware/plugin qualification. Update the guide and runnable tutorial as required by
AGENTS.md. Read and update docs/development/implementation-status.md (create it if absent) with this
task number, completed scope, implemented API/compatibility decisions, verification and concrete
limitations. Use the GitHub connector to publish scoped verified changes on a dedicated branch and
finally open a pull request containing your changes. If an open PR already covers this task, update
that PR instead of creating a duplicate. Target main unless the supplied prerequisite work requires
an explicitly documented stacked PR. Include the task number, problem, implemented behavior,
compatibility decisions, exact verification results and remaining limitations in the PR description.
Check the published diff and CI results; fix failures caused by your changes and report pending or
blocked checks accurately. Return the PR URL, branch, final commit SHA and a concise handoff. A local
commit alone is not the final deliverable. Do not force-push or auto-merge. The next agent must be
able to start from this result.
```

<a id="task-29"></a>

## 29. Improve native synthesis quality without silently changing old songs

```text
Implementation task 29/35: Improve native synthesis quality without silently changing old songs

Repository: https://github.com/SeucheAchat9115/Prism
Repository workflow: Use the GitHub connector for all remote repository communication: reading
repository files, branches, pull requests, review feedback and CI results, and publishing commits,
branches and pull requests. Local file editing, builds, tests and local Git operations are allowed;
do not use shell git fetch/pull/push/clone, gh, curl or direct HTTP clients to contact GitHub.
Discover the connector tools available in your session. If connector access is unavailable or an
operation is blocked, preserve the local work and report the exact blocker; do not silently switch
to another remote transport.

Prism is a script-first Python music-production project. Preserve readable Python authoring and a
lightweight headless offline path while extending production and live workflows.
Audit baseline: 434f538242009e373b62da74c5d527b6bd9120eb, 2026-09-05. This is historical evidence,
not the branch to reset to. Work from the latest integrated implementation that contains the
required preceding tasks. Read AGENTS.md and inspect current code before editing; recheck whether an
audited defect is already fixed. Source paths below refer to the baseline and may have moved.
Implement this task completely, with code rather than only a plan or stubs. Preserve unrelated work,
use a dedicated branch/worktree, and make routine design decisions from the repository and these
requirements. Do not implement later tasks opportunistically. If a prerequisite is absent, resolve
its supplied branch/commit or report the precise dependency rather than inventing an incompatible
substitute.

Required preceding tasks: 7, 19, 20, 22. All earlier integrated changes must remain present.
Where to start: src/prism/synthesis/engine.py; src/prism/synthesis/types.py;
src/prism/stock_plugins/uniwave.py; native oscillator/envelope/filter kernels.

Context and why: Native saw/square oscillators use direct discontinuous waveforms, and the synthesis
wrapper applies fixed nonlinear shaping. This can alias and makes a nominally clean sound less
predictable. Uniwave would also benefit from explicit stereo voice design.

Add band-limited oscillator generation using an appropriate approach such as polyBLEP/minBLEP or
band-limited tables, and optional oversampling for nonlinear stages. Make drive/saturation and
quality mode explicit. Implement intentional stereo/unison behavior, phase/randomization policies
and deterministic seeds without merely duplicating mono output and labeling it wide.

Preserve legacy sound through a versioned sound/quality mode; new defaults can change only with a
documented migration. Reuse native/stateful kernels and account for oversampling/filter latency in
the graph. Keep modulation, envelope lifetime and sample scheduling consistent with prior fixes.
Avoid broadening this into a full wavetable-synth replacement.

Acceptance: Spectral tests compare unwanted aliases with a band-limited reference across
pitch/sample rates. Check gain, DC, finite output, stereo correlation, voice overlap, deterministic
seeds and automated parameters. Offline/live parity holds in the same quality mode. Publish small
before/after listening examples and benchmark cost so producers can choose quality deliberately.

Verification and handoff: Add focused behavioral/regression tests for the described risks. Run
relevant tests plus the repository's required CI/type/lint/docs gates; at the audit baseline these
include pytest --cov, mypy src/prism, ruff check ., and mkdocs build --strict in the appropriate uv
extras. Preserve the separate real-VST workflow. Do not weaken gates, delete assertions, or equate
mocks with hardware/plugin qualification. Update the guide and runnable tutorial as required by
AGENTS.md. Read and update docs/development/implementation-status.md (create it if absent) with this
task number, completed scope, implemented API/compatibility decisions, verification and concrete
limitations. Use the GitHub connector to publish scoped verified changes on a dedicated branch and
finally open a pull request containing your changes. If an open PR already covers this task, update
that PR instead of creating a duplicate. Target main unless the supplied prerequisite work requires
an explicitly documented stacked PR. Include the task number, problem, implemented behavior,
compatibility decisions, exact verification results and remaining limitations in the PR description.
Check the published diff and CI results; fix failures caused by your changes and report pending or
blocked checks accurately. Return the PR URL, branch, final commit SHA and a concise handoff. A local
commit alone is not the final deliverable. Do not force-push or auto-merge. The next agent must be
able to start from this result.
```

<a id="task-30"></a>

## 30. Add sound browsing, asset repair, freeze, and portable project bundles

```text
Implementation task 30/35: Add sound browsing, asset repair, freeze, and portable project bundles

Repository: https://github.com/SeucheAchat9115/Prism
Repository workflow: Use the GitHub connector for all remote repository communication: reading
repository files, branches, pull requests, review feedback and CI results, and publishing commits,
branches and pull requests. Local file editing, builds, tests and local Git operations are allowed;
do not use shell git fetch/pull/push/clone, gh, curl or direct HTTP clients to contact GitHub.
Discover the connector tools available in your session. If connector access is unavailable or an
operation is blocked, preserve the local work and report the exact blocker; do not silently switch
to another remote transport.

Prism is a script-first Python music-production project. Preserve readable Python authoring and a
lightweight headless offline path while extending production and live workflows.
Audit baseline: 434f538242009e373b62da74c5d527b6bd9120eb, 2026-09-05. This is historical evidence,
not the branch to reset to. Work from the latest integrated implementation that contains the
required preceding tasks. Read AGENTS.md and inspect current code before editing; recheck whether an
audited defect is already fixed. Source paths below refer to the baseline and may have moved.
Implement this task completely, with code rather than only a plan or stubs. Preserve unrelated work,
use a dedicated branch/worktree, and make routine design decisions from the repository and these
requirements. Do not implement later tasks opportunistically. If a prerequisite is absent, resolve
its supplied branch/commit or report the precise dependency rather than inventing an incompatible
substitute.

Required preceding tasks: 13, 15, 18, 24, 27. All earlier integrated changes must remain present.
Where to start: src/prism/sample_library.py; VST registry and inspector; project fingerprints/cache;
companion UI; export profiles; native source processor.

Context and why: Project-local file lookup is useful but offers no audible browsing, favorites,
missing-asset repair or robust handoff to a machine without the original plugins.

Add sample and preset browsing with audition routed through the established player, tags/favorites,
useful metadata and explicit import/copy from external folders. Keep discovery bounded and
user-directed; avoid silently scanning the entire machine. Parameter/preset inspection must use the
existing isolated host and preserve current playback when a candidate fails.

Implement missing-asset relinking with content-aware verification and clear ambiguity handling. Add
freeze/bounce that captures a defined graph stage, its time range, source/config/plugin fingerprint
and audio, with explicit unfreeze/invalidation behavior. Handle shared returns, sidechains and
upstream dependencies correctly; a frozen result must never silently stand in for newly edited
settings.

Create a collect/project-bundle workflow containing permitted project assets, state, manifests and
optional frozen audio. Do not copy commercial plugin binaries or assume plugin-private state embeds
every external sample/wavetable. Report unresolved external dependencies and let the recipient use
freeze audio when appropriate.

Acceptance: Browser audition, missing files/duplicates, relinking, moved projects, stale freeze
detection and clean-machine reopening are exercised. Source files remain protected, portable
identity survives relocation, and a bundle with frozen parts can render without its original VST
installation. Add a producer-friendly sharing checklist tied to actual bundle diagnostics.

Verification and handoff: Add focused behavioral/regression tests for the described risks. Run
relevant tests plus the repository's required CI/type/lint/docs gates; at the audit baseline these
include pytest --cov, mypy src/prism, ruff check ., and mkdocs build --strict in the appropriate uv
extras. Preserve the separate real-VST workflow. Do not weaken gates, delete assertions, or equate
mocks with hardware/plugin qualification. Update the guide and runnable tutorial as required by
AGENTS.md. Read and update docs/development/implementation-status.md (create it if absent) with this
task number, completed scope, implemented API/compatibility decisions, verification and concrete
limitations. Use the GitHub connector to publish scoped verified changes on a dedicated branch and
finally open a pull request containing your changes. If an open PR already covers this task, update
that PR instead of creating a duplicate. Target main unless the supplied prerequisite work requires
an explicitly documented stacked PR. Include the task number, problem, implemented behavior,
compatibility decisions, exact verification results and remaining limitations in the PR description.
Check the published diff and CI results; fix failures caused by your changes and report pending or
blocked checks accurately. Return the PR URL, branch, final commit SHA and a concise handoff. A local
commit alone is not the final deliverable. Do not force-push or auto-merge. The next agent must be
able to start from this result.
```

<a id="task-31"></a>

## 31. Add audio input, monitoring, and reliable recording

```text
Implementation task 31/35: Add audio input, monitoring, and reliable recording

Repository: https://github.com/SeucheAchat9115/Prism
Repository workflow: Use the GitHub connector for all remote repository communication: reading
repository files, branches, pull requests, review feedback and CI results, and publishing commits,
branches and pull requests. Local file editing, builds, tests and local Git operations are allowed;
do not use shell git fetch/pull/push/clone, gh, curl or direct HTTP clients to contact GitHub.
Discover the connector tools available in your session. If connector access is unavailable or an
operation is blocked, preserve the local work and report the exact blocker; do not silently switch
to another remote transport.

Prism is a script-first Python music-production project. Preserve readable Python authoring and a
lightweight headless offline path while extending production and live workflows.
Audit baseline: 434f538242009e373b62da74c5d527b6bd9120eb, 2026-09-05. This is historical evidence,
not the branch to reset to. Work from the latest integrated implementation that contains the
required preceding tasks. Read AGENTS.md and inspect current code before editing; recheck whether an
audited defect is already fixed. Source paths below refer to the baseline and may have moved.
Implement this task completely, with code rather than only a plan or stubs. Preserve unrelated work,
use a dedicated branch/worktree, and make routine design decisions from the repository and these
requirements. Do not implement later tasks opportunistically. If a prerequisite is absent, resolve
its supplied branch/commit or report the precise dependency rather than inventing an incompatible
substitute.

Required preceding tasks: 1, 13, 18, 22, 23, 24. All earlier integrated changes must remain present.
Where to start: native audio-device/transport engine; routing graph; project asset model; companion
UI; recording result/manifest modules.

Context and why: Prism can import recordings but cannot capture vocals/instruments or monitor audio
inputs. This is a core gap for full DAW use.

Add audio input enumeration and channel selection, track arming, monitoring modes,
count-in/metronome, and multitrack recording tied to the same transport sample clock. Feed
monitoring through the routing/latency model and make direct versus software monitoring clear. Begin
capture only when the producer explicitly arms/starts it; automated tests should use synthetic
loopback input.

Use bounded preallocated capture buffers with disk writing off the audio callback. Preserve samples
on overload according to a documented policy and report dropouts instead of silently claiming a
complete take. Align recorded material using measured/reported input/output and monitoring latency
with an explicit calibration offset. Handle device loss, cancellation, crashes and disk-full
conditions so a recoverable partial take is not discarded.

Acceptance: Synthetic loopback establishes alignment, channel ordering, transport origin and
long-recording continuity. Fault tests cover slow disk, buffer overrun and device removal. A real
hardware capture/monitoring check is performed where available and reported honestly. Captured files
appear as non-destructive clips with manifests, source protection and no overwrite of prior
recordings. Provide a first-vocal-recording tutorial.

Verification and handoff: Add focused behavioral/regression tests for the described risks. Run
relevant tests plus the repository's required CI/type/lint/docs gates; at the audit baseline these
include pytest --cov, mypy src/prism, ruff check ., and mkdocs build --strict in the appropriate uv
extras. Preserve the separate real-VST workflow. Do not weaken gates, delete assertions, or equate
mocks with hardware/plugin qualification. Update the guide and runnable tutorial as required by
AGENTS.md. Read and update docs/development/implementation-status.md (create it if absent) with this
task number, completed scope, implemented API/compatibility decisions, verification and concrete
limitations. Use the GitHub connector to publish scoped verified changes on a dedicated branch and
finally open a pull request containing your changes. If an open PR already covers this task, update
that PR instead of creating a duplicate. Target main unless the supplied prerequisite work requires
an explicitly documented stacked PR. Include the task number, problem, implemented behavior,
compatibility decisions, exact verification results and remaining limitations in the PR description.
Check the published diff and CI results; fix failures caused by your changes and report pending or
blocked checks accurately. Return the PR URL, branch, final commit SHA and a concise handoff. A local
commit alone is not the final deliverable. Do not force-push or auto-merge. The next agent must be
able to start from this result.
```

<a id="task-32"></a>

## 32. Add takes, comping, punch recording, and recoverable edit history

```text
Implementation task 32/35: Add takes, comping, punch recording, and recoverable edit history

Repository: https://github.com/SeucheAchat9115/Prism
Repository workflow: Use the GitHub connector for all remote repository communication: reading
repository files, branches, pull requests, review feedback and CI results, and publishing commits,
branches and pull requests. Local file editing, builds, tests and local Git operations are allowed;
do not use shell git fetch/pull/push/clone, gh, curl or direct HTTP clients to contact GitHub.
Discover the connector tools available in your session. If connector access is unavailable or an
operation is blocked, preserve the local work and report the exact blocker; do not silently switch
to another remote transport.

Prism is a script-first Python music-production project. Preserve readable Python authoring and a
lightweight headless offline path while extending production and live workflows.
Audit baseline: 434f538242009e373b62da74c5d527b6bd9120eb, 2026-09-05. This is historical evidence,
not the branch to reset to. Work from the latest integrated implementation that contains the
required preceding tasks. Read AGENTS.md and inspect current code before editing; recheck whether an
audited defect is already fixed. Source paths below refer to the baseline and may have moved.
Implement this task completely, with code rather than only a plan or stubs. Preserve unrelated work,
use a dedicated branch/worktree, and make routine design decisions from the repository and these
requirements. Do not implement later tasks opportunistically. If a prerequisite is absent, resolve
its supplied branch/commit or report the precise dependency rather than inventing an incompatible
substitute.

Required preceding tasks: 18, 27, 30, 31. All earlier integrated changes must remain present.
Where to start: recording lifecycle and clip edit models; companion timeline UI;
project/version/state persistence; safe asset management.

Context and why: Capturing one WAV is not a complete recording workflow. Producers need repeated
takes, selection of the best passages, punch-in/out, crossfades, and confidence that edits can be
undone.

Implement take lanes and non-destructive comp regions referencing original captures. Add
transport-aligned punch ranges and loop recording, retaining all captured takes. Reuse the existing
slice/crossfade/warp model and define monitoring behavior at punch boundaries. Preserve source
alignment, tempo-map semantics and tails when switching takes.

Add undo/redo for structured project edits and autosaved recoverable snapshots, with an explicit
relationship to the Python build source. Do not rewrite arbitrary Python syntax or silently
overwrite external script edits. Store supported UI edits in an explicit versioned overlay/state
artifact referenced by the project and provide an intentional save/export-to-script workflow where
safely representable. Recover interrupted recordings and edits without deleting sources.

Acceptance: Punch and loop captures create correctly positioned independent takes. Comp playback has
no accidental gaps, duplicates or clicks; undo/redo reproduces previous sound and asset references.
Test crash recovery, disk failure, concurrent external Python edits and stale state conflicts. A
tutorial demonstrates recording three takes, making a comp and reverting edits while retaining every
original.

Verification and handoff: Add focused behavioral/regression tests for the described risks. Run
relevant tests plus the repository's required CI/type/lint/docs gates; at the audit baseline these
include pytest --cov, mypy src/prism, ruff check ., and mkdocs build --strict in the appropriate uv
extras. Preserve the separate real-VST workflow. Do not weaken gates, delete assertions, or equate
mocks with hardware/plugin qualification. Update the guide and runnable tutorial as required by
AGENTS.md. Read and update docs/development/implementation-status.md (create it if absent) with this
task number, completed scope, implemented API/compatibility decisions, verification and concrete
limitations. Use the GitHub connector to publish scoped verified changes on a dedicated branch and
finally open a pull request containing your changes. If an open PR already covers this task, update
that PR instead of creating a duplicate. Target main unless the supplied prerequisite work requires
an explicitly documented stacked PR. Include the task number, problem, implemented behavior,
compatibility decisions, exact verification results and remaining limitations in the PR description.
Check the published diff and CI results; fix failures caused by your changes and report pending or
blocked checks accurately. Return the PR URL, branch, final commit SHA and a concise handoff. A local
commit alone is not the final deliverable. Do not force-push or auto-merge. The next agent must be
able to start from this result.
```

<a id="task-33"></a>

## 33. Add lossless and compressed listening export formats

```text
Implementation task 33/35: Add lossless and compressed listening export formats

Repository: https://github.com/SeucheAchat9115/Prism
Repository workflow: Use the GitHub connector for all remote repository communication: reading
repository files, branches, pull requests, review feedback and CI results, and publishing commits,
branches and pull requests. Local file editing, builds, tests and local Git operations are allowed;
do not use shell git fetch/pull/push/clone, gh, curl or direct HTTP clients to contact GitHub.
Discover the connector tools available in your session. If connector access is unavailable or an
operation is blocked, preserve the local work and report the exact blocker; do not silently switch
to another remote transport.

Prism is a script-first Python music-production project. Preserve readable Python authoring and a
lightweight headless offline path while extending production and live workflows.
Audit baseline: 434f538242009e373b62da74c5d527b6bd9120eb, 2026-09-05. This is historical evidence,
not the branch to reset to. Work from the latest integrated implementation that contains the
required preceding tasks. Read AGENTS.md and inspect current code before editing; recheck whether an
audited defect is already fixed. Source paths below refer to the baseline and may have moved.
Implement this task completely, with code rather than only a plan or stubs. Preserve unrelated work,
use a dedicated branch/worktree, and make routine design decisions from the repository and these
requirements. Do not implement later tasks opportunistically. If a prerequisite is absent, resolve
its supplied branch/commit or report the precise dependency rather than inventing an incompatible
substitute.

Required preceding tasks: 1, 11, 12, 13, 28. All earlier integrated changes must remain present.
Where to start: export settings/profiles, encoder abstraction, analysis/manifests; CLI render;
optional packaging dependencies.

Context and why: WAV is appropriate for production, but FLAC and convenient compressed listening
copies reduce handoff and preview friction. MIDI remains a separate musical-data format.

Introduce a narrow encoder interface downstream of the common render/delivery pipeline. Implement
FLAC and optional MP3/AAC/Opus profiles where the chosen encoder actually supports them. Verify
supported rates, channels, sample formats, tags and encoder licensing/distribution requirements from
primary documentation; expose capabilities rather than accepting settings an encoder silently
changes.

Keep encoder dependencies optional and fail early with actionable setup information. Preserve
WAV/float headroom behavior. Define lossy encoder delay/padding and loudness/peak analysis
semantics. Reuse safe staged publication and manifests; record actual codec/encoder settings and
versions. Never claim byte-identical lossy output across encoder builds, or that a compressed file
is suitable for additive production stems without qualification.

Acceptance: Independently decode generated files and verify codec, duration accounting, layout,
metadata and finite non-silent audio. Test missing encoders, unsupported profiles, cancellation,
failed writes and reproducible settings. Existing WAV master/stem tests remain intact. Provide named
master/stem/listening profiles and document why producers would choose each.

Verification and handoff: Add focused behavioral/regression tests for the described risks. Run
relevant tests plus the repository's required CI/type/lint/docs gates; at the audit baseline these
include pytest --cov, mypy src/prism, ruff check ., and mkdocs build --strict in the appropriate uv
extras. Preserve the separate real-VST workflow. Do not weaken gates, delete assertions, or equate
mocks with hardware/plugin qualification. Update the guide and runnable tutorial as required by
AGENTS.md. Read and update docs/development/implementation-status.md (create it if absent) with this
task number, completed scope, implemented API/compatibility decisions, verification and concrete
limitations. Use the GitHub connector to publish scoped verified changes on a dedicated branch and
finally open a pull request containing your changes. If an open PR already covers this task, update
that PR instead of creating a duplicate. Target main unless the supplied prerequisite work requires
an explicitly documented stacked PR. Include the task number, problem, implemented behavior,
compatibility decisions, exact verification results and remaining limitations in the PR description.
Check the published diff and CI results; fix failures caused by your changes and report pending or
blocked checks accurately. Return the PR URL, branch, final commit SHA and a concise handoff. A local
commit alone is not the final deliverable. Do not force-push or auto-merge. The next agent must be
able to start from this result.
```

<a id="task-34"></a>

## 34. Expand platform support and simplify clean installation

```text
Implementation task 34/35: Expand platform support and simplify clean installation

Repository: https://github.com/SeucheAchat9115/Prism
Repository workflow: Use the GitHub connector for all remote repository communication: reading
repository files, branches, pull requests, review feedback and CI results, and publishing commits,
branches and pull requests. Local file editing, builds, tests and local Git operations are allowed;
do not use shell git fetch/pull/push/clone, gh, curl or direct HTTP clients to contact GitHub.
Discover the connector tools available in your session. If connector access is unavailable or an
operation is blocked, preserve the local work and report the exact blocker; do not silently switch
to another remote transport.

Prism is a script-first Python music-production project. Preserve readable Python authoring and a
lightweight headless offline path while extending production and live workflows.
Audit baseline: 434f538242009e373b62da74c5d527b6bd9120eb, 2026-09-05. This is historical evidence,
not the branch to reset to. Work from the latest integrated implementation that contains the
required preceding tasks. Read AGENTS.md and inspect current code before editing; recheck whether an
audited defect is already fixed. Source paths below refer to the baseline and may have moved.
Implement this task completely, with code rather than only a plan or stubs. Preserve unrelated work,
use a dedicated branch/worktree, and make routine design decisions from the repository and these
requirements. Do not implement later tasks opportunistically. If a prerequisite is absent, resolve
its supplied branch/commit or report the precise dependency rather than inventing an incompatible
substitute.

Required preceding tasks: 9, 10, 14, 20, 21, 22, 30, 33. All earlier integrated changes must remain
present.
Where to start: pyproject.toml and lock/build configuration; src/prism/vst.py: platform_key; native
host/device integration; CI platform jobs; installation guide.

Context and why: Prism currently targets Python 3.12 and supports VST hosting only on Windows/native
Linux. A broader producer audience needs reliable packaging and a tested macOS path, not merely
removal of a platform guard.

Qualify native macOS VST3 hosting, plugin bundles, native extension wheels, audio devices and editor
threading, including supported CPU architectures. Extend platform-specific plugin registry records
and installation diagnostics. Preserve Windows/Linux functionality. Keep VST2/AU/WSL outside the
support promise unless explicitly implemented and tested; underlying-library capabilities do not
automatically become Prism support.

Review dependency and Python-version constraints against actual available wheels/APIs. Expand Python
support only when the complete optional/native stack and tests support it. Improve clean
installation with optional extras for preview/live/VST/encoders, useful doctor output and pinned
reproducible build dependencies. Document plugin discovery/registration paths and any
packaging/signing requirements using current primary sources.

Acceptance: Clean environment installation and native offline rendering pass on every declared
platform. Real VST fixture/Surge, editor lifecycle, playback and state round-trip tests establish
the supported matrix. Headless CI and manual hardware evidence are labeled separately. If hardware
or distribution access prevents a claim, complete the implementation and available checks but list
that combination as unqualified rather than advertising it as working.

Verification and handoff: Add focused behavioral/regression tests for the described risks. Run
relevant tests plus the repository's required CI/type/lint/docs gates; at the audit baseline these
include pytest --cov, mypy src/prism, ruff check ., and mkdocs build --strict in the appropriate uv
extras. Preserve the separate real-VST workflow. Do not weaken gates, delete assertions, or equate
mocks with hardware/plugin qualification. Update the guide and runnable tutorial as required by
AGENTS.md. Read and update docs/development/implementation-status.md (create it if absent) with this
task number, completed scope, implemented API/compatibility decisions, verification and concrete
limitations. Use the GitHub connector to publish scoped verified changes on a dedicated branch and
finally open a pull request containing your changes. If an open PR already covers this task, update
that PR instead of creating a duplicate. Target main unless the supplied prerequisite work requires
an explicitly documented stacked PR. Include the task number, problem, implemented behavior,
compatibility decisions, exact verification results and remaining limitations in the PR description.
Check the published diff and CI results; fix failures caused by your changes and report pending or
blocked checks accurately. Return the PR URL, branch, final commit SHA and a concise handoff. A local
commit alone is not the final deliverable. Do not force-push or auto-merge. The next agent must be
able to start from this result.
```

<a id="task-35"></a>

## 35. Qualify the complete production workflow and publish an accurate capability map

```text
Implementation task 35/35: Qualify the complete production workflow and publish an accurate
capability map

Repository: https://github.com/SeucheAchat9115/Prism
Repository workflow: Use the GitHub connector for all remote repository communication: reading
repository files, branches, pull requests, review feedback and CI results, and publishing commits,
branches and pull requests. Local file editing, builds, tests and local Git operations are allowed;
do not use shell git fetch/pull/push/clone, gh, curl or direct HTTP clients to contact GitHub.
Discover the connector tools available in your session. If connector access is unavailable or an
operation is blocked, preserve the local work and report the exact blocker; do not silently switch
to another remote transport.

Prism is a script-first Python music-production project. Preserve readable Python authoring and a
lightweight headless offline path while extending production and live workflows.
Audit baseline: 434f538242009e373b62da74c5d527b6bd9120eb, 2026-09-05. This is historical evidence,
not the branch to reset to. Work from the latest integrated implementation that contains the
required preceding tasks. Read AGENTS.md and inspect current code before editing; recheck whether an
audited defect is already fixed. Source paths below refer to the baseline and may have moved.
Implement this task completely, with code rather than only a plan or stubs. Preserve unrelated work,
use a dedicated branch/worktree, and make routine design decisions from the repository and these
requirements. Do not implement later tasks opportunistically. If a prerequisite is absent, resolve
its supplied branch/commit or report the precise dependency rather than inventing an incompatible
substitute.

Required preceding tasks: 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21,
22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32, 33, 34. All earlier integrated changes must remain
present.
Where to start: all implemented APIs; AGENTS.md; README and docs/tutorial; tests and CI workflows;
project/export/host manifests; installation artifacts.

Context and why: Individually completed features can still fail as a production workflow. The audit
originally proved only a small offline song and limited Surge smoke coverage. The final stage must
establish what Prism can actually do after integration.

Run end-to-end acceptance projects covering scripted electronic production, sample/loop editing,
expressive imported MIDI, a real VST instrument/effect chain, sidechain/multi-output routing,
preview hot reload, live patch editing, audio recording/takes, and reopening a portable/frozen
project. Export mastered references, valid stems, MIDI and listening copies. Check non-silence,
timing, content, tails, levels, metadata and reconstruction at the documented graph stage.

Exercise long arrangements, bounded memory, many tracks, rapid code updates, stop/seek/loop, plugin
hang/crash, device loss and interrupted exports/recordings. Use justified numerical and performance
thresholds; do not replace audio correctness with file-exists or peak-only assertions. Keep regular
portable CI, real-plugin CI and hardware qualification clearly separated, with diagnostic artifacts
for failures.

Fix integration defects within this stage and update executable tutorials, clean-install
instructions, migration notes, support/capability tables and known limitations. Record accepted
public API decisions and any remaining limitations in a checked-in implementation-status document so
later agents can continue from evidence. Produce a reviewable release candidate; do not publish a
release or merge unrelated work automatically.

Acceptance: The required workflows complete on the declared matrix, and every unresolved item has a
concrete reproduction, impact and owner-ready follow-up. The final report distinguishes script-based
offline production, refreshed-buffer preview, genuine live processing and full recording workflows.
State exactly which configurations were tested; do not claim DAW parity solely from passing unit
tests.

Verification and handoff: Add focused behavioral/regression tests for the described risks. Run
relevant tests plus the repository's required CI/type/lint/docs gates; at the audit baseline these
include pytest --cov, mypy src/prism, ruff check ., and mkdocs build --strict in the appropriate uv
extras. Preserve the separate real-VST workflow. Do not weaken gates, delete assertions, or equate
mocks with hardware/plugin qualification. Update the guide and runnable tutorial as required by
AGENTS.md. Read and update docs/development/implementation-status.md (create it if absent) with this
task number, completed scope, implemented API/compatibility decisions, verification and concrete
limitations. Use the GitHub connector to publish scoped verified changes on a dedicated branch and
finally open a pull request containing your changes. If an open PR already covers this task, update
that PR instead of creating a duplicate. Target main unless the supplied prerequisite work requires
an explicitly documented stacked PR. Include the task number, problem, implemented behavior,
compatibility decisions, exact verification results and remaining limitations in the PR description.
Check the published diff and CI results; fix failures caused by your changes and report pending or
blocked checks accurately. Return the PR URL, branch, final commit SHA and a concise handoff. A local
commit alone is not the final deliverable. Do not force-push or auto-merge. The next agent must be
able to start from this result.
```

**Audit coverage is explicit.** The source-deletion/overwrite cases map to 1; meter timing to 2; discarded VST settings to 3; controllers to 4; duplicate VST instances to 5; sample tails to 6; release automation and long native songs to 7; automation-before-first-point to 8; worker hangs/state preservation to 9; real-plugin and latency gaps to 10; clipping/dither/normalization to 11; stem overlap to 12; asset/version identity to 13; broken documentation and script-root assumptions to 14; range/caching/auto-tail to 15; missing player/watch/visual feedback to 16–18; memory and real-time architecture to 19–22. All broader producer proposals are assigned to 23–35.

A later agent should adapt these historical findings to the code actually received. Passing a previous agent's checks is not a substitute for preserving its behavior while integrating the next stage.

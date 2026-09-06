# Projects, tracks, and routing

## Project

::: prism.Project
    options:
      members:
        - frames_per_bar
        - quarter_notes_per_bar
        - track
        - bus
        - master_effect
        - section
        - automation
        - validate
        - render
        - render_stems
        - export_midi
        - compile_track_events
        - configuration

`Project.timing` is the shared constant-tempo conversion boundary used by
arrangement placement, audio, automation, and MIDI export. See
[Musical timing](timing.md) for its canonical quarter-note contract and
non-quarter-note migration mode.

`Project.controller_boundary` controls expressive state at concrete clip
boundaries. It defaults to `"reset"`, with `"retain"` and explicit `"legacy"`
compatibility available for deliberate controller continuity. Use
`prism.compile_track_events` when an agent needs to inspect stable note IDs,
absolute positions, controller curves, or repeated/scoped clip occurrences
before rendering.

## Track

::: prism.Track
    options:
      members:
        - clip
        - clips
        - clips_for
        - instrument_plugin
        - instrument_specification
        - instrument_configuration
        - instrument_instance_id
        - sample
        - audio
        - drum
        - midi
        - instrument
        - effect
        - send

## SampleLibrary

Every project exposes this as `song.samples`. The `sounds/` folder is
registered automatically.

::: prism.SampleLibrary
    options:
      members:
        - folders
        - add_folder
        - files
        - find

## Bus

::: prism.Bus
    options:
      members:
        - add
        - effect

## Section

::: prism.Section

## Send

::: prism.Send

## ProjectSummary

::: prism.ProjectSummary

# Projects, tracks, and routing

## Project

::: prism.Project
    options:
      members:
        - frames_per_bar
        - track
        - bus
        - master_effect
        - section
        - automation
        - validate
        - render
        - render_stems
        - export_midi
        - configuration

## Track

::: prism.Track
    options:
      members:
        - clip
        - clips
        - clips_for
        - instrument_plugin
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

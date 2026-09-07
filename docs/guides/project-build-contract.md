
# Project build contract

Prism projects have two operations: describe a song, then deliver files. A
source file is compatible with the CLI build workflow when it defines a
callable build() -> Project that constructs and returns the complete Project.
The function should not render, export MIDI, write audio, or otherwise create
delivery files.

~~~python
from prism import Project, Uniwave


def build() -> Project:
    song = Project("My Song", prism_version="0.2.0.dev0")
    kick = song.track("Kick").drum("kick", "x--- x--- x--- x---")
    bass = song.track("Bass").midi("C2 - C2 Eb2", instrument=Uniwave.bass())
    song.section("Loop", bars=2, tracks=[kick, bass])
    return song


if __name__ == "__main__":
    song = build()
    print(song.validate())
    print(song.render("renders/song.wav"))
~~~

## Separate inspect, build, validate, and render

resolve_project_root() accepts a project folder or its main.py. The
project_root= constructor argument is the supported choice for notebooks,
agents, and tools that construct a Project while their current directory is
somewhere else.

~~~python
from pathlib import Path
from prism import (
    build_contract_info,
    build_project,
    render_project,
    resolve_project_root,
    validate_project,
)

root = resolve_project_root(Path("/work/projects/my-song"))
info = build_contract_info(root)  # static source inspection
song = build_project(root)        # executes build(), no delivery side effect
validation = validate_project(root)
result = render_project(root, "renders/agent.wav")
~~~

build_project() uses a non-main module name while it executes the source, so
the conventional main guard is skipped. This is what makes building safe to
repeat before a person or agent chooses a delivery operation. validate_project
and render_project are explicit operations and return structured results.

## CLI render profiles

Render a source project without executing its export guard:

~~~text
uv run prism render projects/my-song --profile master
uv run prism render projects/my-song --profile listening --output renders/listen.wav
uv run prism render projects/my-song --bit-depth 32 --channels stereo --json
~~~

The named profiles are:

| Profile | Intended use | Delivery contract |
| --- | --- | --- |
| master | production reference | 24-bit stereo, no normalization or dither |
| stem | aligned stem delivery | 24-bit stereo, stem dither enabled when used for stems |
| listening | audition copy | 16-bit stereo, peak normalization and TPDF dither |

A JSON profile can contain the serializable ExportProfile fields such as
bit_depth, channels, delivery_sample_rate, tail_seconds, clipping, and dither.
CLI flags override fields from the selected profile.

## Doctor and migration

prism doctor PROJECT is deliberately metadata-only. It reports:

- the Python and native rendering dependencies;
- registered VST3 paths and whether the optional host is available;
- readable project audio folders;
- whether the source has the build contract and whether migration is needed.

Use --build when you want full source execution and Project validation. The
JSON form is useful to agents and CI:

~~~text
uv run prism doctor projects/my-song --json
uv run prism doctor projects/my-song --build --json
~~~

A missing optional VST host does not prevent a native-only project from being
diagnosed or built. A registered external plugin is reported as unavailable
until its path and optional host are present.

Building is execution of user Python in the current interpreter, not a
security boundary. Do not use build validation as a sandbox for untrusted
source.

Legacy files that construct a Project and call render(), render_stems(), or
export_midi() at module scope still work when run directly. The render CLI
identifies those top-level exports and prints the migration instruction; it
never silently rewrites the source.

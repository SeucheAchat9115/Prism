<div align="center">
  <img src="docs/assets/prism-logo.jpg" alt="A beam of light passing through the Prism logo and becoming colorful music" width="900">
  <h1>Prism</h1>
  <p><strong>Music production guided by you, built for agents.</strong></p>
  <p>
    <a href="https://github.com/SeucheAchat9115/Prism/actions/workflows/ci.yml"><img src="https://github.com/SeucheAchat9115/Prism/actions/workflows/ci.yml/badge.svg?branch=main" alt="CI status"></a>
    <a href="https://seucheachat9115.github.io/Prism/"><img src="https://img.shields.io/badge/docs-open-7c4dff" alt="Open the documentation"></a>
    <img src="https://img.shields.io/badge/Python-3.12-3776ab" alt="Python 3.12">
  </p>
  <p>
    <strong><a href="https://seucheachat9115.github.io/Prism/getting-started/first-song/">Create your first song</a></strong>
    ·
    <strong><a href="https://seucheachat9115.github.io/Prism/">Read the documentation</a></strong>
  </p>
</div>

Prism is a Python music-production toolkit being built for **human-guided agentic
music production**. You describe the musical direction; an agent uses Prism to
compose, design sounds and edit the song while you listen and decide what to keep.
Every musical decision remains visible in a readable, reproducible Python project.

The goal is an iterative workflow: "I like the bassline, but change the notes to
be more euphoric" or "Build a synth lead which fits the bassline." The agent should
preserve what you like, propose targeted alternatives, render them for comparison
and let you accept a choice or restore the previous version.

**Available today:** an external coding agent can edit `main.py`, validate the
project and render WAV, stems and MIDI using Prism's public Python API. Tempo,
notes, samples, instruments, effects, automation and arrangement live together in
the project. You run the script and listen to its output.

**Planned:** structured agent operations, constrained musical edits, recoverable
revisions and an integrated audition/selection loop. Prism does not currently
include a built-in conversational agent or continuous live playback. The first
agentic milestone uses rendered previews; persistent live processing and recording
follow later. The headless Python workflow remains supported.

## Make your first sound

Open a terminal in the downloaded Prism repository. After
[installing uv](https://docs.astral.sh/uv/getting-started/installation/), run:

```text
uv sync --locked
uv run prism create --tutorial
```

Prism creates a ready-to-edit project and prints its exact run command:

```text
uv run "projects/tutorial-20260829-143000/main.py"
```

Your timestamp will be different. Copy the command Prism prints, then open the
new `renders/song.wav` in your normal music player.

## A song is one readable file

```python
from prism import Project, Uniwave

song = Project("My Song", prism_version="0.2.0.dev0", tempo=120)

kick = song.track("Kick", gain_db=-3).drum(
    "kick",
    "x--- x--- x--- x---",
)

bass = song.track("Bass", gain_db=-6).midi(
    "C2 - C2 Eb2 | G1 - Bb1 -",
    instrument=Uniwave.bass(),
    bars=2,
)

song.section("Loop", bars=4, tracks=[kick, bass])
song.render("renders/song.wav")
```

## One toolbox, from idea to finished files

| Compose | Design sounds | Produce | Export |
|---|---|---|---|
| MIDI, drums, samples, clips, and sections | Native Uniwave, stock plugins, and registered VST3 instruments | Stock/VST3 effects, automation, buses, sends, and mixing | WAV masters, aligned stems, and MIDI files |

Every project stays a normal folder that you can open, copy, and back up:

```text
projects/my-song-20260829-143000/
├── main.py       # The complete song
├── vst.json      # Optional VST3 registry
├── plugin-states/ # Optional saved plugin states
├── sounds/       # Your samples and recordings
└── renders/      # WAV, stem, and MIDI output
```

## Learn at your own pace

The **[complete Prism documentation](https://seucheachat9115.github.io/Prism/)**
contains installation help, a beginner-friendly tutorial path, feature guides,
plugin-development instructions, troubleshooting, and the full Python
reference.

## Contributing to the production roadmap

Start with the [ordered implementation tasks](docs/development/implementation-tasks.md)
for reliable rendering, agent editing and musical operations, human audition and
selection, then live playback and broader production features. Follow the stated
delivery order, including inserted tasks A01–A05; the original task IDs stay stable.
Each task links to a complete implementation-agent prompt with dependencies,
acceptance criteria, and handoff instructions. These pages describe planned work;
check the implementation status and linked pull requests for delivered features.


## Project status and contributing

Prism is **alpha software** (`0.2.0.dev0`): APIs and project compatibility may change.
Windows and Linux with Python 3.12 are the currently tested platforms.

Read [CONTRIBUTING.md](CONTRIBUTING.md) to start, [GOVERNANCE.md](GOVERNANCE.md)
for how decisions are made, and [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) for community
expectations. Maximilian Menke (@SeucheAchat9115) is the lead maintainer.

Songs are executable Python and VST plugins are native code. Only run projects and
plugins you trust; the VST worker is not a security sandbox. See
[SECURITY.md](SECURITY.md) for reporting vulnerabilities and known trust boundaries.

Prism is licensed under [GPL-3.0-only](LICENSE). See the [changelog](CHANGELOG.md)
and [maintainer checklist](docs/development/maintainer-checklist.md) for release preparation.

<div align="center">
  <img src="docs/assets/prism-logo.jpg" alt="A beam of light passing through the Prism logo and becoming colorful music" width="900">
  <h1>Prism</h1>
  <p><strong>Write music as Python. Render it reproducibly.</strong></p>
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

Prism is a music-production toolbox for people who want every part of a song to
remain visible and reproducible. Tempo, notes, samples, instruments, effects,
automation, arrangement, and export settings live together in one readable
`main.py` file. Change the file, run it again, and listen to the new render.

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
| MIDI, drums, samples, clips, and sections | Native Uniwave synthesizer and extensible stock plugins | Effects, automation, buses, sends, and mixing | WAV masters, aligned stems, and MIDI files |

Every project stays a normal folder that you can open, copy, and back up:

```text
projects/my-song-20260829-143000/
├── main.py       # The complete song
├── sounds/       # Your samples and recordings
└── renders/      # WAV, stem, and MIDI output
```

## Learn at your own pace

The **[complete Prism documentation](https://seucheachat9115.github.io/Prism/)**
contains installation help, a beginner-friendly tutorial path, feature guides,
plugin-development instructions, troubleshooting, and the full Python
reference.

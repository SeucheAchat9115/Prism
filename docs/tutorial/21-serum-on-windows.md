# Level 21: use Serum reproducibly on Windows

This level applies the same Prism interface to a commercial synthesizer. Serum
itself and its license are not included; install and activate its VST3 version
first.

## 1. Create a project and register Serum

```text
uv sync --extra vst3
uv run prism create serum-song --name "Serum Song" --tempo 128
uv run prism plugins add "projects/serum-song-20260829-143000" serum "C:\Program Files\Common Files\VST3\Serum 2.vst3"
```

Replace the timestamp and path with the values on your computer. If you use an
older Serum VST3, select its actual `.vst3` path.

## 2. Explore an unfamiliar plugin

```text
uv run prism plugins inspect "projects/serum-song-20260829-143000" serum --search cutoff
uv run prism plugins inspect "projects/serum-song-20260829-143000" serum --search resonance
uv run prism plugins inspect "projects/serum-song-20260829-143000" serum --search cutoff --python
```

The final command prints entries ready to paste into a Python `parameters`
dictionary. Use `--all` when you want the full list.

## 3. Build and save the complete sound

```text
uv run prism plugins edit "projects/serum-song-20260829-143000" serum --state "plugin-states/serum-bass.state"
```

Choose the wavetable, modulation routing, and other sound-design details in
Serum, then close the window. Prism saves details that are not represented by
ordinary exposed parameters. While the editor is open, Prism keeps Serum's
silent processing graph active. This prevents Serum from reporting that the DAW
has suspended processing. On Windows, Prism also opts the editor worker into
per-monitor DPI scaling so the window and mouse controls remain correctly sized
on high-resolution displays.

## 4. Use Serum like Uniwave

Put the following structure into the project's `main.py`. Replace the example
parameter names with the exact names printed by your Serum version:

```python
from prism import Project, VST3

song = Project("Serum Song", prism_version="0.2.0.dev0", tempo=128)

serum = VST3(
    "serum",
    state="plugin-states/serum-bass.state",
    parameters={
        "Filter Cutoff": 0.32,
        "Filter Resonance": 0.15,
    },
)

bass = song.track("Serum Bass", gain_db=-7).midi(
    "C2 - C2 Eb2 | G1 - Bb1 -",
    instrument=serum,
    bars=2,
)

song.section("Loop", bars=4, tracks=[bass])
song.render("renders/song.wav", tail_seconds=2)
```

Render from the repository root with the exact command printed when the project
was created. The state is loaded first and the visible parameter values are
then applied, so `main.py` remains the final authority for those controls.

[Read the complete VST3 guide →](../guides/external-vst3.md)

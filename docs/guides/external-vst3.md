# Use external VST3 plugins

Prism can use a registered VST3 instrument in the same place as `Uniwave`, or
a registered VST3 effect in the same place as a stock effect. The important
difference is that the plugin software must also be installed on the computer
that renders the project.

!!! note "Supported systems"

    VST3 hosting supports Windows and native Linux. It does not currently
    support macOS, WSL, VST2, Audio Units, sidechains, or multi-output plugins.

## Install the optional host once

From the Prism repository root, run:

```text
uv sync --extra vst3
```

Normal Prism projects do not need this extra package. It is loaded only when a
project uses a VST3.

## Register a plugin for one project

Every new project contains `vst.json`. Add an alias and the plugin path without
editing that JSON by hand:

```text
uv run prism plugins add "projects/my-song-20260829-143000" serum "C:\Program Files\Common Files\VST3\Serum 2.vst3"
uv run prism plugins add "projects/my-song-20260829-143000" ott "C:\Program Files\Common Files\VST3\OTT.vst3"
```

Use your real timestamp and plugin location. An alias uses lowercase letters,
numbers, `-`, and `_`. Prism records separate Windows and Linux paths, plus a
SHA-256 checksum that detects an accidentally updated or replaced binary.

Useful registry commands are:

```text
uv run prism plugins list "projects/my-song-20260829-143000"
uv run prism plugins remove "projects/my-song-20260829-143000" ott
```

If the binary is inside the project folder, Prism stores a portable relative
path. Otherwise it stores the installed absolute path. Prism never scans the
computer or silently chooses a plugin.

## Discover every setting

A VST can expose hundreds or thousands of parameters. Prism asks the plugin
for their real names and current normalized values:

```text
uv run prism plugins inspect "projects/my-song-20260829-143000" serum --search filter
uv run prism plugins inspect "projects/my-song-20260829-143000" ott --all
uv run prism plugins inspect "projects/my-song-20260829-143000" serum --search cutoff --python
```

Values are normalized from `0.0` to `1.0`, exactly as VST3 defines them. Names
match without regard to capitalization. If a plugin exposes the same name more
than once, use the unambiguous selector printed by Prism, such as
`"#123: Filter Cutoff"`.

## Put the settings in `main.py`

```python
from prism import Project, VST3

song = Project("VST Song", prism_version="0.2.0.dev0", tempo=124)

serum = VST3(
    "serum",
    state="plugin-states/serum-bass.state",
    parameters={
        "Filter Cutoff": 0.35,
        "Filter Resonance": 0.18,
    },
)

bass = song.track("Bass").midi(
    "C2 - C2 Eb2 | G1 - Bb1 -",
    instrument=serum,
    bars=2,
)

ott = bass.effect(
    VST3("ott", parameters={"Depth": 0.65}),
    name="OTT",
)

song.automation(
    "OTT movement",
    target=ott,
    parameter="Depth",
    points=[(0.0, 0.35), (2.0, 0.75), (4.0, 0.5)],
)

song.section("Loop", bars=4)
song.render("renders/song.wav", tail_seconds=2)
```

Use the exact names printed by `inspect`; manufacturers choose their own names.
The loading order is plugin default, state or preset, `parameters`, then Prism
automation. This makes the visible values in `main.py` authoritative.

## Save settings that parameters cannot express

Some plugins keep wavetable selections, modulation routings, sample data, or
other private settings outside the exposed parameter list. Save that complete
state inside the project:

```text
uv run prism plugins edit "projects/my-song-20260829-143000" serum --state "plugin-states/serum-bass.state"
```

The editor worker processes silence while the window is open, which keeps
plugins that monitor their DAW connection active. On Windows it also enables
per-monitor DPI scaling before the plugin UI is created. If an editor still
looks incorrectly sized, close it, move the terminal to the intended monitor,
and run the command again; plugin-specific zoom settings may also apply.

This command is a **state editor**, not a live VST host. Prism does not connect
the editor to an audio device or route live MIDI into it, so a plugin's
on-screen keyboard and the computer keyboard are not audible here. Close the
window to save, then run the project's `main.py` to render and hear the sound.
Use a dedicated live VST host when you need low-latency playing while designing
a patch; save or export the resulting patch and capture it in Prism afterward.

The plugin window opens. Design the sound, close the window, and Prism saves
the state file. The command then lists every exposed parameter whose final
value differs from the starting value. For a new state file, the starting
values are the plugin defaults; for an existing file, they are the previously
saved values. Prism also reports plugin-private state changes even when no
exposed parameter changed. Refer to the file from `VST3(state=...)`. A `.vstpreset` file can
instead be loaded with `VST3(preset="plugin-states/name.vstpreset")`; do not
set both `state` and `preset`.

Commit or back up `main.py`, `vst.json`, and `plugin-states/` together. Plugin
binaries and commercial licenses are not copied by Prism.

## Reproducibility expectations

Prism records the plugin alias, platform, binary checksum, state/preset path,
parameters, and automation without putting machine-specific absolute paths in
the resolved project configuration. Another producer still needs the same
plugin version and an appropriate license. Native Prism projects aim for
deterministic output; third-party VST projects are externally reproducible but
may not be byte-for-byte identical across plugin builds or computers.

Plugins run in separate worker processes. A crash becomes a readable render
error rather than crashing the main Prism process. Reported plugin latency is
compensated during offline rendering.

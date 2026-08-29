# Level 20: build a free VST3 song

This level uses the free **Surge XT** synthesizer and **Xfer OTT** effect. You
will register both plugins, inspect their controls, save a synth sound, automate
OTT, and render a loop. Download and install the VST3 versions from their
official publishers before beginning.

## 1. Add VST3 support

From the Prism repository root:

```text
uv sync --extra vst3
uv run prism create free-vst-song --name "Free VST Song" --tempo 124
```

Copy the new project path printed by Prism. The commands below use
`projects/free-vst-song-20260829-143000`; replace it with yours.

## 2. Register the installed plugins

Windows example:

```text
uv run prism plugins add "projects/free-vst-song-20260829-143000" surge "C:\Program Files\Common Files\VST3\Surge XT.vst3"
uv run prism plugins add "projects/free-vst-song-20260829-143000" ott "C:\Program Files\Common Files\VST3\OTT.vst3"
```

Linux example (adjust these paths to match your installation):

```text
uv run prism plugins add "projects/free-vst-song-20260829-143000" surge "$HOME/.vst3/Surge XT.vst3"
uv run prism plugins add "projects/free-vst-song-20260829-143000" ott "$HOME/.vst3/OTT.vst3"
```

Confirm what the project knows:

```text
uv run prism plugins list "projects/free-vst-song-20260829-143000"
```

## 3. Learn the controls and save a sound

```text
uv run prism plugins inspect "projects/free-vst-song-20260829-143000" surge --search filter
uv run prism plugins inspect "projects/free-vst-song-20260829-143000" ott --search depth
uv run prism plugins edit "projects/free-vst-song-20260829-143000" surge --state "plugin-states/surge-lead.state"
```

When Surge XT opens, choose or design a lead sound. Close its window to save
the state into the project.

## 4. Replace `main.py`

Open the new project's `main.py`, replace everything with this complete song,
and keep the version string originally generated in your file:

```python
from prism import Project, VST3

song = Project("Free VST Song", prism_version="0.2.0.dev0", tempo=124)

kick = song.track("Kick", gain_db=-3).drum("kick", "x--- x--- x--- x---")

lead = song.track("Surge Lead", gain_db=-7).midi(
    "C4 Eb4 G4 Bb4 | G4 F4 Eb4 C4",
    instrument=VST3("surge", state="plugin-states/surge-lead.state"),
    bars=2,
)

ott = lead.effect(
    VST3("ott", parameters={"Depth": 0.55}),
    name="OTT",
)

song.automation(
    "OTT depth",
    target=ott,
    parameter="Depth",
    points=[(0.0, 0.25), (2.0, 0.75), (4.0, 0.45)],
)

song.section("Loop", bars=4, tracks=[kick, lead])

print(song.validate())
print(song.render("renders/song.wav", tail_seconds=2))
```

If your OTT version calls the control something other than `Depth`, copy the
exact name printed in step 3 into both places in `main.py`.

## 5. Render and listen

Run the project from the repository root:

```text
uv run "projects/free-vst-song-20260829-143000/main.py"
```

Open `renders/song.wav`. Then change the normalized Depth values, rerun the same
command, and compare the result. Your sound state, visible parameters, notes,
automation, plugin checksums, and export settings now travel with the project.

[Next: use Serum on Windows →](21-serum-on-windows.md)

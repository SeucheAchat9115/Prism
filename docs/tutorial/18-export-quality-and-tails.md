# Level 18: Export quality and effect tails

In this level you prepare a short song for work in another music program. You
export a 24-bit master, floating-point stems, a professional output sample
rate, and enough time for the final delay and reverb to fade naturally.

## 1. Replace `main.py`

Replace everything in your tutorial project's `main.py` with this:

```python
from prism import Project, Uniwave

song = Project(
    "Finished Export",
    prism_version="0.2.0.dev0",
    tempo=240,
    sample_rate=22_050,
)

kick = song.track("Kick", gain_db=-4).drum(
    "kick", "x--- x--- x--- x---"
)
lead = song.track("Lead", gain_db=-8, pan=0.15).midi(
    "C4 E4 G4 C5",
    instrument=Uniwave.lead(),
    bars=1,
)
lead.effect("delay", time_beats=0.5, feedback=0.45, mix=0.3)

room = song.bus("Room Return", gain_db=-8)
room.effect("reverb", room_size=0.7, damping=0.4, mix=1)
kick.send(room, gain_db=-15)
lead.send(room, gain_db=-12)

song.master_effect("compressor", threshold_db=-10, ratio=2)
song.section("Final Bar", bars=1)

master = song.render(
    "renders/song.wav",
    bit_depth=24,
    channels="stereo",
    sample_rate=48_000,
    tail_seconds=1.5,
)
stems = song.render_stems(
    "renders/stems",
    bit_depth=32,
    channels="stereo",
    sample_rate=48_000,
    tail_seconds=1.5,
)

print(master)
print("Master format:", master.bit_depth, "bit,", master.sample_rate, "Hz")
print(stems)
```

## 2. Run and compare

Run the command Prism printed when it created your tutorial project. Listen to
`renders/song.wav`, especially after the last note. The song is one second
long at this tempo, but the file continues for another 1.5 seconds so the
delay and reverb can finish instead of stopping suddenly.

The master is a stereo, 24-bit WAV at 48 kHz. The files under
`renders/stems/` are stereo 32-bit floating-point WAVs at the same sample rate.
They also contain the complete tail and all start at the same point.

## 3. Choose the right bit depth

- Use `bit_depth=16` for compact listening copies and everyday sharing. This
  is Prism's default.
- Use `bit_depth=24` for a high-quality final WAV or normal DAW exchange.
- Use `bit_depth=32` for floating-point stems with extra mixing headroom.

Prism prevents fixed-point 16-bit and 24-bit files from exceeding the WAV
range. Floating-point files can keep levels above 0 dBFS, allowing a DAW to
turn them down without having already lost that information.

## 4. Try mono and another sample rate

Change one export to:

```python
channels="mono",
sample_rate=44_100,
```

Run the project again. Prism combines left and right evenly into one channel
and performs high-quality sample-rate conversion after mixing. Panning is no
longer audible in mono, so stereo is the normal choice for masters and stems.

## 5. Set a useful tail

`tail_seconds=0` keeps the file exactly as long as the arranged sections. Add
enough time for the slowest release, delay, or reverb in your song. A value
between one and five seconds is a practical starting point; Prism accepts up
to 60 seconds.

Checkpoint: you can now choose delivery quality separately from the sample
rate used while building the song, and your effects can finish naturally.

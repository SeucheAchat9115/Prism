# Make music that stays reproducible

Prism is a Python toolbox for music producers. A song is one readable
`main.py` file: it sets the tempo, creates tracks, writes notes, chooses sounds,
adds effects, arranges sections, and renders a WAV file.

You do not need to build an application or learn a framework. Change the song
file, run it again, and listen to the new render.

[Create your first song](getting-started/first-song.md){ .md-button .md-button--primary }
[Follow the tutorials](tutorial/README.md){ .md-button }

## Hear Prism

This short loop is rendered by Prism itself whenever this documentation is
built. It uses generated drums and the native Uniwave synthesizer, so no sample
downloads or audio hardware are required.

<audio controls preload="metadata" style="width: 100%">
  <source src="assets/audio/uniwave-demo.wav" type="audio/wav">
  Your browser does not support WAV playback.
</audio>

## A complete song remains plain text

```python
from prism import Project, Uniwave

song = Project(
    "First Prism Song",
    prism_version="0.2.0.dev0",
    tempo=120,
)

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

print(song.validate())
print(song.export_midi("renders/song.mid"))
print(song.render("renders/song.wav"))
```

Everything needed to understand the song is visible in that file. Samples stay
inside its project folder and generated audio goes into `renders/`.

## What you can build

- Generated drums, layered Uniwave synthesizer sounds, and sample-based tracks
- Searchable project sample folders with short-name lookup and duplicate protection
- Exact MIDI notes, chords, velocity, pitch bend, modulation, swing, and humanization
- Reusable clips, variations, fills, and named song sections
- Edited samples with cropping, fades, reversing, playback rate, pitch, and stretching
- Ordered effects, buses, sends, master processing, and parameter automation
- 16/24/32-bit WAV masters and aligned stems with selectable channels, sample rate, and tails
- Standard MIDI files and deterministic output hashes

The [tutorial learning path](tutorial/README.md) teaches these features from a
first four-beat loop through a complete arranged and mixed project. The
[Python reference](reference/index.md) gives exact signatures whenever you need
to look up a setting.

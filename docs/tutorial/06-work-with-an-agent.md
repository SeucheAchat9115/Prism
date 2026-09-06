# Level 6 — work safely with a coding agent

Goal: direct an external coding agent to make musical edits while you keep control
of the song. This tutorial uses today's Python-and-render workflow. The integrated
proposal, preview selection and undo tools are planned in
[roadmap tasks A01–A05](../development/implementation-tasks.md).

## What an agent should edit

The intended authoring surface is the producer's `main.py` and project-local
files under `sounds/`. Ask the agent to use only public imports from `prism`.
Good requests are concrete musical edits:

```text
Read my main.py. Add a two-bar bass part in C minor, but do not change the drum
pattern. Keep the file readable for a non-programmer, validate it, render to a
new WAV name, and summarize the musical changes.
```

```text
Refactor repeated numeric values into clearly named variables. Do not introduce
frameworks, helper classes, absolute paths, network calls, or hidden state.
```

```text
Create an Intro, Verse, Chorus, and Outro using my existing track variables.
Show me the arrangement before running the project script.
```

## Guide an iteration with musical intent

These prompts are for your external coding agent, not commands understood by
Prism itself:

```text
I like the bassline, but change its notes to be more euphoric. First explain
your interpretation of that direction. Preserve the rhythm, velocities, bass
sound, drums and arrangement. Save the original main.py and plugin states,
then create two alternative Python versions and render each to a different
WAV filename. Tell me which pitches changed. I will listen and choose.
```

```text
Build a synth lead which fits the bassline. Inspect the existing notes and
harmony first; if the harmony is uncertain, state your assumption. Keep the
bass unchanged. Use an editable native synth sound, explain the melody and
register, and render the lead in the mix so I can judge how they work together.
```

Today, keep separate source copies or use version control to restore a previous
choice; a new WAV filename alone does not preserve the old source or plugin state.
After choosing, ask the agent to apply that version to the working song. Validate
and render again, then listen. Technical checks can catch silence, invalid notes
or changed timing; they cannot decide whether a melody feels euphoric.
Automatic preservation checks, candidate comparison and recoverable revisions
will arrive through the agentic milestone.

## A complete agent-friendly `main.py`

Named groups and short comments make intent clear without hiding Prism calls:

```python
from prism import Project, Uniwave


# Song-wide decisions
TEMPO = 118
OUTPUT = "renders/song.wav"

song = Project(
    "Agent-Assisted Song",
    prism_version="0.2.0.dev0",
    tempo=TEMPO,
)


# Rhythm section
kick = song.track("Kick", gain_db=-3).drum(
    "kick",
    "x--- x--- x-x- x---",
)

snare = song.track("Snare", gain_db=-8).drum(
    "snare",
    "---- x--- ---- x---",
    seed=11,
)

bass = song.track("Bass", gain_db=-6, pan=-0.1).midi(
    "C2 - C2 Eb2 | G1 - Bb1 -",
    instrument=Uniwave.bass(),
    bars=2,
)


# Harmony and melody
pad = song.track("Pad", gain_db=-12, pan=-0.3).midi(
    "C3+Eb3+G3 - | Ab2+C3+Eb3 -",
    instrument=Uniwave.pad(),
    bars=2,
)

lead = song.track("Lead", gain_db=-10, pan=0.3).midi(
    "G4 Bb4 C5 - | G4 F4 Eb4 -",
    instrument=Uniwave.lead(),
    bars=2,
)


# Arrangement: the order here is the playback order
song.section("Intro", bars=2, tracks=[pad])
song.section("Verse", bars=4, tracks=[kick, snare, bass, pad])
song.section("Chorus", bars=4)
song.section("Outro", bars=2, tracks=[kick, pad])


# Deliverables
print(song.validate())
print(song.export_midi("renders/song.mid"))
print(song.render(OUTPUT))
```

## Review before execution

A Python project file is executable code. Before an agent runs an unfamiliar
`main.py`, it should review the file and its imports. A normal Prism project
needs `from prism import Project`; unexpected subprocess, network, credential,
or broad filesystem operations are not part of music authoring.

The agent should then run the ordinary project command:

Use the command Prism printed for your timestamped tutorial project.

Listen to `renders/song.wav` inside the project folder. The printed result also
shows its SHA-256 hash for exact comparisons.

## Readability checklist

- The file reads in the order project → tracks → sections → outputs.
- Track variables use musical names, not generated IDs.
- Patterns are visually grouped into beats or bars.
- Every source path is relative and under `sounds/`.
- Comments explain musical intent, not obvious Python syntax.
- No helper abstraction is introduced until it removes real repetition.
- The agent reports validation errors instead of bypassing them.
- A changed render uses a new filename when the producer wants an A/B comparison.

Checkpoint: the producer can understand and own the result after the agent
leaves; rerunning one reviewed file reproduces the deliverables.

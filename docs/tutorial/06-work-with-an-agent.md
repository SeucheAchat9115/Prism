# Level 6 — work safely with a coding agent

Goal: direct an external coding agent to make musical edits while you keep control
of the song. This tutorial uses readable Python, the local headless build path,
and A01's read-only inspection contract. Scoped edits, source persistence,
audition, and undo remain in
[roadmap tasks A02–A05](../development/implementation-tasks.md).

## What an agent should edit

The intended authoring surface is the producer's `main.py` and project-local
files under `sounds/`. Ask the agent to use only public imports from `prism`.
Good requests are concrete musical edits:

## Inspect before editing

An agent should identify the intended track, section, clip, and instrument
before it proposes a change. The A01 contract is local JSON; it does not need
an LLM service, network access, an audio device, or a VST host for inspection.
The project build executes reviewed Python, so use the task-14 `build() ->
Project` boundary and keep delivery calls in the `__main__` guard.

From the project folder, discover the contract and inspect a bounded context:

```console
prism agent capabilities
prism agent inspect . --limits '{"max_notes":128,"max_clip_instances":64}' --json
```

The response includes stable IDs next to display names, arrangement sections,
clip definitions and repeated clip instances, notes/controllers, routing,
available stock presets and parameters, optional-plugin availability, assets,
and offline render capabilities. Use IDs in a follow-up selection:

```console
prism agent select . --entity track --id "project:main/track:0002" \
  --section "project:main/section:0001" --start-beat 0 --end-beat 16 --json
```

The same operation is available from Python after a project has been built:

```py
from prism import inspect_agent_context, select_agent_entities

context = inspect_agent_context(song)
bass_id = next(
    track["id"]
    for track in context["arrangement"]["tracks"]
    if track["role"]["value"] == "bass"
)
selection = select_agent_entities(
    song,
    {
        "entity": "track",
        "id": bass_id,
        "quarter_note_range": [0, 16],
    },
)
```

Do not select a duplicate display name by guessing. The contract returns an
`ambiguous_name` error with candidate IDs; select by ID, role, or section. Each
result carries a `revision_id` and `selected_ranges`. Send that revision back
with a later request so a stale selection is reported instead of applied to a
changed song.

`musical_context.authored` is the producer's declared `key`, `scale`, and
`chords`. Register and rhythmic summaries are inferred from compiled events,
and inferred harmony includes uncertainty and provenance. Treat those fields
as useful clues for a human listening decision, never as facts about intent or
musical quality.

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
    project_id="agent-song",
    key="C",
    scale="minor",
    chords=("Cm", "Ab", "Eb", "Bb"),
    tempo=TEMPO,
)


# Rhythm section
kick = song.track("Kick", role="drums", gain_db=-3).drum(
    "kick",
    "x--- x--- x-x- x---",
)

snare = song.track("Snare", role="drums", gain_db=-8).drum(
    "snare",
    "---- x--- ---- x---",
    seed=11,
)

bass = song.track("Bass", role="bass", gain_db=-6, pan=-0.1).midi(
    "C2 - C2 Eb2 | G1 - Bb1 -",
    instrument=Uniwave.bass(),
    bars=2,
)


# Harmony and melody
pad = song.track("Pad", role="pad", gain_db=-12, pan=-0.3).midi(
    "C3+Eb3+G3 - | Ab2+C3+Eb3 -",
    instrument=Uniwave.pad(),
    bars=2,
)

lead = song.track("Lead", role="lead", gain_db=-10, pan=0.3).midi(
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

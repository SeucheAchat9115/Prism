from __future__ import annotations

from pathlib import Path

import numpy as np
import soundfile as sf

from prism import Note, Project, compile_track_events
from prism.midi import _pitch_bend_message
from prism.vst_host import _midi_file


def _stream(song: Project, track: object, bars: int) -> object:
    return compile_track_events(
        song,
        track,  # type: ignore[arg-type]
        total_bars=bars,
        total_frames=song.timing.bars_to_frame(bars),
    )


def test_compiled_stream_has_stable_ids_scoped_repeats_and_ordered_retriggers(
    project_script: Path,
) -> None:
    song = Project("Compiled events", prism_version="test", _script=project_script)
    lead = song.track("Lead").midi(
        [
            Note("C4", start=0.0, duration=1.0),
            Note("C4", start=1.0, duration=1.0),
        ],
        bars=1,
        pitch_bend=[(0.0, 0.0), (1.0, 7.0)],
        pitch_bend_range=12.0,
    )
    lead.midi(
        [Note("D4", start=0.0, duration=1.0)],
        bars=1,
        section="Chorus",
        repeat=False,
    )
    song.section("Verse", bars=2, tracks=[lead])
    song.section("Chorus", bars=1, tracks=[lead])

    first = _stream(song, lead, 3)
    second = _stream(song, lead, 3)

    assert first == second
    assert [boundary.start_beat for boundary in first.boundaries] == [0.0, 4.0, 8.0]
    assert [boundary.repeat_index for boundary in first.boundaries] == [0, 1, 0]
    assert len({note.note_id for note in first.notes}) == 5
    assert first.pitch_bend_range == 12.0
    assert all(point.pitch_bend_range == 12.0 for point in first.controllers)

    at_retrigger = [
        event
        for event in first.events
        if event.beat == 1.0 and event.midi_note == 60
    ]
    assert [event.kind for event in at_retrigger] == ["note_off", "note_on"]
    assert [event.order for event in at_retrigger] == sorted(event.order for event in at_retrigger)


def test_controller_curves_and_clip_boundary_reset_are_explicit(
    project_script: Path,
) -> None:
    def build(curve: str, boundary: str = "reset") -> tuple[Project, object]:
        song = Project(
            "Controller policy",
            prism_version="test",
            tempo=120,
            sample_rate=8_000,
            controller_boundary=boundary,  # type: ignore[arg-type]
            _script=project_script,
        )
        track = song.track("Lead").midi(
            [Note("C4", start=0.0, duration=2.0)],
            bars=1,
            pitch_bend=[(0.0, 0.0), (1.0, 2.0)],
            pitch_bend_curve=curve,  # type: ignore[arg-type]
        )
        track.midi([Note("C4", start=0.0, duration=2.0)], section="B", bars=1)
        song.section("A", bars=1, tracks=[track])
        song.section("B", bars=1, tracks=[track])
        return song, _stream(song, track, 2)

    linear_song, linear = build("linear")
    _hold_song, hold = build("hold")
    retained_song, retained = build("linear", "retain")

    linear_mid = [
        event.value
        for event in linear.midi_controller_events(480)
        if event.controller == "pitch_bend" and event.tick == 240
    ]
    hold_mid = [
        event.value
        for event in hold.midi_controller_events(480)
        if event.controller == "pitch_bend" and event.tick == 240
    ]
    assert linear_mid == [1.0]
    assert hold_mid == [0.0]
    assert any(
        point.synthetic_reset and point.beat == 4.0
        for point in linear.controllers
        if point.controller == "pitch_bend"
    )
    assert not any(
        point.synthetic_reset and point.beat == 4.0
        for point in retained.controllers
        if point.controller == "pitch_bend"
    )

    # The shared VST MIDI adapter and the public MIDI bend conversion use the
    # declared 2-semitone legacy default only when a stream says so; this track
    # declares 2 semitones explicitly through its default.
    assert _pitch_bend_message(0, 2.0, 2.0) == bytes((0xE0, 0x7F, 0x7F))
    payload = _midi_file(linear_song.timing, linear)
    assert bytes((0xE0, 0x00, 0x40)) in payload  # reset at the second clip


def test_modulation_overlap_boundaries_and_controller_helpers(
    project_script: Path,
) -> None:
    song = Project(
        "Boundary events",
        prism_version="test",
        tempo=120,
        controller_boundary="reset",
        _script=project_script,
    )
    lead = song.track("Lead").midi(
        [
            Note("C4", start=0.0, duration=4.0),
            Note("C4", start=1.0, duration=2.0),
        ],
        bars=1,
        pitch_bend=[(0.0, 0.0), (1.0, 2.0)],
        modulation=[(0.0, 0.0), (1.0, 1.0)],
    )
    lead.midi([Note("C4", start=0.0, duration=1.0)], section="B", bars=1)
    song.section("A", bars=1, tracks=[lead])
    song.section("B", bars=1, tracks=[lead])

    stream = _stream(song, lead, 2)
    same_pitch = [note for note in stream.notes if note.midi_note == 60]
    assert len(same_pitch) == 3
    assert same_pitch[0].note_id != same_pitch[1].note_id
    assert (same_pitch[0].on_beat, same_pitch[0].off_beat) == (0.0, 4.0)
    assert (same_pitch[1].on_beat, same_pitch[1].off_beat) == (1.0, 3.0)

    boundary_events = [event for event in stream.events if event.beat == 4.0]
    assert [event.kind for event in boundary_events] == [
        "note_off",
        "clip_end",
        "clip_start",
        "controller",
        "controller",
        "note_on",
    ]
    assert [event.controller for event in boundary_events if event.controller] == [
        "pitch_bend",
        "modulation",
    ]

    modulation = [
        event
        for event in stream.midi_controller_events(480)
        if event.controller == "modulation" and event.tick == 240
    ]
    assert modulation and modulation[0].value == 0.5

    chase = stream.controller_chase(4.0, timing=song.timing)
    assert {point.controller: point.value for point in chase} == {
        "pitch_bend": 0.0,
        "modulation": 0.0,
    }
    reset = stream.reset_controller_events(4.0, timing=song.timing)
    assert {point.controller: point.value for point in reset} == {
        "pitch_bend": 0.0,
        "modulation": 0.0,
    }


def test_vst_adapter_and_midi_export_share_compiled_expression_events(
    project_script: Path,
) -> None:
    song = Project("Shared MIDI", prism_version="test", _script=project_script)
    lead = song.track("Lead").midi(
        [Note("A4", start=0.0, duration=2.0)],
        bars=1,
        pitch_bend=[(0.0, 0.0), (1.0, 2.0)],
        modulation=[(0.0, 0.0), (1.0, 1.0)],
    )
    lead.midi([Note("A4", start=0.0, duration=2.0)], section="B", bars=1)
    song.section("A", bars=1, tracks=[lead])
    song.section("B", bars=1, tracks=[lead])
    stream = _stream(song, lead, 2)

    vst_input = _midi_file(song.timing, stream)
    exported = song.export_midi("renders/shared.mid").path.read_bytes()
    bent = bytes((0xE0, 0x7F, 0x7F))
    reset = bytes((0xE0, 0x00, 0x40))
    modulation = bytes((0xB0, 1, 127))
    for payload in (vst_input, exported):
        assert bent in payload
        assert reset in payload
        assert modulation in payload


def test_bend_does_not_leak_into_an_unbent_following_clip(
    project_script: Path,
) -> None:
    def render(pitch_bend: list[tuple[float, float]], output: str) -> np.ndarray:
        song = Project(
            "Bend reset",
            prism_version="test",
            tempo=120,
            sample_rate=8_000,
            normalize=False,
            _script=project_script,
        )
        lead = song.track("Lead").midi(
            [Note("A4", start=0.0, duration=3.0)],
            bars=1,
            instrument="lead",
            waveform="sine",
            release_ms=0.0,
            cutoff_hz=20_000.0,
            pitch_bend=pitch_bend,
        )
        lead.midi(
            [Note("A4", start=0.0, duration=3.0)],
            section="B",
            bars=1,
            waveform="sine",
            release_ms=0.0,
            cutoff_hz=20_000.0,
        )
        song.section("A", bars=1, tracks=[lead])
        song.section("B", bars=1, tracks=[lead])
        result = song.render(output)
        samples, _ = sf.read(result.path, dtype="float64", always_2d=True)
        return samples

    bent = render([(0.0, 0.0), (1.0, 2.0)], "renders/bent.wav")
    flat = render([], "renders/flat.wav")
    bar = 16_000
    assert np.allclose(bent[bar + 100 : 2 * bar - 100], flat[bar + 100 : 2 * bar - 100], atol=1e-12)
    assert not np.allclose(bent[:bar], flat[:bar], atol=1e-6)

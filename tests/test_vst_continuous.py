from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from prism import VST3, Note, Project, ProjectError, vst_host
from prism.vst import VSTRegistry


def _vst_project(tmp_path: Path, *, sample_rate: int = 8_000) -> Project:
    root = tmp_path / "song"
    root.mkdir()
    script = root / "main.py"
    script.write_text("# continuous VST fixture\n", encoding="utf-8")
    plugin = root / "plugins" / "Test Synth.vst3"
    plugin.parent.mkdir()
    plugin.write_bytes(b"fake-vst3")
    registry = VSTRegistry(root)
    registry.initialize()
    registry.add("synth", plugin)
    return Project(
        "Continuous VST",
        prism_version="test",
        tempo=120,
        sample_rate=sample_rate,
        normalize=False,
        controller_boundary="retain",
        _script=script,
    )


def test_vst_track_renders_one_complete_stream_with_leading_silence_and_tail(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    song = _vst_project(tmp_path)
    specification = VST3("synth", parameters={"Cutoff": 0.25})
    lead = song.track("Lead").midi(
        [
            Note("C4", start=0.0, duration=3.0),
            Note("D4", start=1.0, duration=3.0),
        ],
        instrument=specification,
        bars=1,
        gain_db=0.0,
        pitch_bend=[(0.0, 0.0), (1.0, 1.0)],
        modulation=[(0.0, 0.0), (1.0, 1.0)],
    )
    lead.midi(
        [Note("E4", start=0.0, duration=2.0)],
        section="Chorus",
        bars=1,
        gain_db=0.0,
        repeat=False,
        pitch_bend=[(0.0, 1.0)],
    )
    song.section("Intro", bars=1, tracks=[])
    song.section("Verse", bars=2, tracks=[lead])
    song.section("Chorus", bars=1, tracks=[lead])
    instrument = lead.instrument_plugin
    assert instrument is not None
    song.automation(
        "Global cutoff",
        target=instrument,
        parameter="Cutoff",
        points=[(0.0, 0.25), (2.0, 0.75)],
    )

    calls: list[tuple[object, object, int]] = []

    def fake_render(
        project: Project, plugin: object, stream: object, frames: int
    ) -> np.ndarray:
        calls.append((plugin, stream, frames))
        return np.full((frames, 2), 0.25, dtype=np.float64)

    monkeypatch.setattr("prism.vst_host.render_vst3_instrument", fake_render)

    result = song.render("renders/continuous.wav", tail_seconds=0.25)

    assert result.frames == song.timing.bar_to_frame(4) + song.timing.seconds_to_frames(0.25)
    assert len(calls) == 1
    _plugin, raw_stream, frames = calls[0]
    stream = raw_stream
    assert frames == result.frames
    assert len(stream.boundaries) == 3
    assert [boundary.start_beat for boundary in stream.boundaries] == [4.0, 8.0, 12.0]
    assert stream.total_frames == frames
    assert stream.total_frames > song.timing.bar_to_frame(4)
    assert stream.notes[0].on_frame == song.timing.quarter_notes_to_frame(4.0)
    assert stream.notes[0].on_frame > 0  # leading section silence is in the one render
    assert any(
        note.on_beat < other.off_beat and other.on_beat < note.off_beat
        for index, note in enumerate(stream.notes)
        for other in stream.notes[index + 1 :]
    )
    boundary_events = [event for event in stream.events if event.beat == 8.0]
    assert [event.kind for event in boundary_events[:3]] == [
        "note_off",
        "clip_end",
        "clip_start",
    ]
    assert {point.controller for point in stream.controllers} == {
        "pitch_bend",
        "modulation",
    }


def test_vst_clip_gain_migration_requires_one_shared_gain_domain(
    tmp_path: Path,
) -> None:
    song = _vst_project(tmp_path)
    specification = VST3("synth")
    lead = song.track("Lead").midi(
        "C4",
        instrument=specification,
        gain_db=-6.0,
        bars=1,
    )
    lead.midi("E4", section="B", gain_db=-3.0, bars=1, repeat=False)
    song.section("A", bars=1, tracks=[lead])
    song.section("B", bars=1, tracks=[lead])

    with pytest.raises(ProjectError, match="independently scaled"):
        song.validate()

    # Migration: normalize the clip declarations, then express the intended
    # time-varying gain once for the shared instrument output.
    lead.instrument(specification, gain_db=0.0)
    lane = lead.output_gain(
        [(0.0, -6.0), (1.0, -3.0)],
        name="Lead shared gain",
    )

    assert lane.points[-1].value == -3.0
    assert song.validate().bars == 2
    configuration = song.configuration()
    assert configuration["schema_version"] == 11
    assert configuration["tracks"][0]["output_gain"]["name"] == "Lead shared gain"  # type: ignore[index]


def test_stem_generation_reuses_one_vst_track_render_for_track_and_master(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    song = _vst_project(tmp_path)
    lead = song.track("Lead").midi("C4", instrument=VST3("synth"), gain_db=0.0)
    song.section("Only", bars=1, tracks=[lead])
    calls = 0

    def fake_render(
        _project: Project, _plugin: object, _stream: object, frames: int
    ) -> np.ndarray:
        nonlocal calls
        calls += 1
        return np.full((frames, 2), 0.2, dtype=np.float64)

    monkeypatch.setattr("prism.vst_host.render_vst3_instrument", fake_render)

    result = song.render_stems("renders/stems")

    assert calls == 1
    assert result.tracks[0].path.is_file()
    assert result.master.path.is_file()
    assert result.master.path.read_bytes() != result.tracks[0].path.read_bytes()


def test_vst_request_keeps_global_automation_and_full_tail_frame_count(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    song = _vst_project(tmp_path)
    lead = song.track("Lead").midi(
        "C4",
        instrument=VST3("synth", parameters={"Cutoff": 0.25}),
        bars=1,
        gain_db=0.0,
    )
    song.section("Only", bars=2, tracks=[lead])
    instrument = lead.instrument_plugin
    assert instrument is not None
    song.automation(
        "Global cutoff",
        target=instrument,
        parameter="Cutoff",
        points=[(0.0, 0.25), (1.0, 0.75), (2.0, 0.5)],
    )
    stream = song.compile_track_events(lead)
    requests: list[dict[str, object]] = []

    def fake_worker(request: dict[str, object]) -> dict[str, object]:
        requests.append(request)
        automation_path = request["automation"]
        assert isinstance(automation_path, str)
        with np.load(automation_path, allow_pickle=False) as arrays:
            values = np.asarray(arrays["Cutoff"], dtype=np.float64)
        assert values.shape == (stream.total_frames,)
        assert values[0] == pytest.approx(0.25)
        assert values[song.timing.bar_to_frame(1)] == pytest.approx(0.75)
        output_path = request["output_path"]
        assert isinstance(output_path, str)
        np.save(output_path, np.zeros((stream.total_frames, 2), dtype=np.float32))
        return {"frames": stream.total_frames, "latency_samples": 0}

    monkeypatch.setattr(vst_host, "_run_worker", fake_worker)

    rendered = vst_host.render_vst3_instrument(
        song,
        instrument,
        stream,
        stream.total_frames,
    )

    assert rendered.shape == (stream.total_frames, 2)
    assert len(requests) == 1


def test_output_gain_lane_is_applied_after_the_single_instrument_render(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    song = _vst_project(tmp_path)
    lead = song.track("Lead").midi("C4", instrument=VST3("synth"), gain_db=0.0)
    lead.output_gain([(0.0, -6.0), (1.0, 0.0)])
    song.section("Only", bars=1, tracks=[lead])

    def fake_render(
        _project: Project, _plugin: object, _stream: object, frames: int
    ) -> np.ndarray:
        return np.ones((frames, 2), dtype=np.float64)

    monkeypatch.setattr("prism.vst_host.render_vst3_instrument", fake_render)

    result = song.render("renders/output-gain.wav", bit_depth=32)
    samples, _ = sf.read(result.path, dtype="float64", always_2d=True)

    assert samples[0, 0] == pytest.approx(10 ** (-9 / 20), abs=1e-5)
    assert samples[-1, 0] == pytest.approx(10 ** (-3 / 20), abs=1e-4)

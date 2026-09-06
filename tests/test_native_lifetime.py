from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from prism import VST3, Note, Project, SynthWave, Uniwave
from prism.stock_plugins.uniwave import _envelope
from prism.synthesis.engine import render_native_synth
from prism.synthesis.types import NativeSynthSpec
from prism.vst import VSTRegistry


def _sound(*, release_ms: float) -> Uniwave:
    return Uniwave(
        waves=(SynthWave("sine"),),
        attack_ms=0.0,
        decay_ms=0.0,
        sustain=1.0,
        release_ms=release_ms,
        cutoff_hz=5_000.0,
        resonance=0.0,
        drive=0.0,
    )


def _native_spec(
    *,
    sound: Uniwave,
    frames: int,
    automation: dict[str, np.ndarray] | None = None,
    duration: float = 1.0,
) -> NativeSynthSpec:
    return NativeSynthSpec(
        preset="uniwave",
        sequence=("C4",),
        note_events=(Note("C4", start=0.0, duration=duration),),
        uniwave=sound,
        automation=automation,
        frame_count=frames,
        bars=1,
        gain_db=0.0,
    )


def _render_voice(
    *,
    release_ms: float,
    frames: int = 12_000,
    automation: dict[str, np.ndarray] | None = None,
    duration: float = 1.0,
) -> np.ndarray:
    return render_native_synth(
        _native_spec(
            sound=_sound(release_ms=release_ms),
            frames=frames,
            automation=automation,
            duration=duration,
        ),
        sample_rate=8_000,
        tempo_bpm=120.0,
    )


def test_constant_automated_release_matches_static_envelope() -> None:
    frames = 12_000
    automated = _render_voice(
        release_ms=100.0,
        frames=frames,
        automation={"release_ms": np.full(frames, 1_000.0)},
    )
    static = _render_voice(release_ms=1_000.0, frames=frames)

    assert np.allclose(automated, static, atol=1e-12, rtol=0.0)
    assert np.max(np.abs(automated[8_000:])) > 1e-3


def test_release_automation_is_sampled_at_note_off() -> None:
    frames = 12_000
    note_off = 4_000
    increased = np.full(frames, 100.0)
    increased[note_off:] = 1_000.0
    unchanged_after_note_off = increased.copy()
    unchanged_after_note_off[note_off + 1 :] = 0.0

    first = _render_voice(release_ms=100.0, frames=frames, automation={"release_ms": increased})
    second = _render_voice(
        release_ms=100.0,
        frames=frames,
        automation={"release_ms": unchanged_after_note_off},
    )

    assert np.allclose(first, second, atol=1e-12, rtol=0.0)
    assert np.max(np.abs(first[8_000:])) > 1e-3


def test_release_decrease_at_note_off_and_zero_release_end_the_envelope() -> None:
    frames = 6_000
    note_off = 4_000
    sound = _sound(release_ms=1_000.0)
    values = np.full(frames, 1_000.0)
    values[note_off:] = 0.0

    envelope = _envelope(
        frames,
        note_frames=note_off,
        sample_rate=8_000,
        sound=sound,
        automation={"release_ms": values},
        start=0,
        release_ms=0.0,
    )

    assert np.all(envelope[note_off:] == 0.0)


def test_sustained_voice_and_render_range_are_bounded_by_explicit_frames() -> None:
    sustained = _render_voice(release_ms=1_000.0, frames=4_000, duration=8.0)
    truncated = _render_voice(release_ms=1_000.0, frames=4_200)

    assert sustained.shape == (4_000,)
    assert np.max(np.abs(sustained[-500:])) > 1e-3
    assert truncated.shape == (4_200,)


def test_native_spec_rejects_invalid_ranges_and_non_finite_automation() -> None:
    with pytest.raises(ValueError, match="clip bars"):
        replace(_native_spec(sound=_sound(release_ms=100.0), frames=1), bars=257)

    with pytest.raises(ValueError, match="frame_count"):
        _native_spec(sound=_sound(release_ms=100.0), frames=100_000_001)

    bad = _native_spec(
        sound=_sound(release_ms=100.0),
        frames=100,
        automation={"release_ms": np.full(100, np.nan)},
    )
    with pytest.raises(ValueError, match="non-finite"):
        render_native_synth(bad, sample_rate=8_000, tempo_bpm=120.0)


def _long_native_project(script: Path) -> Project:
    song = Project(
        "Long native arrangement",
        prism_version="test",
        tempo=300,
        sample_rate=8_000,
        normalize=False,
        _script=script,
    )
    lead = song.track("Lead").midi("C4", instrument=Uniwave(), bars=1)
    song.section("Long section", bars=256, tracks=[lead])
    song.section("Ending", bars=1, tracks=[lead])
    return song


def test_257_bar_native_melodic_arrangement_validates_and_renders(
    project_script: Path,
) -> None:
    song = _long_native_project(project_script)

    summary = song.validate()
    result = song.render("renders/257-bar-native.wav")

    assert summary.bars == 257
    assert result.frames == song.timing.bar_to_frame(257)
    assert result.path.is_file()


def test_257_bar_native_drum_arrangement_validates_and_renders(
    project_script: Path,
) -> None:
    song = Project(
        "Long native drums",
        prism_version="test",
        tempo=300,
        sample_rate=8_000,
        normalize=False,
        _script=project_script,
    )
    kick = song.track("Kick").drum("kick", "x---", bars=1)
    song.section("Long section", bars=256, tracks=[kick])
    song.section("Ending", bars=1, tracks=[kick])

    result = song.render("renders/257-bar-drums.wav")

    assert result.frames == song.timing.bar_to_frame(257)


def test_large_native_schedule_does_not_use_clip_bar_limit(
    project_script: Path,
) -> None:
    song = Project(
        "Large schedule",
        prism_version="test",
        tempo=300,
        sample_rate=8_000,
        _script=project_script,
    )
    lead = song.track("Lead").midi("C4", bars=1, repeat=False)
    for index in range(300):
        song.section(f"Section {index}", bars=256, tracks=[lead])

    summary = song.validate()
    stream = song.compile_track_events(lead)

    assert summary.bars == 300 * 256
    assert stream.total_frames == song.timing.bar_to_frame(summary.bars)
    assert len(stream.notes) == 300


def test_257_bar_external_instrument_uses_explicit_arrangement_range(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "external-song"
    root.mkdir()
    script = root / "main.py"
    script.write_text("# external instrument fixture\n", encoding="utf-8")
    plugin_path = root / "plugins" / "test.vst3"
    plugin_path.parent.mkdir()
    plugin_path.write_bytes(b"fake-vst3")
    registry = VSTRegistry(root)
    registry.initialize()
    registry.add("synth", plugin_path)

    song = Project(
        "Long external arrangement",
        prism_version="test",
        tempo=300,
        sample_rate=8_000,
        normalize=False,
        _script=script,
    )
    lead = song.track("Lead").midi("C4", instrument=VST3("synth"), bars=1, gain_db=0.0)
    song.section("Long section", bars=256, tracks=[lead])
    song.section("Ending", bars=1, tracks=[lead])
    calls: list[int] = []

    def fake_render(_project: Project, _plugin: object, _stream: object, frames: int) -> np.ndarray:
        calls.append(frames)
        return np.zeros((frames, 2), dtype=np.float64)

    monkeypatch.setattr("prism.vst_host.render_vst3_instrument", fake_render)

    result = song.render("renders/257-bar-external.wav")

    assert result.frames == song.timing.bar_to_frame(257)
    assert calls == [result.frames]

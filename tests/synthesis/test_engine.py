from __future__ import annotations

import io
import math

import numpy as np
import pytest
import soundfile as sf
from pydantic import ValidationError

from prism.synthesis import (
    NativeSynthSpec,
    native_synth_presets,
    note_frequency,
    render_native_synth,
)


def test_note_parser_supports_sharps_flats_chords_and_bounds() -> None:
    assert note_frequency("A4") == pytest.approx(440.0)
    assert note_frequency("C#4") == pytest.approx(note_frequency("Db4"))
    assert note_frequency("C4") == pytest.approx(261.625565, rel=1e-6)
    with pytest.raises(ValueError, match="invalid note"):
        note_frequency("H4")
    with pytest.raises(ValueError, match="outside"):
        note_frequency("C10")


def test_native_synth_is_deterministic_loop_aligned_and_decodable() -> None:
    spec = NativeSynthSpec(preset="kick", bars=2, seed=17)
    first = render_native_synth(spec, sample_rate=8_000, tempo_bpm=120.0)
    second = render_native_synth(spec, sample_rate=8_000, tempo_bpm=120.0)

    assert first.sha256 == second.sha256
    assert first.wav_bytes == second.wav_bytes
    assert first.frames == 32_000
    assert first.duration_seconds == 4.0
    samples, rate = sf.read(io.BytesIO(first.wav_bytes), dtype="float32")
    assert rate == 8_000
    assert samples.shape == (32_000,)
    assert np.max(np.abs(samples)) > 0.1
    assert np.isfinite(samples).all()


@pytest.mark.parametrize("preset", ("snare", "hihat", "bass", "lead", "pad"))
def test_every_native_preset_produces_finite_audio(preset: str) -> None:
    spec = NativeSynthSpec.model_validate({"preset": preset, "bars": 1})
    rendered = render_native_synth(spec, sample_rate=8_000, tempo_bpm=120.0)
    samples, _ = sf.read(io.BytesIO(rendered.wav_bytes), dtype="float32")
    assert samples.shape == (16_000,)
    assert np.isfinite(samples).all()
    assert np.max(np.abs(samples)) > 0.001


def test_melodic_sound_design_controls_change_the_audio() -> None:
    plain = NativeSynthSpec(
        preset="lead",
        sequence=["C4+E4+G4", "-"],
        waveform="sine",
        attack_ms=0.0,
        decay_ms=0.0,
        sustain_level=1.0,
        release_ms=10.0,
        cutoff_hz=8_000.0,
        gate=0.5,
    )
    shaped = plain.model_copy(update={"waveform": "saw", "cutoff_hz": 300.0})
    first = render_native_synth(plain, sample_rate=8_000, tempo_bpm=120.0)
    second = render_native_synth(shaped, sample_rate=8_000, tempo_bpm=120.0)
    assert first.sha256 != second.sha256


def test_synth_contract_rejects_invalid_sequences_and_excessive_duration() -> None:
    with pytest.raises(ValidationError, match="percussion sequence"):
        NativeSynthSpec(preset="kick", sequence=["C4"])
    with pytest.raises(ValidationError, match="only to melodic"):
        NativeSynthSpec(preset="snare", sequence=["x"], waveform="sine")
    with pytest.raises(ValidationError, match="at least one"):
        NativeSynthSpec(preset="bass", sequence=["-", "rest"])
    with pytest.raises(ValueError, match="cannot exceed"):
        render_native_synth(
            NativeSynthSpec(preset="lead", bars=32),
            sample_rate=44_100,
            tempo_bpm=20.0,
        )


def test_preset_catalog_is_complete_and_uses_valid_defaults() -> None:
    presets = native_synth_presets()
    assert [item.name for item in presets] == [
        "kick",
        "snare",
        "hihat",
        "bass",
        "lead",
        "pad",
    ]
    assert all(item.default_sequence for item in presets)
    assert math.isclose(note_frequency("A4"), 440.0)

from __future__ import annotations

from pathlib import Path

import pytest

from prism import Project, ProjectError, SynthWave, Uniwave
from prism.plugins import STOCK_PLUGINS


def _render_sound(
    script: Path,
    sound: Uniwave,
    output: str,
    notes: str = "C4 E4 G4 C5",
) -> bytes:
    song = Project(
        "Uniwave Test",
        prism_version="test",
        tempo=120,
        sample_rate=8_000,
        normalize=False,
        _script=script,
    )
    lead = song.track("Lead").midi(notes, instrument=sound)
    song.section("Only", bars=1, tracks=[lead])
    return song.render(output).path.read_bytes()


def test_uniwave_layers_independent_waves_and_renders_deterministically(
    project_script: Path,
) -> None:
    sound = Uniwave(
        waves=(
            SynthWave("saw", level=0.7, detune_cents=-8),
            SynthWave("square", level=0.35, octave=1, detune_cents=6, phase=0.25),
            SynthWave("sine", level=0.2, semitones=7),
        ),
        attack_ms=12,
        decay_ms=180,
        sustain=0.6,
        release_ms=240,
        cutoff_hz=3_200,
        resonance=0.3,
        drive=0.15,
        vibrato_rate_hz=5.5,
        vibrato_depth_cents=12,
        noise_level=0.04,
        noise_seed=17,
    )

    first = _render_sound(project_script, sound, "renders/uniwave.wav")
    second = _render_sound(project_script, sound, "renders/uniwave-again.wav")
    changed = _render_sound(
        project_script,
        Uniwave(waves=(SynthWave("triangle"),)),
        "renders/triangle.wav",
    )
    polyphonic = _render_sound(
        project_script,
        sound,
        "renders/chord.wav",
        notes="C4+E4+G4 -",
    )

    assert first == second
    assert first != changed
    assert polyphonic != first


def test_uniwave_configuration_and_starting_sounds_are_readable(
    project_script: Path,
) -> None:
    song = Project("Presets", prism_version="test", _script=project_script)
    bass = song.track("Bass").midi("C2 -", instrument=Uniwave.bass())
    song.section("Only", bars=1, tracks=[bass])

    instrument = song.configuration()["tracks"][0]["instrument"]  # type: ignore[index]

    assert STOCK_PLUGINS.get("instrument", "uniwave").synth_processor is not None
    assert instrument["preset"] == "uniwave"
    assert len(instrument["settings"]["waves"]) == 2
    assert instrument["settings"]["cutoff_hz"] == 1_100
    assert len(Uniwave.lead().waves) == 3
    assert len(Uniwave.pad().waves) == 3


@pytest.mark.parametrize(
    "factory",
    [
        lambda: SynthWave("pulse"),
        lambda: SynthWave(level=1.1),
        lambda: SynthWave(octave=4),
        lambda: SynthWave(semitones=13),
        lambda: SynthWave(detune_cents=101),
        lambda: SynthWave(phase=-0.1),
        lambda: Uniwave(waves=()),
        lambda: Uniwave(cutoff_hz=10),
        lambda: Uniwave(resonance=1),
        lambda: Uniwave(noise_seed=-1),
    ],
)
def test_uniwave_rejects_invalid_sound_design_values(factory: object) -> None:
    with pytest.raises(ProjectError):
        factory()  # type: ignore[operator]


def test_uniwave_object_owns_its_sound_settings(project_script: Path) -> None:
    song = Project("Clear settings", prism_version="test", _script=project_script)

    with pytest.raises(ProjectError, match="inside the Uniwave object"):
        song.track("Lead").midi("C4", instrument=Uniwave.lead(), cutoff_hz=800)

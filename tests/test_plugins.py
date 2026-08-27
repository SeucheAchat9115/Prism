from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from prism import Project, ProjectError
from prism.plugins import STOCK_PLUGINS, Parameter, PluginDefinition, PluginRegistry


def _automated_song(script: Path) -> Project:
    song = Project(
        "Automated Beat",
        prism_version="test",
        tempo=120,
        sample_rate=8_000,
        normalize=False,
        _script=script,
    )
    kick = song.track("Kick").drum("kick", "x--- x--- x--- x---")
    level = kick.effect("gain", name="Beat Level", gain_db=0)
    song.automation(
        "Beat Fade",
        target=level,
        parameter="gain_db",
        points=[(0, 0), (1, -60)],
        curve="hold",
    )
    song.section("Two Bars", bars=2, tracks=[kick])
    return song


def test_effect_chain_and_automation_render_in_song_time(project_script: Path) -> None:
    song = _automated_song(project_script)

    first = song.render("renders/automated.wav")
    second = song.render("renders/automated-again.wav")
    samples, _ = sf.read(first.path, dtype="float64", always_2d=True)
    split = song.frames_per_bar

    assert first.path.read_bytes() == second.path.read_bytes()
    assert np.max(np.abs(samples[:split])) > 0.1
    assert np.max(np.abs(samples[split:])) < np.max(np.abs(samples[:split])) * 0.002


def test_multiple_effects_are_applied_in_insertion_order(project_script: Path) -> None:
    def rendered(order: tuple[str, str], output: str) -> bytes:
        song = Project(
            "Effect Order",
            prism_version="test",
            sample_rate=8_000,
            _script=project_script,
        )
        lead = song.track("Lead").midi("C4 E4 G4 C5")
        for preset in order:
            if preset == "filter":
                lead.effect("filter", cutoff_hz=500, mix=1)
            else:
                lead.effect("distortion", drive_db=24, mix=1)
        song.section("Only", bars=1)
        return song.render(output).path.read_bytes()

    filter_then_drive = rendered(("filter", "distortion"), "renders/one.wav")
    drive_then_filter = rendered(("distortion", "filter"), "renders/two.wav")

    assert filter_then_drive != drive_then_filter


def test_explicit_instrument_effects_and_automation_are_inspectable(
    project_script: Path,
) -> None:
    song = Project("Plugin Song", prism_version="test", _script=project_script)
    lead = song.track("Lead").midi("C4 - E4 G4", bars=2, velocity=90)
    synth = lead.instrument("bass", name="Stock Bass", cutoff_hz=700, gain_db=-8)
    delay = lead.effect(
        "delay",
        name="Echo",
        time_beats=0.5,
        feedback=0.3,
        mix=0.2,
    )
    lead.effect("filter", name="Tone", cutoff_hz=2_000, mix=0.8)
    song.automation(
        "Echo Amount",
        target=delay,
        parameter="mix",
        points=[(0, 0), (2, 0.6)],
    )
    song.automation(
        "Bass Cutoff",
        target=synth,
        parameter="cutoff_hz",
        points=[(0, 300), (2, 3_000)],
    )
    song.section("Build", bars=2, tracks=[lead])

    configuration = song.configuration()
    track = configuration["tracks"][0]  # type: ignore[index]
    automation = configuration["automation"]  # type: ignore[index]

    assert track["instrument"]["preset"] == "bass"  # type: ignore[index]
    assert [effect["name"] for effect in track["effects"]] == ["Echo", "Tone"]  # type: ignore[index]
    assert [lane["name"] for lane in automation] == ["Echo Amount", "Bass Cutoff"]  # type: ignore[union-attr]
    assert song.render().path.is_file()


def test_plugin_authoring_errors_are_specific(project_script: Path) -> None:
    song = Project("Errors", prism_version="test", _script=project_script)
    lead = song.track("Lead").midi("C4")
    effect = lead.effect("filter")

    with pytest.raises(ProjectError, match="no parameter"):
        lead.effect("delay", speed=2)
    with pytest.raises(ProjectError, match="cannot be automated"):
        song.automation(
            "Bad Parameter",
            target=effect,
            parameter="resonance",
            points=[(0, 0.5)],
        )
    with pytest.raises(ProjectError, match="strictly increasing"):
        song.automation(
            "Bad Points",
            target=effect,
            parameter="cutoff_hz",
            points=[(1, 500), (1, 1_000)],
        )

    other = Project("Other", prism_version="test", _script=project_script)
    foreign = other.track("Other Lead").midi("C4").effect("gain")
    with pytest.raises(ProjectError, match="from this project"):
        song.automation(
            "Foreign",
            target=foreign,
            parameter="gain_db",
            points=[(0, 0)],
        )

    song.automation(
        "Too Long",
        target=effect,
        parameter="cutoff_hz",
        points=[(0, 500), (3, 1_000)],
    )
    song.section("Short", bars=1)
    with pytest.raises(ProjectError, match="after the song"):
        song.validate()


def test_stock_registry_is_the_single_plugin_catalog() -> None:
    assert {
        "gain",
        "filter",
        "distortion",
        "delay",
        "chorus",
        "reverb",
        "compressor",
        "tremolo",
    } <= STOCK_PLUGINS.presets("effect")
    assert {"bass", "lead", "pad"} <= STOCK_PLUGINS.presets("instrument")
    assert STOCK_PLUGINS.get("effect", "filter").processor is not None
    assert STOCK_PLUGINS.get("instrument", "lead").synth_patch is not None

    local = PluginRegistry()
    custom = PluginDefinition(
        preset="test_effect",
        kind="effect",
        parameters={"mix": Parameter(0.5, 0.0, 1.0)},
        defaults={"mix": 0.5},
        processor=lambda samples, parameters, sample_rate, tempo: samples,
    )
    local.register(custom)
    assert local.get("effect", "test_effect") is custom
    with pytest.raises(ProjectError, match="already registered"):
        local.register(custom)


@pytest.mark.parametrize("preset", ["chorus", "reverb", "compressor", "tremolo"])
def test_new_effect_processors_are_deterministic_and_audible(preset: str) -> None:
    definition = STOCK_PLUGINS.get("effect", preset)
    assert definition.processor is not None
    frames = 4_096
    positions = np.arange(frames, dtype=np.float64) / 8_000.0
    source = 0.8 * np.sin(2.0 * np.pi * 220.0 * positions)
    samples = np.column_stack((source, source))
    parameters = {
        name: np.full(frames, parameter.default, dtype=np.float64)
        for name, parameter in definition.parameters.items()
    }

    first = definition.processor(samples, parameters, 8_000, 120.0)
    second = definition.processor(samples, parameters, 8_000, 120.0)

    assert first.shape == samples.shape
    assert np.all(np.isfinite(first))
    assert np.array_equal(first, second)
    assert not np.allclose(first, samples)


@pytest.mark.parametrize(
    ("preset", "setting", "invalid"),
    [
        ("chorus", "rate_hz", 0.0),
        ("reverb", "room_size", 1.1),
        ("compressor", "ratio", 0.5),
        ("tremolo", "depth", -0.1),
    ],
)
def test_new_effect_parameters_are_validated(
    project_script: Path, preset: str, setting: str, invalid: float
) -> None:
    song = Project("Effect validation", prism_version="test", _script=project_script)
    track = song.track("Lead").midi("C4")

    with pytest.raises(ProjectError, match=setting):
        track.effect(preset, **{setting: invalid})

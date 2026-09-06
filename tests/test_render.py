from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

import prism.render as render_module
from prism import (
    ExportProfile,
    Project,
    ProjectError,
    RenderError,
    StemFile,
    StemRenderResult,
)


def _mini_song(script: Path) -> Project:
    song = Project(
        "Deterministic Mini Song",
        prism_version="test",
        tempo=120,
        sample_rate=8_000,
        _script=script,
    )
    kick = song.track("Kick", gain_db=-3).drum("kick", "x--- x--- x--- x---")
    snare = song.track("Snare", gain_db=-7).drum("snare", "---- x--- ---- x---", seed=11)
    hat = song.track("Hi-Hat", gain_db=-12, pan=0.25).drum(
        "hihat", "x-x- x-x- x-x- x-x-", seed=17
    )
    bass = song.track("Bass", gain_db=-5, pan=-0.15).midi(
        "C2 - C2 Eb2 | G1 - Bb1 -", instrument="bass", bars=2
    )
    pad = song.track("Pad", gain_db=-10, pan=-0.3).midi(
        "C3+Eb3+G3 - Ab2+C3+Eb3 -",
        instrument="pad",
        bars=2,
        attack_ms=180,
        release_ms=300,
    )
    song.section("Intro", bars=2, tracks=[hat, pad])
    song.section("Verse", bars=2, tracks=[kick, snare, hat, bass])
    song.section("Chorus", bars=2)
    return song


def _write_stereo_source(script: Path, name: str, frames: int, value: float = 0.2) -> Path:
    sounds = script.parent / "sounds"
    sounds.mkdir(exist_ok=True)
    path = sounds / name
    sf.write(
        path,
        np.full((frames, 2), value, dtype=np.float32),
        8_000,
        subtype="PCM_16",
    )
    return path


def _loud_song(script: Path) -> Project:
    song = Project(
        "Loud Export",
        prism_version="test",
        tempo=300,
        sample_rate=8_000,
        master_gain_db=12,
        normalize=False,
        _script=script,
    )
    song.track("Loud Kick", gain_db=12).drum("kick", "x---")
    song.section("Hit", bars=1)
    return song


def test_render_is_non_silent_and_deterministic(project_script: Path) -> None:
    song = _mini_song(project_script)

    first = song.render("renders/first.wav")
    second = song.render("renders/second.wav")
    samples, sample_rate = sf.read(first.path, dtype="float32", always_2d=True)

    assert first.path.read_bytes() == second.path.read_bytes()
    assert first.sha256 == hashlib.sha256(first.path.read_bytes()).hexdigest()
    assert sample_rate == 8_000
    assert samples.shape == (96_000, 2)
    assert np.max(np.abs(samples)) > 0.05


def test_render_stems_exports_aligned_tracks_buses_and_exact_master(
    project_script: Path,
) -> None:
    song = Project(
        "Stem Song",
        prism_version="test",
        tempo=240,
        sample_rate=8_000,
        normalize=False,
        _script=project_script,
    )
    kick = song.track("Kick", gain_db=-4).drum("kick", "x---")
    lead = song.track("Lead & Main", pan=0.25).midi(
        "C4 E4 G4 -", instrument="lead", bars=1
    )
    drums = song.bus("Drum Group", tracks=[kick], gain_db=-2)
    drums.effect("compressor", threshold_db=-20, ratio=3)
    room = song.bus("Room Return", gain_db=-8)
    room.effect("reverb", mix=1)
    lead.send(room, gain_db=-12)
    song.master_effect("gain", gain_db=-1)
    song.section("Loop", bars=1)

    result = song.render_stems("renders/stems")
    normal = song.render("renders/song.wav")

    assert isinstance(result, StemRenderResult)
    assert all(isinstance(item, StemFile) for item in result.files)
    assert [item.path.name for item in result.tracks] == [
        "01-kick.wav",
        "02-lead-main.wav",
    ]
    assert [item.path.name for item in result.buses] == [
        "01-drum-group.wav",
        "02-room-return.wav",
    ]
    assert result.master.path.name == "master.wav"
    assert result.master.path.read_bytes() == normal.path.read_bytes()
    assert result.frames == song.frames_per_bar
    assert result.sample_rate == 8_000
    assert result.channels == 2
    assert result.bit_depth == 16
    assert result.tail_seconds == 0.0
    assert result.vst_backend is not None
    assert result.vst_backend["render_block_size"] == 512
    assert len(result.files) == 5
    for item in result.files:
        samples, rate = sf.read(item.path, dtype="float32", always_2d=True)
        assert rate == result.sample_rate
        assert samples.shape == (result.frames, result.channels)
        assert item.sha256 == hashlib.sha256(item.path.read_bytes()).hexdigest()
        assert np.max(np.abs(samples)) > 0.0

    unrelated = result.directory / "tracks" / "99-producer-file.wav"
    unrelated.write_bytes(b"producer-owned")
    note = result.directory / "tracks" / "keep.txt"
    note.write_text("mine", encoding="utf-8")
    rerendered = song.render_stems("renders/stems")

    assert rerendered.master.sha256 == result.master.sha256
    assert unrelated.read_bytes() == b"producer-owned"
    assert note.read_text(encoding="utf-8") == "mine"
    assert rerendered.generation == result.generation + 1

    manifest_path = project_script.parent / "renders" / "stems" / ".prism-stems" / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["schema_version"] == 1
    assert manifest["generation"] == rerendered.generation
    assert manifest["vst_backend"]["render_block_size"] == 512
    assert {entry["path"] for entry in manifest["files"]} == {
        "tracks/01-kick.wav",
        "tracks/02-lead-main.wav",
        "buses/01-drum-group.wav",
        "buses/02-room-return.wav",
        "master.wav",
    }


@pytest.mark.parametrize(
    ("bit_depth", "subtype"),
    ((16, "PCM_16"), (24, "PCM_24"), (32, "FLOAT")),
)
def test_render_writes_selected_bit_depth_and_preserves_float_headroom(
    project_script: Path, bit_depth: int, subtype: str
) -> None:
    song = Project(
        "WAV Quality",
        prism_version="test",
        tempo=300,
        sample_rate=8_000,
        master_gain_db=12,
        normalize=False,
        _script=project_script,
    )
    song.track("Loud Kick", gain_db=12).drum("kick", "x---")
    song.section("Hit", bars=1)

    result = song.render(f"renders/{bit_depth}.wav", bit_depth=bit_depth)  # type: ignore[arg-type]
    info = sf.info(result.path)
    samples, _ = sf.read(result.path, dtype="float64", always_2d=True)

    assert info.subtype == subtype
    assert result.bit_depth == bit_depth
    if bit_depth == 32:
        assert np.max(np.abs(samples)) > 1.0
    else:
        assert np.max(np.abs(samples)) <= 1.0


def test_export_profile_records_delivery_diagnostics_and_clipping_policy(
    project_script: Path,
) -> None:
    strict = ExportProfile(
        name="strict-master",
        bit_depth=16,
        normalization="none",
        clipping="error",
    )
    with pytest.raises(RenderError, match="overloaded samples"):
        _loud_song(project_script).render("renders/strict.wav", profile=strict)

    warn_profile = ExportProfile(
        name="warn-master",
        bit_depth=16,
        normalization="none",
        clipping="warn",
    )
    with pytest.warns(RuntimeWarning, match="clipped"):
        warned = _loud_song(project_script).render(
            "renders/warn.wav", profile=warn_profile
        )
    assert warned.diagnostics is not None
    assert warned.diagnostics.preclip_peak > 1.0
    assert warned.diagnostics.overload_samples > 0
    assert warned.diagnostics.clipped_samples == warned.diagnostics.overload_samples
    warned_samples, _ = sf.read(warned.path, dtype="float64", always_2d=True)
    assert np.max(np.abs(warned_samples)) <= 1.0

    float_profile = ExportProfile(
        name="float-headroom",
        bit_depth=32,
        normalization="none",
        clipping="clip",
    )
    floating = _loud_song(project_script).render(
        "renders/headroom.wav", sample_rate=16_000, profile=float_profile
    )
    assert floating.export_profile is not None
    assert floating.export_profile["delivery_sample_rate"] == 8_000
    assert floating.diagnostics is not None
    assert floating.diagnostics.overload_samples > 0
    assert floating.diagnostics.clipped_samples == 0
    floating_samples, rate = sf.read(floating.path, dtype="float64", always_2d=True)
    assert rate == 8_000
    assert np.max(np.abs(floating_samples)) > 1.0


def test_export_profile_normalizes_after_delivery_conversion_and_is_serializable(
    project_script: Path,
) -> None:
    profile = ExportProfile(
        name="delivery-48k",
        bit_depth=32,
        channels="mono",
        delivery_sample_rate=16_000,
        normalization="peak",
        normalization_target_dbfs=-6.0,
    )
    assert json.loads(json.dumps(profile.as_dict()))["name"] == "delivery-48k"
    result = _loud_song(project_script).render(
        "renders/delivery-profile.wav",
        sample_rate=8_000,
        profile=profile,
    )

    assert result.sample_rate == 16_000
    assert result.channels == 1
    assert result.export_profile == profile.as_dict()
    assert result.diagnostics is not None
    assert result.diagnostics.peak_before_normalization > 10.0 ** (-6.0 / 20.0)
    assert result.diagnostics.normalized is True
    assert result.diagnostics.preclip_peak == pytest.approx(10.0 ** (-6.0 / 20.0))
    samples, rate = sf.read(result.path, dtype="float64", always_2d=True)
    assert rate == 16_000
    assert samples.shape[1] == 1
    assert np.max(np.abs(samples)) == pytest.approx(10.0 ** (-6.0 / 20.0), abs=1e-6)


def test_export_profile_dither_is_seeded_and_only_applies_to_integer_delivery(
    project_script: Path,
) -> None:
    profile = ExportProfile(bit_depth=16, dither="tpdf", dither_seed=1234)
    settings = render_module._export_settings(
        _mini_song(project_script),
        bit_depth=16,
        channels="stereo",
        sample_rate=None,
        tail_seconds=0.0,
        profile=profile,
    )
    source = np.full((512, 2), 0.1234567, dtype=np.float64)
    first = render_module._prepare_export_diagnostics(
        source, 8_000, settings, normalize=False
    )
    second = render_module._prepare_export_diagnostics(
        source, 8_000, settings, normalize=False
    )
    assert first.diagnostics.dithered is True
    assert np.array_equal(first.samples, second.samples)
    assert not np.array_equal(first.samples, source)

    plain_settings = render_module._export_settings(
        _mini_song(project_script),
        bit_depth=32,
        channels="stereo",
        sample_rate=None,
        tail_seconds=0.0,
        profile=ExportProfile(bit_depth=32),
    )
    plain = render_module._prepare_export_diagnostics(
        source, 8_000, plain_settings, normalize=False
    )
    assert plain.diagnostics.dithered is False
    assert np.array_equal(plain.samples, source)
    with pytest.raises(ProjectError, match="TPDF"):
        ExportProfile(bit_depth=32, dither="tpdf")


def test_export_profile_rejects_nonfinite_audio_and_reports_silence(
    project_script: Path,
) -> None:
    song = _mini_song(project_script)
    profile = ExportProfile(bit_depth=32)
    settings = render_module._export_settings(
        song,
        bit_depth=32,
        channels="stereo",
        sample_rate=None,
        tail_seconds=0.0,
        profile=profile,
    )
    silence = render_module._prepare_export_diagnostics(
        np.zeros((32, 2), dtype=np.float64), 8_000, settings, normalize=False
    )
    assert silence.diagnostics.peak_before_normalization == 0.0
    assert silence.diagnostics.overload_samples == 0
    assert np.count_nonzero(silence.samples) == 0
    with pytest.raises(RenderError, match="non-finite"):
        render_module._prepare_export_diagnostics(
            np.array([[np.nan, np.inf]]), 8_000, settings, normalize=False
        )


def test_export_profile_detects_resampling_overshoot_before_fixed_point_clip(
    project_script: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def overshoot(
        samples: np.ndarray, source_rate: int, target_rate: int, **_: object
    ) -> np.ndarray:
        return np.full((samples.shape[0] * 2, samples.shape[1]), 1.5, dtype=np.float64)

    monkeypatch.setattr(render_module.soxr, "resample", overshoot)
    song = _mini_song(project_script)
    settings = render_module._export_settings(
        song,
        bit_depth=16,
        channels="stereo",
        sample_rate=16_000,
        tail_seconds=0.0,
        profile=ExportProfile(
            bit_depth=16,
            delivery_sample_rate=16_000,
            normalization="none",
            clipping="error",
        ),
    )
    with pytest.raises(RenderError, match="overloaded samples"):
        render_module._prepare_export_diagnostics(
            np.zeros((32, 2), dtype=np.float64), 8_000, settings, normalize=False
        )
    clipped_settings = render_module._export_settings(
        song,
        bit_depth=16,
        channels="stereo",
        sample_rate=16_000,
        tail_seconds=0.0,
        profile=ExportProfile(
            bit_depth=16,
            delivery_sample_rate=16_000,
            normalization="none",
            clipping="clip",
        ),
    )
    clipped = render_module._prepare_export_diagnostics(
        np.zeros((32, 2), dtype=np.float64),
        8_000,
        clipped_settings,
        normalize=False,
    )
    assert clipped.diagnostics.preclip_peak == pytest.approx(1.5)
    assert clipped.diagnostics.overload_samples == 128
    assert clipped.diagnostics.clipped_samples == 128
    assert np.max(np.abs(clipped.samples)) == 1.0


def test_render_can_downmix_resample_and_keep_an_effect_tail(
    project_script: Path,
) -> None:
    song = Project(
        "Tail Export",
        prism_version="test",
        tempo=240,
        sample_rate=8_000,
        normalize=False,
        _script=project_script,
    )
    kick = song.track("Last Kick").drum("kick", "---x")
    kick.effect("delay", time_beats=1, feedback=0.5, mix=1)
    song.section("One Bar", bars=1)

    result = song.render(
        "renders/tail.wav",
        bit_depth=24,
        channels="mono",
        sample_rate=16_000,
        tail_seconds=0.5,
    )
    samples, rate = sf.read(result.path, dtype="float64", always_2d=True)

    assert sf.info(result.path).subtype == "PCM_24"
    assert rate == result.sample_rate == 16_000
    assert samples.shape[1] == result.channels == 1
    assert abs(result.frames - 24_000) <= 1
    assert result.duration_seconds == pytest.approx(1.5, abs=1 / rate)
    assert result.tail_seconds == 0.5
    assert np.max(np.abs(samples[16_000:])) > 0.01


def test_render_stem_quality_options_apply_to_every_file(project_script: Path) -> None:
    song = Project(
        "Stem Quality",
        prism_version="test",
        tempo=300,
        sample_rate=8_000,
        _script=project_script,
    )
    kick = song.track("Kick").drum("kick", "x---")
    bus = song.bus("Drums", tracks=[kick])
    bus.effect("reverb", mix=1)
    song.section("Hit", bars=1)

    stems = song.render_stems(
        "renders/quality-stems",
        bit_depth=32,
        channels="mono",
        sample_rate=16_000,
        tail_seconds=0.25,
    )
    master = song.render(
        "renders/quality-master.wav",
        bit_depth=32,
        channels="mono",
        sample_rate=16_000,
        tail_seconds=0.25,
    )

    assert stems.bit_depth == 32
    assert stems.channels == 1
    assert stems.sample_rate == 16_000
    assert stems.tail_seconds == 0.25
    assert stems.master.path.read_bytes() == master.path.read_bytes()
    for item in stems.files:
        info = sf.info(item.path)
        assert info.subtype == "FLOAT"
        assert info.channels == 1
        assert info.samplerate == 16_000
        assert info.frames == stems.frames


def test_render_rejects_invalid_export_quality(project_script: Path) -> None:
    song = _mini_song(project_script)

    with pytest.raises(ProjectError, match="bit_depth"):
        song.render(bit_depth=20)  # type: ignore[arg-type]
    with pytest.raises(ProjectError, match="channels"):
        song.render(channels="surround")  # type: ignore[arg-type]
    with pytest.raises(ProjectError, match="sample_rate"):
        song.render(sample_rate=1_000)
    with pytest.raises(ProjectError, match="tail_seconds"):
        song.render(tail_seconds=-1)


def test_render_stems_rejects_unsafe_or_root_output(project_script: Path) -> None:
    song = _mini_song(project_script)

    with pytest.raises(ProjectError, match="relative"):
        song.render_stems("../stems")
    with pytest.raises(ProjectError, match="inside"):
        song.render_stems(".")


def test_render_stems_rejects_source_collisions_without_changing_audio(
    project_script: Path,
) -> None:
    source_directory = project_script.parent / "sounds" / "tracks"
    source_directory.mkdir(parents=True)
    vocal = source_directory / "01-vocal.wav"
    original_take = source_directory / "original-take.wav"
    source_samples = np.linspace(0.25, -0.25, 32, dtype=np.float32)
    sf.write(vocal, source_samples, 8_000, subtype="PCM_16")
    sf.write(original_take, source_samples, 8_000, subtype="PCM_16")
    before_vocal = vocal.read_bytes()
    before_original_take = original_take.read_bytes()

    song = Project(
        "Protected Sources", prism_version="test", sample_rate=8_000, _script=project_script
    )
    song.track("Vocal").sample("sounds/tracks/01-vocal.wav", bars=1)
    song.section("Only", bars=1)

    with pytest.raises(ProjectError, match="protected project file"):
        song.render_stems("sounds")
    with pytest.raises(ProjectError, match="protected project file"):
        song.render_stems("sounds/tracks")

    assert vocal.read_bytes() == before_vocal
    assert original_take.read_bytes() == before_original_take


def test_render_stems_rejects_scripts_and_plugin_states_as_output(
    project_script: Path,
) -> None:
    scripts = project_script.parent / "scripts"
    scripts.mkdir()
    (scripts / "prepare.py").write_text("# producer helper\n", encoding="utf-8")
    states = project_script.parent / "plugin-states"
    states.mkdir()
    (states / "lead.state").write_bytes(b"plugin state")

    song = _mini_song(project_script)
    with pytest.raises(ProjectError, match="protected project file"):
        song.render_stems("scripts")
    with pytest.raises(ProjectError, match="protected project file"):
        song.render_stems("plugin-states")


def test_render_stems_removes_only_unchanged_owned_files_after_rename_and_removal(
    project_script: Path,
) -> None:
    song = Project(
        "Changing Stems", tempo=240, prism_version="test", sample_rate=8_000, _script=project_script
    )
    renamed = song.track("Original").drum("kick", "x---")
    song.track("Other").drum("snare", "---- x---")
    song.section("Only", bars=1)

    first = song.render_stems("renders/stems")
    old_original = next(item.path for item in first.tracks if item.name == "Original")
    renamed.name = "Renamed"

    second = song.render_stems("renders/stems")
    new_renamed = next(item.path for item in second.tracks if item.name == "Renamed")
    assert new_renamed.is_file()
    assert not old_original.exists()

    song.tracks.remove(renamed)
    third = song.render_stems("renders/stems")

    assert all(item.name != "Renamed" for item in third.tracks)
    assert not new_renamed.exists()


def test_render_stems_preserves_modified_generated_and_added_files(
    project_script: Path,
) -> None:
    song = Project(
        "Preserve Producer Files",
        tempo=240,
        prism_version="test",
        sample_rate=8_000,
        _script=project_script,
    )
    song.track("Kick").drum("kick", "x---")
    song.section("Only", bars=1)

    first = song.render_stems("renders/stems")
    modified = first.tracks[0].path
    modified.write_bytes(b"producer changed this generated file")
    added = first.directory / "tracks" / "producer-added.wav"
    added.write_bytes(b"producer added this file")

    second = song.render_stems("renders/stems")

    assert modified.read_bytes() == b"producer changed this generated file"
    assert added.read_bytes() == b"producer added this file"
    assert second.tracks[0].path != modified
    assert second.tracks[0].path.is_file()


def test_render_stems_rejects_child_symlink_before_writing(
    project_script: Path, tmp_path: Path
) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    sentinel = outside / "sentinel.wav"
    sentinel.write_bytes(b"outside")
    container = tmp_path / "renders" / "stems"
    container.mkdir(parents=True)
    try:
        (container / "tracks").symlink_to(outside, target_is_directory=True)
    except (OSError, NotImplementedError) as error:
        pytest.skip(f"symlinks are unavailable: {error}")

    song = _mini_song(project_script)
    with pytest.raises(ProjectError, match="symlink"):
        song.render_stems("renders/stems")

    assert sentinel.read_bytes() == b"outside"
    assert not (outside / "master.wav").exists()


def test_render_stems_failure_keeps_previous_manifest_and_generation(
    project_script: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    song = _mini_song(project_script)
    first = song.render_stems("renders/stems")
    container = project_script.parent / "renders" / "stems"
    manifest_path = container / ".prism-stems" / "manifest.json"
    manifest_before = manifest_path.read_bytes()
    master_before = first.master.path.read_bytes()
    original_write_stem = render_module._write_stem
    calls = 0

    def fail_on_second_write(*args: object, **kwargs: object) -> StemFile:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("simulated middle stem failure")
        return original_write_stem(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(render_module, "_write_stem", fail_on_second_write)
    with pytest.raises(RenderError, match="Previous completed generation remains"):
        song.render_stems("renders/stems")

    assert calls == 2
    assert manifest_path.read_bytes() == manifest_before
    assert first.master.path.read_bytes() == master_before
    generations = container / ".prism-stems" / "generations"
    assert len([path for path in generations.iterdir() if path.is_dir()]) == 1
    assert not any(path.name.startswith(".staging-") for path in generations.iterdir())


def test_project_local_sample_is_loaded_and_resampled(
    project_script: Path, sample_file: Path
) -> None:
    song = Project(
        "Sample Beat",
        prism_version="test",
        tempo=120,
        sample_rate=16_000,
        _script=project_script,
    )
    song.track("Kick").sample("sounds/kick.wav", "x--- x---", bars=1)
    song.section("Loop", bars=2)

    result = song.render("renders/sample-beat.wav")
    samples, rate = sf.read(result.path, dtype="float32", always_2d=True)

    assert rate == 16_000
    assert samples.shape == (64_000, 2)
    assert np.max(np.abs(samples[:4_000])) > 0.1
    assert sample_file.is_file()


def test_audio_editing_options_change_source_and_are_serialized(
    project_script: Path, sample_file: Path
) -> None:
    def render(edited: bool, output: str) -> tuple[bytes, dict[str, object]]:
        song = Project(
            "Edited Audio",
            prism_version="test",
            sample_rate=8_000,
            normalize=False,
            _script=project_script,
        )
        track = song.track("Texture")
        if edited:
            track.audio(
                "sounds/kick.wav",
                bars=1,
                loop=False,
                start_seconds=0.02,
                end_seconds=0.08,
                fade_in_ms=8,
                fade_out_ms=12,
                reverse=True,
                playback_rate=0.8,
                transpose_semitones=7,
                stretch_bars=1,
            )
        else:
            track.audio("sounds/kick.wav", bars=1, loop=False)
        song.section("Only", bars=1, tracks=[track])
        part = song.configuration()["tracks"][0]["part"]  # type: ignore[index]
        return song.render(output).path.read_bytes(), part  # type: ignore[return-value]

    plain, _ = render(False, "renders/plain.wav")
    edited, part = render(True, "renders/edited.wav")
    assert plain != edited
    assert part["start_seconds"] == 0.02
    assert part["reverse"] is True
    assert part["transpose_semitones"] == 7
    assert part["stretch_bars"] == 1.0


def test_audio_one_shot_pads_without_looping(project_script: Path, sample_file: Path) -> None:
    song = Project(
        "One Shot", prism_version="test", sample_rate=8_000, _script=project_script
    )
    song.track("Texture").audio("sounds/kick.wav", bars=1, loop=False)
    song.section("Only", bars=1)

    result = song.render()
    samples, _ = sf.read(result.path, dtype="float32", always_2d=True)

    assert np.max(np.abs(samples[:800])) > 0.1
    assert np.max(np.abs(samples[1_000:])) == 0.0


def test_late_sample_trigger_keeps_release_in_export_tail(project_script: Path) -> None:
    _write_stereo_source(project_script, "late.wav", 8_000, value=0.25)
    song = Project(
        "Late Sample",
        prism_version="test",
        tempo=120,
        sample_rate=8_000,
        master_gain_db=0,
        normalize=False,
        _script=project_script,
    )
    song.track("Late").sample("sounds/late.wav", "---x", bars=1, repeat=False)
    song.section("Only", bars=1)

    result = song.render("renders/late.wav", tail_seconds=1.0)
    samples, _ = sf.read(result.path, dtype="float64", always_2d=True)

    assert result.frames == 24_000
    assert np.max(np.abs(samples[12_000:16_000])) > 0.1
    assert np.max(np.abs(samples[16_000:20_000])) > 0.1


def test_natural_one_shot_crosses_an_inactive_section_but_cut_does_not(
    project_script: Path,
) -> None:
    _write_stereo_source(project_script, "long-shot.wav", 20_000, value=0.25)

    def render(policy: str, output: str) -> np.ndarray:
        song = Project(
            f"{policy} release",
            prism_version="test",
            tempo=120,
            sample_rate=8_000,
            master_gain_db=0,
            normalize=False,
            audio_release_policy=policy,  # type: ignore[arg-type]
            _script=project_script,
        )
        track = song.track("Shot").audio(
            "sounds/long-shot.wav",
            bars=1,
            loop=False,
            repeat=False,
        )
        song.section("Active", bars=1, tracks=[track])
        song.section("Inactive", bars=1, tracks=[])
        result = song.render(output, tail_seconds=1.0)
        return sf.read(result.path, dtype="float64", always_2d=True)[0]

    natural = render("natural", "renders/natural.wav")
    cut = render("cut", "renders/cut.wav")

    assert np.max(np.abs(natural[16_000:20_000])) > 0.1
    assert np.max(np.abs(cut[16_000:])) == 0.0


def test_loop_and_repeat_are_independent_for_audio_placements(project_script: Path) -> None:
    _write_stereo_source(project_script, "short.wav", 2_000, value=0.25)

    loop_song = Project(
        "One loop placement",
        prism_version="test",
        tempo=120,
        sample_rate=8_000,
        master_gain_db=0,
        normalize=False,
        _script=project_script,
    )
    loop_song.track("Loop").audio(
        "sounds/short.wav", bars=1, loop=True, repeat=False
    )
    loop_song.section("Two bars", bars=2)
    loop_result = loop_song.render("renders/loop.wav")
    loop_samples, _ = sf.read(loop_result.path, dtype="float64", always_2d=True)

    repeat_song = Project(
        "Repeated one shots",
        prism_version="test",
        tempo=120,
        sample_rate=8_000,
        master_gain_db=0,
        normalize=False,
        _script=project_script,
    )
    repeat_song.track("Shots").audio(
        "sounds/short.wav", bars=1, loop=False, repeat=True
    )
    repeat_song.section("Two bars", bars=2)
    repeat_result = repeat_song.render("renders/repeat.wav")
    repeat_samples, _ = sf.read(repeat_result.path, dtype="float64", always_2d=True)

    assert np.max(np.abs(loop_samples[:16_000])) > 0.1
    assert np.max(np.abs(loop_samples[16_000:])) == 0.0
    assert np.max(np.abs(repeat_samples[8_000:16_000])) == 0.0
    assert np.max(np.abs(repeat_samples[16_000:18_000])) > 0.1


def test_repeated_sample_hits_overlap_naturally_or_choke_explicitly(
    project_script: Path,
) -> None:
    _write_stereo_source(project_script, "overlap.wav", 10_000, value=0.2)

    def render(policy: str, output: str) -> np.ndarray:
        song = Project(
            f"{policy} hits",
            prism_version="test",
            tempo=120,
            sample_rate=8_000,
            master_gain_db=0,
            normalize=False,
            _script=project_script,
        )
        song.track("Hits").sample(
            "sounds/overlap.wav",
            "x-x-",
            bars=1,
            repeat=False,
            release_policy=policy,  # type: ignore[arg-type]
        )
        song.section("Only", bars=1)
        result = song.render(output)
        return sf.read(result.path, dtype="float64", always_2d=True)[0]

    natural = render("natural", "renders/natural-hits.wav")
    choke = render("choke", "renders/choke-hits.wav")

    assert np.mean(np.abs(natural[8_800:9_200])) > 1.5 * np.mean(
        np.abs(choke[8_800:9_200])
    )


def test_cut_fade_ends_at_the_actual_arrangement_boundary(project_script: Path) -> None:
    _write_stereo_source(project_script, "cut.wav", 20_000, value=0.25)
    song = Project(
        "Cut Fade",
        prism_version="test",
        tempo=120,
        sample_rate=8_000,
        master_gain_db=0,
        normalize=False,
        _script=project_script,
    )
    song.track("Cut").audio(
        "sounds/cut.wav",
        bars=1,
        loop=False,
        repeat=False,
        fade_out_ms=500,
        release_policy="cut",
    )
    song.section("Only", bars=1)

    result = song.render("renders/cut-fade.wav", tail_seconds=0.5)
    samples, _ = sf.read(result.path, dtype="float64", always_2d=True)

    assert np.max(np.abs(samples[8_000:12_000])) > 0.1
    assert np.max(np.abs(samples[14_000:16_000])) < 0.13
    assert np.max(np.abs(samples[15_999])) == 0.0
    assert np.max(np.abs(samples[16_000:])) == 0.0


def test_native_percussion_release_is_not_step_choked_by_default(
    project_script: Path,
) -> None:
    def render(policy: str, output: str) -> np.ndarray:
        song = Project(
            f"{policy} percussion",
            prism_version="test",
            tempo=300,
            sample_rate=8_000,
            master_gain_db=0,
            normalize=False,
            _script=project_script,
        )
        song.track("Kick").drum("kick", "x---", release_policy=policy)  # type: ignore[arg-type]
        song.section("Only", bars=1)
        result = song.render(output)
        return sf.read(result.path, dtype="float64", always_2d=True)[0]

    natural = render("natural", "renders/natural-kick.wav")
    legacy = render("legacy", "renders/legacy-kick.wav")

    assert np.max(np.abs(natural[1_600:2_400])) > 0.001
    assert np.max(np.abs(legacy[1_600:2_400])) == 0.0


def test_release_tail_is_frame_aligned_in_stems_and_master(project_script: Path) -> None:
    _write_stereo_source(project_script, "tail.wav", 8_000, value=0.25)
    song = Project(
        "Aligned Tail",
        prism_version="test",
        tempo=120,
        sample_rate=8_000,
        master_gain_db=0,
        normalize=False,
        _script=project_script,
    )
    track = song.track("Tail").audio("sounds/tail.wav", loop=False, repeat=False)
    song.section("Only", bars=1, tracks=[track])

    stems = song.render_stems("renders/tail-stems", tail_seconds=0.5)
    master = song.render("renders/tail-master.wav", tail_seconds=0.5)

    assert stems.frames == master.frames == 20_000
    assert stems.master.path.read_bytes() == master.path.read_bytes()
    for item in stems.files:
        samples, rate = sf.read(item.path, dtype="float64", always_2d=True)
        assert rate == 8_000
        assert samples.shape == (stems.frames, stems.channels)


def test_section_clip_replaces_default_and_starts_at_requested_bar(
    project_script: Path,
) -> None:
    song = Project(
        "Placed Clips",
        prism_version="test",
        tempo=120,
        sample_rate=8_000,
        normalize=False,
        _script=project_script,
    )
    kick = song.track("Kick").drum("kick", "x---")
    kick.drum(
        "kick",
        "x---",
        section="Chorus",
        start_bar=1,
        repeat=False,
    )
    song.section("Verse", bars=1, tracks=[kick])
    song.section("Chorus", bars=2, tracks=[kick])

    result = song.render("renders/placed.wav")
    samples, _ = sf.read(result.path, dtype="float64", always_2d=True)
    bar = song.frames_per_bar

    assert np.max(np.abs(samples[:bar])) > 0.1
    assert np.max(np.abs(samples[bar : 2 * bar])) == 0.0
    assert np.max(np.abs(samples[2 * bar :])) > 0.1


def test_render_rejects_unsafe_or_wrong_output(project_script: Path) -> None:
    song = _mini_song(project_script)
    with pytest.raises(ProjectError, match="relative"):
        song.render("../song.wav")
    with pytest.raises(ProjectError, match=".wav"):
        song.render("renders/song.mp3")


def test_render_rejects_symlink_output_before_writing(
    project_script: Path, tmp_path: Path
) -> None:
    outside = tmp_path / "outside.wav"
    outside.write_bytes(b"outside")
    renders = tmp_path / "renders"
    renders.mkdir()
    try:
        (renders / "song.wav").symlink_to(outside)
    except (OSError, NotImplementedError) as error:
        pytest.skip(f"symlinks are unavailable: {error}")

    with pytest.raises(ProjectError, match="symlink"):
        _mini_song(project_script).render("renders/song.wav")

    assert outside.read_bytes() == b"outside"


def test_render_reports_unsupported_multichannel_source(
    project_script: Path, tmp_path: Path
) -> None:
    sounds = tmp_path / "sounds"
    sounds.mkdir()
    sf.write(sounds / "wide.wav", np.zeros((100, 3), dtype=np.float32), 8_000)
    song = Project("Wide", prism_version="test", sample_rate=8_000, _script=project_script)
    song.track("Wide").audio("sounds/wide.wav")
    song.section("Only", bars=1)
    with pytest.raises(RenderError, match="mono or stereo"):
        song.render()

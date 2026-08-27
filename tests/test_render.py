from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from prism import Project, ProjectError, RenderError


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

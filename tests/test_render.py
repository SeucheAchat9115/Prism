from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from prism import Project, ProjectError, RenderError


def _mini_song(script: Path) -> Project:
    song = Project(script, "Deterministic Mini Song", tempo=120, sample_rate=8_000)
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


def test_render_is_non_silent_deterministic_and_manifested(project_script: Path) -> None:
    song = _mini_song(project_script)

    first = song.render("renders/first.wav")
    second = song.render("renders/second.wav")
    samples, sample_rate = sf.read(first.path, dtype="float32", always_2d=True)
    manifest = json.loads(first.manifest_path.read_text(encoding="utf-8"))

    assert first.path.read_bytes() == second.path.read_bytes()
    assert first.sha256 == hashlib.sha256(first.path.read_bytes()).hexdigest()
    assert sample_rate == 8_000
    assert samples.shape == (96_000, 2)
    assert np.max(np.abs(samples)) > 0.05
    assert manifest["script"] == "main.py"
    assert manifest["script_sha256"] == hashlib.sha256(project_script.read_bytes()).hexdigest()
    assert manifest["render"]["sha256"] == second.sha256
    assert manifest["tracks"][3]["part"]["kind"] == "midi"


def test_project_local_sample_is_loaded_resampled_and_hashed(
    project_script: Path, sample_file: Path
) -> None:
    song = Project(project_script, "Sample Beat", tempo=120, sample_rate=16_000)
    song.track("Kick").sample("sounds/kick.wav", "x--- x---", bars=1)
    song.section("Loop", bars=2)

    result = song.render("renders/sample-beat.wav")
    samples, rate = sf.read(result.path, dtype="float32", always_2d=True)
    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))

    assert rate == 16_000
    assert samples.shape == (64_000, 2)
    assert np.max(np.abs(samples[:4_000])) > 0.1
    assert manifest["sources"]["sounds/kick.wav"]["sha256"] == hashlib.sha256(
        sample_file.read_bytes()
    ).hexdigest()


def test_audio_one_shot_pads_without_looping(project_script: Path, sample_file: Path) -> None:
    song = Project(project_script, "One Shot", sample_rate=8_000)
    song.track("Texture").audio("sounds/kick.wav", bars=1, loop=False)
    song.section("Only", bars=1)

    result = song.render()
    samples, _ = sf.read(result.path, dtype="float32", always_2d=True)

    assert np.max(np.abs(samples[:800])) > 0.1
    assert np.max(np.abs(samples[1_000:])) == 0.0


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
    song = Project(project_script, "Wide", sample_rate=8_000)
    song.track("Wide").audio("sounds/wide.wav")
    song.section("Only", bars=1)
    with pytest.raises(RenderError, match="mono or stereo"):
        song.render()

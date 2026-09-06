from __future__ import annotations

import json
import shutil
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from prism import VST3, ExportProfile, Project, ProjectError
from prism.fingerprint import (
    migrate_project_configuration,
    migrate_render_manifest,
)
from prism.vst import VSTRegistry


def _write_script(path: Path, text: str = "# reproducible project\n") -> None:
    path.write_text(text, encoding="utf-8")


def _write_source(path: Path, value: float = 0.25) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(
        path,
        np.full((128, 2), value, dtype=np.float32),
        8_000,
        subtype="PCM_16",
    )
    return path


def _sample_song(script: Path, source: str = "sounds/kick.wav") -> Project:
    song = Project(
        "Fingerprint Song",
        prism_version="0.2.0.dev0",
        tempo=120,
        sample_rate=8_000,
        _script=script,
    )
    song.track("Kick").sample(source, "x---")
    song.track("Hat").drum("hihat", "x---", seed=11)
    song.section("Loop", bars=1)
    return song


def test_fingerprint_is_portable_cached_and_sensitive_to_content_and_settings(
    tmp_path: Path,
) -> None:
    root = tmp_path / "song"
    root.mkdir()
    script = root / "main.py"
    _write_script(script, "# first revision\n")
    source = _write_source(root / "sounds" / "kick.wav")
    song = _sample_song(script)

    first = song.fingerprint()
    second = song.fingerprint()

    assert first.portable_sha256 == second.portable_sha256
    assert first.render_key == second.render_key
    assert first.script.path == "main.py"
    assert first.source_audio[0].path == "sounds/kick.wav"
    assert any(item["value"] == 11 for item in first.seeds)
    cache = root / ".prism-cache" / "fingerprints.json"
    assert cache.is_file()
    assert str(root) not in cache.read_text(encoding="utf-8")
    json.loads(json.dumps(first.as_dict()))

    profile = ExportProfile(name="float", bit_depth=32, normalization="none")
    assert song.fingerprint(profile=profile).portable_sha256 != first.portable_sha256
    assert (
        song.fingerprint(stem_mode="channel_taps").portable_sha256
        != song.fingerprint(stem_mode="master_inputs").portable_sha256
    )

    original = source.read_bytes()
    source.write_bytes(bytes((byte ^ 0x01) for byte in original))
    changed_source = song.fingerprint()
    assert changed_source.source_audio[0].sha256 != first.source_audio[0].sha256
    assert changed_source.portable_sha256 != first.portable_sha256

    moved_root = tmp_path / "moved-project"
    moved_root.mkdir()
    shutil.copy2(script, moved_root / "main.py")
    shutil.copytree(root / "sounds", moved_root / "sounds")
    moved = _sample_song(moved_root / "main.py")
    moved_fingerprint = moved.fingerprint()
    assert moved_fingerprint.portable_sha256 == changed_source.portable_sha256


def test_fingerprint_records_external_plugin_assets_and_invalidates_them(tmp_path: Path) -> None:
    root = tmp_path / "song"
    root.mkdir()
    script = root / "main.py"
    _write_script(script)
    _write_source(root / "sounds" / "kick.wav")
    state = root / "plugin-states" / "fake.state"
    state.parent.mkdir()
    state.write_bytes(b"state-v1")
    bundle = root / "plugins" / "Fake.vst3"
    (bundle / "Contents").mkdir(parents=True)
    binary = bundle / "Contents" / "x86_64-linux" / "Fake.so"
    binary.parent.mkdir()
    binary.write_bytes(b"plugin-v1")

    registry = VSTRegistry(root)
    registry.initialize()
    entry = registry.add("fake", bundle)
    song = Project(
        "External Fingerprint Song",
        prism_version="0.2.0.dev0",
        tempo=120,
        sample_rate=8_000,
        _script=script,
    )
    track = song.track("External")
    track.sample("sounds/kick.wav", "x---")
    track.effect(VST3("fake", state="plugin-states/fake.state"))
    song.section("Loop", bars=1, tracks=[track])

    first = song.fingerprint()
    assert first.deterministic is False
    assert first.external_backend["name"] == "dawdreamer"
    assert first.external_backend["determinism"] == "conditional_external"
    assert first.vst_binaries == (
        {"alias": entry.alias, "platform": entry.platform, "sha256": entry.sha256},
    )
    assert first.plugin_states[0].path == "plugin-states/fake.state"

    state.write_bytes(b"state-v2")
    changed_state = song.fingerprint()
    assert changed_state.plugin_states[0].sha256 != first.plugin_states[0].sha256
    assert changed_state.portable_sha256 != first.portable_sha256

    binary.write_bytes(b"plugin-v2")
    with pytest.raises(ProjectError, match="has changed"):
        song.fingerprint()


def test_fingerprint_migrations_reject_future_versions() -> None:
    migrated = migrate_project_configuration({"schema_version": 10, "name": "Old"})
    assert migrated["schema_version"] == 11
    assert migrated["migrated_from_schema_version"] == 10
    assert migrated["timing_compatibility"]
    assert migrated["automation_compatibility"]
    assert migrated["audio_release_policy"] == "legacy"
    assert migrated["controller_boundary"] == "legacy"

    with pytest.raises(ProjectError, match="newer"):
        migrate_project_configuration({"schema_version": 12})

    manifest = migrate_render_manifest({"schema_version": 1, "generation": 2})
    assert manifest["schema_version"] == 2
    assert manifest["fingerprint"] == {}
    with pytest.raises(ProjectError, match="newer"):
        migrate_render_manifest({"schema_version": 3})


def test_fingerprint_reports_missing_assets(tmp_path: Path) -> None:
    root = tmp_path / "song"
    root.mkdir()
    script = root / "main.py"
    _write_script(script)
    song = _sample_song(script)
    with pytest.raises(ProjectError, match="missing"):
        song.fingerprint()

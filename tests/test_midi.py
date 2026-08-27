from __future__ import annotations

from pathlib import Path

import pytest

from prism import Project, ProjectError


def test_midi_export_contains_conductor_drums_and_notes(project_script: Path) -> None:
    song = Project(project_script, "MIDI Song", tempo=90, beats_per_bar=3)
    kick = song.track("Kick").drum("kick", "x-- x--")
    bass = song.track("Bass").midi("C2 - G1", instrument="bass", gate=0.5)
    song.section("A", bars=2, tracks=[kick, bass])

    first = song.export_midi("renders/song.mid")
    payload = first.path.read_bytes()
    second = song.export_midi("renders/song-again.mid")

    assert payload[:4] == b"MThd"
    assert payload.count(b"MTrk") == 3
    assert payload == second.path.read_bytes()
    assert first.tracks == 2
    assert first.ticks_per_beat == 480
    assert len(first.sha256) == 64


def test_midi_export_requires_midi_capable_tracks(project_script: Path, sample_file: Path) -> None:
    song = Project(project_script, "Audio Only")
    song.track("Sample").sample("sounds/kick.wav")
    song.section("Only", bars=1)
    with pytest.raises(ProjectError, match="no built-in drum or MIDI tracks"):
        song.export_midi()


def test_one_midi_track_uses_readable_singular_word(project_script: Path) -> None:
    song = Project(project_script, "Solo")
    song.track("Lead").midi("C4")
    song.section("Only", bars=1)

    assert "1 MIDI track to" in str(song.export_midi())

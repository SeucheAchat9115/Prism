"""Exercise the installed public package without importing repository helpers."""

from __future__ import annotations

import tempfile
from pathlib import Path

import soundfile as sf

from prism import Project


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="prism-wheel-") as temporary:
        root = Path(temporary)
        script = root / "main.py"
        script.write_text("# clean-wheel Prism smoke project\n", encoding="utf-8")
        song = Project(script, "Wheel Smoke", tempo=120)
        kick = song.track("Kick").drum("kick", "x--- x--- x--- x---")
        song.track("Bass").midi("C2 - C2 - G1 - Bb1 -", instrument="bass")
        song.section("Loop", bars=2, tracks=[kick, "Bass"])
        midi = song.export_midi("renders/wheel-smoke.mid")
        render = song.render("renders/wheel-smoke.wav")
        info = sf.info(render.path)
        assert info.channels == 2
        assert info.frames == render.frames
        assert midi.path.is_file()
        assert render.manifest_path.is_file()


if __name__ == "__main__":
    main()

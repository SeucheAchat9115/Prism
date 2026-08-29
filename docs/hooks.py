"""Small deterministic assets generated as part of the documentation build."""

from pathlib import Path

from prism import Project, Uniwave, __version__


def on_pre_build(*, config: object) -> None:
    """Render the documentation audio player with the installed Prism version."""

    song = Project(
        "Documentation Demo",
        prism_version=__version__,
        tempo=112,
        sample_rate=22_050,
        master_gain_db=-4,
        _script=Path(__file__),
    )
    kick = song.track("Kick", gain_db=-4).drum("kick", "x--- x--- x--- x---")
    snare = song.track("Snare", gain_db=-8).drum("snare", "---- x--- ---- x---")
    hat = song.track("Hi-hat", gain_db=-12).drum("hihat", "x-x- x-x- x-x- x-x-")
    bass = song.track("Bass", gain_db=-8).midi(
        "C2 - C2 Eb2 | G1 - Bb1 -",
        instrument=Uniwave.bass(),
        bars=2,
    )
    bass.effect("chorus", rate_hz=0.7, depth_ms=4, mix=0.18)
    song.section("Demo", bars=2, tracks=[kick, snare, hat, bass])
    song.render("assets/audio/uniwave-demo.wav")

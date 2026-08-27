from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import soundfile as sf


@pytest.fixture
def project_script(tmp_path: Path) -> Path:
    script = tmp_path / "main.py"
    script.write_text("# reproducible Prism project\n", encoding="utf-8")
    return script


@pytest.fixture
def sample_file(tmp_path: Path) -> Path:
    sounds = tmp_path / "sounds"
    sounds.mkdir()
    path = sounds / "kick.wav"
    samples = np.linspace(0.8, 0.0, 800, dtype=np.float32)
    sf.write(path, samples, 8_000, subtype="PCM_16")
    return path

from __future__ import annotations

import ast
from pathlib import Path

import pytest

import prism


def test_public_package_is_small_and_script_first() -> None:
    assert prism.__version__ == "0.2.0.dev0"
    assert set(prism.__all__) == {
        "AutomationLane",
        "AutomationPoint",
        "MidiResult",
        "Plugin",
        "PrismError",
        "Project",
        "ProjectError",
        "ProjectSummary",
        "RenderError",
        "RenderResult",
        "Section",
        "Track",
        "__version__",
    }


def test_legacy_runtime_interfaces_and_examples_are_absent() -> None:
    root = Path(__file__).resolve().parents[1]
    assert not list((root / "examples").glob("*.py"))
    assert not list((root / "examples" / "tutorials").glob("*.md"))
    assert not list((root / "src" / "prism" / "api").glob("*.py"))
    assert not list((root / "src" / "prism" / "command_line").glob("*.py"))
    assert not list((root / "src" / "prism" / "web").rglob("*.html"))
    assert not list((root / "src" / "prism" / "web").rglob("*.js"))
    packaging = (root / "pyproject.toml").read_text(encoding="utf-8")
    assert 'prism = "prism.cli:main"' in packaging


def test_progressive_tutorial_is_the_only_learning_surface() -> None:
    root = Path(__file__).resolve().parents[1]
    index = (root / "tutorial" / "README.md").read_text(encoding="utf-8")
    expected = (
        "00-create-a-project.md",
        "01-first-render.md",
        "02-use-your-own-samples.md",
        "03-write-midi.md",
        "04-build-a-mini-song.md",
        "05-shape-and-mix.md",
        "06-work-with-an-agent.md",
        "07-audio-loops-and-one-shots.md",
        "08-inspect-and-reproduce.md",
        "09-complete-reference-project.md",
        "10-parameter-reference.md",
        "11-plugins-and-automation.md",
        "12-clips-variations-and-fills.md",
    )
    for name in expected:
        assert (root / "tutorial" / name).is_file()
        assert f"]({name})" in index


@pytest.mark.parametrize(
    "tutorial_name",
    (
        "01-first-render.md",
        "03-write-midi.md",
        "04-build-a-mini-song.md",
        "05-shape-and-mix.md",
        "06-work-with-an-agent.md",
        "08-inspect-and-reproduce.md",
        "11-plugins-and-automation.md",
        "12-clips-variations-and-fills.md",
    ),
)
def test_complete_tutorial_projects_are_readable_and_runnable(
    tmp_path: Path, tutorial_name: str
) -> None:
    root = Path(__file__).resolve().parents[1]
    document = (root / "tutorial" / tutorial_name).read_text(encoding="utf-8")
    code = document.split("```python", maxsplit=1)[1].split("```", maxsplit=1)[0].strip()
    tree = ast.parse(code)
    imports = [node for node in tree.body if isinstance(node, ast.ImportFrom)]

    assert len(code.splitlines()) <= 90
    assert any(node.module == "prism" for node in imports)
    assert not any(isinstance(node, ast.ClassDef | ast.FunctionDef) for node in tree.body)
    assert "__file__" not in code
    assert 'prism_version="0.2.0.dev0"' in code

    script = tmp_path / "main.py"
    script.write_text(code + "\n", encoding="utf-8")
    namespace = {"__file__": str(script), "__name__": "__main__"}
    exec(compile(code, script, "exec"), namespace)

    output = tmp_path / "renders" / "song.wav"
    assert output.is_file()


def test_complete_reference_mentions_every_authoring_feature() -> None:
    root = Path(__file__).resolve().parents[1]
    document = (root / "tutorial" / "09-complete-reference-project.md").read_text(
        encoding="utf-8"
    )
    expected = (
        ".sample(",
        ".audio(",
        '"kick"',
        '"snare"',
        '"hihat"',
        'instrument="bass"',
        '.instrument(',
        'instrument="pad"',
        "velocity=",
        "waveform=",
        'waveform="sine"',
        'waveform="triangle"',
        'waveform="saw"',
        'waveform="square"',
        "attack_ms=",
        "decay_ms=",
        "sustain=",
        "release_ms=",
        "cutoff_hz=",
        "gate=",
        "muted=True",
        ".configuration()",
        ".effect(",
        ".automation(",
        ".export_midi(",
        ".render(",
    )
    for token in expected:
        assert token in document


def test_user_documentation_never_requires_file_dunder_or_changing_folders() -> None:
    root = Path(__file__).resolve().parents[1]
    documents = [root / "README.md", *sorted((root / "tutorial").glob("*.md"))]
    text = "\n".join(path.read_text(encoding="utf-8") for path in documents)

    assert "__file__" not in text
    assert "uv run python" not in text
    assert "cd my-song" not in text
    assert "cd tutorial-song" not in text
    assert "tutorial-song" not in text
    assert ".prism" not in text
    assert "project.json" not in text
    assert "manifest" not in text.lower()
    assert "zip" not in text.lower()


def test_generated_projects_are_ignored() -> None:
    root = Path(__file__).resolve().parents[1]
    gitignore = (root / ".gitignore").read_text(encoding="utf-8")
    assert "/projects/" in gitignore.splitlines()


def test_stock_plugin_contributor_guide_is_complete_and_packaged() -> None:
    root = Path(__file__).resolve().parents[1]
    guide = (root / "docs" / "adding-stock-plugins.md").read_text(encoding="utf-8")
    packaging = (root / "pyproject.toml").read_text(encoding="utf-8")

    for topic in (
        "Add a stock effect",
        "Add a stock melodic instrument",
        "Add a stock percussion instrument",
        "automation",
        "MIDI",
        "deterministic",
        "tests/test_plugins.py",
    ):
        assert topic in guide
    assert '"/docs"' in packaging
    assert "docs/adding-stock-plugins.md" in (root / "README.md").read_text(
        encoding="utf-8"
    )

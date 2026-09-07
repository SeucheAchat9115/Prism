
from __future__ import annotations

from pathlib import Path

from prism import Project, build_project


def run_contract_tutorial(document: Path, root: Path) -> Project:
    """Materialize the contract tutorial in a temporary project and build it."""

    text = document.read_text(encoding="utf-8")
    try:
        code = text.split("~~~python", maxsplit=1)[1].split("~~~", maxsplit=1)[0].strip()
    except IndexError as error:
        raise AssertionError("The contract tutorial must contain a Python example.") from error
    root.mkdir(parents=True, exist_ok=True)
    (root / "main.py").write_text(code + "\n", encoding="utf-8")
    return build_project(root)

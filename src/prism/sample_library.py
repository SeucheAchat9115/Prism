"""Project-local sample discovery with readable filenames and errors."""

from __future__ import annotations

from difflib import get_close_matches
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Self

from prism.errors import ProjectError

AUDIO_EXTENSIONS = frozenset({".aif", ".aiff", ".flac", ".ogg", ".wav", ".wave"})


class SampleLibrary:
    """The sample folders searched when a track uses a short filename.

    Every project starts with ``sounds`` registered. Additional folders must
    remain inside the project so copying the project keeps its audio sources.
    """

    def __init__(self, root: Path) -> None:
        self._root = root.resolve(strict=False)
        self._folders: list[str] = ["sounds"]

    @property
    def folders(self) -> tuple[str, ...]:
        """Return registered project-relative folders in search order."""

        return tuple(self._folders)

    def add_folder(self, path: str | Path) -> Self:
        """Register an existing project-local folder for short-name lookup."""

        relative, resolved = _project_path(self._root, path, label="Sample folder")
        if not resolved.is_dir():
            raise ProjectError(f"Sample folder does not exist: {relative}")
        if all(folder.casefold() != relative.casefold() for folder in self._folders):
            self._folders.append(relative)
        return self

    def files(self) -> tuple[str, ...]:
        """List supported audio files in all registered folders."""

        found: dict[Path, str] = {}
        for folder in self._folders:
            directory = (self._root / folder).resolve(strict=False)
            if not directory.is_dir():
                continue
            for path in directory.rglob("*"):
                if path.is_file() and path.suffix.casefold() in AUDIO_EXTENSIONS:
                    resolved = path.resolve(strict=False)
                    try:
                        relative = resolved.relative_to(self._root).as_posix()
                    except ValueError:
                        continue
                    found[resolved] = relative
        return tuple(sorted(found.values(), key=str.casefold))

    def find(self, name: str | Path) -> str:
        """Resolve a short filename or validate an explicit relative path."""

        relative, resolved = _project_path(self._root, name, label="Sample path")
        raw = str(name)
        posix = PurePosixPath(raw)
        windows = PureWindowsPath(raw)
        explicit = len(posix.parts) > 1 or len(windows.parts) > 1
        if explicit or resolved.is_file():
            return relative

        matches = [
            candidate
            for candidate in self.files()
            if Path(candidate).name.casefold() == Path(relative).name.casefold()
        ]
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            choices = ", ".join(repr(candidate) for candidate in matches)
            raise ProjectError(
                f"Sample name {Path(relative).name!r} is ambiguous. "
                f"Use one of these relative paths: {choices}."
            )

        available = {Path(candidate).name: candidate for candidate in self.files()}
        suggestion = get_close_matches(
            Path(relative).name,
            available,
            n=1,
            cutoff=0.55,
        )
        hint = ""
        if suggestion:
            hint = f" Did you mean {suggestion[0]!r}?"
        folders = ", ".join(repr(folder) for folder in self._folders)
        raise ProjectError(
            f"Sample {Path(relative).name!r} was not found in {folders}.{hint}"
        )


def project_audio_files(root: Path) -> tuple[Path, ...]:
    """List supported audio files in a project without executing its script."""

    resolved_root = root.resolve(strict=False)
    files: list[Path] = []
    for path in resolved_root.rglob("*"):
        if not path.is_file() or path.suffix.casefold() not in AUDIO_EXTENSIONS:
            continue
        resolved = path.resolve(strict=False)
        try:
            relative = resolved.relative_to(resolved_root)
        except ValueError:
            continue
        folders = {part.casefold() for part in relative.parts[:-1]}
        if "renders" not in folders and not any(
            part.startswith(".") for part in relative.parts
        ):
            files.append(resolved)
    return tuple(
        sorted(
            files,
            key=lambda path: path.relative_to(resolved_root).as_posix().casefold(),
        )
    )


def _project_path(root: Path, value: str | Path, *, label: str) -> tuple[str, Path]:
    raw = str(value)
    posix = PurePosixPath(raw)
    windows = PureWindowsPath(raw)
    if (
        not raw.strip()
        or posix.is_absolute()
        or bool(windows.drive)
        or bool(windows.root)
        or ".." in posix.parts
        or ".." in windows.parts
    ):
        raise ProjectError(f"{label} must be relative to the project folder.")
    resolved = (root / Path(value)).resolve(strict=False)
    try:
        relative = resolved.relative_to(root).as_posix()
    except ValueError as error:
        raise ProjectError(f"{label} must stay inside the project folder.") from error
    if resolved == root:
        raise ProjectError(f"{label} cannot be the complete project folder.")
    return relative, resolved


__all__ = ["SampleLibrary"]

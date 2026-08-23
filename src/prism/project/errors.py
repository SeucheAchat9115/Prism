"""Errors and structured validation issues for Prism projects."""

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class ValidationIssue:
    """One actionable problem found in a project or archive."""

    code: str
    path: str
    message: str

    def as_dict(self) -> dict[str, str]:
        return {"code": self.code, "path": self.path, "message": self.message}


class ProjectArchiveError(Exception):
    """Base class for project archive failures."""


class InvalidArchiveError(ProjectArchiveError):
    """The project is not a valid or safe ZIP archive."""


class InvalidProjectError(ProjectArchiveError):
    """The manifest cannot be parsed as a current project."""

    def __init__(self, message: str, *, issues: tuple[ValidationIssue, ...] = ()) -> None:
        super().__init__(message)
        self.issues = issues


class ProjectValidationError(ProjectArchiveError):
    """The project contains one or more actionable validation issues."""

    def __init__(self, issues: tuple[ValidationIssue, ...] | list[ValidationIssue]) -> None:
        self.issues = tuple(issues)
        message = "; ".join(f"{issue.path}: {issue.message}" for issue in self.issues)
        super().__init__(message or "Project validation failed")

    def as_dict(self) -> dict[str, Any]:
        return {"ok": False, "issues": [issue.as_dict() for issue in self.issues]}


class UnsupportedSchemaVersionError(ProjectArchiveError):
    """The archive uses a schema newer than this Prism version."""


class MigrationError(ProjectArchiveError):
    """A project migration is missing or failed."""


class AssetImportError(ProjectArchiveError):
    """An audio asset could not be safely imported."""


class WorkingProjectError(ProjectArchiveError):
    """A working-project repository operation failed."""


class ProjectLockedError(WorkingProjectError):
    """Another process already owns the writable project."""


class ExternalProjectChangeError(WorkingProjectError):
    """The portable source or working manifest changed outside the repository."""


class ProjectResourceLimitError(WorkingProjectError):
    """An archive, upload, or request exceeded a configured resource limit."""


class StagedUploadError(WorkingProjectError):
    """A staged audio upload is missing, expired, or invalid."""

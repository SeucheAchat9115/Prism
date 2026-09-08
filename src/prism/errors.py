"""Friendly public exceptions raised by Prism."""

from __future__ import annotations

from typing import Mapping


class PrismError(Exception):
    """Base class for errors a producer can fix in a project script."""


class ProjectError(PrismError):
    """The Python project description or one of its source files is invalid."""


class RenderError(PrismError):
    """Prism could not create the requested audio or MIDI artifact."""


class AgentError(PrismError):
    """A provider-neutral agent operation could not be completed.

    The regular Python authoring API raises this exception when a caller wants
    normal exception semantics.  The agent operation adapter serializes the
    same code and details into its result envelope so a CLI or another tool
    never has to parse human-oriented exception text.
    """

    def __init__(
        self,
        code: str,
        message: str,
        *,
        details: Mapping[str, object] | None = None,
    ) -> None:
        self.code = code
        self.details = dict(details or {})
        super().__init__(message)

    def as_dict(self) -> dict[str, object]:
        """Return the stable machine-readable error shape."""

        return {
            "code": self.code,
            "message": str(self),
            "details": dict(self.details),
        }

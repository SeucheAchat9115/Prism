"""Friendly public exceptions raised by Prism."""


class PrismError(Exception):
    """Base class for errors a producer can fix in a project script."""


class ProjectError(PrismError):
    """The Python project description or one of its source files is invalid."""


class RenderError(PrismError):
    """Prism could not create the requested audio or MIDI artifact."""

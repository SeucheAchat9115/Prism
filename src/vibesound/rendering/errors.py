"""Errors raised by the deterministic offline renderer."""


class RenderError(Exception):
    """Base class for offline rendering failures."""


class InvalidRenderRequestError(RenderError):
    """A render range or command sequence is invalid."""


class RenderValidationError(RenderError):
    """A project, archive, or source does not satisfy the render contract."""


class RenderOutputError(RenderError):
    """The renderer could not safely create or replace its output."""

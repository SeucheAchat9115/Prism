"""Typed failures raised by the application service."""

from __future__ import annotations


class ApplicationError(Exception):
    """A stable, HTTP-mappable application-service failure."""

    def __init__(
        self,
        message: str,
        *,
        code: str = "application_error",
        path: str = "",
        status_code: int = 400,
        current_revision: int | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.path = path
        self.status_code = status_code
        self.current_revision = current_revision


class EventStreamOverflowError(Exception):
    """A WebSocket subscriber fell behind its bounded event queue."""

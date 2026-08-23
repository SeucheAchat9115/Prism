"""Deterministic offline rendering for VibeSound projects."""

from vibesound.rendering.errors import (
    InvalidRenderRequestError,
    RenderCancelledError,
    RenderError,
    RenderOutputError,
    RenderValidationError,
)
from vibesound.rendering.offline import render, render_project, render_snapshot
from vibesound.rendering.sources import (
    prepare_archive_playback_project,
    prepare_working_playback_project,
    resample_hq,
    resample_linear,
)
from vibesound.rendering.types import RenderCommand, RenderMetadata, RenderRequest

__all__ = [
    "InvalidRenderRequestError",
    "RenderCommand",
    "RenderCancelledError",
    "RenderError",
    "RenderMetadata",
    "RenderOutputError",
    "RenderRequest",
    "RenderValidationError",
    "render",
    "render_project",
    "render_snapshot",
    "prepare_archive_playback_project",
    "prepare_working_playback_project",
    "resample_hq",
    "resample_linear",
]

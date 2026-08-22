"""Deterministic offline rendering for VibeSound projects."""

from vibesound.rendering.errors import (
    InvalidRenderRequestError,
    RenderError,
    RenderOutputError,
    RenderValidationError,
)
from vibesound.rendering.offline import render, render_project
from vibesound.rendering.sources import prepare_archive_playback_project, resample_linear
from vibesound.rendering.types import RenderCommand, RenderMetadata, RenderRequest

__all__ = [
    "InvalidRenderRequestError",
    "RenderCommand",
    "RenderError",
    "RenderMetadata",
    "RenderOutputError",
    "RenderRequest",
    "RenderValidationError",
    "render",
    "render_project",
    "prepare_archive_playback_project",
    "resample_linear",
]

"""Headless backend adapter preserving the Phase 3 render functions."""

from __future__ import annotations

from pathlib import Path

from vibesound.engine import ClipSourceProvider
from vibesound.project.models import Project
from vibesound.rendering import RenderMetadata, RenderRequest, render, render_project


class OfflineRenderBackend:
    """Expose offline rendering behind a backend-shaped object."""

    def render(
        self,
        project: Project,
        sources: ClipSourceProvider,
        output_path: Path | str,
        request: RenderRequest,
    ) -> RenderMetadata:
        """Render a loaded project without opening an audio device."""

        return render(project, sources, output_path, request)

    def render_project(
        self,
        project_path: Path | str,
        output_path: Path | str,
        request: RenderRequest,
    ) -> RenderMetadata:
        """Render a self-contained project archive without opening a device."""

        return render_project(project_path, output_path, request)

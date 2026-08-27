"""Prism: write a song as Python and render it reproducibly."""

from prism.errors import PrismError, ProjectError, RenderError
from prism.midi import MidiResult
from prism.project import Project, ProjectSummary, Section, Track
from prism.render import RenderResult

__all__ = [
    "MidiResult",
    "PrismError",
    "Project",
    "ProjectError",
    "ProjectSummary",
    "RenderError",
    "RenderResult",
    "Section",
    "Track",
    "__version__",
]

__version__ = "0.2.0.dev0"

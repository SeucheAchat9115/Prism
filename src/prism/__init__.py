"""Prism: write a song as Python and render it reproducibly."""

from prism.errors import PrismError, ProjectError, RenderError
from prism.midi import MidiResult
from prism.plugins import AutomationLane, AutomationPoint, Plugin
from prism.project import Project, ProjectSummary, Section, Track
from prism.render import RenderResult
from prism.version import __version__

__all__ = [
    "AutomationLane",
    "AutomationPoint",
    "MidiResult",
    "Plugin",
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

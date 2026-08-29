"""Prism: write a song as Python and render it reproducibly."""

from prism.errors import PrismError, ProjectError, RenderError
from prism.midi import MidiResult
from prism.music import Note
from prism.plugins import AutomationLane, AutomationPoint, Plugin
from prism.project import Bus, Project, ProjectSummary, Section, Send, Track
from prism.render import RenderResult, StemFile, StemRenderResult
from prism.sample_library import SampleLibrary
from prism.synthesis.types import SynthWave, Uniwave
from prism.version import __version__

__all__ = [
    "AutomationLane",
    "AutomationPoint",
    "Bus",
    "MidiResult",
    "Note",
    "Plugin",
    "PrismError",
    "Project",
    "ProjectError",
    "ProjectSummary",
    "RenderError",
    "RenderResult",
    "SampleLibrary",
    "Section",
    "Send",
    "StemFile",
    "StemRenderResult",
    "SynthWave",
    "Track",
    "Uniwave",
    "__version__",
]

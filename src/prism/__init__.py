"""Prism: write a song as Python and render it reproducibly."""

from prism.arrangement import (  # noqa: F401
    CompiledClipBoundary,
    CompiledControllerEvent,
    CompiledNote,
    CompiledTrackEvents,
    compile_track_events,
)
from prism.errors import PrismError, ProjectError, RenderError
from prism.midi import MidiResult
from prism.music import ControlPoint, Note  # noqa: F401
from prism.plugins import AutomationLane, AutomationPoint, OutputGainLane, Plugin
from prism.project import Bus, Project, ProjectSummary, Section, Send, Track
from prism.render import RenderResult, StemFile, StemRenderResult
from prism.sample_library import SampleLibrary
from prism.synthesis.types import SynthWave, Uniwave
from prism.version import __version__
from prism.vst import VST3, VSTRegistry

__all__ = [
    "AutomationLane",
    "AutomationPoint",
    "Bus",
    "MidiResult",
    "Note",
    "OutputGainLane",
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
    "VST3",
    "VSTRegistry",
    "__version__",
]

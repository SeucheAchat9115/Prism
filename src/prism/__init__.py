"""Prism: write a song as Python and render it reproducibly."""

from prism.arrangement import (  # noqa: F401
    CompiledClipBoundary,
    CompiledControllerEvent,
    CompiledNote,
    CompiledTrackEvents,
    compile_track_events,
)
from prism.build import (
    BuildInspection,
    build,
    build_contract_info,
    build_project,
    doctor_project,
    inspect_project,
    render_project,
    resolve_project_root,
    validate_project,
)
from prism.errors import PrismError, ProjectError, RenderError
from prism.fingerprint import FingerprintedFile, ProjectFingerprint
from prism.midi import MidiResult
from prism.music import ControlPoint, Note  # noqa: F401
from prism.plugins import AutomationLane, AutomationPoint, OutputGainLane, Plugin
from prism.project import Bus, Project, ProjectSummary, Section, Send, Track
from prism.render import (
    ExportDiagnostics,
    ExportProfile,
    RenderResult,
    StemDeliveryContract,
    StemFile,
    StemRenderResult,
)
from prism.sample_library import SampleLibrary
from prism.synthesis.types import SynthWave, Uniwave
from prism.version import __version__
from prism.vst import VST3, VSTBackendConfig, VSTRegistry

__all__ = [
    "AutomationLane",
    "AutomationPoint",
    "BuildInspection",
    "Bus",
    "build",
    "build_contract_info",
    "build_project",
    "doctor_project",
    "ExportDiagnostics",
    "ExportProfile",
    "FingerprintedFile",
    "MidiResult",
    "Note",
    "OutputGainLane",
    "Plugin",
    "inspect_project",
    "PrismError",
    "Project",
    "ProjectError",
    "ProjectSummary",
    "ProjectFingerprint",
    "RenderError",
    "RenderResult",
    "render_project",
    "resolve_project_root",
    "SampleLibrary",
    "Section",
    "Send",
    "StemDeliveryContract",
    "StemFile",
    "StemRenderResult",
    "SynthWave",
    "Track",
    "Uniwave",
    "validate_project",
    "VST3",
    "VSTBackendConfig",
    "VSTRegistry",
    "__version__",
]

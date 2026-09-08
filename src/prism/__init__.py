"""Prism: write a song as Python and render it reproducibly."""

from prism.agent import (  # noqa: F401
    AGENT_CONTRACT,
    AGENT_CONTRACT_VERSION,
    AGENT_SCHEMA_VERSION,
    IDENTITY_SCHEMA_VERSION,
    AgentError,
    AgentLimits,
    AgentOperationRequest,
    agent_capabilities,
    agent_operation,
    build_agent_operation,
    inspect_agent_context,
    project_revision_id,
    select_agent_entities,
)
from prism.arrangement import (  # noqa: F401
    CompiledClipBoundary,
    CompiledControllerEvent,
    CompiledNote,
    CompiledTrackEvents,
    compile_track_events,
)
from prism.build import (  # noqa: F401
    BuildInspection,
    build,
    build_contract_info,
    build_project,
    doctor_project,
    inspect_agent,
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
    "AGENT_CONTRACT",
    "AGENT_CONTRACT_VERSION",
    "AGENT_SCHEMA_VERSION",
    "AutomationLane",
    "AutomationPoint",
    "AgentError",
    "AgentLimits",
    "AgentOperationRequest",
    "BuildInspection",
    "Bus",
    "build_agent_operation",
    "build",
    "build_contract_info",
    "build_project",
    "doctor_project",
    "ExportDiagnostics",
    "ExportProfile",
    "FingerprintedFile",
    "IDENTITY_SCHEMA_VERSION",
    "inspect_agent",
    "inspect_agent_context",
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
    "select_agent_entities",
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
    "agent_capabilities",
    "agent_operation",
    "project_revision_id",
    "__version__",
]

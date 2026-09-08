"""Provider-neutral inspection and selection for human-guided music agents.

The agent contract is deliberately a read-only boundary in this milestone.
It describes the executable Python project that a person has authored; it
does not execute an LLM, contact a service, or mutate the source.  A future
operation can use the same IDs and revision envelope when it proposes a
reversible edit.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, field, is_dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Literal, Mapping, Sequence

from prism.errors import AgentError, PrismError, ProjectError
from prism.music import note_to_midi
from prism.plugins import STOCK_PLUGINS, Parameter, Plugin, parameter_identity
from prism.project.builder import (
    AudioClip,
    ClipPlacement,
    DrumClip,
    MidiClip,
    Project,
    SampleClip,
    Section,
    Track,
)
from prism.sample_library import project_audio_files

if TYPE_CHECKING:
    from prism.arrangement import CompiledControllerEvent, CompiledNote


AGENT_CONTRACT = "prism.agent"
AGENT_CONTRACT_VERSION = 1
AGENT_SCHEMA_VERSION = 1
IDENTITY_SCHEMA_VERSION = 1

AgentOperation = Literal["capabilities", "inspect", "select"]


@dataclass(frozen=True, slots=True)
class AgentLimits:
    """Hard response bounds for one agent inspection."""

    max_tracks: int = 64
    max_sections: int = 64
    max_clip_definitions: int = 256
    max_clip_instances: int = 1_024
    max_notes: int = 4_096
    max_controllers: int = 2_048
    max_plugins: int = 256
    max_parameters: int = 1_024
    max_assets: int = 512

    @classmethod
    def from_mapping(cls, value: Mapping[str, object] | None) -> "AgentLimits":
        if value is None:
            return cls()
        defaults = cls()
        parsed: dict[str, int] = {}
        for field_name in cls.__dataclass_fields__:
            raw = value.get(field_name, getattr(defaults, field_name))
            if isinstance(raw, bool) or not isinstance(raw, int):
                raise AgentError(
                    "invalid_limit",
                    f"Agent limit {field_name!r} must be an integer.",
                    details={"field": field_name},
                )
            if raw < 1 or raw > 100_000:
                raise AgentError(
                    "invalid_limit",
                    f"Agent limit {field_name!r} must be between 1 and 100000.",
                    details={"field": field_name, "value": raw},
                )
            parsed[field_name] = raw
        return cls(**parsed)

    def as_dict(self) -> dict[str, int]:
        return {
            field_name: int(getattr(self, field_name))
            for field_name in self.__dataclass_fields__
        }


@dataclass(frozen=True, slots=True)
class AgentOperationRequest:
    """A versioned, provider-neutral read request."""

    operation: AgentOperation
    schema_version: int = AGENT_SCHEMA_VERSION
    selection: Mapping[str, object] = field(default_factory=dict)
    limits: AgentLimits = field(default_factory=AgentLimits)
    revision_id: str | None = None

    @classmethod
    def from_mapping(
        cls, value: Mapping[str, object] | "AgentOperationRequest"
    ) -> "AgentOperationRequest":
        if isinstance(value, cls):
            if value.schema_version != AGENT_SCHEMA_VERSION:
                raise AgentError(
                    "unsupported_schema_version",
                    f"Agent request schema {value.schema_version} is not supported.",
                    details={
                        "requested": value.schema_version,
                        "supported": [AGENT_SCHEMA_VERSION],
                        "contract": AGENT_CONTRACT,
                    },
                )
            if value.operation not in {"capabilities", "inspect", "select"}:
                raise AgentError(
                    "unsupported_operation",
                    f"Agent operation {value.operation!r} is not supported.",
                )
            return value
        if not isinstance(value, Mapping):
            raise AgentError("invalid_request", "Agent request must be an object.")
        source = value
        raw_schema = source.get("schema_version", AGENT_SCHEMA_VERSION)
        if isinstance(raw_schema, bool) or not isinstance(raw_schema, int):
            raise AgentError(
                "invalid_schema_version",
                "Agent request schema_version must be an integer.",
            )
        if raw_schema != AGENT_SCHEMA_VERSION:
            raise AgentError(
                "unsupported_schema_version",
                f"Agent request schema {raw_schema} is not supported.",
                details={
                    "requested": raw_schema,
                    "supported": [AGENT_SCHEMA_VERSION],
                    "contract": AGENT_CONTRACT,
                },
            )
        operation_value = source.get("operation")
        if not isinstance(operation_value, str):
            raise AgentError(
                "invalid_operation",
                "Agent request operation must be a string.",
            )
        operation = operation_value.strip().casefold()
        if operation not in {"capabilities", "inspect", "select"}:
            raise AgentError(
                "unsupported_operation",
                f"Agent operation {operation_value!r} is not supported.",
                details={"supported": ["capabilities", "inspect", "select"]},
            )
        raw_selection = source.get("selection", source.get("selector", {}))
        if raw_selection is None:
            raw_selection = {}
        if not isinstance(raw_selection, Mapping):
            raise AgentError(
                "invalid_selection",
                "Agent request selection must be an object.",
            )
        raw_limits = source.get("limits")
        if raw_limits is not None and not isinstance(raw_limits, Mapping):
            raise AgentError("invalid_limit", "Agent request limits must be an object.")
        raw_revision = source.get("revision_id", source.get("expected_revision_id"))
        if raw_revision is not None and not isinstance(raw_revision, str):
            raise AgentError(
                "invalid_revision_id",
                "Agent request revision_id must be a string when supplied.",
            )
        return cls(
            operation=operation,  # type: ignore[arg-type]
            schema_version=raw_schema,
            selection=dict(raw_selection),
            limits=AgentLimits.from_mapping(raw_limits),
            revision_id=raw_revision,
        )


def project_revision_id(project: Project) -> str:
    """Return a deterministic revision ID without requiring VST binaries."""

    payload = {
        "identity_schema_version": IDENTITY_SCHEMA_VERSION,
        "project": _project_payload(project),
    }
    encoded = json.dumps(
        _json_safe(payload), sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def agent_capabilities(
    project: Project | None = None,
    *,
    limits: AgentLimits | Mapping[str, object] | None = None,
) -> dict[str, object]:
    """Describe the supported contract and bounded read operations."""

    resolved_limits = _limits(limits)
    project_id = None if project is None else _project_id(project)
    revision_id = None if project is None else project_revision_id(project)
    return {
        "contract": AGENT_CONTRACT,
        "contract_version": AGENT_CONTRACT_VERSION,
        "schema_version": AGENT_SCHEMA_VERSION,
        "identity_schema_version": IDENTITY_SCHEMA_VERSION,
        "project_id": project_id,
        "revision_id": revision_id,
        "selected_ranges": [],
        "operations": {
            "capabilities": {"read_only": True},
            "inspect": {
                "read_only": True,
                "returns": [
                    "arrangement",
                    "musical_context",
                    "routing",
                    "plugins",
                    "assets",
                    "render_capabilities",
                ],
            },
            "select": {
                "read_only": True,
                "filters": [
                    "id",
                    "name",
                    "musical_role",
                    "section_id",
                    "quarter_note_range",
                ],
            },
        },
        "entity_types": [
            "project",
            "track",
            "section",
            "bus",
            "clip_definition",
            "clip_instance",
            "plugin",
            "note",
            "controller",
        ],
        "limits": resolved_limits.as_dict(),
        "execution": {
            "requires_llm": False,
            "requires_network": False,
            "requires_audio_device": False,
            "builds_python": True,
            "mutates_source": False,
        },
    }


def inspect_agent_context(
    project: Project,
    *,
    limits: AgentLimits | Mapping[str, object] | None = None,
) -> dict[str, object]:
    """Return bounded arrangement, musical, plugin, and asset context."""

    resolved_limits = _limits(limits)
    revision_id = project_revision_id(project)
    sections = _section_entries(project, resolved_limits.max_sections)
    tracks = _track_entries(project, resolved_limits.max_tracks)
    clip_definitions = _clip_definition_entries(
        project, tracks, resolved_limits.max_clip_definitions
    )
    all_notes: list[dict[str, object]] = []
    all_controllers: list[dict[str, object]] = []
    clip_instances: list[dict[str, object]] = []
    track_notes: dict[str, list[dict[str, object]]] = {str(item["id"]): [] for item in tracks}
    track_controllers: dict[str, list[dict[str, object]]] = {
        str(item["id"]): [] for item in tracks
    }

    total_bars = sum(section.bars for section in project.sections)
    for track in project.tracks[: resolved_limits.max_tracks]:
        track_id = _track_id(project, track, project.tracks.index(track))
        compiled = _try_compile(project, track, total_bars)
        if compiled is not None:
            for note in compiled.notes:  # type: ignore[attr-defined]
                item = _compiled_note_entry(note)
                all_notes.append(item)
                track_notes.setdefault(track_id, []).append(item)
            for point in compiled.controllers:  # type: ignore[attr-defined]
                item = _compiled_controller_entry(point)
                all_controllers.append(item)
                track_controllers.setdefault(track_id, []).append(item)
            clip_instances.extend(
                _compiled_boundary_entry(boundary)
                for boundary in compiled.boundaries  # type: ignore[attr-defined]
            )
        else:
            clip_instances.extend(_fallback_instances(project, track))

    clip_instances, instances_truncated = _take(
        clip_instances, resolved_limits.max_clip_instances
    )
    all_notes, notes_truncated = _take(all_notes, resolved_limits.max_notes)
    all_controllers, controllers_truncated = _take(
        all_controllers, resolved_limits.max_controllers
    )
    plugin_entries, plugin_truncated, parameters_truncated = _plugin_entries(
        project, resolved_limits
    )
    assets, assets_truncated = _asset_entries(project, resolved_limits.max_assets)
    available_vst3, vst_catalog_truncated = _registry_catalog(
        project, resolved_limits.max_plugins
    )

    for track_entry in tracks:
        track_id = str(track_entry["id"])
        notes = track_notes.get(track_id, [])
        controllers = track_controllers.get(track_id, [])
        track_entry["register"] = _register_summary(notes)
        track_entry["rhythm"] = _rhythm_summary(notes, controllers)
        track_entry["note_count"] = len(notes)
        track_entry["controller_count"] = len(controllers)

    authored_context = {
        "key": _authored_value(project.key),
        "scale": _authored_value(project.scale),
        "chords": [
            {"value": chord, "source": "authored"} for chord in project.chords
        ],
    }
    inferred_harmony = _infer_harmony(all_notes)
    total_beats = project.timing.bars_to_quarter_notes(total_bars)
    selected_ranges = [{"start_beat": 0.0, "end_beat": total_beats}]
    truncated = [
        name
        for name, value in (
            ("sections", len(project.sections) > len(sections)),
            ("tracks", len(project.tracks) > len(tracks)),
            ("clip_definitions", _count_clip_definitions(project) > len(clip_definitions)),
            ("clip_instances", instances_truncated),
            ("notes", notes_truncated),
            ("controllers", controllers_truncated),
            ("plugins", plugin_truncated),
            ("parameters", parameters_truncated),
            ("available_vst3", vst_catalog_truncated),
            ("assets", assets_truncated),
        )
        if value
    ]
    return {
        "contract": AGENT_CONTRACT,
        "contract_version": AGENT_CONTRACT_VERSION,
        "schema_version": AGENT_SCHEMA_VERSION,
        "identity_schema_version": IDENTITY_SCHEMA_VERSION,
        "project_id": _project_id(project),
        "revision_id": revision_id,
        "selected_ranges": selected_ranges,
        "bounds": {
            "limits": resolved_limits.as_dict(),
            "truncated": truncated,
        },
        "project": {
            "id": _project_id(project),
            "name": project.name,
            "display_name": project.name,
            "revision_id": revision_id,
            "tempo_bpm": project.tempo,
            "sample_rate": project.sample_rate,
            "time_signature": [project.beats_per_bar, project.beat_unit],
            "quarter_notes_per_bar": project.quarter_notes_per_bar,
            "script": project.script.name,
        },
        "musical_context": {
            "authored": authored_context,
            "inferred": {"harmony": inferred_harmony},
            "provenance_note": (
                "Only authored.key, authored.scale, and authored.chords describe "
                "declared intent. Inferred values are estimates with uncertainty."
            ),
        },
        "arrangement": {
            "sections": sections,
            "tracks": tracks,
            "clip_definitions": clip_definitions,
            "clip_instances": clip_instances,
            "notes": all_notes,
            "controllers": all_controllers,
            "controller_boundary": project.controller_boundary,
        },
        "routing": _routing_entries(project),
        "plugins": {
            "instances": plugin_entries,
            "available_instruments": _stock_catalog("instrument"),
            "available_effects": _stock_catalog("effect"),
            "available_vst3": available_vst3,
        },
        "assets": assets,
        "render_capabilities": _render_capabilities(project, plugin_entries),
    }


def select_agent_entities(
    project: Project,
    selection: Mapping[str, object],
    *,
    limits: AgentLimits | Mapping[str, object] | None = None,
) -> dict[str, object]:
    """Resolve a selection against one revision and return bounded entities."""

    context = inspect_agent_context(project, limits=limits)
    selected = _select_from_context(context, selection)
    selected["project_id"] = _project_id(project)
    selected["revision_id"] = str(context["revision_id"])
    selected["contract"] = AGENT_CONTRACT
    selected["contract_version"] = AGENT_CONTRACT_VERSION
    selected["schema_version"] = AGENT_SCHEMA_VERSION
    return selected


def agent_operation(
    project: Project,
    request: Mapping[str, object] | AgentOperationRequest,
) -> dict[str, object]:
    """Execute one read-only request and always return a result envelope."""

    operation_hint = request.operation if isinstance(request, AgentOperationRequest) else (
        request.get("operation") if isinstance(request, Mapping) else None
    )
    operation = operation_hint if isinstance(operation_hint, str) else "unknown"
    try:
        parsed = AgentOperationRequest.from_mapping(request)
        revision_id = project_revision_id(project)
        if parsed.revision_id is not None and parsed.revision_id != revision_id:
            raise AgentError(
                "stale_revision",
                "The project revision changed; inspect again before selecting or editing.",
                details={
                    "expected_revision_id": parsed.revision_id,
                    "current_revision_id": revision_id,
                },
            )
        if parsed.operation == "capabilities":
            result = agent_capabilities(project, limits=parsed.limits)
            ranges: list[dict[str, object]] = []
        elif parsed.operation == "inspect":
            result = inspect_agent_context(project, limits=parsed.limits)
            ranges = _range_list(result.get("selected_ranges"))
        else:
            result = select_agent_entities(
                project, parsed.selection, limits=parsed.limits
            )
            ranges = _range_list(result.get("selected_ranges"))
        return _result_envelope(
            operation=parsed.operation,
            project_id=_project_id(project),
            revision_id=revision_id,
            selected_ranges=ranges,
            result=result,
        )
    except AgentError as error:
        return _result_envelope(
            operation=operation,
            project_id=_project_id(project),
            revision_id=_safe_revision(project),
            selected_ranges=[],
            error=error,
        )
    except (OSError, ProjectError, PrismError) as error:
        wrapped = AgentError(
            "project_error",
            str(error),
            details={"type": type(error).__name__},
        )
        return _result_envelope(
            operation=operation,
            project_id=_project_id(project),
            revision_id=_safe_revision(project),
            selected_ranges=[],
            error=wrapped,
        )


def build_agent_operation(
    project: str | Path = ".",
    request: Mapping[str, object] | AgentOperationRequest | None = None,
) -> dict[str, object]:
    """Build a Python project and execute an agent request without VST hosting."""

    from prism.build import build_project

    resolved_request: Mapping[str, object] | AgentOperationRequest = (
        {"operation": "inspect"} if request is None else request
    )
    try:
        built = build_project(project, validate=False, verify_vst=False)
    except (OSError, PrismError) as error:
        code = "build_contract_required" if "build()" in str(error) else "build_error"
        return _result_envelope(
            operation=_request_operation(resolved_request),
            project_id=None,
            revision_id=None,
            selected_ranges=[],
            error=AgentError(code, str(error), details={"type": type(error).__name__}),
        )
    return agent_operation(built, resolved_request)


def _result_envelope(
    *,
    operation: str,
    project_id: str | None,
    revision_id: str | None,
    selected_ranges: Sequence[Mapping[str, object]],
    result: Mapping[str, object] | None = None,
    error: AgentError | None = None,
) -> dict[str, object]:
    return {
        "contract": AGENT_CONTRACT,
        "contract_version": AGENT_CONTRACT_VERSION,
        "schema_version": AGENT_SCHEMA_VERSION,
        "operation": operation,
        "status": "error" if error is not None else "ok",
        "project_id": project_id,
        "revision_id": revision_id,
        "selected_ranges": [dict(item) for item in selected_ranges],
        "result": None if result is None else _json_safe(result),
        "error": None if error is None else error.as_dict(),
    }


def _limits(value: AgentLimits | Mapping[str, object] | None) -> AgentLimits:
    if isinstance(value, AgentLimits):
        return value
    return AgentLimits.from_mapping(value)


def _project_id(project: Project) -> str:
    return str(getattr(project, "project_id", "project:main"))


def _track_id(project: Project, track: Track, index: int) -> str:
    return str(getattr(track, "track_id", f"{_project_id(project)}/track:{index + 1:04d}"))


def _section_id(project: Project, section: Section, index: int) -> str:
    return str(
        getattr(section, "section_id", "")
        or f"{_project_id(project)}/section:{index + 1:04d}"
    )


def _clip_definition_id(
    project: Project,
    track: Track,
    placement: ClipPlacement,
    index: int,
) -> str:
    return str(
        getattr(placement, "clip_definition_id", "")
        or f"{_track_id(project, track, project.tracks.index(track))}/clip:{index + 1:04d}"
    )


def _plugin_id(plugin: Plugin, fallback: str) -> str:
    return str(plugin.instance_id or fallback)


def _authored_value(value: str | None) -> dict[str, object] | None:
    return None if value is None else {"value": value, "source": "authored"}


def _section_entries(project: Project, limit: int) -> list[dict[str, object]]:
    cursor_bar = 0.0
    result: list[dict[str, object]] = []
    for index, section in enumerate(project.sections[:limit]):
        start_beat = project.timing.bars_to_quarter_notes(cursor_bar)
        end_bar = cursor_bar + section.bars
        end_beat = project.timing.bars_to_quarter_notes(end_bar)
        result.append(
            {
                "id": _section_id(project, section, index),
                "section_id": _section_id(project, section, index),
                "name": section.name,
                "display_name": section.name,
                "bars": section.bars,
                "start_bar": cursor_bar,
                "end_bar": end_bar,
                "start_beat": start_beat,
                "end_beat": end_beat,
                "track_ids": list(section.track_ids or ()),
                "track_names": list(section.tracks or ()),
            }
        )
        cursor_bar = end_bar
    return result


def _track_entries(project: Project, limit: int) -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    total_beats = project.timing.bars_to_quarter_notes(
        sum(section.bars for section in project.sections)
    )
    section_ids = {
        section.name: _section_id(project, section, index)
        for index, section in enumerate(project.sections)
    }
    for index, track in enumerate(project.tracks[:limit]):
        track_id = _track_id(project, track, index)
        role = _track_role(track)
        clip_ids = [
            _clip_definition_id(project, track, placement, clip_index)
            for clip_index, placement in enumerate(track.clips)
        ]
        active_sections = [
            section_ids[section.name]
            for section in project.sections
            if _active_section(section, track)
        ]
        result.append(
            {
                "id": track_id,
                "track_id": track_id,
                "name": track.name,
                "display_name": track.name,
                "role": role,
                "gain_db": track.gain_db,
                "pan": track.pan,
                "muted": track.muted,
                "start_beat": 0.0,
                "end_beat": total_beats,
                "instrument_plugin_id": (
                    None
                    if track.instrument_plugin is None
                    else _plugin_id(track.instrument_plugin, f"{track_id}/plugin:instrument")
                ),
                "output_bus_id": None if track.output_bus is None else track.output_bus.bus_id,
                "send_bus_ids": [send.bus_id for send in track.sends],
                "clip_definition_ids": clip_ids,
                "section_ids": active_sections,
            }
        )
    return result


def _clip_definition_entries(
    project: Project,
    tracks: Sequence[Mapping[str, object]],
    limit: int,
) -> list[dict[str, object]]:
    track_by_name = {str(entry["id"]): entry for entry in tracks}
    result: list[dict[str, object]] = []
    section_lookup = {
        section.name: (_section_id(project, section, index), index)
        for index, section in enumerate(project.sections)
    }
    for track_index, track in enumerate(project.tracks):
        track_id = _track_id(project, track, track_index)
        if track_id not in track_by_name:
            continue
        for clip_index, placement in enumerate(track.clips):
            if len(result) >= limit:
                return result
            definition_id = _clip_definition_id(project, track, placement, clip_index)
            section_id = None
            if placement.section is not None:
                section_id = section_lookup.get(placement.section, (None, 0))[0]
            result.append(
                {
                    "id": definition_id,
                    "clip_definition_id": definition_id,
                    "name": f"{_clip_kind(placement.clip).title()} clip {clip_index + 1}",
                    "display_name": f"{_clip_kind(placement.clip).title()} clip {clip_index + 1}",
                    "track_id": track_id,
                    "track_name": track.name,
                    "kind": _clip_kind(placement.clip),
                    "section_id": section_id,
                    "section": placement.section,
                    "start_bar": placement.start_bar,
                    "repeat": placement.repeat,
                    "bars": placement.clip.bars,
                    "events": _authored_clip_events(placement.clip, definition_id),
                }
            )
    return result


def _authored_clip_events(clip: object, definition_id: str) -> dict[str, object]:
    if isinstance(clip, MidiClip):
        notes = [
            {
                "id": f"{definition_id}/note:{index + 1:04d}",
                "pitch": note.pitch,
                "midi_note": note_to_midi(note.pitch),
                "start_beat": note.start,
                "duration_beats": note.duration,
                "velocity": note.velocity,
                "source": "authored",
            }
            for index, note in enumerate(clip.events)
        ]
        return {
            "notes": notes,
            "controllers": {
                "pitch_bend": [_json_safe(point) for point in clip.pitch_bend],
                "modulation": [_json_safe(point) for point in clip.modulation],
            },
        }
    if isinstance(clip, DrumClip):
        return {
            "hits": [
                {"step": index, "token": token, "source": "authored"}
                for index, token in enumerate(clip.pattern)
                if token != "-"
            ]
        }
    if isinstance(clip, SampleClip):
        return {"sample_path": clip.path, "pattern": list(clip.pattern)}
    if isinstance(clip, AudioClip):
        return {"audio_path": clip.path, "loop": clip.loop}
    return {}


def _try_compile(project: Project, track: Track, total_bars: int) -> object | None:
    if not isinstance(track.clip, DrumClip | MidiClip):
        return None
    try:
        from prism.arrangement import compile_track_events

        return compile_track_events(
            project,
            track,
            total_bars=total_bars,
            total_frames=project.timing.bar_to_frame(total_bars),
        )
    except (OSError, ProjectError, ValueError):
        return None


def _compiled_note_entry(note: CompiledNote) -> dict[str, object]:
    return {
        "id": note.note_id,
        "note_id": note.note_id,
        "pitch": note.pitch,
        "midi_note": note.midi_note,
        "velocity": note.velocity,
        "start_beat": note.on_beat,
        "end_beat": note.off_beat,
        "start_frame": note.on_frame,
        "end_frame": note.off_frame,
        "clip_instance_id": note.clip_instance_id or note.clip_id,
        "clip_definition_id": note.clip_definition_id,
        "section_id": note.section_id,
        "source": "compiled",
    }


def _compiled_controller_entry(point: CompiledControllerEvent) -> dict[str, object]:
    return {
        "id": (
            f"{point.clip_instance_id or point.clip_id}/controller:"
            f"{point.controller}:{point.sequence}"
        ),
        "controller": point.controller,
        "beat": point.beat,
        "frame": point.frame,
        "value": point.value,
        "curve": point.curve,
        "clip_instance_id": point.clip_instance_id or point.clip_id,
        "clip_definition_id": point.clip_definition_id,
        "section_id": point.section_id,
        "synthetic_reset": point.synthetic_reset,
        "source": "compiled" if not point.synthetic_reset else "generated_boundary_policy",
    }


def _compiled_boundary_entry(boundary: object) -> dict[str, object]:
    return {
        "id": boundary.clip_instance_id or boundary.clip_id,  # type: ignore[attr-defined]
        "clip_instance_id": boundary.clip_instance_id or boundary.clip_id,  # type: ignore[attr-defined]
        "clip_definition_id": boundary.clip_definition_id,  # type: ignore[attr-defined]
        "track_id": boundary.track_id,  # type: ignore[attr-defined]
        "section_id": boundary.section_id,  # type: ignore[attr-defined]
        "section": boundary.section,  # type: ignore[attr-defined]
        "placement_index": boundary.placement_index,  # type: ignore[attr-defined]
        "repeat_index": boundary.repeat_index,  # type: ignore[attr-defined]
        "start_beat": boundary.start_beat,  # type: ignore[attr-defined]
        "end_beat": boundary.end_beat,  # type: ignore[attr-defined]
        "start_frame": boundary.start_frame,  # type: ignore[attr-defined]
        "end_frame": boundary.end_frame,  # type: ignore[attr-defined]
        "repeat": boundary.repeat,  # type: ignore[attr-defined]
        "gain_db": boundary.gain_db,  # type: ignore[attr-defined]
        "source": "compiled",
    }


def _fallback_instances(project: Project, track: Track) -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    section_cursor = 0.0
    for section_index, section in enumerate(project.sections):
        section_start = project.timing.bars_to_quarter_notes(section_cursor)
        section_end = project.timing.bars_to_quarter_notes(section_cursor + section.bars)
        if _active_section(section, track):
            placements = _selected_placements(track, section.name)
            for placement_index, placement in placements:
                definition_id = _clip_definition_id(
                    project, track, placement, placement_index
                )
                clip_beats = project.timing.bars_to_quarter_notes(placement.clip.bars)
                start = section_start + project.timing.bars_to_quarter_notes(placement.start_bar)
                available = section_end - start
                repeats = max(1, math.ceil(available / clip_beats)) if placement.repeat else 1
                for repeat_index in range(repeats):
                    instance_start = start + repeat_index * clip_beats
                    if instance_start >= section_end:
                        continue
                    instance_end = min(section_end, instance_start + clip_beats)
                    instance_id = (
                        f"{definition_id}/instance:{_section_id(project, section, section_index)}:"
                        f"{repeat_index + 1:04d}"
                    )
                    result.append(
                        {
                            "id": instance_id,
                            "clip_instance_id": instance_id,
                            "clip_definition_id": definition_id,
                            "track_id": _track_id(project, track, project.tracks.index(track)),
                            "section_id": _section_id(project, section, section_index),
                            "section": section.name,
                            "placement_index": placement_index,
                            "repeat_index": repeat_index,
                            "start_beat": instance_start,
                            "end_beat": instance_end,
                            "start_frame": project.timing.quarter_notes_to_frame(instance_start),
                            "end_frame": project.timing.quarter_notes_to_frame(instance_end),
                            "repeat": placement.repeat,
                            "gain_db": placement.clip.gain_db,
                            "source": "arrangement",
                        }
                    )
        section_cursor += section.bars
    return result


def _selected_placements(
    track: Track, section_name: str
) -> tuple[tuple[int, ClipPlacement], ...]:
    placements = tuple(enumerate(track.clips))
    scoped = tuple((index, item) for index, item in placements if item.section == section_name)
    if scoped:
        return scoped
    return tuple((index, item) for index, item in placements if item.section is None)


def _active_section(section: Section, track: Track) -> bool:
    if section.tracks is None:
        return True
    if section.track_ids is not None:
        return track.track_id in section.track_ids
    return track.name in section.tracks


def _plugin_entries(
    project: Project, limits: AgentLimits
) -> tuple[list[dict[str, object]], bool, bool]:
    result: list[dict[str, object]] = []
    parameter_count = 0
    parameters_truncated = False

    def add(plugin: Plugin, owner_type: str, owner_id: str, owner_name: str) -> None:
        nonlocal parameter_count, parameters_truncated
        if len(result) >= limits.max_plugins:
            return
        available = True
        availability_error: str | None = None
        if plugin.vst3 is not None:
            try:
                project.vsts.resolve(plugin.vst3.alias, verify=False)
            except ProjectError as error:
                available = False
                availability_error = str(error)
        fallback = f"{owner_id}/plugin:{plugin.kind}:{len(result) + 1:04d}"
        plugin_id = _plugin_id(plugin, fallback)
        entries: list[dict[str, object]] = []
        for name, parameter, value in _plugin_parameter_items(plugin):
            if parameter_count >= limits.max_parameters:
                parameters_truncated = True
                break
            entries.append(_parameter_entry(plugin, name, parameter, value))
            parameter_count += 1
        entry: dict[str, object] = {
            "id": plugin_id,
            "plugin_id": plugin_id,
            "name": plugin.name,
            "display_name": plugin.name,
            "owner_type": owner_type,
            "owner_id": owner_id,
            "owner_name": owner_name,
            "kind": plugin.kind,
            "format": "vst3" if plugin.vst3 is not None else "stock",
            "preset": plugin.preset,
            "settings": _json_safe(plugin.settings),
            "available": available,
            "parameters": entries,
            "parameter_count": len(entries),
        }
        if availability_error is not None:
            entry["availability_error"] = availability_error
        result.append(entry)

    for track_index, track in enumerate(project.tracks):
        owner_id = _track_id(project, track, track_index)
        if track.instrument_plugin is not None:
            add(track.instrument_plugin, "track", owner_id, track.name)
        for effect in track.effects:
            add(effect, "track", owner_id, track.name)
    for bus in project.buses:
        for effect in bus.effects:
            add(effect, "bus", bus.bus_id, bus.name)
    for effect in project.master_effects:
        add(effect, "master", f"{_project_id(project)}/master", "Master")
    total_plugins = sum(
        (1 if track.instrument_plugin is not None else 0) + len(track.effects)
        for track in project.tracks
    )
    total_plugins += sum(len(bus.effects) for bus in project.buses)
    total_plugins += len(project.master_effects)
    return result, total_plugins > limits.max_plugins, parameters_truncated


def _plugin_parameter_items(
    plugin: Plugin,
) -> list[tuple[str, Parameter, object]]:
    result = [
        (name, parameter, plugin.settings.get(name))
        for name, parameter in plugin.automatable.items()
    ]
    if plugin.vst3 is None:
        return result
    seen = {name.casefold() for name, _parameter, _value in result}
    for description in plugin.vst3.parameter_metadata:
        index = getattr(description, "index", None)
        name = getattr(description, "name", None)
        if not isinstance(index, int) or not isinstance(name, str):
            continue
        selector = f"#{index}: {name}"
        if selector.casefold() in seen:
            continue
        value = plugin.settings.get(selector, plugin.settings.get(name, 0.0))
        numeric_value = float(value) if isinstance(value, int | float) else 0.0
        result.append((selector, Parameter(numeric_value, 0.0, 1.0), value))
        seen.add(selector.casefold())
    return result


def _parameter_entry(
    plugin: Plugin,
    name: str,
    parameter: Parameter,
    value: object,
) -> dict[str, object]:
    try:
        identity = parameter_identity(plugin, name)
        parameter_id = identity.parameter_id
        selector = identity.selector
        display_name = identity.display_name
    except ProjectError as error:
        parameter_id = f"unresolved:{name.casefold()}"
        selector = name
        display_name = name
        return {
            "id": f"{plugin.stable_instance_id}/{parameter_id}",
            "parameter_id": parameter_id,
            "selector": selector,
            "display_name": display_name,
            "value": _json_safe(value),
            "minimum": parameter.minimum,
            "maximum": parameter.maximum,
            "source": "authored",
            "resolution_error": str(error),
        }
    return {
        "id": f"{plugin.stable_instance_id}/{parameter_id}",
        "parameter_id": parameter_id,
        "selector": selector,
        "display_name": display_name,
        "value": _json_safe(value),
        "minimum": parameter.minimum,
        "maximum": parameter.maximum,
        "source": "authored",
    }


def _stock_catalog(kind: Literal["instrument", "effect"]) -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    for preset in sorted(STOCK_PLUGINS.presets(kind)):
        definition = STOCK_PLUGINS.get(kind, preset)
        result.append(
            {
                "id": f"stock:{kind}:{preset}",
                "preset": preset,
                "kind": kind,
                "parameters": [
                    {
                        "id": f"stock:{kind}:{preset}:{name}",
                        "name": name,
                        "default": parameter.default,
                        "minimum": parameter.minimum,
                        "maximum": parameter.maximum,
                    }
                    for name, parameter in definition.parameters.items()
                ],
                "melodic": definition.melodic,
                "drum_note": definition.drum_note,
            }
        )
    return result


def _registry_catalog(
    project: Project, limit: int
) -> tuple[list[dict[str, object]], bool]:
    """List registered external instruments/effects without loading a host."""

    try:
        entries = project.vsts.all_entries()
    except ProjectError:
        return [], False
    result = [
        {
            "id": f"vst3:{entry.alias}:{entry.platform}",
            "alias": entry.alias,
            "platform": entry.platform,
            "sha256": entry.sha256,
            "available": (
                (project.root / entry.path).is_file()
                or (project.root / entry.path).is_dir()
                if not Path(entry.path).is_absolute()
                else Path(entry.path).is_file() or Path(entry.path).is_dir()
            ),
            "source": "project_vst_registry",
        }
        for entry in entries
    ]
    return result[:limit], len(result) > limit


def _routing_entries(project: Project) -> dict[str, object]:
    return {
        "tracks": [
            {
                "track_id": track.track_id,
                "output_bus_id": None if track.output_bus is None else track.output_bus.bus_id,
                "sends": [
                    {
                        "track_id": send.track_id or track.track_id,
                        "bus_id": send.bus_id,
                        "gain_db": send.gain_db,
                    }
                    for send in track.sends
                ],
            }
            for track in project.tracks
        ],
        "buses": [
            {
                "id": bus.bus_id,
                "bus_id": bus.bus_id,
                "name": bus.name,
                "display_name": bus.name,
                "track_ids": [track.track_id for track in bus.tracks],
                "gain_db": bus.gain_db,
                "pan": bus.pan,
                "muted": bus.muted,
            }
            for bus in project.buses
        ],
        "master": {"id": f"{_project_id(project)}/master", "name": "Master"},
    }


def _asset_entries(project: Project, limit: int) -> tuple[list[dict[str, object]], bool]:
    paths: set[str] = set()
    try:
        paths.update(
            path.relative_to(project.root).as_posix()
            for path in project_audio_files(project.root)
        )
    except OSError:
        pass
    for track in project.tracks:
        for placement in track.clips:
            clip = placement.clip
            if isinstance(clip, SampleClip | AudioClip):
                paths.add(clip.path)
    for plugin in project._external_plugins():
        if plugin.vst3 is not None:
            paths.update(
                relative
                for relative in (plugin.vst3.state, plugin.vst3.preset)
                if relative is not None
            )
    result: list[dict[str, object]] = []
    for relative in sorted(paths, key=str.casefold)[:limit]:
        path = project.root / relative
        exists = path.is_file() or path.is_dir()
        result.append(
            {
                "id": f"asset:{relative}",
                "path": relative,
                "kind": (
                    "audio"
                    if path.suffix.casefold()
                    in {".wav", ".aif", ".aiff", ".flac", ".ogg", ".wave"}
                    else "plugin_state_or_preset"
                ),
                "exists": exists,
                "size": path.stat().st_size if path.is_file() else None,
                "source": "filesystem",
            }
        )
    return result, len(paths) > len(result)


def _render_capabilities(
    project: Project,
    plugins: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    external = [entry for entry in plugins if entry.get("format") == "vst3"]
    unavailable_external = [entry for entry in external if entry.get("available") is False]
    return {
        "offline": True,
        "requires_network": False,
        "requires_audio_device": False,
        "can_render_native": not external,
        "can_render_midi": any(
            isinstance(track.clip, DrumClip | MidiClip) for track in project.tracks
        ),
        "can_render_audio": bool(project.tracks),
        "can_render_stems": bool(project.tracks),
        "formats": {
            "audio": ["wav"],
            "midi": ["mid"],
            "channels": ["mono", "stereo"],
            "bit_depth": [16, 24, 32],
            "profiles": ["master", "stem", "listening"],
        },
        "external_plugins": len(external),
        "missing_optional_plugins": len(unavailable_external),
        "external_host": "optional VST3 host" if external else None,
        "metadata_only_diagnostics": True,
    }


def _register_summary(notes: Sequence[Mapping[str, object]]) -> dict[str, object]:
    midi_values = [value for note in notes if isinstance((value := note.get("midi_note")), int)]
    if not midi_values:
        return {
            "lowest_midi": None,
            "highest_midi": None,
            "center_midi": None,
            "note_count": 0,
            "source": "inferred",
            "provenance": {"method": "compiled note events", "notes_considered": 0},
        }
    return {
        "lowest_midi": min(midi_values),
        "highest_midi": max(midi_values),
        "center_midi": round(sum(midi_values) / len(midi_values), 3),
        "note_count": len(midi_values),
        "source": "inferred",
        "provenance": {"method": "compiled note events", "notes_considered": len(midi_values)},
    }


def _rhythm_summary(
    notes: Sequence[Mapping[str, object]], controllers: Sequence[Mapping[str, object]]
) -> dict[str, object]:
    starts: list[float] = []
    durations: list[float] = []
    for note in notes:
        start = note.get("start_beat")
        end = note.get("end_beat")
        if isinstance(start, int | float):
            starts.append(float(start))
        if isinstance(start, int | float) and isinstance(end, int | float):
            durations.append(float(end) - float(start))
    unique_grids: list[float] = []
    for start in sorted(starts):
        if start <= 1e-9:
            continue
        for divisor in (1.0, 2.0, 4.0, 8.0, 16.0):
            grid = 1.0 / divisor
            if abs(start / grid - round(start / grid)) < 1e-6:
                unique_grids.append(grid)
                break
    return {
        "note_count": len(notes),
        "controller_count": len(controllers),
        "onset_count": len(starts),
        "onset_density_per_quarter": round(
            len(starts) / max(1.0, max(starts) - min(starts) + 1.0)
            if starts
            else 0.0,
            6,
        ),
        "mean_duration_quarter": round(sum(durations) / len(durations), 6) if durations else None,
        "smallest_observed_grid_quarter": min(unique_grids) if unique_grids else None,
        "source": "inferred",
        "provenance": {
            "method": "compiled event positions",
            "events_considered": len(notes) + len(controllers),
        },
    }


def _infer_harmony(notes: Sequence[Mapping[str, object]]) -> dict[str, object]:
    pitch_classes: list[int] = []
    for note in notes:
        midi_note = note.get("midi_note")
        if isinstance(midi_note, int):
            pitch_classes.append(midi_note % 12)
    counts = [pitch_classes.count(index) for index in range(12)]
    if not pitch_classes:
        return {
            "candidate": None,
            "uncertainty": 1.0,
            "source": "inferred",
            "provenance": {"method": "pitch-class histogram", "notes_considered": 0},
        }
    candidates: list[tuple[float, int, str]] = []
    names = ("C", "C#", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B")
    for root in range(12):
        for mode, intervals in (("major", (0, 4, 7)), ("minor", (0, 3, 7))):
            score = sum(counts[(root + interval) % 12] for interval in intervals)
            candidates.append((float(score), root, mode))
    candidates.sort(key=lambda item: (-item[0], item[1], item[2]))
    best, root, mode = candidates[0]
    second = candidates[1][0] if len(candidates) > 1 else 0.0
    confidence = (best - second) / best if best else 0.0
    return {
        "candidate": f"{names[root]} {mode}",
        "uncertainty": round(1.0 - max(0.0, min(1.0, confidence)), 6),
        "source": "inferred",
        "provenance": {
            "method": "pitch-class histogram",
            "notes_considered": len(pitch_classes),
            "pitch_class_counts": counts,
            "confidence_is_not_authored_intent": True,
        },
    }


def _track_role(track: Track) -> dict[str, object]:
    if track.role is not None:
        return {"value": track.role, "source": "authored"}
    haystack = f"{track.name} {_clip_kind(track.clip) if track.clip is not None else ''}"
    lowered = haystack.casefold()
    roles = (
        ("bass", ("bass", "sub")),
        ("drums", ("drum", "kick", "snare", "hat", "perc")),
        ("pad", ("pad", "chord", "harmony")),
        ("lead", ("lead", "melody", "solo")),
    )
    for role, tokens in roles:
        if any(token in lowered for token in tokens):
            return {
                "value": role,
                "source": "inferred",
                "uncertainty": 0.35,
                "provenance": {"method": "track name and clip kind"},
            }
    return {
        "value": "unknown",
        "source": "inferred",
        "uncertainty": 1.0,
        "provenance": {"method": "track name and clip kind"},
    }


def _clip_kind(clip: object) -> str:
    if isinstance(clip, SampleClip):
        return "sample"
    if isinstance(clip, AudioClip):
        return "audio"
    if isinstance(clip, DrumClip):
        return "drum"
    if isinstance(clip, MidiClip):
        return "midi"
    return "unknown"


def _count_clip_definitions(project: Project) -> int:
    return sum(len(track.clips) for track in project.tracks)


def _project_payload(project: Project) -> dict[str, object]:
    return {
        "id": _project_id(project),
        "name": project.name,
        "prism_version": project.prism_version,
        "tempo": project.tempo,
        "sample_rate": project.sample_rate,
        "time_signature": [project.beats_per_bar, project.beat_unit],
        "controller_boundary": project.controller_boundary,
        "audio_release_policy": project.audio_release_policy,
        "musical_context": {
            "key": project.key,
            "scale": project.scale,
            "chords": list(project.chords),
        },
        "tracks": [
            {
                "id": _track_id(project, track, index),
                "name": track.name,
                "role": track.role,
                "clips": [
                    {
                        "id": _clip_definition_id(project, track, placement, clip_index),
                        "section": placement.section,
                        "start_bar": placement.start_bar,
                        "repeat": placement.repeat,
                        "clip": _json_safe(placement.clip),
                    }
                    for clip_index, placement in enumerate(track.clips)
                ],
                "instrument": _json_safe(track.instrument_plugin),
                "effects": [_json_safe(effect) for effect in track.effects],
            }
            for index, track in enumerate(project.tracks)
        ],
        "sections": [_json_safe(section) for section in project.sections],
        "buses": [
            {
                "id": bus.bus_id,
                "name": bus.name,
                "track_ids": [track.track_id for track in bus.tracks],
                "effects": [_json_safe(effect) for effect in bus.effects],
            }
            for bus in project.buses
        ],
        "master_effects": [_json_safe(effect) for effect in project.master_effects],
    }


def _select_from_context(
    context: Mapping[str, object], selection: Mapping[str, object]
) -> dict[str, object]:
    entity_value = selection.get("entity", selection.get("entity_type", "track"))
    if not isinstance(entity_value, str):
        raise AgentError("invalid_selection", "Selection entity must be a string.")
    entity = entity_value.strip().casefold()
    aliases = {
        "tracks": "track",
        "sections": "section",
        "clips": "clip_definition",
        "clip": "clip_definition",
        "instances": "clip_instance",
        "plugins": "plugin",
        "notes": "note",
        "controllers": "controller",
    }
    entity = aliases.get(entity, entity)
    collections = {
        "project": [context["project"]],
        "track": context["arrangement"]["tracks"],  # type: ignore[index]
        "section": context["arrangement"]["sections"],  # type: ignore[index]
        "bus": context["routing"]["buses"],  # type: ignore[index]
        "clip_definition": context["arrangement"]["clip_definitions"],  # type: ignore[index]
        "clip_instance": context["arrangement"]["clip_instances"],  # type: ignore[index]
        "note": context["arrangement"]["notes"],  # type: ignore[index]
        "controller": context["arrangement"]["controllers"],  # type: ignore[index]
        "plugin": context["plugins"]["instances"],  # type: ignore[index]
    }
    try:
        candidates = list(collections[entity])
    except KeyError as error:
        raise AgentError(
            "unsupported_entity_type",
            f"Selection entity {entity_value!r} is not supported.",
            details={"supported": sorted(collections)},
        ) from error

    requested_id = selection.get("id", selection.get(f"{entity}_id"))
    requested_ids = selection.get("ids")
    if requested_ids is not None:
        if (
            isinstance(requested_ids, str)
            or not isinstance(requested_ids, Sequence)
            or not all(isinstance(item, str) for item in requested_ids)
        ):
            raise AgentError("invalid_selection", "Selection ids must be a list of strings.")
        requested_id_set = set(requested_ids)
        candidates = [item for item in candidates if item.get("id") in requested_id_set]
        if not candidates:
            raise AgentError(
                "unknown_id",
                "None of the requested IDs exists in this revision.",
                details={"entity": entity, "ids": list(requested_ids)},
            )
    elif requested_id is not None:
        if not isinstance(requested_id, str):
            raise AgentError("invalid_selection", "Selection id must be a string.")
        candidates = [item for item in candidates if item.get("id") == requested_id]
        if not candidates:
            raise AgentError(
                "unknown_id",
                f"No {entity} has ID {requested_id!r} in this revision.",
                details={"entity": entity, "id": requested_id},
            )

    requested_name = selection.get("name", selection.get("display_name"))
    if requested_name is not None:
        if not isinstance(requested_name, str):
            raise AgentError("invalid_selection", "Selection name must be a string.")
        named = [
            item
            for item in candidates
            if str(item.get("name", item.get("display_name", ""))).casefold()
            == requested_name.casefold()
        ]
        if len(named) > 1:
            raise AgentError(
                "ambiguous_name",
                f"{entity.title()} name {requested_name!r} is ambiguous; use an ID.",
                details={
                    "entity": entity,
                    "name": requested_name,
                    "candidates": [
                        {"id": item.get("id"), "name": item.get("name")} for item in named
                    ],
                },
            )
        candidates = named

    role = selection.get("role", selection.get("musical_role"))
    if role is not None:
        if not isinstance(role, str):
            raise AgentError("invalid_selection", "Selection role must be a string.")
        candidates = [
            item
            for item in candidates
            if isinstance(item.get("role"), Mapping)
            and str(item["role"].get("value", "")).casefold() == role.casefold()
        ]

    section_value = selection.get("section", selection.get("section_id"))
    if section_value is not None:
        if not isinstance(section_value, str):
            raise AgentError("invalid_selection", "Selection section must be a string.")
        section_ids = {
            str(item["id"])
            for item in context["arrangement"]["sections"]  # type: ignore[index]
            if str(item.get("id")) == section_value
            or str(item.get("name", "")).casefold() == section_value.casefold()
        }
        if not section_ids:
            raise AgentError(
                "unknown_id",
                f"No section has ID or name {section_value!r} in this revision.",
                details={"section": section_value},
            )
        candidates = [
            item
            for item in candidates
            if str(item.get("section_id", "")) in section_ids
            or str(item.get("id", "")) in section_ids
            or any(str(value) in section_ids for value in item.get("section_ids", []))
        ]

    start_beat, end_beat = _selection_range(selection)
    if start_beat is not None:
        candidates = [
            item
            for item in candidates
            if _overlaps_range(item, start_beat, end_beat or start_beat)
        ]
    if not candidates:
        raise AgentError(
            "no_match",
            f"The {entity} selection matched no entities.",
            details={"entity": entity},
        )
    if start_beat is not None:
        selected_ranges = [{"start_beat": start_beat, "end_beat": end_beat}]
    else:
        ranged = [
            (float(item[start_key]), float(item[end_key]))
            for item in candidates
            for start_key, end_key in (("start_beat", "end_beat"),)
            if isinstance(item.get(start_key), int | float)
            and isinstance(item.get(end_key), int | float)
        ]
        selected_ranges = (
            [
                {
                    "start_beat": min(item[0] for item in ranged),
                    "end_beat": max(item[1] for item in ranged),
                }
            ]
            if ranged
            else []
        )
    return {
        "entity_type": entity,
        "items": candidates,
        "count": len(candidates),
        "selected_ranges": selected_ranges,
    }


def _selection_range(selection: Mapping[str, object]) -> tuple[float | None, float | None]:
    raw = selection.get("quarter_note_range", selection.get("range"))
    start: object | None = selection.get("start_beat")
    end: object | None = selection.get("end_beat")
    if raw is not None:
        if isinstance(raw, Mapping):
            start = raw.get("start_beat", raw.get("start", start))
            end = raw.get("end_beat", raw.get("end", end))
        elif isinstance(raw, Sequence) and not isinstance(raw, str) and len(raw) == 2:
            start, end = raw[0], raw[1]
        else:
            raise AgentError(
                "invalid_range",
                "quarter_note_range must be [start, end] or an object.",
            )
    if start is None and end is None:
        return None, None
    if start is None:
        start = 0.0
    if end is None:
        raise AgentError("invalid_range", "A quarter-note range needs an end beat.")
    if isinstance(start, bool) or not isinstance(start, int | float):
        raise AgentError("invalid_range", "Range start must be a finite number.")
    if isinstance(end, bool) or not isinstance(end, int | float):
        raise AgentError("invalid_range", "Range end must be a finite number.")
    resolved_start = float(start)
    resolved_end = float(end)
    if (
        not math.isfinite(resolved_start)
        or not math.isfinite(resolved_end)
        or resolved_start < 0.0
        or resolved_end <= resolved_start
    ):
        raise AgentError("invalid_range", "Range must be finite with 0 <= start < end.")
    return resolved_start, resolved_end


def _overlaps_range(item: Mapping[str, object], start: float, end: float) -> bool:
    item_start = item.get("start_beat", item.get("beat"))
    item_end = item.get("end_beat", item_start)
    if not isinstance(item_start, int | float) or not isinstance(item_end, int | float):
        return False
    return float(item_start) < end and float(item_end) >= start


def _request_operation(request: Mapping[str, object] | AgentOperationRequest) -> str:
    if isinstance(request, AgentOperationRequest):
        return request.operation
    operation = request.get("operation")
    return operation if isinstance(operation, str) else "unknown"


def _safe_revision(project: Project) -> str | None:
    try:
        return project_revision_id(project)
    except Exception:
        return None


def _take(items: Sequence[dict[str, object]], limit: int) -> tuple[list[dict[str, object]], bool]:
    return list(items[:limit]), len(items) > limit


def _range_list(value: object) -> list[dict[str, object]]:
    if not isinstance(value, Sequence) or isinstance(value, str):
        return []
    return [dict(item) for item in value if isinstance(item, Mapping)]


def _json_safe(value: object) -> object:
    if value is None or isinstance(value, str | int | bool):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, Path):
        return value.as_posix()
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        return [_json_safe(item) for item in value]
    if is_dataclass(value):
        return {
            str(field_name): _json_safe(getattr(value, field_name))
            for field_name in value.__dataclass_fields__
        }
    return str(value)


__all__ = [
    "AGENT_CONTRACT",
    "AGENT_CONTRACT_VERSION",
    "AGENT_SCHEMA_VERSION",
    "IDENTITY_SCHEMA_VERSION",
    "AgentError",
    "AgentLimits",
    "AgentOperationRequest",
    "agent_capabilities",
    "agent_operation",
    "build_agent_operation",
    "inspect_agent_context",
    "project_revision_id",
    "select_agent_entities",
]

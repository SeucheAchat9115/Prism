"""Readable, script-first project builders for music producers."""

from __future__ import annotations

import inspect
import math
from dataclasses import asdict, dataclass, replace
from pathlib import Path, PurePath
from typing import TYPE_CHECKING, Literal, Self

from prism.errors import ProjectError
from prism.music import note_steps, rhythm_steps, validate_gain, validate_pan
from prism.plugins import (
    AutomationCurve,
    AutomationLane,
    EffectPreset,
    Plugin,
    automation_points,
    effect_plugin,
    instrument_plugin,
)
from prism.synthesis.engine import native_instrument_settings
from prism.synthesis.types import (
    MAX_SYNTH_SECONDS,
    MELODIC_PRESETS,
    PERCUSSION_PRESETS,
    SynthWaveform,
)

if TYPE_CHECKING:
    from prism.midi import MidiResult
    from prism.render import RenderResult


@dataclass(frozen=True, slots=True)
class SampleClip:
    path: str
    pattern: tuple[str, ...]
    bars: int
    gain_db: float


@dataclass(frozen=True, slots=True)
class AudioClip:
    path: str
    bars: int
    loop: bool
    gain_db: float


@dataclass(frozen=True, slots=True)
class DrumClip:
    preset: Literal["kick", "snare", "hihat"]
    pattern: tuple[str, ...]
    bars: int
    gain_db: float
    seed: int


@dataclass(frozen=True, slots=True)
class MidiClip:
    instrument: Literal["bass", "lead", "pad"]
    notes: tuple[str, ...]
    bars: int
    velocity: int
    waveform: SynthWaveform | None
    attack_ms: float | None
    decay_ms: float | None
    sustain: float | None
    release_ms: float | None
    cutoff_hz: float | None
    gate: float
    gain_db: float


TrackClip = SampleClip | AudioClip | DrumClip | MidiClip


@dataclass(frozen=True, slots=True)
class Section:
    """One consecutive song section in the rendered arrangement."""

    name: str
    bars: int
    tracks: tuple[str, ...] | None = None


@dataclass(frozen=True, slots=True)
class ProjectSummary:
    """A small, printable validation result."""

    name: str
    tracks: int
    sections: int
    bars: int
    duration_seconds: float

    def __str__(self) -> str:
        return (
            f"{self.name}: {self.tracks} {'track' if self.tracks == 1 else 'tracks'}, "
            f"{self.sections} {'section' if self.sections == 1 else 'sections'}, "
            f"{self.bars} {'bar' if self.bars == 1 else 'bars'}, "
            f"{self.duration_seconds:.2f} seconds"
        )


class Track:
    """A named mixer channel with one loopable musical part."""

    def __init__(
        self,
        project: Project,
        name: str,
        *,
        gain_db: float = 0.0,
        pan: float = 0.0,
        muted: bool = False,
    ) -> None:
        self._project = project
        self.name = _name(name, "Track")
        self.gain_db = validate_gain(gain_db, label=f"Track {self.name!r} gain")
        self.pan = validate_pan(pan)
        self.muted = bool(muted)
        self._clip: TrackClip | None = None
        self._instrument: Plugin | None = None
        self.effects: list[Plugin] = []

    @property
    def clip(self) -> TrackClip | None:
        return self._clip

    @property
    def instrument_plugin(self) -> Plugin | None:
        """The stock instrument that turns this track's events into sound."""

        return self._instrument

    def sample(
        self,
        path: str | Path,
        pattern: str = "x",
        *,
        bars: int = 1,
        gain_db: float = 0.0,
    ) -> Self:
        """Trigger a project-local WAV/AIFF sample from an ``x---`` pattern."""

        self._set_clip(
            SampleClip(
                path=self._project._source_name(path),
                pattern=rhythm_steps(pattern),
                bars=_bars(bars, f"Sample track {self.name!r}"),
                gain_db=validate_gain(gain_db, label=f"Sample track {self.name!r} clip gain"),
            )
        )
        assert self._clip is not None
        self._instrument = instrument_plugin(
            "sampler",
            name=f"{self.name} Sampler",
            track=self.name,
            settings={"gain_db": self._clip.gain_db},
            melodic=False,
        )
        return self

    def audio(
        self,
        path: str | Path,
        *,
        bars: int = 1,
        loop: bool = True,
        gain_db: float = 0.0,
    ) -> Self:
        """Use a project-local audio loop or one-shot as the track content."""

        self._set_clip(
            AudioClip(
                path=self._project._source_name(path),
                bars=_bars(bars, f"Audio track {self.name!r}"),
                loop=bool(loop),
                gain_db=validate_gain(gain_db, label=f"Audio track {self.name!r} clip gain"),
            )
        )
        assert self._clip is not None
        self._instrument = instrument_plugin(
            "audio_player",
            name=f"{self.name} Audio Player",
            track=self.name,
            settings={"gain_db": self._clip.gain_db},
            melodic=False,
        )
        return self

    def drum(
        self,
        preset: Literal["kick", "snare", "hihat"],
        pattern: str,
        *,
        bars: int = 1,
        gain_db: float = -3.0,
        seed: int = 0,
    ) -> Self:
        """Program a built-in drum without needing an external sample."""

        if preset not in PERCUSSION_PRESETS:
            raise ProjectError("Built-in drums are kick, snare, or hihat.")
        if not 0 <= seed <= 4_294_967_295:
            raise ProjectError("Drum seed must be between 0 and 4294967295.")
        self._set_clip(
            DrumClip(
                preset=preset,
                pattern=rhythm_steps(pattern),
                bars=_synth_bars(bars, f"Drum track {self.name!r}", self._project),
                gain_db=validate_gain(gain_db, label=f"Drum track {self.name!r} clip gain"),
                seed=seed,
            )
        )
        assert self._clip is not None
        self._instrument = instrument_plugin(
            preset,
            name=f"{self.name} Instrument",
            track=self.name,
            settings={"gain_db": self._clip.gain_db, "seed": float(seed)},
            melodic=False,
        )
        return self

    def midi(
        self,
        notes: str,
        *,
        instrument: Literal["bass", "lead", "pad"] = "lead",
        bars: int = 1,
        velocity: int = 100,
        waveform: SynthWaveform | None = None,
        attack_ms: float | None = None,
        decay_ms: float | None = None,
        sustain: float | None = None,
        release_ms: float | None = None,
        cutoff_hz: float | None = None,
        gate: float = 0.8,
        gain_db: float = -6.0,
    ) -> Self:
        """Build a MIDI-note clip and render it with a built-in instrument."""

        if instrument not in MELODIC_PRESETS:
            raise ProjectError("Built-in MIDI instruments are bass, lead, or pad.")
        _waveform(waveform)
        if not 1 <= velocity <= 127:
            raise ProjectError("MIDI velocity must be between 1 and 127.")
        _optional_range(attack_ms, 0.0, 5000.0, "Attack")
        _optional_range(decay_ms, 0.0, 5000.0, "Decay")
        _optional_range(sustain, 0.0, 1.0, "Sustain")
        _optional_range(release_ms, 0.0, 5000.0, "Release")
        _optional_range(cutoff_hz, 20.0, 20_000.0, "Cutoff")
        if not 0.05 <= gate <= 1.0:
            raise ProjectError("MIDI gate must be between 0.05 and 1.0.")
        self._set_clip(
            MidiClip(
                instrument=instrument,
                notes=note_steps(notes),
                bars=_synth_bars(bars, f"MIDI track {self.name!r}", self._project),
                velocity=velocity,
                waveform=waveform,
                attack_ms=attack_ms,
                decay_ms=decay_ms,
                sustain=sustain,
                release_ms=release_ms,
                cutoff_hz=cutoff_hz,
                gate=float(gate),
                gain_db=validate_gain(gain_db, label=f"MIDI track {self.name!r} clip gain"),
            )
        )
        self._set_melodic_instrument(instrument, name=None)
        return self

    def instrument(
        self,
        preset: Literal["bass", "lead", "pad"],
        *,
        name: str | None = None,
        waveform: SynthWaveform | None = None,
        attack_ms: float | None = None,
        decay_ms: float | None = None,
        sustain: float | None = None,
        release_ms: float | None = None,
        cutoff_hz: float | None = None,
        gain_db: float | None = None,
    ) -> Plugin:
        """Choose the stock instrument that consumes this track's MIDI notes."""

        clip = self._clip
        if not isinstance(clip, MidiClip):
            raise ProjectError("instrument() follows midi() on the same track.")
        if preset not in MELODIC_PRESETS:
            raise ProjectError("Built-in MIDI instruments are bass, lead, or pad.")
        _waveform(waveform)
        _optional_range(attack_ms, 0.0, 5000.0, "Attack")
        _optional_range(decay_ms, 0.0, 5000.0, "Decay")
        _optional_range(sustain, 0.0, 1.0, "Sustain")
        _optional_range(release_ms, 0.0, 5000.0, "Release")
        _optional_range(cutoff_hz, 20.0, 20_000.0, "Cutoff")
        resolved_gain = clip.gain_db if gain_db is None else validate_gain(
            gain_db, label=f"Instrument {self.name!r} gain"
        )
        self._clip = replace(
            clip,
            instrument=preset,
            waveform=waveform,
            attack_ms=attack_ms,
            decay_ms=decay_ms,
            sustain=sustain,
            release_ms=release_ms,
            cutoff_hz=cutoff_hz,
            gain_db=resolved_gain,
        )
        return self._set_melodic_instrument(preset, name=name)

    def effect(
        self,
        preset: EffectPreset,
        *,
        name: str | None = None,
        **settings: float,
    ) -> Plugin:
        """Append one stock effect after the instrument on this track."""

        if self._clip is None:
            raise ProjectError("Add MIDI, a drum, a sample, or audio before adding effects.")
        base_name = preset.replace("_", " ").title() if name is None else _name(name, "Plugin")
        plugin_name = base_name
        suffix = 2
        used = {effect.name.casefold() for effect in self.effects}
        if self._instrument is not None:
            used.add(self._instrument.name.casefold())
        while plugin_name.casefold() in used:
            plugin_name = f"{base_name} {suffix}"
            suffix += 1
        plugin = effect_plugin(
            preset, name=plugin_name, track=self.name, settings=settings
        )
        self.effects.append(plugin)
        return plugin

    def _set_melodic_instrument(
        self,
        preset: Literal["bass", "lead", "pad"],
        *,
        name: str | None,
    ) -> Plugin:
        clip = self._clip
        assert isinstance(clip, MidiClip)
        settings: dict[str, object] = {}
        settings.update(native_instrument_settings(preset))
        overrides = {
            "waveform": clip.waveform,
            "attack_ms": clip.attack_ms,
            "decay_ms": clip.decay_ms,
            "sustain": clip.sustain,
            "release_ms": clip.release_ms,
            "cutoff_hz": clip.cutoff_hz,
        }
        settings.update({key: value for key, value in overrides.items() if value is not None})
        settings["gain_db"] = clip.gain_db
        self._instrument = instrument_plugin(
            preset,
            name=f"{self.name} Instrument" if name is None else _name(name, "Plugin"),
            track=self.name,
            settings=settings,
            melodic=True,
        )
        return self._instrument

    def _set_clip(self, clip: TrackClip) -> None:
        if self._clip is not None:
            raise ProjectError(
                f"Track {self.name!r} already has content. Create another track for another part."
            )
        self._clip = clip


class Project:
    """A complete song described by the producer's ``main.py`` file.

    Prism locates the running script automatically. Relative sample and output
    paths are resolved inside that script's project folder.
    """

    def __init__(
        self,
        name: str,
        *,
        prism_version: str,
        tempo: float = 120.0,
        sample_rate: int = 44_100,
        beats_per_bar: int = 4,
        beat_unit: Literal[1, 2, 4, 8, 16] = 4,
        master_gain_db: float = -3.0,
        normalize: bool = True,
        _script: str | Path | None = None,
    ) -> None:
        self.script = _project_script(_script)
        self.root = self.script.parent
        self.name = _name(name, "Project")
        self.prism_version = _version(prism_version)
        if not math.isfinite(tempo) or not 20.0 <= tempo <= 300.0:
            raise ProjectError("Tempo must be between 20 and 300 BPM.")
        if not 8_000 <= sample_rate <= 192_000:
            raise ProjectError("Sample rate must be between 8000 and 192000 Hz.")
        if not 1 <= beats_per_bar <= 32:
            raise ProjectError("Beats per bar must be between 1 and 32.")
        if beat_unit not in {1, 2, 4, 8, 16}:
            raise ProjectError("Beat unit must be 1, 2, 4, 8, or 16.")
        self.tempo = float(tempo)
        self.sample_rate = int(sample_rate)
        self.beats_per_bar = int(beats_per_bar)
        self.beat_unit = beat_unit
        self.master_gain_db = validate_gain(master_gain_db, label="Master gain")
        self.normalize = bool(normalize)
        self.tracks: list[Track] = []
        self.sections: list[Section] = []
        self.automation_lanes: list[AutomationLane] = []

    @property
    def frames_per_bar(self) -> int:
        return int(round(self.sample_rate * self.beats_per_bar * 60.0 / self.tempo))

    def track(
        self,
        name: str,
        *,
        gain_db: float = 0.0,
        pan: float = 0.0,
        muted: bool = False,
    ) -> Track:
        """Add a track and return it so its musical content can be described."""

        clean = _name(name, "Track")
        if any(track.name.casefold() == clean.casefold() for track in self.tracks):
            raise ProjectError(f"Track names must be unique; {clean!r} is already used.")
        track = Track(self, clean, gain_db=gain_db, pan=pan, muted=muted)
        self.tracks.append(track)
        return track

    def section(
        self,
        name: str,
        *,
        bars: int,
        tracks: list[Track | str] | tuple[Track | str, ...] | None = None,
    ) -> Section:
        """Append a song section. Omit ``tracks`` to play every track."""

        clean = _name(name, "Section")
        if any(section.name.casefold() == clean.casefold() for section in self.sections):
            raise ProjectError(f"Section names must be unique; {clean!r} is already used.")
        names = (
            None
            if tracks is None
            else tuple(item.name if isinstance(item, Track) else item for item in tracks)
        )
        section = Section(clean, _bars(bars, f"Section {clean!r}"), names)
        self.sections.append(section)
        return section

    def automation(
        self,
        name: str,
        *,
        target: Plugin,
        parameter: str,
        points: list[tuple[float, float]] | tuple[tuple[float, float], ...],
        curve: AutomationCurve = "linear",
    ) -> AutomationLane:
        """Add an automation track for one stock-plugin setting."""

        clean = _name(name, "Automation")
        if curve not in {"linear", "hold"}:
            raise ProjectError("Automation curve must be linear or hold.")
        if any(lane.name.casefold() == clean.casefold() for lane in self.automation_lanes):
            raise ProjectError(f"Automation names must be unique; {clean!r} is already used.")
        if not self._owns_plugin(target):
            raise ProjectError("Automation target must be a plugin from this project.")
        if any(
            lane.target is target and lane.parameter == parameter
            for lane in self.automation_lanes
        ):
            raise ProjectError(
                f"Plugin {target.name!r} parameter {parameter!r} already has automation."
            )
        lane = AutomationLane(
            name=clean,
            target=target,
            parameter=parameter,
            points=automation_points(points, target=target, parameter_name=parameter),
            curve=curve,
        )
        self.automation_lanes.append(lane)
        return lane

    def validate(self) -> ProjectSummary:
        """Check the complete description and return a readable summary."""

        if self.script.suffix.casefold() != ".py" or not self.script.is_file():
            raise ProjectError(
                f"Project script does not exist or is not a Python file: {self.script}"
            )
        if not self.tracks:
            raise ProjectError("Add at least one track before rendering.")
        for track in self.tracks:
            if track.clip is None:
                raise ProjectError(
                    f"Track {track.name!r} has no sample, drum, audio, or MIDI part."
                )
        if not self.sections:
            raise ProjectError("Add at least one section before rendering.")
        known = {track.name for track in self.tracks}
        for section in self.sections:
            if section.tracks is None:
                continue
            unknown = [name for name in section.tracks if name not in known]
            if unknown:
                raise ProjectError(
                    f"Section {section.name!r} refers to unknown tracks: {', '.join(unknown)}."
                )
            if len(set(section.tracks)) != len(section.tracks):
                raise ProjectError(f"Section {section.name!r} lists the same track more than once.")
        files = tuple(sorted(self._sample_files(), key=lambda path: path.as_posix().casefold()))
        for path in files:
            if not path.is_file():
                relative = path.relative_to(self.root)
                raise ProjectError(
                    f"Sample file is missing: {relative}. Put it inside the project folder."
                )
        bars = sum(section.bars for section in self.sections)
        for lane in self.automation_lanes:
            if not self._owns_plugin(lane.target):
                raise ProjectError(
                    f"Automation {lane.name!r} targets a plugin that was replaced."
                )
            if lane.points[-1].bar > bars:
                raise ProjectError(
                    f"Automation {lane.name!r} ends at bar {lane.points[-1].bar:g}, "
                    f"after the song's {bars} bars."
                )
        return ProjectSummary(
            name=self.name,
            tracks=len(self.tracks),
            sections=len(self.sections),
            bars=bars,
            duration_seconds=bars * self.beats_per_bar * 60.0 / self.tempo,
        )

    def render(self, output: str | Path = "renders/song.wav") -> RenderResult:
        """Validate and deterministically render the arrangement to a WAV file."""

        from prism.render import render_project

        return render_project(self, output)

    def export_midi(self, output: str | Path = "renders/song.mid") -> MidiResult:
        """Write built-in drum and MIDI tracks as a standard MIDI file."""

        from prism.midi import export_midi

        return export_midi(self, output)

    def configuration(self) -> dict[str, object]:
        """Return the resolved song settings as a plain dictionary."""

        tracks: list[dict[str, object]] = []
        for track in self.tracks:
            assert track.clip is not None
            tracks.append(
                {
                    "name": track.name,
                    "gain_db": track.gain_db,
                    "pan": track.pan,
                    "muted": track.muted,
                    "part": {"kind": _clip_kind(track.clip), **asdict(track.clip)},
                    "instrument": _plugin_configuration(track.instrument_plugin),
                    "effects": [_plugin_configuration(effect) for effect in track.effects],
                }
            )
        return {
            "schema_version": 2,
            "prism_version": self.prism_version,
            "name": self.name,
            "script": self.script.name,
            "tempo": self.tempo,
            "sample_rate": self.sample_rate,
            "time_signature": [self.beats_per_bar, self.beat_unit],
            "master_gain_db": self.master_gain_db,
            "normalize": self.normalize,
            "tracks": tracks,
            "sections": [asdict(section) for section in self.sections],
            "automation": [
                {
                    "name": lane.name,
                    "track": lane.target.track,
                    "target": lane.target.name,
                    "parameter": lane.parameter,
                    "curve": lane.curve,
                    "points": [asdict(point) for point in lane.points],
                }
                for lane in self.automation_lanes
            ],
        }

    def _owns_plugin(self, plugin: Plugin) -> bool:
        return any(
            track.instrument_plugin is plugin or any(effect is plugin for effect in track.effects)
            for track in self.tracks
        )

    def _source_name(self, value: str | Path) -> str:
        path = Path(value)
        if path.is_absolute() or ".." in PurePath(path).parts:
            raise ProjectError(
                f"Sample paths must be relative to the project folder, not {str(value)!r}."
            )
        candidate = (self.root / path).resolve(strict=False)
        try:
            relative = candidate.relative_to(self.root)
        except ValueError as error:
            raise ProjectError("Sample paths must stay inside the project folder.") from error
        return relative.as_posix()

    def _output_path(self, value: str | Path, *, suffix: str) -> Path:
        path = Path(value)
        if path.is_absolute() or ".." in PurePath(path).parts:
            raise ProjectError("Output paths must be relative to the project folder.")
        if path.suffix.casefold() != suffix:
            raise ProjectError(f"Output must use the {suffix} extension: {path}")
        resolved = (self.root / path).resolve(strict=False)
        try:
            resolved.relative_to(self.root)
        except ValueError as error:
            raise ProjectError("Output paths must stay inside the project folder.") from error
        if resolved == self.script:
            raise ProjectError("An output cannot overwrite the project script.")
        if resolved in self._sample_files():
            raise ProjectError("An output cannot overwrite a source sample.")
        return resolved

    def _sample_files(self) -> set[Path]:
        paths: set[Path] = set()
        for track in self.tracks:
            clip = track.clip
            if isinstance(clip, SampleClip | AudioClip):
                paths.add((self.root / clip.path).resolve(strict=False))
        return paths


def _clip_kind(clip: TrackClip) -> str:
    if isinstance(clip, SampleClip):
        return "sample"
    if isinstance(clip, AudioClip):
        return "audio"
    if isinstance(clip, DrumClip):
        return "drum"
    return "midi"


def _plugin_configuration(plugin: Plugin | None) -> dict[str, object] | None:
    if plugin is None:
        return None
    return {
        "name": plugin.name,
        "track": plugin.track,
        "kind": plugin.kind,
        "preset": plugin.preset,
        "settings": dict(plugin.settings),
    }


def _name(value: str, label: str) -> str:
    clean = value.strip()
    if not clean:
        raise ProjectError(f"{label} name cannot be empty.")
    if len(clean) > 120:
        raise ProjectError(f"{label} name cannot exceed 120 characters.")
    return clean


def _version(value: str) -> str:
    clean = value.strip()
    if not clean or len(clean) > 64:
        raise ProjectError("Prism version must be a non-empty value from the project template.")
    return clean


def _project_script(value: str | Path | None) -> Path:
    if value is not None:
        return Path(value).resolve(strict=False)
    frame = inspect.currentframe()
    try:
        constructor = None if frame is None else frame.f_back
        caller = None if constructor is None else constructor.f_back
        filename = None if caller is None else caller.f_code.co_filename
    finally:
        del frame
    if filename is None or filename.startswith("<"):
        raise ProjectError("Create and run a main.py file so Prism can locate the project folder.")
    return Path(filename).resolve(strict=False)


def _bars(value: int, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 256:
        raise ProjectError(f"{label} bars must be an integer between 1 and 256.")
    return value


def _synth_bars(value: int, label: str, project: Project) -> int:
    bars = _bars(value, label)
    duration = bars * project.beats_per_bar * 60.0 / project.tempo
    if duration > MAX_SYNTH_SECONDS:
        raise ProjectError(
            f"{label} cannot exceed {MAX_SYNTH_SECONDS:g} seconds; use fewer bars."
        )
    return bars


def _optional_range(value: float | None, low: float, high: float, label: str) -> None:
    if value is not None and (not math.isfinite(value) or not low <= value <= high):
        raise ProjectError(f"{label} must be between {low:g} and {high:g}.")


def _waveform(value: SynthWaveform | None) -> None:
    if value not in {None, "sine", "triangle", "saw", "square"}:
        raise ProjectError("Waveform must be sine, triangle, saw, or square.")


__all__ = [
    "Project",
    "ProjectSummary",
    "Section",
    "Track",
]

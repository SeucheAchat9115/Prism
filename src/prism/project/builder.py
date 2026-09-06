"""Readable, script-first project builders for music producers."""

from __future__ import annotations

import inspect
import math
import random
from dataclasses import asdict, dataclass, replace
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import TYPE_CHECKING, Literal, Self, Sequence, TypedDict

from prism.errors import ProjectError
from prism.music import (
    ControlCurve,
    ControllerBoundaryMode,
    ControlPoint,
    Note,
    note_steps,
    rhythm_steps,
    validate_gain,
    validate_pan,
)
from prism.plugins import (
    CANONICAL_AUTOMATION_VERSION,
    LEGACY_AUTOMATION_VERSION,
    STOCK_PLUGINS,
    AutomationCompatibility,
    AutomationCurve,
    AutomationLane,
    EffectPreset,
    OutputGainLane,
    Plugin,
    automation_points,
    effect_plugin,
    instrument_plugin,
    output_gain_points,
    parameter_identity,
    vst3_plugin,
)
from prism.sample_library import SampleLibrary
from prism.synthesis.engine import native_instrument_settings
from prism.synthesis.types import (
    MAX_SYNTH_CLIP_BARS,
    MAX_SYNTH_SECONDS,
    SynthWaveform,
    Uniwave,
)
from prism.timing import CANONICAL_TIMING_VERSION, MusicalTiming, TimeSignature, TimingCompatibility
from prism.vst import VST3, VSTRegistry

if TYPE_CHECKING:
    from prism.arrangement import CompiledTrackEvents
    from prism.midi import MidiResult
    from prism.render import RenderResult, StemRenderResult


@dataclass(frozen=True, slots=True)
class SampleClip:
    path: str
    pattern: tuple[str, ...]
    bars: int
    gain_db: float
    start_seconds: float = 0.0
    end_seconds: float | None = None
    fade_in_ms: float = 0.0
    fade_out_ms: float = 0.0
    reverse: bool = False
    playback_rate: float = 1.0
    transpose_semitones: int = 0
    stretch_bars: float | None = None
    release_policy: AudioReleasePolicy | None = None


@dataclass(frozen=True, slots=True)
class AudioClip:
    path: str
    bars: int
    loop: bool
    gain_db: float
    start_seconds: float = 0.0
    end_seconds: float | None = None
    fade_in_ms: float = 0.0
    fade_out_ms: float = 0.0
    reverse: bool = False
    playback_rate: float = 1.0
    transpose_semitones: int = 0
    stretch_bars: float | None = None
    release_policy: AudioReleasePolicy | None = None


class _AudioEditing(TypedDict):
    start_seconds: float
    end_seconds: float | None
    fade_in_ms: float
    fade_out_ms: float
    reverse: bool
    playback_rate: float
    transpose_semitones: int
    stretch_bars: float | None


@dataclass(frozen=True, slots=True)
class DrumClip:
    preset: str
    pattern: tuple[str, ...]
    bars: int
    gain_db: float
    seed: int
    release_policy: AudioReleasePolicy | None = None


@dataclass(frozen=True, slots=True)
class MidiClip:
    instrument: str
    uniwave: Uniwave | None
    notes: tuple[str, ...]
    events: tuple[Note, ...]
    pitch_bend: tuple[ControlPoint, ...]
    modulation: tuple[ControlPoint, ...]
    pitch_bend_range: float
    pitch_bend_curve: ControlCurve
    modulation_curve: ControlCurve
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
    swing: float
    humanize_timing_ms: float
    humanize_velocity: int
    humanize_seed: int


TrackClip = SampleClip | AudioClip | DrumClip | MidiClip
InstrumentSpecification = str | Uniwave | VST3
AudioReleasePolicy = Literal["natural", "cut", "choke", "legacy"]
DEFAULT_AUDIO_RELEASE_POLICY: AudioReleasePolicy = "natural"


@dataclass(frozen=True, slots=True)
class ClipPlacement:
    """One track clip placed relative to a section's beginning."""

    clip: TrackClip
    section: str | None
    start_bar: float
    repeat: bool


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


@dataclass(frozen=True, slots=True)
class Send:
    """A post-fader copy of one track routed to a return bus."""

    track: str
    bus: str
    gain_db: float


class Track:
    """A named mixer channel containing compatible, reusable musical clips."""

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
        self._clips: list[ClipPlacement] = []
        self._instrument: Plugin | None = None
        self._instrument_specification: InstrumentSpecification | None = None
        self._instrument_instance_id = f"track:{self.name}:instrument"
        self._output_gain_lane: OutputGainLane | None = None
        self._pitch_bend_range: float | None = None
        self.effects: list[Plugin] = []
        self.output_bus: Bus | None = None
        self.sends: list[Send] = []

    @property
    def clip(self) -> TrackClip | None:
        """Return the first clip for compatibility with one-clip projects."""

        return None if not self._clips else self._clips[0].clip

    @property
    def clips(self) -> tuple[ClipPlacement, ...]:
        """Return every clip placement on this track in authoring order."""

        return tuple(self._clips)

    def clips_for(self, section: Section) -> tuple[ClipPlacement, ...]:
        """Resolve this section's explicit variation or the track defaults."""

        scoped = tuple(item for item in self._clips if item.section == section.name)
        if scoped:
            return scoped
        return tuple(item for item in self._clips if item.section is None)

    @property
    def instrument_plugin(self) -> Plugin | None:
        """The stock instrument that turns this track's events into sound."""

        return self._instrument

    @property
    def instrument_specification(self) -> InstrumentSpecification | None:
        """The immutable instrument declaration owned by this track.

        MIDI clips refer to this declaration instead of owning independent VST3
        state. A second clip may repeat an equivalent declaration, but a
        different VST3 alias, state, preset, or parameter map is rejected.
        """

        return self._instrument_specification

    @property
    def instrument_configuration(self) -> InstrumentSpecification | None:
        """Compatibility alias for :attr:`instrument_specification`."""

        return self._instrument_specification

    @property
    def output_gain_lane(self) -> OutputGainLane | None:
        """Return the explicit shared post-instrument gain envelope, if any."""

        return self._output_gain_lane

    def output_gain(
        self,
        points: Sequence[tuple[float, float]],
        *,
        name: str = "Shared output gain",
        curve: AutomationCurve = "linear",
    ) -> OutputGainLane:
        """Add one shared post-instrument output-gain lane in dB.

        This is a track-level envelope, not independent gain for individual
        clips or voices.  It is therefore safe to use with one continuous
        polyphonic VST instance after normalizing all of that track's clip
        gains to a common value.
        """

        if self._output_gain_lane is not None:
            raise ProjectError(f"Track {self.name!r} already has an output-gain lane.")
        if curve not in {"linear", "hold"}:
            raise ProjectError("Output-gain curve must be linear or hold.")
        lane = OutputGainLane(
            name=_name(name, "Output gain"),
            points=output_gain_points(
                points,
                label=f"Output gain lane on track {self.name!r}",
            ),
            curve=curve,
        )
        self._output_gain_lane = lane
        return lane

    @property
    def instrument_instance_id(self) -> str:
        """Return the stable identity of this track's instrument instance."""

        return self._instrument_instance_id

    def sample(
        self,
        path: str | Path,
        pattern: str = "x",
        *,
        bars: int = 1,
        gain_db: float = 0.0,
        section: str | None = None,
        start_bar: float = 0.0,
        repeat: bool = True,
        start_seconds: float = 0.0,
        end_seconds: float | None = None,
        fade_in_ms: float = 0.0,
        fade_out_ms: float = 0.0,
        reverse: bool = False,
        playback_rate: float = 1.0,
        transpose_semitones: int = 0,
        stretch_bars: float | None = None,
        release_policy: AudioReleasePolicy | None = None,
    ) -> Self:
        """Add a placed project-local sample pattern to this track.

        ``release_policy`` controls what happens when a triggered source reaches
        an arrangement boundary.  ``None`` inherits the project's
        ``audio_release_policy``; ``natural`` keeps the prepared source alive,
        ``cut`` stops it at the owning placement/section boundary, and
        ``choke`` stops an earlier voice when a later voice on this track starts.
        ``legacy`` is the pre-task-06 boundary-truncated behavior.
        """

        self._add_clip(
            SampleClip(
                path=self._project._source_name(path),
                pattern=rhythm_steps(pattern),
                bars=_bars(bars, f"Sample track {self.name!r}"),
                gain_db=validate_gain(gain_db, label=f"Sample track {self.name!r} clip gain"),
                **_audio_editing(
                    start_seconds=start_seconds,
                    end_seconds=end_seconds,
                    fade_in_ms=fade_in_ms,
                    fade_out_ms=fade_out_ms,
                    reverse=reverse,
                    playback_rate=playback_rate,
                    transpose_semitones=transpose_semitones,
                    stretch_bars=stretch_bars,
                ),
                release_policy=_optional_audio_release_policy(
                    release_policy, f"Sample track {self.name!r}"
                ),
            ),
            section=section,
            start_bar=start_bar,
            repeat=repeat,
        )
        if self._instrument is None:
            clip = self.clips[0].clip
            assert isinstance(clip, SampleClip)
            self._instrument = instrument_plugin(
                "sampler",
                name=f"{self.name} Sampler",
                track=self.name,
                settings={"gain_db": clip.gain_db},
                melodic=False,
                instance_id=self._instrument_instance_id,
            )
        return self

    def audio(
        self,
        path: str | Path,
        *,
        bars: int = 1,
        loop: bool = True,
        gain_db: float = 0.0,
        section: str | None = None,
        start_bar: float = 0.0,
        repeat: bool = True,
        start_seconds: float = 0.0,
        end_seconds: float | None = None,
        fade_in_ms: float = 0.0,
        fade_out_ms: float = 0.0,
        reverse: bool = False,
        playback_rate: float = 1.0,
        transpose_semitones: int = 0,
        stretch_bars: float | None = None,
        release_policy: AudioReleasePolicy | None = None,
    ) -> Self:
        """Add a placed project-local audio loop or one-shot to this track.

        ``loop`` repeats the prepared source inside one clip placement.
        ``repeat`` repeats that placement through the active section.  They are
        independent: ``loop=False, repeat=False`` is one source playback at one
        timeline position.  ``release_policy`` controls source voices that would
        otherwise cross the placement or section boundary.
        """

        self._add_clip(
            AudioClip(
                path=self._project._source_name(path),
                bars=_bars(bars, f"Audio track {self.name!r}"),
                loop=bool(loop),
                gain_db=validate_gain(gain_db, label=f"Audio track {self.name!r} clip gain"),
                **_audio_editing(
                    start_seconds=start_seconds,
                    end_seconds=end_seconds,
                    fade_in_ms=fade_in_ms,
                    fade_out_ms=fade_out_ms,
                    reverse=reverse,
                    playback_rate=playback_rate,
                    transpose_semitones=transpose_semitones,
                    stretch_bars=stretch_bars,
                ),
                release_policy=_optional_audio_release_policy(
                    release_policy, f"Audio track {self.name!r}"
                ),
            ),
            section=section,
            start_bar=start_bar,
            repeat=repeat,
        )
        if self._instrument is None:
            clip = self.clips[0].clip
            assert isinstance(clip, AudioClip)
            self._instrument = instrument_plugin(
                "audio_player",
                name=f"{self.name} Audio Player",
                track=self.name,
                settings={"gain_db": clip.gain_db},
                melodic=False,
                instance_id=self._instrument_instance_id,
            )
        return self

    def drum(
        self,
        preset: str,
        pattern: str,
        *,
        bars: int = 1,
        gain_db: float = -3.0,
        seed: int = 0,
        section: str | None = None,
        start_bar: float = 0.0,
        repeat: bool = True,
        release_policy: AudioReleasePolicy | None = None,
    ) -> Self:
        """Add a placed built-in drum clip without needing an external sample.

        Native percussion envelopes are natural by default.  Use ``choke`` when
        deliberately stopping a previous hit at the next hit, or ``cut`` when
        the arrangement boundary should stop the voice.
        """

        drum_definition = STOCK_PLUGINS.get("instrument", preset)
        if drum_definition.drum_note is None:
            raise ProjectError("This stock instrument is not a percussion preset.")
        if not 0 <= seed <= 4_294_967_295:
            raise ProjectError("Drum seed must be between 0 and 4294967295.")
        self._add_clip(
            DrumClip(
                preset=preset,
                pattern=rhythm_steps(pattern),
                bars=_synth_bars(bars, f"Drum track {self.name!r}", self._project),
                gain_db=validate_gain(gain_db, label=f"Drum track {self.name!r} clip gain"),
                seed=seed,
                release_policy=_optional_audio_release_policy(
                    release_policy, f"Drum track {self.name!r}"
                ),
            ),
            section=section,
            start_bar=start_bar,
            repeat=repeat,
        )
        if self._instrument is None:
            clip = self.clips[0].clip
            assert isinstance(clip, DrumClip)
            self._instrument = instrument_plugin(
                preset,
                name=f"{self.name} Instrument",
                track=self.name,
                settings={"gain_db": clip.gain_db, "seed": float(seed)},
                melodic=False,
                instance_id=self._instrument_instance_id,
            )
        return self

    def midi(
        self,
        notes: str | Sequence[str] | Sequence[Note],
        *,
        instrument: str | Uniwave | VST3 | None = None,
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
        section: str | None = None,
        start_bar: float = 0.0,
        repeat: bool = True,
        pitch_bend: Sequence[tuple[float, float]] = (),
        modulation: Sequence[tuple[float, float]] = (),
        pitch_bend_range: float | None = None,
        pitch_bend_curve: ControlCurve = "linear",
        modulation_curve: ControlCurve = "linear",
        swing: float = 0.5,
        humanize_timing_ms: float = 0.0,
        humanize_velocity: int = 0,
        humanize_seed: int = 0,
    ) -> Self:
        """Add a placed MIDI-note clip rendered by this track's instrument."""

        requested_instrument: str | Uniwave | VST3 = (
            self._instrument_specification
            if instrument is None and self._instrument_specification is not None
            else "uniwave"
            if instrument is None
            else instrument
        )
        preset, uniwave, external = _resolve_instrument(
            requested_instrument,
            waveform=waveform,
            attack_ms=attack_ms,
            decay_ms=decay_ms,
            sustain=sustain,
            release_ms=release_ms,
            cutoff_hz=cutoff_hz,
        )
        if external is None:
            definition = STOCK_PLUGINS.get("instrument", preset)
            if not definition.melodic:
                raise ProjectError("MIDI instruments must be melodic stock instruments.")
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
        resolved_bars = _synth_bars(bars, f"MIDI track {self.name!r}", self._project)
        notation, events = _midi_notes(
            notes,
            clip_beats=self._project.timing.bars_to_quarter_notes(resolved_bars),
            velocity=velocity,
            gate=gate,
            tempo=self._project.tempo,
            swing=swing,
            humanize_timing_ms=humanize_timing_ms,
            humanize_velocity=humanize_velocity,
            humanize_seed=humanize_seed,
        )
        clip_beats = self._project.timing.bars_to_quarter_notes(resolved_bars)
        resolved_pitch_bend_range = _pitch_bend_range(
            (
                self._pitch_bend_range
                if self._pitch_bend_range is not None
                else 2.0
                if pitch_bend_range is None
                else pitch_bend_range
            )
        )
        if (
            self._pitch_bend_range is not None
            and not math.isclose(
                resolved_pitch_bend_range, self._pitch_bend_range, rel_tol=0.0, abs_tol=1e-9
            )
        ):
            raise ProjectError(
                f"Track {self.name!r} already declares an effective pitch-bend range of "
                f"{self._pitch_bend_range:g} semitones; use the same range on every clip."
            )
        bends = _control_points(
            pitch_bend,
            label="Pitch bend",
            minimum=-resolved_pitch_bend_range,
            maximum=resolved_pitch_bend_range,
            clip_beats=clip_beats,
            curve=pitch_bend_curve,
        )
        modulation_points = _control_points(
            modulation,
            label="Modulation",
            minimum=0.0,
            maximum=1.0,
            clip_beats=clip_beats,
            curve=modulation_curve,
        )
        specification = _instrument_specification(preset, uniwave, external)
        self._add_clip(
            MidiClip(
                instrument=preset,
                uniwave=uniwave,
                notes=notation,
                events=events,
                pitch_bend=bends,
                modulation=modulation_points,
                pitch_bend_range=resolved_pitch_bend_range,
                pitch_bend_curve=pitch_bend_curve,
                modulation_curve=modulation_curve,
                bars=resolved_bars,
                velocity=velocity,
                waveform=None if uniwave is not None else waveform,
                attack_ms=None if uniwave is not None else attack_ms,
                decay_ms=None if uniwave is not None else decay_ms,
                sustain=None if uniwave is not None else sustain,
                release_ms=None if uniwave is not None else release_ms,
                cutoff_hz=None if uniwave is not None else cutoff_hz,
                gate=float(gate),
                gain_db=validate_gain(gain_db, label=f"MIDI track {self.name!r} clip gain"),
                swing=float(swing),
                humanize_timing_ms=float(humanize_timing_ms),
                humanize_velocity=humanize_velocity,
                humanize_seed=humanize_seed,
            ),
            section=section,
            start_bar=start_bar,
            repeat=repeat,
            instrument_specification=specification,
        )
        if self._pitch_bend_range is None:
            self._pitch_bend_range = resolved_pitch_bend_range
        if self._instrument is None:
            self._set_melodic_instrument(
                external or preset,
                name=None,
                specification=specification,
            )
        return self

    def instrument(
        self,
        preset: str | Uniwave | VST3,
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

        clip = self.clip
        if not isinstance(clip, MidiClip):
            raise ProjectError("instrument() follows midi() on the same track.")
        preset_name, uniwave, external = _resolve_instrument(
            preset,
            waveform=waveform,
            attack_ms=attack_ms,
            decay_ms=decay_ms,
            sustain=sustain,
            release_ms=release_ms,
            cutoff_hz=cutoff_hz,
        )
        if external is None:
            definition = STOCK_PLUGINS.get("instrument", preset_name)
            if not definition.melodic:
                raise ProjectError("MIDI instruments must be melodic stock instruments.")
        _waveform(waveform)
        _optional_range(attack_ms, 0.0, 5000.0, "Attack")
        _optional_range(decay_ms, 0.0, 5000.0, "Decay")
        _optional_range(sustain, 0.0, 1.0, "Sustain")
        _optional_range(release_ms, 0.0, 5000.0, "Release")
        _optional_range(cutoff_hz, 20.0, 20_000.0, "Cutoff")
        resolved_gain = clip.gain_db if gain_db is None else validate_gain(
            gain_db, label=f"Instrument {self.name!r} gain"
        )
        specification = _instrument_specification(preset_name, uniwave, external)
        updated_clips = [
            replace(
                placement,
                clip=replace(
                    placement.clip,
                    instrument=preset_name,
                    uniwave=uniwave,
                    waveform=None if uniwave is not None else waveform,
                    attack_ms=None if uniwave is not None else attack_ms,
                    decay_ms=None if uniwave is not None else decay_ms,
                    sustain=None if uniwave is not None else sustain,
                    release_ms=None if uniwave is not None else release_ms,
                    cutoff_hz=None if uniwave is not None else cutoff_hz,
                    gain_db=resolved_gain,
                ),
            )
            for placement in self._clips
            if isinstance(placement.clip, MidiClip)
        ]
        updated_clip = next(
            (placement.clip for placement in updated_clips if isinstance(placement.clip, MidiClip)),
            None,
        )
        assert isinstance(updated_clip, MidiClip)
        plugin = self._set_melodic_instrument(
            external or preset_name,
            name=name,
            clip=updated_clip,
            specification=specification,
        )
        self._clips = updated_clips
        return plugin

    def effect(
        self,
        preset: EffectPreset | VST3,
        *,
        name: str | None = None,
        **settings: float,
    ) -> Plugin:
        """Append one stock or registered VST3 effect after the instrument."""

        if not self._clips:
            raise ProjectError("Add MIDI, a drum, a sample, or audio before adding effects.")
        plugin = _chain_effect(
            self.effects,
            preset,
            name=name,
            channel=self.name,
            settings=settings,
            reserved=() if self._instrument is None else (self._instrument.name,),
        )
        self.effects.append(plugin)
        return plugin

    def send(self, bus: Bus, *, gain_db: float = -12.0) -> Send:
        """Send a post-fader copy of this track to a return bus."""

        if bus._project is not self._project or bus not in self._project.buses:
            raise ProjectError("A send bus must belong to the same project as its track.")
        if self.output_bus is bus:
            raise ProjectError(
                f"Track {self.name!r} already routes through bus {bus.name!r}; "
                "a send to the same bus would duplicate it."
            )
        if any(send.bus == bus.name for send in self.sends):
            raise ProjectError(
                f"Track {self.name!r} already has a send to bus {bus.name!r}."
            )
        send = Send(
            track=self.name,
            bus=bus.name,
            gain_db=validate_gain(gain_db, label=f"Send from {self.name!r} to {bus.name!r}"),
        )
        self.sends.append(send)
        return send

    def _set_melodic_instrument(
        self,
        preset: str | VST3,
        *,
        name: str | None,
        clip: MidiClip | None = None,
        specification: InstrumentSpecification | None = None,
    ) -> Plugin:
        source_clip = self.clip if clip is None else clip
        assert isinstance(source_clip, MidiClip)
        if isinstance(preset, VST3):
            plugin = vst3_plugin(
                preset,
                name=f"{self.name} Instrument" if name is None else _name(name, "Plugin"),
                track=self.name,
                kind="instrument",
                instance_id=self._instrument_instance_id,
            )
        else:
            settings: dict[str, object] = {}
            if source_clip.uniwave is not None:
                from prism.stock_plugins.uniwave import settings as uniwave_settings

                settings.update(uniwave_settings(source_clip.uniwave))
            else:
                settings.update(native_instrument_settings(preset))
            overrides = {
                "waveform": source_clip.waveform,
                "attack_ms": source_clip.attack_ms,
                "decay_ms": source_clip.decay_ms,
                "sustain": source_clip.sustain,
                "release_ms": source_clip.release_ms,
                "cutoff_hz": source_clip.cutoff_hz,
            }
            settings.update({key: value for key, value in overrides.items() if value is not None})
            settings["gain_db"] = source_clip.gain_db
            plugin = instrument_plugin(
                preset,
                name=f"{self.name} Instrument" if name is None else _name(name, "Plugin"),
                track=self.name,
                settings=settings,
                melodic=True,
                instance_id=self._instrument_instance_id,
            )
        effective_specification = preset if specification is None else specification
        self._replace_instrument(plugin, effective_specification)
        return plugin

    def _replace_instrument(
        self,
        plugin: Plugin,
        specification: InstrumentSpecification,
    ) -> None:
        previous = self._instrument
        if previous is not None:
            remapped: list[AutomationLane] = []
            for lane in self._project.automation_lanes:
                if lane.target is not previous:
                    remapped.append(lane)
                    continue
                parameter = plugin.automatable.get(lane.parameter)
                if plugin.vst3 is None and parameter is None:
                    raise ProjectError(
                        f"Cannot replace instrument on track {self.name!r}: automation "
                        f"{lane.name!r} targets parameter {lane.parameter!r}, which the "
                        "new instrument does not expose. Remove or retarget that lane "
                        "before replacing the instrument."
                    )
                if plugin.vst3 is not None:
                    # A replacement may expose a different set of indexed
                    # parameters.  If inspected metadata is available, reject
                    # an orphan before mutating the track; the live worker
                    # repeats this check for portable declarations without a
                    # metadata cache.
                    parameter_identity(plugin, lane.parameter)
                if parameter is not None and any(
                    point.value < parameter.minimum or point.value > parameter.maximum
                    for point in lane.points
                ):
                    raise ProjectError(
                        f"Cannot replace instrument on track {self.name!r}: automation "
                        f"{lane.name!r} contains values outside the new instrument's "
                        f"range for {lane.parameter!r}. Remove or retarget that lane "
                        "before replacing the instrument."
                    )
                remapped.append(replace(lane, target=plugin))
            self._project.automation_lanes = remapped
        self._instrument = plugin
        self._instrument_specification = specification

    def _check_instrument_compatibility(
        self,
        requested: InstrumentSpecification,
    ) -> None:
        existing = self._instrument_specification
        if existing is None or existing == requested:
            return
        if isinstance(existing, VST3) or isinstance(requested, VST3):
            if isinstance(existing, VST3) and isinstance(requested, VST3):
                differences: list[str] = []
                if existing.alias != requested.alias:
                    differences.append(f"alias {existing.alias!r} vs {requested.alias!r}")
                if existing.state != requested.state:
                    differences.append(f"state {existing.state!r} vs {requested.state!r}")
                if existing.preset != requested.preset:
                    differences.append(f"preset {existing.preset!r} vs {requested.preset!r}")
                if dict(existing.parameters) != dict(requested.parameters):
                    differences.append(
                        f"parameters {dict(existing.parameters)!r} vs "
                        f"{dict(requested.parameters)!r}"
                    )
                detail = "; ".join(differences) or "the VST3 configuration"
            else:
                detail = (
                    f"instrument type {type(existing).__name__} vs "
                    f"{type(requested).__name__}"
                )
            raise ProjectError(
                f"Track {self.name!r} owns one VST3 instrument instance, but this clip "
                f"requests an incompatible {detail}. Clips reuse the track-owned VST3 "
                "configuration; use song.automation(...) for timed parameter changes "
                "or a separate track for a different patch."
            )
        raise ProjectError(
            f"Track {self.name!r} already owns a different instrument configuration. "
            "Use track.instrument(...) to replace it for the whole track."
        )

    def _vst_clip_gain_db(self) -> float:
        """Return the common VST clip gain or reject independent scaling."""

        if self._instrument is None or self._instrument.vst3 is None:
            return 0.0
        gains = tuple(
            placement.clip.gain_db
            for placement in self._clips
            if isinstance(placement.clip, MidiClip)
        )
        if not gains:
            return 0.0
        common = gains[0]
        if all(math.isclose(value, common, rel_tol=0.0, abs_tol=1e-9) for value in gains[1:]):
            return common
        raise ProjectError(
            f"VST instrument track {self.name!r} has independently scaled MIDI clip gains "
            f"{gains!r}. One continuous polyphonic VST instance cannot preserve those gains "
            "for overlapping voices or release/internal-effect tails. Normalize every VST "
            "clip to one common gain (usually 0 dB) and use track.output_gain(...) for a "
            "shared output envelope, or move differently scaled parts to separate tracks."
        )

    def _validate_output_gain_lane(self, total_bars: int) -> None:
        lane = self._output_gain_lane
        if lane is not None and lane.points[-1].bar > total_bars:
            raise ProjectError(
                f"Output-gain lane {lane.name!r} ends at bar {lane.points[-1].bar:g}, "
                f"after the song's {total_bars} bars."
            )

    def _add_clip(
        self,
        clip: TrackClip,
        *,
        section: str | None,
        start_bar: float,
        repeat: bool,
        instrument_specification: InstrumentSpecification | None = None,
    ) -> None:
        if self._clips:
            first = self._clips[0].clip
            if type(first) is not type(clip):
                raise ProjectError(
                    f"Track {self.name!r} already has content of another type. "
                    "Use another track for a different instrument or player."
                )
            if isinstance(first, DrumClip) and isinstance(clip, DrumClip):
                if first.preset != clip.preset:
                    raise ProjectError("All drum clips on one track must use the same preset.")
            if isinstance(first, MidiClip) and isinstance(clip, MidiClip):
                if instrument_specification is not None:
                    self._check_instrument_compatibility(instrument_specification)
                if first.instrument != clip.instrument:
                    raise ProjectError(
                        "All MIDI clips on one track must use the same instrument."
                    )
                first_sound = (
                    first.uniwave,
                    first.waveform,
                    first.attack_ms,
                    first.decay_ms,
                    first.sustain,
                    first.release_ms,
                    first.cutoff_hz,
                )
                clip_sound = (
                    clip.uniwave,
                    clip.waveform,
                    clip.attack_ms,
                    clip.decay_ms,
                    clip.sustain,
                    clip.release_ms,
                    clip.cutoff_hz,
                )
                if first_sound != clip_sound:
                    raise ProjectError(
                        "All MIDI clips on one track must use the same synth settings. "
                        "Call instrument() once after adding the clips to change them together."
                    )
        clean_section = None if section is None else _name(section, "Clip section")
        self._clips.append(
            ClipPlacement(
                clip=clip,
                section=clean_section,
                start_bar=_start_bar(start_bar),
                repeat=bool(repeat),
            )
        )


class Bus:
    """A shared mixer channel for grouped tracks or parallel sends."""

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
        self.name = _name(name, "Bus")
        self.gain_db = validate_gain(gain_db, label=f"Bus {self.name!r} gain")
        self.pan = validate_pan(pan)
        self.muted = bool(muted)
        self.tracks: list[Track] = []
        self.effects: list[Plugin] = []

    def add(self, *tracks: Track) -> Self:
        """Route tracks through this bus before they reach the master."""

        if len({id(track) for track in tracks}) != len(tracks):
            raise ProjectError("A track can be listed only once when adding it to a bus.")
        for track in tracks:
            if track._project is not self._project:
                raise ProjectError("Bus tracks must belong to the same project as the bus.")
            if track.output_bus is not None and track.output_bus is not self:
                raise ProjectError(
                    f"Track {track.name!r} already routes through bus "
                    f"{track.output_bus.name!r}."
                )
            if track in self.tracks:
                raise ProjectError(
                    f"Track {track.name!r} is already in bus {self.name!r}."
                )
            if any(send.bus == self.name for send in track.sends):
                raise ProjectError(
                    f"Track {track.name!r} already sends to bus {self.name!r}; "
                    "remove that send before using the bus as its main output."
                )
        for track in tracks:
            track.output_bus = self
            self.tracks.append(track)
        return self

    def effect(
        self,
        preset: EffectPreset | VST3,
        *,
        name: str | None = None,
        **settings: float,
    ) -> Plugin:
        """Append a stock or registered VST3 effect to this bus."""

        plugin = _chain_effect(
            self.effects,
            preset,
            name=name,
            channel=f"Bus {self.name}",
            settings=settings,
        )
        self.effects.append(plugin)
        return plugin


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
        timing_compatibility: TimingCompatibility = CANONICAL_TIMING_VERSION,
        controller_boundary: ControllerBoundaryMode = "reset",
        automation_compatibility: str = CANONICAL_AUTOMATION_VERSION,
        audio_release_policy: AudioReleasePolicy = DEFAULT_AUDIO_RELEASE_POLICY,
        master_gain_db: float = -3.0,
        normalize: bool = True,
        _script: str | Path | None = None,
    ) -> None:
        self.script = _project_script(_script)
        self.root = self.script.parent
        self.samples = SampleLibrary(self.root)
        self.vsts = VSTRegistry(self.root)
        self.name = _name(name, "Project")
        self.prism_version = _version(prism_version)
        self.timing = MusicalTiming(
            tempo_bpm=tempo,
            sample_rate=sample_rate,
            time_signature=TimeSignature(
                numerator=beats_per_bar,
                denominator=beat_unit,
            ),
            compatibility=timing_compatibility,
        )
        if controller_boundary not in {"reset", "retain", "legacy"}:
            raise ProjectError(
                "Controller boundary must be 'reset', 'retain', or 'legacy'."
            )
        self.controller_boundary: ControllerBoundaryMode = controller_boundary
        self.automation_compatibility: AutomationCompatibility = _automation_compatibility(
            automation_compatibility
        )
        self.audio_release_policy = _audio_release_policy(
            audio_release_policy, "Project audio_release_policy"
        )
        self.tempo = self.timing.tempo_bpm
        self.sample_rate = self.timing.sample_rate
        self.beats_per_bar = self.timing.numerator
        self.beat_unit = self.timing.denominator
        self.master_gain_db = validate_gain(master_gain_db, label="Master gain")
        self.normalize = bool(normalize)
        self.tracks: list[Track] = []
        self.buses: list[Bus] = []
        self.master_effects: list[Plugin] = []
        self.sections: list[Section] = []
        self.automation_lanes: list[AutomationLane] = []

    @property
    def frames_per_bar(self) -> int:
        """Return one bar's frame length, rounded at the absolute boundary."""

        return self.timing.bars_to_frames(1)

    @property
    def quarter_notes_per_bar(self) -> float:
        """Return the configured bar length in canonical quarter-note beats."""

        return self.timing.quarter_notes_per_bar

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

    def bus(
        self,
        name: str,
        *,
        tracks: Sequence[Track] = (),
        gain_db: float = 0.0,
        pan: float = 0.0,
        muted: bool = False,
    ) -> Bus:
        """Create a group or return bus and optionally route tracks through it."""

        clean = _name(name, "Bus")
        if clean.casefold() == "master" or any(
            bus.name.casefold() == clean.casefold() for bus in self.buses
        ):
            raise ProjectError(f"Bus names must be unique; {clean!r} is already used.")
        bus = Bus(self, clean, gain_db=gain_db, pan=pan, muted=muted)
        bus.add(*tracks)
        self.buses.append(bus)
        return bus

    def master_effect(
        self,
        preset: EffectPreset | VST3,
        *,
        name: str | None = None,
        **settings: float,
    ) -> Plugin:
        """Append a stock or registered VST3 effect to the final master channel."""

        plugin = _chain_effect(
            self.master_effects,
            preset,
            name=name,
            channel="Master",
            settings=settings,
        )
        self.master_effects.append(plugin)
        return plugin

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
        requested_identity = parameter_identity(target, parameter)
        if any(
            lane.target is target
            and lane.parameter_identity.parameter_id == requested_identity.parameter_id
            for lane in self.automation_lanes
        ):
            raise ProjectError(
                f"Plugin {target.name!r} parameter {parameter!r} already has automation "
                f"for physical target {requested_identity.parameter_id!r}."
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
        section_by_name = {section.name: section for section in self.sections}
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
        for track in self.tracks:
            active_sections = [
                section
                for section in self.sections
                if section.tracks is None or track.name in section.tracks
            ]
            for placement in track.clips:
                if isinstance(placement.clip, SampleClip | AudioClip | DrumClip):
                    _optional_audio_release_policy(
                        placement.clip.release_policy,
                        f"Track {track.name!r} clip",
                    )
                if placement.section is not None:
                    target_section = section_by_name.get(placement.section)
                    if target_section is None:
                        raise ProjectError(
                            f"Track {track.name!r} has a clip for unknown section "
                            f"{placement.section!r}."
                        )
                    if (
                        target_section.tracks is not None
                        and track.name not in target_section.tracks
                    ):
                        raise ProjectError(
                            f"Track {track.name!r} has a clip for section "
                            f"{target_section.name!r}, "
                            "but that track is not active there."
                        )
                    if placement.start_bar >= target_section.bars:
                        raise ProjectError(
                            f"Track {track.name!r} clip starts at bar "
                            f"{placement.start_bar:g}, outside section "
                            f"{target_section.name!r}."
                        )
                elif active_sections and all(
                    placement.start_bar >= section.bars for section in active_sections
                ):
                    raise ProjectError(
                        f"Track {track.name!r} default clip starts after every active section."
                    )
        files = tuple(sorted(self._sample_files(), key=lambda path: path.as_posix().casefold()))
        for path in files:
            if not path.is_file():
                relative = path.relative_to(self.root)
                raise ProjectError(
                    f"Sample file is missing: {relative}. Put it inside the project folder."
                )
        verified_aliases: set[str] = set()
        for plugin in self._external_plugins():
            assert plugin.vst3 is not None
            if plugin.vst3.parameter_metadata:
                seen_parameters: set[str] = set()
                for selector in plugin.vst3.parameters:
                    identity = parameter_identity(plugin, selector)
                    if identity.parameter_id in seen_parameters:
                        raise ProjectError(
                            f"VST plugin {plugin.name!r} declares duplicate physical "
                            f"parameter target {identity.parameter_id!r}; use one selector."
                        )
                    seen_parameters.add(identity.parameter_id)
            if plugin.vst3.alias not in verified_aliases:
                self.vsts.resolve(plugin.vst3.alias)
                verified_aliases.add(plugin.vst3.alias)
            for state_relative in (plugin.vst3.state, plugin.vst3.preset):
                if state_relative is not None and not (
                    self.root / state_relative
                ).is_file():
                    raise ProjectError(
                        f"VST file is missing for {plugin.name!r}: {state_relative}."
                    )
        bars = sum(section.bars for section in self.sections)
        for track in self.tracks:
            track._validate_output_gain_lane(bars)
            track._vst_clip_gain_db()
        lane_targets: set[tuple[str, str]] = set()
        for lane in self.automation_lanes:
            if not self._owns_plugin(lane.target):
                raise ProjectError(
                    f"Automation {lane.name!r} targets a plugin that was replaced."
                )
            identity = lane.parameter_identity
            target_key = (identity.instance_id, identity.parameter_id)
            if target_key in lane_targets:
                raise ProjectError(
                    f"Automation {lane.name!r} duplicates physical parameter target "
                    f"{identity.parameter_id!r} on instance {identity.instance_id!r}."
                )
            lane_targets.add(target_key)
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
            duration_seconds=self.timing.bars_to_seconds(bars),
        )

    def render(
        self,
        output: str | Path = "renders/song.wav",
        *,
        bit_depth: Literal[16, 24, 32] = 16,
        channels: Literal["mono", "stereo"] = "stereo",
        sample_rate: int | None = None,
        tail_seconds: float = 0.0,
    ) -> RenderResult:
        """Render the arrangement with selectable WAV quality and effect tail."""

        from prism.render import render_project

        return render_project(
            self,
            output,
            bit_depth=bit_depth,
            channels=channels,
            sample_rate=sample_rate,
            tail_seconds=tail_seconds,
        )

    def render_stems(
        self,
        output: str | Path = "renders/stems",
        *,
        bit_depth: Literal[16, 24, 32] = 16,
        channels: Literal["mono", "stereo"] = "stereo",
        sample_rate: int | None = None,
        tail_seconds: float = 0.0,
    ) -> StemRenderResult:
        """Render aligned track, bus, and master WAV files into a generation.

        Track stems contain each track's instrument or audio, effects, gain,
        and pan. Bus stems contain their routed tracks and sends followed by
        the bus effects, gain, and pan. The master is identical to a normal
        :meth:`render` of the same project when given the same export options.
        The requested folder is a container; the returned result points to a
        versioned completed generation inside it.
        """

        from prism.render import render_stems

        return render_stems(
            self,
            output,
            bit_depth=bit_depth,
            channels=channels,
            sample_rate=sample_rate,
            tail_seconds=tail_seconds,
        )

    def export_midi(self, output: str | Path = "renders/song.mid") -> MidiResult:
        """Write built-in drum and MIDI tracks as a standard MIDI file."""

        from prism.midi import export_midi

        return export_midi(self, output)

    def compile_track_events(self, track: Track) -> CompiledTrackEvents:
        """Compile one track into the shared absolute musical event stream."""

        if track._project is not self:
            raise ProjectError("The track must belong to this project.")
        summary = self.validate()
        from prism.arrangement import compile_track_events

        return compile_track_events(
            self,
            track,
            total_bars=summary.bars,
            total_frames=self.timing.bar_to_frame(summary.bars),
        )

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
                    "output_bus": (
                        None if track.output_bus is None else track.output_bus.name
                    ),
                    "sends": [asdict(send) for send in track.sends],
                    "part": {"kind": _clip_kind(track.clip), **asdict(track.clip)},
                    "clips": [
                        {
                            "kind": _clip_kind(placement.clip),
                            "section": placement.section,
                            "start_bar": placement.start_bar,
                            "repeat": placement.repeat,
                            **asdict(placement.clip),
                        }
                        for placement in track.clips
                    ],
                    "instrument_instance_id": track.instrument_instance_id,
                    "instrument_specification": _instrument_specification_configuration(
                        track.instrument_specification,
                        track.instrument_plugin,
                    ),
                    "instrument": _plugin_configuration(track.instrument_plugin),
                    "output_gain": (
                        None
                        if track.output_gain_lane is None
                        else {
                            "name": track.output_gain_lane.name,
                            "curve": track.output_gain_lane.curve,
                            "points": [
                                asdict(point) for point in track.output_gain_lane.points
                            ],
                        }
                    ),
                    "effects": [_plugin_configuration(effect) for effect in track.effects],
                }
            )
        return {
            "schema_version": 11,
            "prism_version": self.prism_version,
            "name": self.name,
            "script": self.script.name,
            "tempo": self.tempo,
            "sample_rate": self.sample_rate,
            "time_signature": [self.beats_per_bar, self.beat_unit],
            "timing_compatibility": self.timing.compatibility,
            "quarter_notes_per_bar": self.timing.quarter_notes_per_bar,
            "controller_boundary": self.controller_boundary,
            "automation_compatibility": self.automation_compatibility,
            "audio_release_policy": self.audio_release_policy,
            "master_gain_db": self.master_gain_db,
            "normalize": self.normalize,
            "sample_folders": self.samples.folders,
            "vst3": [
                {
                    "alias": entry.alias,
                    "platform": entry.platform,
                    "sha256": entry.sha256,
                }
                for alias in dict.fromkeys(
                    plugin.preset for plugin in self._external_plugins()
                )
                for _path, entry in (self.vsts.resolve(alias),)
            ],
            "tracks": tracks,
            "buses": [
                {
                    "name": bus.name,
                    "gain_db": bus.gain_db,
                    "pan": bus.pan,
                    "muted": bus.muted,
                    "tracks": [track.name for track in bus.tracks],
                    "effects": [
                        _plugin_configuration(effect) for effect in bus.effects
                    ],
                }
                for bus in self.buses
            ],
            "master_effects": [
                _plugin_configuration(effect) for effect in self.master_effects
            ],
            "sections": [asdict(section) for section in self.sections],
            "automation": [
                {
                    "name": lane.name,
                    "track": lane.target.track,
                    "target": lane.target.name,
                    "parameter": lane.parameter,
                    "instance_id": lane.parameter_identity.instance_id,
                    "parameter_id": lane.parameter_identity.parameter_id,
                    "resolved_selector": lane.parameter_identity.selector,
                    "curve": lane.curve,
                    "points": [asdict(point) for point in lane.points],
                }
                for lane in self.automation_lanes
            ],
        }

    def _owns_plugin(self, plugin: Plugin) -> bool:
        track_plugin = any(
            track.instrument_plugin is plugin or any(effect is plugin for effect in track.effects)
            for track in self.tracks
        )
        bus_plugin = any(any(effect is plugin for effect in bus.effects) for bus in self.buses)
        return track_plugin or bus_plugin or any(
            effect is plugin for effect in self.master_effects
        )

    def _external_plugins(self) -> tuple[Plugin, ...]:
        plugins = [
            plugin
            for track in self.tracks
            for plugin in (
                *((track.instrument_plugin,) if track.instrument_plugin is not None else ()),
                *track.effects,
            )
            if plugin.vst3 is not None
        ]
        plugins.extend(
            effect
            for bus in self.buses
            for effect in bus.effects
            if effect.vst3 is not None
        )
        plugins.extend(effect for effect in self.master_effects if effect.vst3 is not None)
        return tuple(plugins)

    def _source_name(self, value: str | Path) -> str:
        return self.samples.find(value)

    def _output_path(self, value: str | Path, *, suffix: str) -> Path:
        path = Path(value)
        if _unsafe_project_path(value):
            raise ProjectError("Output paths must be relative to the project folder.")
        if path.suffix.casefold() != suffix:
            raise ProjectError(f"Output must use the {suffix} extension: {path}")
        candidate = self.root / path
        _reject_symlink_path(candidate, self.root, "Output")
        resolved = (self.root / path).resolve(strict=False)
        try:
            resolved.relative_to(self.root)
        except ValueError as error:
            raise ProjectError("Output paths must stay inside the project folder.") from error
        if resolved == self.script:
            raise ProjectError("An output cannot overwrite the project script.")
        if resolved in self._protected_project_files():
            raise ProjectError("An output cannot overwrite a protected project file.")
        return resolved

    def _output_directory(self, value: str | Path) -> Path:
        path = Path(value)
        if _unsafe_project_path(value):
            raise ProjectError("Output folders must be relative to the project folder.")
        candidate = self.root / path
        _reject_symlink_path(candidate, self.root, "Output folder")
        resolved = (self.root / path).resolve(strict=False)
        try:
            resolved.relative_to(self.root)
        except ValueError as error:
            raise ProjectError("Output folders must stay inside the project folder.") from error
        if resolved == self.root:
            raise ProjectError("Choose an output folder inside the project folder.")
        protected = self._protected_project_files()
        if any(_paths_overlap(resolved, protected_path) for protected_path in protected):
            raise ProjectError(
                "A stem output folder cannot contain or replace a protected project file."
            )
        return resolved

    def _sample_files(self) -> set[Path]:
        paths: set[Path] = set()
        for track in self.tracks:
            for placement in track.clips:
                if isinstance(placement.clip, SampleClip | AudioClip):
                    paths.add((self.root / placement.clip.path).resolve(strict=False))
        return paths

    def _protected_project_files(self) -> set[Path]:
        """Return project files that no export operation may replace."""

        paths = {self.script, (self.root / "vst.json").resolve(strict=False)}
        paths.update(self._sample_files())
        for relative_file in self.samples.files():
            paths.add((self.root / relative_file).resolve(strict=False))

        for path in self.root.rglob("*.py"):
            if path.is_file():
                paths.add(path.resolve(strict=False))
        state_root = self.root / "plugin-states"
        if state_root.is_dir():
            paths.update(
                path.resolve(strict=False)
                for path in state_root.rglob("*")
                if path.is_file()
            )
        for plugin in self._external_plugins():
            assert plugin.vst3 is not None
            for state_relative in (plugin.vst3.state, plugin.vst3.preset):
                if state_relative is not None:
                    paths.add((self.root / state_relative).resolve(strict=False))
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
    configuration: dict[str, object] = {
        "name": plugin.name,
        "track": plugin.track,
        "kind": plugin.kind,
        "preset": plugin.preset,
        "settings": dict(plugin.settings),
    }
    if plugin.instance_id is not None:
        configuration["instance_id"] = plugin.instance_id
    if plugin.vst3 is not None:
        configuration["format"] = "vst3"
        configuration["external"] = {
            "alias": plugin.vst3.alias,
            "state": plugin.vst3.state,
            "preset": plugin.vst3.preset,
            "parameters": dict(plugin.vst3.parameters),
        }
    else:
        configuration["format"] = "stock"
    return configuration


def _instrument_specification_configuration(
    specification: InstrumentSpecification | None,
    plugin: Plugin | None,
) -> dict[str, object] | None:
    if specification is None:
        return None
    if isinstance(specification, VST3):
        return {
            "format": "vst3",
            "alias": specification.alias,
            "state": specification.state,
            "preset": specification.preset,
            "parameters": dict(specification.parameters),
        }
    if plugin is None:
        return {"format": "stock", "preset": specification}
    return {
        "format": "stock",
        "preset": plugin.preset,
        "settings": dict(plugin.settings),
    }


def _instrument_specification(
    preset: str,
    uniwave: Uniwave | None,
    external: VST3 | None,
) -> InstrumentSpecification:
    if external is not None:
        return external
    if uniwave is not None:
        return uniwave
    return preset


def _chain_effect(
    chain: Sequence[Plugin],
    preset: EffectPreset | VST3,
    *,
    name: str | None,
    channel: str,
    settings: dict[str, float],
    reserved: Sequence[str] = (),
) -> Plugin:
    preset_name = preset.alias if isinstance(preset, VST3) else preset
    base_name = (
        preset_name.replace("_", " ").title() if name is None else _name(name, "Plugin")
    )
    plugin_name = base_name
    suffix = 2
    used = {item.name.casefold() for item in chain}
    used.update(item.casefold() for item in reserved)
    while plugin_name.casefold() in used:
        plugin_name = f"{base_name} {suffix}"
        suffix += 1
    instance_id = f"{channel}:effect:{plugin_name}"
    if isinstance(preset, VST3):
        if settings:
            raise ProjectError("Put VST3 parameters inside VST3(parameters={...}).")
        return vst3_plugin(
            preset,
            name=plugin_name,
            track=channel,
            kind="effect",
            instance_id=instance_id,
        )
    return effect_plugin(
        preset,
        name=plugin_name,
        track=channel,
        settings=settings,
        instance_id=instance_id,
    )


def _name(value: str, label: str) -> str:
    clean = value.strip()
    if not clean:
        raise ProjectError(f"{label} name cannot be empty.")
    if len(clean) > 120:
        raise ProjectError(f"{label} name cannot exceed 120 characters.")
    return clean


def _start_bar(value: float) -> float:
    resolved = float(value)
    if not math.isfinite(resolved) or resolved < 0.0:
        raise ProjectError("Clip start_bar must be finite and zero or greater.")
    return resolved


def _version(value: str) -> str:
    clean = value.strip()
    if not clean or len(clean) > 64:
        raise ProjectError("Prism version must be a non-empty value from the project template.")
    return clean


def _automation_compatibility(value: str) -> AutomationCompatibility:
    aliases: dict[str, AutomationCompatibility] = {
        CANONICAL_AUTOMATION_VERSION: CANONICAL_AUTOMATION_VERSION,
        "canonical": CANONICAL_AUTOMATION_VERSION,
        "base_value": CANONICAL_AUTOMATION_VERSION,
        "initial_value": CANONICAL_AUTOMATION_VERSION,
        LEGACY_AUTOMATION_VERSION: LEGACY_AUTOMATION_VERSION,
        "legacy": LEGACY_AUTOMATION_VERSION,
        "legacy_first_point": LEGACY_AUTOMATION_VERSION,
    }
    clean = str(value).strip().casefold()
    try:
        return aliases[clean]
    except KeyError as error:
        choices = ", ".join((CANONICAL_AUTOMATION_VERSION, LEGACY_AUTOMATION_VERSION))
        raise ProjectError(
            f"automation_compatibility must be one of {choices}; got {value!r}."
        ) from error


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
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or not 1 <= value <= MAX_SYNTH_CLIP_BARS
    ):
        raise ProjectError(
            f"{label} bars must be an integer between 1 and {MAX_SYNTH_CLIP_BARS}."
        )
    return value


def _synth_bars(value: int, label: str, project: Project) -> int:
    bars = _bars(value, label)
    duration = project.timing.bars_to_seconds(bars)
    if duration > MAX_SYNTH_SECONDS:
        raise ProjectError(
            f"{label} cannot exceed {MAX_SYNTH_SECONDS:g} seconds; use fewer bars."
        )
    return bars


def _midi_notes(
    value: str | Sequence[str] | Sequence[Note],
    *,
    clip_beats: float,
    velocity: int,
    gate: float,
    tempo: float,
    swing: float,
    humanize_timing_ms: float,
    humanize_velocity: int,
    humanize_seed: int,
) -> tuple[tuple[str, ...], tuple[Note, ...]]:
    if not math.isfinite(swing) or not 0.5 <= swing <= 0.75:
        raise ProjectError("MIDI swing must be between 0.5 and 0.75.")
    if not math.isfinite(humanize_timing_ms) or not 0.0 <= humanize_timing_ms <= 50.0:
        raise ProjectError("MIDI humanize_timing_ms must be between 0 and 50.")
    if not isinstance(humanize_velocity, int) or not 0 <= humanize_velocity <= 30:
        raise ProjectError("MIDI humanize_velocity must be an integer between 0 and 30.")
    if not isinstance(humanize_seed, int) or not 0 <= humanize_seed <= 4_294_967_295:
        raise ProjectError("MIDI humanize_seed must be between 0 and 4294967295.")

    authored: tuple[Note, ...]
    if isinstance(value, str):
        notation = note_steps(value)
        authored = _step_notes(notation, clip_beats, velocity, gate)
    else:
        supplied = tuple(value)
        if supplied and all(isinstance(item, Note) for item in supplied):
            notation = ()
            authored = tuple(item for item in supplied if isinstance(item, Note))
        elif all(isinstance(item, str) for item in supplied):
            notation = note_steps(tuple(item for item in supplied if isinstance(item, str)))
            authored = _step_notes(notation, clip_beats, velocity, gate)
        else:
            raise ProjectError(
                "MIDI notes must be notation text or a non-empty list of Note objects."
            )
    if not authored:
        raise ProjectError("A MIDI clip needs at least one Note.")
    for note in authored:
        if note.start >= clip_beats or note.start + note.duration > clip_beats + 1e-9:
            raise ProjectError(
                f"Note {note.pitch!r} must start and finish inside the clip's "
                f"{clip_beats:g} beats."
            )
    return notation, _humanized_notes(
        authored,
        clip_beats=clip_beats,
        tempo=tempo,
        swing=swing,
        timing_ms=humanize_timing_ms,
        velocity_range=humanize_velocity,
        seed=humanize_seed,
    )


def _step_notes(
    notation: tuple[str, ...], clip_beats: float, velocity: int, gate: float
) -> tuple[Note, ...]:
    step = clip_beats / len(notation)
    return tuple(
        Note(pitch, index * step, step * gate, velocity)
        for index, token in enumerate(notation)
        if token != "-"
        for pitch in token.split("+")
    )


def _humanized_notes(
    notes: tuple[Note, ...],
    *,
    clip_beats: float,
    tempo: float,
    swing: float,
    timing_ms: float,
    velocity_range: int,
    seed: int,
) -> tuple[Note, ...]:
    generator = random.Random(seed)
    maximum_jitter = timing_ms * tempo / 60_000.0
    timing_by_start: dict[float, float] = {}
    resolved: list[Note] = []
    for note in notes:
        if note.start not in timing_by_start:
            timing_by_start[note.start] = generator.uniform(-maximum_jitter, maximum_jitter)
        fraction = note.start - math.floor(note.start)
        swing_delay = swing - 0.5 if math.isclose(fraction, 0.5, abs_tol=1e-9) else 0.0
        start = note.start + swing_delay + timing_by_start[note.start]
        start = min(max(0.0, start), clip_beats - note.duration)
        velocity = note.velocity + generator.randint(-velocity_range, velocity_range)
        resolved.append(
            Note(note.pitch, start, note.duration, min(127, max(1, velocity)))
        )
    return tuple(resolved)


def _control_points(
    values: Sequence[tuple[float, float]],
    *,
    label: str,
    minimum: float,
    maximum: float,
    clip_beats: float,
    curve: ControlCurve,
) -> tuple[ControlPoint, ...]:
    if curve not in {"linear", "hold"}:
        raise ProjectError(f"{label} curve must be 'linear' or 'hold'.")
    points: list[ControlPoint] = []
    previous = -1.0
    for beat, value in values:
        resolved_beat = float(beat)
        resolved_value = float(value)
        if (
            not math.isfinite(resolved_beat)
            or resolved_beat < 0.0
            or resolved_beat > clip_beats
        ):
            raise ProjectError(
                f"{label} positions must be between 0 and {clip_beats:g} clip beats."
            )
        if resolved_beat <= previous:
            raise ProjectError(f"{label} positions must be in strictly increasing order.")
        if not math.isfinite(resolved_value) or not minimum <= resolved_value <= maximum:
            raise ProjectError(
                f"{label} values must be between {minimum:g} and {maximum:g}."
            )
        points.append(ControlPoint(resolved_beat, resolved_value, curve))
        previous = resolved_beat
    return tuple(points)


def _pitch_bend_range(value: float) -> float:
    try:
        resolved = float(value)
    except (TypeError, ValueError) as error:
        raise ProjectError(
            "pitch_bend_range must be a finite value between 0.01 and 96 semitones."
        ) from error
    if not math.isfinite(resolved) or not 0.01 <= resolved <= 96.0:
        raise ProjectError(
            "pitch_bend_range must be a finite value between 0.01 and 96 semitones."
        )
    return resolved


def _optional_range(value: float | None, low: float, high: float, label: str) -> None:
    if value is not None and (not math.isfinite(value) or not low <= value <= high):
        raise ProjectError(f"{label} must be between {low:g} and {high:g}.")


def _audio_editing(
    *,
    start_seconds: float,
    end_seconds: float | None,
    fade_in_ms: float,
    fade_out_ms: float,
    reverse: bool,
    playback_rate: float,
    transpose_semitones: int,
    stretch_bars: float | None,
) -> _AudioEditing:
    """Validate and normalize deterministic source-editing options."""

    _finite_range(start_seconds, 0.0, math.inf, "Audio start_seconds")
    if end_seconds is not None:
        _finite_range(end_seconds, 0.0, math.inf, "Audio end_seconds")
        if end_seconds <= start_seconds:
            raise ProjectError("Audio end_seconds must be greater than start_seconds.")
    _finite_range(fade_in_ms, 0.0, 60_000.0, "Audio fade_in_ms")
    _finite_range(fade_out_ms, 0.0, 60_000.0, "Audio fade_out_ms")
    _finite_range(playback_rate, 0.25, 4.0, "Audio playback_rate")
    if not isinstance(transpose_semitones, int) or not -24 <= transpose_semitones <= 24:
        raise ProjectError("Audio transpose_semitones must be an integer between -24 and 24.")
    if stretch_bars is not None:
        _finite_range(stretch_bars, 0.25, 256.0, "Audio stretch_bars")
    result: _AudioEditing = {
        "start_seconds": float(start_seconds),
        "end_seconds": None if end_seconds is None else float(end_seconds),
        "fade_in_ms": float(fade_in_ms),
        "fade_out_ms": float(fade_out_ms),
        "reverse": bool(reverse),
        "playback_rate": float(playback_rate),
        "transpose_semitones": transpose_semitones,
        "stretch_bars": None if stretch_bars is None else float(stretch_bars),
    }
    return result


def _audio_release_policy(value: str, label: str) -> AudioReleasePolicy:
    """Validate one explicit sample/audio voice lifetime policy."""

    if value not in {"natural", "cut", "choke", "legacy"}:
        raise ProjectError(
            f"{label} must be 'natural', 'cut', 'choke', or 'legacy'."
        )
    return value  # type: ignore[return-value]


def _optional_audio_release_policy(
    value: AudioReleasePolicy | None,
    label: str,
) -> AudioReleasePolicy | None:
    """Validate an optional per-placement policy that inherits at render time."""

    if value is None:
        return None
    return _audio_release_policy(value, f"{label} release_policy")


def _finite_range(value: float, low: float, high: float, label: str) -> None:
    if not math.isfinite(value) or value < low or value > high:
        high_text = "any finite value" if math.isinf(high) else f"between {low:g} and {high:g}"
        raise ProjectError(f"{label} must be {high_text}.")


def _waveform(value: SynthWaveform | None) -> None:
    if value not in {None, "sine", "triangle", "saw", "square"}:
        raise ProjectError("Waveform must be sine, triangle, saw, or square.")


def _resolve_instrument(
    value: str | Uniwave | VST3,
    *,
    waveform: SynthWaveform | None,
    attack_ms: float | None,
    decay_ms: float | None,
    sustain: float | None,
    release_ms: float | None,
    cutoff_hz: float | None,
) -> tuple[str, Uniwave | None, VST3 | None]:
    overrides = (waveform, attack_ms, decay_ms, sustain, release_ms, cutoff_hz)
    if isinstance(value, VST3):
        if any(item is not None for item in overrides):
            raise ProjectError("Put VST3 settings inside VST3(parameters={...}).")
        return value.alias, None, value
    if isinstance(value, Uniwave):
        if any(item is not None for item in overrides):
            raise ProjectError(
                "Configure waveform, envelope, and cutoff inside the Uniwave object."
            )
        return "uniwave", value, None
    if value != "uniwave":
        return value, None, None
    sound = Uniwave()
    if waveform is not None:
        sound = replace(sound, waves=(replace(sound.waves[0], waveform=waveform),))
    return "uniwave", replace(
        sound,
        attack_ms=sound.attack_ms if attack_ms is None else attack_ms,
        decay_ms=sound.decay_ms if decay_ms is None else decay_ms,
        sustain=sound.sustain if sustain is None else sustain,
        release_ms=sound.release_ms if release_ms is None else release_ms,
        cutoff_hz=sound.cutoff_hz if cutoff_hz is None else cutoff_hz,
    ), None


def _unsafe_project_path(value: str | Path) -> bool:
    """Recognize absolute paths and traversal using either platform's syntax."""

    raw = str(value)
    posix = PurePosixPath(raw)
    windows = PureWindowsPath(raw)
    return (
        posix.is_absolute()
        or bool(windows.drive)
        or bool(windows.root)
        or ".." in posix.parts
        or ".." in windows.parts
    )


def _paths_overlap(left: Path, right: Path) -> bool:
    """Return whether either path is the other path or one of its descendants."""

    return _is_same_or_child(left, right) or _is_same_or_child(right, left)


def _is_same_or_child(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def _reject_symlink_path(path: Path, root: Path, label: str) -> None:
    """Reject symlink components before resolving a project-local destination."""

    try:
        relative = path.relative_to(root)
    except ValueError as error:
        raise ProjectError(f"{label} must stay inside the project folder.") from error
    current = root
    for part in relative.parts:
        current /= part
        if current.is_symlink():
            raise ProjectError(f"{label} cannot pass through a symlink: {current}")


__all__ = [
    "Project",
    "ProjectSummary",
    "Section",
    "Track",
]

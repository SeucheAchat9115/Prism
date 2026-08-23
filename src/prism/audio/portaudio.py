"""PortAudio-backed real-time output with a non-blocking callback."""

from __future__ import annotations

import time
from collections import deque
from concurrent.futures import Future
from concurrent.futures import TimeoutError as FutureTimeoutError
from dataclasses import dataclass
from queue import Full, Queue
from threading import Event, Lock, RLock, Thread, current_thread
from typing import Any
from uuid import UUID

import numpy as np
import sounddevice as sd

from prism.audio.errors import (
    AudioBackendError,
    AudioCallbackError,
    AudioCommandTimeoutError,
    AudioConfigurationError,
    AudioDeviceError,
    AudioRuntimeError,
    AudioStateError,
)
from prism.audio.ring import AudioRingBuffer
from prism.audio.types import (
    AudioBackendConfig,
    AudioBackendSnapshot,
    AudioBackendState,
    AudioCommandName,
    AudioDeviceInfo,
    AudioErrorInfo,
)
from prism.engine import EngineError, EngineEvent, SessionEngine
from prism.engine.sources import ClipSourceProvider
from prism.engine.types import ScheduledAction
from prism.project.models import Project

_COMMAND_QUEUE_CAPACITY = 64
_PREFILL_BLOCKS = 2
_MONITOR_INTERVAL_SECONDS = 0.01


@dataclass(slots=True)
class _ControlRequest:
    name: AudioCommandName
    args: tuple[object, ...]
    future: Future[object]


def list_output_devices() -> tuple[AudioDeviceInfo, ...]:
    """Return stereo-capable output devices known to PortAudio."""

    try:
        raw_devices = sd.query_devices()
        raw_hostapis = sd.query_hostapis()
    except Exception as exc:
        raise AudioDeviceError(f"Could not query PortAudio output devices: {exc}") from exc

    devices: list[AudioDeviceInfo] = []
    for index, raw_device in enumerate(raw_devices):
        max_channels = int(raw_device.get("max_output_channels", 0))
        if max_channels < 2:
            continue
        host_api_index = int(raw_device.get("hostapi", -1))
        if 0 <= host_api_index < len(raw_hostapis):
            host_api = str(raw_hostapis[host_api_index].get("name", "unknown"))
        else:
            host_api = "unknown"
        devices.append(
            AudioDeviceInfo(
                index=index,
                name=str(raw_device.get("name", f"Output device {index}")),
                host_api=host_api,
                max_output_channels=max_channels,
                default_sample_rate=float(raw_device.get("default_samplerate", 0.0)),
            )
        )
    return tuple(devices)


class PortAudioBackend:
    """Threaded real-time backend using a PortAudio output stream."""

    def __init__(
        self,
        project: Project,
        sources: ClipSourceProvider,
        *,
        config: AudioBackendConfig | None = None,
    ) -> None:
        self._config = config or AudioBackendConfig()
        if (
            self._config.sample_rate is not None
            and self._config.sample_rate != project.transport.sample_rate
        ):
            raise AudioConfigurationError(
                "Audio backend sample_rate must match the project's transport sample_rate"
            )
        try:
            self._engine = SessionEngine(project, sources)
        except EngineError as exc:
            raise AudioConfigurationError(f"Project cannot start audio playback: {exc}") from exc

        self._ring = AudioRingBuffer(self._config.block_size, self._config.queue_blocks)
        self._commands: Queue[_ControlRequest] = Queue(maxsize=_COMMAND_QUEUE_CAPACITY)
        self._wake = Event()
        self._shutdown = Event()
        self._prefilled = Event()
        self._lifecycle_lock = RLock()
        self._state_lock = Lock()
        self._state = AudioBackendState.STOPPED
        self._snapshot = self._engine.snapshot()
        self._events: list[EngineEvent] = []
        self._device: AudioDeviceInfo | None = None
        self._stream: Any | None = None
        self._muted = True
        self._produce_enabled = False
        self._underrun_count = 0
        self._underrun_times: deque[float] = deque()
        self._reported_underrun_count = 0
        self._last_error: AudioErrorInfo | None = None
        self._callback_fault_code: str | None = None
        self._worker_fault: tuple[str, str] | None = None
        self._closed = False

        self._worker = Thread(
            target=self._worker_loop,
            name="prism-audio-producer",
            daemon=True,
        )
        self._monitor = Thread(
            target=self._monitor_loop,
            name="prism-audio-monitor",
            daemon=True,
        )
        self._worker.start()
        self._monitor.start()

    @property
    def config(self) -> AudioBackendConfig:
        """Return the immutable stream configuration."""

        return self._config

    def start(self) -> None:
        """Open the selected device if needed and start or resume playback."""

        with self._lifecycle_lock:
            self._require_operable()
            if self._state == AudioBackendState.RUNNING:
                return
            if self._state == AudioBackendState.STARTING:
                raise AudioStateError("Audio backend is already starting")
            if self._state not in (AudioBackendState.STOPPED, AudioBackendState.PAUSED):
                raise AudioStateError(f"Cannot start audio backend from state {self._state}")

            self._set_state(AudioBackendState.STARTING)
            self._muted = True
            try:
                if self._stream is None:
                    self._open_stream()
                self._prefilled.clear()
                self._submit("play")
                self._wait_for_prefill()
                stream = self._stream
                if stream is None:
                    raise AudioDeviceError("Audio stream disappeared before playback started")
                stream.start()
                self._muted = False
                self._set_state(AudioBackendState.RUNNING)
            except AudioDeviceError as exc:
                self._muted = True
                self._close_stream_safely()
                self._set_fault("device_open_failed", str(exc))
                raise
            except AudioBackendError as exc:
                self._muted = True
                self._close_stream_safely()
                self._set_fault("start_failed", str(exc))
                raise
            except Exception as exc:
                self._muted = True
                self._close_stream_safely()
                self._set_fault("start_failed", f"Audio backend could not start playback: {exc}")
                raise AudioDeviceError(f"Could not start audio playback: {exc}") from exc

    def pause(self) -> None:
        """Pause transport and emit silence while retaining the open stream."""

        with self._lifecycle_lock:
            self._require_operable()
            if self._state == AudioBackendState.PAUSED:
                return
            if self._state == AudioBackendState.STARTING:
                raise AudioStateError("Cannot pause audio backend while it is starting")
            self._muted = True
            self._submit("pause")
            self._set_state(AudioBackendState.PAUSED)

    def stop(self) -> None:
        """Stop transport and release the output device without closing the backend."""

        with self._lifecycle_lock:
            self._require_operable()
            if self._state == AudioBackendState.STOPPED and self._stream is None:
                self._submit("stop")
                return
            self._muted = True
            self._submit("stop")
            self._close_stream_safely()
            self._set_state(AudioBackendState.STOPPED)

    def reset(self) -> None:
        """Stop transport, release the device, and return to frame zero."""

        with self._lifecycle_lock:
            self._require_operable()
            self._muted = True
            self._submit("reset")
            self._close_stream_safely()
            self._set_state(AudioBackendState.STOPPED)

    def launch_slot(self, track_id: UUID, scene_id: UUID) -> ScheduledAction:
        """Forward a slot launch through the producer-owned engine."""

        self._require_commandable()
        result = self._submit("launch_slot", track_id, scene_id)
        assert isinstance(result, ScheduledAction)
        return result

    def launch_scene(self, scene_id: UUID) -> ScheduledAction:
        """Forward a scene launch through the producer-owned engine."""

        self._require_commandable()
        result = self._submit("launch_scene", scene_id)
        assert isinstance(result, ScheduledAction)
        return result

    def stop_track(self, track_id: UUID) -> ScheduledAction:
        """Forward a track stop through the producer-owned engine."""

        self._require_commandable()
        result = self._submit("stop_track", track_id)
        assert isinstance(result, ScheduledAction)
        return result

    def stop_all(self) -> ScheduledAction:
        """Forward a stop-all command through the producer-owned engine."""

        self._require_commandable()
        result = self._submit("stop_all")
        assert isinstance(result, ScheduledAction)
        return result

    def update_mixer(self, project: Project) -> None:
        """Apply mixer values on the producer thread without rebuilding audio."""

        self._require_commandable()
        self._submit("update_mixer", project)

    def replace_project(self, project: Project, sources: ClipSourceProvider) -> None:
        """Replace the producer engine while retaining compatible runtime state."""

        self._require_commandable()
        self._submit("replace_project", project, sources)

    def drain_events(self) -> tuple[EngineEvent, ...]:
        """Take actual engine transitions on the producer thread."""

        self._require_commandable()
        result = self._submit("drain_events")
        assert isinstance(result, tuple)
        return result

    def snapshot(self) -> AudioBackendSnapshot:
        """Return the latest producer/device snapshot without blocking the callback."""

        with self._state_lock:
            return AudioBackendSnapshot(
                state=self._state,
                engine_snapshot=self._snapshot,
                device=self._device,
                underrun_count=self._underrun_count,
                last_error=self._last_error,
                queued_latency_frames=self._ring.queued_blocks * self._ring.block_size,
            )

    def close(self) -> None:
        """Stop all threads and release the stream; safe to call repeatedly."""

        with self._lifecycle_lock:
            if self._closed:
                return
            self._muted = True
            self._produce_enabled = False
            self._shutdown.set()
            self._wake.set()
            self._close_stream_safely()
            self._closed = True
            self._set_state(AudioBackendState.CLOSED)

        if self._worker is not current_thread():
            self._worker.join(timeout=self._config.control_timeout_seconds)
        if self._monitor is not current_thread():
            self._monitor.join(timeout=self._config.control_timeout_seconds)
        alive = [
            thread.name
            for thread in (self._worker, self._monitor)
            if thread is not current_thread() and thread.is_alive()
        ]
        if alive:
            with self._state_lock:
                self._last_error = AudioErrorInfo(
                    code="shutdown_timeout",
                    message=f"Audio threads did not terminate in time: {', '.join(alive)}",
                    recoverable=False,
                )

    def __enter__(self) -> "PortAudioBackend":
        self._require_operable()
        return self

    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> None:
        self.close()

    def _open_stream(self) -> None:
        self._device = _resolve_output_device(self._config.device)
        if self._device.max_output_channels < 2:
            raise AudioDeviceError(
                f"Output device {self._device.name!r} does not provide stereo output"
            )
        try:
            self._stream = sd.OutputStream(
                samplerate=self._engine.project.transport.sample_rate,
                blocksize=self._config.block_size,
                device=self._device.index,
                channels=2,
                dtype="float32",
                callback=self._callback,
            )
        except Exception as exc:
            self._stream = None
            raise AudioDeviceError(
                f"Could not open output device {self._device.name!r}: {exc}"
            ) from exc

    def _submit(self, name: AudioCommandName, *args: object) -> object:
        if self._shutdown.is_set():
            raise AudioStateError("Audio backend worker is shut down")
        future: Future[object] = Future()
        request = _ControlRequest(name=name, args=args, future=future)
        try:
            self._commands.put_nowait(request)
        except Full as exc:
            raise AudioCommandTimeoutError("Audio backend command queue is full") from exc
        self._wake.set()
        try:
            return future.result(timeout=self._config.control_timeout_seconds)
        except FutureTimeoutError as exc:
            raise AudioCommandTimeoutError(
                f"Audio backend command {name!r} did not complete in time"
            ) from exc

    def _worker_loop(self) -> None:
        while not self._shutdown.is_set():
            self._drain_commands()
            if self._shutdown.is_set():
                break
            if self._produce_enabled:
                if self._ring.queued_blocks >= self._ring.capacity:
                    self._wake.wait(0.002)
                    self._wake.clear()
                    continue
                try:
                    step = self._engine.advance(self._ring.block_size)
                except Exception as exc:
                    self._worker_fault = ("worker_error", str(exc))
                    self._produce_enabled = False
                    self._wake.wait(0.01)
                    self._wake.clear()
                    continue
                if not self._ring.try_write(step.samples):
                    continue
                self._events.extend(step.events)
                self._snapshot = self._engine.snapshot()
                if self._ring.queued_blocks >= min(_PREFILL_BLOCKS, self._ring.capacity - 1):
                    self._prefilled.set()
                continue
            self._wake.wait(0.01)
            self._wake.clear()

        while True:
            try:
                request = self._commands.get_nowait()
            except Exception:
                break
            if not request.future.done():
                request.future.set_exception(AudioStateError("Audio backend worker is shut down"))

    def _drain_commands(self) -> None:
        while True:
            try:
                request = self._commands.get_nowait()
            except Exception:
                return
            try:
                result = self._apply_command(request.name, request.args)
            except EngineError as exc:
                request.future.set_exception(exc)
            except Exception as exc:
                request.future.set_exception(exc)
                self._worker_fault = ("worker_error", str(exc))
                self._produce_enabled = False
            else:
                self._snapshot = self._engine.snapshot()
                request.future.set_result(result)

    def _apply_command(self, name: AudioCommandName, args: tuple[object, ...]) -> object:
        if name == "play":
            self._engine.play()
            self._ring.invalidate()
            self._produce_enabled = True
            self._prefilled.clear()
            return None
        if name == "pause":
            self._engine.pause()
            self._ring.invalidate()
            self._produce_enabled = False
            return None
        if name == "stop":
            self._engine.stop()
            self._ring.invalidate()
            self._produce_enabled = False
            return None
        if name == "reset":
            self._engine.reset()
            self._ring.invalidate()
            self._produce_enabled = False
            return None
        if name == "launch_slot":
            return self._engine.launch_slot(args[0], args[1])  # type: ignore[arg-type]
        if name == "launch_scene":
            return self._engine.launch_scene(args[0])  # type: ignore[arg-type]
        if name == "stop_track":
            return self._engine.stop_track(args[0])  # type: ignore[arg-type]
        if name == "stop_all":
            return self._engine.stop_all()
        if name == "update_mixer":
            self._engine.update_mixer(args[0])  # type: ignore[arg-type]
            return None
        if name == "replace_project":
            self._engine = self._engine.reconfigured(
                args[0],  # type: ignore[arg-type]
                args[1],  # type: ignore[arg-type]
            )
            self._ring.invalidate()
            return None
        events = (*self._events, *self._engine.drain_events())
        self._events.clear()
        return events

    def _wait_for_prefill(self) -> None:
        deadline = time.monotonic() + self._config.control_timeout_seconds
        while not self._prefilled.is_set():
            if self._callback_fault_code is not None:
                raise AudioCallbackError("PortAudio callback faulted while pre-filling audio")
            if self._worker_fault is not None:
                raise AudioRuntimeError(self._worker_fault[1])
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise AudioRuntimeError("Audio producer could not pre-fill the output ring")
            self._prefilled.wait(min(remaining, 0.01))

    def _callback(
        self,
        outdata: np.ndarray,
        frames: int,
        time_info: object,
        status: object,
    ) -> None:
        del time_info
        try:
            had_underrun = bool(
                status is not None and getattr(status, "output_underflow", False)
            )
            underrun = self._ring.read_into(outdata, muted=self._muted)
            if underrun and not self._muted:
                had_underrun = True
            if had_underrun:
                self._underrun_count += 1
                self._underrun_times.append(time.monotonic())
        except Exception:
            outdata.fill(0.0)
            self._callback_fault_code = "callback_exception"
        del frames

    def _monitor_loop(self) -> None:
        while not self._shutdown.is_set():
            if self._callback_fault_code is not None:
                self._set_fault(
                    self._callback_fault_code,
                    "PortAudio callback reported an output fault",
                )
                self._muted = True
                self._produce_enabled = False
                self._close_stream_safely()
            elif self._underrun_count != self._reported_underrun_count:
                self._reported_underrun_count = self._underrun_count
                now = time.monotonic()
                cutoff = now - self._config.underrun_window_seconds
                while self._underrun_times and self._underrun_times[0] < cutoff:
                    self._underrun_times.popleft()
                if len(self._underrun_times) >= self._config.underrun_fault_count:
                    self._set_fault(
                        "output_underflow",
                        (
                            "PortAudio exceeded the recoverable underrun threshold "
                            f"({self._config.underrun_fault_count} within "
                            f"{self._config.underrun_window_seconds:g}s)"
                        ),
                    )
                    self._muted = True
                    self._produce_enabled = False
                    self._close_stream_safely()
                else:
                    with self._state_lock:
                        self._last_error = AudioErrorInfo(
                            code="output_underflow",
                            message=(
                                "An isolated output underrun was recovered; playback continues"
                            ),
                            recoverable=True,
                        )
            elif self._worker_fault is not None:
                code, message = self._worker_fault
                self._set_fault(code, f"Audio producer failed: {message}")
                self._muted = True
                self._produce_enabled = False
                self._close_stream_safely()
            self._shutdown.wait(_MONITOR_INTERVAL_SECONDS)

    def _require_operable(self) -> None:
        if self._closed or self._state == AudioBackendState.CLOSED:
            raise AudioStateError("Audio backend is closed")
        if self._state == AudioBackendState.FAULTED:
            raise AudioStateError(
                "Audio backend is faulted; close it before creating a new backend"
            )

    def _require_commandable(self) -> None:
        with self._state_lock:
            state = self._state
        if state in (AudioBackendState.CLOSED, AudioBackendState.FAULTED):
            raise AudioStateError(f"Cannot issue audio command while backend is {state}")

    def _set_state(self, state: AudioBackendState) -> None:
        with self._state_lock:
            self._state = state

    def _set_fault(self, code: str, message: str) -> None:
        with self._state_lock:
            if self._state == AudioBackendState.CLOSED:
                return
            self._state = AudioBackendState.FAULTED
            self._last_error = AudioErrorInfo(code=code, message=message)

    def _close_stream_safely(self) -> None:
        stream = self._stream
        self._stream = None
        if stream is None:
            return
        try:
            stream.stop()
        except Exception:
            pass
        try:
            stream.close()
        except Exception:
            pass


def _resolve_output_device(device: int | str | None) -> AudioDeviceInfo:
    devices = list_output_devices()
    if not devices:
        raise AudioDeviceError("No stereo-capable output devices are available")
    if device is None:
        try:
            default_devices = sd.default.device
            default_index = int(default_devices[1])
        except (TypeError, ValueError, IndexError):
            default_index = -1
        if default_index >= 0:
            for item in devices:
                if item.index == default_index:
                    return item
        try:
            default_info = sd.query_devices(None, "output")
            default_name = str(default_info.get("name", ""))
        except Exception as exc:
            raise AudioDeviceError(f"Could not resolve the default output device: {exc}") from exc
        matches = [item for item in devices if item.name == default_name]
        if len(matches) == 1:
            return matches[0]
        raise AudioDeviceError("The PortAudio default output device is unavailable")
    if isinstance(device, int):
        for item in devices:
            if item.index == device:
                return item
        raise AudioDeviceError(f"Stereo output device index {device} is unavailable")
    matches = [item for item in devices if item.name == device]
    if len(matches) != 1:
        raise AudioDeviceError(f"Stereo output device name {device!r} is unavailable or ambiguous")
    return matches[0]

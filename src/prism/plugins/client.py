"""Bounded controller for the persistent isolated plugin subprocess."""

from __future__ import annotations

import os
import queue
import subprocess
import sys
from collections.abc import Mapping
from multiprocessing import shared_memory
from pathlib import Path
from threading import RLock, Thread
from typing import Any, Literal, NoReturn
from uuid import UUID, uuid4

import numpy as np
from pydantic import ValidationError

from prism.plugins.errors import (
    PluginUnavailableError,
    PluginWorkerError,
    PluginWorkerTimeoutError,
)
from prism.plugins.protocol import WorkerRequest, WorkerResponse
from prism.plugins.types import PluginParameter, PluginWorkerStatus


class PluginWorkerClient:
    """Serialize requests to one worker and kill it whenever a boundary is violated."""

    def __init__(
        self,
        *,
        timeout_seconds: float = 10.0,
        discovery_timeout_seconds: float = 15.0,
        command: tuple[str, ...] | None = None,
    ) -> None:
        self.timeout_seconds = timeout_seconds
        self.discovery_timeout_seconds = discovery_timeout_seconds
        self.command = command or (sys.executable, "-m", "prism.plugins.worker")
        self._process: subprocess.Popen[str] | None = None
        self._responses: queue.Queue[str | None] = queue.Queue()
        self._stderr: list[str] = []
        self._lock = RLock()
        self._restart_count = 0
        self._last_error: str | None = None

    def status(self) -> PluginWorkerStatus:
        process = self._process
        if process is None:
            state: Literal["stopped", "failed"] = (
                "failed" if self._last_error else "stopped"
            )
            return PluginWorkerStatus(
                state=state,
                restart_count=self._restart_count,
                last_error=self._last_error,
            )
        if process.poll() is None:
            return PluginWorkerStatus(
                state="ready",
                pid=process.pid,
                restart_count=self._restart_count,
                last_error=self._last_error,
            )
        return PluginWorkerStatus(
            state="failed",
            restart_count=self._restart_count,
            last_error=self._last_error or self._stderr_tail(),
        )

    def start(self) -> None:
        if self._process is not None and self._process.poll() is None:
            return
        self._responses = queue.Queue()
        self._stderr = []
        creationflags = 0
        if os.name == "nt":
            creationflags = subprocess.CREATE_NO_WINDOW
        try:
            self._process = subprocess.Popen(
                self.command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                bufsize=1,
                creationflags=creationflags,
            )
        except OSError as error:
            self._last_error = str(error)
            raise PluginWorkerError(f"Could not start the plugin worker: {error}") from error
        assert self._process.stdout is not None
        assert self._process.stderr is not None
        responses = self._responses
        stderr_lines = self._stderr
        Thread(
            target=self._read_stdout,
            args=(self._process.stdout, responses),
            name="prism-plugin-worker-out",
            daemon=True,
        ).start()
        Thread(
            target=self._read_stderr,
            args=(self._process.stderr, stderr_lines),
            name="prism-plugin-worker-err",
            daemon=True,
        ).start()
        try:
            self._request("ping", {}, timeout=self.discovery_timeout_seconds)
        except Exception:
            self.stop()
            raise

    def stop(self) -> None:
        process = self._process
        self._process = None
        if process is None:
            return
        if process.poll() is None:
            try:
                process.terminate()
                process.wait(timeout=1.0)
            except (OSError, subprocess.TimeoutExpired):
                process.kill()
                process.wait(timeout=1.0)

    def restart(self) -> PluginWorkerStatus:
        self.stop()
        self._restart_count += 1
        self._last_error = None
        self.start()
        return self.status()

    def close(self) -> None:
        try:
            if self._process is not None and self._process.poll() is None:
                self._request("shutdown", {}, timeout=1.0)
        except PluginWorkerError:
            pass
        finally:
            self.stop()

    def probe(self, path: Path | str) -> list[dict[str, str]]:
        result = self._request(
            "probe",
            {"path": str(Path(path).resolve(strict=True))},
            timeout=self.discovery_timeout_seconds,
        )
        plugins = result.get("plugins")
        if not isinstance(plugins, list):
            raise PluginWorkerError("Plugin worker returned malformed probe metadata")
        return [dict(item) for item in plugins if isinstance(item, dict)]

    def load(
        self,
        instance_id: UUID,
        path: Path | str,
        plugin_identifier: str,
        *,
        sample_rate: int,
        parameters: Mapping[str, float] | None = None,
        state: bytes | None = None,
        bypassed: bool = False,
    ) -> list[PluginParameter]:
        import base64

        result = self._request(
            "load",
            {
                "instance_id": str(instance_id),
                "path": str(Path(path).resolve(strict=True)),
                "plugin_identifier": plugin_identifier,
                "sample_rate": sample_rate,
                "parameters": dict(parameters or {}),
                "state": None if state is None else base64.b64encode(state).decode("ascii"),
                "bypassed": bypassed,
            },
        )
        return [PluginParameter.model_validate(item) for item in result.get("parameters", [])]

    def parameters(self, instance_id: UUID) -> list[PluginParameter]:
        result = self._request("parameters", {"instance_id": str(instance_id)})
        return [PluginParameter.model_validate(item) for item in result.get("parameters", [])]

    def set_parameter(self, instance_id: UUID, parameter_id: str, raw_value: float) -> None:
        self._request(
            "set_parameter",
            {
                "instance_id": str(instance_id),
                "parameter_id": parameter_id,
                "raw_value": raw_value,
            },
        )

    def set_bypass(self, instance_id: UUID, bypassed: bool) -> None:
        self._request(
            "set_bypass",
            {"instance_id": str(instance_id), "bypassed": bypassed},
        )

    def get_state(self, instance_id: UUID, *, max_bytes: int) -> bytes:
        import base64

        result = self._request(
            "get_state",
            {"instance_id": str(instance_id), "max_bytes": max_bytes},
        )
        value = result.get("state")
        if not isinstance(value, str):
            raise PluginWorkerError("Plugin worker returned malformed opaque state")
        return base64.b64decode(value, validate=True)

    def unload(self, instance_id: UUID) -> None:
        self._request("unload", {"instance_id": str(instance_id)})

    def process(
        self,
        instance_id: UUID,
        samples: np.ndarray,
        sample_rate: int,
        *,
        reset: bool = False,
    ) -> np.ndarray:
        audio = np.ascontiguousarray(samples, dtype=np.float32)
        if audio.ndim != 2 or audio.shape[1] not in (1, 2):
            raise ValueError("Plugin audio must be shaped as frames x mono/stereo channels")
        if audio.size == 0:
            return audio.copy()
        memory = shared_memory.SharedMemory(create=True, size=audio.nbytes)
        try:
            shared = np.ndarray(audio.shape, dtype=np.float32, buffer=memory.buf)
            shared[:] = audio
            self._request(
                "process",
                {
                    "instance_id": str(instance_id),
                    "shared_memory": memory.name,
                    "frames": audio.shape[0],
                    "channels": audio.shape[1],
                    "sample_rate": sample_rate,
                    "reset": reset,
                },
            )
            return shared.copy()
        finally:
            memory.close()
            memory.unlink()

    def _request(
        self,
        method: str,
        params: dict[str, Any],
        *,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        with self._lock:
            if method != "ping":
                self.start()
            process = self._process
            if process is None or process.poll() is not None or process.stdin is None:
                message = self._stderr_tail() or "Plugin worker is not running"
                self._last_error = message
                raise PluginWorkerError(message)
            request = WorkerRequest(
                request_id=uuid4().hex,
                method=method,
                params=params,
            )
            try:
                process.stdin.write(request.model_dump_json() + "\n")
                process.stdin.flush()
            except (BrokenPipeError, OSError) as error:
                self._fail_worker(f"Plugin worker pipe failed: {error}")
            try:
                line = self._responses.get(timeout=timeout or self.timeout_seconds)
            except queue.Empty:
                message = f"Plugin worker timed out during {method}"
                self._fail_worker(message, timeout=True)
            if line is None:
                self._fail_worker(self._stderr_tail() or "Plugin worker exited unexpectedly")
            try:
                response = WorkerResponse.model_validate_json(line)
            except ValidationError as error:
                self._fail_worker(f"Plugin worker returned malformed JSON: {error}")
            if response.request_id != request.request_id:
                self._fail_worker("Plugin worker response ID did not match the request")
            if not response.ok:
                failure = response.error
                message = failure.message if failure else "Plugin worker rejected the request"
                if failure and failure.code == "host_unavailable":
                    raise PluginUnavailableError(message)
                raise PluginWorkerError(message)
            return response.result or {}

    def _fail_worker(self, message: str, *, timeout: bool = False) -> NoReturn:
        self._last_error = message
        self.stop()
        if timeout:
            raise PluginWorkerTimeoutError(message)
        raise PluginWorkerError(message)

    @staticmethod
    def _read_stdout(stream: Any, responses: queue.Queue[str | None]) -> None:
        try:
            for line in stream:
                responses.put(line)
        finally:
            responses.put(None)

    @staticmethod
    def _read_stderr(stream: Any, stderr_lines: list[str]) -> None:
        for line in stream:
            stderr_lines.append(line.rstrip())
            if len(stderr_lines) > 50:
                del stderr_lines[:10]

    def _stderr_tail(self) -> str:
        return "\n".join(self._stderr[-10:]).strip()

    def __enter__(self) -> "PluginWorkerClient":
        self.start()
        return self

    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> None:
        self.close()

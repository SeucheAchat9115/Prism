"""Inspect PortAudio devices and optionally play a generated clip.

This example is intentionally opt-in and is not part of the device-free test
suite. Run it only when a stereo output device is available.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time

from _support import make_memory_fixture

from prism.audio import AudioBackendConfig, PortAudioBackend, list_output_devices
from prism.audio.errors import AudioBackendError


def _device_value(value: str) -> int | str:
    return int(value) if value.isdigit() else value


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Inspect stereo PortAudio devices and optionally play a generated clip."
    )
    parser.add_argument(
        "--device",
        help="Optional exact device index or name; defaults to the OS PortAudio device.",
    )
    parser.add_argument(
        "--play-seconds",
        type=float,
        default=0.0,
        help="If positive, play the generated clip for this many seconds.",
    )
    args = parser.parse_args()
    if args.play_seconds < 0:
        parser.error("--play-seconds must not be negative")

    doctor = subprocess.run(
        [sys.executable, "-m", "prism", "doctor"],
        check=False,
        capture_output=True,
        text=True,
    )
    if doctor.returncode != 0:
        print(doctor.stderr or doctor.stdout)
        return doctor.returncode
    print(doctor.stdout.strip())

    try:
        devices = list_output_devices()
    except AudioBackendError as error:
        print(f"Could not query output devices: {error}")
        return 1
    print("Stereo-capable output devices:")
    for device in devices:
        print(
            f"  [{device.index}] {device.name} ({device.host_api}) "
            f"default_rate={device.default_sample_rate:g}"
        )
    if not devices:
        print("No stereo-capable PortAudio output devices were found.")
        return 1 if args.play_seconds > 0 else 0
    if args.play_seconds == 0:
        print("Diagnostics complete. Pass --play-seconds to test playback.")
        return 0

    project, provider, track, scene, _ = make_memory_fixture(
        sample_rate=44100,
        seconds=max(args.play_seconds, 1.0),
        quantization="none",
        loop=True,
    )
    config = AudioBackendConfig(device=_device_value(args.device) if args.device else None)
    backend: PortAudioBackend | None = None
    try:
        backend = PortAudioBackend(project, provider, config=config)
        action = backend.launch_slot(track.id, scene.id)
        backend.start()
        print(
            f"Playing until frame {action.target_frame} was scheduled; "
            f"listening for {args.play_seconds:g}s."
        )
        time.sleep(args.play_seconds)
        print(f"Backend snapshot: {backend.snapshot()}")
        backend.stop()
        return 0
    except AudioBackendError as error:
        print(f"PortAudio playback failed: {error}")
        if backend is not None:
            print(f"Backend snapshot: {backend.snapshot()}")
        return 1
    finally:
        if backend is not None:
            backend.close()


if __name__ == "__main__":
    raise SystemExit(main())

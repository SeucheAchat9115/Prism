"""Play a generated clip through a real PortAudio output device.

This example is intentionally opt-in and is not part of the device-free test
suite. Run it only when a stereo output device is available.
"""

from __future__ import annotations

import argparse
import time

from _support import make_memory_fixture

from vibesound.audio import AudioBackendConfig, PortAudioBackend, list_output_devices
from vibesound.audio.errors import AudioBackendError


def _device_value(value: str) -> int | str:
    return int(value) if value.isdigit() else value


def main() -> int:
    parser = argparse.ArgumentParser(description="Play a generated clip through PortAudio.")
    parser.add_argument(
        "--device",
        help="Optional exact device index or name; defaults to the OS PortAudio device.",
    )
    parser.add_argument("--seconds", type=float, default=3.0, help="Playback time.")
    args = parser.parse_args()
    if args.seconds <= 0:
        parser.error("--seconds must be positive")

    try:
        devices = list_output_devices()
    except AudioBackendError as error:
        print(f"Could not query output devices: {error}")
        return 1
    if not devices:
        print("No stereo-capable PortAudio output devices were found.")
        return 1

    print("Stereo-capable output devices:")
    for device in devices:
        print(f"  [{device.index}] {device.name} ({device.host_api})")

    project, provider, track, scene, _ = make_memory_fixture(
        sample_rate=44100,
        seconds=max(args.seconds, 1.0),
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
            f"listening for {args.seconds:g}s."
        )
        time.sleep(args.seconds)
        print(backend.snapshot())
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

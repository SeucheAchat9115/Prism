"""Create the synthetic demo and open the opt-in Phase 7 browser session."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the blocking local Prism browser session until Ctrl+C.",
    )
    parser.add_argument(
        "path",
        type=Path,
        nargs="?",
        default=Path(__file__).resolve().parent / "output" / "browser-demo.prism-work",
        help="Demo working-project directory.",
    )
    parser.add_argument("--host", default="127.0.0.1", help="Loopback bind address.")
    parser.add_argument("--port", type=int, default=8765, help="Local service port.")
    parser.add_argument(
        "--no-open",
        action="store_true",
        help="Print the URL without asking the system browser to open it.",
    )
    args = parser.parse_args()

    command = [
        sys.executable,
        "-m",
        "prism",
        "demo",
        str(args.path),
        "--host",
        args.host,
        "--port",
        str(args.port),
    ]
    if not args.no_open:
        command.append("--open")
    print("Starting the local session; press Ctrl+C here to stop Prism.")
    return subprocess.call(command)


if __name__ == "__main__":
    raise SystemExit(main())

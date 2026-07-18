"""Command-line entrypoint for the metadata pipeline."""

from __future__ import annotations

import argparse
import platform
import sys
from collections.abc import Sequence

from metadata_pipeline import __version__

MINIMUM_PYTHON = (3, 9)


def build_parser() -> argparse.ArgumentParser:
    """Build the top-level command parser."""
    parser = argparse.ArgumentParser(
        prog="metadata",
        description="Manage the ClickHouse metadata review pipeline.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )

    commands = parser.add_subparsers(dest="command")
    commands.add_parser(
        "doctor",
        help="Check whether the local runtime meets project requirements.",
    )
    return parser


def run_doctor() -> int:
    """Check the Python runtime and return a process-compatible status code."""
    current = sys.version_info[:2]
    supported = current >= MINIMUM_PYTHON
    status = "ok" if supported else "unsupported"
    minimum = ".".join(str(part) for part in MINIMUM_PYTHON)

    print(f"python={platform.python_version()} status={status} minimum={minimum}")
    return 0 if supported else 1


def main(argv: Sequence[str] | None = None) -> int:
    """Execute the CLI and return an exit code without terminating the interpreter."""
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "doctor":
        return run_doctor()

    parser.print_help()
    return 0


def entrypoint() -> None:
    """Console-script adapter."""
    raise SystemExit(main())


if __name__ == "__main__":
    entrypoint()

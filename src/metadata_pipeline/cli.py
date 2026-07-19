"""Command-line entrypoint for the metadata pipeline."""

from __future__ import annotations

import argparse
import platform
import sys
from collections.abc import Sequence
from pathlib import Path

from metadata_pipeline import __version__
from metadata_pipeline.application.review_contract import (
    export_review_json_schema,
    validate_review_directory,
)

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
    export_schema = commands.add_parser(
        "export-review-schema",
        help="Generate JSON Schema from the Pydantic reviewer contract.",
    )
    export_schema.add_argument(
        "--output",
        type=Path,
        default=Path("schemas/reviewer_metadata.schema.json"),
    )
    validate_review = commands.add_parser(
        "validate-review",
        help="Validate reviewer metadata against raw tbls schema.json.",
    )
    validate_review.add_argument(
        "--schema",
        type=Path,
        default=Path("schema/raw/commerce_demo/schema.json"),
    )
    validate_review.add_argument(
        "--review-dir",
        type=Path,
        default=Path("metadata/review/commerce_demo"),
    )
    validate_review.add_argument(
        "--contract",
        type=Path,
        default=Path("config/metadata_contract.yml"),
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


def run_validate_review(schema: Path, review_dir: Path, contract: Path) -> int:
    """Print actionable review issues and return a CI-compatible status."""
    issues = validate_review_directory(schema, review_dir, contract)
    for issue in issues:
        print(
            f"{issue.path}:{issue.field}: {issue.code}: {issue.message}",
            file=sys.stderr,
        )
    if issues:
        print(f"review metadata validation failed: {len(issues)} issue(s)", file=sys.stderr)
        return 1
    print(f"review metadata validation passed: {review_dir}")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """Execute the CLI and return an exit code without terminating the interpreter."""
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "doctor":
        return run_doctor()
    if args.command == "export-review-schema":
        export_review_json_schema(args.output)
        print(f"review JSON Schema written: {args.output}")
        return 0
    if args.command == "validate-review":
        return run_validate_review(args.schema, args.review_dir, args.contract)

    parser.print_help()
    return 0


def entrypoint() -> None:
    """Console-script adapter."""
    raise SystemExit(main())


if __name__ == "__main__":
    entrypoint()

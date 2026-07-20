"""YAML adapter for database catalog profiles."""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import ValidationError

from metadata_pipeline.domain.catalog import DatabaseProfile


class DatabaseProfileError(ValueError):
    """Raised when a database profile cannot be loaded safely."""


def load_database_profile(path: Path) -> DatabaseProfile:
    """Parse one strict database profile from YAML."""
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise DatabaseProfileError(f"database profile not found: {path}") from error
    except (OSError, yaml.YAMLError) as error:
        raise DatabaseProfileError(f"unable to read database profile {path}: {error}") from error
    try:
        return DatabaseProfile.model_validate(payload)
    except ValidationError as error:
        details = "; ".join(
            f"{'.'.join(str(part) for part in issue['loc']) or '$'}: {issue['msg']}"
            for issue in error.errors()
        )
        raise DatabaseProfileError(f"invalid database profile {path}: {details}") from error

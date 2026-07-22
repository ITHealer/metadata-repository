"""Shared loading for local dotenv overrides and CI-provided environment values."""

from __future__ import annotations

import os
from collections.abc import Mapping

from dotenv import find_dotenv, load_dotenv


def load_runtime_environment(
    environ: Mapping[str, str] | None = None,
) -> Mapping[str, str]:
    """Load the nearest ``.env`` without replacing values exported by the runtime."""
    if environ is not None:
        return environ
    dotenv_path = find_dotenv(usecwd=True)
    if dotenv_path:
        load_dotenv(dotenv_path=dotenv_path, override=False)
    return os.environ

"""Atomic byte writer for generated artifacts that may not always be UTF-8 text."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path


def write_bytes_if_changed(path: Path, content: bytes) -> bool:
    """Atomically write changed bytes and return whether the destination changed."""
    try:
        if path.read_bytes() == content:
            return False
    except FileNotFoundError:
        pass

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary.write(content)
            temporary.flush()
            os.fsync(temporary.fileno())
            temporary_path = Path(temporary.name)
        os.replace(temporary_path, path)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
    return True

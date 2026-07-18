"""Tests for the foundation CLI."""

from __future__ import annotations

import pytest

from metadata_pipeline import __version__
from metadata_pipeline.cli import main


def test_cli_shows_version(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as error:
        main(["--version"])

    assert error.value.code == 0
    assert capsys.readouterr().out.strip() == f"metadata {__version__}"


def test_cli_doctor_accepts_supported_python(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["doctor"]) == 0

    output = capsys.readouterr().out
    assert "status=ok" in output
    assert "minimum=3.9" in output


def test_cli_without_command_prints_help(capsys: pytest.CaptureFixture[str]) -> None:
    assert main([]) == 0
    assert "Manage the ClickHouse metadata review pipeline" in capsys.readouterr().out

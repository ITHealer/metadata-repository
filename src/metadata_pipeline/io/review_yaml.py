"""YAML file adapters for reviewer-owned metadata."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TypeVar

import yaml
from pydantic import ValidationError

from metadata_pipeline.domain.review import ReviewContractConfig, ReviewDocument
from metadata_pipeline.io.atomic_text import write_text_if_changed

ModelT = TypeVar("ModelT", ReviewDocument, ReviewContractConfig)


class _IndentedSafeDumper(yaml.SafeDumper):
    """Keep block-list indentation aligned with reviewer-authored YAML."""

    def increase_indent(self, flow: bool = False, indentless: bool = False) -> None:
        return super().increase_indent(flow, False)


@dataclass(frozen=True)
class ReviewParseIssue:
    """One actionable YAML or Pydantic parsing problem."""

    field: str
    message: str


class ReviewFileError(ValueError):
    """Raised when a review or contract file cannot be parsed."""

    def __init__(self, path: Path, issues: tuple[ReviewParseIssue, ...]) -> None:
        super().__init__(f"{path}: invalid reviewer metadata")
        self.path = path
        self.issues = issues


def load_review_document(path: Path) -> ReviewDocument:
    """Load one reviewer YAML file into the strict Pydantic contract."""
    return _load_model(path, ReviewDocument)


def load_review_contract(path: Path) -> ReviewContractConfig:
    """Load the canonical review contract version settings."""
    return _load_model(path, ReviewContractConfig)


def dump_review_document(review: ReviewDocument) -> str:
    """Serialize reviewer metadata to stable, human-readable YAML."""
    return yaml.dump(
        review.model_dump(mode="json"),
        Dumper=_IndentedSafeDumper,
        allow_unicode=True,
        default_flow_style=False,
        sort_keys=False,
        width=100,
    )


def write_review_document(path: Path, review: ReviewDocument) -> bool:
    """Atomically write changed reviewer YAML and return whether bytes changed."""
    return write_text_if_changed(path, dump_review_document(review))


def _load_model(path: Path, model_type: type[ModelT]) -> ModelT:
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise ReviewFileError(path, (ReviewParseIssue("$", "file not found"),)) from error
    except yaml.YAMLError as error:
        raise ReviewFileError(path, (ReviewParseIssue("$", f"invalid YAML: {error}"),)) from error
    except OSError as error:
        raise ReviewFileError(
            path, (ReviewParseIssue("$", f"unable to read file: {error}"),)
        ) from error

    try:
        return model_type.model_validate(payload)
    except ValidationError as error:
        issues = tuple(
            ReviewParseIssue(
                ".".join(str(part) for part in item["loc"]) or "$",
                str(item["msg"]),
            )
            for item in error.errors()
        )
        raise ReviewFileError(path, issues) from error

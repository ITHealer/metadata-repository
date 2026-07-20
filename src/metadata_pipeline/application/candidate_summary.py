"""Reviewer-facing Markdown summary for generated candidate artifacts."""

from __future__ import annotations

from pathlib import Path

from metadata_pipeline.io.candidate_json import CandidateFileError, load_candidate
from metadata_pipeline.io.review_yaml import ReviewFileError, load_review_document


class CandidateSummaryError(ValueError):
    """Raised when a reviewer summary cannot be built from committed artifacts."""


def render_candidate_summary(
    *,
    repository_root: Path,
    database: str,
    review_dir: Path,
    structured_dir: Path,
    published_dir: Path,
    repository_url: str = "",
) -> str:
    """Render links, lifecycle state, and candidate hash for every reviewer YAML."""
    rows = []
    for review_path in sorted((*review_dir.glob("*.yml"), *review_dir.glob("*.yaml"))):
        try:
            review = load_review_document(review_path)
            candidate_path = structured_dir / f"{review.table}.json"
            candidate = load_candidate(candidate_path)
        except (ReviewFileError, CandidateFileError) as error:
            raise CandidateSummaryError(str(error)) from error
        published_path = published_dir / f"{review.table}.md"
        rows.append(
            (
                review.table,
                review.document_status.value,
                candidate.state.value,
                candidate.candidate_hash[:12],
                _link(repository_root, review_path, "YAML", repository_url),
                _link(repository_root, published_path, "Markdown", repository_url),
            )
        )
    if not rows:
        raise CandidateSummaryError(f"no reviewer YAML found in {review_dir}")
    lines = [
        f"### Metadata candidates: `{database}`",
        "",
        "| Table | Review status | Candidate state | Candidate hash | Input | Preview |",
        "|---|---|---|---|---|---|",
    ]
    lines.extend(
        f"| `{table}` | `{status}` | `{state}` | `{candidate_hash}` | "
        f"{review_link} | {preview_link} |"
        for table, status, state, candidate_hash, review_link, preview_link in rows
    )
    lines.extend(
        (
            "",
            "Reviewer action: edit only YAML. Read the generated Markdown; when it is correct, "
            "change only `document_status` to `approved` and commit.",
        )
    )
    return "\n".join(lines) + "\n"


def _link(repository_root: Path, path: Path, label: str, repository_url: str) -> str:
    try:
        relative = path.resolve().relative_to(repository_root.resolve()).as_posix()
    except ValueError as error:
        raise CandidateSummaryError(f"artifact is outside repository root: {path}") from error
    if repository_url:
        return f"[{label}]({repository_url.rstrip('/')}/{relative})"
    return f"`{relative}`"

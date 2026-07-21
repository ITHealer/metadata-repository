"""Pure path classification for metadata Pull Request automation."""

from __future__ import annotations

from dataclasses import dataclass
from fnmatch import fnmatch

GENERATION_SOURCE_PATTERNS = (
    "src/metadata_pipeline/application/publish_metadata.py",
    "src/metadata_pipeline/adapters/generator/deterministic.py",
    "src/metadata_pipeline/domain/published.py",
    "src/metadata_pipeline/io/published_markdown.py",
)
INPUT_PATTERNS = (
    "config/databases/**",
    "catalog/*/generated/raw/**",
    "catalog/*/review/**",
    "prompts/**",
    "guidelines/**",
    "contracts/metadata_contract.yml",
    *GENERATION_SOURCE_PATTERNS,
)
GENERATED_OUTPUT_PATTERNS = (
    "catalog/*/generated/structured/**",
    "catalog/*/generated/published/**",
)


@dataclass(frozen=True)
class ChangedPath:
    """One normalized Git name-status entry."""

    status: str
    path: str
    previous_path: str = ""

    @property
    def all_paths(self) -> tuple[str, ...]:
        """Include both sides of a rename so policy cannot be bypassed."""
        return tuple(path for path in (self.path, self.previous_path) if path)


@dataclass(frozen=True)
class ChangeClassification:
    """Stable booleans and counts consumed by GitHub Actions."""

    total: int
    input_count: int
    generation_source_count: int
    published_count: int
    unrelated_count: int

    @property
    def has_inputs(self) -> bool:
        return self.input_count > 0

    @property
    def has_published(self) -> bool:
        return self.published_count > 0

    @property
    def has_generation_sources(self) -> bool:
        return self.generation_source_count > 0

    @property
    def only_published(self) -> bool:
        return self.total > 0 and self.published_count == self.total

    def github_outputs(self, prefix: str = "") -> dict[str, str]:
        """Return lowercase values accepted by the GITHUB_OUTPUT protocol."""
        return {
            f"{prefix}total": str(self.total),
            f"{prefix}input_count": str(self.input_count),
            f"{prefix}generation_source_count": str(self.generation_source_count),
            f"{prefix}published_count": str(self.published_count),
            f"{prefix}unrelated_count": str(self.unrelated_count),
            f"{prefix}has_inputs": str(self.has_inputs).lower(),
            f"{prefix}has_generation_sources": str(self.has_generation_sources).lower(),
            f"{prefix}has_published": str(self.has_published).lower(),
            f"{prefix}only_published": str(self.only_published).lower(),
        }


def classify_changed_paths(changes: tuple[ChangedPath, ...]) -> ChangeClassification:
    """Classify each change once, giving protected published output precedence."""
    input_count = 0
    generation_source_count = 0
    published_count = 0
    unrelated_count = 0
    for change in changes:
        paths = change.all_paths
        if any(
            any(_matches(path, pattern) for pattern in GENERATED_OUTPUT_PATTERNS) for path in paths
        ):
            published_count += 1
        elif any(any(_matches(path, pattern) for pattern in INPUT_PATTERNS) for path in paths):
            input_count += 1
            if any(
                any(_matches(path, pattern) for pattern in GENERATION_SOURCE_PATTERNS)
                for path in paths
            ):
                generation_source_count += 1
        else:
            unrelated_count += 1
    return ChangeClassification(
        total=len(changes),
        input_count=input_count,
        generation_source_count=generation_source_count,
        published_count=published_count,
        unrelated_count=unrelated_count,
    )


def _matches(path: str, pattern: str) -> bool:
    normalized = path.removeprefix("./")
    return fnmatch(normalized, pattern)

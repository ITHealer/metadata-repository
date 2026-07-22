"""Database-aware catalog layout resolution and scope validation."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from metadata_pipeline.adapters.schema.tbls_json import TblsSchemaSource
from metadata_pipeline.domain.catalog import DatabaseProfile
from metadata_pipeline.io.database_profile import load_database_profile
from metadata_pipeline.ports.schema_source import SchemaSourceError


class CatalogConfigurationError(ValueError):
    """Raised when a profile, path, or raw schema violates the catalog boundary."""


@dataclass(frozen=True)
class CatalogLayout:
    """All repository paths derived from one stable lowercase database key."""

    repository_root: Path
    database: str

    @property
    def profile_dir(self) -> Path:
        return self.repository_root / "config" / "databases" / self.database

    @property
    def profile_path(self) -> Path:
        return self.profile_dir / "database.yml"

    @property
    def tbls_config_path(self) -> Path:
        return self.profile_dir / "tbls.yml"

    @property
    def database_root(self) -> Path:
        return self.repository_root / "catalog" / self.database

    @property
    def raw_dir(self) -> Path:
        return self.database_root / "generated" / "raw"

    @property
    def schema_path(self) -> Path:
        return self.raw_dir / "schema.json"

    @property
    def review_dir(self) -> Path:
        return self.database_root / "review"

    @property
    def structured_dir(self) -> Path:
        return self.database_root / "generated" / "structured"

    @property
    def published_dir(self) -> Path:
        return self.database_root / "generated" / "published"

    @property
    def chunk_output(self) -> Path:
        return self.repository_root / "build" / "chunks" / f"{self.database}.jsonl"


@dataclass(frozen=True)
class CatalogContext:
    """Validated profile and its deterministic repository layout."""

    profile: DatabaseProfile
    layout: CatalogLayout


def load_catalog_context(database: str, repository_root: Path = Path(".")) -> CatalogContext:
    """Load one profile and ensure its declared key matches its directory name."""
    layout = CatalogLayout(repository_root.resolve(), database)
    profile = load_database_profile(layout.profile_path)
    if profile.key != database:
        raise CatalogConfigurationError(
            f"database profile key {profile.key!r} does not match directory {database!r}"
        )
    if profile.enabled and not layout.tbls_config_path.is_file():
        raise CatalogConfigurationError(f"tbls config not found: {layout.tbls_config_path}")
    return CatalogContext(profile, layout)


def validate_database_scope(
    profile: DatabaseProfile,
    schema_path: Path,
    *,
    allow_missing_tables: bool = False,
) -> None:
    """Reject out-of-scope tables and optionally treat missing tables as schema drift."""
    try:
        schema = TblsSchemaSource(schema_path).load()
    except SchemaSourceError as error:
        raise CatalogConfigurationError(str(error)) from error
    if schema.name != profile.clickhouse_database:
        raise CatalogConfigurationError(
            f"raw schema database {schema.name!r} does not match configured ClickHouse database "
            f"{profile.clickhouse_database!r}"
        )
    actual = {table.name for table in schema.tables}
    allowed = set(profile.tables)
    unexpected = sorted(actual - allowed)
    missing = sorted(allowed - actual)
    messages = []
    if unexpected:
        messages.append(f"tables outside allowlist: {', '.join(unexpected)}")
    if missing and not allow_missing_tables:
        messages.append(f"allowlisted tables missing from raw schema: {', '.join(missing)}")
    if messages:
        raise CatalogConfigurationError("; ".join(messages))


def discover_database_keys(
    repository_root: Path = Path("."), *, enabled_only: bool = False
) -> tuple[str, ...]:
    """Return configured database directory names in deterministic order."""
    profiles_root = repository_root.resolve() / "config" / "databases"
    keys = (
        tuple(
            path.name
            for path in sorted(profiles_root.iterdir())
            if path.is_dir() and (path / "database.yml").is_file()
        )
        if profiles_root.is_dir()
        else ()
    )
    if not enabled_only:
        return keys
    return tuple(
        key for key in keys if load_database_profile(profiles_root / key / "database.yml").enabled
    )


def discover_scheduled_database_keys(repository_root: Path = Path(".")) -> tuple[str, ...]:
    """Return enabled profiles that explicitly opt in to scheduled extraction."""
    profiles_root = repository_root.resolve() / "config" / "databases"
    return tuple(
        key
        for key in discover_database_keys(repository_root)
        if (profile := load_database_profile(profiles_root / key / "database.yml")).enabled
        and profile.scheduled_sync
    )


def discover_ready_database_keys(repository_root: Path = Path(".")) -> tuple[str, ...]:
    """Return enabled databases whose scheduled bootstrap has produced a raw schema."""
    root = repository_root.resolve()
    return tuple(
        key
        for key in discover_database_keys(root, enabled_only=True)
        if CatalogLayout(root, key).schema_path.is_file()
    )

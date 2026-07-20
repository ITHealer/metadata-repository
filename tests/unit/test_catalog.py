"""Tests for database profiles, layout resolution, and table scope enforcement."""

from pathlib import Path
from shutil import copy2

import pytest

from metadata_pipeline.application.catalog import (
    CatalogConfigurationError,
    CatalogLayout,
    discover_database_keys,
    load_catalog_context,
    validate_database_scope,
)
from metadata_pipeline.domain.catalog import DatabaseProfile
from metadata_pipeline.io.database_profile import DatabaseProfileError, load_database_profile

ROOT = Path(__file__).resolve().parents[2]


def test_loads_profile_and_derives_database_first_layout() -> None:
    context = load_catalog_context("commerce_demo", ROOT)

    assert context.profile.clickhouse_database == "commerce_demo"
    assert context.profile.tables == ("customers", "order_items", "orders")
    assert context.layout.schema_path == (ROOT / "catalog/commerce_demo/generated/raw/schema.json")
    assert context.layout.review_dir == ROOT / "catalog/commerce_demo/review"
    assert context.layout.structured_dir == (ROOT / "catalog/commerce_demo/generated/structured")
    assert context.layout.published_dir == ROOT / "catalog/commerce_demo/generated/published"


def test_rejects_profile_key_that_does_not_match_directory(tmp_path: Path) -> None:
    profile_dir = tmp_path / "config/databases/example"
    profile_dir.mkdir(parents=True)
    profile_dir.joinpath("database.yml").write_text(
        "key: wrong\ndisplay_name: Example\nclickhouse_database: example\n"
        "description: Test profile\ntables: [events]\n",
        encoding="utf-8",
    )
    profile_dir.joinpath("tbls.yml").write_text("name: example\n", encoding="utf-8")

    with pytest.raises(CatalogConfigurationError, match="does not match directory"):
        load_catalog_context("example", tmp_path)


def test_rejects_duplicate_table_allowlist(tmp_path: Path) -> None:
    path = tmp_path / "database.yml"
    path.write_text(
        "key: example\ndisplay_name: Example\nclickhouse_database: example\n"
        "description: Test profile\ntables: [events, events]\n",
        encoding="utf-8",
    )

    with pytest.raises(DatabaseProfileError, match="must be unique"):
        load_database_profile(path)


def test_scope_rejects_raw_tables_outside_allowlist(tmp_path: Path) -> None:
    schema_path = tmp_path / "schema.json"
    copy2(ROOT / "catalog/commerce_demo/generated/raw/schema.json", schema_path)
    profile = DatabaseProfile(
        key="commerce_demo",
        display_name="Commerce Demo",
        clickhouse_database="commerce_demo",
        description="Narrow test scope",
        tables=("customers", "orders"),
    )

    with pytest.raises(CatalogConfigurationError, match="outside allowlist: order_items"):
        validate_database_scope(profile, schema_path)


def test_discovers_only_database_profile_directories(tmp_path: Path) -> None:
    profiles = tmp_path / "config/databases"
    (profiles / "b").mkdir(parents=True)
    (profiles / "a").mkdir()
    (profiles / "ignored").mkdir()
    (profiles / "a/database.yml").touch()
    (profiles / "b/database.yml").touch()

    assert discover_database_keys(tmp_path) == ("a", "b")


def test_layout_keeps_build_artifacts_database_scoped(tmp_path: Path) -> None:
    layout = CatalogLayout(tmp_path, "urcard")

    assert layout.chunk_output == tmp_path / "build/chunks/urcard.jsonl"

"""Tests for database profiles, layout resolution, and table scope enforcement."""

from pathlib import Path
from shutil import copy2

import pytest

from metadata_pipeline.application.catalog import (
    CatalogConfigurationError,
    CatalogLayout,
    discover_database_keys,
    discover_ready_database_keys,
    discover_scheduled_database_keys,
    load_catalog_context,
    validate_database_scope,
)
from metadata_pipeline.cli import run_catalog_check
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
    copy2(ROOT / "tests/fixtures/commerce_demo/schema.json", schema_path)
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
    profile = (
        "enabled: true\nkey: {key}\ndisplay_name: Example\nclickhouse_database: example\n"
        "description: Test profile\ntables: [events]\n"
    )
    (profiles / "a/database.yml").write_text(profile.format(key="a"), encoding="utf-8")
    (profiles / "b/database.yml").write_text(profile.format(key="b"), encoding="utf-8")

    assert discover_database_keys(tmp_path) == ("a", "b")


def test_database_discovery_can_exclude_disabled_profiles(tmp_path: Path) -> None:
    profiles = tmp_path / "config/databases"
    (profiles / "enabled").mkdir(parents=True)
    (profiles / "disabled").mkdir()
    (profiles / "enabled/database.yml").write_text(
        "enabled: true\nkey: enabled\ndisplay_name: Enabled\n"
        "clickhouse_database: enabled\ndescription: Enabled profile\ntables: [events]\n",
        encoding="utf-8",
    )
    (profiles / "disabled/database.yml").write_text(
        "enabled: false\nkey: disabled\ndisplay_name: Disabled\n"
        "clickhouse_database: Disabled\ndescription: Pending profile\ntables: []\n",
        encoding="utf-8",
    )

    assert discover_database_keys(tmp_path, enabled_only=True) == ("enabled",)


def test_discovers_only_enabled_profiles_opted_in_to_scheduled_sync(tmp_path: Path) -> None:
    profiles = tmp_path / "config/databases"
    for key, enabled, scheduled in (
        ("scheduled", True, True),
        ("manual", True, False),
        ("disabled", False, False),
    ):
        profile_dir = profiles / key
        profile_dir.mkdir(parents=True)
        profile_dir.joinpath("database.yml").write_text(
            f"enabled: {str(enabled).lower()}\n"
            f"scheduled_sync: {str(scheduled).lower()}\n"
            f"key: {key}\ndisplay_name: {key}\nclickhouse_database: {key}\n"
            f"description: Test profile\ntables: {'[events]' if enabled else '[]'}\n"
            + ("tbls_dsn_env: TBLS_DSN_SCHEDULED\n" if scheduled else ""),
            encoding="utf-8",
        )
        if enabled:
            profile_dir.joinpath("tbls.yml").write_text(
                f"name: {key}\n",
                encoding="utf-8",
            )

    assert discover_scheduled_database_keys(tmp_path) == ("scheduled",)


def test_scheduled_profile_is_not_automation_ready_until_schema_bootstrap(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    profile_dir = tmp_path / "config/databases/scheduled"
    profile_dir.mkdir(parents=True)
    profile_dir.joinpath("database.yml").write_text(
        "enabled: true\nscheduled_sync: true\ntbls_dsn_env: TBLS_DSN_SCHEDULED\n"
        "key: scheduled\ndisplay_name: Scheduled\nclickhouse_database: scheduled\n"
        "description: Scheduled bootstrap profile\ntables: [events]\n",
        encoding="utf-8",
    )
    profile_dir.joinpath("tbls.yml").write_text("name: scheduled\n", encoding="utf-8")
    context = load_catalog_context("scheduled", tmp_path)

    assert discover_scheduled_database_keys(tmp_path) == ("scheduled",)
    assert discover_ready_database_keys(tmp_path) == ()
    assert run_catalog_check(context, context.layout.schema_path) == 0
    assert "scheduled bootstrap has not produced schema.json" in capsys.readouterr().out

    context.layout.raw_dir.mkdir(parents=True)
    copy2(ROOT / "tests/fixtures/commerce_demo/schema.json", context.layout.schema_path)
    assert discover_ready_database_keys(tmp_path) == ("scheduled",)


@pytest.mark.parametrize(
    ("profile", "message"),
    (
        (
            "enabled: true\nscheduled_sync: true\nkey: example\n"
            "display_name: Example\nclickhouse_database: example\n"
            "description: Test\ntables: [events]\n",
            "requires tbls_dsn_env",
        ),
        (
            "enabled: false\nscheduled_sync: true\ntbls_dsn_env: TBLS_DSN_EXAMPLE\n"
            "key: example\ndisplay_name: Example\nclickhouse_database: example\n"
            "description: Test\ntables: []\n",
            "requires the database profile to be enabled",
        ),
        (
            "enabled: true\nscheduled_sync: true\ntbls_dsn_env: invalid-name\n"
            "key: example\ndisplay_name: Example\nclickhouse_database: example\n"
            "description: Test\ntables: [events]\n",
            "String should match pattern",
        ),
    ),
)
def test_rejects_unsafe_scheduled_profile_configuration(
    tmp_path: Path,
    profile: str,
    message: str,
) -> None:
    path = tmp_path / "database.yml"
    path.write_text(profile, encoding="utf-8")

    with pytest.raises(DatabaseProfileError, match=message):
        load_database_profile(path)


def test_layout_keeps_build_artifacts_database_scoped(tmp_path: Path) -> None:
    layout = CatalogLayout(tmp_path, "urcard")

    assert layout.chunk_output == tmp_path / "build/chunks/urcard.jsonl"


def test_disabled_onboarding_profile_can_have_no_tables(tmp_path: Path) -> None:
    profile_dir = tmp_path / "config/databases/urgift"
    profile_dir.mkdir(parents=True)
    profile_dir.joinpath("database.yml").write_text(
        "enabled: false\nkey: urgift\ndisplay_name: UrGift\n"
        "clickhouse_database: UrGift\ndescription: Pending onboarding\ntables: []\n",
        encoding="utf-8",
    )

    context = load_catalog_context("urgift", tmp_path)

    assert context.profile.enabled is False
    assert context.profile.tables == ()


def test_disabled_profile_validates_scope_once_raw_schema_exists(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    profile_dir = tmp_path / "config/databases/commerce_demo"
    profile_dir.mkdir(parents=True)
    profile_dir.joinpath("database.yml").write_text(
        "enabled: false\nkey: commerce_demo\ndisplay_name: Commerce Demo\n"
        "clickhouse_database: commerce_demo\ndescription: Pending onboarding\n"
        "tables: [customers, order_items, orders]\n",
        encoding="utf-8",
    )
    context = load_catalog_context("commerce_demo", tmp_path)
    schema_path = tmp_path / "schema.json"
    copy2(ROOT / "tests/fixtures/commerce_demo/schema.json", schema_path)

    assert run_catalog_check(context, schema_path) == 0
    assert "3 table(s), onboarding" in capsys.readouterr().out

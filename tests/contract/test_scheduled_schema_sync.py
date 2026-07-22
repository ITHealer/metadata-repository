"""Contract tests for staged multi-database scheduled schema synchronization."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from shutil import copy2
from typing import Any

import pytest

from metadata_pipeline.application.catalog import CatalogConfigurationError
from metadata_pipeline.application.create_drafts import create_review_drafts
from metadata_pipeline.application.scheduled_schema_sync import (
    ScheduledSchemaSyncError,
    synchronize_scheduled_schemas,
)
from metadata_pipeline.domain.catalog import DatabaseProfile
from metadata_pipeline.domain.review import DocumentStatus
from metadata_pipeline.domain.schema_sync import ScheduledSchemaSyncReport, SchemaSyncOutcome
from metadata_pipeline.io.review_yaml import load_review_document, write_review_document
from metadata_pipeline.io.schema_sync_settings import (
    SchemaSyncConfigurationError,
    SchemaSyncSettings,
)
from metadata_pipeline.ports.schema_documenter import SchemaDocumenterError

ROOT = Path(__file__).resolve().parents[2]
BASE_SCHEMA: dict[str, Any] = json.loads(
    (ROOT / "tests/fixtures/commerce_demo/schema.json").read_text(encoding="utf-8")
)


class FakeSchemaDocumenter:
    """Write configured snapshots while recording calls and optionally failing one database."""

    def __init__(
        self,
        snapshots: dict[str, dict[str, Any]],
        *,
        fail_database: str = "",
    ) -> None:
        self.snapshots = snapshots
        self.fail_database = fail_database
        self.calls: list[str] = []

    def generate(
        self,
        *,
        profile: DatabaseProfile,
        config_path: Path,
        output_dir: Path,
        dsn: str,
    ) -> None:
        assert config_path.name == "tbls.yml"
        assert dsn == f"clickhouse://{profile.key}-secret"
        self.calls.append(profile.key)
        if profile.key == self.fail_database:
            raise SchemaDocumenterError(f"{profile.key}: simulated tbls failure")
        _write_raw_snapshot(output_dir, self.snapshots[profile.key])


def test_disabled_run_stops_before_profile_or_external_resolution(tmp_path: Path) -> None:
    documenter = FakeSchemaDocumenter({})

    report = synchronize_scheduled_schemas(
        repository_root=tmp_path,
        staging_root=tmp_path / "build/schema-sync/staging",
        run_id="disabled-test",
        settings=SchemaSyncSettings.from_env({"SCHEMA_SYNC_ENABLED": "false"}),
        documenter=documenter,
    )

    assert report.outcome is SchemaSyncOutcome.DISABLED
    assert report.databases == ()
    assert documenter.calls == []
    assert not (tmp_path / "build/schema-sync/staging").exists()


def test_enabled_run_without_opted_in_profiles_is_a_noop(tmp_path: Path) -> None:
    _configure_database(tmp_path, "manual", _schema("manual"), scheduled=False)
    documenter = FakeSchemaDocumenter({})

    report = _synchronize(tmp_path, documenter)

    assert report.outcome is SchemaSyncOutcome.NOOP
    assert "no enabled database profile" in report.warnings[0]
    assert documenter.calls == []


def test_same_scheduled_snapshots_are_an_idempotent_noop(tmp_path: Path) -> None:
    alpha = _schema("alpha")
    _configure_database(tmp_path, "alpha", alpha)
    before = _tree_bytes(tmp_path / "catalog")
    documenter = FakeSchemaDocumenter({"alpha": alpha})

    first = _synchronize(tmp_path, documenter)
    first_staging = _tree_bytes(tmp_path / "build/schema-sync/staging/contract-test")
    second = _synchronize(tmp_path, documenter)

    assert first.outcome is SchemaSyncOutcome.NOOP
    assert first == second
    assert first.databases[0].raw_changed_paths == ()
    assert _tree_bytes(tmp_path / "catalog") == before
    assert _tree_bytes(tmp_path / "build/schema-sync/staging/contract-test") == first_staging


def test_multi_database_change_publishes_only_after_full_preflight(tmp_path: Path) -> None:
    alpha = _schema("alpha")
    beta = _schema("beta")
    _configure_database(tmp_path, "alpha", alpha)
    _configure_database(tmp_path, "beta", beta)
    beta_customer_path = tmp_path / "catalog/beta/review/customers.yml"
    beta_customer = load_review_document(beta_customer_path)
    write_review_document(
        beta_customer_path,
        beta_customer.model_copy(
            update={
                "owner": "beta-owner",
                "document_status": DocumentStatus.APPROVED,
                "business": beta_customer.business.model_copy(
                    update={"purpose": ("Reviewer-owned beta purpose.",)}
                ),
            }
        ),
    )
    alpha_before = _tree_bytes(tmp_path / "catalog/alpha")
    beta_orders_path = tmp_path / "catalog/beta/review/orders.yml"
    beta_orders_before = beta_orders_path.read_bytes()
    changed_beta = _add_column(beta, "customers", "channel")
    documenter = FakeSchemaDocumenter({"alpha": alpha, "beta": changed_beta})

    report = _synchronize(tmp_path, documenter)

    assert report.outcome is SchemaSyncOutcome.CHANGED
    assert documenter.calls == ["alpha", "beta"]
    alpha_report, beta_report = report.databases
    assert alpha_report.key == "alpha"
    assert alpha_report.modified == ()
    assert beta_report.key == "beta"
    assert beta_report.modified == ("customers",)
    assert beta_report.raw_changed_paths == (
        "catalog/beta/generated/raw/customers.md",
        "catalog/beta/generated/raw/schema.json",
    )
    assert beta_report.review_paths == ("catalog/beta/review/customers.yml",)
    assert _tree_bytes(tmp_path / "catalog/alpha") == alpha_before
    assert beta_orders_path.read_bytes() == beta_orders_before
    refreshed = load_review_document(beta_customer_path)
    assert refreshed.owner == "beta-owner"
    assert refreshed.business.purpose == ("Reviewer-owned beta purpose.",)
    assert refreshed.document_status is DocumentStatus.NEEDS_REVIEW
    assert "channel" in refreshed.columns


def test_second_database_failure_never_publishes_first_database_stage(tmp_path: Path) -> None:
    alpha = _schema("alpha")
    beta = _schema("beta")
    _configure_database(tmp_path, "alpha", alpha)
    _configure_database(tmp_path, "beta", beta)
    before = _tree_bytes(tmp_path / "catalog")
    documenter = FakeSchemaDocumenter(
        {
            "alpha": _add_column(alpha, "orders", "channel"),
            "beta": _add_column(beta, "customers", "channel"),
        },
        fail_database="beta",
    )

    with pytest.raises(SchemaDocumenterError, match="simulated tbls failure"):
        _synchronize(tmp_path, documenter)

    assert documenter.calls == ["alpha", "beta"]
    assert _tree_bytes(tmp_path / "catalog") == before


def test_missing_second_database_dsn_stops_before_any_external_call(tmp_path: Path) -> None:
    alpha = _schema("alpha")
    beta = _schema("beta")
    _configure_database(tmp_path, "alpha", alpha)
    _configure_database(tmp_path, "beta", beta)
    documenter = FakeSchemaDocumenter({"alpha": alpha, "beta": beta})

    with pytest.raises(SchemaSyncConfigurationError, match="TBLS_DSN_BETA"):
        synchronize_scheduled_schemas(
            repository_root=tmp_path,
            staging_root=tmp_path / "build/schema-sync/staging",
            run_id="missing-secret",
            settings=_settings("alpha"),
            documenter=documenter,
        )

    assert documenter.calls == []
    assert not (tmp_path / "build/schema-sync/staging").exists()


def test_table_outside_allowlist_fails_without_publishing_catalog(tmp_path: Path) -> None:
    alpha = _schema("alpha")
    _configure_database(tmp_path, "alpha", alpha)
    before = _tree_bytes(tmp_path / "catalog")
    unsafe = deepcopy(alpha)
    unsafe["tables"].append(
        {
            "name": "unapproved_table",
            "type": "BASE TABLE",
            "comment": "Must not cross the configured scope boundary.",
            "columns": [],
        }
    )

    with pytest.raises(CatalogConfigurationError, match="outside allowlist"):
        _synchronize(tmp_path, FakeSchemaDocumenter({"alpha": unsafe}))

    assert _tree_bytes(tmp_path / "catalog") == before


def test_deleted_column_requires_manual_cleanup_without_deleting_review_data(
    tmp_path: Path,
) -> None:
    alpha = _schema("alpha")
    _configure_database(tmp_path, "alpha", alpha)
    removed = deepcopy(alpha)
    customers = next(table for table in removed["tables"] if table["name"] == "customers")
    customers["columns"] = [
        column for column in customers["columns"] if column["name"] != "segment"
    ]
    documenter = FakeSchemaDocumenter({"alpha": removed})

    report = _synchronize(tmp_path, documenter)

    assert report.outcome is SchemaSyncOutcome.MANUAL_CLEANUP_REQUIRED
    assert report.manual_cleanup == ("alpha.customers:orphaned_review_column:segment",)
    review = load_review_document(tmp_path / "catalog/alpha/review/customers.yml")
    assert "segment" in review.columns


def test_deleted_table_is_reported_but_reviewer_yaml_is_preserved(tmp_path: Path) -> None:
    alpha = _schema("alpha")
    _configure_database(tmp_path, "alpha", alpha)
    removed = deepcopy(alpha)
    removed["tables"] = [table for table in removed["tables"] if table["name"] != "customers"]
    removed["relations"] = [
        relation
        for relation in removed["relations"]
        if relation["table"] != "customers" and relation["parent_table"] != "customers"
    ]
    review_path = tmp_path / "catalog/alpha/review/customers.yml"
    review_before = review_path.read_bytes()

    report = _synchronize(tmp_path, FakeSchemaDocumenter({"alpha": removed}))

    assert report.outcome is SchemaSyncOutcome.MANUAL_CLEANUP_REQUIRED
    assert report.databases[0].deleted == ("customers",)
    assert report.manual_cleanup == ("alpha.customers:orphaned_review_table",)
    assert not (tmp_path / "catalog/alpha/generated/raw/customers.md").exists()
    assert review_path.read_bytes() == review_before


def test_first_onboarding_snapshot_creates_all_reviewer_drafts(tmp_path: Path) -> None:
    alpha = _schema("alpha")
    _configure_profile(tmp_path, "alpha", alpha, scheduled=True)
    documenter = FakeSchemaDocumenter({"alpha": alpha})

    report = _synchronize(tmp_path, documenter)

    assert report.outcome is SchemaSyncOutcome.CHANGED
    assert report.databases[0].added == ("customers", "order_items", "orders")
    assert sorted(path.name for path in (tmp_path / "catalog/alpha/review").glob("*.yml")) == [
        "customers.yml",
        "order_items.yml",
        "orders.yml",
    ]


def test_rejects_unsafe_run_id_before_resetting_staging(tmp_path: Path) -> None:
    alpha = _schema("alpha")
    _configure_database(tmp_path, "alpha", alpha)

    with pytest.raises(ScheduledSchemaSyncError, match="run_id"):
        synchronize_scheduled_schemas(
            repository_root=tmp_path,
            staging_root=tmp_path / "build/schema-sync/staging",
            run_id="../unsafe",
            settings=_settings("alpha"),
            documenter=FakeSchemaDocumenter({"alpha": alpha}),
        )


def test_rejects_staging_root_outside_build_schema_sync(tmp_path: Path) -> None:
    alpha = _schema("alpha")
    _configure_database(tmp_path, "alpha", alpha)
    protected_file = tmp_path / "protected/contract-test/keep.txt"
    protected_file.parent.mkdir(parents=True)
    protected_file.write_text("must survive\n", encoding="utf-8")

    with pytest.raises(ScheduledSchemaSyncError, match="staging_root"):
        synchronize_scheduled_schemas(
            repository_root=tmp_path,
            staging_root=tmp_path / "protected",
            run_id="contract-test",
            settings=_settings("alpha"),
            documenter=FakeSchemaDocumenter({"alpha": alpha}),
        )

    assert protected_file.read_text(encoding="utf-8") == "must survive\n"


def _synchronize(
    repository_root: Path,
    documenter: FakeSchemaDocumenter,
) -> ScheduledSchemaSyncReport:
    database_keys = tuple(sorted(documenter.snapshots))
    return synchronize_scheduled_schemas(
        repository_root=repository_root,
        staging_root=repository_root / "build/schema-sync/staging",
        run_id="contract-test",
        settings=_settings(*database_keys),
        documenter=documenter,
    )


def _settings(*database_keys: str) -> SchemaSyncSettings:
    values = {"SCHEMA_SYNC_ENABLED": "true"}
    values.update(
        {f"TBLS_DSN_{key.upper()}": f"clickhouse://{key}-secret" for key in database_keys}
    )
    return SchemaSyncSettings.from_env(values)


def _configure_database(
    repository_root: Path,
    key: str,
    schema: dict[str, Any],
    *,
    scheduled: bool = True,
) -> None:
    _configure_profile(repository_root, key, schema, scheduled=scheduled)
    raw_dir = repository_root / f"catalog/{key}/generated/raw"
    _write_raw_snapshot(raw_dir, schema)
    create_review_drafts(
        raw_dir / "schema.json",
        repository_root / f"catalog/{key}/review",
        repository_root / "contracts/metadata_contract.yml",
    )


def _configure_profile(
    repository_root: Path,
    key: str,
    schema: dict[str, Any],
    *,
    scheduled: bool,
) -> None:
    profile_dir = repository_root / f"config/databases/{key}"
    profile_dir.mkdir(parents=True)
    tables = ", ".join(sorted(table["name"] for table in schema["tables"]))
    profile_dir.joinpath("database.yml").write_text(
        "enabled: true\n"
        f"scheduled_sync: {str(scheduled).lower()}\n"
        f"key: {key}\n"
        f"display_name: {key.title()}\n"
        f"clickhouse_database: {schema['name']}\n"
        "description: Contract test profile\n"
        f"tables: [{tables}]\n" + (f"tbls_dsn_env: TBLS_DSN_{key.upper()}\n" if scheduled else ""),
        encoding="utf-8",
    )
    profile_dir.joinpath("tbls.yml").write_text(
        f"name: {schema['name']}\n",
        encoding="utf-8",
    )
    contracts = repository_root / "contracts"
    contracts.mkdir(exist_ok=True)
    copy2(ROOT / "contracts/metadata_contract.yml", contracts / "metadata_contract.yml")


def _schema(database: str) -> dict[str, Any]:
    schema = deepcopy(BASE_SCHEMA)
    schema["name"] = database
    return schema


def _add_column(
    schema: dict[str, Any],
    table_name: str,
    column_name: str,
) -> dict[str, Any]:
    changed = deepcopy(schema)
    table = next(table for table in changed["tables"] if table["name"] == table_name)
    table["columns"].append(
        {
            "name": column_name,
            "type": "String",
            "nullable": False,
            "comment": f"Technical {column_name}",
        }
    )
    return changed


def _write_raw_snapshot(raw_dir: Path, schema: dict[str, Any]) -> None:
    raw_dir.mkdir(parents=True, exist_ok=True)
    raw_dir.joinpath("schema.json").write_text(
        json.dumps(schema, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    table_names = sorted(table["name"] for table in schema["tables"])
    raw_dir.joinpath("README.md").write_text(
        f"# {schema['name']}\n\n" + "\n".join(table_names) + "\n",
        encoding="utf-8",
    )
    for table in schema["tables"]:
        raw_dir.joinpath(f"{table['name']}.md").write_text(
            json.dumps(table, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )


def _tree_bytes(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }

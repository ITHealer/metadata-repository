# Raw schema artifacts

Everything below this directory is generated from the live database by `tbls`.

- Never edit `schema/raw/commerce_demo/**` manually.
- Change ClickHouse DDL or `.tbls.yml`, then run `make schema-doc`.
- Commit generated changes in the same Pull Request as their source change.
- Never place credentials, DSNs, or production row data in generated artifacts.

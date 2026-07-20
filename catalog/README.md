# Database-first metadata catalog

Each database has one isolated workspace under `catalog/<database>/`:

- `generated/raw/` is generated from ClickHouse by `tbls`; never edit it manually.
- `review/` contains reviewer-owned YAML business metadata.
- `generated/structured/` stores machine-readable generation candidates.
- `generated/published/` stores generated Markdown; never edit it manually.

Keep credentials, DSNs, and production row data out of every catalog artifact. Database-specific
runtime configuration belongs under `config/databases/<database>/`.

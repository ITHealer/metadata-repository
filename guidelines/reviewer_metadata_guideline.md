# Guideline 1 — Reviewer Metadata Guideline

**Status:** Active contract (`reviewer-v1`)
**Audience:** Domain Reviewer, Data Steward, Data Analyst
**Applies to:** `catalog/*/review/**`
**Does not apply to:** generated files under `catalog/*/generated/raw/**`

## 1. Purpose

This guideline tells reviewers what business metadata to add, where to add it, and what evidence is
required before a review document can be marked `approved`.

The reviewer supplies verified facts and explicitly records unknowns. The reviewer does not need to
rewrite technical schema information already extracted by `tbls`, and does not optimize prose for
LLM retrieval. The later transformation guideline is responsible for producing retrieval-ready
content.

## 2. Current source scope

The only technical source currently authorized and implemented by this project is **ClickHouse**.

- `tbls` reads the live ClickHouse schema and writes `catalog/*/generated/raw/**`.
- Table names, column names, data types, ClickHouse keys, DDL, and database comments come from the
  ClickHouse connection and the checked-in `tbls` configuration.
- A source system such as PostgreSQL, MySQL, Kafka, dbt, or an application service must not be stated
  as fact unless the reviewer provides project-specific evidence.
- Examples that mention another source system are hypothetical teaching examples only. They are not
  evidence about the actual production architecture.
- If the upstream source is unknown, write `Unknown — needs confirmation`; do not infer it from
  naming conventions or common architecture patterns.

## 3. File ownership and generation boundary

```text
ClickHouse
  ↓ tbls
catalog/*/generated/raw/**                 Machine-generated; never edit manually
  +
catalog/*/review/**            Reviewer-owned business metadata
  ↓ publish/enrichment step
catalog/*/generated/published/**        Machine-generated enriched output
```

Reviewers must not edit:

- `catalog/*/generated/raw/**`
- `catalog/*/generated/published/**`

Running `tbls doc --rm-dist` deletes and regenerates the raw directory, so manual changes under
`catalog/*/generated/raw/**` will be lost.

The reviewer reads the raw Markdown and `schema.json` for technical context, then edits the matching
YAML file under `catalog/*/review/**`. YAML is human-editable while also supporting strict Pydantic
and JSON Schema validation.

## 4. Current command status

Raw schema extraction remains a separate command:

```bash
make schema-doc
```

This command does **not** merge reviewer metadata and does not create enriched output. PR-04 adds
the following reviewer contract commands:

```bash
# Regenerate the committed JSON Schema from the Pydantic model
make review-schema

# Validate YAML structure, versions, schema hashes, tables, columns, and joins
make review-validate

# Run both steps (the command used by CI)
make review-check
```

PR-05 adds deterministic draft creation and schema refresh:

```bash
# Create files for new tables; preserve human content when technical schema changes
make review-draft
```

`make review-draft` may normalize YAML formatting when it refreshes a document. Store every durable
review decision in a contract field such as `business`, `columns`, `relationships`, `rules`, or
`evidence`; do not keep required information only in YAML comments because comments are not part of
the Pydantic contract and are not preserved by the deterministic writer.

The remaining planned workflow is:

```bash
# PR-06: merge raw schema + approved review metadata into published output
./scripts/metadata publish --mode mock
```

The publish subcommand is not implemented yet. There is currently no valid local command for
producing enriched output; rerunning `make schema-doc` only regenerates raw tbls output.

## 5. Reviewer workflow

1. Read the matching raw table document and `catalog/<database>/generated/raw/schema.json`.
2. Open the matching document under `catalog/<database>/review/`.
3. Verify that every referenced table and column exists in the raw schema.
4. Complete required and conditionally required sections below.
5. Attach evidence for business rules and relationships.
6. Mark unknown information explicitly instead of guessing.
7. Run `make review-validate` and resolve every reported field path.
8. Change `document_status` to `approved` only after the checklist passes.

## 6. Required metadata

| Information | Reviewer question | Requirement |
|---|---|---|
| Purpose | Which business process, decision, or analysis does this table support? | Required |
| Grain | What exactly does one row represent, and what is its logical key? | Required |
| Owner | Which person or team is accountable for the meaning of this data? | Required |
| Reviewer | Who verified the current metadata? | Required for approval |
| Appropriate use | When should consumers use this table? | Required |
| Inappropriate use | When can this table produce incomplete, duplicated, or misleading results? | Required |
| Key columns | What do important identifiers, measures, dimensions, statuses, and timestamps mean? | Required |
| Business rules | Which filters, exclusions, mappings, formulas, or deduplication rules apply? | Required when present |
| Relationships | Which tables can be joined, on which columns, with what cardinality and duplicate risk? | Required when present |
| Time semantics | Which timestamp is event time, processing time, or update time? What timezone applies? | Required when timestamps exist |
| Units | What currency, percentage, quantity, timezone, or measurement unit applies? | Required for measures |
| Value semantics | What do important codes and statuses mean? Which values are invalid or deprecated? | Required for codes/statuses |
| Freshness | How often is data updated and what delay is expected? | Recommended |
| Data quality | Are there known null, duplicate, late-arrival, completeness, or reconciliation issues? | Required when known |
| Security | Which fields are PII, sensitive, restricted, or unsuitable for examples? | Required when applicable |
| Business aliases | Which alternative terms are users likely to search for? | Recommended |
| Example questions | Which questions can and cannot be answered with this table? | Recommended |
| Evidence | Which query, dashboard, ticket, policy, config, or approved commit supports each claim? | Required for business rules |

## 7. Writing rules

### 7.1 Write precise claims

Avoid:

```text
This is the standard orders table and is normally accurate.
```

Prefer:

```text
Each row represents one `order_id`. Cancelled orders remain in the table and must be excluded from
recognized-revenue calculations.
```

### 7.2 Separate facts, hypotheses, and unknowns

Use one of these evidence states:

- `confirmed`: verified by an accountable reviewer and supported by evidence.
- `proposed`: believed to be correct but awaiting domain approval.
- `unknown`: no reliable evidence is available.
- `conflicting`: available sources disagree and generation must stop for resolution.

Never convert `proposed`, `unknown`, or `conflicting` information into a confident statement merely
to make validation pass.

### 7.3 Use exact technical identifiers

- Put table and column identifiers in backticks, for example `orders.customer_id`.
- Do not rename technical identifiers inside factual references.
- Add a business display name or aliases separately when a technical name is unclear.

### 7.4 Do not duplicate machine-owned facts unnecessarily

The reviewer does not need to copy data types, ClickHouse engines, partition keys, sorting keys, or
raw DDL into the review document. Those facts remain in `catalog/*/generated/raw/**`.

Add reviewer content only when it supplies business meaning, usage conditions, ownership,
governance, quality context, or verified relationship semantics.

### 7.5 Protect secrets and sensitive data

- Never include credentials, DSNs, access tokens, or private keys.
- Never paste real customer rows or personal information.
- Use synthetic examples such as the `.test` email domain when an example is necessary.

## 8. Table description guidance

A useful table description should cover:

```text
Business entity or event
  + row grain
  + scope/inclusion
  + important exclusion
  + time behavior when relevant
```

Example:

```text
Stores one row per `order_id` in the ClickHouse commerce dataset. Paid, pending, shipped, and
cancelled orders remain present. Consumers calculating recognized revenue must apply the
domain-approved status filter documented below.
```

Do not claim how data reached ClickHouse unless an actual pipeline, query, configuration, or owner
confirmation is available as evidence.

## 9. Column description guidance

For each important column, record applicable details:

- business meaning;
- identifier or semantic type;
- unit, currency, or timezone;
- meaning of null or default values;
- allowed values and status definitions;
- valid aggregation behavior;
- sensitivity classification;
- known caveats.

Example:

```markdown
| Column | Business meaning | Unit/values | Caveat | Evidence state |
|---|---|---|---|---|
| `total_amount` | Order total after discounts | VND | Whether shipping fees are included is unknown | unknown |
| `order_status` | Current lifecycle state | `pending`, `paid`, `shipped`, `cancelled` | Revenue treatment needs domain approval | proposed |
```

## 10. Relationship guidance

A documented relationship must include:

- source table and columns;
- target table and columns;
- full join condition;
- expected cardinality;
- whether the relationship is optional;
- whether the join can increase the row count;
- business meaning;
- evidence source and evidence state.

Example based only on the current ClickHouse demo metadata:

```markdown
- From: `orders.customer_id`
- To: `customers.customer_id`
- Join: `orders.customer_id = customers.customer_id`
- Cardinality: many orders to one customer — proposed until verified by the domain reviewer
- Enforcement: logical metadata only; the current ClickHouse schema does not enforce this join
- Duplicate risk: unknown until key uniqueness is verified
- Evidence: `config/databases/commerce_demo/tbls.yml` virtual relation and ClickHouse column comments
- Evidence state: proposed
```

The existence of similarly named columns is not sufficient evidence. Do not state a relationship as
`confirmed` based only on naming convention or an automatically detected virtual relation.

## 11. Evidence guidance

Acceptable evidence includes:

- ClickHouse DDL or comments read from the authorized live schema;
- a reviewed transformation query or pipeline configuration actually used by the project;
- an approved dashboard or metric definition;
- a ticket, policy, runbook, or architecture decision record;
- an accountable domain owner confirmation recorded in a commit or review thread;
- a repeatable validation query with its expected interpretation.

For each evidence reference, record enough information for another reviewer to find it. Do not use
generic evidence such as `confirmed by team` without a person/team, location, and review context.

## 12. Example review document

```yaml
contract_version: reviewer-v1
review_guideline_version: reviewer-v1
transformation_guideline_version: retrieval-v1
source_scope: clickhouse
database: commerce_demo
table: orders
owner: commerce-domain
reviewer: unassigned
document_status: needs_review
schema_hash: <64-character-hash-from-current-raw-schema>
business:
  display_name: Orders
  description: One technical row per order represented in the ClickHouse demo dataset.
  grain: One row per order_id.
  purpose:
    - Support order lifecycle analysis in the demo dataset.
  appropriate_use:
    - Analyze counts by order_status after the status semantics are approved.
  inappropriate_use:
    - Calculate recognized revenue before cancellation and amount rules are confirmed.
  aliases: [order fact]
  freshness: Unknown — needs confirmation
  caveats: []
  evidence:
    - kind: clickhouse_comment
      reference: catalog/commerce_demo/generated/raw/schema.json#tables.orders.comment
      status: proposed
      note: Business meaning still requires reviewer confirmation.
columns:
  total_amount:
    business_name: Order total amount
    description: Order total recorded after discounts.
    semantic_type: monetary_amount
    unit: VND
    nullable_meaning: not_applicable
    sensitivity: internal
    allowed_values: {}
    caveats:
      - Shipping-fee treatment is unknown.
    evidence:
      - kind: clickhouse_comment
        reference: catalog/commerce_demo/generated/raw/schema.json#tables.orders.columns.total_amount
        status: proposed
        note: Derived from the ClickHouse column comment.
relationships: []
business_rules: []
data_quality: []
security: []
```

Use the complete, validator-passing examples in `catalog/commerce_demo/review/` as templates.

## 13. Approval checklist

Before changing `document_status` to `approved`, confirm:

```text
[ ] Purpose and grain are explicit and do not contradict schema.json
[ ] Owner and reviewer are assigned
[ ] Important columns have business meaning
[ ] Time, unit, status, filter, and aggregation semantics are documented where applicable
[ ] Relationships include both sides, join condition, cardinality, and duplicate risk
[ ] Caveats, sensitive fields, and known data-quality issues are recorded
[ ] Business rules have evidence or remain explicitly unconfirmed
[ ] Every referenced table and column exists in schema.json
[ ] No unverified upstream source is presented as fact
[ ] No credentials, secrets, or real personal data are present
```

## 14. Change policy

- Wording-only changes that do not alter reviewer obligations may be handled as a documentation
  patch.
- Adding or removing required fields changes the metadata contract and requires validator/template
  updates.
- Canonical guideline versions live in `contracts/metadata_contract.yml`; each review file repeats the
  expected versions so a committed review remains auditable.
- Changes that affect published output require regeneration after the publish pipeline exists.

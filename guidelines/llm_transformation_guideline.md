# Guideline 2 — LLM Transformation and Retrieval Contract

**Status:** Active specification (`retrieval-v1`); publish implementation is planned for PR-06
**Audience:** AI Engineer, Data Engineer, reviewer of generated metadata
**Inputs:** `schema/raw/**`, validated `metadata/review/**`, `config/metadata_contract.yml`
**Output:** generated files under `knowledge/published/**`

## 1. Purpose

This guideline defines how a generator must combine technical ClickHouse metadata and
reviewer-owned business metadata without inventing facts. It also defines the structure required so
later chunking and retrieval preserve grain, rules, joins, units, caveats, and evidence together.

The guideline is a transformation contract, not an authorization to query another database or infer
an upstream architecture. The only implemented technical source is ClickHouse through the committed
raw tbls `schema.json`.

## 2. Input boundary

```text
schema/raw/<database>/schema.json       Technical ClickHouse facts
  +
metadata/review/<database>/<table>.yml  Reviewer business claims and evidence states
  +
config/metadata_contract.yml            Expected contract/guideline versions
  ↓
validate-review                         Structural and cross-file gate
  ↓
publish (planned PR-06)                 Deterministic merge + optional LLM wording
```

The generator must stop before generation when:

- YAML does not satisfy the Pydantic/JSON Schema contract;
- a declared table, column, or relationship endpoint does not exist in raw `schema.json`;
- the review `schema_hash` is stale;
- guideline or contract versions differ from the canonical config;
- a claim has `conflicting` evidence status;
- required input is missing.

## 3. Source precedence

Use this precedence per kind of fact; do not treat it as one global overwrite order.

| Fact type | Authoritative input | Merge behavior |
|---|---|---|
| Table/column identifiers | raw `schema.json` | Never rename or create identifiers from prose |
| Data type, nullability, ClickHouse engine/comment | raw `schema.json` | Preserve exactly as technical context |
| Business purpose, grain, use/not-use | reviewer YAML | Include with evidence state |
| Business column meaning, unit, sensitivity | reviewer YAML | Include only for a raw column that validates |
| Join endpoint | raw existence + reviewer YAML | Both endpoints must exist; keep reviewer cardinality confidence |
| Owner, caveat, quality, security | reviewer YAML | Preserve; do not silently omit warnings |
| Guideline versions | canonical config | Copy to published provenance |

Raw ClickHouse comments may seed `proposed` descriptions. They do not automatically prove business
ownership, business cardinality, freshness, revenue treatment, or an upstream data source.

## 4. Claim and evidence rules

Every generated business claim inherits its evidence state:

- `confirmed`: write as a factual statement and retain the evidence reference.
- `proposed`: label as awaiting reviewer confirmation; never strengthen the wording.
- `unknown`: state that the value is unknown and what needs confirmation.
- `conflicting`: fail generation and report all conflicting references.

An LLM may improve readability, normalize headings, or combine duplicate wording. It must not:

- create a table, column, join, value, owner, SLA, formula, or upstream source;
- convert `proposed` or `unknown` to `confirmed`;
- remove a caveat because it makes the summary less concise;
- copy secrets, credentials, DSNs, or real row data into output;
- use model memory as evidence.

When reviewer prose contradicts raw technical facts, stop with an actionable conflict. Example:
reviewer says `orders.total_amount` is nullable while raw `schema.json` says it is non-nullable.
Technical nullability comes from raw schema; the reviewer may instead document a business sentinel or
quality caveat.

## 5. Published document structure

Each table produces one generated document with provenance followed by stable sections:

```text
Provenance
Summary
Grain and purpose
Appropriate use
Inappropriate use
Columns
Relationships and join risks
Business rules
Time and unit semantics
Data quality and caveats
Security
Evidence
```

Required provenance fields:

```yaml
database: commerce_demo
table: orders
document_status: approved
schema_hash: <validated-review-hash>
contract_version: reviewer-v1
review_guideline_version: reviewer-v1
transformation_guideline_version: retrieval-v1
source_schema_path: schema/raw/commerce_demo/schema.json
source_review_path: metadata/review/commerce_demo/orders.yml
source_review_commit: <git-commit>
generator_mode: mock-or-live
```

Only an `approved` review may enter the active retrieval index. A `needs_review` document may be
rendered for preview but must be clearly labeled and excluded from active indexing.

## 6. Relationship transformation

A relationship block must keep these facts together:

- source table and columns;
- target table and columns;
- executable join condition;
- expected cardinality;
- optionality;
- row-count/duplicate risk;
- business meaning;
- evidence state and references.

Do not split the join condition from cardinality or duplicate risk during chunking. A retrieval hit
that says only “join orders to customers” is incomplete and unsafe.

## 7. Chunking contract

Chunk by semantic unit, not by an arbitrary fixed character window. Allowed chunk types for
`retrieval-v1` are:

- `table_overview`;
- `column_group`;
- `relationship`;
- `business_rule`;
- `quality_and_security`.

Every chunk must carry:

```text
stable chunk_id
database and table
chunk_type
document_status
schema_hash
guideline versions
source review commit/path
evidence references and statuses used by the chunk
```

Required co-location rules:

- `table_overview`: purpose + grain + appropriate/not-appropriate use + major caveats;
- `column_group`: exact column names + business meanings + unit/time/value semantics;
- `relationship`: both endpoints + join condition + cardinality + duplicate risk + evidence;
- `business_rule`: rule/formula/filter + scope + exceptions + evidence;
- `quality_and_security`: issue/classification + affected fields + safe-use instruction.

If a semantic unit exceeds the configured token limit in a later implementation, split at item
boundaries and repeat the minimum provenance and qualifiers. Never cut a join condition, formula, or
evidence reference in half.

## 8. Retrieval acceptance rules

Golden retrieval tests must check required facts, not only whether the correct table name appears.
Examples:

| Question type | Required facts in one result or linked chunk set |
|---|---|
| What is the orders grain? | `orders`, one row per `order_id`, evidence/confidence |
| How do orders join customers? | both tables, both columns, full condition, cardinality, duplicate risk |
| What does total_amount mean? | exact column, VND unit, discount statement, unresolved caveats |
| Can cancelled orders be counted? | status rule, intended metric context, evidence status |

Retrieval must exclude unapproved documents from the active index and must remove deleted or renamed
chunks using the manifest/diff process planned for later PRs.

## 9. Determinism and auditability

- The mock generation mode must be deterministic and is the golden-test baseline.
- A live LLM output must pass the same structural and factual validators as mock output.
- Prompt/model metadata may be recorded for observability, but it does not replace source commit,
  schema hash, or guideline version provenance.
- Re-running generation with unchanged inputs in mock mode must produce no Git diff.
- Generated output is never edited manually; corrections happen in raw schema sources, reviewer YAML,
  or this guideline, followed by regeneration.

## 10. Current implementation boundary

PR-04 implements the reviewer Pydantic contract, JSON Schema export, YAML validation, raw table and
column reference checks, and CI gates. It does not implement raw + review merge, publishing,
chunking, indexing, or an LLM call.

Therefore:

```bash
make schema-doc       # raw ClickHouse/tbls output only
make review-validate  # reviewer contract validation only
```

There is no publish command yet. PR-06 must implement this guideline as testable application logic
before enriched output can be considered valid.

## 11. Change policy

- Wording changes that preserve behavior may retain `retrieval-v1`.
- Changes to precedence, stop conditions, required published fields, chunk types, or co-location rules
  require a new transformation guideline version and regeneration of published artifacts.
- A PR changing this guideline must state impact on validators, golden outputs, chunks, manifests,
  and retrieval tests.

# Vector index apply and retrieval runbook

## Safety model

`Index Manifest` builds an auditable desired-state package. `Apply Vector Index` is the first
workflow that mutates VectorDB. It remains disabled until the non-production Gemini/Qdrant UAT has
passed:

```text
approved structured candidates
  -> manifest-v2 + body hashes
  -> read actual managed Qdrant points
  -> embed only created/updated chunks
  -> upsert successful vectors
  -> delete stale managed points
  -> re-read and verify exact IDs/body hashes
  -> run golden questions through Gemini query embeddings + Qdrant
  -> emit index_done only when apply changed state and both checks passed
```

The adapter filters on `managed_by=metadata-pipeline`. It never deletes points outside that
namespace. Point IDs are deterministic UUIDv5 values derived from stable chunk IDs.

## Provisioning

Create a non-production collection configuration using repository variables:

- `INDEX_APPLY_ENABLED=false` during provisioning and UAT.
- `EMBEDDING_PROVIDER=gemini`.
- `EMBEDDING_MODEL=gemini-embedding-001`.
- `EMBEDDING_DIMENSION=768`.
- `QDRANT_COLLECTION=metadata__gemini_embedding_001__768`.

Create Actions secrets without pasting them into workflow inputs or repository files:

- `GEMINI_API_KEY`.
- `QDRANT_URL`.
- `QDRANT_API_KEY`.

The model and dimension suffix in the collection name is validated. A model/dimension migration
must bootstrap a new collection instead of mixing incompatible vectors.

## Non-production UAT

Keep `INDEX_APPLY_ENABLED=false` globally. Temporarily enable it only for a controlled test window,
then manually dispatch **Apply Vector Index** with `bootstrap_collection=true`.

Verify the uploaded evidence:

- `manifest.json` has the intended source commit and manifest hash;
- `apply-summary.json` is `applied` and `verified: true`;
- `vector-retrieval-report.json` passes the configured document-hit and required-fact gates;
- Telegram receives one `index_done` only when actual upsert/delete counts are non-zero.

Dispatch again without changes. Expected result is `noop`, zero Gemini document embedding calls,
zero Qdrant mutation calls, a successful retrieval health check, and no duplicate `index_done`.

Test one changed approved chunk and one removed approved chunk before production enablement. A failed
upsert must occur before deletion, leave the workflow failed, and become idempotently retriable.

Manual dispatch supports `force_run=true`, so live UAT can execute while the repository-wide
`INDEX_APPLY_ENABLED` variable remains false. Follow the complete initial/no-op/change/removal and
reviewer-to-index procedure in
[`phase-2-production-validation.md`](./phase-2-production-validation.md).

## Rollback and recovery

- Immediate stop: set `INDEX_APPLY_ENABLED=false`.
- Partial failure: rerun the same source commit. Apply reads actual Qdrant state and skips points
  whose body hashes already match.
- Dimension mismatch: do not recreate or delete the collection; provision a new versioned name.
- Retrieval regression: keep the previous collection as the read-side target and investigate the
  candidate/chunk or embedding change.
- Credential exposure: disable apply, rotate the affected Gemini/Qdrant secret, then rerun the
  non-production UAT.

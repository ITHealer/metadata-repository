# Index manifest and retrieval smoke runbook

## What the MVP indexes

The `manifest-v2` package is the deterministic desired state for a vector database. It includes
only chunks whose
reviewer document is `approved`. Preview chunks from `needs_review` documents are read and validated
but excluded from the manifest.

```text
published change merged to main
  -> rebuild structured chunks
  -> filter approved chunks
  -> replace complete manifest snapshot
  -> map Git document actions and hash-based chunk actions
  -> run 10 golden retrieval questions
  -> upload manifest, actions, and report
```

Run the same checks locally:

```bash
make index-build
make retrieval-smoke
```

Artifacts are written under `build/index/` and are not committed.

## Version replacement

Chunk identity is stable. Each chunk has a canonical `body_hash`, while the complete package has a
`manifest_hash`. `schema_hash`, `source_review_commit`, and transformation
guideline version identify its content version. When any version or chunk content changes, the
adapter reports all prior chunk IDs as deletes before reporting the replacement chunk IDs as
upserts. Deleted and renamed published files map to document deletes so stale chunks cannot survive.

`build/index/chunk-actions.json` classifies every chunk as created, updated, removed, or unchanged.
The vector apply adapter must still reconcile against actual VectorDB state—the ignored local
manifest is audit evidence, not a production checkpoint.

## Reading retrieval results

`tests/fixtures/golden_questions.yml` contains at least 10 inspectable questions. A passing report
requires:

- expected document present in top 3 for at least 90% of questions;
- every `required_fact` present in the combined top-3 chunk content;
- only approved chunks participating in ranking.

The lexical retriever is intentionally small and deterministic. It validates chunk boundaries and
fact co-location; it is not a claim about production semantic-search quality.

## Recovery

- Empty manifest: confirm documents are approved; current demo reviewer files intentionally remain
  `needs_review`.
- Missing required fact: inspect whether the fact belongs in the same semantic chunk before tuning
  ranking.
- Stale chunks: run `make index-build` from a clean checkout and inspect `actions.json` plus version
  fields in `manifest.json`.
- Failed post-merge workflow: re-run `Index Manifest`; it is read-only to GitHub and writes only
  ephemeral artifacts.

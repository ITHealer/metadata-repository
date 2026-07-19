# Index manifest and retrieval smoke runbook

## What the MVP indexes

The manifest is a deterministic stand-in for a vector database. It includes only chunks whose
reviewer document is `approved`. Preview chunks from `needs_review` documents are read and validated
but excluded from the manifest.

```text
published change merged to main
  -> rebuild structured chunks
  -> filter approved chunks
  -> replace complete manifest snapshot
  -> map Git A/M/D/R to audit actions
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

Document identity is stable, while `schema_hash`, `source_review_commit`, and transformation
guideline version identify its content version. When any version or chunk content changes, the
adapter reports all prior chunk IDs as deletes before reporting the replacement chunk IDs as
upserts. Deleted and renamed published files map to document deletes so stale chunks cannot survive.

The MVP rebuilds a complete snapshot on each run. A future vector-store adapter should execute the
reported deletes before upserts and publish the new manifest only after all writes succeed.

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

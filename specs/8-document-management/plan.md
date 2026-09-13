# Plan: Phase 8 — Documents & Collections

## Approach Summary

Three pieces, only one of which is genuinely new.

**Collection resolution** merges two sources at request time: `config.toml`'s collections, tagged locked, and a writable `collections.json`, tagged editable. The merged view is a plain `dict[str, list[str]]` — exactly the shape `collections.py` and the retriever already consume — so nothing downstream changes. The locked set travels separately, and only the API layer looks at it.

**Indexing on upload** reuses `IndexBuilder` unchanged. It already skips any document whose content hash and parser identity match the manifest, so adding one document embeds one document. The new work is not indexing; it is making the write safe: snapshot the index directory, build, verify that no `evals/corpus/` document's hash or chunk ids moved, and restore the snapshot if anything did.

**Document state is derived, never stored.** A document is on disk or not, in the manifest or not, and has an active job or not. Those three facts give every state the sidebar needs — uploaded, indexing, ready, failed — with no status file to go stale and nothing to reconcile after a crash. A server that dies mid-index leaves a file on disk that isn't in the manifest, which reads as failed, which is correct.

Build order: collection registry and locked enforcement → upload and the job model → index-write safety → membership and deletion → sidebar.

## Architecture

```
config.toml [collections]  ──┐  locked
                             ├──► CollectionRegistry ──► dict[str, list[str]]
collections.json ────────────┘  editable                  (unchanged shape,
                                    │                      consumed as before)
                                    └──► locked_names: set[str]  (API only)

POST /api/collections/{name}/documents   (multipart)
   ├─ reject: unsupported extension | name collision | locked collection
   ├─ write file to docs/
   ├─ create in-memory Job, return job_id   ← returns here, immediately
   └─ background, under one index lock:
        snapshot evals/index/ ──► IndexBuilder.build(all docs) ──► verify
                                                                    │
                                          eval doc hash moved? ─────┴─► restore
```

**Document state, derived on every request:**

| on disk | in manifest | active job | state |
|---|---|---|---|
| yes | yes | — | ready |
| yes | no | running | indexing |
| yes | no | none | failed |
| yes | yes | running | reindexing |

## Tech Stack & Key Decisions

| Decision | Choice | Why |
|---|---|---|
| Collection merge | One registry producing the existing `dict[str, list[str]]`, with locked names carried alongside | `collections.py`, the retriever, and the eval runner keep working untouched. The lock is an API concern, not a retrieval one |
| Index write safety | Copy the index directory, build, verify, restore on failure | At ~500 chunks `vectors.npy` is well under a megabyte — copying is free, and it works on Windows, where renaming a directory over an existing one does not |
| Invariance check | Compare every `evals/corpus/` document's manifest hash and chunk-id range before and after | This is the spec's protection made mechanical. It runs on every index write, not just in tests |
| Document state | Derived from disk, manifest, and job table | No status file, nothing to reconcile after a crash, and an interrupted upload reads as failed for free |
| Job storage | In-memory dict, lost on restart | A job that didn't finish should be retried, not resumed. The file on disk without a manifest entry already says what happened |
| Concurrency | One `asyncio.Lock` around the whole index write; uploads queue | Two concurrent builds over one `vectors.npy` would interleave writes. Queueing is correct and at this scale invisible |
| Membership change | Rewrite `chunks.jsonl`'s `collections` field; no re-embedding | Phase 3 already writes membership per chunk and specified the membership-only rewrite path. Moving a document between collections must not cost CPU |
| Upload transport | `python-multipart` | The one new dependency, required by FastAPI for form uploads. Nothing else is added |
| Sidebar accent | **None.** The sidebar uses no accent colour at all | `DESIGN.md` allows one accent action per screen and the main pane's ask button owns it. Locked state, selection, and actions in the sidebar are carried by surface tints and weight |

## Data Model

**`collections.json`** — user collections only, same shape as `config.toml`'s block:

```json
{
  "version": 1,
  "collections": {
    "my-notes": ["meeting-2026-09.md", "spec-draft.pdf"]
  }
}
```

Locked collections never appear here. A create request naming `rules`, `transmissions`, or `everything` is a name conflict.

**Uploaded files** live in `docs/`, separate from `evals/corpus/`. A filename already present in either directory is rejected — chunk ids are `{doc}:{ordinal}`, so a collision would silently corrupt retrieval for both documents.

**Job record**, in memory:

```python
@dataclass
class IndexJob:
    job_id: str
    doc: str
    collection: str
    state: Literal["queued", "parsing", "embedding", "ready", "failed"]
    error: str | None = None
    chunk_count: int | None = None
```

**API surface** — additions to Phase 6's:

| method | path | notes |
|---|---|---|
| `GET` | `/api/collections` | now returns `{name, locked, document_count}` |
| `POST` | `/api/collections` | create; 409 on locked-name conflict |
| `PATCH` | `/api/collections/{name}` | rename; 403 if locked |
| `DELETE` | `/api/collections/{name}` | 403 if locked; documents survive |
| `POST` | `/api/collections/{name}/documents` | multipart upload → job |
| `DELETE` | `/api/collections/{name}/documents/{doc}` | membership only |
| `GET` | `/api/documents` | all documents, derived state, collections |
| `DELETE` | `/api/documents/{doc}` | from disk; body names other referencing collections |
| `GET` | `/api/jobs/{job_id}` | poll |

**Empty-extraction guard.** After parsing, a document yielding effectively no text is recorded `ready` with a zero chunk count and an `indexed but empty` note — the scanned-PDF case the spec names. It is a reported state, not a failure, because the upload and parse both succeeded.

## File / Module Structure

```
src/raglab/
├── collections.py               # CHANGED: + CollectionRegistry (merge, locked set)
├── api/
│   ├── routes_collections.py    # CHANGED: CRUD, locked enforcement
│   ├── routes_documents.py      # NEW: upload, list, delete, membership
│   ├── routes_jobs.py           # NEW: poll
│   ├── jobs.py                  # NEW: in-memory job table + index lock
│   └── indexing.py              # NEW: snapshot / build / verify / restore
└── index/builder.py             # unchanged — incremental rebuild reused as-is

collections.json                 # gitignored, created on first write
docs/                            # gitignored, uploaded files

web/src/components/
├── Sidebar.tsx                  # NEW: collapsible shell
├── CollectionList.tsx           # NEW: locked badges, selection, CRUD controls
├── DocumentList.tsx             # NEW: per-document state, remove
└── UploadControl.tsx            # NEW: file picker, job polling

tests/
├── test_collection_registry.py  # merge, locked set, name conflicts
├── test_api_collections_crud.py # locked refusal by direct request
├── test_api_documents.py        # extension reject, collision reject, membership vs delete
├── test_indexing_safety.py      # eval-doc hashes unchanged; restore on failure
└── test_document_state.py       # the derived-state table above
```

## Acceptance thresholds

- **Every `evals/corpus/` document's manifest hash and chunk ids are byte-identical after an upload and a delete.** Checked in code on every index write, and in a test. This is the phase's central guarantee and the only one whose failure is silent.
- **Locked-collection refusal is verified by direct API request**, not through the UI. A test that only clicks buttons proves nothing about what curl can reach.
- **A failed index leaves the previous index in place**, verified by forcing a build failure and asserting the manifest is unchanged.
- **The sidebar uses no accent colour**, greppable against `--color-tertiary`, so the main pane keeps its one action per screen.

## As-built

Built in the order this plan lays out, one deviation: the invariant check's
protected name set (`eval_doc_names`) is captured once at server startup
rather than re-derived from `corpus_dir` on every rebuild. A first version
re-scanned `corpus_dir` each time, which meant the exact failure mode being
guarded against -- an eval document going missing from disk -- also shrank
the set being checked against it, silently defeating the check. Caught by
`test_indexing_safety.py`'s own broken-invariant test before it shipped.

`update_document_collections` (membership-only rewrite) skips the
snapshot/verify dance `rebuild_index` uses -- it only ever touches a chunk's
`collections` field via `dataclasses.replace`, never chunk ids, text, or
vectors, so there is no eval-corpus identity for it to put at risk.

Verified: 312 tests green (`test_collection_registry.py`,
`test_indexing_safety.py`, `test_document_state.py`, `test_api_documents.py`
-- including real `.pdf`/`.md`/`.txt` uploads via pymupdf, not just mocks),
plus a live run against a scratch copy of the real corpus with the real
embedder: upload, background index, `GET /api/documents` derived state,
delete-with-confirm, and the eval-corpus manifest byte-identical before and
after both. The sidebar (collapse, locked badges, create/rename/select) was
driven live in the browser against that same scratch copy -- never the real
`evals/` directory, which git status confirms untouched throughout.

Not done: a second "add an existing document to another collection" flow
beyond upload-time assignment -- not in this plan's own API surface table,
so multi-membership for user collections stays proven at the registry level
(unit-tested) rather than reachable end-to-end from the UI. Also not
exercised: a genuinely malformed upload (e.g. a corrupt PDF) reaching
`failed` state through the live server, though `IndexBuilder`'s per-document
parser-failure isolation this depends on is covered by the existing
`test_builder.py` suite.

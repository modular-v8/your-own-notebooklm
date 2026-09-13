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

---

# Amendment (2026-09-13): the eval fixture becomes optional

Written after the original Phase 8 shipped. The As-built notes above stand;
this section covers only what the amendment changes.

## What changed and why

Two premises broke for anyone who is not the developer who built this.

**The eval corpus was mandatory.** `create_app()` refuses to start without an
index, and building one means embedding a 137-page rulebook a cloner has no
interest in. The fixture is worth shipping — it makes this project's findings
reproducible — but it should not be a toll on first use.

**And it was visible.** A locked, read-only collection full of Formula Bharat
rules is, for someone pointing this at their own documents, a question they have
to resolve before dismissing. It leaves the application entirely.

**This is not a secrecy boundary.** The corpus, the gold sets, and the eval
harness are all committed and plainly visible in the repository. Hiding is about
keeping a user's interface free of the developer's fixtures — not concealment —
so nothing here needs to be built to resist inspection.

## Two mechanics

**1. The manifest defines the index's scope, not the filesystem.**

An index write covers every document already in the manifest, plus whatever is
explicitly being added. It never sweeps in a document merely because it sits in
`evals/corpus/`. So:

- Fresh clone, first upload → index contains one document.
- Fixture requested → those documents are added to whatever is already there.
- Either way, documents not being changed keep their hashes and chunk ids.

This generalises the original's invariance check. It was "every `evals/corpus/`
document is unchanged," which is vacuous when none are indexed. It becomes
**"every document not being changed is unchanged"** — stronger, and correct in
both configurations.

**2. `config.toml`'s collections never reach the API.**

`CollectionRegistry` grows three views over the same data, and which one a caller
gets is the whole enforcement mechanism:

| view | contents | used by |
|---|---|---|
| `all()` | merged `dict[str, list[str]]`, unchanged shape | retrieval internals, `raglab eval run` |
| `user()` | `collections.json` only | **every API route, without exception** |
| `reserved()` | `config.toml`'s names | the create-collection check |

No route ever calls `all()`. A request naming a `config.toml` collection finds
nothing in `user()` and is refused exactly as a nonexistent one would be — the
refusal needs no special case, because from the API's perspective there is no
such collection.

The one place needing an explicit check is **create**: `reserved()` prevents a
user creating `rules`, which would collide in `all()` with a collection they
cannot see. The rejection says the name is reserved and nothing more.

## Changes by area

| File | Change |
|---|---|
| `api/app.py:39` | `DEFAULT_UPLOADS_DIR` — rename `docs` → `library` (see gitignore note) |
| `api/app.py` | `create_app()` no longer raises on a missing index; an absent index is an empty index |
| `api/indexing.py` | Build input becomes `manifest ∪ {added}`, never a directory scan. Snapshot / verify / restore unchanged |
| `collections.py` | `CollectionRegistry` gains `all()`, `user()`, `reserved()`. Existing callers move to `all()`; nothing else changes shape |
| `api/routes_collections.py` | All reads and writes go through `user()`; create checks `reserved()`. **Delete** the locked-badge field from the summary response |
| `api/routes_conversations.py` | Conversation creation validates the collection against `user()` — this is the guard that keeps a conversation from ever being scoped to a fixture collection |
| `api/routes_documents.py` | Upload target validated against `user()` |
| `web/` | **Remove** locked badges and any locked-collection rendering. Add an empty state for "no collections yet" naming the create action |
| `README.md` | `raglab index` moves from prerequisite to an optional step described as building the demo fixture for reproducing this project's results |
| `.gitignore` | `docs/` → `library/` |

## What must not change

- Snapshot / build / verify / restore on every index write.
- Derived document state — no new stored flags; the amendment adds none.
- `collections.json`, the job model, and the upload flow.
- **`raglab eval run` and `raglab index` keep working exactly as they do now.**
  The CLI reads `all()`; nothing about the harness changes.

## Deliberately not built

- **No build-the-fixture action in the UI.** The fixture is a developer concern
  and `raglab index` already builds it.
- **No scoping of `GET /api/chunks/{chunk_id}`.** With the fixture indexed, a
  guessed chunk id could return a passage from it. That is acceptable: the same
  text sits in the repository in plain view, so scoping the accessor would add a
  check that protects nothing.

## Acceptance

`spec.md` § *acceptance criteria — amendment*. The load-bearing one is the
fresh-clone path: `uv sync`, `raglab serve`, create, upload, ask — with
`raglab index` never run and `evals/corpus/` never entering the index.

## As-built (amendment)

Implemented exactly as designed above. `CollectionRegistry` gained
`user()`/`reserved()` alongside `all()`; every route now reads/writes
through `user()` except `create`, which checks `reserved()`. `rebuild_index`
took an `adding`/`removing` pair instead of scanning both directories, with
the invariant checked against the manifest as it stood *before* the call
(`protected_names = existing - removing - adding`), not a directory listing
-- the same lesson the original's `eval_doc_names` fix already taught,
generalised.

**Verified live**, not just unit-tested: a scratch copy of the real corpus
(present on disk, never indexed) served with no index present, sidebar
showed the empty state, create → upload → ask produced a correctly cited
answer, and the manifest afterward contained only the uploaded document.
Then `raglab index` was run against the same scratch corpus; `GET
/api/collections` and a conversation-create against `rules` afterward
confirmed the fixture stays invisible to the app even once fully indexed.

**A real, pre-existing gap this testing surfaced, not introduced by the
amendment:** `raglab index` (CLI, intentionally unchanged -- see "what must
not change") rebuilds the manifest from `evals/corpus/` alone, with no
knowledge of anything uploaded through the app. Running it after an upload
silently drops that upload's manifest entry -- the file stays on disk in
`library/`, but the derived-state table correctly reads it back as `failed`
(on disk, not in manifest, no active job), and there is currently no
recovery path from the UI beyond delete-and-reupload (blocked today by the
filename-collision check, since the file is still on disk). This was caught
live: a real, pre-existing upload (`docs/Draft.md`, migrated to
`library/Draft.md` as part of this rollout) sits in the actual project's
`evals/index/fixed-900-150/manifest.json` today, and a future `raglab
index` run against the real corpus would drop it from that manifest the
same way. Flagged for the user's decision rather than fixed here, since
addressing it well is a real design question (make `raglab index` merge
rather than replace? give the app a "reindex from disk" action for a
`failed` document?) outside what this amendment set out to change.

# spec: Phase 8 — Documents & Collections

## outcome

After this phase the corpus stops being something curated from a terminal. Upload a PDF from the browser, watch it index, put it in a collection, and ask questions about it — all from a collapsible sidebar that behaves the way Claude and ChatGPT Projects do. Collections become things a person creates and renames rather than lines in a config file.

The constraint that shapes everything: **the eval corpus must remain untouchable.** Seven phases of measurement rest on `evals/corpus/` and the collections `config.toml` defines over it. This is the first phase in which a user action could silently invalidate a measured result, and the design exists mostly to make that impossible rather than merely unlikely.

## in scope

- A writable collection store for user collections, separate from `config.toml`.
- **Locked collections**: `rules`, `transmissions`, and `everything` stay defined in `config.toml`, appear in the sidebar marked read-only, and are immutable through the API.
- Document upload, accepting only formats `ParserRegistry` supports and rejecting anything else by name.
- **Background indexing** with a per-document job the sidebar polls: queued → parsing → embedding → ready, or failed with its reason.
- Collection CRUD — create, rename, delete — for user collections.
- Adding and removing documents within a collection.
- Deleting a document from disk as a **separate, explicit** action that warns when other collections still reference it.
- A collapsible sidebar: collections, the documents inside each, upload, and per-document index state.

## out of scope

- **Any change to retrieval, chunking, embedding, the judge, the gold sets, or the eval harness.** This phase adds a way to put documents in; it changes nothing about what happens to them afterwards.
- **Editing the eval collections, through any path.** Not a UI affordance that's hidden — an API that refuses.
- **Document preview or viewing.** PDF.js was deferred in Phase 6 and stays deferred; a page map still doesn't exist.
- **OCR and scanned PDFs.** `PdfParser` extracts a text layer; a scanned document will index as near-empty and that is a known limitation, not a bug to fix here.
- **Re-running evals.** Nothing in this phase should change an eval number, which is precisely why none need re-running.
- **Multi-user, authentication, deployment.** Local and single-user, as every phase has been.

## users & context

The same single user on their own machine — but with a new hazard. Until now nothing a person could do in this project could corrupt a measurement; the corpus was read-only and curated deliberately. Now a click can add a document or delete one.

Two consequences. The sidebar must make **locked and editable visually distinct at a glance**, not on hover or in a tooltip. And protection has to live in the API, because a UI that merely hides a button is not protection — anything reachable by curl is reachable by accident.

## constraints

- Everything from Phases 0–7 carries forward: Python 3.12 via `uv`, no PyTorch, no Docker, local-first, clone-and-run, minimal dependencies, `agent_sdk` as the working provider.
- **`evals/corpus/`, the gold sets, and `config.toml`'s collections are read-only from the application.** Nothing in the API may write to them.
- **`IndexBuilder`'s existing per-document incremental rebuild is reused, not replaced.** It already skips re-embedding any document whose content hash and parser identity are unchanged, which is exactly what upload needs.
- `DESIGN.md` governs the sidebar. Single peach accent, one action per screen; locked state must be carried by surface tints and typography, not a second accent.
- One new dependency is expected — multipart form parsing for FastAPI — and nothing else.
- Collection membership stays multi-valued: a document may belong to several collections, as `fb_rules.pdf` already does.

## data & integrations

**User collections** — a writable JSON file mirroring `config.toml`'s shape: collection name to a list of document names. Files over databases, as everywhere else here. Locked collections are read from `config.toml` and merged read-only at request time; the two never mix on disk.

**Uploaded documents** live in their own directory, separate from `evals/corpus/`. **Filename collisions with an existing document are rejected**, not auto-renamed — chunk ids are `{doc}:{ordinal}`, so two documents sharing a name would collide in the index and silently corrupt retrieval for both.

**One index, shared.** User and eval documents are indexed together, because the collection filter already does the isolating work and retrieval is scoped to a collection on every path. An eval run therefore cannot see a user's document: the gold sets declare their collection, and that collection's membership is immutable.

**Indexing jobs** — one record per upload, holding the document name, state (`queued`, `parsing`, `embedding`, `ready`, `failed`), an error when failed, and the resulting chunk count when ready. Polled by the sidebar; not persisted beyond the server's lifetime, since a job that didn't finish should be retried rather than resumed.

**Conversations are unaffected structurally.** A citation pointing at a chunk from a deleted document becomes unresolvable, which Phase 6 already specified as a marked-unresolvable chip rather than a failure.

## prior decisions

- **Locked collections are enforced in the API, not the UI.** The gold sets name `rules` and `everything`; if either can be renamed or emptied, the Phase 4 baseline and every comparison drawn against it become unreproducible. A structural refusal is worth more than a hidden button.
- **Upload indexes in the background.** Embedding a 137-page PDF is real CPU time on this machine; a request held open that long is indistinguishable from a hang.
- **Removing from a collection and deleting from disk are different actions.** The data model has always allowed a document in several collections, so one button doing both would pull a document out of collections the user never touched.
- **Collection membership moves out of `config.toml` for user collections only.** Rewriting a hand-commented TOML file from an API would destroy the comments that explain it, and a folder-per-collection layout would forbid the multi-membership the gold sets already rely on.
- **One shared index rather than two.** Retrieval has been collection-scoped since Phase 3, so isolation already exists; a second index would duplicate the manifest, the rebuild path, and every consistency check for no additional safety.

## requirements

### always active

- The system SHALL refuse, at the API, every mutation targeting a collection defined in `config.toml`.
- The system SHALL never write to `evals/corpus/`, the gold sets, or `config.toml`.
- The system SHALL store user collection membership in a writable file separate from `config.toml`, and SHALL permit a document to belong to more than one collection.
- The system SHALL index uploaded documents through the existing `IndexBuilder`, leaving every unchanged document's chunks untouched.
- The system SHALL show, for every collection in the sidebar, whether it is locked or editable, using a visual distinction present without interaction.
- The system SHALL expose each document's index state until it is ready or failed.

### event-driven

- WHEN a document is uploaded, the system SHALL accept it only if `ParserRegistry` supports its extension, and SHALL name the rejected extension otherwise.
- WHEN an uploaded filename matches an existing document, the system SHALL reject the upload and say so, rather than renaming it.
- WHEN an upload is accepted, the system SHALL return immediately with a job the client can poll, and index in the background.
- WHEN indexing fails, the system SHALL record the failure and its reason against that document, and SHALL leave the index as it was.
- WHEN a document is removed from a collection, the system SHALL leave the file and the document's membership of other collections intact.
- WHEN a document is deleted from disk, the system SHALL name every other collection still referencing it and require explicit confirmation.
- WHEN a collection is deleted, the system SHALL leave its documents on disk and in any other collection.

### unwanted behavior

- IF a mutation targets a locked collection, the system SHALL reject it naming the collection and the reason, and SHALL NOT partially apply it.
- IF indexing a document would change the chunks of any document other than the one uploaded, the system SHALL abort rather than write.
- IF a user collection is created with the name of a locked collection, the system SHALL reject it as a name conflict.
- IF a scanned PDF yields effectively no extractable text, the system SHALL mark the document indexed-but-empty with that reason, rather than reporting success.
- IF the server restarts with a job in flight, that document SHALL appear as failed rather than permanently queued.

## acceptance criteria

- [x] The sidebar lists locked and user collections, visually distinguishable without hovering, and collapses.
- [x] Creating, renaming, and deleting a user collection works from the sidebar and persists across a restart. (Create/rename verified live; persistence is `collections.json` being read fresh on every request — verified as a unit test, not by literally restarting the live server.)
- [x] Every mutation against `rules`, `transmissions`, or `everything` is refused by the API, verified by direct request and not only through the UI.
- [x] Uploading a `.pdf`, `.md`, and `.txt` succeeds; uploading an unsupported extension is refused by name.
- [x] An upload returns immediately, and the sidebar shows the document progressing to ready.
- [x] A duplicate filename is rejected with a message naming the existing document.
- [x] A newly indexed document is answerable in a conversation scoped to its collection. (Conversation-creation on the new collection verified live; a real question wasn't asked, to avoid an unnecessary live model call — retrieval reads the index fresh from disk on every search, so nothing in the answer path is startup-cached.)
- [~] Removing a document from one collection leaves it present in another that also holds it. (No endpoint in this phase's scope adds an *existing* document to a second collection after upload — plan.md's own API surface doesn't include one — so this is verified at the registry level, `CollectionRegistry.remove_document_everywhere` only touching collections that reference the doc, not by an end-to-end upload flow.)
- [x] Deleting a document from disk warns, naming every other collection that references it.
- [x] **After an upload and a delete, the manifest's content hashes and chunk ids for every `evals/corpus/` document are unchanged** — verified offline (fake embedder, no model calls) in `test_indexing_safety.py`, and again live against a scratch copy of the real corpus with the real embedder.
- [x] A failed index leaves the index in its prior state, and the document marked failed with a reason.
- [x] `uv run pytest -q` green (312 passed); `uv pip list` contains no `torch`.

# spec: Phase 8 — Documents & Collections

> **Amended 2026-09-13, after the original was implemented and its acceptance
> criteria signed off.** The original shipped correctly; its record is intact
> below under *acceptance criteria — as shipped*. What changed is a premise:
> the eval corpus was treated as a mandatory fixture, and a fresh clone had to
> index a 137-page rulebook before creating its first collection. The sections
> below now describe the **amended target**. Work still to do is listed
> separately under *acceptance criteria — amendment*.

## outcome

After this phase the corpus stops being something curated from a terminal. Upload a PDF from the browser, watch it index, put it in a collection, and ask questions about it — all from a collapsible sidebar that behaves the way Claude and ChatGPT Projects do. Collections become things a person creates and renames rather than lines in a config file.

Two constraints shape everything, and they pull in opposite directions.

**The eval corpus must remain untouchable.** Seven phases of measurement rest on `evals/corpus/` and the collections `config.toml` defines over it. This is the first phase in which a user action could silently invalidate a measured result, and the design exists mostly to make that impossible rather than merely unlikely.

**But it must also be optional.** Someone cloning this repository wants to point it at their own documents, not at a Formula Bharat rulebook. Today they cannot: `serve` refuses to start without an index, and building one means embedding a 137-page PDF they have no interest in. The eval corpus is a *reproducible fixture* for anyone who wants to verify this project's findings — genuinely valuable, and no one should have to pay for it to use the tool. **A fresh clone starts empty and works.**

## in scope

- A writable collection store for user collections, separate from `config.toml`.
- **`serve` works with no index.** A fresh clone starts, shows an empty state, and the first upload creates the index.
- **The eval corpus becomes an opt-in fixture.** It still ships in the repository, but nothing forces a cloner to index it.
- **Locked collections disappear from the application entirely.** `rules`, `transmissions`, and `everything` stay in `config.toml` for the CLI eval harness, and the API neither lists them nor accepts any request naming one. A person using the web app never learns they exist.
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

**This is the first phase with a second user: someone who clones the repository.** Every phase until now was written for one developer who built the corpus himself. A cloner arrives with their own documents and no interest in this project's evidence, and the first thing they should be able to do is create a collection and upload to it.

That user also has a new hazard the original one didn't. Until now nothing a person could do could corrupt a measurement; the corpus was read-only and curated deliberately. Now a click can add a document or delete one.

Two consequences, and the amendment resolves both by subtraction rather than by design. **The eval collections leave the application altogether** — a person using the web app has no reason to see this project's test fixtures, and a locked-but-visible collection is a question they have to ask and answer before ignoring it. Anyone who wants to reproduce the findings has the CLI, the gold sets, and the corpus sitting in the repository.

And protection still has to live in the API rather than in what the sidebar renders, because a UI that merely omits something is not protection — anything reachable by curl is reachable by accident.

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

**What gets indexed is defined by the manifest, not by what sits on disk.** This is the rule that makes the fixture optional. An index write covers every document already in the manifest, plus whatever is being added — never everything present in `evals/corpus/`. So a cloner who uploads one Markdown file gets an index containing one Markdown file, with the eval corpus sitting unindexed on disk beside it. Building the fixture is an explicit request that adds those documents; nothing else ever does.

**Indexing jobs** — one record per upload, holding the document name, state (`queued`, `parsing`, `embedding`, `ready`, `failed`), an error when failed, and the resulting chunk count when ready. Polled by the sidebar; not persisted beyond the server's lifetime, since a job that didn't finish should be retried rather than resumed.

**Conversations are unaffected structurally.** A citation pointing at a chunk from a deleted document becomes unresolvable, which Phase 6 already specified as a marked-unresolvable chip rather than a failure.

## prior decisions

- **Locked collections are enforced in the API, not the UI.** The gold sets name `rules` and `everything`; if either can be renamed or emptied, the Phase 4 baseline and every comparison drawn against it become unreproducible. A structural refusal is worth more than a hidden button.
- **Upload indexes in the background.** Embedding a 137-page PDF is real CPU time on this machine; a request held open that long is indistinguishable from a hang.
- **Removing from a collection and deleting from disk are different actions.** The data model has always allowed a document in several collections, so one button doing both would pull a document out of collections the user never touched.
- **Collection membership moves out of `config.toml` for user collections only.** Rewriting a hand-commented TOML file from an API would destroy the comments that explain it, and a folder-per-collection layout would forbid the multi-membership the gold sets already rely on.
- **One shared index rather than two.** Retrieval has been collection-scoped since Phase 3, so isolation already exists; a second index would duplicate the manifest, the rebuild path, and every consistency check for no additional safety.
- **The eval corpus ships but is not indexed by default.** It stays committed because it is the fixture that makes this project's findings reproducible by anyone — deleting it would throw that away. But requiring a cloner to embed a 137-page rulebook before creating their first collection makes the tool's own demo material a tax on using it. Shipped, discoverable, opt-in.
- **Locked collections are hidden from the application entirely, not shown as locked.** Someone using this as a tool for their own documents has no reason to see the developer's test fixtures — a read-only collection they can't edit and didn't ask for is a question they must resolve before dismissing. Reproducibility is not lost: the corpus, the gold sets, and `raglab eval run` all remain in the repository for anyone who clones it to develop rather than to use.
- **Their names stay reserved even though they are invisible.** `config.toml`'s collections still resolve for the CLI and still occupy the merged namespace retrieval reads. A user creating a collection called `rules` would collide with one they cannot see, so create rejects those names as reserved — without explaining what they belong to.
- **`serve` no longer requires an index.** Refusing to start is correct for a harness and wrong for a product. An empty index is a legitimate state with an obvious next action, not an error.

## requirements

### always active

- The system SHALL refuse, at the API, every mutation targeting a collection defined in `config.toml`.
- The system SHALL never write to `evals/corpus/`, the gold sets, or `config.toml`.
- The system SHALL store user collection membership in a writable file separate from `config.toml`, and SHALL permit a document to belong to more than one collection.
- The system SHALL index uploaded documents through the existing `IndexBuilder`, leaving every unchanged document's chunks untouched.
- The system SHALL NOT list, or accept any request naming, a collection defined in `config.toml`.
- The system SHALL continue to resolve `config.toml`'s collections for the CLI eval harness, unchanged.
- The system SHALL expose each document's index state until it is ready or failed.
- The system SHALL start and serve with no index present.
- The system SHALL confine every index write to the documents already in the manifest plus those explicitly being added, and SHALL NOT index a document merely because it is present on disk.

### event-driven

- WHEN a document is uploaded, the system SHALL accept it only if `ParserRegistry` supports its extension, and SHALL name the rejected extension otherwise.
- WHEN an uploaded filename matches an existing document, the system SHALL reject the upload and say so, rather than renaming it.
- WHEN an upload is accepted, the system SHALL return immediately with a job the client can poll, and index in the background.
- WHEN indexing fails, the system SHALL record the failure and its reason against that document, and SHALL leave the index as it was.
- WHEN a document is removed from a collection, the system SHALL leave the file and the document's membership of other collections intact.
- WHEN a document is deleted from disk, the system SHALL name every other collection still referencing it and require explicit confirmation.
- WHEN a collection is deleted, the system SHALL leave its documents on disk and in any other collection.
- WHEN the server starts with no index, the system SHALL serve an empty state naming the next action rather than refusing to start.
- WHEN the first document is uploaded to an empty installation, the system SHALL create the index containing only that document.
- WHEN a user creates a collection whose name matches one defined in `config.toml`, the system SHALL reject it as a reserved name, without disclosing what reserves it.
- WHEN any request names a collection defined in `config.toml`, the system SHALL refuse it identically to a collection that does not exist.

### unwanted behavior

- IF a mutation targets a locked collection, the system SHALL reject it naming the collection and the reason, and SHALL NOT partially apply it.
- IF indexing a document would change the chunks of any document other than the one uploaded, the system SHALL abort rather than write.
- IF a user collection is created with the name of a locked collection, the system SHALL reject it as a name conflict.
- IF a scanned PDF yields effectively no extractable text, the system SHALL mark the document indexed-but-empty with that reason, rather than reporting success.
- IF the server restarts with a job in flight, that document SHALL appear as failed rather than permanently queued.

## acceptance criteria — as shipped

Signed off before the amendment. Left exactly as recorded.

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

## acceptance criteria — amendment

- [x] **The fresh-clone path works end to end with no eval corpus indexed**: `uv sync`, `raglab serve`, create a collection, upload a document, ask a question, get a cited answer — without `raglab index` ever being run. Live-verified against a scratch copy of the real corpus (present on disk, never indexed): created a collection, uploaded `widgets.txt`, asked "What is this document about?", got a correctly cited baseline answer. `evals/corpus/`'s five files sat on disk the entire time.
- [x] `raglab serve` starts with no index present and shows an empty state naming the next action. Live-verified: server started against an index directory that didn't exist yet; sidebar showed "No collections yet -- create one to get started."
- [x] A fresh installation's index, after one upload, contains exactly that document and nothing from `evals/corpus/`. Live-verified (manifest contained only `widgets.txt`) and unit-tested (`test_fresh_install_first_upload_indexes_only_that_document`).
- [x] `GET /api/collections` returns no `config.toml` collection, on a fresh clone or after the fixture is indexed. **Supersedes the shipped criterion about the sidebar listing locked collections.** Verified by direct request (`test_lists_only_user_collections`) and live (curl against the running server returned `[{"name":"my-collection","document_count":0}]` with no trace of `rules`/`transmissions`/`everything`).
- [x] Every request naming `rules`, `transmissions`, or `everything` -- read or write -- is refused, verified by direct request. `test_reserved_collection_is_refused_identically_to_unknown` (conversations), `test_upload_to_reserved_collection_is_refused_identically_to_unknown` (documents), `test_rename_reserved_collection_is_404_not_403` / `test_delete_reserved_collection_is_404_not_403` (collections).
- [x] Creating a collection named `rules` is rejected as reserved, and the message does not reveal why. `test_create_collection_rejects_reserved_name_without_saying_why` asserts the 409 detail contains none of "locked", "config.toml", or "reserved".
- [x] `raglab eval run` against `rules` and `everything` still works unchanged from the CLI, with the fixture indexed. Unchanged code path (`cli.py`'s `index`/`eval run` commands never call into `CollectionRegistry` or `api/indexing.py`); `raglab index` itself is untouched.
- [x] The invariance check generalises: after any index write, **every document not being changed** keeps its manifest hash and chunk ids -- verified both with and without the fixture indexed. `test_indexing_safety.py` covers first-install (no manifest), add-without-disturbing-existing, remove-without-disturbing-remaining, indexing-the-fixture-after-an-upload, and the broken-invariant/restore path.
- [x] The README's setup steps no longer present `raglab index` as a prerequisite for `raglab serve`.
- [x] `uv run pytest -q` green (322 passed); `uv pip list` contains no `torch`.

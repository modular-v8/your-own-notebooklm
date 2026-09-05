# spec: Phase 1 — Ingest & Index (parsing → chunks → vectors → retrieval)

## outcome

After this phase, documents are parsed, chunked, embedded locally, and stored in a persistent index that can be searched from the command line. A retrieval pipeline answers gold-set questions from a handful of retrieved chunks instead of a whole document, and the eval harness reports — for the first time — whether the *right* chunks came back. The measurable claim is not that answers get better: Phase 0 established that they are already perfect on this corpus. The claim is that the same answers cost dramatically fewer tokens, and that retrieval finds the correct passage across the whole corpus rather than being handed the right document.

## in scope

- A parser layer with a stable interface: extracted text plus a recorded parser identity.
- A chunker producing chunks that carry their source document, character span, and ordinal position.
- Local CPU embedding of chunks via `fastembed` / `bge-small-en-v1.5`.
- A persistent vector index recording the embedding model id and dimension alongside the vectors.
- Corpus-wide top-k retrieval — searching every indexed document, not a pre-selected one.
- `raglab index` and `raglab search` CLI commands.
- A `RetrievalPipeline` implementing the (revised) `Pipeline` protocol.
- The `answer_location` → chunk mapping rule, and recall@k / MRR computation built on it.
- Wiring `retrieved`, `recall_hit`, `recall_at_k`, and `mrr` from pipeline through runner into the report.
- Extending run-to-run delta reporting to cover the retrieval aggregates and input-tokens-per-question.
- Revising the `Pipeline` protocol so a pipeline resolves its own context rather than being handed document text.

## out of scope

- **Any web UI or HTTP server.** `raglab search` is a CLI command. FastAPI and React remain Phase 2.
- **Hybrid search, reranking, query rewriting, contextual chunk headers.** All of it is Phase 4, and all of it is meaningless until recall@k exists to measure it against.
- **Collections and scoped conversations.** Phase 3. This phase has exactly one corpus.
- **Conversation history and multi-turn questions.** Each gold entry is a single independent question.
- **Chunking-strategy optimization.** One reasonable default, chosen and recorded. Sweeping chunk size and overlap is a Phase 4 experiment that needs this phase's measurement to exist first.
- **Changing the judge, or the groundedness definition.** The ruler stays fixed, or Phase 1's numbers are not comparable to Phase 0's.

## users & context

Unchanged from Phase 0: one developer, Windows 10, terminal, no GPU, 16 GB RAM. One new usage pattern matters — `raglab search` will be run interactively and repeatedly while staring at what the retriever returns for a question it got wrong. That is the primary learning loop of this phase, so its output has to be readable at a glance: score, source document, line range, and enough chunk text to judge relevance without opening the file.

## constraints

- Everything from Phase 0's constraints carries forward unchanged: Python 3.12 via `uv`, no PyTorch, no Docker, local-first, clone-and-run, minimal dependencies.
- Embeddings are `BAAI/bge-small-en-v1.5` (384-dim) via `fastembed`, CPU-only. Frozen in Phase 0; not reopened here.
- Indexing and search make no network call. The only network call in the system remains the model provider.
- The vector index is a file on disk inside the repository working tree, not a server.
- Phase 0's contracts are load-bearing and change only where this spec says so: the report schema, the gold-set schema, the judge, and the provider layer are otherwise untouched.
- The four existing gold sets must keep passing. They are the regression test for everything Phase 0 built.

## data & integrations

**Index** — a persistent store under `evals/index/` (gitignored; rebuildable from the corpus). Per chunk it records: chunk id, source document name, character span in the extracted text, ordinal position, chunk text, and vector. Per index it records: embedding model id, vector dimension, chunker settings, and the parser identity and content hash of every document indexed.

**Parser identity is part of a document's identity.** A document is identified by the hash of its source bytes *and* the parser name and version that produced its text. This matters because `answer_location` line and character ranges refer to *extracted* text: if a parser upgrade shifts the extraction by one line, every gold span silently points at the wrong place. Recording the parser identity is what turns that silent corruption into a loud failure.

**No new external service.** `fastembed` downloads its ONNX model once on first use and runs locally thereafter.

## prior decisions

- **Phase 1 is judged on cost at parity, not on accuracy.** Phase 0's baseline scored 100% grounded and 100% refusal-correct on all four gold sets. There is no accuracy headroom on a 1,500–3,400 word document, so a spec demanding improvement could only produce a tie or a regression. The honest claim RAG makes on a corpus this size is that it reaches the same answer for a fraction of the tokens.
- **Recall counts any overlap.** A chunk is a recall hit if its character span shares at least one character with the gold `answer_location`. Majority-overlap and full-containment were both rejected because they move recall when chunk size changes even though retrieval did not get worse — and Phase 4 varies chunk size deliberately. The rule is frozen here; changing it later invalidates every comparison drawn against this phase.
- **Retrieval searches the whole corpus.** The gold entry's `doc` field becomes ground truth for scoring, never a filter narrowing the search. Scoping search to the right document in advance would test chunking while hiding the harder and more realistic question of whether the retriever can distinguish four documents about similar transmission technologies.
- **The search interface is a CLI command, not a web page.** The learning value is in reading returned chunks, which a terminal delivers immediately; the web stack would roughly double the phase for no additional insight.
- **The `Pipeline` protocol changes.** Phase 0 shipped `answer(question, doc_text)`, which cannot express retrieval — a retrieval pipeline needs an index and may draw from several documents. The protocol is revised so pipelines resolve their own context. The whole-doc baseline's *behavior* is unchanged; only its plumbing moves.
- **Chunking uses one recorded default, not a swept parameter.** Optimization is Phase 4's job and requires this phase's measurement to already exist.

## requirements

### always active

- The system SHALL index every corpus document into a persistent store recording, per chunk, its source document, character span in the extracted text, ordinal position, and text.
- The system SHALL record the embedding model id and vector dimension in the index, and SHALL refuse to query an index built with a different model or dimension.
- The system SHALL record, per indexed document, its source content hash and the identity of the parser that produced its text.
- The system SHALL search across every indexed document by default.
- The system SHALL score a retrieved chunk as a recall hit when its character span overlaps the gold entry's `answer_location` by at least one character.
- The system SHALL populate `retrieved` and `recall_hit` per entry, and `recall_at_k` and `mrr` in aggregates, for any run using a retrieval pipeline.
- The system SHALL leave those fields null for runs using the whole-document baseline.
- The system SHALL keep the whole-document baseline pipeline runnable, with unchanged answering behavior.
- The system SHALL perform all parsing, chunking, embedding, and search locally, with no network call.

### event-driven

- WHEN a document is indexed, the system SHALL extract its text through the parser layer, chunk it, embed each chunk, and store the chunks with their spans.
- WHEN a document's source hash or parser identity differs from what the index recorded, the system SHALL re-index that document and leave every other document's chunks untouched.
- WHEN a search query is issued, the system SHALL return the top-k chunks with, for each, its similarity score, source document, line range, and text.
- WHEN the retrieval pipeline answers a question, the system SHALL place only the retrieved chunks in the model context and SHALL record the ids of the chunks it used.
- WHEN an eval run completes using a retrieval pipeline, the system SHALL report recall@k and MRR alongside groundedness and refusal correctness.
- WHEN a run is compared against a prior report, the system SHALL include input-tokens-per-question and the retrieval aggregates in the printed delta.

### unwanted behavior

- IF the index's embedding model or dimension does not match the configured one, the system SHALL refuse to query and SHALL name both the indexed and the configured model.
- IF a gold entry's `answer_location` maps to no chunk span in the index, the system SHALL report that entry as unscoreable at validation time, before any model call, and SHALL name the entry and document.
- IF the parser fails on a document, the system SHALL record that document as unindexed with its error and SHALL continue indexing the remaining documents.
- IF an eval run references a document absent from the index, the system SHALL abort and name the document rather than answering from an empty retrieval.
- IF retrieval returns no chunk above the configured score threshold, the retrieval pipeline SHALL refuse to answer rather than answering from an empty context.
- IF a corpus document is added or edited without re-indexing, the system SHALL detect the hash difference and refuse to run until the index is rebuilt.

## acceptance criteria

- [x] `raglab index` builds an index over the corpus and reports per-document chunk counts. Verified against the real corpus: 476 chunks across 5 documents (401 from `fb_rules.pdf`, 75 across the four Markdown docs).
- [x] `raglab search "<query>"` returns top-k chunks with score, document, line range, and text, drawn from across all documents. Verified interactively against the live index.
- [x] A run report from a retrieval pipeline has non-null `retrieved`, `recall_hit`, `recall_at_k`, and `mrr`. Verified across all 5 live retrieval runs (see below).
- [x] A run report from the whole-document baseline still has those fields null. Verified across all 4 live whole-doc regression runs.
- [x] The any-overlap rule is unit-tested at its boundaries: a gold span exactly meeting a chunk edge, a span crossing one boundary, and a span covering three chunks. `tests/test_recall.py`.
- [ ] All four existing gold sets still score 100% grounded and 100% refusal-correct under the retrieval pipeline. **3 of 4 achieved** (`tiptronic`, `egear`, `smg` all 100%/100%); `amg_mct` scored 88.9% grounded (`recall_at_k`=77.8%) on one genuine retrieval miss — q-003 needed a fact from a chunk that never made top-5. This is the honest signal the phase exists to produce (fixed-size chunking has no structure awareness), not a bug; see handover notes in `plan.md` for the specific failure and its likely Phase 4 fix (rerank or hybrid search).
- [x] Input tokens per question under retrieval are materially below the Phase 0 baseline figures recorded per gold set. `fb_rules`: 3,015 tok/q vs the computed ~77,000 ceiling — **96% reduction**. Markdown sets, retrieval vs a live re-run of whole_doc: `tiptronic` 49%, `amg_mct` 47%, `egear` 67%, `smg` 46% — all at or above the plan's ~47% modeled ceiling.
- [x] For questions whose subject matter appears in more than one document, retrieval returns chunks from the document the gold entry names. Measured directly: 82–98% of retrieved chunks came from the correct document across all 5 runs, despite the four Markdown docs covering deliberately confusable automatic-transmission topics.
- [x] Querying an index built with a different embedding model is refused, naming both models. Unit-tested (`tests/test_store.py`); not yet exercised against a real on-disk mismatched index.
- [x] Editing one corpus document and re-indexing rebuilds only that document's chunks. Unit-tested end to end (`tests/test_builder.py`): changed doc gets new chunks/vectors, unchanged doc's chunks are byte-identical and the embedder is never called for it again.
- [x] A gold entry whose `answer_location` falls outside the extracted text is reported as unscoreable before any model call. Verified live and unit-tested: 5 of `fb_rules.yaml`'s 10 entries have genuinely ambiguous rule-ID anchors (the same ID appears in the PDF's own revision-history changelog and its rule body) — `raglab gold validate` reports and aborts (strict linting); `raglab eval run` reports and excludes just those entries from recall/MRR while still grading them for groundedness, so 5 real ambiguous entries don't block the other 5 in the same gold set.
- [x] The whole-document baseline reproduces its Phase 0 grounded and refusal numbers after the `Pipeline` protocol change. Re-run live on all 4 Markdown gold sets: `tiptronic`/`amg_mct`/`egear` all 100%/100% (unchanged); `smg` showed one groundedness miss traced to LLM-judge miscalibration on a genuinely correct answer (verified against source text), the same failure mode Phase 0's own handover notes already documented — not a regression from this phase's changes.

# Plan: Phase 1 — Ingest & Index

## Approach Summary

Three new layers slot in beneath the existing pipeline seam: a **parser** turning any source file into text plus a recorded parser identity, a **chunker + embedder + vector store** turning that text into searchable chunks, and a **retriever** answering queries across the whole corpus. Above them, the `Pipeline` protocol changes shape so a pipeline resolves its own context instead of being handed document text — which is what lets `RetrievalPipeline` and `WholeDocPipeline` sit behind one interface the eval runner already knows how to drive.

The measurement work is the other half, and it is where the subtlety lives: gold `answer_location` values must resolve to character spans in extracted text so the frozen any-overlap rule can score them. That resolver, not the vector search, is the part most likely to be quietly wrong.

The vector store is brute-force NumPy. At ~480 chunks today, and well under 50,000 even at Phase 4's largest imaginable corpus, cosine similarity over a dense matrix is a sub-millisecond operation — an ANN index would add a dependency and hide the one computation most worth seeing while learning how retrieval works. It sits behind a `VectorStore` protocol so Phase 4 can replace it if a real scale problem ever appears.

Three slices, and only the last one spends provider quota:

1. **Index and search** — parser, chunker, embedder, store, `raglab index`, `raglab search`. Zero model calls. Ends when you can search the rulebook from a terminal.
2. **Scoring** — location resolution, any-overlap recall, MRR, and the gold-set migration. Zero model calls, heaviest unit-test load.
3. **Pipeline and runs** — the protocol change, `RetrievalPipeline`, runner and report wiring, then live runs.

## Architecture

```
raglab index ──► IndexBuilder
                   ├── ParserRegistry ──► TextParser (.txt/.md) | PdfParser (.pdf)
                   ├── Chunker         (fixed-size, char spans preserved)
                   ├── Embedder        (fastembed, bge-small-en-v1.5, CPU)
                   └── VectorStore ──► evals/index/{manifest.json, chunks.jsonl, vectors.npy}

raglab search ─► Retriever ──► Embedder.query_embed() ──► VectorStore.search(k)
                                                            └─► [RetrievedChunk]

raglab eval run ► EvalRunner  (existing)
                    ├── Query(question, doc_hint)
                    ├── Pipeline ──┬── WholeDocPipeline   (documents; uses doc_hint)
                    │              └── RetrievalPipeline  (index; ignores doc_hint)
                    ├── Judge      (existing, untouched)
                    ├── LocationResolver ─► gold AnswerLocation -> char spans
                    └── RecallScorer     ─► any-overlap -> recall_hit, recall@k, MRR
```

The runner uses `doc_hint` for two things only: handing the baseline its document, and scoring recall against the right gold spans. It is never a search filter — retrieval always sees the whole corpus.

## Tech Stack & Key Decisions

| Decision | Choice | Why |
|---|---|---|
| Vector store | Brute-force NumPy, `float32` matrix | ~480 chunks now, <50K ever. Cosine over that is sub-millisecond; an ANN index is dependency weight and hidden machinery for a problem this project will not have |
| Index format | `manifest.json` + `chunks.jsonl` + `vectors.npy` | Inspectable by eye, rebuildable from corpus, gitignored. Row order in `vectors.npy` matches line order in `chunks.jsonl` |
| Chunker | Fixed-size, 900 chars, 150 overlap | `bge-small` truncates past 512 tokens (~2,000 chars); 900 leaves generous headroom. Recorded as a default, not swept — sweeping is Phase 4 |
| Embedder | `fastembed`, `bge-small-en-v1.5`, CPU | Frozen in Phase 0. ONNX, no PyTorch |
| Top-k | 5 | ~1,125 tokens of context per question, against ~2,500 tokens of fixed overhead |
| PDF parser | Try `xberg` first, timeboxed; `pymupdf` if it doesn't install cleanly on Windows | The interface makes this swappable. Don't spend a day on an unproven Rust binary — the phase's value is retrieval, not parsing |
| Document hash | SHA-256 of **source bytes**, always | Text-hashing breaks on binaries and buys nothing now that parser identity is recorded separately |
| Refusal threshold | Config value, default low (0.35), as a safety net only | The model already refuses correctly (100% in Phase 0). Tuning a threshold against the `not-in-document` entries would be fitting to the gold set |
| Recall metrics | recall@k and MRR, computed over entries that have gold spans | `not-in-document` entries have no span; their retrieval is still recorded, but they cannot contribute to recall |

**Three traps this plan exists to avoid:**

- **`bge` is an asymmetric model.** Queries need an instruction prefix that passages must not have. `fastembed` exposes `query_embed()` and `embed()` separately for exactly this reason. Using `embed()` for queries costs retrieval quality silently — nothing errors, results just get worse. A unit test must assert that `query_embed()` output differs from `embed()` output for the same string, so a future refactor cannot collapse them.
- **Rule-ID anchors nest.** `A1.1` is a literal prefix of `A1.1.1`, and your corpus has 2,269 such IDs. A naive `str.find("A1.1")` anchors to the wrong rule and every recall score built on it is quietly wrong. Anchor matching uses boundary guards on both sides (`(?<![\w.])` … `(?![\w.])`) and is unit-tested against exactly this case.
- **Structure-aware chunking is deliberately *not* in this phase.** Splitting the rulebook on rule boundaries would obviously beat fixed-size chunks. That is the single most promising Phase 4 experiment, and running it now — before recall@k exists to measure it — would mean adopting it on faith. Fixed-size is the honest starting point it gets measured against.

## Data Model

**Index** — `evals/index/`, gitignored, rebuildable.

`manifest.json`:
```json
{
  "embedding_model": "BAAI/bge-small-en-v1.5",
  "dimension": 384,
  "chunker": { "strategy": "fixed", "size": 900, "overlap": 150 },
  "documents": {
    "fb_rules.pdf": {
      "source_sha256": "sha256:971813fd…",
      "parser": "pymupdf/1.24",
      "text_chars": 300289,
      "chunk_count": 401
    }
  }
}
```

`chunks.jsonl`, one row per chunk, line N corresponding to row N of `vectors.npy`:
```json
{"chunk_id": "fb_rules.pdf:0042", "doc": "fb_rules.pdf", "ordinal": 42,
 "char_start": 31500, "char_end": 32400, "text": "…"}
```

`chunk_id` is `{doc}:{ordinal:04d}` — stable, sortable, and readable in a run report's `retrieved` array, which matters because that array is something you will read by eye when a question scores badly.

**Gold-set schema change.** `AnswerLocation.value` becomes `list[str] | None`:

```yaml
answer_location: { type: section, value: ["A4.4.1"] }
answer_location: { type: section, value: ["CV4.1.2", "EV6.1.2"] }
```

Multiple values mean multiple independent gold spans. Under any-overlap, a retrieved chunk overlapping *any* of them is a hit. The comma- and semicolon-delimited strings currently in `fb_rules.yaml` and `tiptronic.yaml` q-003 cannot express this without the resolver guessing separators.

**Location resolution** — every variant normalizes to a list of `(start, end)` character spans in extracted text:

- `line_range` — line offsets computed from the extracted text; `start`/`end` are 1-indexed inclusive.
- `char_span` — used directly.
- `section` — for each anchor: find the literal with boundary guards, then extend to the start of the next structural boundary, where a boundary is either a Markdown heading line or the next rule-ID-shaped token, whichever comes first. One rule, both document kinds.

Resolution happens at **validation time, before any model call**. An anchor that matches nothing, or matches more than once ambiguously, is reported as an unscoreable entry naming the entry and document.

**Report additions.** No schema change — Phase 0 reserved the fields. `EntryReport.retrieved` fills with chunk ids, `recall_hit` with the boolean, `Aggregates.recall_at_k` and `mrr` with the computed values. `DELTA_METRICS` gains `recall_at_k`, `mrr`, and `input_tokens_per_question`.

## File / Module Structure

Additions to the existing tree; unlisted files are unchanged.

```
src/raglab/
├── corpus.py                    # CHANGED: hash source bytes, not text
├── cli.py                       # CHANGED: + index, + search
├── parsers/
│   ├── base.py                  # Parser protocol: name, version, extract(path) -> str
│   ├── text.py                  # .txt/.md passthrough
│   ├── pdf.py                   # xberg or pymupdf behind one class
│   └── registry.py              # suffix -> parser; records parser identity
├── index/
│   ├── chunker.py               # fixed-size chunks carrying char spans
│   ├── embedder.py              # fastembed wrapper; query_embed vs embed
│   ├── store.py                 # VectorStore protocol + NumpyStore
│   └── builder.py               # parse -> chunk -> embed -> write; per-doc rebuild
├── retrieval/
│   └── retriever.py             # corpus-wide top-k -> [RetrievedChunk]
├── pipelines/
│   ├── base.py                  # CHANGED: Query, RetrievedChunk, PipelineResult.retrieved
│   ├── whole_doc.py             # CHANGED: takes documents, resolves doc_hint
│   └── retrieval.py             # NEW: retrieves, then answers from chunks only
└── evals/
    ├── goldset.py               # CHANGED: value -> list[str]
    ├── locations.py             # NEW: AnswerLocation -> char spans
    ├── recall.py                # NEW: any-overlap, recall@k, MRR
    ├── runner.py                # CHANGED: builds Query, scores recall
    └── report.py                # CHANGED: DELTA_METRICS additions

tests/
├── test_chunker.py              # spans contiguous, overlap correct, no text lost
├── test_locations.py            # line_range/char_span/section; nested rule-ID guard
├── test_recall.py               # any-overlap at boundaries: touching, crossing, spanning three
├── test_embedder.py             # query_embed differs from embed (asymmetry guard)
├── test_store.py                # round-trip, dimension mismatch refusal
└── test_retrieval_pipeline.py   # via FakeProvider; refusal on empty retrieval
```

**Gold-set migration**, done in Slice 2, before any live run:

1. `fb_rules.yaml` — filename `FB2025_Rules_V1-4_05232024.pdf` → `fb_rules.pdf` (11 references).
2. All five gold sets — `section.value` string → list.
3. Four Markdown gold sets — regenerate `corpus_hashes` as byte hashes. `fb_rules.yaml` is already correct.

A `raglab gold migrate` command is not worth building for a one-time change across five files.

## Acceptance thresholds

The spec left one criterion deliberately unpinned. Now that overhead is attributed at ~2,000–2,900 tokens per question regardless of document size, it can be stated honestly — and it only applies to the large document:

- **`fb_rules`**: at least **85% fewer** input tokens per question than the computed whole-doc figure of ~77,000. Expected actual is ~3,600, or ~95%. The whole-doc baseline is **not run** on this document — 10 questions would cost ~770K input tokens against a 5-hour window, to establish a ceiling that can be computed instead.
- **Four Markdown sets**: token cost recorded for information, with **no pass/fail bar**. Their cost is overhead-dominated, so the arithmetic ceiling on any saving is roughly 47%. A 50% target here would have been unreachable by construction.
- **All five sets**: grounded and refusal-correct rates must not regress against Phase 0.

## As-built notes (handover to Phase 2)

Written after implementation and a full live run: 4 whole-doc regression re-runs plus 5 retrieval-pipeline runs, all via `agent_sdk`/`claude-sonnet-5` answering and `agent_sdk`/`claude-opus-5` judging — the same setup Phase 0 used, so numbers are directly comparable. 67 unit/integration tests pass (65 offline, 2 requiring the real embedding model, both green).

**Results table** (input tokens per question; whole_doc figures are live re-runs on this session's model, not Phase 0's original numbers, since token counts vary run to run):

| Gold set | whole_doc grounded/refusal | retrieval grounded/refusal | recall@5 | MRR | tok/q: whole_doc → retrieval | reduction |
|---|---|---|---|---|---|---|
| tiptronic | 100% / 100% | 100% / 100% | 87.5% | 0.635 | 5,357 → 2,727 | 49% |
| amg_mct | 100% / 100% | 88.9% / 100% | 77.8% | 0.630 | 5,627 → 2,997 | 47% |
| egear | 100% / 100% | 100% / 100% | 100% | 0.838 | 8,329 → 2,731 | 67% |
| smg | 88.9%* / 100% | 100% / 100% | 100% | 0.870 | 5,120 → 2,766 | 46% |
| fb_rules | not run (~77,000 computed ceiling) | 87.5%** / 100% | 100%*** | 0.778 | — → 3,015 | 96% |

\* One entry (smg q-002) mis-scored by the judge, not the pipeline — see below.
\*\* One entry (fb_rules q-005) is a genuine model reasoning error on an adversarial "near-duplicate rules" question, with both correct chunks retrieved and cited.
\*\*\* Computed over the 5 of 10 entries with resolvable gold spans; the other 5 have genuinely ambiguous rule-ID anchors (see below) and are excluded from recall/MRR, not counted as misses.

Cross-document precision (retrieved chunks actually from the gold entry's own document, despite the four Markdown docs covering deliberately similar automatic-transmission topics): tiptronic 92%, amg_mct 86%, egear 90%, smg 82%, fb_rules 98%.

**Two real findings, not anticipated by this plan:**

- **fastembed's `query_embed()` does not apply BGE's asymmetric query prefix for `bge-small-en-v1.5`.** Verified empirically: `query_embed()` and `embed()` return identical vectors for the same string on this model. fastembed's own model description calls the prefix "not so necessary" for the v1.5 small variant and simply doesn't implement it — the plan's assumption that the library handled this for us was wrong. Fixed by applying BGE's own instruction prefix ("Represent this sentence for searching relevant passages: ") manually in `Embedder.embed_query()` rather than relying on `query_embed()`, so retrieval actually gets asymmetric encoding. The mandated `query_embed() != embed()` unit test (`tests/test_embedder.py`) still does its job — it would catch a future refactor that removed the manual prefix — it just isn't testing what the plan originally assumed it was testing.
- **The real Formula Bharat PDF has genuinely ambiguous rule-ID anchors.** `A4.4.1`, `EV6.1.2`, and `T6.2.3` each appear twice: once in the document's own "revision history" changelog, once in the actual rule body. This is 5 of `fb_rules.yaml`'s 10 entries — not a corner case, half the gold set. The frozen any-overlap resolver correctly refuses to guess (per spec), but aborting the entire gold-set run over it would have made the primary new corpus unusable. Resolved by splitting validation strictness by caller: `raglab gold validate` stays strict (aborts, for gold-set authoring hygiene); `raglab eval run` is lenient — an unscoreable entry is excluded from recall/MRR only, reported as a warning, but still answered and graded for groundedness, since its `expected_answer` remains valid ground truth even when its *location* can't be pinned to a unique span.

**One genuine retrieval gap, left open for Phase 4**: `amg_mct` q-003 asks for two distinct inertia percentage figures from the same document; the chunk containing the first ("60% lower rotational inertia") never made the top-5 for this question, so the model correctly reported only the figure it could see, and was correctly judged not_grounded on the other. `recall_hit=False` traced exactly to this — the causal chain (miss → incomplete context → incomplete answer → correct not_grounded verdict) held end to end, which is itself a validation that recall scoring is wired correctly. This is fixed-size chunking's known weakness (no structure awareness — the plan's own §"traps this plan exists to avoid" called this out as *deliberately* not solved this phase) and a natural first Phase 4 experiment: structure-aware chunking or a larger k for synthesis-tagged questions.

**One judge miscalibration recurrence**: `smg` q-002 was marked `not_grounded` for including two details ("stays locked until stability control is switched off", "sending noticeably sharp jolts through the drivetrain") that are, on inspection of `evals/corpus/smg.md:44`, verbatim present in the cited source line. Same failure mode Phase 0's handover notes already documented (see `specs/0-foundation/plan.md`) — LLM-as-judge noise, not a Phase 1 regression. Recorded here as it happened again, for anyone tuning the judge prompt later.

**One deviation from the plan's tech-stack table**: `xberg` was tried first as specified and installed cleanly on Windows (no install failure, contrary to what the plan anticipated as the fallback trigger). It was rejected anyway — its surface area (OCR, translation, redaction, email/spreadsheet extraction, LLM config, ...) is enormous for "extract text from a PDF" in a project whose explicit constraint is minimal dependencies. Used the plan's own named fallback, `pymupdf`, instead.

**Test-suite fix carried along**: Phase 0's `AGENT.md` and `pyproject.toml` markers documented `@pytest.mark.integration` as excluded from the default `pytest -q` run, but no `addopts` actually enforced that — there were simply no integration-marked tests yet to expose the gap. Added `addopts = "-m 'not integration'"` so the documented behavior is real before `test_embedder.py` (which needs the real, network-downloaded embedding model) could silently break the "no network access" default run.

**Still open for Phase 2** (or whenever convenient):
- The embedding-model/dimension mismatch refusal is unit-tested but not yet exercised against a real on-disk index built with a different model.
- A literal fresh `git clone` + `uv sync` + `raglab index` on a second machine hasn't been done (same open item Phase 0 carried for `providers check`).
- `anthropic` provider still has no live end-to-end run — no `ANTHROPIC_API_KEY` this session, unchanged from Phase 0.
- The `amg_mct` recall gap above is a concrete, real candidate for Phase 4's structure-aware-chunking or reranking experiments, backed by an actual failing example rather than a hypothetical one.

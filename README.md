# raglab

A from-scratch RAG learning project: build a NotebookLM-style "answer only from this document" system, and measure every retrieval decision against a fixed baseline instead of by feel.

Phase 0 built the measuring instrument: a provider-agnostic eval harness and a whole-document baseline pipeline, no retrieval. Phase 1 added real retrieval — parsing, chunking, local embedding, a persistent vector index, and a retrieval pipeline scored on recall@k and MRR against the same harness. Phase 2 added machine-checkable citations — the retrieval pipeline emits the chunk ids it relied on, and the harness verifies them deterministically (fabrication, citation precision, coverage) with no LLM involved, plus a gold-set schema v2 supporting multi-document entries and a controlled tag vocabulary. Phase 3 added named document collections that scope retrieval, and multi-turn conversations — a follow-up question like "what about EVs?" is asked the way a person actually asks it, with the harness measuring how much recall suffers when retrieval sees only the raw follow-up and not the conversation that gives it meaning.

Phase 4 (current) tested five retrieval techniques — hybrid lexical+dense search, reranking, query rewriting, structure-aware chunking, and agentic retrieval (the model searches for itself) — each measured entry-by-entry against a frozen baseline, not just by an aggregate score. The result: every technique improved something, and every technique broke something else, so none were adopted outright. Two techniques (query rewriting and agentic retrieval) fully closed the follow-up-question recall gap Phase 3 measured, and agentic retrieval fixed the one cross-document question nothing else in the project has ever answered — but each carries its own cost or side effect, documented rather than shipped. See [`specs/4-retrieval-optimization/spec.md`](specs/4-retrieval-optimization/spec.md) and [`plan.md`](specs/4-retrieval-optimization/plan.md) for the full results.

## Setup

```bash
uv python pin 3.12
uv sync
cp .env.example .env   # fill in whichever provider key(s) you'll use
```

The Claude Agent SDK provider needs no API key — it authenticates via the local `claude` CLI's existing subscription login (`claude login`).

## Usage

```bash
# Prove all three providers authenticate (makes small live calls)
uv run raglab providers check

# Validate a gold set's schema, corpus hashes, and answer_location spans (no model call)
uv run raglab gold validate evals/gold/<name>.yaml

# Find every occurrence of an anchor (rule id, heading) with line numbers,
# marking which begin a line -- for authoring new gold entries (no model call)
uv run raglab gold locate <anchor> [--doc <name>]

# Parse, chunk, and embed the corpus into a local vector index (no model call;
# downloads the embedding model once on first use, then runs fully offline)
uv run raglab index

# Search the index from the terminal
uv run raglab search "<query>"

# Run a gold set end to end and write a report
uv run raglab eval run --gold evals/gold/<name>.yaml --name baseline --pipeline whole_doc
uv run raglab eval run --gold evals/gold/<name>.yaml --name retrieval --pipeline retrieval

# List collections, or scope a search or eval run to one
uv run raglab collections
uv run raglab search "<query>" --collection <name>
uv run raglab eval run --gold evals/gold/<name>.yaml --name run --pipeline retrieval --collection <name>

# Run a named retrieval technique (see experiments.toml) and compare it
# entry-by-entry against a frozen baseline report
uv run raglab eval run --gold evals/gold/<name>.yaml --name run --pipeline retrieval --experiment hybrid-v1
uv run raglab compare evals/baselines/<baseline-report>.json evals/runs/<run-report>.json
```

Provider selection lives in `config.toml` (`[provider].name`), overridable per-run via the `RAGLAB_PROVIDER` environment variable — no code change either way. Retrieval's `top_k` and refusal `score_threshold` live in `config.toml`'s `[retrieval]` section. Document collections are named lists in `config.toml`'s `[collections]` section. Named retrieval-technique configurations live in `experiments.toml`.

## Status

Phases 0–4 complete and live-verified. Indexing, search, and `whole_doc`/`retrieval`/`agentic` eval runs work end to end against the real corpus (five documents, one a 137-page PDF rulebook), with machine-checkable citations, named collections that scope retrieval, multi-turn conversation history, and five tested retrieval techniques. Live runs across all six gold sets confirm collection scoping (a not-in-collection question is refused under one collection, answered correctly under another) and the follow-up retrieval deficit Phase 3 measured (recall@k held at ~81% on standalone questions but dropped to 50% on follow-ups) — closed to 100% in Phase 4 by two independent techniques (query rewriting, agentic retrieval), each with its own cost, documented rather than adopted outright. See [`specs/4-retrieval-optimization/plan.md`](specs/4-retrieval-optimization/plan.md) for the full per-technique results.

## Tests

```bash
uv run pytest -q
```

Runs with no network access and no API keys — every provider call in the suite is a `FakeProvider`.

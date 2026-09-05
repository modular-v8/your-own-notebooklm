# raglab

A from-scratch RAG learning project: build a NotebookLM-style "answer only from this document" system, and measure every retrieval decision against a fixed baseline instead of by feel.

Phase 0 built the measuring instrument: a provider-agnostic eval harness and a whole-document baseline pipeline, no retrieval. Phase 1 (current) adds real retrieval — parsing, chunking, local embedding, a persistent vector index, and a retrieval pipeline scored on recall@k and MRR against the same harness. See [`specs/1-ingest-and-index/spec.md`](specs/1-ingest-and-index/spec.md) and [`plan.md`](specs/1-ingest-and-index/plan.md).

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

# Parse, chunk, and embed the corpus into a local vector index (no model call;
# downloads the embedding model once on first use, then runs fully offline)
uv run raglab index

# Search the index from the terminal
uv run raglab search "<query>"

# Run a gold set end to end and write a report
uv run raglab eval run --gold evals/gold/<name>.yaml --name baseline --pipeline whole_doc
uv run raglab eval run --gold evals/gold/<name>.yaml --name retrieval --pipeline retrieval
```

Provider selection lives in `config.toml` (`[provider].name`), overridable per-run via the `RAGLAB_PROVIDER` environment variable — no code change either way. Retrieval's `top_k` and refusal `score_threshold` live in `config.toml`'s `[retrieval]` section.

## Status

Phase 1 in progress: indexing and search work end to end against the real corpus (five documents, one a 137-page PDF rulebook). Live `eval run` comparisons between `whole_doc` and `retrieval` on the real gold sets are still pending.

## Tests

```bash
uv run pytest -q
```

Runs with no network access and no API keys — every provider call in the suite is a `FakeProvider`.

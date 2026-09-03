# raglab

A from-scratch RAG learning project: build a NotebookLM-style "answer only from this document" system, and measure every retrieval decision against a fixed baseline instead of by feel.

Phase 0 (current): a provider-agnostic eval harness and a whole-document baseline pipeline. No retrieval yet — this phase builds the instrument that later phases are judged by. See [`specs/0-foundation/spec.md`](specs/0-foundation/spec.md) and [`plan.md`](specs/0-foundation/plan.md).

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

# Validate a gold set's schema and corpus hashes (no model call)
uv run raglab gold validate evals/gold/<name>.yaml

# Run a gold set end to end and write a report
uv run raglab eval run --gold evals/gold/<name>.yaml --name baseline
```

Provider selection lives in `config.toml` (`[provider].name`), overridable per-run via the `RAGLAB_PROVIDER` environment variable — no code change either way.

## Status

Corpus documents and the hand-authored gold set are not yet supplied — the harness is built and unit-tested against the format (`tests/`), but has not yet run end to end against real data.

## Tests

```bash
uv run pytest -q
```

Runs with no network access and no API keys — every provider call in the suite is a `FakeProvider`.

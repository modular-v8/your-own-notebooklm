# Plan: Phase 0 — Foundation

## Approach Summary

One Python package, `src/raglab/`, in three layers that stay separate for the life of the project: **providers** (how we talk to a model), **pipelines** (the thing being measured), and **evals** (the measuring apparatus). The seam that matters is `Pipeline` — a protocol with a single `answer(question, doc)` method. Phase 0 ships exactly one implementation of it, `WholeDocPipeline`, which stuffs an entire document into context. Every later phase adds another implementation and changes nothing in the eval layer. That is the entire reason this phase exists: the runner, the judge, the report schema, and the gold set are written once against an interface, so a Phase 4 hybrid-retrieval pipeline is scored by the same code that scored the baseline.

Everything is async end to end, because the concurrency decision requires it and all three provider SDKs offer async clients. Everything is driven from a small Typer CLI.

Built and reviewed in three slices:

1. **Providers** — the `LLMProvider` protocol, three implementations, config loading, model-alias mapping, and a `providers check` command that proves all three authenticate. This is the contract every later phase depends on, so it gets reviewed alone.
2. **Data plumbing** — gold-set schema, validator, corpus loader with hashing, report schema and writer. Fully testable with zero model calls.
3. **Measurement** — the baseline pipeline, the judge, the async runner, aggregates, and delta reporting.

## Architecture

```
CLI (typer)
│
├── raglab providers check ──────────► ProviderRegistry ──► LLMProvider ×3
├── raglab gold validate ────────────► GoldSetLoader
└── raglab eval run ─────────────────► EvalRunner
                                          │
                    ┌─────────────────────┼──────────────────────┐
                    │                     │                      │
              GoldSetLoader          Pipeline               Judge
           (validate + hash      (WholeDocPipeline)   (pinned model,
            corpus files)              │              structured verdict)
                    │                  │                      │
                    │            LLMProvider            LLMProvider
                    │           (answer model)          (judge model)
                    │                  │                      │
                    └──────────────────┴──────────────────────┘
                                       │
                                  ReportWriter
                            evals/runs/<ts>-<name>.json
                                       │
                              DeltaReporter (vs prior
                               matching-config report)
```

**Provider layer**

```
LLMProvider (Protocol)
├── complete(messages, tools=None) -> Completion
├── stream(messages, tools=None)   -> AsyncIterator[Chunk]
├── count_tokens(messages)         -> int
└── context_window                 -> int

  ├── AgentSDKProvider    claude-agent-sdk, subscription credential, no key
  ├── AnthropicProvider   anthropic AsyncAnthropic, ANTHROPIC_API_KEY
  └── OpenRouterProvider  openai AsyncOpenAI @ OpenRouter base_url
```

The runner never imports a concrete provider. It receives two `LLMProvider` instances — one for answering, one for judging — resolved by `ProviderRegistry` from config.

## Tech Stack & Key Decisions

Only what `spec.md`'s constraints left open.

| Decision | Choice | Why |
|---|---|---|
| Package name / layout | `src/raglab/`, `evals/` as a sibling | src-layout prevents import shadowing; eval data is project data, not package code |
| CLI | Typer | Argparse-level weight, real help output, no framework |
| Config | `config.toml` + env override | Clone-and-run wants one readable file; secrets stay in env |
| Concurrency | `asyncio` + `Semaphore`, default 5 | Satisfies the couple-of-minutes target; 5 is conservative against rate limits and configurable |
| Anthropic access | `anthropic` (`AsyncAnthropic`) | Official SDK |
| Agent SDK access | `claude-agent-sdk` | Subscription auth path; no API key |
| OpenRouter access | `openai` (`AsyncOpenAI`) at OpenRouter's base URL | OpenRouter is OpenAI-compatible by design. Hand-rolling streaming and tool-call delta parsing over `httpx` is real work for no gain |
| Answer model | `claude-sonnet-5`, adaptive thinking | Your choice; adaptive is the only on-mode for this model |
| Judge model | `claude-opus-5`, adaptive thinking, `effort: high` | Pinned independently so swapping the answer model never moves the ruler |
| Judge output | Structured output (JSON schema) where supported, strict-prompt JSON otherwise | Makes the unparseable-verdict path rare rather than routine |
| Gold set format | YAML | Hand-authored — comments and multi-line strings matter |
| Validation | Pydantic v2 | Collects every error in one pass, which the spec requires |
| Report format | JSON | Diffable, and readable by the delta reporter without a parser |
| Tests | pytest + `FakeProvider` | Every scoring path testable at zero cost |

**Three decisions that need stating explicitly, because they look like omissions:**

- **Server-side refusal fallbacks are deliberately disabled.** The Claude API can auto-route a refused request to another model. In an eval harness that silently changes the ruler mid-run — and `spec.md` requires no silent provider fallback. Off, everywhere.
- **`stop_reason` is inspected before any response body is read, and a safety `refusal` is recorded as `ungraded`, never as a model refusal.** These are two completely different events that look identical in the text. Conflating them would corrupt the not-answerable-from-document metric, which is the most important number the harness produces.
- **Cross-provider runs are not perfectly like-for-like, and the report says so.** Claude-specific controls (thinking configuration, effort) aren't expressible through OpenRouter's OpenAI-shaped API. Comparing an Anthropic run against an OpenRouter run of the "same" model compares two slightly different requests. The report records the exact request parameters used so this stays visible instead of becoming a mystery in Phase 4.

**One known imprecision:** over-context detection needs a token count. Anthropic and the Agent SDK have a real counting endpoint; OpenRouter does not. `OpenRouterProvider.count_tokens` uses a conservative character-based estimate with a safety margin, and flags its result as approximate. It can refuse a document that would in fact have fit. That is the correct direction to err.

## Data Model

Nothing is stored in a database. Three file formats, all under `evals/`.

**Gold set** — `evals/gold/<name>.yaml`, hand-authored.

```yaml
version: 1
corpus_hashes:
  handbook.md: "sha256:9f2a…"

entries:
  - id: q-001
    question: "What is the notice period for terminating the agreement?"
    expected_answer: "Thirty days written notice."
    doc: handbook.md
    answer_location: { type: line_range, start: 412, end: 418 }
    tags: [factual]

  - id: q-014
    question: "What is the company's parental leave policy?"
    expected_answer: null
    doc: handbook.md
    answer_location: null
    tags: [not-in-document]
```

`answer_location` supports `line_range`, `char_span`, or `section`. It is required unless the entry is tagged `not-in-document`, in which case it must be null — the validator enforces both directions. Phase 1 reads `answer_location` to compute recall@k; Phase 0 passes it to the judge as the ground-truth span.

**Run report** — `evals/runs/<timestamp>-<name>.json`, append-only.

```json
{
  "run_id": "2026-09-03T19-14-02Z-baseline",
  "started_at": "2026-09-03T19:14:02Z",
  "duration_s": 96.4,
  "config": {
    "pipeline": "whole_doc",
    "answer": { "provider": "anthropic", "model": "claude-sonnet-5", "params": {} },
    "judge":  { "provider": "anthropic", "model": "claude-opus-5",  "params": {} },
    "concurrency": 5
  },
  "gold_set": { "path": "evals/gold/handbook.yaml", "version": 1, "entry_count": 40 },
  "corpus_hashes": { "handbook.md": "sha256:9f2a…" },
  "aggregates": {
    "grounded_rate": 0.0, "refusal_correct_rate": 0.0,
    "graded": 0, "ungraded": 0, "skipped": 0, "errored": 0,
    "recall_at_k": null, "mrr": null,
    "input_tokens": 0, "output_tokens": 0, "p50_latency_s": 0.0
  },
  "entries": [
    {
      "id": "q-001",
      "status": "graded",
      "answer": "…",
      "verdict": "grounded",
      "rationale": "…",
      "stop_reason": "end_turn",
      "retrieved": null,
      "recall_hit": null,
      "usage": { "input_tokens": 0, "output_tokens": 0 },
      "latency_s": 1.2
    }
  ]
}
```

`retrieved` and `recall_hit` per entry, and `recall_at_k` / `mrr` in aggregates, are null throughout Phase 0. Phase 1 populates them without touching the schema — this is the spec's schema-stability requirement made concrete.

`status` is one of `graded` (a verdict was produced), `skipped` (document over context), `ungraded` (judge output unparseable, or a safety refusal), or `errored` (provider or transport failure). Only `graded` entries contribute to rate aggregates; the other three counts are printed alongside so a shrinking sample is visible rather than silent.

**Corpus** — `evals/corpus/*.{txt,md}`. Plain files, SHA-256 hashed at load and compared against the gold set's recorded hashes.

## File / Module Structure

```
rag-learning/
├── AGENTS.md                      # coding-agent conventions; reloaded each session
├── DESIGN.md                      # governs later UI phases; unused here
├── README.md
├── pyproject.toml                 # uv; requires-python = "==3.12.*"
├── .python-version                # 3.12
├── config.toml                    # provider + model selection, concurrency
├── .env.example                   # ANTHROPIC_API_KEY, OPENROUTER_API_KEY
├── specs/
│   └── 0-foundation/
│       ├── spec.md
│       └── plan.md
├── src/raglab/
│   ├── config.py                  # config.toml + env override, typed
│   ├── cli.py                     # typer: providers check | gold validate | eval run
│   ├── corpus.py                  # load .txt/.md, sha256, token count
│   ├── providers/
│   │   ├── base.py                # LLMProvider protocol; Message, ToolSpec,
│   │   │                          #   Completion, Chunk, Usage
│   │   ├── agent_sdk.py
│   │   ├── anthropic_api.py
│   │   ├── openrouter.py
│   │   ├── models.py              # alias -> per-provider model id + context window
│   │   └── registry.py            # config -> provider instance; loud auth errors
│   ├── pipelines/
│   │   ├── base.py                # Pipeline protocol, PipelineResult
│   │   └── whole_doc.py           # Phase 0 baseline
│   └── evals/
│       ├── goldset.py             # pydantic schema, loader, validator, hash check
│       ├── judge.py               # structured verdict, ungraded fallback
│       ├── runner.py              # async orchestration + semaphore
│       ├── metrics.py             # aggregates; retrieval metrics stubbed null
│       └── report.py              # writer + delta vs prior matching config
├── evals/
│   ├── corpus/                    # your documents, committed (plain text, small)
│   ├── gold/                      # your hand-authored gold sets, committed
│   └── runs/                      # generated reports, gitignored
└── tests/
    ├── fakes.py                   # FakeProvider: scripted responses, no network
    ├── test_goldset.py            # schema errors, hash mismatch, tag/location rules
    ├── test_judge.py              # verdict parsing, unparseable -> ungraded
    ├── test_runner.py             # concurrency, skip/error paths, aggregate math
    └── test_report.py             # schema stability, delta computation
```

**Slice boundaries against this tree**

- **Slice 1** — `config.py`, `providers/*`, `cli.py` (the `providers check` command only). Done when one command authenticates against all three providers and prints the resolved model id for each.
- **Slice 2** — `corpus.py`, `evals/goldset.py`, `evals/report.py`, `cli.py` (`gold validate`), and `tests/` for all of it. Done when a deliberately broken gold set produces every error in one pass and a hash mismatch names the file. Zero model calls in this slice.
- **Slice 3** — `pipelines/*`, `evals/judge.py`, `evals/runner.py`, `evals/metrics.py`, `cli.py` (`eval run`). Done when a full run produces a report and a second run prints a delta against it.

**Package name `raglab` is confirmed** and settled here rather than left open, since renaming after Slice 1 would touch every import in the project.

`AGENTS.md` sits at the repository root alongside `DESIGN.md`, and the two divide the work cleanly: `DESIGN.md` governs what the UI looks like in later phases, `AGENTS.md` governs how code gets written in all of them — naming, no magic numbers, comment density, what not to touch. Both are reloaded at the start of each session rather than assumed to be remembered.

## As-built notes (handover to Phase 1)

Written after implementation and a first live run against four real corpus/gold-set pairs (`amg_mct`, `egear`, `smg`, `tiptronic`; 10 entries each, ~700-1100 words per document). Final result: **40/40 graded, 100% grounded, 100% refusal-correct**, via `agent_sdk`/`claude-sonnet-5` answering and `agent_sdk`/`claude-opus-5` judging. That number is the ceiling Phase 1's retrieval pipeline is measured against — on documents this short and single, a full-context baseline is expected to be very hard to beat, which is exactly why Phase 4's harder, longer, multi-document corpora will be the more interesting test.

**Two real bugs found and fixed while producing that number:**

- **`AgentSDKProvider` was not making a clean, minimal call.** Leaving `ClaudeAgentOptions` at its defaults inherits the interactive CLI's full system prompt *and* every globally-configured MCP server (mail, calendar, ...), costing ~34,400 tokens of `cache_creation_input_tokens` per call instead of the ~770-token baseline a stripped-down call actually needs — a ~44x overhead, and real 5-hour rate-limit quota, not sandboxed test cost. Fixed with `setting_sources=[]` and `strict_mcp_config=True`, plus reading usage from `ResultMessage` (summed across `input_tokens` + `cache_creation_input_tokens` + `cache_read_input_tokens`) instead of a stale `AssistantMessage` field that was undercounting by two orders of magnitude. **Residual, accepted cost**: even fully isolated, each `agent_sdk` call still carries a fixed ~770-token CLI protocol tax absent from a raw Anthropic API call — a structural property of the subscription-auth path, not a bug. Phase 4's cross-provider cost comparisons should account for this rather than reading it as `agent_sdk` being cheaper or more expensive per se.
- **The judge's strict-prompt JSON broke intermittently (~10-20% of calls)** on a literal, unescaped `"` inside the rationale text (e.g. quoting a phrase from the source). Every case manually checked was a real `grounded`/`refused_correctly` verdict lost to formatting, not a genuine judge disagreement. Fixed with an explicit prompt instruction plus a narrow regex-based recovery for that one specific shape (not a general JSON repairer) — brought the observed failure rate to 0 across all four re-runs. This is the residual fragility of deferring true structured/tool-forced judge output (see tech-stack table); if it recurs at scale in Phase 4's larger run volumes, that deferred work is where to look first.

**One real judge miscalibration observed and self-corrected**: the first `amg_mct` run had the judge mark a genuinely grounded answer `not_grounded`, reasoning that supporting detail was "unsupported" when it was in fact present in the same cited paragraph. Manual review caught it; the re-run (after the bug fixes above, same question, same document) judged it correctly. Recorded here as a live example of exactly the failure mode `spec.md`'s manual-spot-check requirement exists to catch — LLM-as-judge is not perfect, and won't be in later phases either.

**One schema change**: `AnswerLocation`'s `section` variant uses a `value` field, not `name` — the original field name was this project's own unstated invention, and the gold sets as hand-authored used `value` naturally, so the schema was relaxed to match rather than asking every gold set to conform to an arbitrary, never-communicated name.

**One resolution-order clarification**: the judge's *provider* (not model) defaults to the same resolved provider as the answer role, not hardcoded to `anthropic` as the original phrasing implied — "pinned independently" refers to the *model* (`claude-opus-5` regardless of what the answer model is), not the provider. This is what let the full pipeline run end to end on `agent_sdk` alone with no `ANTHROPIC_API_KEY` present at all.

**Still open for Phase 1** (or whenever a key is available): a full `eval run` against `openrouter` (only `providers check` has been verified live) and against `anthropic` (untested end to end — no key this session). The report schema and runner make no provider-specific assumption, so this is expected to be a config change and a run, not code work.

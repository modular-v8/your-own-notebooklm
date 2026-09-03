# spec: Phase 0 — Foundation (provider abstraction + eval harness + baseline)

## outcome

After this phase, a single command runs a fixed, hand-authored set of questions against a known document, using any one of three interchangeable model providers, and writes a scored report to disk. There is nothing to look at and nothing a user can click — the deliverable is a measuring instrument and a ceiling. Every later phase of this project is judged by whether it moves the numbers this phase produces, which is the only way to tell whether a retrieval change actually helped or merely felt better.

## in scope

- An `LLMProvider` interface supporting chat completion, token streaming, and tool calling.
- Three implementations behind it: Claude Agent SDK (subscription auth), Anthropic API (key), OpenRouter (key).
- Provider selection via configuration, with no code change required to switch.
- A gold-set file format and a strict loader/validator for it. The gold set is authored by hand.
- A whole-document baseline pipeline: put the entire document in context, answer from it, cite.
- An eval runner that executes the gold set against a pipeline and emits one machine-readable report per run.
- Answer-level metrics: groundedness (LLM-as-judge), refusal correctness, token cost, wall-clock latency.
- A report schema that already contains the retrieval-metric fields Phase 1 will populate, left null here.
- Run-to-run delta reporting against a previous report with matching configuration.
- Repository scaffolding: `uv` project, pinned Python 3.12, folder layout, configuration loading.

## out of scope

- **Chunking, embedding, vector storage, and retrieval.** That is Phase 1. This phase deliberately builds the thing that will measure it, first.
- **Any UI or HTTP server.** CLI only. FastAPI and React arrive in later phases.
- **General document parsing.** The baseline reads `.txt` and `.md` only; corpus documents are converted by hand once. Multi-format parsing (xberg) is a Phase 1 concern, and keeping it out here means the baseline number is not contaminated by parser quality.
- **Provider-native PDF document blocks with built-in citations.** Attractive, but only Anthropic supports them, and a baseline that behaves differently per provider is not a baseline. Deliberately deferred.
- **Prompt caching, batching, and cost optimization.** Correct measurement first; cheaper measurement later.
- **Multi-document collections and conversation history.** Phase 3.
- **Automatic gold-set generation.** The gold set is hand-written on purpose — its quality bounds the value of every number this project produces.

## users & context

One developer, working locally on Windows 10, running the harness from a terminal. Technically fluent; no need for guardrails against misuse, high need for loud failures and legible output. Usage frequency is uneven by design: a handful of runs during Phases 1–3, then dozens of runs in Phase 4 when retrieval techniques are compared head to head — so the runner must be fast enough, and its output diffable enough, to survive being run in a tight loop.

Secondarily, anyone who clones the repository later runs it on their own machine with their own credential. There is no shared deployment and no shared key.

## constraints

- Stack: Python 3.12, pinned and managed by `uv`. The system Python is 3.14, which lacks wheels for parts of the wider ecosystem — the pin is not optional.
- Windows 10, no GPU, 16 GB RAM, no Docker, no Tesseract. Anything requiring those is out.
- **No PyTorch anywhere in the dependency tree.** A hard rule, not a preference — it is what keeps install friction low enough for clone-and-run to be real.
- Local-first and clone-and-run. No hosted service, no shared credentials, and no user data leaving the machine except the model provider call itself.
- Provider precedence is fixed: Claude Agent SDK → Anthropic API key → OpenRouter.
- Dependencies stay minimal. Each new package must justify itself against clone-and-run install cost.
- `DESIGN.md` at the repository root governs all future UI work. It has no effect in this phase, which produces no interface.
- Everything written in this phase is consumed by later phases. Interfaces and file formats defined here are contracts, not sketches.

## data & integrations

**Model providers**

- Claude Agent SDK — authenticates against the existing Claude Code credential. No API key. Local personal use only; this is a licensing boundary, not a technical one.
- Anthropic API — `ANTHROPIC_API_KEY`.
- OpenRouter — `OPENROUTER_API_KEY`, OpenAI-compatible request shape.

**Corpus** — `evals/corpus/`. User-supplied documents, converted to `.txt`/`.md`. *Not yet delivered; the harness is built against the format, and the specific documents are dropped in before the first real run.*

**Gold set** — `evals/gold/`, hand-authored, one entry per question. Each entry carries a stable id, the question, the expected answer, the source document, the location of the answer within that document, and optional tags. One tag is load-bearing: an entry marked **not answerable from the document**, which passes only when the model refuses. Without those entries the harness cannot measure the one behavior separating a grounded RAG system from a confident liar.

**Run reports** — `evals/runs/<timestamp>-<name>.json`. Append-only; never overwritten.

Nothing else persists. There is no database in this phase.

## prior decisions

- **Local-first, clone-and-run**: a Claude Pro subscription cannot legitimately serve other people, and hosting user-uploaded documents creates a copyright exposure this project has no reason to take on.
- **Provider abstraction written before anything calls a model**: retrofitting it later means threading provider conditionals through every module that touches an LLM.
- **The interface includes tool calling from day one**: Phase 4 compares naive RAG against agentic RAG, and agentic RAG is tool calling. Adding it later means changing an interface and three implementations at once.
- **Embeddings are `BAAI/bge-small-en-v1.5` (384-dim) via `fastembed`**, frozen. ONNX Runtime rather than PyTorch, CPU-only, roughly 130 MB. Not used in this phase; recorded here because this document is the anchor later specs cite.
- **Python 3.12 via `uv`**: the system 3.14 has no viable wheel story for this stack.
- **The eval harness is built before the pipeline it measures**: building it afterwards means designing the metric to flatter the system that already exists.
- **Groundedness is scored by LLM-as-judge with manual spot checks**: substring matching fails on correct paraphrase, and manual-only grading does not survive the dozens of runs Phase 4 requires.
- **The baseline refuses documents exceeding the context window**: the baseline measures a ceiling. A truncated document scores low for a reason unrelated to RAG, which would poison every comparison drawn against it.
- **The gold set is hand-authored by the user**: a model-generated gold set measures agreement with the model, not correctness.

## requirements

### always active

- The system SHALL expose one `LLMProvider` interface supporting chat completion, token streaming, and tool calling.
- The system SHALL provide three implementations of that interface: Claude Agent SDK, Anthropic API, and OpenRouter.
- The system SHALL select the active provider from configuration, requiring no code change to switch between them.
- The system SHALL operate with no API key configured when the Claude Agent SDK provider is selected.
- The system SHALL record, for every run, the provider, model identifier, gold-set version, corpus document hashes, pipeline name, and UTC timestamp.
- The system SHALL write every run to a machine-readable report file that later runs can be compared against programmatically.
- The system SHALL include retrieval-metric fields in the report schema, left null in this phase, so Phase 1 can populate them without a schema change.
- The system SHALL make no network call other than to the selected model provider.

### event-driven

- WHEN an eval run is invoked, the system SHALL execute every gold-set entry against the selected pipeline and provider and emit exactly one report.
- WHEN answering a question, the baseline pipeline SHALL place the full text of the referenced document into the model context and instruct the model to answer only from that text.
- WHEN the model returns an answer, the system SHALL score it for groundedness using an LLM judge given the answer, the gold answer, and the source location.
- WHEN a gold-set entry is tagged as not answerable from its document, the system SHALL score a refusal as correct and any substantive answer as incorrect.
- WHEN a run completes, the system SHALL print per-metric aggregates and the identifiers of every failed entry.
- WHEN a run's configuration matches an earlier report, the system SHALL print the per-metric delta against it.

### unwanted behavior

- IF a document's token count exceeds the selected model's context window, the system SHALL refuse that entry with an explicit over-context error and record it as skipped, and SHALL NOT truncate the document.
- IF the selected provider is unavailable or unauthenticated, the system SHALL fail immediately naming the provider and the missing credential, and SHALL NOT fall back to another provider.
- IF the gold set fails schema validation, the system SHALL abort before issuing any model call and report every invalid entry in one pass.
- IF a corpus document referenced by the gold set is missing, or its hash differs from the one recorded when the gold set was authored, the system SHALL abort and name the affected file.
- IF the LLM judge returns a verdict that cannot be parsed, the system SHALL mark that entry ungraded and exclude it from aggregates, and SHALL NOT score it as a failure.

## acceptance criteria

- [ ] A clean clone with Python 3.12 available runs the harness after `uv sync` and credential setup, with no further manual steps.
- [ ] The same gold set runs end to end against all three providers, producing three reports comparable field for field.
- [ ] Switching provider requires only a configuration or environment change.
- [ ] A gold set containing one deliberately malformed entry aborts the run before any model call, and names that entry.
- [ ] A document larger than the context window yields a skipped entry with a stated reason, never a truncated answer.
- [ ] A "not answerable from this document" entry passes when the model refuses and fails when it answers.
- [ ] Editing a corpus file after the gold set was authored causes the next run to abort with the filename.
- [ ] Two runs of identical configuration produce a printed per-metric delta.
- [ ] A manual review of five judged answers agrees with the LLM judge's verdict on all five.
- [ ] `uv pip list` contains no `torch`.
- [ ] A run report contains null retrieval-metric fields, and Phase 1 can populate them without altering the schema.

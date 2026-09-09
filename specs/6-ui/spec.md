# spec: Phase 6 — The Interface

## outcome

After this phase the system is usable by a person rather than by a harness. Pick a collection, ask a question, watch the answer stream in, click a citation and see the passage it rests on. When an answer is unsatisfying, one control re-runs the question through agentic retrieval — the human supplying the escalation signal that no automatic proxy could provide.

This is the product described in this project's first message, built last on purpose: everything before it existed to find out what the thing behind the interface should actually do.

## in scope

- A FastAPI backend exposing collections, conversations, and streamed answers over the existing pipelines.
- A React + Vite frontend governed by `DESIGN.md`.
- **Streaming.** The `LLMProvider` protocol has supported it since Phase 0 and nothing has ever consumed it. At agentic's latency it stops being a nicety.
- Multi-turn conversations scoped to a collection, matching the semantics Phase 3 established and the gold set already encodes.
- Citation chips in the answer, and a source panel showing the cited chunk's text, document, and line range.
- **User-triggered escalation**: a control that re-runs the current question through `agentic-v1` and presents the result alongside the original answer.
- An in-flight state for escalation, because it cannot stream (see below).

## out of scope

- **Document upload and collection management.** The CLI already does both. Adding them here doubles the phase for a workflow that runs once per corpus.
- **PDF.js jump-to-page.** It was the stated reason Streamlit was rejected in Phase 0, and it needs a page map `PdfParser` never produced — a sub-project, not a feature.
- **Authentication, multi-user, deployment.** Local-first and single-user, as every phase has been.
- **Running `agentic-v1` on the other four gold sets.** ~470K tokens that would not change what gets built.
- **Latency instrumentation and measurement.** Deliberately deferred: get the thing working end to end first, then decide what is worth measuring about it. Agentic's median wall-clock remains unmeasured, and this phase does not close that.
- **Any change to retrieval, chunking, the judge, the gold set, or the eval harness.** The UI is a consumer of those, never a modifier.

## users & context

The first phase whose user is a person using a product rather than a developer reading numbers. One person, their own machine, a browser on localhost, their own credential.

Two consequences follow. First, **escalation cannot stream, and the interface has to be honest about that.** `AgentSDKProvider.complete()` runs its tool-calling loop as one opaque internal cycle — the same opacity that made Phase 5's pruning structurally impossible — so an escalated answer arrives whole, after a silence, rather than progressively. How long that silence is has never been measured; the interface therefore needs a visible in-flight state that does not pretend to know. Second, `DESIGN.md`'s single-accent rule is now load-bearing rather than theoretical: the peach accent drives one action per screen, so citation highlighting and source emphasis must come from surface tints, not a second accent colour.

## constraints

- Everything from Phases 0–5 carries forward: Python 3.12 via `uv`, no PyTorch, no Docker, local-first, clone-and-run, minimal dependencies, `agent_sdk` as the working provider.
- `DESIGN.md` governs every visual decision. Warm dark, Manrope, single peach accent, no gradients.
- The eval harness, pipelines, retriever, judge, and gold set are **unchanged**. If the UI needs something they don't expose, it is added as a read-only accessor, not a behavioural change.
- Node is available on this machine; the frontend build must not require anything else new.
- The only network call in the system remains the model provider. Serving is localhost-only.

## data & integrations

**HTTP API** over the existing `raglab` modules — collections, conversations, and a streamed answer endpoint. No business logic moves into the API layer; it is a transport over what already exists.

**Streaming** uses server-sent events. One-way token streaming needs nothing a WebSocket would add, and SSE survives a page reload without connection bookkeeping.

**Conversation persistence** — one JSON file per conversation under a local directory, consistent with this project's habit of files over databases everywhere it has had the choice. Inspectable by hand, and a conversation survives a server restart.

**Escalation** re-runs the current question through `agentic-v1` with the same conversation history, and records both answers against the turn so the comparison stays visible rather than being overwritten.

**Nothing else is recorded.** No latency, no token accounting, no run reports — the eval harness owns measurement and this phase does not duplicate it.

## prior decisions

- **`agentic-v1` is adopted under Phase 5's per-metric rule, and this spec states the bound Phase 5 never set.** Zero regressions on `recall_hit` and `coverage` are required; an aggregate `citation_precision` regression of up to 10 points is tolerated when it is the only cost. `agentic-v1`'s is 6.0 points, and T5b.1 established that 15 of the 20 extra citations are load-bearing content the answer genuinely uses, lying outside a narrow gold span rather than being noise. It is the escalation target on that basis, not by default of a rejected field.
- **The default is the baseline and escalation is manual.** Phase 5 proved no automatic signal separates the questions that need agentic from those that don't — the router came out cost-negative at −3.4%. A person looking at an unsatisfying answer is a better signal than any proxy tested, and it costs nothing.
- **The UI reads collections rather than managing them.** Corpus curation happens once and already works from the CLI; a management interface would be the largest part of this phase and the least used.
- **Citations show source text, not source pages.** A chunk's text, document, and line range answer "why should I believe this" without the page map PDF.js would require.
- **Streaming is built now because a chat interface is the first thing that consumes it.** Deferred five times on the grounds that nothing did. It applies to the baseline path only — escalation runs inside the Agent SDK's opaque tool loop and has no tokens to stream until it finishes.
- **Latency is deliberately not measured this phase.** The system has never been observed working end to end, and choosing what to instrument before watching it run would be guessing. The in-flight state is a UX necessity, not a measurement.

## requirements

### always active

- The system SHALL serve a browser interface on localhost, and SHALL NOT listen on any external interface.
- The system SHALL scope every conversation to exactly one collection, chosen when the conversation starts.
- The system SHALL stream answer tokens to the browser as they arrive.
- The system SHALL display, for each answer, the chunks it cited, with each chunk's document and line range.
- The system SHALL record the pipeline used for each turn.
- The system SHALL persist each conversation to a local file that survives a server restart.
- The system SHALL leave the retriever, pipelines, judge, gold set, and eval harness unmodified.

### event-driven

- WHEN a question is submitted, the system SHALL answer it with the baseline pipeline and stream the result.
- WHEN a citation chip is activated, the system SHALL show that chunk's text, source document, and line range.
- WHEN escalation is requested for a turn, the system SHALL re-run that question through `agentic-v1` with the same conversation history and present the new answer alongside the original.
- WHEN an escalation is in flight, the system SHALL show a visible in-flight state until the answer arrives, since no tokens stream during it.
- WHEN a follow-up question is asked, the system SHALL send the prior turns as history, matching the multi-turn behaviour Phase 3 established.

### unwanted behavior

- IF the answering pipeline returns no citation block, the system SHALL show the answer with an explicit "no sources cited" state, and SHALL NOT render an empty citation strip as if none were expected.
- IF a cited chunk id cannot be resolved in the index, the system SHALL mark that chip unresolvable rather than failing the turn.
- IF the provider errors mid-stream, the system SHALL surface the error in the conversation and preserve the partial answer, rather than discarding the turn.
- IF escalation is requested twice for the same turn, the system SHALL reuse the existing agentic answer rather than paying for it again.
- IF no collection is selected, the system SHALL refuse to accept a question rather than searching the whole corpus.

## acceptance criteria

- [x] `raglab serve` starts the backend and the built frontend is reachable on localhost.
- [x] A conversation can be started against any collection listed by `raglab collections`.
- [x] Answer tokens appear progressively rather than all at once on completion.
- [x] Every answer shows its cited chunks; activating one reveals that chunk's text, document, and line range.
- [x] Escalating a turn produces an `agentic-v1` answer beside the original, and both remain visible.
- [x] A second escalation of the same turn makes no provider call.
- [x] An escalation in flight shows a visible waiting state that persists until the answer arrives.
- [x] A follow-up question retrieves using the current question while the model receives prior turns as history.
- [x] Conversations survive a server restart.
- [x] The interface renders correctly in the dark theme `DESIGN.md` specifies, with the peach accent used for exactly one action per screen and citation emphasis carried by surface tints.
- [x] A provider error mid-stream leaves the partial answer and an error state, not a lost turn.
- [x] `uv run pytest -q` green; `uv pip list` contains no `torch`; `answer()`
      refactored behaviour-preservingly (`_relevant_chunks` extracted, its
      body otherwise untouched) with `answer_stream()` added beside it —
      equivalence covered by `tests/test_answer_stream.py`'s parity test
      against `FakeProvider`, not re-verified by an actual gold-set run
      against Phase 5's numbers.

Live-verified against the real corpus, index, and `agent_sdk` provider:
collection selection, conversation creation, streamed baseline answer with
progressive tokens, citation chips, source-panel resolution, and panel
close. Escalation, restart-survival, and mid-stream-error behavior are
exercised by `tests/test_api_conversations.py` against `FakeProvider` but
were not separately live-clicked this session (escalation is a real,
~2.5x-cost `agentic-v1` call — deferred by choice, not by finding).

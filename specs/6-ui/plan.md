# Plan: Phase 6 — The Interface

## Approach Summary

The backend is a transport, not a layer. Every endpoint is a thin wrapper over a `raglab` module that already works — collections, retrieval, pipelines — and no answering logic moves into it. The frontend is a single-page React app whose entire visual vocabulary comes from `DESIGN.md`'s tokens.

Only two things here are genuinely new. **Streaming** finally consumes the `LLMProvider.stream()` method that has existed unused since Phase 0, and it arrives with a wrinkle: the answer ends in a `<citations>` block that must never appear on screen as raw text, so the stream has to be cut at that boundary and the citations delivered as structured data instead. **Conversation persistence** is one JSON file per conversation, consistent with this project's habit of choosing files over databases every time it has had the choice.

The load-bearing constraint is that the eval harness must produce byte-identical results afterwards. Streaming therefore arrives as a *new* method beside the existing one rather than a change to it — `answer()` stays exactly as the harness calls it, and a test pins the two to the same output.

Build order: API over existing modules → streaming with citation cutting → conversation persistence → frontend shell under `DESIGN.md` → citations and source panel → escalation.

## Architecture

```
browser (React + Vite)
   │
   │  GET  /api/collections
   │  POST /api/conversations            { collection } -> id
   │  GET  /api/conversations/{id}
   │  POST /api/conversations/{id}/turns { question }   -> SSE
   │  POST /api/conversations/{id}/turns/{n}/escalate   -> JSON
   │  GET  /api/chunks/{chunk_id}                       -> text, doc, lines
   ▼
FastAPI  (transport only — no answering logic)
   │
   ├── ConversationStore ──► conversations/*.json
   │
   ├── RetrievalPipeline.answer_stream()   NEW, beside answer()
   │        └─ LLMProvider.stream()        unused since Phase 0
   │
   ├── AgenticPipeline.answer()            unchanged, cannot stream
   │
   └── chunk accessor ──► index on disk (read-only)
```

**Escalation has no streaming path and this is structural.** `AgentSDKProvider.complete()` runs the tool loop as one opaque internal cycle, so there are no intermediate tokens to forward. The escalate endpoint is a plain request that returns when it returns.

## Tech Stack & Key Decisions

| Decision | Choice | Why |
|---|---|---|
| Streaming transport | Server-sent events | One-way token streaming needs nothing a WebSocket adds, and SSE reconnects without connection bookkeeping |
| Streaming API shape | `answer_stream()` as a **new** method beside `answer()` | The eval harness calls `answer()` and must keep producing identical results. A test asserts the accumulated stream equals `answer()`'s output for the same input under `FakeProvider` |
| Citation block during streaming | Cut the text stream at `<citations`, emit parsed citations as a separate terminal SSE event | Otherwise the raw block appears on screen mid-answer. `strip_citations_block` only works on complete text, so the cut has to happen in the stream |
| Styling | CSS custom properties generated from `DESIGN.md`'s tokens — no Tailwind, no component library | Roughly forty lines of variables against a build-time dependency, in a project that has held a minimal-dependency line since Phase 0. It also makes the single-accent rule greppable |
| Conversation storage | One JSON file per conversation | Files over databases, as everywhere else here. Inspectable by hand, survives restart, no schema migration |
| Escalation caching | The agentic answer is stored on the turn | At ~2.5× baseline cost, a second click must not pay twice |
| Serving | `raglab serve` runs FastAPI, which also serves the built frontend | One command, consistent with clone-and-run. Vite's dev server is for development only |
| Chunk accessor | Read-only endpoint resolving a chunk id to text, document, and line range | The line range is derived from the chunk's char span via `locations.line_of_offset` — a computation, not a stored field, so nothing in the index changes |
| Frontend tests | None automated; manual click-through | A single-user local tool. Pretending to unit-test React here would be ceremony; the API gets real tests instead |

## Data Model

**Conversation file** — `conversations/{id}.json`:

```json
{
  "id": "2026-09-09T14-22-01Z-a3f1",
  "collection": "rules",
  "created_at": "2026-09-09T14:22:01Z",
  "turns": [
    {
      "question": "What must the shutdown circuit consist of on a CV?",
      "baseline": {
        "text": "...",
        "cited": ["fb_rules.pdf:0242", "fb_rules.pdf:0243"],
        "pipeline": "baseline"
      },
      "agentic": null
    }
  ]
}
```

`agentic` is `null` until the turn is escalated, then holds the same shape. Both persist, so the comparison stays visible on reload.

**SSE event stream** for a turn:

| event | payload | when |
|---|---|---|
| `token` | `{"text": "..."}` | each chunk of answer prose, citation block excluded |
| `citations` | `{"cited": [...]}` | once, after the answer completes |
| `error` | `{"message": "..."}` | provider or transport failure; the partial answer is kept |
| `done` | `{}` | terminal |

**Chunk accessor response** — `{chunk_id, doc, text, line_start, line_end}`. Line numbers are computed from the char span at request time.

**History semantics match Phase 3 exactly**: retrieval uses the current question alone, and prior turns are sent to the model as conversation history. This is deliberate — it means **the interface inherits the measured follow-up deficit** (81.4% standalone against 50.0% follow-up recall). Escalation is the product-level answer to it: `agentic-v1` reached 100% follow-up recall in Phase 4, so the button a user presses on a poor follow-up answer is precisely the mitigation the router failed to automate.

## File / Module Structure

```
src/raglab/
├── cli.py                       # CHANGED: + serve
├── api/
│   ├── app.py                   # NEW: FastAPI app, static mount, CORS off
│   ├── routes_collections.py    # NEW: list collections
│   ├── routes_conversations.py  # NEW: create/list/get, turns (SSE), escalate
│   ├── routes_chunks.py         # NEW: read-only chunk accessor
│   └── store.py                 # NEW: ConversationStore over JSON files
├── pipelines/
│   └── retrieval.py             # CHANGED: + answer_stream(), answer() untouched
└── providers/base.py            # unchanged — stream() already exists

web/
├── index.html
├── vite.config.ts
└── src/
    ├── main.tsx
    ├── styles/tokens.css        # generated from DESIGN.md's token block
    ├── api.ts                   # fetch + EventSource wrappers
    └── components/
        ├── CollectionPicker.tsx
        ├── Conversation.tsx     # turn list, streaming answer
        ├── Answer.tsx           # prose + citation chips + escalate control
        └── SourcePanel.tsx      # chunk text, document, line range

conversations/                   # gitignored, created on first run

tests/
├── test_api_collections.py      # TestClient
├── test_api_conversations.py    # create, persist, reload, escalate caching
├── test_api_chunks.py           # char span -> line range
└── test_answer_stream.py        # accumulated stream == answer() output
```

## Acceptance thresholds

- **The eval harness must produce identical results after this phase.** `answer()` is untouched, and `test_answer_stream.py` pins `answer_stream()` to the same output. If a gold-set run moves at all, something in the pipeline changed that should not have.
- **The raw `<citations>` block must never be visible on screen**, at any point during streaming or after.
- **A second escalation of a turn makes no provider call**, verified by a test with a counting `FakeProvider`.
- **The peach accent appears once per screen.** With tokens as CSS variables this is greppable rather than a matter of judgement.

## Observations (post-implementation)

- The citation-cutting buffer (`retrieval.py:_tag_prefix_holdback`) had to hold
  back trailing whitespace, not just a partial `<citations` prefix — the
  system prompt's own newline before the block was otherwise flushed as
  prose one chunk early, breaking the answer_stream()/answer() parity test.
  Once both holdbacks compose, parity holds byte-for-byte under `FakeProvider`.
- `Chunk` (providers/base.py) carries no usage/stop_reason, so a streamed
  turn's `PipelineResult` records `usage=Usage(0,0)` and
  `stop_reason="end_turn"` unconditionally — consistent with the spec's
  "latency and token accounting are not recorded this phase," but worth
  knowing if that field is ever read downstream of the API layer.
  `AgenticPipeline.answer()` (used only for escalation) is unaffected — it
  still returns real usage since it never streams.
- Both pipelines share one `LLMProvider` instance (`config.answer`) — nothing
  in `AgentSDKProvider` holds per-call state, so reuse across the baseline
  and escalation paths needed no changes there.
- Live-verified end to end against the real `transmissions` collection and
  `agent_sdk` provider: collection pick → conversation create → streamed
  answer with progressive tokens → citation chips → source panel → close.
  Escalation was exercised only under `FakeProvider` (see spec.md's
  acceptance-criteria note) — a real `agentic-v1` click-through is still
  worth doing before calling the escalation control production-trustworthy.

# spec: markdown rendering for AI answers

## outcome
Someone reading an AI answer in the chat UI sees actual formatting — bold text, bullet/numbered lists, italics, inline code, links — instead of the raw markdown syntax the model emits (most visibly, literal `**` around words that were meant to be bold). This applies to every answer bubble (baseline and escalated/agentic) and to the answer as it streams in, not just once it's finished.

## in scope
- Render `answer.text` (completed turns) and `pendingText` (the in-progress streamed answer) as markdown wherever they're shown in the chat UI.
- Support GFM markdown: bold, italics, bullet lists, numbered lists, inline code, links.
- Add a markdown-rendering library (`react-markdown` + `remark-gfm`) to `web/`.
- Preserve the current line-break/paragraph spacing behavior (today provided by `white-space: pre-wrap` in `app.css`) for answers that contain no markdown.

## out of scope
- The question input box — stays plain text, untouched.
- Citation chip rendering/styling. *(Amended 2026-09-13 — see the amendment below, which brings inline chunk-id references into scope.)*
- Any backend prompt (`retrieval.py`, `whole_doc.py`, `agentic.py` `SYSTEM_PROMPT`s) — left exactly as-is; the model's markdown output is taken as given, not suppressed.
- Any other UI text (headers, escalation status text, error banners).

## constraints
- Stack: React 18 + TypeScript + Vite (`web/`), no new state-management dependency.
- Only new dependencies allowed: `react-markdown` and `remark-gfm` (plus their own transitive deps) — nothing beyond what rendering requires.
- No backend (Python) changes of any kind for this fix.
- Must not regress plain-text answers: an answer with no markdown must look the same as it does today.
- Follow `AGENTS.md`: minimize changed lines, no unrelated refactors, no touching files outside the answer-rendering path.

## prior decisions
- **Render with a library, not a hand-rolled parser**: `react-markdown` + `remark-gfm` chosen over a custom regex parser for correctness across bold/lists/links/etc. and to avoid maintaining parsing logic. Don't reconsider a custom parser.
- **System prompt stays untouched**: this is a frontend-only fix. Don't add prompt instructions telling the model to avoid markdown.
- **Scope is the AI's response text only**: don't extend markdown rendering to any other UI surface.

## requirements
- The system SHALL render `**bold**` markdown in AI answer text as visually bold, not literal asterisks.
- The system SHALL render other GFM markdown present in AI answer text (bullet lists, numbered lists, italics, inline code, links) with proper formatting rather than showing raw syntax.
- The system SHALL apply this rendering to both the baseline answer and the escalated/agentic answer within a turn.
- The system SHALL apply this rendering to `pendingText` while an answer is still streaming, not only once the turn completes.
- The system SHALL preserve paragraph/line-break spacing equivalent to today's `white-space: pre-wrap` for answers containing no markdown.
- WHEN a streamed answer contains a markdown span that hasn't closed yet (e.g. an opening `**` with no matching closer received so far), the system SHALL render the visible text without throwing or crashing.
- WHEN the stream completes and the final answer text arrives, the system SHALL continue rendering it with the same markdown treatment.

### unwanted behavior
- IF the answer text contains no markdown syntax, the system SHALL render it identically to current plain-text behavior — no stray escaping, no visual diff.
- IF markdown parsing fails for any input, the system SHALL NOT crash the chat UI — the underlying text SHALL remain visible.
- IF the answer text contains HTML-like content, the system SHALL NOT render it as live HTML — markdown rendering must not become an HTML/script-injection path.

---

# Amendment (2026-09-13): inline chunk-id references

Written after the original shipped. Markdown rendering works; this covers a
defect it made visible.

## The observed problem

Baseline answers contain stray bracketed references in the prose —
`[fb_rules.pdf:0042]` — which render as literal brackets, or occasionally as a
broken link. Agentic answers do not.

## Diagnosis: neither the renderer nor the model is at fault

The two pipelines use different prompts, and the baseline's teaches the
convention twice over.

Its excerpts are formatted with the id in brackets:

```python
excerpts = "\n\n".join(f"[{c.chunk_id}] ({c.doc})\n{c.text}" for c in chunks)
```

and its system prompt closes with *"Use exactly the chunk ids shown **in
brackets** before each excerpt below; do not invent ids."*

So the baseline model sees `[fb_rules.pdf:0042] (fb_rules.pdf)` before every
excerpt, is told the ids live in brackets, and mirrors that notation inline in
its prose. The renderer is faithfully displaying text the model wrote.

`AgenticPipeline` has no equivalent line — it cannot, because its chunks arrive
as tool results rather than pre-formatted in the system prompt. It never learns
the convention, so it never emits it. That is the entire difference.

A second-order hazard: `[id] (doc)` is one space away from markdown link
syntax. Depending on exactly what the model echoes, the same defect surfaces
either as literal brackets or as a broken link.

## The fix cannot be in the prompt

`RetrievalPipeline.SYSTEM_PROMPT` and `_build_messages` **are** the frozen
Phase 4 baseline. Every comparison in Phases 4–7 — agentic's +22.6 recall
points, every citation-precision figure, the entire Haiku study — rests on that
prompt producing those exact messages. Removing the brackets from the excerpt
format is the obvious fix and would silently invalidate all of it.

This is the same constraint that produced `answer_stream()` beside `answer()`
rather than a change to it: **the repair happens in the rendering layer.**

## The work itself is Phase 10

This amendment records the **diagnosis** — it belongs with Phase 9, because it
explains a defect Phase 9's rendering made visible, and because the
prompt-is-frozen constraint is the thing most likely to be violated by someone
fixing it.

The **build** is specified in
[`specs/10-inline-citations/BRIEF.md`](../10-inline-citations/BRIEF.md): render
well-formed inline `[chunk-id]` tokens as citation chips via a remark plugin,
reusing Phase 6's chip component and chunk endpoint, touching nothing under
`src/raglab/`.

Deliberately kept in one place so the two documents cannot drift.

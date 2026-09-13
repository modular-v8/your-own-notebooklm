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
- Citation chip rendering/styling.
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

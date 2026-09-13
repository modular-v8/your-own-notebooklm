# Phase 10 — Inline citation chips

A one-page brief, not a spec/plan/tasks phase. This is a frontend change to one
rendering path.

## What you are building

Baseline answers contain bracketed chunk references in their prose —
`[fb_rules.pdf:0042]` — which currently render as literal brackets, or
occasionally as a broken markdown link. Render them as citation chips instead,
resolved the same way the trailing citation strip already is.

Agentic answers don't have this problem, for a reason that matters below.

## Read this before you touch anything

**Do not fix this in the prompt.** The obvious repair is to stop putting chunk
ids in brackets in `RetrievalPipeline._build_messages`:

```python
excerpts = "\n\n".join(f"[{c.chunk_id}] ({c.doc})\n{c.text}" for c in chunks)
```

That, plus the system prompt's closing line — *"Use exactly the chunk ids shown
in brackets before each excerpt below"* — is why the model writes brackets in
its prose. It is copying the convention it was shown twice.

**`RetrievalPipeline.SYSTEM_PROMPT` and `_build_messages` are the frozen Phase 4
baseline.** Every comparison in Phases 4 through 7 rests on that prompt producing
exactly those messages: agentic's +22.6 recall points, every citation-precision
figure, the whole Haiku study. Changing the excerpt format would invalidate all
of it, silently, with no test failing.

`AgenticPipeline` has no equivalent line — its chunks arrive as tool results
rather than pre-formatted in the system prompt — which is the entire reason its
answers are clean. Don't "fix" that either.

**This change must touch no file under `src/raglab/`.** If you find yourself
needing a backend change, stop and raise it.

## What to build

Render a well-formed inline `[chunk-id]` as a citation chip. The pieces already
exist: Phase 6 shipped the chip component and `GET /api/chunks/{chunk_id}`.

**Use a remark plugin, not string replacement on the answer text.** A plugin
operates on markdown text nodes, so it skips code blocks and inline code for
free. A regex over the raw string would rewrite chunk ids inside a fenced
example — and an answer explaining chunk ids in a code block is entirely
plausible in this corpus.

Match only well-formed ids, mirroring `CHUNK_ID_RE` in
`src/raglab/evals/citations.py` — roughly `\[([^\s\],:]+:\d+)\]`. Ordinary
bracketed prose and genuine markdown links must pass through untouched.

## Edge cases that decide whether this is done

| input | expected |
|---|---|
| `[fb_rules.pdf:0042]` inline | chip, opens the source panel |
| id that resolves to nothing in the index | **plain text**, not a dead chip |
| chunk id inside a fenced code block | left verbatim |
| `[some note]` — not id-shaped | normal markdown handling |
| `[text](url)` — real link | still a link |
| mid-stream, answer incomplete | chips appear as they arrive |

The unresolvable case matters most: a chip that looks clickable and does nothing
is worse than the literal brackets you have today.

## Where the work goes

`web/src/` only — the markdown rendering path Phase 9 added, plus a small remark
plugin beside it, plus reuse of the existing chip and source-panel components.

## Done when

- [x] A baseline answer with an inline `[chunk-id]` shows a chip, not brackets. Live-verified: asked the real `PDK Transmission` collection a question that made the model cite inline four times (`[Draft.md:0011]`); all four rendered as chips.
- [x] Activating an inline chip opens the same source panel a trailing chip does. Clicked one live -- opened `Draft.md`, lines 55-62, same as a trailing chip.
- [x] An unresolvable id renders as plain text. Verified `GET /api/chunks/<bogus-id>` 404s (the mechanism `InlineChunkRef` depends on); the component's render only special-cases the resolved state, defaulting to plain `[id]` text otherwise -- not additionally forced through a live bad-id answer, since eliciting a specific hallucinated id from the model on demand isn't controllable.
- [x] A chunk id inside a code block is verbatim. Live-verified: asked the model to show the citation syntax in a fenced code block; `[Draft.md:0011]` rendered with accessibility role `generic` (plain text), not `button`.
- [x] A genuine markdown link is unaffected. Structural, not probabilistic -- a real `[text](url)` is parsed into a `link` node by remark's core parser before any plugin runs, so it's never a `text` node this plugin's visitor can match against.
- [x] Chips appear during streaming, not only on completion. Same `ReactMarkdown` pipeline Phase 9 already re-renders on every streamed token; not separately re-verified live.
- [x] **`git diff` touches no file under `src/raglab/`.** `git diff --stat -- src/raglab/` is empty.
- [x] `uv run pytest -q` green (322 passed) -- unchanged, since nothing backend moved.

## A real bug the live check caught

`react-markdown`'s default `urlTransform` strips any URL protocol it doesn't
recognize (XSS hardening) -- including the private `raglab-chunk:` scheme this
plugin uses to smuggle a chunk id through to the `components.a` override. Without
a fix, every inline reference silently fell back to a bare, href-less anchor
showing the literal `[chunk-id]` text -- passing every case in this table by
accident, since a broken chip and "not yet built" look identical in the DOM
until you check the accessibility role. Fixed by passing a custom `urlTransform`
to `ReactMarkdown` that allowlists `raglab-chunk:` and defers to
`defaultUrlTransform` for everything else, so real links keep their existing
sanitization. Caught only because the live check inspected element roles
(`button` vs `link` vs `generic`), not just visible text -- the two look the
same in `get_page_text`.

## Background

Full diagnosis in `specs/9-markdown-rendering/spec.md` § *Amendment*. It explains
why the two pipelines differ and why the prompt is untouchable. Read it if
anything above seems arbitrary.

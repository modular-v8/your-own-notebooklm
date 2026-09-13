# raglab: a NotebookLM-like RAG system with measurable retrieval

A browser-based chat interface for answering questions about your documents with cited sources. Built from the ground up to measure whether retrieval techniques actually work, using a frozen eval corpus and deterministic citation checking instead of subjective scores.

## Why this exists

This project started as a learning exercise in RAG systems and retrieval measurement: finding out precisely what works and what doesn't in retrieval-augmented generation, rather than shipping a perfect product on the first try.

Tools like NotebookLM and Claude Projects are genuinely good at answering questions over a pile of documents. But they run on infrastructure you don't control, often hosted in another country under another company's data-handling policy. For a student asking about lecture notes, that's irrelevant. For a company sitting on confidential contracts, financial models, or internal specs, uploading that content to a third-party service is a risk that security and legal teams routinely refuse to accept, no matter how good the retrieval is.

raglab keeps the parts of that workflow that matter (chat with your documents, get an answer with a citation you can verify) while keeping the documents themselves off anyone else's servers. Indexing, chunking, and embedding all happen locally. The only thing that ever leaves your machine is the specific question and the specific passages needed to answer it, sent to whichever LLM you've configured. Point that at your own company's model endpoint instead of a public one, and nothing about the documents you're asking questions over needs to touch infrastructure you don't control. The provider layer exists as a swappable interface for exactly this reason. Today it ships with three cloud options to prove the retrieval and evaluation work correctly; wiring it to a self-hosted or on-prem model is additional engineering, not an architectural change.

## What this tool can do

- **Chat with your documents.** Upload PDFs, Markdown, or plain text, organize them into collections, and ask questions that get cited answers.
- **See where answers come from.** Every answer displays the exact passages it uses, with clickable source panels showing document name and line numbers.
- **Get better answers when needed.** A manual escalation button re-runs uncertain questions through a more powerful (and slower) reasoning path based on **agentic retrieval**, showing both answers side by side so you can pick the best one.
- **Understand retrieval trade-offs.** Built on 10 phases of measurement showing what retrieval techniques improve recall, what breaks citations, and what makes cross-document questions fail.
- **Reproduce research findings.** Every phase's design and results are documented; the eval corpus and test gold-sets ship with the repo.

## What this tool cannot do

- **Handle scanned PDFs.** If your PDF has no extractable text layer, it will index as empty.
- **Automatically decide when to escalate.** The system tried building an automatic router to use expensive reasoning only when needed. It failed: no statistical signal separates questions that need help from those that don't. Letting a human decide, through the "escalate" button, works better than any router tested.
- **Guarantee perfect citations.** A stronger reasoning model produces more thorough answers, which sometimes cite supporting material that lies just outside the gold-standard answer span. This is a known limitation, not something a prompt tweak fixed.
- **Jump to specific PDF pages.** You get line numbers and text excerpts instead. A full page-map feature would require a separate PDF parsing pass.
- **Support multiple users or authentication.** This is a local-first, single-user tool. Share documents by sharing files, not by user accounts.
- **Handle follow-up questions well by default.** On a question like "what about...?", the retriever searches using only that question, not your prior turns, so it can miss context a human would infer instantly. The model will still try, but results suffer. Write each question as a complete, standalone thought rather than treating this like a conversational assistant such as Gemini, or use the escalation button, which handles follow-ups correctly.

## Getting started

### Requirements

- Python 3.12 or 3.13 (Python 3.14+ lacks compatible wheels for this stack)
- Node 18+ (for the frontend)
- An LLM API or subscription: [Claude API](https://console.anthropic.com/), [OpenRouter](https://openrouter.ai/), a Claude subscription authenticated through the `claude` CLI, or any other LLM API you'd rather wire up through the provider interface

### Setup

Clone the repository:

```bash
git clone https://github.com/yourusername/raglab.git
cd raglab
```

Install dependencies:

```bash
uv python pin 3.12
uv sync
cp .env.example .env
```

Configure your LLM provider in `.env`. Choose one:

```bash
# Claude API (Anthropic)
ANTHROPIC_API_KEY=your-key-here

# OpenRouter (supports many models)
OPENROUTER_API_KEY=your-key-here

# Claude subscription via the Agent SDK (no key needed)
# Just run: claude login
```

Build the frontend (one-time):

```bash
cd web && npm install && npm run build && cd ..
```

### Running

Start the server:

```bash
uv run raglab serve
```

Open your browser to `http://localhost:8000`. You'll see an empty state; create a collection and upload your first document to get started.

#### Supported document formats

- `.pdf`: PDF files (text layer required; scanned PDFs without OCR will be empty)
- `.md`: Markdown
- `.txt`: Plain text

## Using the interface

1. **Create a collection.** Click "Create collection" in the sidebar to organize documents.
2. **Upload documents.** Drag and drop, or use the upload button. Indexing happens in the background.
3. **Ask questions.** Type your question and watch the answer stream in with source citations.
4. **Click a citation.** See the exact passage that supports each claim, with document name and line numbers.
5. **Escalate if needed.** If an answer seems incomplete or uncertain, click "Escalate" to re-run it through deeper reasoning.

## Command-line tools

Use the CLI for batch operations, retrieval testing, and reproducibility checks:

```bash
# Verify your LLM provider is configured
uv run raglab providers check

# Search across all documents
uv run raglab search "your query here"

# Validate document collections
uv run raglab collections

# Run evaluation against the bundled gold-standard test set
# (requires the optional evaluation corpus)
uv run raglab eval run --gold evals/gold/<test-name>.yaml --name run --pipeline retrieval
```

Run `uv run raglab --help` (or `--help` on any subcommand) for the full list of commands and options.

## How it works

### The retrieval pipeline

When you ask a question:

1. **Embed the question.** It's converted to vector form using a fast local embedding model.
2. **Search documents.** Find passages with matching embeddings (dense search) and keyword overlap (lexical search).
3. **Retrieve relevant chunks.** Take the top results and pass them to the language model.
4. **Generate an answer.** The model reads those chunks and answers your question, citing what it used.
5. **Check citations.** Deterministically verify that every claim points to real passages (no LLM involved).

On follow-up questions ("What about...?"), the model sees your full conversation history so it understands context, but *only the current question is used for retrieval*. This helps with clarification, but a follow-up sometimes needs richer context than that. The escalation button re-runs it with a reasoning loop that formulates its own search queries.

### Why ten phases?

This project was built to answer a specific question: *which retrieval techniques actually work?* Each phase measures a piece:

- **Phases 1 to 3:** build the retrieval, chunking, and evaluation pipeline with hard metrics.
- **Phases 4 and 5:** test five retrieval techniques exhaustively; find that none are perfect, build an automatic escalation router, then find the router fails.
- **Phase 6:** ship the interface with *manual* escalation, since humans turned out better than automation at deciding when to escalate.
- **Phases 7 to 10:** explore model swaps (Haiku vs. Sonnet), UI improvements (citations, markdown), and user features (collections, uploads).

See `specs/` in this repo for complete design docs and measurement results for each phase.

## What worked well

- **Measuring retrieval precisely.** Rather than asking "is this better or worse," measure *what specifically* improved: recall at 5 results, citation precision, coverage of the answer.
- **Testing the hard cases.** Cross-document questions and follow-up questions reveal more about retrieval than average questions do.
- **The manual escalation pattern.** Every automatic routing technique tried (probabilistic confidence, token-budget-based routing, learned classifiers) failed. A human looking at an unsatisfying answer is a better signal than any algorithm.
- **Deterministic citation checking.** Citations get verified without calling the model again, which makes every comparison reproducible.
- **Splitting history from retrieval.** The model reasons over the full conversation, but retrieval searches using only the current question. This split turned out to be the sweet spot between accuracy and efficiency.

## What didn't work

- **Automatic retrieval routing.** Tried building a system to use expensive reasoning only when needed. No automatic signal can predict which questions need it, and the router ended up costing more than always using the strong model.
- **Citation pruning.** Tried removing over-cited material from agentic answers. It turns out 75% of extra citations are legitimate context the answer genuinely needs, not hallucination.
- **Cheaper models for reasoning.** Tested Haiku on the hardest questions. It's indistinguishable from Sonnet on most cases but fails on multi-document questions by stopping its search too early, so it wasn't worth the token savings on an escalation-only path.
- **Tightened citation prompts.** Adjusting system prompts to reduce citation "noise" didn't help. It just reduced recall.

See [Phase 5 (Adaptive Retrieval)](specs/5-adaptive-retrieval/spec.md) and [Phase 7 (Haiku Study)](specs/7-haiku-agentic/BRIEF.md) for detailed measurement results.

## Architecture

```
browser (React + TypeScript)
   |
FastAPI backend
   |-- Collection & document management
   |-- Conversation storage (JSON files)
   `-- Answer pipeline with streaming
       |-- Retrieval (vector + lexical search)
       |-- Baseline answering (fast)
       `-- Agentic answering (slow but thorough)
   |
Embedding model (running locally, offline-capable)
```

No PyTorch, no Docker, no external databases. Just Python, Node, and a local vector index on disk.

## Testing

Run the test suite (no API calls, no network required):

```bash
uv run pytest -q
```

The test suite uses fake LLM providers to verify behavior without consuming quota.

## Evaluation & reproducibility

The bundled `evals/corpus/` folder contains five documents (including a 137-page racing rulebook) and gold-standard test sets in `evals/gold/`. This is optional; you don't need it to use raglab as a tool.

To reproduce the research findings:

```bash
uv run raglab index
uv run raglab eval run --gold evals/gold/<name>.yaml --name baseline --pipeline whole_doc
uv run raglab eval run --gold evals/gold/<name>.yaml --name retrieval --pipeline retrieval
```

The `compare` command shows entry-by-entry differences:

```bash
uv run raglab compare evals/baselines/<baseline>.json evals/runs/<run>.json
```

## Working on this project

Design docs and measurement results for every phase live in [`specs/`](specs/), documented for anyone building similar systems. Start there to understand why something was built a particular way before changing it. Keep changes minimal and scoped, don't add dependencies without a reason, run `uv run pytest -q` before opening a pull request, and read the relevant spec before touching the eval harness or frozen baseline prompts. Several phases' results depend on those staying exactly as they are.

---

**Questions?** File an issue or start a discussion.

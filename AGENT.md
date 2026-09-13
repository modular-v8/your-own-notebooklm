# AGENTS.md

Instructions for any AI coding agent working in this repository. Humans wanting to *use* the tool should read `README.md` instead — this file is about developing *on* it. `DESIGN.md` governs what the UI looks like in later phases; this file governs how code gets written in all of them.

## General Rules

- When writing something intended for human consumption (comment, commit message, reply to prompt), use as few words as possible. Pick every word meticulously. Be to the point. Less is more.
- Avoid superlatives and praise. Don't tell me I am absolutely right. Give me the cold hard truth.
- Avoid magic numbers and strings — extract recurring or meaningful values into descriptive constants or enums. Keep self-explanatory, one-off values inline. If a value comes from a spec (e.g. HTTP 200), use a constant regardless.
- Reduce code indentation. Avoid the arrow anti-pattern. Prefer early return and continue.
- Keep function names short — under 30 characters.
- Let the reader breathe. Add empty lines between logical blocks of code.
- Add a small, to-the-point comment to explain *why* a block does what it does, not *what* it does — names should already say what. Use examples where helpful.
- Treat member visibility changes as a breaking design shift. Keep fields and functions private unless external access is strictly required. Ask before changing anything from private to internal or public.
- Don't touch code unrelated to the feature you're implementing. Minimize the number of changed lines.
- **NEVER read or print `.env`.** It holds real API keys. Code in this repo (`config.py`, provider modules) reads it programmatically via its own env-loading logic at runtime — that's expected. An agent using a file-reading tool to open `.env` directly, or echoing its contents to a shell, is not.
- If the user allows a commit message, follow these 7 rules:
  1. Separate subject from body with a blank line.
  2. Limit the subject line to 50 characters (72 hard limit).
  3. Capitalize the first letter of the subject line.
  4. No period at the end of the subject line.
  5. Imperative mood ("Fix bug," "Add feature," not "Fixed" or "Adds"). Test: it completes "If applied, this commit will ___."
  6. Wrap the body manually at 72 characters.
  7. Use the body to explain what and why, not how — the code explains how.
- When writing or editing the [README.md](README.md), keep it free from overly technical details. Readme is user-facing and anyone looking at it for the first time should have a brief idea of what the tool does, how it works (briefly), and of course the setup and usage commands.
- Review and update spec, plan and task files periodically after completion of major milestones and update them with a brief summary of observations. 
- In case you notice a sudden and surprising change in the codebase, there is a good chance the user might have done it without informing you. Good practice to confirm with the user by interrupting the task, and then proceed accordingly. Might save you from going into a confusion loop.

## Tool Specific Rules

### Setup

```bash
uv python pin 3.12
uv sync
```

Python 3.12 is pinned deliberately (`spec.md`'s constraints): the system Python (3.14+) lacks a viable wheel story for this stack. Don't change the pin without checking wheel availability first.

### Running tests

```bash
uv run pytest -q
```

Must pass with **no network access and no API keys set** — every provider call in the test suite goes through `tests/fakes.py:FakeProvider`, never a real SDK client. If a test genuinely needs a live provider, mark it `@pytest.mark.integration`; the default run excludes that marker.

### Live model calls cost real money and quota — treat them as a deliberate action, not a routine one

- `raglab providers check` and `raglab eval run` make real, metered calls (Anthropic API, OpenRouter) or consume the user's Claude subscription quota (Agent SDK). Say which provider/model before invoking either, and don't chain runs silently.
- **No silent provider fallback, ever.** If the configured provider is unavailable or unauthenticated, the system fails loud naming the provider and the missing credential (`spec.md`, unwanted-behavior section) — never retries against a different provider. Don't "helpfully" add a fallback.
- **No server-side refusal fallback either.** Anthropic API calls never opt into auto-rerouting a refused request to another model — that would silently change the eval harness's ruler mid-run.
- **Never truncate an over-context document.** `OverContextError` is a skip, not a retry-with-truncation. A truncated document scores low for a reason unrelated to retrieval, which would poison every comparison drawn against the baseline.

### Never open, read, or print `.env`

See "General Rules" above — it's restated here because it is the single most consequential mistake an agent can make in this repo.

### Before committing or pushing

- Check what a broad `git add` actually staged (`git status`) before committing.
- Never commit `.env` or `evals/runs/*` (gitignored already; don't force-add them).
- Run the full test suite before pushing, not just the tests you touched.
- Confirm with the user before pushing — treat any push as needing an explicit go-ahead.

### Architecture, briefly

```
providers/  -- how we talk to a model (LLMProvider protocol + 3 implementations)
pipelines/  -- the thing being measured (Pipeline protocol; whole_doc is Phase 0's only implementation)
evals/      -- the measuring apparatus (gold set, judge, runner, metrics, report)
```

The seam that matters is `Pipeline.answer(question, doc_text)`. Every later phase adds a new pipeline implementation and changes nothing in `evals/`. Don't let a pipeline reach into `evals/`, and don't let `evals/` assume anything about a pipeline beyond that one method.

Tool calling is resolved *inside* a provider's `complete()`, not by the caller — each `ToolSpec` carries its own async handler, and the provider runs its own request/execute/respond loop. This keeps `LLMProvider` identical across Anthropic, OpenRouter, and the Agent SDK, where the CLI subprocess owns tool execution regardless of what the caller wants.

### Known environment gotchas (Windows)

- This tool runs Git Bash's `sh`, not PowerShell — target that shell's syntax unless a task specifically needs PowerShell.
- `uv tool install`/`uninstall` can fail mid-operation with a Windows file-lock error (`os error 32`), most likely real-time antivirus scanning a native `.pyd`. Don't force-retry; use `uvx --from <spec> <command>` instead.

### Where to look for more context

- `README.md` — what the tool does, how to install and use it.
- `specs/<phase>/spec.md` + `plan.md` — the authoritative design for each phase, reviewed before implementation starts.
- `DESIGN.md` — governs UI work in later phases (FastAPI + React); no effect on the CLI-only phases.

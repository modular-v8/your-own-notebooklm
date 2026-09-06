# spec: Phase 3 — Collections & Conversations

## outcome

After this phase, documents belong to named collections, and a conversation is scoped to one of them: retrieval searches that collection and nothing else. Questions become multi-turn, so a follow-up like "what about EVs?" is asked the way a person actually asks it — with meaning that lives in the previous turn rather than in the question itself. The harness measures what that costs. This is the phase where the project stops being a single flat corpus and starts being the thing it set out to clone.

The measurement this phase exists to produce is a **deficit, not an improvement**: retrieval on a raw follow-up question, without the history that gives it meaning, is expected to be materially worse than retrieval on a standalone question. Quantifying that gap is the point. Phase 4 closes it with query rewriting, and cannot claim credit for doing so without a number to close.

## in scope

- Named collections: a document belongs to zero or more, defined in configuration.
- One index carrying a `collection` field per chunk; retrieval filters to the active collection.
- `raglab collections` to list membership, and a `--collection` flag on `index`, `search`, and `eval run`.
- Gold-set schema v3: `turns` replaces `question`, with prior turns carrying scripted answers and the final turn graded.
- A `collection` field on a gold set, naming the collection its entries are evaluated against.
- Multi-turn answering: the pipeline receives conversation history and retrieves for the final turn.
- Per-turn-position metrics: recall and citation quality broken down by whether a question is standalone or a follow-up.
- A `not-in-collection` tag: a question answerable elsewhere in the corpus but not in the active collection, which must be refused.
- Two carry-overs from Phase 2: a `gold validate` warning when a `not-in-document` question has strong lexical matches in the corpus, and a resolver guard rejecting an anchor match immediately followed by `)`.
- A fix to delta reporting: prior-run matching must include gold-set identity, not only provider and pipeline configuration.

## out of scope

- **Web UI, FastAPI, React.** Deferred again. Collections and conversations are both expressible as CLI commands, and a UI would roughly double the phase while adding no measurement.
- **Query rewriting, history-aware retrieval, or any fix for the follow-up deficit.** Phase 4. Measuring the gap and closing it in the same phase would leave nothing to attribute the improvement to.
- **Hybrid search, reranking, structure-aware chunking.** Phase 4, unchanged.
- **Live conversation history.** Prior turns carry scripted answers rather than being answered by the model at run time — see prior decisions.
- **Changing the judge, retrieval parameters, or the any-overlap rule.** Frozen since Phase 0, and they stay frozen.
- **Streaming.** Still no consumer for it.

## users & context

Unchanged: one developer, Windows 10, terminal. One new loop matters — `raglab search --collection X` gets run repeatedly while checking that scoping actually excludes what it should. The failure mode this phase can produce is subtle and silent: a filter that quietly does nothing looks exactly like a filter that works, as long as the right answer was in the active collection anyway. The `not-in-collection` entries exist to make that failure loud.

## constraints

- Everything from Phases 0–2 carries forward: Python 3.12 via `uv`, no PyTorch, no Docker, local-first, clone-and-run, minimal dependencies, `agent_sdk` as the working provider.
- Retrieval parameters (900/150, k=5, `bge-small-en-v1.5`), the judge model and prompt, and the any-overlap rule are unchanged. Phase 3's numbers must stay comparable to Phase 2's.
- **Retrieval still never filters to a single document.** Phase 1 froze corpus-wide search so that scoping could not hide the hard problem. A collection is a wider unit than a document, and the gold entry's `doc` remains ground truth for scoring, never a filter.
- Gold-set schema v3 is a breaking change. The loader accepts v3 and rejects v1 and v2 by name.
- The existing five gold sets must keep passing, migrated mechanically.

## data & integrations

**Collections** are defined in `config.toml` as named lists of document names. A document may appear in several collections; one that appears in none is indexed but unreachable by any scoped query, which is itself a validation warning.

**Index** gains a `collection` field per chunk. A document belonging to two collections is embedded once and carries both memberships, so the store grows with documents rather than with collection assignments.

**Gold-set schema v3.** `question` is replaced by `turns`; a gold set names the collection its entries run against:

```yaml
version: 3
collection: rules
corpus_hashes: { ... }

entries:
  - id: q-001
    turns:
      - question: "What is the minimum age for a Formula Bharat team member?"
    expected_answer: "16 years of age."
    sources: [ ... ]
    tags: [lexical-anchor]

  - id: q-031
    turns:
      - question: "What must the shutdown circuit consist of on a combustion vehicle?"
        answer: "A series connection of at least the LVMS, the BSPD, three shutdown buttons, the BOTS, and the inertia switch."
      - question: "What about EVs?"
    expected_answer: "..."
    sources: [ ... ]
    tags: [follow-up, near-duplicate]
```

Every prior turn carries a scripted `answer`; the final turn carries none and is the one graded. A single-turn entry is a one-element list, which is how all 69 existing entries migrate.

**Tag vocabulary** gains `follow-up` (the final turn depends on a prior turn for its meaning) and `not-in-collection` (answerable elsewhere in the corpus, not in the active collection).

**Report additions** — the active collection in `config`, and a breakdown of every existing rate by turn position: standalone versus follow-up. No change to how existing fields are computed.

## prior decisions

- **Conversation history is scripted, not generated at run time.** Answering prior turns live would mean a poor answer at turn one silently corrupts turn two's retrieval, and nothing in the report could attribute the failure. Scripted history makes the input to the graded turn deterministic and identical across runs, which is the same reason the judge and retrieval parameters are frozen. Live history is a legitimate Phase 4+ variant, measured against this as the baseline.
- **Phase 3 measures the follow-up deficit and does not fix it.** A raw follow-up ("what about EVs?") carries almost no retrievable signal. Retrieval will do badly on it, and that number is the deliverable — Phase 4's query rewriting needs a gap to close, established under a frozen configuration.
- **One index with a collection field, not an index per collection.** A document in two collections is embedded once, there is one manifest and one rebuild path, and the existing NumPy store needs a boolean mask rather than a second storage layout.
- **Collections scope retrieval; documents never do.** The Phase 1 decision that retrieval must not be narrowed to the gold entry's own document is unchanged. A collection is a coarser unit, chosen by the user, and it is what a Projects-style product actually exposes.
- **The UI is deferred a third time.** It has no measurement value, and Phase 4 is the reason this project exists. It becomes worth building once retrieval is optimized and there is something worth looking at.
- **`not-in-collection` is a sharper hallucination test than `not-in-document`.** The same question is correctly answered against one collection and must be refused against another. A scoping filter that silently does nothing passes every other test in the suite and fails this one.

## requirements

### always active

- The system SHALL record a `collection` membership set for every indexed chunk.
- The system SHALL restrict retrieval to the active collection, and SHALL never restrict it to a single document.
- The system SHALL accept gold sets declaring `version: 3` and SHALL reject `version: 1` and `version: 2`, naming the required migration.
- The system SHALL treat the final turn of an entry as the graded question and all prior turns as conversation history.
- The system SHALL pass scripted prior-turn answers to the model unchanged, without generating them.
- The system SHALL report every rate broken down by turn position, standalone versus follow-up, alongside the existing per-tag breakdown.
- The system SHALL keep the judge, retrieval parameters, and any-overlap rule unchanged.

### event-driven

- WHEN `raglab index` runs, the system SHALL record each chunk's collection memberships from configuration.
- WHEN a search or eval run names a collection, the system SHALL consider only chunks belonging to it.
- WHEN a multi-turn entry is evaluated, the system SHALL retrieve using the final turn's question and place the prior turns in the model's context as history.
- WHEN an entry is tagged `not-in-collection`, the system SHALL score a refusal as correct and a substantive answer as incorrect.
- WHEN `raglab gold validate` encounters a `not-in-document` entry whose salient terms match strongly in the corpus, the system SHALL emit a warning naming the matching lines, and SHALL NOT reject the entry.
- WHEN `raglab collections` is invoked, the system SHALL list each collection with its documents and chunk counts.

### unwanted behavior

- IF a gold set names a collection that does not exist in configuration, the system SHALL abort naming both.
- IF an entry's gold `doc` is not a member of the gold set's collection, the system SHALL report it as invalid unless the entry is tagged `not-in-collection`.
- IF a document belongs to no collection, the system SHALL warn at index time, since it is unreachable by any scoped query.
- IF an anchor match is immediately followed by `)`, the system SHALL treat it as a cross-reference and exclude it from the match set.
- IF a prior turn carries no scripted `answer`, or the final turn carries one, the system SHALL report the entry as invalid.
- IF retrieval returns no chunk from the active collection, the pipeline SHALL refuse rather than falling back to the wider corpus.
- IF no prior report exists with both a matching configuration and a matching gold-set identity, the system SHALL report that no comparable prior run was found, and SHALL NOT print a delta against a run of a different gold set.

## acceptance criteria

- [x] `raglab collections` lists each collection with its documents and chunk counts.
- [x] `raglab search --collection X` never returns a chunk from a document outside X, verified against a query whose best global match sits outside it.
- [x] All five gold sets load as `version: 3`; v1 and v2 files are rejected by name. (Six, counting the new `scoping.yaml`.)
- [x] The 69 existing entries migrate mechanically to one-element `turns` lists and reproduce their Phase 2 recall and coverage numbers.
- [x] At least six `follow-up` entries exist, whose final turn is meaningless without its predecessor.
- [x] Recall on `follow-up` entries is reported separately, and the standalone-versus-follow-up gap is stated as a number. (80% standalone vs. 50% follow-up, live run.)
- [x] At least two `not-in-collection` entries exist; each is answered correctly under its home collection and refused under the scoped one.
- [x] A `not-in-document` entry whose answer is in fact present triggers a `gold validate` warning naming the matching lines — verified by reintroducing the original `q-027`.
- [x] An anchor followed by `)` is excluded, verified on `CV3.2.1`, and `q-027` resolves without needing `occurrence`.
- [x] Input tokens per question on follow-up entries are reported, showing what conversation history costs.
- [x] Grounded, refusal-correct, citation precision, and coverage on the migrated single-turn entries do not regress against Phase 2. (Recall/MRR/coverage identical across all five gold sets; grounded-rate deltas fall within known judge noise.)
- [x] Running two different gold sets in succession under identical provider configuration produces no delta between them; a repeat run of the same gold set does.

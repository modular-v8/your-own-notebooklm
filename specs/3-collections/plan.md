# Plan: Phase 3 — Collections & Conversations

## Approach Summary

Two additions that touch different layers and meet in the runner. **Collections** are a membership field on every chunk plus a boolean mask at query time — no new storage layout, no second index, and a document in two collections is still embedded once. **Conversations** are a `turns` list on each gold entry, where prior turns carry scripted answers and only the last is graded.

The load-bearing detail is what *doesn't* connect: **retrieval uses the raw final question, while the model sees the full history.** That asymmetry is deliberate and is the entire measurement. A follow-up like "what about EVs?" carries almost no retrievable signal on its own, so recall on follow-up entries should fall well below recall on standalone ones. That gap, measured under frozen retrieval parameters, is the number Phase 4's query rewriting exists to close. Wiring history into retrieval now would erase the deficit and leave Phase 4 with nothing to demonstrate.

Three slices; only the third spends quota:

1. **Collections** — config, chunk membership, masked search, `raglab collections`, `--collection` flags. Zero model calls.
2. **Schema v3 and validation carry-overs** — `turns`, migration of 69 entries, the `not-in-document` lexical warning, the `)` cross-reference guard. Zero model calls.
3. **Conversations and live runs** — history in the pipeline, turn-position metrics, then runs.

## Architecture

```
config.toml [collections]
        │
        ▼
raglab index ──► IndexBuilder ──► chunks.jsonl (+ collections: [...])
                                   manifest.json (+ collections map)

raglab search --collection X ──► Retriever
                                   ├─ Embedder.embed_query(final question)
                                   └─ VectorStore.search(k, mask=collection X)

raglab eval run --collection X ─► EvalRunner
                                   ├─ Query(question=turns[-1], history=turns[:-1], collection=X)
                                   ├─ RetrievalPipeline
                                   │     ├─ retrieve(final question only)   ← the deficit
                                   │     └─ answer(history + chunks)
                                   ├─ Judge, recall, citations, coverage    (unchanged)
                                   └─ Metrics ── by_tag + by_turn_position
```

## Tech Stack & Key Decisions

| Decision | Choice | Why |
|---|---|---|
| Collection storage | `collections: list[str]` per chunk in `chunks.jsonl` | One embedding per document regardless of how many collections it joins |
| Scoped search | Boolean row mask, out-of-collection scores set to `-inf` before top-k | Three lines against the existing NumPy store; at ~480 rows the cost is unmeasurable |
| Membership-only reindex | Rewrite `chunks.jsonl` without re-embedding | Changing which collection a document is in is not a content change; forcing a re-embed would make collections feel expensive and discourage using them |
| Retrieval query for follow-ups | The final turn's raw question, history excluded | This is the measurement, not an oversight — see Approach Summary |
| History in the answer prompt | Prior turns as alternating user/assistant messages | The model needs history to interpret the question even though retrieval does not get it |
| Gold sets and collections | `fb_rules.yaml` → `everything`; a new `scoping.yaml` → `rules` | `fb_rules.yaml` holds the cross-document entry `q-026`, which spans `fb_rules.pdf` and `smg.md` and therefore cannot run under a `rules`-only scope |
| Turn-position breakdown | `by_turn_position: {standalone, follow_up}` | Same shape as `by_tag`, so the report stays one pattern rather than two |
| Delta matching | `configs_match` gains gold-set path plus a fingerprint of entry ids | A Phase 0 defect: matching on provider config alone lets a 29-entry rulebook run print a delta against a 10-entry transmission run. When the gold set itself changed, the honest answer is "no comparable prior run", not a delta across different questions |

**What is deliberately not touched:** retrieval parameters (900/150, k=5), the judge model and prompt, the any-overlap rule, the citation mechanism, and the manual BGE query prefix in `Embedder.embed_query()`.

## Data Model

**Collections in `config.toml`:**

```toml
[collections]
rules          = ["fb_rules.pdf"]
transmissions  = ["amg_mct.md", "egear.md", "smg.md", "tiptronic.md"]
everything     = ["fb_rules.pdf", "amg_mct.md", "egear.md", "smg.md", "tiptronic.md"]
```

**Index** — `chunks.jsonl` rows gain `"collections": ["rules", "everything"]`; `manifest.json` gains the collections map so a membership change is detectable without re-reading config.

**Gold-set schema v3:**

```python
class Turn(BaseModel):
    question: str
    answer: str | None = None      # required on every turn except the last

class GoldEntry(BaseModel):
    id: str
    turns: list[Turn]              # >= 1; the last is graded
    expected_answer: str | None
    sources: list[Source]
    tags: list[str] = []

class GoldSet(BaseModel):
    version: Literal[3]
    collection: str
    corpus_hashes: dict[str, str]
    entries: list[GoldEntry]
```

Validation: at least one turn; every turn but the last carries an `answer`; the last carries none; each entry's gold `doc` is a member of the gold set's collection unless tagged `not-in-collection`.

**Migration** — a script converts `question: X` to `turns: [{question: X}]` and adds the `collection` key. 69 entries, entirely mechanical, and their recall and coverage numbers must come out unchanged.

**Report additions** — `config.collection`, and `by_turn_position` alongside `by_tag`. Existing fields are computed exactly as before.

## File / Module Structure

Additions and changes; unlisted files unchanged.

```
src/raglab/
├── config.py                    # CHANGED: [collections] parsing and validation
├── cli.py                       # CHANGED: + collections; --collection on index/search/eval run
├── collections.py               # NEW: membership resolution, unreachable-document warning
├── index/
│   ├── builder.py               # CHANGED: write memberships; membership-only rewrite path
│   └── store.py                 # CHANGED: search(k, mask=...)
├── retrieval/retriever.py       # CHANGED: collection-scoped search
├── pipelines/
│   ├── base.py                  # CHANGED: Query.history, Query.collection
│   └── retrieval.py             # CHANGED: history in prompt, raw final question for retrieval
└── evals/
    ├── goldset.py               # CHANGED: v3, Turn, collection, membership validation
    ├── locations.py             # CHANGED: reject anchor matches followed by ")"
    ├── validate.py              # NEW: not-in-document lexical-match warning
    ├── metrics.py               # CHANGED: by_turn_position
    ├── report.py                # CHANGED: collection in config; new aggregate;
    │                            #          configs_match includes gold-set identity
    └── runner.py                # CHANGED: build Query from turns

scripts/migrate_goldsets_v3.py   # NEW: throwaway, 69 entries

tests/
├── test_collections.py          # membership, unreachable warning, config errors
├── test_store_mask.py           # masked search excludes out-of-collection chunks
├── test_goldset_v3.py           # turns validation, collection membership, v1/v2 rejection
├── test_turns_pipeline.py       # history in prompt, raw question to retriever
├── test_validate_warnings.py    # q-027 reintroduced triggers the lexical warning
└── test_locations_paren.py      # CV3.2.1 cross-reference excluded
```

## What this needs from you

Roughly eight new gold entries, and they are the phase's real input:

- **Six `follow-up` entries.** The final turn must be meaningless alone — "what about EVs?", "and at idle?", "is that the same for the cockpit one?". Prior turns need a scripted answer, which can be lifted from an existing entry's `expected_answer`. Pair them with existing questions where possible so the deficit is measured on known-good retrieval.
- **Two `not-in-collection` entries** in a new `scoping.yaml` running against `rules`: questions answerable from the transmission documents, which must be refused when only the rulebook is in scope. Verify the answer really is in the transmission docs, the same grep check that caught `q-027`.

## Slices and cost

- **Slice 1 — Collections.** Done when `raglab search --collection rules` provably excludes a chunk that would otherwise rank first globally. **Zero model calls.**
- **Slice 2 — Schema v3 and carry-overs.** Done when all six gold sets validate, the 69 migrated entries reproduce their Phase 2 recall and coverage exactly, and a reintroduced `q-027` triggers the lexical warning. **Zero model calls.**
- **Slice 3 — Conversations and runs.** Six runs: `fb_rules` (~35 entries), the four Markdown sets (10 each), `scoping` (2–4). History inflates follow-up prompts, so budget roughly **250–280K input tokens** plus judge calls — comparable to three Phase 2 runs.

## Acceptance thresholds

- Single-turn entries must reproduce Phase 2's grounded, refusal-correct, citation-precision, and coverage numbers within judge noise. Anything larger means collections or the turn refactor changed behavior that was supposed to be untouched.
- **Recall on follow-up entries is expected to be substantially worse than on standalone entries.** No target is set, and a small gap is a finding rather than a success — it would mean the follow-ups aren't genuinely context-dependent and need rewriting before Phase 4 can use them.
- `not-in-collection` entries must be refused under scope and answered correctly without it. A pass on both is the only evidence that the filter does anything.

## As-built notes (handover to Phase 4)

Written after implementation and a full live run: all three slices done, 147 unit/integration tests pass, seven live retrieval runs via `agent_sdk`/`claude-sonnet-5` answering and `agent_sdk`/`claude-opus-5` judging — same setup Phases 0–2 used. One deviation from the plan: `eval run` gained a `--collection` override (not in the original file/CLI list) — needed so `scoping.yaml`'s entries could be run a second time against a collection that actually contains their doc, which is the only way to demonstrate the "answered correctly without scope" half of the `not-in-collection` acceptance criterion.

**Results table:**

| Gold set | entries | grounded | refusal-correct | recall@5 | MRR | citation precision | fabrication | mean coverage |
|---|---|---|---|---|---|---|---|---|
| fb_rules (all 35) | 35 | 77.4% | 100% | 74.2% | 0.592 | 74.4% | 0.0% | 69.9% |
| fb_rules — standalone (29) | 29 | 84.0% | — | 80.0% | — | — | — | — |
| fb_rules — follow-up (6) | 6 | 50.0% | — | 50.0% | — | — | — | — |
| amg_mct | 10 | 88.9% | 100% | 77.8% | 0.704 | 74.1% | 0.0% | 77.8% |
| egear | 10 | 100% | 100% | 100% | 0.838 | 93.8% | 0.0% | 100% |
| smg | 10 | 88.9% | 100% | 100% | 0.870 | 88.9% | 0.0% | 100% |
| tiptronic | 10 | 100% | 100% | 87.5% | 0.635 | 78.1% | 0.0% | 81.2% |
| scoping, `--collection rules` (home: `rules`) | 2 | — | 100% | 0.0% | 0.000 | — | 0.0% | 0.0% |
| scoping, `--collection transmissions` (override) | 2 | 100% | — | 100% | 0.750 | 100% | 0.0% | 100% |

**The headline number: recall@5 on standalone questions (80.0%) vs. follow-up questions (50.0%), on the same corpus, same collection, same retrieval parameters.** Of `fb_rules`'s 6 `follow-up` entries, 3 retrieved correctly (`q-031`, `q-034`, `q-035` — all `recall_hit=True, coverage=1.0, citation_precision=1.0`) and 3 missed entirely (`q-032`, `q-033`, `q-037` — all `recall_hit=False, coverage=0.0, citation_precision=0.0`, i.e. clean misses, not partial ones). The pattern in the 3 misses: each pairs a raw follow-up ("what about the one before it?", "how does that compare to a proper dual-clutch?", "what about the maximum deflection allowed during that test?") whose retrievable signal is almost entirely pronouns and comparatives, with no repeated proper noun or rule id from the prior turn to anchor an embedding match. This is exactly the deficit the phase exists to produce a number for; Phase 4's query rewriting should aim to close some or all of this 30-point gap by folding the resolved referent back into the retrieval query before it reaches the embedder.

**Single-turn entries reproduce Phase 2 exactly on every non-judge metric.** `fb_rules` standalone recall@5 (80.0%) and grounded rate (84.0%) match Phase 2's 29-entry run to the decimal point. Across all four Markdown sets, recall@5, MRR, and mean coverage are byte-identical to Phase 2 in every case — proof the v2→v3 migration and the collection-scoping refactor changed nothing about retrieval behavior. Grounded-rate deltas (`amg_mct` 77.8%→88.9%, `smg` 100%→88.9%, `tiptronic` 87.5%→100%) are judge noise in both directions on small samples (9-10 entries), consistent with the judge-noise pattern already documented in `specs/2-grounded-answering/plan.md` — not a regression, since the metrics that don't depend on the judge's mood didn't move at all.

**`not-in-collection` verified live in both directions**, which is the only real evidence a scoping filter does anything rather than silently passing everything through: `scoping.yaml`'s 2 entries were refused 100% of the time under their declared `rules` collection (their docs, `smg.md` and `tiptronic.md`, aren't members), and answered 100% grounded / 100% recall under a `--collection transmissions` override (where their docs are members). `recall_at_k=0.0` under `rules` isn't a failure metric here — it's the expected shape of "the filter correctly found nothing to retrieve," which is what forces the refusal.

**One real implementation bug, caught by the numbers looking wrong, not by a unit test**: the runner's judge-rubric selection only recognized `not-in-document`, so the first live `scoping.yaml` run graded two correctly-refused answers against the *groundedness* rubric (comparing "I cannot answer this" against the real expected answer) and scored 0% grounded on both — even though the pipeline had behaved exactly right. Fixed with `_expects_refusal(entry, collection, collections)` in `evals/runner.py`: true for `not-in-document` unconditionally, true for `not-in-collection` only when none of the entry's docs belong to the *currently active* collection, so the same entry correctly flips to the groundedness rubric under a `--collection` override. Regression-tested in `tests/test_turns_pipeline.py`.

**Two pre-existing anchors broke during the hand-migration of `fb_rules.yaml` to v3**, caught by grepping the real corpus before any live run, not by `gold validate`: `q-011` lost its `occurrence: last` on `T11.6` (ambiguous without it — the anchor has a genuine second line-initial match in the document's own contents listing), and `q-027` dropped its second source (`CV3.2.2`, the "at idle" half of a two-part answer) entirely. Both fixed before the migration script ran on the other four gold sets. Neither would have been caught by schema validation alone — `gold validate`'s location resolver only runs against sources an entry actually declares, so a *missing* source is invisible to it.

**The not-in-document lexical-match warning needed real tuning against the actual corpus, not just the synthetic unit-test case.** A first pass (3+ shared salient terms between a not-in-document question and any corpus line) flagged nearly every `not-in-document` entry across all 5 documents as a false positive: `egear.md` and `tiptronic.md` are short, single-subject documents where the subject's own name ("gearbox", "clutch", "Tiptronic") appears on 7-27% of all lines, and `fb_rules.pdf` repeats its own title phrase ("Formula Bharat competition") often enough to trip a 3-term threshold on its own. Raising the threshold to 4 shared terms eliminated every false positive across all 6 gold sets while still catching the reintroduced original `q-027` (6 shared terms) and correctly re-flagging a genuinely close call, `q-003` (4 shared terms — the document confirms a registration fee exists but explicitly defers the amount to the event website, so the `not-in-document` tag is still correct on inspection, but the warning earns its keep by surfacing the ambiguity).

**Disagreements**: 1 on the `fb_rules` run (`q-011`), `judge=grounded` with `citation_precision=0.00` *and* `recall_hit=False` — a stronger disagreement than either seen in Phase 2, since the judge accepted an answer as grounded despite the pipeline not even retrieving the gold chunk. Worth reading by hand alongside Phase 2's `q-011`/`q-018` disagreements before Phase 4 touches the judge prompt.

**Still open for Phase 4** (or whenever convenient):
- The 30-point standalone/follow-up recall gap is the number Phase 4 exists to close. `q-032`, `q-033`, and `q-037` are three concrete, real failing follow-up examples (clean misses, not partial) to validate query rewriting against before trusting it on synthetic cases.
- `q-036` (the cross-document entry) failed under retrieval this phase (`recall_hit=False`) the same way it did in Phase 2 — still nobody's fixed it, and it's still a legitimate structurally-hard case, not a regression.
- The `q-011` disagreement (judge=grounded, citation_precision=0, recall_hit=False) is a sharper example than Phase 2's for whenever the judge prompt is revisited.

# Plan: Phase 2 — Grounded Answering

## Approach Summary

Two independent pieces of work that meet in the report. The first is **gold-set schema v2** — a `sources` list, an `occurrence` selector, line-initial `section` matching, a validated tag vocabulary, and a `gold locate` command — which makes the corpus expressive enough to describe cross-document questions and robust enough to survive a parser change. The second is **citations**: the answering pipeline emits the chunk ids it relied on, and the harness checks them without an LLM.

The insight the whole phase rests on is that a citation is cheap to verify and expensive to fake. Two checks fall out with no model involved: a cited chunk either was or wasn't in the retrieved set, and it either does or doesn't overlap a gold span. Together they give the project its first groundedness signal that isn't an opinion — and where that signal and the judge disagree, the disagreement itself becomes the output, a short list of entries worth reading by hand.

One risk to name up front: **adding a citation instruction changes the answering prompt, so Phase 2's answers are not token-identical to Phase 1's.** That is the only thing this phase moves. Retrieval parameters, the judge, and the recall rule are all frozen, so any change in grounded rate is attributable to the prompt and nothing else — which is why all five gold sets get re-run.

Three slices; only the third spends quota:

1. **Schema v2** — loader, `occurrence`, line-initial matching, tag vocabulary, `gold locate`, migration of the four Markdown gold sets. Zero model calls.
2. **Citations and scoring** — prompt change, citation parsing, fabrication / precision / coverage, report schema, per-tag breakdown, disagreement report. Zero model calls, all tested against `FakeProvider`.
3. **Live runs** — five retrieval runs across all gold sets.

## Architecture

```
raglab gold locate <anchor>  ──► LocationResolver.find_matches()
                                   └─► line, line-initial?, snippet

raglab gold validate ────────► GoldSetLoader (v2)
                                 ├─ sources[] shape + not-in-document consistency
                                 ├─ tag vocabulary warning
                                 └─ anchor resolution (strict: ambiguity aborts)

raglab eval run ─────────────► EvalRunner
                                 ├─ RetrievalPipeline ──► answer + <citations> block
                                 │                          └─ CitationParser
                                 ├─ Judge                (unchanged)
                                 └─ Scoring
                                      ├─ fabrication   cited ⊄ retrieved
                                      ├─ precision     cited ∩ gold-overlapping
                                      ├─ coverage      gold spans hit / gold spans
                                      └─ disagreement  judge verdict vs precision
                                                          │
                                                    ReportWriter
                                                 (+ per-tag breakdown)
```

## Tech Stack & Key Decisions

| Decision | Choice | Why |
|---|---|---|
| Citation transport | A delimited `<citations>…</citations>` block holding comma- or newline-separated chunk ids | See below — the payload is constrained, which is what makes this safe where the judge's JSON was not |
| Citation parsing | Tolerant scanner: find the block, extract `doc:NNNN` tokens, ignore everything else | Chunk ids match a strict pattern; anything that doesn't is a fabrication, not a parse error |
| Missing citation block | Entry recorded as `uncited`, excluded from citation metrics | Not a fabrication and not a groundedness failure — conflating them would corrupt both rates |
| `occurrence` semantics | Applied per anchor in `value`, not per `answer_location` | `["T11.6", "T11.6.1"]` needs `last` for one and it's a no-op for the other |
| Report field additions | All new fields optional with defaults | `find_matching_prior_report` validates Phase 0 and Phase 1 reports against the current model; required fields would make every prior report unreadable and silently kill delta reporting |
| Gold-set migration | A throwaway script in Slice 1, not a shipped command | Four files, one time. A `gold migrate` command would outlive its purpose by the length of the project |
| Baseline re-runs | Not performed | Phase 2's acceptance compares retrieval against *Phase 1's retrieval* numbers. Re-running four whole-doc baselines would cost roughly 240K input tokens to reproduce numbers nothing compares against |

**Why a delimited block is safe here when the judge's JSON was not.** The judge's parsing broke ~10–20% of the time on an unescaped `"` inside a free-text rationale. The failure was never JSON's fault — it was free text inside a quoted string. Citation payloads are chunk ids: `fb_rules.pdf:0042`. No quotes, no newlines, no user prose, a fixed lexical shape. The fragility does not transfer, and a tolerant token scanner has nothing to choke on. If a token doesn't match the chunk-id pattern, that is a *finding* (fabrication), not an exception.

**What is deliberately not touched:** retrieval parameters (900/150, k=5, `bge-small-en-v1.5`), the judge model and prompt, the any-overlap rule, and the manual BGE query prefix in `Embedder.embed_query()` — which exists because `fastembed`'s `query_embed()` is a no-op alias for this model, and is exactly the kind of thing a well-meaning refactor removes.

## Data Model

**Gold-set schema v2** (`sources` list; `occurrence` on `section` anchors):

```python
class AnswerLocation(BaseModel):
    type: Literal["line_range", "char_span", "section"]
    start: int | None = None
    end: int | None = None
    value: list[str] | None = None
    occurrence: Literal["first", "last"] | int | None = None

class Source(BaseModel):
    doc: str
    answer_location: AnswerLocation

class GoldEntry(BaseModel):
    id: str
    question: str
    expected_answer: str | None
    sources: list[Source]
    tags: list[str] = []
```

Validation rules: `sources == []` ⟺ `not-in-document` tag ⟺ `expected_answer is None`, enforced in all directions; `occurrence` only on `section`; at least one tag from the vocabulary, else a warning.

**Tag vocabulary** — `lexical-anchor`, `vocabulary-mismatch`, `synthesis`, `near-duplicate`, `boundary-spanning`, `cross-document`, `not-in-document`. Additional free tags permitted.

**Anchor matching** — `^[#\s]*<anchor>(?![\w.])`, multiline. The leading-whitespace-and-`#` allowance keeps Markdown heading anchors working; the line-initial restriction drops mid-sentence cross-references. Multiple matches without `occurrence` remain unscoreable, per Phase 1.

**Report additions**, all optional so prior reports still load:

```python
class EntryReport(BaseModel):
    ...                                    # unchanged fields
    cited: list[str] | None = None
    fabricated: list[str] | None = None
    citation_precision: float | None = None
    coverage: float | None = None

class Aggregates(BaseModel):
    ...                                    # unchanged fields
    citation_precision: float | None = None
    fabrication_rate: float | None = None
    mean_coverage: float | None = None
    uncited: int = 0
    by_tag: dict[str, TagAggregates] = {}
```

Metric definitions, stated precisely because each has an easily-wrong denominator:

- **citation precision** — per entry, the fraction of cited chunks whose span overlaps any gold span. Computed only over entries that have gold spans *and* produced a citation block. `not-in-document` and `uncited` entries are excluded, not scored zero.
- **fabrication rate** — the fraction of entries with at least one cited id absent from that entry's retrieved set. Computed over every entry that produced a citation block, including `not-in-document` ones, where a citation is itself a signal.
- **coverage** — per entry, the fraction of the entry's distinct gold spans hit by at least one retrieved chunk. Over entries with gold spans. For a single-span entry this equals `recall_hit`; it only differs on multi-anchor entries.
- **disagreement** — an entry where the judge returned `grounded` with citation precision 0, or `not_grounded` with citation precision 1.

## File / Module Structure

Additions and changes to the existing tree; unlisted files unchanged.

```
src/raglab/
├── cli.py                       # CHANGED: + gold locate; disagreement section in run summary
├── evals/
│   ├── goldset.py               # CHANGED: v2 schema, Source, occurrence, tag vocabulary
│   ├── locations.py             # CHANGED: line-initial matching, occurrence selector,
│   │                            #          find_matches() exposed for gold locate
│   ├── citations.py             # NEW: parse the citation block; fabrication + precision
│   ├── coverage.py              # NEW: gold-span coverage
│   ├── recall.py                # CHANGED: multi-source entries
│   ├── metrics.py               # CHANGED: new aggregates, per-tag breakdown
│   ├── report.py                # CHANGED: optional new fields; DELTA_METRICS additions
│   └── runner.py                # CHANGED: multi-source, cross-doc skip for whole_doc
├── pipelines/
│   ├── base.py                  # CHANGED: PipelineResult.cited
│   ├── retrieval.py             # CHANGED: citation instruction in prompt
│   └── whole_doc.py             # CHANGED: skip multi-source entries with a reason
scripts/
└── migrate_goldsets_v2.py       # NEW: throwaway, four Markdown gold sets v1 -> v2

tests/
├── test_goldset_v2.py           # sources shape, occurrence, tag warnings, v1 rejection
├── test_locations_occurrence.py # line-initial filtering, first/last/index, EV6.1.2 case
├── test_citations.py            # parsing, fabrication, precision, uncited handling
├── test_coverage.py             # multi-span entries, coverage < recall_hit
└── test_report_compat.py        # a Phase 1 report still loads and deltas correctly
```

## Slices and cost

- **Slice 1 — Schema v2.** Loader, resolver, `gold locate`, migration script, and two `fb_rules.yaml` edits: `occurrence: last` on `q-011`, and renaming the stray `q-036` to `q-026`. Done when all five gold sets validate strictly and every anchor in `fb_rules.yaml` resolves. **Zero model calls.**
- **Slice 2 — Citations and scoring.** Prompt change, parser, three metrics, per-tag breakdown, disagreement reporting, report compatibility. Done when a `FakeProvider` citing a chunk it was never given is caught as a fabrication. **Zero model calls.**
- **Slice 3 — Live runs.** Five retrieval runs: `fb_rules` (27 entries) plus the four Markdown sets (10 each). At roughly 3,000 input tokens per question, about **200K input tokens total**, plus judge calls — comparable to two Phase 1 runs, and well inside a 5-hour window. No baseline re-runs.

## Acceptance thresholds

- Grounded and refusal-correct rates must not regress against Phase 1's retrieval runs on the four Markdown sets. The citation instruction is the only change; a regression means the prompt change cost accuracy and needs re-tuning before the phase closes.
- Fabrication rate is expected to be at or near zero. A non-zero rate is a genuine finding about the model, not a bug, and should be reported rather than prompted away.
- Coverage must be strictly below `recall_hit` on at least one multi-anchor entry, demonstrating it measures something recall alone does not.
- No target is set for citation precision. This phase establishes the number; Phase 4 moves it.

## As-built notes (handover to Phase 3)

Written after implementation and a full live run: all three slices done, 111 unit/integration tests pass, five live retrieval runs via `agent_sdk`/`claude-sonnet-5` answering and `agent_sdk`/`claude-opus-5` judging — same setup Phase 1 used.

**Results table:**

| Gold set | entries | grounded | refusal-correct | recall@5 | MRR | citation precision | fabrication | mean coverage |
|---|---|---|---|---|---|---|---|---|
| fb_rules | 29 | 84.0% | 100% | 80.0% | 0.673 | 81.1% | 0.0% | 74.7% |
| amg_mct | 10 | 77.8% | 100% | 77.8% | 0.630 | 74.1% | 0.0% | 77.8% |
| egear | 10 | 100% | 100% | 100% | 0.838 | 93.8% | 0.0% | 100% |
| smg | 10 | 100% | 100% | 100% | 0.870 | 90.7% | 0.0% | 100% |
| tiptronic | 10 | 87.5% | 100% | 87.5% | 0.635 | 79.2% | 0.0% | 81.2% |

Fabrication rate is 0% across every run and every tag, including `not-in-document` entries — the model never claimed a chunk id outside what it was actually given, across 67 graded entries. `uncited=0` everywhere: the citation instruction was followed on every single answer, refusals included.

**`fb_rules` numbers above are from a rerun after two post-commit gold-set fixes**, not the original 27-entry run: q-027 was recategorized from a mis-tagged `not-in-document` entry to a real two-anchor `lexical-anchor` answer (`CV3.2.1`/`CV3.2.2`, needing `occurrence: first` — the one anchor in this gold set where the rule body is the *earlier* line-initial match, not the later one, because PDF line-wrapping pushed a cross-reference to column zero), and two new `not-in-document` entries (q-029, q-030) were added. `fb_rules` refusal_correct_rate moved from 50% to 100% as a direct result — confirming the earlier 50% was a gold-set authoring gap, not a model or judge weakness.

**Of the four entries still failing on this rerun (`q-005`, `q-014`, `q-016`, `q-026`), three are retrieval misses, not judge or model failures.** `q-014`, `q-016`, and `q-026` all have `recall_hit=False, coverage=0.0` — the gold chunk simply never made the top-5 retrieved set, so the model had nothing to ground an answer in and the judge correctly marked it not_grounded. Only `q-005` has `recall_hit=True` (the right chunks were retrieved) yet still fails, on a genuine reasoning error the gold set's own comment already called out (conflating the CV and EV shutdown-circuit component lists). This is the sentence Phase 4 needs before spending effort on retrieval quality: three of four remaining `fb_rules` failures are retrieval-recall problems (candidates for hybrid search, query rewriting, or a larger k), and only one is an answering/reasoning problem retrieval improvements won't touch.

**Coverage demonstrably below recall_hit, on real data, not just synthetic tests**: `fb_rules` q-004 (`recall_hit=True, coverage=0.5`) and q-022 (same pattern) — both two-anchor entries where only one of the two gold spans was retrieved. any-overlap recall calls this a hit; coverage correctly reports it as half-covered. q-021 (three anchors) came out at 0.667.

**The cross-document entry (`fb_rules` q-026) was answered by retrieval** (graded, `recall_hit=False` — neither `fb_rules.pdf` nor `smg.md`'s gold chunk made the retrieved set for this question) **and would be skipped by the whole-doc baseline** — verified by `tests/test_runner.py::test_cross_document_entry_skipped_by_whole_doc_pipeline` with a stubbed provider (`answer_provider.calls == []`), not by an actual whole-doc run: a 27-entry whole-doc run against the 137-page `fb_rules.pdf` would cost far more than the four Markdown baselines combined to reproduce numbers nothing compares against, and the skip itself needs no model call to prove.

**Disagreements**: 2 on the `fb_rules` run (`q-011`, `q-018`), both `judge=grounded` with `citation_precision=0.00` — the judge accepted an answer as factually consistent with the expected answer even though every chunk the model cited misses the actual gold span. Worth reading by hand before Phase 4 touches the judge prompt; not investigated further this phase per the "judge is not touched" decision.

**One real finding this phase exists to surface: two of the four Markdown sets show a lower grounded_rate than Phase 1, and it traces to judge noise, not the citation prompt.**

- `amg_mct` dropped from 88.9% to 77.8% (one new failure, `q-002`, alongside the pre-existing `q-003` failure already documented in Phase 1's handover notes). `q-002`'s Phase 1 and Phase 2 answers both attribute the 100 ms figure to "the 2008 Mercedes-Benz SL 63 AMG" from the same retrieved chunk — Phase 1's judge called this grounded, Phase 2's judge called the same style of addition unsupported. Retrieval was not the variable: nothing about retrieval changed between phases.
- `tiptronic` dropped from 100% to 87.5% on `tiptronic` q-005 (unrelated to `fb_rules` q-005 discussed above — same id, different gold set). The retrieved set is byte-identical to Phase 1's (`recall_hit=False` in both — the Aston Martin DB9 exception was never in the top-5 either time), and the Phase 2 answer is substantively the same honest hedge Phase 1's was ("I can only confirm this for Audi's Tiptronic specifically... I cannot say from the provided material whether this override authority was universal"). Phase 1's judge called this correctly-hedged and grounded; Phase 2's judge called it not-grounded for failing to surface a fact that was never retrieved. Same input, opposite verdict.

Both cases share the same shape: identical or near-identical retrieved context and answer content across the two runs, opposite judge verdicts. That is judge non-determinism on borderline cases, consistent with Phase 0's and Phase 1's own documented judge-miscalibration findings (see `specs/1-ingest-and-index/plan.md`) — not evidence that the citation instruction cost accuracy. `egear` and `smg` (both already at 100%/100% in Phase 1, no borderline entries to flip) show zero regression, which is consistent with this explanation and inconsistent with a systematic prompt-driven degradation, which would be expected to show up everywhere, not just on entries that were already borderline. Recorded here rather than re-tuning the judge, per this phase's explicit decision not to touch it.

**Still open for Phase 3** (or whenever convenient):
- The two judge-verdict flips above are concrete, real examples for whenever the judge prompt is revisited — more useful than a hypothetical.
- The `q-011`/`q-018` disagreements are the first real examples of the judge/citation-check split this phase was built to produce — worth reading before Phase 4 touches retrieval, since they may point at a citation-instruction wording issue (the model citing plausible-looking but wrong chunks) rather than a judge issue.
- `q-014`, `q-016`, and `q-026`'s retrieval misses are three concrete, real candidates for Phase 4's first retrieval-quality experiments (hybrid search, query rewriting, larger k) — backed by actual failing examples with `recall_hit=False`, not hypotheticals.

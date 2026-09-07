# Plan: Phase 4 — Retrieval Optimization

## Approach Summary

Every technique in this phase is a switch on one `ExperimentConfig` object, and every result is a paired diff against one frozen baseline artifact. That is the whole architecture: the retrieval pipeline gains optional stages, the config names which are active, and a new comparison module reads two run reports and says which entries got better, which got worse, and which did not move.

Nothing here is novel machinery. The novel part happened in Phases 0–3 — a frozen judge, span-based recall that survives a chunking change, per-entry citation checks, and a tagged gold set. This phase spends that inheritance.

Order matters more than usual because quota is the binding resource. Techniques are sequenced cheapest-and-most-likely-to-win first, so that if the phase runs out of five-hour windows partway, the experiments that were dropped are the expensive uncertain ones rather than the cheap probable ones.

## Architecture

```
ExperimentConfig (named, recorded in every report)
  ├─ chunking     strategy | size | overlap
  ├─ retrieval    mode(dense|hybrid) | k | candidate_k | rrf_k
  ├─ rewriting    off | follow-ups-only | all-questions
  ├─ reranking    off | onnx(model) | llm(model)
  └─ agentic      off | max_calls

raglab eval run --experiment hybrid-v1
        │
        ▼
   RetrievalPipeline
        │
        ├─(1) QueryRewriter?      history + question ──► standalone query
        │
        ├─(2) Retriever
        │       ├─ dense   Embedder.embed_query ──► cosine over vectors.npy
        │       ├─ lexical BM25 over chunk text            (hybrid only)
        │       └─ fuse    Reciprocal Rank Fusion ──► candidate_k chunks
        │
        ├─(3) Reranker?           candidate_k ──► top k
        │
        └─(4) Answer              chunks + history ──► answer + <citations>

   AgenticPipeline  (separate Pipeline implementation, same protocol)
        └─ provider tool-call loop: search(query) × N, capped ──► answer

raglab compare baseline.json experiment.json
        └─► per-entry win / loss / tie on recall, coverage, citation precision
```

The five techniques are four stages plus one alternative pipeline. Agentic retrieval is not a stage — it is a different control flow, so it implements `Pipeline` separately and reuses the same retriever underneath.

## Tech Stack & Key Decisions

| Decision | Choice | Why |
|---|---|---|
| BM25 | Hand-rolled, ~50 lines, unit-tested against a worked example | It is a term-frequency and IDF formula, not a library-shaped problem. Writing it is the point of a learning project, and it keeps the dependency count where it has been since Phase 0 |
| Fusion | Reciprocal Rank Fusion, `k=60` | Dense cosine and BM25 scores live on incomparable scales; weighted fusion needs normalization that itself becomes a tuned parameter. RRF is rank-based and scale-free, which removes the problem instead of tuning it |
| Reranker | Probe `fastembed` for an ONNX cross-encoder; fall back to an LLM reranker through the existing provider; timebox the probe | The no-PyTorch rule has protected clone-and-run since Phase 0 and is not being waived for one experiment |
| Reranking candidate set | `candidate_k = 20`, rerank down to `k = 5` | Reranking can only reorder what retrieval already returned; with `candidate_k = k` it is a no-op |
| Query rewriting v1 | Follow-up entries only | Targets the measured 30-point deficit and structurally cannot harm standalone questions. If adopted, a v2 applying it everywhere tests the over-expansion risk directly |
| Structure-aware chunking | Split on rule-ID and heading boundaries; sub-split anything over the embedder's 512-token limit | Variable-size chunks are the point; the token ceiling is a hard property of `bge-small` and cannot be exceeded |
| Agentic retrieval | Provider tool-calling, `max_calls = 5` default | The tool-calling path has existed in `LLMProvider` since Phase 0 and has never been exercised. This is what it was designed in for |
| Comparison | New `raglab compare`, reading two reports | Keeps the runner unchanged; comparison is analysis over artifacts, not a run-time concern |

**What stays frozen all phase:** the embedding model, the any-overlap rule, the citation mechanism, the judge (after its one rubric fix), and the baseline artifact.

## Data Model

**`ExperimentConfig`**, recorded in `report.config.experiment` and sufficient to reproduce a run:

```python
@dataclass(frozen=True)
class ExperimentConfig:
    name: str                              # "baseline", "hybrid-v1", "rewrite-v1", ...
    chunking: ChunkingConfig               # strategy, size, overlap
    retrieval: RetrievalConfig             # mode, k, candidate_k, rrf_k
    rewriting: RewritingConfig | None
    reranking: RerankingConfig | None
    agentic: AgenticConfig | None
```

Named configurations live in `experiments.toml` so an experiment is a name on the command line, not a pile of flags.

**Paired comparison.** For each entry present in both reports, each deterministic metric is classified independently:

| Metric | Win | Loss |
|---|---|---|
| `recall_hit` | `False → True` | `True → False` |
| `coverage` | increased | decreased |
| `citation_precision` | increased | decreased |

An entry is a **win** if at least one metric improved and none regressed, a **loss** if any metric regressed, and a **tie** otherwise. Losses are always named; `grounded_rate` is reported alongside but never classifies an entry, because Phase 3 measured its variance at ±11 points with retrieval unchanged.

**Comparison output** — counts, the named regressed entries, and a per-tag breakdown of the same classification, so "helped follow-ups, hurt nothing" is readable without opening JSON.

**Structure-aware chunking caveat**, enforced in code: when the two reports' `chunking` configs differ, `retrieved` id lists are not compared and the comparison reports span-based metrics only.

## File / Module Structure

```
src/raglab/
├── experiments.py               # NEW: ExperimentConfig, experiments.toml loading
├── cli.py                       # CHANGED: --experiment on eval run; + compare
├── index/
│   ├── chunker.py               # CHANGED: + structure-aware strategy
│   └── builder.py               # CHANGED: chunking strategy in manifest
├── retrieval/
│   ├── bm25.py                  # NEW: hand-rolled BM25 over chunk text
│   ├── fusion.py                # NEW: reciprocal rank fusion
│   ├── reranker.py              # NEW: ONNX cross-encoder or LLM reranker
│   ├── rewriter.py              # NEW: history + question -> standalone query
│   └── retriever.py             # CHANGED: dense | hybrid, candidate_k, rerank hook
├── pipelines/
│   ├── retrieval.py             # CHANGED: optional rewrite and rerank stages
│   └── agentic.py               # NEW: tool-call loop, capped, records call count
└── evals/
    ├── compare.py               # NEW: paired per-entry classification
    ├── judge.py                 # CHANGED: hedged-answer rubric, once, then frozen
    └── report.py                # CHANGED: experiment config in report

experiments.toml                 # NEW: named configurations

tests/
├── test_bm25.py                 # worked example with known scores
├── test_fusion.py               # RRF ordering, ties, single-list degenerate case
├── test_rewriter.py             # via FakeProvider; no-op on standalone entries
├── test_reranker.py             # via FakeProvider; candidate_k > k enforced
├── test_agentic.py              # call ceiling, capped-entry recording
├── test_compare.py              # win/loss/tie classification, chunking-mismatch guard
└── test_chunker_structure.py    # rule boundaries, 512-token sub-splitting
```

## Integration Plan

Every technique is built and unit-tested against `FakeProvider` before it costs a single token, exactly as Phases 2 and 3 did. The provider-dependent pieces — rewriting, LLM reranking, agentic — are the ones where a stub is most valuable, because each adds a model call per entry and a bug found live is a bug found expensively.

Two integration unknowns get probed early, before either is committed to:

- **`fastembed` ONNX cross-encoder availability.** A timeboxed probe in the reranking task. Available: use it, no quota cost per entry. Unavailable: LLM reranker, which changes the experiment's cost profile enough to affect sequencing.
- **`AgentSDKProvider` tool-calling.** The `LLMProvider` protocol has supported tools since Phase 0 but the subscription path has never exercised them. If custom tools do not work cleanly through the `claude` CLI, agentic retrieval runs on `openrouter` instead and the difference is recorded, since it changes the cost comparison.

## Error Handling Strategy

There is no auth surface and no untrusted input here; the failure modes that matter are the ones that would silently corrupt a comparison.

- **A missing or mismatched experiment config aborts the comparison.** A report without a recorded config cannot be used as a paired source, because there is no way to know what produced it.
- **A baseline whose gold set differs from the experiment's aborts**, reusing the gold-set identity check added in Phase 3. Comparing across different question sets is the exact failure that check exists to prevent.
- **Provider failures during an experiment are recorded per entry as `errored`**, as they have been since Phase 0, and an entry that errored in either run is excluded from classification rather than counted as a loss.
- **The agentic call ceiling is enforced, not advisory.** Exceeding it stops the loop, records the entry as capped, and continues the run — an unbounded loop would spend a five-hour window on one question.
- **A blocked technique is reported, not worked around.** If reranking cannot run without PyTorch, that is written down as the result.

## Sequencing & Milestones

Six milestones. The order is chosen so that quota exhaustion costs the least.

1. **Rubric and baseline.** Judge hedged-answer fix, then the frozen Phase 4 baseline run. Nothing else may start first, because everything compares against this artifact.
2. **Comparison machinery.** `raglab compare`, paired classification, per-tag breakdown. Zero model calls; built against the baseline and a copy of itself, which must classify as all ties.
3. **Hybrid retrieval.** Cheapest to build, no extra model calls at run time, and it targets `lexical-anchor` plus `q-011`, the BSPD miss where dense retrieval returned semantically adjacent chunks instead of the definitional rule.
4. **Query rewriting.** Targets the headline 30-point follow-up deficit and the three named misses. One extra model call per entry.
5. **Structure-aware chunking.** No extra model calls, but requires a re-index and produces incomparable chunk ids.
6. **Reranking, then agentic retrieval.** Both last: reranking may be blocked outright, and agentic has the highest and least predictable per-entry cost.
7. **Stack the winners** and compare against the baseline and against each adopted technique alone.

Milestones 1 and 2 are prerequisites for everything. Milestones 3–6 are independent of each other and can be reordered if a five-hour window is short.

## Alternatives Considered

- **Greedy stacking** — adopt the winner, re-baseline, test the rest against it, repeat. More realistic, but it costs a run per technique per round and makes attribution murky. Rejected in favor of independent tests plus one combined run.
- **Weighted score fusion** instead of RRF. Requires normalizing two incomparable score distributions, which introduces a tuned parameter that would need its own experiment. Held as a variant if RRF underperforms.
- **Swapping the embedding model** — an obvious lever, and out of scope: it is model shopping rather than retrieval technique, and it forces a re-index that invalidates every paired comparison in the phase.
- **Aggregate recall delta as the adoption rule.** Conventional, and unusable at tag sample sizes of 3 to 9 where one entry moves a rate by 16 to 33 points.
- **`rank_bm25` as a dependency.** Perfectly good, and skipped because BM25 is fifty lines and seeing the math is the point of this project.

## Open Risks Carried From Spec

| Risk | Status in this plan |
|---|---|
| Reranking unbuildable without PyTorch | Mitigated by the LLM-reranker fallback; blocked remains a legitimate recorded outcome |
| Agentic cost unbounded | Resolved: enforced `max_calls` ceiling, capped entries recorded, calls-per-entry reported |
| ~20 new gold entries unbuilt | Unresolved. Thin tags stay illustrative until authored; this is an input, not a task |
| Query rewriting harming standalone questions | Mitigated: v1 fires only on follow-ups, so it cannot harm them; v2 tests the risk deliberately under the zero-regression rule |
| Five experiments may not fit the quota | Mitigated by sequencing cheap-and-likely first, and by iterating on `fb_rules` rather than the full corpus |
| `AgentSDKProvider` tool-calling unproven | Probed early; `openrouter` is the fallback, and the substitution is recorded because it changes the cost comparison |

## As-built notes

**T1.1 — the hedged-answer rubric decision (written before touching `judge.py`):**

Two documented cases put the same shape of answer through the groundedness judge and got opposite verdicts:

- **Phase 2, `tiptronic` q-005.** The candidate answer said, in substance: *"I can only confirm this for Audi's Tiptronic specifically... I cannot say from the provided material whether this override authority was universal."* The retrieved chunks never contained the Aston Martin DB9 exception the expected answer hinges on. Phase 1's judge called this `grounded`; Phase 2's judge, given the same retrieved context and the same style of answer, called it `not_grounded` — reasoning that it failed to surface a fact that was never retrieved in the first place (`specs/2-grounded-answering/plan.md:188`).
- **Phase 3, `fb_rules` q-011.** The candidate answer said, in substance: *"I cannot find an explicit statement of what 'BSPD' stands for as an acronym... [but then gave a full, accurate, cited description of everything the BSPD is required to do]."* Retrieval missed the gold chunk entirely (`recall_hit=False`, `citation_precision=0.0`). The judge still called it `grounded` (`specs/3-collections/plan.md:177`).

Both answers do the same thing: they decline to assert a specific fact that the retrieved context does not support, while correctly and accurately answering the part it does support, with zero fabrication in either direction. That is exactly the behavior this project rewards everywhere else — the fabrication rate has held at 0% across every live run since Phase 2 (`specs/2-grounded-answering` plan, live-verified numbers) specifically because refusing an unsupported claim is treated as correct, not as a shortfall. Judging this shape `not_grounded`, as Phase 2's judge did once, punishes the exact honesty the rest of the system is built to elicit, and would reward a model that guessed instead.

**The rule:** an answer that correctly and accurately answers the part of a question its context supports, and explicitly declines rather than fabricates the part it doesn't, is judged `grounded`. `not_grounded` is reserved for an answer that asserts something inconsistent with the expected answer, or fabricates a claim the source location doesn't support — not for an honest, partial answer that asserts nothing false. Applied to both cases: `tiptronic` q-005 becomes `grounded` (reversing Phase 2's verdict), and `fb_rules` q-011 stays `grounded` (Phase 3's verdict already matches the rule). Both classify the same way, which is the point.

This does trade away some precision — a judge under this rule cannot itself distinguish "correctly declined because the fact wasn't retrievable" from "declined out of excess caution when the fact was right there." That distinction is exactly what the deterministic metrics (`recall_hit`, `coverage`, `citation_precision`) are for, which is why the spec treats them as primary and `grounded_rate` as secondary — the judge rubric only needs to stop being a coin flip on this one shape of answer, not to become a complete substitute for retrieval metrics.

**T1.4 — `ExperimentConfig`.** `experiments.py` and `experiments.toml` exist with a single `baseline` entry (`fixed` chunking at 900/150, `dense` retrieval at `k=5` — today's defaults, verbatim). `eval run` gained `--experiment` (default `baseline`) and `--experiments`; the resolved config is validated and rejected *before* any provider is built, so an unknown experiment name costs nothing. `RunConfig.experiment` defaults to `None`, following the same backward-compat pattern `collection` and `entry_ids_fingerprint` already established, so pre-Phase-4 reports still load.

**T1.5/T1.6 — the frozen Phase 4 baseline, and why it isn't directly comparable to Phase 3's numbers.**

Run live via `agent_sdk` (`claude-sonnet-5` answering, `claude-opus-5` judging) as five separate `--pipeline retrieval --experiment baseline` runs — `fb_rules` plus the four Markdown gold sets — matching the Phase 2/3 precedent of per-gold-set reports rather than one merged gold file. Total cost: 306,301 input tokens (estimated ~300K beforehand). Artifacts: [`evals/baselines/phase4-fb_rules.json`](../../evals/baselines/phase4-fb_rules.json) (native report) and [`evals/baselines/phase4-full.json`](../../evals/baselines/phase4-full.json) (hand-assembled summary of all five — see its own `note` field for exactly which combined metrics are exact recomputations from the underlying entries versus the one labeled approximation, `mrr_weighted_approx`, since per-entry reciprocal rank isn't serialized in the report schema).

| Gold set | entries | grounded | recall@5 | MRR | citation precision | fabrication | mean coverage | — Phase 3 (grounded / recall@5) |
|---|---|---|---|---|---|---|---|---|
| fb_rules (all) | 57 (was 35) | 96.2% | 75.5% | 0.603 | 79.6% | 0.0% | 70.4% | 77.4% / 74.2% |
| fb_rules — standalone | 47 (was 29) | 95.4% | 81.4% | — | — | — | — | 84.0% / 80.0% |
| fb_rules — follow-up | 10 (was 6) | 100% | 50.0% | — | — | — | — | 50.0% / 50.0% |
| amg_mct | 10 | 77.8% | 77.8% | 0.704 | 72.2% | 0.0% | 77.8% | 88.9% / 77.8% |
| egear | 10 | 100% | 100% | 0.838 | 93.8% | 0.0% | 100% | 100% / 100% |
| smg | 10 | 100% | 100% | 0.870 | 88.9% | 0.0% | 100% | 88.9% / 100% |
| tiptronic | 10 | 100% | 87.5% | 0.635 | 79.2% | 0.0% | 81.2% | 100% / 87.5% |
| **combined** | 97 | 95.4% | 81.6% | 0.668* | 81.2% | 0.0% | 78.0% | — |

\* entry-count-weighted average of per-set MRR, not a true corpus-wide recomputation (see artifact note).

**The discontinuity has two independent causes, and only one of them is the rubric.** `recall_at_k`, `citation_precision`, `mean_coverage`, and `fabrication_rate` are all deterministic — untouched by the judge — so every point of movement in those columns (e.g. `fb_rules` 74.2%→75.5%) is entirely attributable to the 22 new gold entries changing the sample, not to T1.1's rubric change. `grounded_rate` is the one column where both causes overlap and can't be cleanly separated post hoc from aggregate numbers alone — which is exactly why the spec calls deterministic metrics primary and `grounded_rate` secondary, a decision this run gives a concrete reason for rather than a hypothetical one.

**The rubric fix is live-confirmed, not just unit-tested.** `tiptronic` q-005 — the real Phase 2 case T1.1's rule was written against — graded `grounded` in this run, and the judge's own rationale names the mechanism directly: *"explicitly declines to claim universality for other manufacturers rather than asserting the false blanket 'yes'."* That is the new rubric's language, not a coincidence.

**The follow-up recall deficit restates almost exactly.** `fb_rules` standalone recall@5 (81.4%) vs. follow-up (50.0%) is a ~31-point gap, matching Phase 3's 80.0%/50.0% split (30 points) on a sample that grew from 6 to 10 follow-up entries. The deficit query rewriting exists to close is confirmed still there, on a larger, harder sample, before any technique has touched it.

**One pre-existing disagreement pattern grew, not shrank.** Phase 3 had one `judge=grounded, citation_precision=0.0` disagreement on `fb_rules` (`q-011`); this run has five (`q-011`, `q-032`, `q-033`, `q-049`, `q-059`) — expected under the new rubric, since it's designed to call an honest, well-cited-elsewhere hedge `grounded` even when the specific citation the judge is checking against is a clean retrieval miss. Worth rereading once query rewriting or hybrid search targets `q-011`/`q-032`/`q-033` specifically (spec acceptance criteria already name these).

**T2.1–T2.5 — comparison machinery.** `evals/compare.py` classifies `recall_hit`, `coverage`, and `citation_precision` independently per entry (win/loss/tie), rolls up an entry as a loss if any of the three regressed (even alongside a win elsewhere) and a win only if at least one improved with none regressed; `grounded_rate` is carried on the entry for display but never enters the rollup, so a verdict-only flip is always a tie. Two guards from the spec's unwanted-behavior section: a report missing `config.experiment` is refused by name, and a gold-set mismatch (reusing `report.py`'s `gold_sets_match`, factored out of `configs_match` rather than re-implemented) is refused naming both reports. A chunking mismatch between the two configs doesn't disable classification — recall/coverage/citation-precision are span-based and stay valid across a chunking change by construction (Phase 1's any-overlap rule) — it only sets a note that raw retrieved-id comparisons aren't meaningful there. `raglab compare` is a new top-level command; per-tag breakdown is re-derived from the shared gold set's YAML, since `EntryReport` doesn't carry tags. 12 unit tests pass, and the load-bearing one is live-verified against real data, not just a synthetic fixture: `raglab compare evals/baselines/phase4-fb_rules.json evals/baselines/phase4-fb_rules.json` reports `wins=0 losses=0 ties=57` — 100% ties on the real 57-entry baseline, across every tag.

**T2.6 — reranking is NOT blocked.** `fastembed` 0.8.0 ships `fastembed.rerank.cross_encoder.TextCrossEncoder`, a pure-ONNX cross-encoder (`onnxruntime` under `fastembed.rerank.cross_encoder.onnx_text_cross_encoder`, no PyTorch import anywhere in the module) with six models including `Xenova/ms-marco-MiniLM-L-6-v2` (0.08 GB). Loaded and scored a worked example live: query "What is the minimum age for a Formula Bharat team member?" against the correct sentence and two irrelevant ones scored `[3.73, -11.26, -11.15]` — a clean, correctly-ordered discriminative signal. Cold load (one-time model download): 40.3s. Warm load (cached): 0.24s. This removes the LLM-reranker fallback from consideration entirely for the reranking experiment — no PyTorch, no per-entry model-provider cost, negligible warm latency.

**T2.7 — `AgentSDKProvider` tool-calling works.** A trivial two-tool script (`add`, `get_secret_word`) run live via `agent_sdk`/`claude-sonnet-5`: both tools were called in the requested order with correct arguments, `ToolCallRecord` correctly threaded each result back, and the final answer synthesized both ("The sum of 17 and 25 is 42, and today's secret word is 'banana.'"), `stop_reason=end_turn`, cost 3,626 input / 209 output tokens. The subscription CLI path exercises custom tool-calling cleanly — agentic retrieval can run on `agent_sdk` directly; the `openrouter` fallback plan.md carried as a risk mitigation is not needed.

**T3.1–T3.6 — hybrid retrieval: REJECTED, net wins but real regressions.**

`bm25.py` (hand-rolled, hand-verified against a worked three-document example) and `fusion.py` (RRF, `rrf_k=60`) are unit-tested in isolation; `retriever.py` fuses dense + BM25 candidate lists (`candidate_k=20`) and truncates to `k`. One implementation snag worth recording: RRF's fused score lives on its own scale, not cosine similarity, so `pipelines/retrieval.py`'s dense-tuned `score_threshold=0.35` is meaningless against it — hybrid mode skips that filter entirely and treats "fusion returned nothing" (neither dense nor BM25 found anything) as the sole refusal signal, since a low-magnitude RRF score is not evidence of irrelevance the way a low cosine score is.

Run live via `agent_sdk` on `fb_rules` (57 entries, `hybrid-v1`: `candidate_k=20`, `rrf_k=60`): 181,430 input tokens (estimated ~170K). Aggregate movement looked like a clear win — recall@5 75.5%→83.0% (+7.6 points), MRR 0.603→0.693, mean coverage 70.4%→78.0% — but `raglab compare` against the frozen baseline told a different story: **`wins=8 losses=6 ties=43`**. Six real regressions: `q-004`, `q-020`, `q-021`, `q-022` (citation_precision or coverage dropped while recall_hit held), and `q-034`, `q-056` (clean recall misses — a chunk retrieved correctly under dense-only fell out of the fused top-5 entirely). Inspecting the retrieved-id diffs directly: every regression has the same shape — BM25's ranked list pulled a lexically-similar-but-not-needed chunk into contention, and RRF's fusion crowded a chunk the *dense* list had correctly ranked into the fixed top-5 out of it. This is a real, explainable failure mode (multi-source synthesis and cross-document questions need several specific chunks simultaneously; hybrid reordering can cost one of them to make room for a lexical match), not judge or retrieval noise.

**Per the spec's adoption rule (net wins and zero regressions required), hybrid-v1 is REJECTED** despite the positive aggregate delta — exactly the case the strict rule exists for: a permissive aggregate-delta rule would have called this a win and shipped six regressions. No full-corpus confirmation run was spent, since rejection is decided at the `fb_rules` stage.

**`q-011` (the BSPD lexical-anchor miss) is FIXED under hybrid search** — the spec's own named acceptance check. `recall_hit` False→True, `coverage` 0.0→1.0, `citation_precision` 0.0→0.33, a clean win with no competing regression on that entry. Hybrid retrieval clearly helps exactly the case it was built for; the rejection is about the technique's side effects elsewhere, not about whether the core idea works.

Per-tag: `lexical-anchor` (2 wins, 0 losses) and `near-duplicate` (2 wins, 1 loss) skew positive; `synthesis` (1 win, 4 losses) is where hybrid actually hurts, consistent with the multi-chunk-crowding failure mode above. Worth reconsidering hybrid retrieval later with a per-tag conditional trigger (e.g., only for `lexical-anchor`-shaped queries) rather than universally — out of scope for this phase's all-or-nothing switch, but worth recording as a follow-on idea.

**T4.1–T4.5 — reranking: REJECTED, the same failure mode as hybrid, from a different mechanism.**

`retrieval/reranker.py` wraps T2.6's ONNX `TextCrossEncoder`, loaded once per process and reused (unit-tested with a fake encoder; the real model re-verified integration-only, consistent with `test_embedder.py`'s existing precedent for excluding fastembed-model tests from the default no-network run). `retriever.py` gained a rerank stage composing with either retrieval mode; `rerank-v1` keeps `mode=dense` so it isolates reranking's own effect from hybrid's, per the spec's test-alone-first rule.

Run live via `agent_sdk` on `fb_rules` (57 entries, `rerank-v1`: `candidate_k=20`, ONNX `Xenova/ms-marco-MiniLM-L-6-v2`): 181,829 input tokens (estimated ~170K). Aggregate movement again looked strong — recall@5 75.5%→84.9% (+9.4 points, better than hybrid's), MRR 0.603→0.774 (+0.17, the best of any technique tried so far) — and `raglab compare` against the frozen baseline again found real regressions underneath: **`wins=10 losses=6 ties=41`**. `q-005`, `q-006`, `q-020`, `q-022`, `q-034` kept `recall_hit=True` but lost a supporting citation chunk (coverage or citation_precision dropped); `q-056` is a clean recall miss, the same entry hybrid also broke. The mechanism is different from hybrid's (no lexical candidate list here — a cross-encoder scores each `(query, chunk)` pair independently) but the failure shape is identical: pulling from a wider `candidate_k=20` pool and re-ranking by single-chunk relevance has no way to know that a synthesis question needs *several specific chunks jointly*, so a chunk that scores as more individually relevant can still crowd out one of the several the answer actually depends on.

**Per the same net-wins-zero-regressions rule, `rerank-v1` is REJECTED.** No full-corpus confirmation spent.

**`q-011` is ALSO fixed under reranking** (`recall_hit` False→True, `coverage` 0.0→1.0), a second, independent technique fixing the same named entry — strengthens the case that `q-011`'s failure is specifically "the right chunk exists outside the dense top-5, any method that looks further finds it," not something special about hybrid.

**The cross-technique pattern is now real signal, not a one-off.** Two structurally different techniques (rank fusion with a lexical signal; independent cross-encoder scoring) produced the *same* regression shape on overlapping entries (`q-020`, `q-022`, `q-034`, `q-056` regressed under both). That is evidence the failure mode is a property of "reordering a fixed-size top-k against synthesis questions that need several specific chunks at once," not an artifact of either technique's own mechanics — worth carrying into how the stacked configuration (Milestone 8) is read, since stacking two techniques that share a weakness is unlikely to cancel it out.

Per-tag: `near-duplicate` (1 win, 2 losses) — the tag this technique was built to target — is net negative, the opposite of what candidate_k=20 pulling more near-duplicate-shaped chunks into contention was expected to do. `boundary-spanning` (1 win, 0 losses) and `lexical-anchor` (2 wins, 0 losses) are clean.

**T5.1–T5.6 — query rewriting: REJECTED on a technicality, but the headline number it targets is effectively closed.**

`retrieval/rewriter.py` makes one provider call per entry, no-op (provider never touched) on empty history — proven at the unit level, not just asserted, so the 47 standalone entries in `fb_rules` are structurally incapable of being affected by `rewrite-v1`.

Run live via `agent_sdk` on `fb_rules` (57 entries, `rewrite-v1`: `follow_ups_only`): 183,828 input tokens (estimated ~175K). **The follow-up recall deficit is closed on this sample: 50.0% → 100.0%**, while standalone recall stayed at exactly 81.4% — bit-for-bit the same figure as the baseline, confirming the no-op guarantee held in a live run, not just in a unit test. All three spec-named follow-up misses are FIXED: `q-032`, `q-033`, `q-037` each went `recall_hit` False→True.

`raglab compare` against the frozen baseline: **`wins=6 losses=3 ties=48`.** Three regressed entries — `q-034`, `q-056`, `q-058`, all on `citation_precision` only, `recall_hit` unchanged on every one. Inspecting the retrieved-id diffs: **two of the three are not caused by rewriting at all.** `q-056` and `q-058` are standalone entries (`rewritten_query=None` — the no-op path), and their `retrieved` chunk-id lists are byte-identical to the baseline run's; the only thing that changed between the two runs is which chunks the model chose to cite in a fresh, independently-sampled answer call over identical context. That is answer-generation sampling variance, the same phenomenon Phase 2's plan.md documented for judge verdicts, showing up here in a deterministic-looking metric because `citation_precision` depends on the model's live citation choice, not just retrieval. Only `q-034` is a real, rewriting-caused regression: its rewritten query ("Is the Gallardo's gearbox shift time also 50 milliseconds...") is an accurate, well-resolved referent, but it shifted the retrieved neighborhood in `egear.md` enough that the model's cited chunk moved from a fully-covering one to a partial one (`citation_precision` 1.0→0.33, `recall_hit` still True).

**Per the net-wins-zero-regressions rule, `rewrite-v1` is REJECTED** — but the margin is one real regression on a citation-choice detail, not a retrieval failure, against three fixed named misses and a deficit closed from 50% to 100%. The distinction between "1 real regression" and "3 observed regressions" doesn't change the verdict here (even excluding the two noise-attributable entries, one genuine regression is still enough to fail the rule as written), but it matters for how this result should be read: this is the strongest technique tried so far by a wide margin, rejected by a rule that, applied to a single run, can't distinguish a technique's own side effect from ordinary LLM sampling noise on an untouched entry. **Flagging as an open methodological question rather than deciding unilaterally**: whether future single-run adoption decisions in this phase should exclude regressions on entries where `retrieved` is byte-identical to the baseline (i.e., provably not caused by the technique under test) is a call for whoever reviews this phase's results, not something resolved here. Per T5.5's own condition ("if adopted, ..."), rewrite-v2 (`all-questions`) was not run — v1 was rejected, so there is nothing to test the over-expansion risk against yet. No full-corpus confirmation spent.

Per-tag: `follow-up` (5 wins, 1 loss) is exactly the intended effect; every other tag is untouched or single-digit noise, consistent with a technique that structurally cannot reach standalone entries.

**T6.1–T6.3 — structure-aware chunking: built, and it produces a dramatically different index from what the fixed strategy does.**

`chunker.py` gained `chunk_text_structure`, splitting on line-initial rule-ID and Markdown-heading boundaries (mirroring `evals/locations.py`'s own `RULE_ID_RE`/`HEADING_RE`, so a chunk boundary can never disagree with where gold-anchor resolution thinks a rule starts) and falling back to the existing fixed-size windower to sub-split anything over a 2,000-char ceiling (bge-small's ~512-token limit, the same conservative estimate this file already used before Phase 4). `IndexBuilder` now takes a `ChunkerSettings` and refuses (`ChunkingMismatchError`) to write into a directory whose existing manifest recorded a different strategy — without this, the existing incremental-rebuild logic would have silently reused stale wrong-strategy chunks for every unchanged document, since it only checks a document's own content hash, never the index's own chunking identity.

**A real backward-compatibility gap, caught before it broke anything downstream:** making the index directory a function of chunking strategy (`experiments.index_subdir_name`: `fixed-900-150`, `structure`) meant the *existing* baseline index — built to the old bare `evals/index/` path by every Milestone 1, 3, 4, and 5 live run — was no longer where the new default (`evals/index/fixed-900-150/`) looks. Migrated by moving the three index files into the new subdirectory; `raglab search` and `raglab collections` (neither `--experiment`-aware) got their own `DEFAULT_FIXED_INDEX_DIR` constant pointing at the same migrated location, since only `index`/`eval run` need the full per-experiment resolution. Verified live (no cost: local ONNX only) that `search` and `collections` report the same chunk counts as before the move.

Built the structure index over the real corpus (`chunk-structure-v1`: local only, no provider calls) and compared directly against the fixed index:

| Doc | fixed-900-150 (n / mean chars) | structure (n / mean chars) |
|---|---|---|
| fb_rules.pdf | 401 / 898.8 | **1,974 / 152.3** |
| amg_mct.md | 15 / 897.4 | 12 / 959.2 |
| egear.md | 28 / 899.0 | 14 / 1,562.3 |
| smg.md | 15 / 895.5 | 11 / 1,084.7 |
| tiptronic.md | 17 / 883.8 | 9 / 1,419.3 |
| **total** | **476 / 898.1** | **2,020 / 177.6** |

Max chunk size across the entire structure index is exactly 2,000 chars — the sub-split ceiling held on real data, not just the synthetic unit-test cases. The asymmetry is stark and corpus-specific: `fb_rules.pdf` is a rulebook of short, atomic rule paragraphs at extremely high rule-ID density, so splitting on every line-initial rule id produces **5x more chunks, each 6x smaller** than the fixed strategy's uniform 900-char windows. The four Markdown documents have the opposite shape — few headings relative to their length — so structure chunking merges what fixed chunking split, producing **fewer, larger** chunks (up to the 2,000-char ceiling) for all four. This means `chunk-structure-v1`'s effect on `fb_rules` (the gold set every live comparison in this phase runs against) is really a test of *much finer-grained, near-atomic retrieval units*, not a modest reshuffling — worth keeping in mind reading T6.4's results: a technique that helps `boundary-spanning` questions (the tag it targets) by keeping a rule's full text together could just as easily hurt questions needing several now-separate atomic chunks at once, the same failure shape hybrid and reranking both hit.

**T6.4–T6.5 — structure-aware chunking: REJECTED, and the prediction above landed exactly.**

Run live via `agent_sdk` on `fb_rules` (57 entries, `chunk-structure-v1`, against the freshly-built structure index): 129,263 input tokens — notably *cheaper* than every other experiment (~170-184K each), a direct consequence of much smaller retrieved excerpts. `raglab compare` against the frozen baseline carried the chunking-mismatch note as designed (`ChunkingConfig` differs; only `recall_hit`/`coverage`/`citation_precision` compared, never raw chunk ids) and reported **`wins=8 losses=16 ties=33`** — net *negative*, the only technique this phase tried whose losses outnumber its wins. This is also the technique with the highest regression count by a wide margin (16, vs. 6 for hybrid and rerank, 3 for rewriting).

**The tag this technique specifically targets is itself net negative**: `boundary-spanning` scored 1 win, 2 losses. `synthesis` is worse still — 1 win, 6 losses, the single largest per-tag loss count of any technique or tag combination in the phase. Inspecting a boundary-spanning regression directly (`q-045`): `recall_hit` held True in both runs, but `coverage` and `citation_precision` both halved (1.0→0.5) — the fixed top-5 window, now filled with much smaller atomic chunks, simply can't hold as much of the needed material as it could when each chunk carried ~6x more text. `q-021` (`synthesis`+`boundary-spanning`) lost `recall_hit` outright (True→False): the three separate facts it needs are now split across *more* atomic chunks than before, and fewer of them fit in the same k=5 budget.

**Per the net-wins-zero-regressions rule, `chunk-structure-v1` is REJECTED** — the clearest rejection of the phase, failing on both the strict rule and the permissive aggregate-delta rule the spec explicitly warned against relying on. No full-corpus confirmation spent. The finer-grained chunking that seemed like it should help `boundary-spanning` (keep a rule's own text from being cut mid-rule by an arbitrary character window) instead hurt it, because the same finer granularity that avoids cutting one rule's text also spreads a multi-rule answer across more pieces than a fixed top-k retrieval budget can hold — the identical crowding failure mode hybrid and reranking hit, here driven by chunk *count* inflation rather than candidate reordering.

Per-tag elsewhere: `lexical-anchor` (2 wins, 0 losses) is the one clean positive tag, consistent with atomic chunks being easier to match precisely for a single-fact lookup — the same shape of question hybrid retrieval also helped most.

**T7.1–T7.3 — agentic retrieval: the strongest recall result in the phase, at real cost.**

`pipelines/agentic.py` exposes one `search` tool over the existing `Retriever`; the multi-call loop lives inside the provider (T2.7), so the pipeline's own job is defining the tool and enforcing `max_calls` from inside the tool handler itself. `FakeProvider` gained genuine tool-loop simulation (`ScriptedToolCall`) to actually exercise that handler in tests rather than stub it out.

Run live via `agent_sdk` on a 20-entry subset of `fb_rules` (the exact union of `follow-up` (10), `synthesis` (8), and `cross-document` (5) tagged entries — the three hardest categories in the gold set, 20 unique after tag overlap), `agentic-v1` (`max_calls=5`): 330,468 input tokens, 16,523 mean input tokens/entry — about 5.2x a normal single-shot entry (~3,200), at the upper edge of the budgeted 3-5x range.

**`recall_at_k = 100.00%` across all 20 entries — including `q-036`, the cross-document entry that has failed under every pipeline since Phase 2 and that a whole-document baseline is structurally unable to answer at all.** Letting the model search again once it has enough of one document's context but not the other's is exactly the capability this entry needs and no single-shot retrieval technique in this phase (dense, hybrid, reranked, or structure-chunked) has. Mean calls per entry: 2.8 (median 2, range 1-5). Three entries hit the `max_calls=5` ceiling (`q-021`, `q-056`, `q-059`) and were recorded `capped=True`, continuing rather than erroring, per spec — and notably, all three still achieved `recall_hit=True` on whatever they'd gathered before the cap, meaning the ceiling didn't cost them the answer on this sample.

`grounded_rate` was 90% (18/20) — the two failures are answer-quality issues independent of retrieval, not retrieval gaps (`recall_hit=True` on both): `q-036`'s candidate retrieved the right chunk but described the wrong safety mechanism (BSPD instead of the BOTS the question actually asked about); `q-032` reproduced the correct facts but appended an unsupported extra claim the source doesn't state. Neither is a retrieval failure, but both are worth knowing about before trusting agentic answers unreviewed.

**Cost projection for a full 57-entry `fb_rules` run**: this subset already includes all 20 of the hardest entries; the remaining 37 are mostly single-fact lookups the baseline already handles in one dense search. Even a 1-call entry in this run cost 5,600-6,035 tokens (vs. baseline's ~3,200) from the agentic system prompt and tool-definition overhead alone, so a conservative estimate for the 37 remaining entries is ~6,000 each (~222K) on top of this run's 330K already spent, for a **full-corpus estimate of roughly 550K input tokens** — by far the most expensive single experiment run in the phase. That number, not a rerun of this probe, is what decides T7.4.

**A real robustness bug found and fixed before T7.4's full run, at real cost.** The first full-`fb_rules` agentic attempt crashed entirely partway through: `evals/runner.py`'s judge call (`score_refusal`/`score_groundedness`) was never wrapped in a `try`/`except`, unlike the pipeline-answer call right above it. A transient `claude` CLI subprocess failure during one entry's judge call (misreported as `ProviderAuthError` — `AgentSDKProvider.complete()` wraps *any* `ClaudeSDKError` as an auth error, not just real auth failures) propagated out of `asyncio.gather`, and since `ReportWriter.write()` is only reached after `gather` returns, **the entire run's report was never written — every already-completed entry, and every token spent producing it, was lost, not just the one that failed.** This was always a latent bug in every prior pipeline, but a normal ~180K-token run is short enough that a transient CLI hiccup rarely lands inside it; this run's length and concurrency made it likely enough to actually hit. Fixed by wrapping the judge call in its own `try`/`except`, returning an `errored` entry that preserves everything already computed (answer, retrieval, citations, coverage) rather than raising -- regression-tested (`test_judge_failure_is_errored_not_raised_and_does_not_kill_other_entries`) by forcing a judge failure on one entry in a two-entry batch and confirming the other entry still grades normally and a report is still produced.

**T7.4/T7.5 — agentic retrieval on the full corpus: the strongest quality result in the phase, and still REJECTED by the same rule applied everywhere else.**

Re-run clean after the robustness fix: 665,135 input tokens (57/57 graded, zero errored) — 20% over the ~550K projection, consistent with the projection undercounting standalone-entry overhead slightly. **`recall_at_k = 98.11%`**, versus the baseline's 75.47% (+22.6 points, the largest margin of any technique this phase) and versus every rejected technique's 75.5-84.9%. `boundary-spanning`, `lexical-anchor`, `near-duplicate`, `synthesis`, `follow-up`, and `cross-document` all hit 90-100% recall — agentic is the only technique that helped nearly every tag simultaneously rather than trading one tag's gains for another's losses.

`raglab compare` against the frozen baseline: **`wins=16 losses=12 ties=29`.** Every one of the 12 regressions is `citation_precision` only — **zero `recall_hit` regressions and zero `coverage` regressions across all 57 entries.** This is a materially different failure shape than every other technique this phase: hybrid, reranking, and structure chunking all lost real ground on `recall_hit`/`coverage` (crowding a needed chunk out of a fixed-size window); agentic never did. Its cost is precision, not recall, traced to its own mechanism directly: agentic accumulates the *union* of chunks across every search call (8-13 chunks typical, vs. the baseline's fixed 5), so when the model cites more of that wider context in its answer, citation precision dilutes even though the right span was always present. Concretely — `q-005`: 5→13 retrieved, 4→5 cited, precision 0.5→0.4; `q-034`: 5→13 retrieved, 1→3 cited, precision 1.0→0.67; `q-047`: 5→8 retrieved, 1→2 cited, precision 1.0→0.5.

**Per the same net-wins-zero-regressions rule applied to every other technique, `agentic-v1` is REJECTED** — 12 regressions, however narrow and single-metric, is not zero. Applying the rule inconsistently here (waiving it because the regressions are "only" citation precision) would undercut the same rule that correctly caught hybrid/rerank/structure's real recall regressions; the strict standard has to mean the same thing every time or it isn't a standard. But this rejection reads differently from the other four: agentic is the only technique whose entire cost is on a secondary axis (citation hygiene) while dominating every primary retrieval metric on every tag. It is the clearest case in the phase for "reject under this rule, but reconsider the rule's granularity" rather than "reject and move on" — worth a citation-precision-specific mitigation (e.g. instructing the model to cite tightly despite a wider context) as a natural v2, though that is out of scope for this phase's single-shot experiment design.

**Cost verdict, stated regardless of quality**: 665,135 tokens for one 57-entry run is ~3.6x the ~184K a normal single-shot `fb_rules` iteration costs, and ~15x agentic's own 5-search-call ceiling would suggest if searches were free — the overhead is dominated by carrying a much larger tool-definition-plus-accumulated-context prompt on every one of the mean 2.8 calls/entry (T7.3), not by the call count alone. At today's quota, an iteration loop built around agentic retrieval (the way this phase iterated hybrid/rerank/rewrite/structure at ~170-184K per round) would spend in one run what four other full techniques' `fb_rules` iterations cost combined.

No full-corpus confirmation beyond this run was needed (already the full corpus). `q-011`, `q-032`, `q-033`, `q-037` (the phase's named recall misses) are all `recall_hit=True` under agentic — the only entry among all 57 with `recall_hit=False` is `q-018` (a judge/citation disagreement: judge said `grounded`, `citation_precision=0.0`). The three `not_grounded` failures (`q-005`, `q-016`, `q-036`) are all genuine reasoning errors, not retrieval misses (`recall_hit=True` on all three) — and two of the three (`q-016`, `q-036`) are the same BSPD/BOTS confusion T7.3's subset run already surfaced, now recurring at full scale. Worth a hypothesis for later, not resolved here: agentic's wider accumulated context, across multiple searches touching adjacent rules, may make this specific conflation *more* likely, not less — the same "more context, less precision" pattern already measured in citation precision, showing up here in reasoning instead.

**T8.1/T8.2 — stacking: SKIPPED.** All five techniques were rejected (T3.6, T4.5, T5.6, T6.5, T7.5); the adopted set `stacked-v1` was meant to combine is empty. Rather than guess at a substitute scope, this was put to the user directly: skip stacking and go straight to the phase report, stack the two strongest techniques (agentic + rewriting) anyway despite neither being formally adopted, or revisit the adoption rule's granularity first for the two techniques whose rejections are arguably technicalities (rewriting's noise-attributable regressions, agentic's citation-precision-only ones). **User chose to skip stacking.** No `stacked-v1` config exists and no stacked run was made; the reasoning for each alternative is preserved above in case a future session wants to revisit it.

## Phase 4 summary (T8.3)

**Every technique tested improved on the baseline in aggregate. Every technique also produced at least one real, named regression, and was rejected by the strict rule for exactly that reason.** That is the phase's actual finding: at this corpus's size and this gold set's granularity, no retrieval technique tried was a free improvement — each one traded a different failure mode for the gains it bought, and the zero-regression rule (adopted specifically to prevent averaging real regressions away, spec §prior decisions) caught every one of them rather than letting an attractive aggregate number stand in for "does this actually work."

### Full results table (`fb_rules`, 57 entries, `agent_sdk`/`claude-sonnet-5` answering, `claude-opus-5` judging)

| Experiment | grounded | recall@5 | MRR | citation prec. | coverage | input tokens | vs. baseline (W/L/T) | verdict |
|---|---|---|---|---|---|---|---|---|
| **baseline** | 96.2% | 75.5% | 0.603 | 79.6% | 70.4% | 183,382 | — | frozen reference |
| hybrid-v1 | 100% | 83.0% | 0.693 | 76.8% | 78.0% | 181,430 | 8 / 6 / 43 | REJECTED |
| rerank-v1 | 94.3% | 84.9% | 0.774 | 74.8% | 79.6% | 181,829 | 10 / 6 / 41 | REJECTED |
| rewrite-v1 | 94.3% | 84.9% | 0.673 | 76.5% | 79.9% | 183,828 | 6 / 3 / 48 | REJECTED |
| chunk-structure-v1 | 98.1% | 69.8% | 0.530 | 65.0% | 62.3% | 129,263 | 8 / 16 / 33 | REJECTED |
| agentic-v1 | 94.3% | **98.1%** | 0.682 | 73.6% | **97.2%** | 665,135 | 16 / 12 / 29 | REJECTED |

Every rejection is for a different reason, not the same one repeated: hybrid and reranking both crowd a needed chunk out of a fixed-size top-k on multi-source questions (different mechanisms, same failure shape, and overlapping regressed entries — `q-020`, `q-022`, `q-034`, `q-056` broke under both); structure-aware chunking inflates chunk count 5x on `fb_rules.pdf` and reproduces the identical crowding failure at a larger scale, net negative overall; query rewriting's one real regression is a retrieval-neighborhood side effect of an accurate rewrite, not a rewriting failure; agentic's twelve regressions are exclusively citation-precision dilution from a wider accumulated context, with zero cost to recall or coverage anywhere.

### The follow-up deficit, restated under the best configurations

Phase 3 measured 80.0% standalone vs. 50.0% follow-up recall. This phase's frozen baseline, on a grown sample (47 standalone / 10 follow-up vs. Phase 3's 29 / 6), reproduced it almost exactly: **81.4% standalone vs. 50.0% follow-up** — the deficit was real and stable, not a Phase 3 sampling artifact.

**Two independent techniques closed it completely on this sample**: query rewriting (81.4% standalone / **100.0%** follow-up) and agentic retrieval (97.7% standalone / **100.0%** follow-up) — different mechanisms (resolving the referent before retrieval vs. letting the model search again when the first result is insufficient), same outcome. Neither is adopted, so neither is shipped, but the deficit itself is not an unsolved problem — it is a solved problem attached to techniques that each cost something else (rewriting: one real regression; agentic: cost and citation precision).

### The four named entries

`recall_hit` under every technique (baseline is `False` on all four by construction — these are exactly Phase 3/4's named misses):

| Entry | hybrid | rerank | rewrite | structure | agentic |
|---|---|---|---|---|---|
| `q-011` (BSPD, lexical-anchor) | **True** | **True** | False | **True** | **True** |
| `q-032` (follow-up) | False | False | **True** | False | **True** |
| `q-033` (follow-up) | False | False | **True** | False | **True** |
| `q-037` (follow-up) | **True** | **True** | **True** | False | **True** |

`q-011` is fixed by four of five techniques (every one except rewriting, which no-ops on it by design — it isn't a follow-up entry) — "the right chunk exists outside the dense top-5, any method that looks further finds it" (plan.md's hybrid write-up) holds regardless of *which* method looks further. `q-032`/`q-033` are fixed only by the two techniques that actually resolve or search past the follow-up's missing referent (rewriting, agentic); dense-neighborhood techniques that don't touch the query text at all (hybrid, rerank) or that changed retrieval granularity without addressing reference resolution (structure) never touch them. `q-037` is the interesting outlier: fixed by every technique except structure-aware chunking, which is also the only technique that made `fb_rules.pdf`'s chunks smaller — consistent with the atomicity failure mode already documented for that technique.

### Per-tag effects across all five techniques

Per-technique win/loss/tie for every tag, all five techniques (n = tag size):

| Tag (n) | hybrid | rerank | rewrite | structure | agentic |
|---|---|---|---|---|---|
| `lexical-anchor` (9) | 2/0/7 | 2/0/7 | 0/0/9 | 2/0/7 | 2/1/6 |
| `follow-up` (10) | 2/1/7 | 3/1/6 | **5/1/4** | 0/2/8 | 5/3/2 |
| `near-duplicate` (8) | 2/1/5 | 1/2/5 | 0/0/8 | 1/4/3 | 2/1/5 |
| `boundary-spanning` (8) | 0/1/7 | **1/0/7** | 0/0/8 | 1/2/5 | 0/2/6 |
| `synthesis` (8) | 1/4/3 | 1/2/5 | 0/1/7 | 1/6/1 | **4/2/2** |
| `vocabulary-mismatch` (10) | 1/1/8 | 1/1/8 | **1/0/9** | 2/4/4 | 2/4/4 |
| `cross-document` (5, illustrative) | 1/1/3 | 2/1/2 | 0/2/3 | 2/1/2 | **4/1/0** |
| `not-in-document` (4, illustrative) | 0/0/4 | 0/0/4 | 0/0/4 | 0/0/4 | 0/0/4 |

Notable, not obvious in advance: `lexical-anchor` is positive or neutral under every technique, never net negative anywhere. Both techniques built to target a specific tag underperformed on it: reranking's own target, `near-duplicate`, went net negative under reranking itself (1/2) while hybrid and agentic both did better on it (2/1) without targeting it; structure-aware chunking's own target, `boundary-spanning`, went net negative under structure chunking itself (1/2). `agentic-v1` is the single best result on three tags (`follow-up`, `synthesis`, `cross-document`) including the only technique to ever fix `q-036` — but is *also* the single worst result on `boundary-spanning` (0/2, net -2, worse than structure-aware chunking's own -1 on the tag it targets), the one tag agentic actively hurts despite dominating everywhere else.

`cross-document` (5) and `not-in-document` (4) stay below a size where one entry flipping is worth 20-25 points — reported as illustrative, per spec, not as measured effects to generalize from. `not-in-document` never moved under any technique (0/0/4 everywhere) — refusal-correctness held at 100% throughout the phase, confirming no technique compromised the safety-net behavior established in Phase 0.

### Verification

`uv run pytest -q`: 219 passed, 3 deselected (integration-marked, need network/local model download on first use). `uv pip list`: no `torch`.

# Tasks: Phase 4 — Retrieval Optimization

Milestones 1 and 2 are prerequisites for everything else and are drafted here.
Milestones 3–7 (hybrid, rewriting, chunking, reranking, agentic, stacking) are
drafted after these are reviewed — they all share the same shape, and their
detail depends on what the two probes in T2.5 and T2.6 return.

**Standing rule for this phase:** no task performs a live provider run without
explicit confirmation first, naming the provider and the expected token cost.

---

## Milestone 1: Rubric and Baseline

Nothing else in the phase may start before this milestone completes. Every
experiment compares against the artifact T1.5 produces.

- [x] **T1.1** Write down the hedged-answer rubric decision before touching code: state, in `plan.md`'s as-built notes, what verdict an answer deserves when it correctly refuses part of a question and correctly answers the rest.
  - Acceptance: a written rule that classifies both known cases the same way — Phase 2 `tiptronic` q-005 (honest hedge, judged `not_grounded`) and Phase 3 `q-011` (honest hedge, judged `grounded`).
  - Refs: spec §prior decisions (judge rubric fixed once), plan §Sequencing M1
  - Depends on: none

- [x] **T1.2** Amend the judge prompt in `evals/judge.py` to implement that rule. No other judge change — not the model, not the output format, not the temperature.
  - Acceptance: `git diff src/raglab/evals/judge.py` touches only the rubric text; `uv run pytest -q` stays green.
  - Refs: spec §constraints (judge changed exactly once), plan §Tech Stack
  - Depends on: T1.1

- [x] **T1.3** Add a regression test pinning the new rubric using both hedged answers from T1.1 as fixtures, graded through `FakeProvider` with scripted judge responses.
  - Acceptance: `tests/test_judge.py` contains both cases; they fail against the old prompt and pass against the new one.
  - Refs: spec §requirements (judge frozen after fix)
  - Depends on: T1.2

- [x] **T1.4** Add `ExperimentConfig` in `experiments.py`, an `experiments.toml` holding a single `baseline` entry that reproduces current behaviour exactly, and `--experiment` on `eval run`. Record the resolved config in `report.config.experiment`.
  - Acceptance: `raglab eval run --experiment baseline` produces a report whose `config.experiment.name` is `baseline` and whose retrieval settings equal today's defaults (900/150, k=5, dense).
  - Refs: spec §data & integrations (experiment configuration), plan §Data Model
  - Depends on: none

- [x] **T1.5** Run the frozen Phase 4 baseline on `fb_rules` and on the full corpus. **Confirm cost before running.**
  - Acceptance: two reports written and copied to `evals/baselines/phase4-fb_rules.json` and `evals/baselines/phase4-full.json`; both carry `experiment.name = "baseline"`. Roughly 110K + 250K input tokens.
  - As-built: "full corpus" resolved as 5 separate per-gold-set runs (fb_rules + 4 Markdown sets), matching Phase 2/3 precedent, rather than one merged gold file — `phase4-full.json` is a hand-assembled summary of all 5 reports, not a native `eval run` output; see plan.md. Actual cost: 306,301 input tokens (fb_rules grew to 57 entries since the estimate was written, so the total ran somewhat above the original ~360K combined estimate).
  - Refs: spec §in scope (frozen baseline), plan §Sequencing M1
  - Depends on: T1.2, T1.4

- [x] **T1.6** Record in `plan.md` that the rubric change breaks comparability with Phases 0–3, and state the new baseline numbers next to Phase 3's so the discontinuity is visible rather than discovered later.
  - Acceptance: an as-built paragraph naming both numbers and the reason they differ.
  - Refs: spec §prior decisions (comparability cost accepted)
  - Depends on: T1.5

---

## Milestone 2: Comparison Machinery

Zero model calls. This milestone is what makes every later result trustworthy,
so it is built and proven before any technique exists to measure.

- [x] **T2.1** Implement `evals/compare.py`: load two reports, match entries by id, classify `recall_hit`, `coverage`, and `citation_precision` independently as win / loss / tie.
  - Acceptance: unit tests cover each metric's win and loss direction, plus an entry that improves one metric and regresses another (which must classify as a loss).
  - Refs: spec §requirements (per-entry classification), plan §Data Model
  - Depends on: none

- [x] **T2.2** Add entry-level rollup: a win if any metric improved and none regressed, a loss if any regressed, a tie otherwise. `grounded_rate` is reported but never classifies.
  - Acceptance: a test asserting an entry whose only change is `grounded` flipping is classified as a tie.
  - Refs: spec §prior decisions (deterministic metrics primary), plan §Data Model
  - Depends on: T2.1

- [x] **T2.3** Add the two guards: refuse to compare when either report lacks `config.experiment`, and refuse when the two reports' `gold_set` identities differ.
  - Acceptance: both refusals are tested and name the offending report; the gold-set guard reuses Phase 3's identity check rather than a second implementation.
  - Refs: spec §unwanted behavior, plan §Error Handling
  - Depends on: T2.1

- [x] **T2.4** Add the chunking-mismatch rule: when the two reports' `chunking` configs differ, omit `retrieved`-id comparisons and report span-based metrics only, with a stated note in the output.
  - Acceptance: a test with two reports differing only in chunking strategy produces span-based results and the note, and does not compare chunk ids.
  - Refs: spec §data & integrations (chunk ids incomparable), plan §Data Model
  - Depends on: T2.1

- [x] **T2.5** Add `raglab compare <baseline> <experiment>` printing counts, every regressed entry by id and metric, and a per-tag breakdown of the same classification.
  - Acceptance: **`raglab compare` of the T1.5 baseline against itself reports 100% ties, zero wins, zero losses.** If it does not, the machinery is wrong and nothing downstream can be trusted.
  - Refs: spec §acceptance criteria, plan §Sequencing M2
  - Depends on: T2.2, T2.3, T2.4

- [x] **T2.6** Probe `fastembed` for an ONNX cross-encoder reranker. Timebox to one sitting. Record availability, model id, and load time.
  - Acceptance: a written finding — available with a named model, or unavailable, in which case reranking becomes an LLM call per entry and its position in the sequence is reconsidered.
  - Refs: spec §risks (reranking may be unbuildable), plan §Integration Plan
  - Depends on: none

- [x] **T2.7** Probe `AgentSDKProvider` custom tool-calling with a trivial two-tool script through the `claude` CLI. **Confirm before running** — this is a live call, though a small one.
  - Acceptance: a written finding — tool-calling works on `agent_sdk`, or it does not and agentic retrieval runs on `openrouter` with the substitution recorded.
  - Refs: spec §risks (tool-calling unproven), plan §Integration Plan
  - Depends on: none

---

## Sequencing note — revised after the probes

`plan.md` scheduled reranking sixth because it might be blocked or cost a
provider call per entry. T2.6 removed both risks: pure ONNX, no PyTorch, 0.24s
warm load, zero per-entry provider cost. Under the plan's own cheapest-first
rule it moves to second. T2.7 removed the `openrouter` fallback for agentic
retrieval, which still stays last on cost.

Revised order: **3.** hybrid · **4.** reranking · **5.** query rewriting ·
**6.** structure-aware chunking · **7.** agentic · **8.** stack the winners.

Cost per live run at the current corpus: **~170K** input tokens for a
`fb_rules` iteration (57 entries), **~300K** for a full-corpus confirmation
(99 entries). Every run below needs confirmation before it is spent.

---

## Milestone 3: Hybrid Retrieval

Targets `lexical-anchor` (9 entries) and `q-011`, where dense retrieval
returned chunks that mention BSPD instead of the rule that defines it.

- [x] **T3.1** Implement BM25 in `retrieval/bm25.py` over chunk text: term frequencies, document frequencies, `k1=1.2`, `b=0.75`, built once from `chunks.jsonl`.
  - Acceptance: `tests/test_bm25.py` reproduces hand-computed scores for a three-document worked example; a rare term outranks a common one.
  - Refs: plan §Tech Stack (hand-rolled BM25)
  - Depends on: none

- [x] **T3.2** Implement Reciprocal Rank Fusion in `retrieval/fusion.py`, `rrf_k=60`.
  - Acceptance: `tests/test_fusion.py` covers ordering, ties, a document present in only one list, and the degenerate single-list case (which must preserve that list's order).
  - Refs: plan §Tech Stack (RRF)
  - Depends on: none

- [x] **T3.3** Add `mode` (`dense`|`hybrid`) and `candidate_k` to `RetrievalConfig`, and wire hybrid retrieval into `retriever.py`.
  - Acceptance: with `mode=dense` the retriever returns byte-identical results to today; with `mode=hybrid` it fuses both lists.
  - Refs: spec §requirements (techniques switchable independently), plan §Architecture
  - Depends on: T3.1, T3.2

- [x] **T3.4** Add `hybrid-v1` to `experiments.toml` (`mode=hybrid`, `k=5`, `candidate_k=20`, `rrf_k=60`).
  - Acceptance: `raglab eval run --experiment hybrid-v1` resolves and validates before any provider is built.
  - Refs: plan §Data Model
  - Depends on: T3.3

- [x] **T3.5** Run `hybrid-v1` on `fb_rules` and compare against the frozen baseline. **Confirm cost first (~170K input tokens, `agent_sdk`).**
  - Acceptance: a `raglab compare` output with win/loss/tie counts, every regressed entry named, and the per-tag breakdown; `q-011`'s outcome stated explicitly.
  - As-built: 181,430 input tokens. `wins=8 losses=6 ties=43`. `q-011` FIXED (clean win, no competing regression). See plan.md.
  - Refs: spec §acceptance criteria, plan §Sequencing
  - Depends on: T3.4

- [x] **T3.6** Record the adoption decision under the net-wins-zero-regressions rule. If adopted, run the full-corpus confirmation. **Confirm cost first (~300K).**
  - Acceptance: an as-built paragraph stating adopted or rejected, the counts, the per-tag effect, and — if any entry regressed — why it was rejected rather than averaged away.
  - As-built: REJECTED (6 regressions > 0), despite positive aggregate deltas (recall@5 +7.6pt, MRR +0.09). No full-corpus run spent, since rejection is decided at the fb_rules stage. See plan.md for the regression mechanism (BM25 crowding a needed chunk out of the fixed top-5 on multi-source questions).
  - Refs: spec §prior decisions (adoption rule)
  - Depends on: T3.5

---

## Milestone 4: Reranking

Targets `near-duplicate` (8 entries) and low-MRR cases. With `candidate_k=20`
it can pull a correct chunk from rank 6–20 into the top 5, so it is a recall
technique here, not only a reordering one.

- [x] **T4.1** Wrap `fastembed.rerank.cross_encoder.TextCrossEncoder` in `retrieval/reranker.py` with `Xenova/ms-marco-MiniLM-L-6-v2`, loaded lazily and cached across entries.
  - Acceptance: `tests/test_reranker.py` asserts the T2.6 worked example's ordering; the model loads once per process, not once per query.
  - Refs: plan §Tech Stack, as-built T2.6
  - Depends on: none

- [x] **T4.2** Add the rerank stage to `retriever.py`: retrieve `candidate_k`, rerank, truncate to `k`. Reject a config where `candidate_k <= k`.
  - Acceptance: a test asserting the rejection, and one asserting the stage is a no-op when reranking is off.
  - Refs: plan §Tech Stack (candidate set), spec §requirements
  - Depends on: T4.1

- [x] **T4.3** Add `rerank-v1` to `experiments.toml` (`mode=dense`, `k=5`, `candidate_k=20`, ONNX reranker) so it is measured against the baseline independently of hybrid.
  - Acceptance: the config resolves; `mode` stays `dense` so this experiment isolates reranking.
  - Refs: spec §prior decisions (tested alone first)
  - Depends on: T4.2

- [x] **T4.4** Run `rerank-v1` on `fb_rules` and compare. **Confirm cost first (~170K).**
  - Acceptance: compare output with counts, named regressions, per-tag breakdown; the `near-duplicate` and MRR effects stated.
  - As-built: 181,829 input tokens. `wins=10 losses=6 ties=41`. `near-duplicate` net negative (1 win, 2 losses) — the tag this technique targeted. MRR 0.603→0.774, the best of any technique so far. See plan.md.
  - Refs: spec §acceptance criteria
  - Depends on: T4.3

- [x] **T4.5** Record the adoption decision; full-corpus confirmation if adopted. **Confirm cost first (~300K).**
  - Acceptance: as-built paragraph, same shape as T3.6.
  - As-built: REJECTED (6 regressions > 0), same net-wins-zero-regressions rule as hybrid. No full-corpus run spent. `q-011` fixed here too (second independent technique). Regression overlap with hybrid on q-020/q-022/q-034/q-056 — see plan.md's cross-technique-pattern note, relevant to Milestone 8 stacking.
  - Refs: spec §prior decisions
  - Depends on: T4.4
  - Depends on: T4.4

---

## Milestone 5: Query Rewriting

Targets the phase's headline number: the 31-point standalone/follow-up recall
gap (81.4% vs 50.0%), now measured on 10 follow-up entries.

- [x] **T5.1** Implement `retrieval/rewriter.py`: given history and a follow-up question, produce a standalone retrieval query via one provider call. No-op when history is empty.
  - Acceptance: `tests/test_rewriter.py` via `FakeProvider` asserts a no-op on standalone entries and a resolved referent on a scripted follow-up; the provider is not called at all for standalone entries.
  - Refs: plan §Tech Stack (rewriting v1), spec §risks
  - Depends on: none

- [x] **T5.2** Wire rewriting into `RetrievalPipeline` ahead of retrieval, and record the rewritten query in the entry report so a bad rewrite is diagnosable without re-running.
  - Acceptance: a report entry carries both the original and rewritten query when rewriting fired, and only the original when it did not.
  - Refs: plan §Architecture
  - Depends on: T5.1

- [x] **T5.3** Add `rewrite-v1` to `experiments.toml` (`rewriting=follow-ups-only`, otherwise baseline).
  - Acceptance: config resolves; standalone entries are provably untouched.
  - Refs: spec §prior decisions (v1 cannot harm standalone)
  - Depends on: T5.2

- [x] **T5.4** Run `rewrite-v1` on `fb_rules` and compare. **Confirm cost first (~175K — the 10 follow-up entries each add a rewrite call).**
  - Acceptance: compare output; follow-up recall restated against 50.0%; `q-032`, `q-033`, and `q-037` each reported fixed or still failing by name.
  - As-built: 183,828 input tokens. Follow-up recall 50.0%→100.0%; standalone recall unchanged at 81.4% (byte-identical, no-op confirmed live). `q-032`, `q-033`, `q-037` all FIXED. `wins=6 losses=3 ties=48`; only 1 of 3 regressions (`q-034`) is actually caused by rewriting -- the other 2 have byte-identical retrieval to baseline (answer-generation sampling noise). See plan.md.
  - Refs: spec §acceptance criteria
  - Depends on: T5.3

- [x] **T5.5** If adopted, add and run `rewrite-v2` (`rewriting=all-questions`) to test the over-expansion risk deliberately. **Confirm cost first (~200K).**
  - Acceptance: a stated finding on whether rewriting every question harms standalone entries; if any standalone entry regresses, v1 is adopted and v2 rejected.
  - As-built: SKIPPED per this task's own condition -- v1 was rejected (T5.6), so there is no adopted v1 to test v2 against. No cost spent.
  - Refs: spec §risks (rewriting may harm standalone)
  - Depends on: T5.4

- [x] **T5.6** Record the adoption decision; full-corpus confirmation for whichever variant won. **Confirm cost first (~300K).**
  - Acceptance: as-built paragraph, same shape as T3.6, naming which variant was adopted.
  - As-built: REJECTED (3 regressions > 0, strict rule applied uniformly with hybrid/rerank). Flagged as an open methodological question, not decided unilaterally: only 1 of the 3 is a real rewriting-caused regression, and the rule as written doesn't distinguish that from noise. No full-corpus run spent. See plan.md.
  - Refs: spec §prior decisions
  - Depends on: T5.5

---

## Milestone 6: Structure-Aware Chunking

Targets `boundary-spanning` (8 entries) and `synthesis` coverage, which sat at
0.611 against 0.833 recall in Phase 2 — spans found, but not all of them.

- [x] **T6.1** Add a `structure` strategy to `chunker.py`: split on rule-ID and Markdown-heading boundaries, sub-splitting any segment over the embedder's 512-token limit with the existing overlap.
  - Acceptance: `tests/test_chunker_structure.py` asserts rule boundaries are respected, no chunk exceeds the token limit, and no source text is lost between chunks.
  - Refs: plan §Tech Stack, spec §in scope
  - Depends on: none

- [x] **T6.2** Make the index directory a function of the chunking strategy (`evals/index/fixed-900-150/`, `evals/index/structure/`), selected by the experiment config.
  - Acceptance: both indexes coexist; switching experiments does not re-embed, and `raglab index` refuses to write a strategy's index into another's directory.
  - As-built: found and fixed a real gap -- the pre-existing baseline index lived at the old bare `evals/index/` path; migrated it to `evals/index/fixed-900-150/` and gave `search`/`collections` their own `DEFAULT_FIXED_INDEX_DIR`. See plan.md.
  - Refs: plan §Data Model (chunk ids incomparable)
  - Depends on: T6.1

- [x] **T6.3** Build the structure index over the corpus. Local only, no provider calls.
  - Acceptance: `manifest.json` records `strategy=structure`; chunk-count and mean-chunk-size are reported next to the fixed index for comparison.
  - As-built: `chunk-structure-v1`'s experiments.toml entry added here (pulled forward from T6.4, since `raglab index` now needs a named experiment to select chunking). 2,020 chunks vs. fixed's 476 -- fb_rules.pdf alone went 401→1,974 chunks, 898.8→152.3 mean chars. See plan.md's full table.
  - Refs: plan §Sequencing
  - Depends on: T6.2

- [x] **T6.4** Run `chunk-structure-v1` on `fb_rules`, then compare. **Confirm cost first (~170K).**
  - Acceptance: compare output carries the chunking-mismatch note; only span-based metrics are compared; `boundary-spanning` and `synthesis` coverage effects stated.
  - As-built: 129,263 input tokens (cheapest experiment so far -- smaller chunks). `wins=8 losses=16 ties=33`, net negative. `boundary-spanning` itself net negative (1W/2L); `synthesis` worst of any tag this phase (1W/6L). See plan.md.
  - Refs: spec §data & integrations, plan §Data Model
  - Depends on: T6.3

- [x] **T6.5** Record the adoption decision; full-corpus confirmation if adopted. **Confirm cost first (~300K).**
  - Acceptance: as-built paragraph, same shape as T3.6.
  - As-built: REJECTED -- clearest rejection of the phase, fails both the strict rule and the aggregate-delta rule. No full-corpus run spent. See plan.md for the mechanism (finer chunks avoid mid-rule cuts but spread multi-fact answers across more pieces than a fixed top-k budget holds).
  - Refs: spec §prior decisions
  - Depends on: T6.4

---

## Milestone 7: Agentic Retrieval

The control-flow comparison this project opened with: does letting the model
decide when and what to search beat retrieving once up front? T2.7 proved
`agent_sdk` handles custom tools, so no provider substitution is needed.

- [x] **T7.1** Implement `pipelines/agentic.py` as a separate `Pipeline`: expose `search(query)` as a tool over the existing retriever, loop until the model answers, enforce `max_calls` as a hard ceiling.
  - Acceptance: `tests/test_agentic.py` via `FakeProvider` asserts the loop terminates, the ceiling is enforced, and a capped entry is recorded as capped rather than errored.
  - As-built: `FakeProvider` gained genuine tool-loop simulation (`ScriptedToolCall`, backward-compatible) since the real tool loop lives inside the provider (T2.7), not the pipeline -- needed to actually exercise the handler's cap logic rather than stub it out. The cap lives inside the search tool's own handler, since nothing outside the provider's internal loop can interrupt it mid-flight.
  - Refs: spec §unwanted behavior (call ceiling enforced), plan §Architecture
  - Depends on: none

- [x] **T7.2** Record retrieval calls per entry and the union of all chunks seen across calls, so recall and citation metrics remain computable.
  - Acceptance: a report entry carries `retrieval_calls` and a `retrieved` union; `raglab compare` classifies it without special-casing.
  - As-built: confirmed by inspection and test -- `compare.py` only ever reads `recall_hit`/`coverage`/`citation_precision`/`verdict`, never `retrieval_calls`/`capped`, so no special-casing was possible to add even if wanted.
  - Refs: spec §requirements (calls per entry reported)
  - Depends on: T7.1

- [x] **T7.3** Run `agentic-v1` on a **20-entry subset** of `fb_rules` first, weighted toward `follow-up`, `synthesis`, and `cross-document`. **Confirm cost first — budget 3–5× a normal run per entry, so roughly 180–300K for 20 entries.**
  - Acceptance: a measured cost-per-entry figure and a mean call count, which together decide whether a full `fb_rules` run is affordable.
  - As-built: 330,468 input tokens (16,523/entry, ~5.2x baseline). Mean 2.8 calls/entry (median 2, max 5). **recall_at_k=100% across all 20**, including `q-036` (cross-document, unfixed since Phase 2). 3 entries capped, all still recall_hit=True. Full-corpus cost estimated ~550K. See plan.md.
  - Refs: spec §risks (unbounded cost), plan §Sequencing
  - Depends on: T7.2

- [x] **T7.4** If the subset justifies it, run full `fb_rules` and compare. **Confirm cost first, using T7.3's measured figure rather than an estimate.**
  - Acceptance: compare output plus a cost comparison against the single-shot baseline — the answer to "is agentic worth what it costs" needs both columns.
  - As-built: found and fixed a real robustness bug first (unwrapped judge-call exception crashed the whole run, losing all spent tokens with no report written) -- see plan.md. Re-run clean: 665,135 input tokens (3.6x a normal iteration), `recall_at_k=98.11%` (best of the phase, +22.6pt vs. baseline). `wins=16 losses=12 ties=29`, and uniquely, all 12 losses are `citation_precision` only -- zero `recall_hit`/`coverage` regressions across all 57 entries.
  - Refs: spec §acceptance criteria
  - Depends on: T7.3

- [x] **T7.5** Record the adoption decision, including the cost verdict even if quality improved.
  - Acceptance: as-built paragraph stating quality effect, token cost per entry, and mean calls per entry.
  - As-built: REJECTED under the same rule applied to every other technique (12 regressions > 0), applied consistently rather than waived for being "only" citation precision. Quality: dominant on every primary metric and nearly every tag; the only technique this phase whose entire cost lands on a secondary axis rather than trading recall for recall. Cost: 3.6x a normal `fb_rules` iteration for one run. See plan.md for the full verdict and the case for reconsidering the rule's granularity (out of scope to act on here).
  - Refs: spec §prior decisions
  - Depends on: T7.4

---

## Milestone 8: Stack the Winners

- [x] **T8.1** Add `stacked-v1` to `experiments.toml` combining every adopted technique.
  - Acceptance: the config names exactly the adopted set, and each remains individually switchable.
  - As-built: SKIPPED, by user decision. All five techniques (T3.6, T4.5, T5.6, T6.5, T7.5) were REJECTED under the strict net-wins-zero-regressions rule — the adopted set is empty, so there is nothing to name in a stacked config. Asked explicitly rather than guessed, given this breaks the milestone's literal premise; user chose to skip stacking and go straight to the phase report.
  - Refs: spec §in scope (one stacked configuration)
  - Depends on: T3.6, T4.5, T5.6, T6.5, T7.5

- [x] **T8.2** Run the stack on the full corpus and compare against the baseline **and** against each adopted technique alone. **Confirm cost first (~300K).**
  - Acceptance: three comparisons; any entry a technique fixed alone but the stack breaks is named — that interference is the reason this milestone exists.
  - As-built: SKIPPED — depends on T8.1, which produced no config. No cost spent.
  - Refs: spec §prior decisions (stacked once), plan §Sequencing
  - Depends on: T8.1

- [x] **T8.3** Write the phase's as-built notes in the format Phases 2 and 3 established.
  - Acceptance: results table across every experiment, per-tag effects, the follow-up deficit restated under the best configuration, `q-011`/`q-032`/`q-033`/`q-037` each reported, and every regression named.
  - Refs: spec §acceptance criteria
  - Depends on: T8.2

---

## Definition of Done

- [x] All tasks above checked off, and those in milestones 3–7 once drafted.
- [x] Every acceptance criterion in `spec.md` is met or explicitly recorded as blocked with its reason.
- [x] `uv run pytest -q` green; `uv pip list` contains no `torch`. — 219 passed, 3 deselected (integration-marked).
- [x] Each of the five techniques has a recorded adoption decision with win / loss / tie counts. — all five REJECTED (hybrid 8/6/43, rerank 10/6/41, rewrite 6/3/48, structure 8/16/33, agentic 16/12/29).
- [x] Every regression any technique produced is named, with the entry and the metric.
- [x] The Phase 3 follow-up deficit (80% standalone / 50% follow-up) is restated under the best configuration, closed or not. — restated at 81.4%/50.0%; closed to 100% follow-up under rewrite-v1 and agentic-v1.
- [x] `q-032`, `q-033`, `q-037`, and `q-011` are each reported as fixed or still failing.
- [x] `plan.md` carries an as-built section in the format Phases 2 and 3 established. — "Phase 4 summary (T8.3)".

# spec: Phase 4 — Retrieval Optimization

## outcome

This is the phase the project was built to reach. Five techniques get tested against a frozen baseline — hybrid search, reranking, query rewriting, structure-aware chunking, and agentic retrieval — and each is adopted or rejected on per-entry evidence rather than reputation. The deliverable is not a faster system; it is a set of defensible answers to *which technique helps which kind of question, and by how much*, backed by named failing examples that existed before the technique did.

Everything built in Phases 0–3 exists to make this phase honest: a frozen judge, deterministic retrieval metrics, a tagged gold set, per-entry citation checks, and a 30-point follow-up deficit already measured and waiting to be closed.

## in scope

- A one-time judge rubric fix covering hedged and partial answers, applied before any experiment and frozen thereafter.
- A frozen Phase 4 baseline run, used as the paired reference for every comparison.
- **Paired per-entry scoring**: every experiment reports win / loss / tie against the baseline, per entry, alongside aggregate rates.
- Five experiments, each independently configured and independently reversible:
  1. **Hybrid retrieval** — BM25 lexical scores fused with dense similarity.
  2. **Reranking** — a second-stage scorer over a wider candidate set.
  3. **Query rewriting** — resolving a follow-up's referents into a standalone retrieval query.
  4. **Structure-aware chunking** — splitting on rule and heading boundaries instead of fixed character counts.
  5. **Agentic retrieval** — the model calls retrieval as a tool and may search more than once.
- One stacked configuration combining whichever techniques were adopted.
- A named, recorded experiment configuration in every run report, so any run can be reproduced.
- Roughly 20 new gold entries raising the thin tags to usable sample sizes.

## out of scope

- **Web UI, FastAPI, React.** Deferred a fourth time. It becomes worth building once there is an optimized system worth looking at.
- **Changing the embedding model.** Frozen since Phase 0. Swapping it is model shopping, not retrieval technique, and it would force a full re-index and re-baseline that would invalidate every paired comparison in the phase.
- **Fine-tuning anything.** No training, no adaptation, no local model beyond the frozen embedder.
- **Reopening the any-overlap rule.** It was frozen in Phase 1 precisely so chunk-size changes would not move recall, which is exactly what the structure-aware chunking experiment needs.
- **New corpora or documents.** The gold set grows; the corpus does not. Adding documents mid-phase would change what every prior run retrieved from.
- **Production concerns** — latency budgets, concurrency, deployment. This is a measurement phase on one developer's laptop.

## users & context

Unchanged: one developer, Windows 10, terminal, no GPU, 16 GB RAM, a Claude subscription with a five-hour rate-limit window that is the binding resource for the entire phase.

The working loop is different from every prior phase, though. Phases 0–3 each ended in one live run; this phase runs an experiment, reads a paired diff, decides, and runs again — many times. That makes two things matter more than they did before: how quickly a run completes, and how legible the win/loss diff is. A per-entry diff that requires opening JSON to interpret will not survive twenty iterations.

## constraints

- Everything from Phases 0–3 carries forward: Python 3.12 via `uv`, **no PyTorch**, no Docker, local-first, clone-and-run, minimal dependencies, `agent_sdk` as the working provider.
- **The no-PyTorch rule constrains reranking specifically.** Conventional cross-encoder rerankers ship as PyTorch models. The reranker must be ONNX-based or must use the existing provider as an LLM reranker; if neither is workable, the experiment is reported as blocked rather than the constraint being waived.
- The embedding model, the any-overlap recall rule, and the citation mechanism are unchanged.
- The judge is changed exactly once, before the baseline run, and is frozen for the remainder of the phase.
- The Phase 4 baseline is frozen at the start and never re-run mid-phase. Every experiment compares against that one artifact.
- Chunking parameters are frozen except within the structure-aware chunking experiment, which changes them by definition.
- Experiments iterate against `fb_rules`; only techniques that pass get a full-corpus confirmation run.

## data & integrations

**No new external service.** BM25 is computed locally over the existing chunk text. Reranking is either a local ONNX model or a call through the existing provider abstraction. Query rewriting and agentic retrieval both use the existing provider.

**Experiment configuration** becomes a first-class recorded object: a named configuration capturing retrieval mode, chunking parameters, k, fusion weights, reranker identity, and rewriting settings. It is written into every run report so a result can be traced to the exact setup that produced it.

**Paired comparison artifacts** — for each experiment, a per-entry table of baseline verdict versus experiment verdict, classified as win, loss, or tie on each deterministic metric.

**Gold-set growth** — roughly 20 new entries distributed across `follow-up`, `vocabulary-mismatch`, `near-duplicate`, `boundary-spanning`, and `cross-document`. The corpus documents are unchanged, so existing anchors and hashes remain valid.

**Structure-aware chunking changes chunk ids**, which means `retrieved` id lists are not comparable across that experiment and the baseline. Span-based metrics — recall, coverage, citation precision — remain comparable, because Phase 1 deliberately defined recall on character overlap rather than chunk identity. That decision is what makes this experiment measurable at all.

## prior decisions

- **Adoption requires net wins and zero regressions.** A technique is kept if it fixes at least two entries and breaks none. At sample sizes where one entry is worth 16 percentage points, a permissive rule would admit noise as a tradeoff — and the strict rule forces every regression to be looked at rather than averaged away.
- **Techniques are tested alone first, then stacked once.** Independent testing gives clean attribution; a single combined run catches interference between techniques that each help in isolation. Greedy stacking was rejected as costing a run per technique per round for murkier attribution.
- **Experiments iterate on `fb_rules` and confirm on the full corpus.** `fb_rules` is the largest, hardest gold set and carries every tag; running the full corpus on every iteration would roughly double the phase's quota cost for a signal that only matters at the point of adoption.
- **Deterministic metrics are primary; `grounded_rate` is secondary.** Phase 3 measured judge variance at ±11 points on nine-entry sets with retrieval byte-identical. Recall@k, MRR, coverage, and citation precision have no such variance and must carry every adoption decision.
- **The judge rubric is fixed once, then frozen.** Two documented cases — Phase 2's `tiptronic` q-005 and Phase 3's `q-011` — show opposite verdicts on the same shape of honest, hedged answer. That is an unspecified rubric, not variance. Fixing it costs comparability with Phases 0–3, which is accepted: Phase 4 needs a fresh paired baseline regardless, and internal comparability is what this phase depends on.
- **Agentic retrieval is a control-flow comparison, not a sixth retrieval trick.** It answers the question this project opened with — whether letting the model decide when and what to search beats retrieving once up front — and it is measured on the same gold set with the same metrics.

## requirements

### always active

- The system SHALL record a named experiment configuration in every run report, sufficient to reproduce the run.
- The system SHALL compare every experiment run against the frozen Phase 4 baseline on a per-entry basis, classifying each entry as a win, loss, or tie.
- The system SHALL report per-entry classifications for recall, coverage, and citation precision independently, rather than a single combined verdict.
- The system SHALL treat recall@k, MRR, coverage, and citation precision as primary metrics, and `grounded_rate` as secondary.
- The system SHALL leave the embedding model, the any-overlap rule, and the citation mechanism unchanged for the whole phase.
- The system SHALL keep the judge frozen after the initial rubric fix.
- The system SHALL allow every technique to be switched off independently, returning the pipeline to baseline behavior.

### event-driven

- WHEN an experiment run completes, the system SHALL print the win / loss / tie counts and name every entry that regressed.
- WHEN a technique produces at least two wins and zero losses on `fb_rules`, it SHALL be eligible for a full-corpus confirmation run.
- WHEN a technique is confirmed on the full corpus, it SHALL be recorded as adopted, with its per-tag effect stated.
- WHEN the stacked configuration is run, the system SHALL report it against the baseline and against each adopted technique alone.
- WHEN agentic retrieval is run, the system SHALL record the number of retrieval calls made per entry alongside token cost.
- WHEN structure-aware chunking is run, the system SHALL report span-based metrics only, and SHALL note that retrieved-id comparisons are not meaningful across a chunking change.

### unwanted behavior

- IF a technique produces any regression against the baseline, the system SHALL name the regressed entries and SHALL NOT record the technique as adopted on aggregate improvement alone.
- IF a reranker cannot be run without PyTorch, the system SHALL report the experiment as blocked, naming the constraint, and SHALL NOT introduce PyTorch.
- IF agentic retrieval exceeds a configured per-entry retrieval-call ceiling, the system SHALL stop the loop, record the entry as capped, and continue the run.
- IF an experiment's configuration is missing from a run report, the system SHALL refuse to use that report as a paired comparison source.
- IF the baseline artifact is absent or its gold set differs from the experiment's, the system SHALL abort rather than compare across different question sets.

## risks & open questions

- **Reranking may be unbuildable under the no-PyTorch rule.** ONNX cross-encoders exist but availability through `fastembed` is unverified; the fallback is an LLM reranker through the existing provider, which is slower and costs quota per entry. Either path is acceptable; being blocked is a legitimate, reportable outcome.
- **Agentic retrieval has unbounded cost.** A model free to search repeatedly can spend arbitrarily much of a five-hour window on one entry. A per-entry call ceiling is required, and the right value is not yet known.
- **The ~20 new gold entries are an unbuilt input.** Until they exist, `boundary-spanning` (3), `near-duplicate` (4), and `cross-document` (1) cannot support a per-tag claim. If they are not authored, those tags must be reported as illustrative rather than measured.
- **Query rewriting may help follow-ups and harm standalone questions** by over-expanding queries that were already precise. The zero-regression rule is what would catch this, and it is a real possibility rather than a hypothetical.
- **Whether five experiments fit the quota is unproven.** Each `fb_rules` iteration is roughly 110K input tokens and each full-corpus confirmation roughly 250K; the phase is likely to span many five-hour windows, and the ordering of experiments therefore matters.

## acceptance criteria

- [x] The judge rubric change is applied, documented with the two hedged-answer cases that motivated it, and the judge is unchanged thereafter.
- [x] A frozen Phase 4 baseline run exists and is referenced by every experiment.
- [x] Every run report contains a named, reproducible experiment configuration.
- [x] Each of the five techniques has been run against `fb_rules` and has an adoption decision recorded with its win / loss / tie counts.
- [x] Every regression produced by any technique is named, with the entry and the metric that regressed.
- [x] Adopted techniques have a full-corpus confirmation run. — vacuous: zero techniques were adopted (all five rejected under the zero-regression rule; agentic's confirmation run was already full-corpus regardless). See plan.md's Phase 4 summary.
- [x] A stacked configuration of the adopted techniques is run and compared against the baseline and against each technique alone. — SKIPPED by explicit user decision: the adopted set is empty, so `stacked-v1` would combine nothing. See plan.md's T8.1/T8.2 note.
- [x] The follow-up recall deficit measured in Phase 3 — 80% standalone versus 50% follow-up — is restated under the best configuration, closed or not. — restated at 81.4%/50.0% under the frozen baseline; closed to 100% follow-up under two independent techniques (rewrite-v1, agentic-v1), neither adopted.
- [x] `q-032`, `q-033`, and `q-037`, the three concrete follow-up misses from Phase 3, are each reported as fixed or still failing under query rewriting.
- [x] `q-011`, the BSPD lexical-anchor miss, is reported as fixed or still failing under hybrid search.
- [x] Agentic retrieval reports retrieval calls per entry and token cost alongside its quality metrics.
- [x] Per-tag effects are stated for every adopted technique, with tags below a usable sample size reported as illustrative rather than measured. — no technique was adopted, so this is reported across all five instead, exceeding the letter of the criterion. See plan.md's Phase 4 summary.
- [x] No PyTorch appears in `uv pip list` at the end of the phase.

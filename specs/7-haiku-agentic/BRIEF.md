# Phase 7 — Haiku in the agentic loop

Deliberately a one-page brief, not the spec/plan/tasks treatment earlier phases
got. The change is one config value and two runs; a three-file phase would be
ceremony.

## The question

Not "is Haiku cheaper" — on the `agent_sdk` subscription path it will consume
roughly the same five-hour-window tokens. The real question is which half of
agentic's advantage comes from the *loop* and which from the *model*:

- `recall_hit` / `coverage` measure **search quality** — did it formulate good
  queries and know when to search again?
- `grounded_rate` / `citation_precision` measure **answer quality** — did it
  reason correctly over what it found?

Two informative outcomes. If Haiku holds recall but loses groundedness,
capability matters for answering and not for searching, which licenses a
cheap-model-searches / strong-model-answers split. If Haiku loses recall too,
agentic's edge was capability all along, not the loop.

## What to do

**1. Probe first (cheap).** Confirm `AgentSDKProvider` runs `claude-haiku-4-5`
with custom tools at all. Haiku 4.5 is a 4.5-generation model and does not take
the same thinking/effort parameters the 5-family does; if anything in the path
sets those, it will fail. One trivial two-tool script, same shape as Phase 4's
T2.7. **Stop here and report if it doesn't work.**

**2. Run the 20-entry hard subset**, the same union of `follow-up`, `synthesis`,
and `cross-document` entries Phase 4 used. Compare against that subset's
`agentic-v1` figures. If Haiku collapses here, don't pay for the full run.

**3. Run full `fb_rules` (57 entries)** and compare per-entry against Phase 4's
existing `agentic-v1` report with `raglab compare`.

## What must not change

- **The judge stays `claude-opus-5`.** Changing the model under test is the
  experiment; changing the ruler would void six phases of comparability.
- Retrieval, chunking, the gold set, `max_calls`, and the agentic prompt are all
  unchanged. The answer model is the only variable.
- Record the model in the report — `RunConfig.answer.model` already does this,
  so provenance is automatic.

Setting it: edit `[answer].model` in `config.toml` between runs, or add a small
`--answer-model` override to `eval run`. Either is fine; the report captures it
regardless.

## Cost

Probe: negligible. Subset: ~330K input tokens. Full run: ~665K. Confirm each
before spending, per standing practice.

## What counts as a result

A filled-in version of this table, plus a per-entry `raglab compare` against
`agentic-v1`:

| | agentic-v1 (Sonnet 5) | agentic-haiku |
|---|---|---|
| recall@k | 98.1% | |
| coverage | 97.2% | |
| grounded | 94.3% | |
| citation precision | 73.6% | |
| input tokens | 665,135 | |
| **median wall-clock** | never measured | |

That last row is a free bonus: Phase 6 deferred latency measurement, and this
run produces the number for both models if you time the turns.

**A negative result is a result.** "Haiku is worse at both" closes the question
in one afternoon and is worth writing down.

---

## Result: the 20-entry hard subset

| | agentic-v1 (Sonnet 5) | agentic-haiku |
|---|---|---|
| recall@k | 100.0% | 95.0% |
| coverage | 92.5% | 90.0% |
| grounded | 90.0% | 85.0% |
| citation precision | 68.0% | **75.8%** |
| input tokens | 330,468 | **257,255** (−22%) |
| p50 wall-clock | 24.6s | **27.0s** |

Paired: **6 wins / 5 losses / 9 ties.** Regressions `q-004`, `q-034`, `q-036`
(citation precision only), `q-022` (coverage), `q-059` (recall, coverage, and
citation precision — the only real recall loss).

**Read it as no detectable difference, not as a mild softening.** Eleven entries
changed, six one way and five the other — a sign test on that is p ≈ 1.0. The
recall drop is one entry. The groundedness drop is one entry. Citation precision
*improved* by 7.8 points, which neither predicted outcome anticipated. The
honest summary is that on the hardest 20 questions in the corpus, Haiku is
indistinguishable from Sonnet 5 at 22% fewer tokens.

**Two corrections to the phase's premise, both from this data:**

- **Haiku is not faster.** p50 rose 24.6s → 27.0s. Whatever the case for Haiku
  in the escalation path is, it is not latency.
- **The 22% is quota, not dollars.** On the `agent_sdk` subscription the saving
  is 22% of the five-hour window. On an API key it would compound with Haiku's
  2× lower per-token price to roughly 60% cheaper. Quote whichever you mean.

## Next step: do NOT run the full 57 — measure variance instead

A 57-entry run cannot resolve what is actually open. Distinguishing "equal" from
"5% worse" needs far more than 57 entries; at that size a 6/5 split would still
be a 6/5 split, for ~665K tokens.

**The real unknown is how much an agentic run varies against itself.** Every
single-shot pipeline in this project is deterministic on retrieval — same query,
same chunks, every time. Agentic is not: the model composes its own search
queries, so two identical runs can retrieve differently. That variance has never
been measured, in any phase.

**Re-run the same 20 entries with Haiku a second time.** Same config, same
everything, ~257K tokens — under half the full run.

- Haiku-vs-Haiku also churns ~5W/6L → the Sonnet comparison above is noise,
  conclusively, and Haiku is a free 22%.
- Haiku-vs-Haiku comes back near-all-ties → the 6/5 split is real signal and
  worth chasing on the tags where it slipped (`cross-document` 1W/2L/2T,
  `synthesis` 2W/3L/3T).

**This also reaches backwards, which is the uncomfortable part.** Phase 4's
`agentic-v1` figures rest on a *single* run. The twelve citation-precision
regressions that justified all of Phase 5 — the router, the pruning, the citation
prompt, roughly 1.5M tokens of investigation — were never checked against
run-to-run variance. If agentic varies by a few points against itself, part of
what Phase 5 chased was noise. Worth knowing either way.

## Result: Haiku self-variance (same 20 entries, re-run)

| | haiku run 1 | haiku run 2 |
|---|---|---|
| recall@k | 95.0% | 95.0% |
| coverage | 90.0% | 87.5% |
| grounded | 85.0% | 95.0% |
| citation precision | 75.8% | 74.2% |
| input tokens | 257,255 | 254,341 |
| p50 wall-clock | 27.0s | 25.9s |

Paired against itself: **3 wins / 4 losses / 13 ties** (65% tied) — fewer
entries move than the Sonnet-vs-Haiku comparison (45% tied, 11 of 20 changed
vs. 7 of 20 here). By the tags that slipped in the Sonnet comparison:
`cross-document` goes from 1W/2L/2T (vs. Sonnet) to 0W/1L/4T (vs. itself);
`synthesis` goes from 2W/3L/3T to 2W/1L/5T. Both tags churn less against
Haiku's own repeat than against Sonnet — consistent with, though not proof
of, the Sonnet gap being partly real rather than pure noise on those two tags.

**`grounded_rate`'s own swing (85%→95%, 10 points) is larger than the
Sonnet-vs-Haiku gap it was compared against (90%→85%, 5 points).** Read
literally, run-to-run noise on this one metric exceeds the cross-model
difference — the single strongest piece of evidence in this phase that the
groundedness result is not a reliable signal, not "Haiku is worse at
answering," on the evidence collected so far.

**`recall_at_k` held exactly at 95.0% both times** — not noise. But the entry
behind it was misidentified in an earlier draft of this brief, and the
correction changes the conclusion.

**Corrected: the recall miss is `q-059`, not `q-036`, and Sonnet gets it
right.** Verified directly against all three reports — Sonnet's subset run has
*zero* `recall_hit=False` entries; both Haiku runs have exactly one, `q-059`.
`q-036` is not a recall miss in any run.

`q-059` is a **cross-document** question, and the mechanism is persistence, not
search quality:

| | calls | capped | recall | coverage |
|---|---|---|---|---|
| Sonnet | **5** | yes, hit the ceiling | True | 0.5 |
| Haiku run 1 | **2** | no | False | 0.0 |
| Haiku run 2 | **3** | no | False | 0.0 |

Sonnet kept searching until it hit `max_calls=5` and found the material. Haiku
concluded after two or three searches and answered anyway, reproducibly. This
is axis 2 from this brief's own framing — *deciding when to search again* — and
**Haiku never reaches the call ceiling, so `max_calls` is not the constraint;
the prompt is.**

It corroborates the tag data above: `cross-document` churns 1W/2L/2T against
Sonnet but only 0W/1L/4T against Haiku's own repeat. Less self-churn than
cross-model churn means the gap on that tag is real. All five `cross-document`
entries are in this subset, so that is the whole tag's evidence.

(`q-036` is a genuine shared failure — both models substitute BSPD for the
Brake Over-Travel Switch `T6.2.1` asks about — but it is a *groundedness*
failure with `recall_hit=True`, not the recall miss.)

**Reading the two comparisons together:** self-variance is real but smaller
than the cross-model differences on `citation_precision` (1.7pt self-swing vs.
+7.8pt Sonnet-Haiku gap, in Haiku's favour both times) and on `recall_at_k`
(0pt self-swing, exactly reproduced twice, vs. a 5pt gap that is one real
entry Sonnet gets and Haiku does not). It is *larger* than the cross-model gap
on `grounded_rate` specifically. Net: the citation-precision improvement is a
real replicated effect, the recall gap is a real replicated deficit, and the
groundedness dip is noise.

## Standing conclusion — Phase 7 closed

**Haiku is a viable escalation model on token cost and citation precision, not
on speed, and not on cross-document questions.**

- **Recall is not at parity.** 19/20 against Sonnet's 20/20 on the hardest
  entries — small, but real and replicated, and concentrated in exactly one
  failure mode: stopping the search too early on multi-document questions.
- **Citation precision improved** +7.8 points, replicated across both runs and
  well outside self-variance.
- **Groundedness is indistinguishable.** The apparent 5-point dip is smaller
  than the metric's own 10-point run-to-run swing. "No difference detected,"
  not "Haiku is worse at answering."
- **22% fewer tokens**, and ~10% *slower*.

**Decision: no change. Sonnet stays on both paths.** The reasoning is not the
size of the recall gap — it is where the gap lands. Escalation is the control a
user presses *because they already care about this answer*; they have accepted
the wait and the cost, and **there is no backstop behind it.** Trading any
accuracy for 22% fewer tokens on the one operation whose entire purpose is
quality is optimising the wrong thing.

No full 57-entry run was needed to reach this: it would have cost ~665K to
arrive at a noisier version of what a second 20-entry run settled for ~254K.

## Open thread for whenever this is picked up

**The untested configuration is the inverse: Haiku on the *default* path,
Sonnet on escalation.** It has a real argument behind it and no evidence
either way.

- The default path is the high-volume one — every question runs it. At roughly
  100 questions with 20 escalations, the default burns ~320K against
  escalation's ~260K.
- A quality drop there is *recoverable*, because escalation is the safety net
  sitting right behind it. A weak default answer costs one button press; a weak
  escalation costs the answer.
- Haiku's known failure mode cannot occur there. Early stopping requires a
  search loop to stop; the baseline is single-shot.

**Cost to find out: ~183K** — one baseline run on `fb_rules` against the frozen
Phase 4 baseline, which already exists as a paired reference. The cheapest
experiment proposed anywhere in this project.

Also still open, and deliberately not taken: a one-line agentic prompt change
telling the model to search each document separately on multi-document
questions. Since Haiku never hits the call ceiling, the prompt is the lever, and
the same 20-entry subset would give a paired comparison against two existing
Haiku runs.

**One methodological note for later phases:** Phase 4's and Phase 5's
`agentic-v1` figures rest on single runs. This phase's two Haiku runs are the
first measurement of agentic retrieval's self-variance anywhere in this
project, and it is not zero — `grounded_rate` swung 10 points with nothing
else changed. Any future single-run agentic comparison should be read with
that in mind.

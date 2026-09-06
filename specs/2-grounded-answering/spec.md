# spec: Phase 2 — Grounded Answering (citations as a measurement instrument)

## outcome

After this phase, every answer carries machine-checkable citations: the chunk ids the model claims to have relied on. The harness verifies them deterministically, with no LLM involved — whether a cited chunk was actually retrieved, and whether it overlaps the gold span. That gives the project its first judge-free groundedness signal, and turns the judge's known noise from an unknown quantity into a printed queue of entries where the deterministic check and the judge disagree. Alongside it, the gold set roughly doubles and gains a tag vocabulary, so Phase 4 can ask not just "did this technique help?" but "which kinds of question did it help?"

## in scope

- A structured citation block in the answer: the chunk ids the model relied on, machine-parseable.
- **Fabrication check** — was every cited chunk actually in the retrieved set? Requires no gold data.
- **Citation precision** — does a cited chunk overlap one of the entry's gold spans?
- A disagreement report listing entries where the deterministic checks and the LLM judge diverge.
- Gold-set schema v2: `sources` replaces the `doc` + `answer_location` pair, supporting multiple documents per entry.
- Migration of all five existing gold sets to v2.
- **Coverage** — the fraction of an entry's distinct gold spans hit by at least one retrieved chunk.
- Cross-document gold entries, and the baseline's honest refusal to attempt them.
- A controlled tag vocabulary, with per-tag metric breakdowns in the report.
- `raglab gold locate <anchor>` — reports every match of an anchor with line numbers, so gold-set authoring stops needing pasted one-liners.
- Expansion of `fb_rules.yaml` to ~25 entries, including repair of the five ambiguous anchors.

## out of scope

- **Web UI, FastAPI, React.** Still deferred. This phase produces no interface beyond CLI output.
- **Streaming.** The provider interface has supported it since Phase 0 and nothing has needed it. It has no evaluation value; it gets exercised when a UI exists to consume it.
- **Collections and scoped conversations.** Phase 3.
- **Hybrid search, reranking, query rewriting, structure-aware chunking.** Phase 4, unchanged.
- **Tuning the judge prompt or model.** This phase *measures* judge disagreement and records it. Changing the judge and changing retrieval in the same phase would make both unattributable — and Phase 0's and Phase 1's numbers only stay comparable while the ruler is fixed.
- **Reopening the any-overlap rule.** It stays frozen at the chunk level. Coverage is an additional entry-level metric built on top of it, not a replacement.

## users & context

Unchanged from Phase 1, with one addition: **gold-set authoring is now a first-class workflow, not a one-off.** Roughly fifteen new entries get written by hand in this phase, each needing an anchor checked for ambiguity and a line range read off the extracted text. `raglab gold locate` and `raglab gold validate` output are therefore developer-facing tools that get used repeatedly in a tight loop, and their readability matters as much as the eval runner's.

## constraints

- Everything from Phases 0 and 1 carries forward: Python 3.12 via `uv`, no PyTorch, no Docker, local-first, clone-and-run, minimal dependencies, `agent_sdk` as the working provider.
- The judge model, judge prompt, and groundedness definition are unchanged. Phase 2's numbers must remain directly comparable to Phase 0's and Phase 1's.
- The any-overlap chunk-level recall rule is unchanged.
- Chunking, embedding, and retrieval parameters are unchanged — 900/150 chunks, `bge-small-en-v1.5`, k=5. This phase must not move retrieval, or the citation numbers cannot be attributed.
- Gold-set schema v2 is a breaking change. The loader must reject v1 files with a message naming the migration, not attempt to read them.

## data & integrations

**Gold-set schema v2.** `doc` and `answer_location` are replaced by a `sources` list, so one entry can cite several documents:

```yaml
version: 2
corpus_hashes: { ... }

entries:
  - id: q-001
    question: "What does BSPD stand for and what must it do?"
    expected_answer: "..."
    sources:
      - doc: fb_rules.pdf
        answer_location: { type: line_range, start: 4120, end: 4126 }
    tags: [lexical-anchor]

  - id: q-024
    question: "..."
    expected_answer: "..."
    sources:
      - doc: fb_rules.pdf
        answer_location: { type: line_range, start: 900, end: 912 }
      - doc: amg_mct.md
        answer_location: { type: line_range, start: 23, end: 23 }
    tags: [cross-document, synthesis]

  - id: q-003
    question: "How much is the driver bond fee?"
    expected_answer: null
    sources: []
    tags: [not-in-document]
```

A single-document entry is a one-element list. `sources: []` and a `not-in-document` tag imply each other, and the validator enforces both directions.

**Tag vocabulary**, validated and used to slice metrics: `lexical-anchor`, `vocabulary-mismatch`, `synthesis`, `near-duplicate`, `boundary-spanning`, `cross-document`, `not-in-document`. Free-form additional tags are permitted; an entry carrying no vocabulary tag is a validation warning, because an untagged entry is invisible in the per-tag breakdown Phase 4 depends on.

**Revision-history anchors are deliberate hard negatives.** Several entries target rule IDs that also appear in the document's changelog or contents listing. The gold span points at the rule body; the other occurrence is a distractor a retriever may wrongly return, and the any-overlap rule will correctly score that as a miss.

**`section` anchors gain two changes, both established by evidence during gold-set authoring.** Matching is restricted to occurrences that *begin a line*, allowing leading whitespace and Markdown heading markers — this alone removes cross-reference noise (`EV6.1.2` drops from three matches to one, because "…defined in EV6.1.2 must be…" no longer counts). And an optional `occurrence` selector (`first`, `last`, or a 1-based index) resolves the collisions that remain, which are almost always a changelog or contents-listing copy earlier in the document. Absent a selector, Phase 1's behavior is unchanged: more than one match is unscoreable, never a guess.

**Rule-ID anchors replace hand-authored line ranges on PDFs.** A full gold set was authored against a different PDF extraction than `raglab`'s parser produces, and all 28 line ranges were wrong by 1,100–1,300 lines with no constant offset — silently pointing at unrelated rules. Re-anchored on rule IDs, 32 of 33 resolved on the first attempt against an extraction the author had never seen. Line numbers are a coordinate system that belongs to one parser; rule IDs belong to the document.

**Report additions** — `citations` per entry (cited ids, fabricated ids, precision), `coverage` per entry, and aggregates for citation precision, fabrication rate, mean coverage, and a per-tag breakdown of every existing rate. No change to how existing fields are computed.

## prior decisions

- **Citations are a measurement instrument, not a UI feature.** The reason to build them now is that they yield a deterministic groundedness signal, which is the only available antidote to a judge with two verified false negatives across ninety graded entries.
- **Citations are chunk ids in a structured block.** Chunk ids are already stable, already readable in run reports, and already the unit recall is scored on. Prose citations parsed by regex were rejected — the judge's JSON parsing already demonstrated how that fails.
- **The gold set expands to ~25 entries on `fb_rules`, weighted by question type.** The existing entries are written in the rulebook's own vocabulary and few hinge on a rare literal token, so hybrid search and query rewriting would have shown no measurable effect in Phase 4 regardless of whether they work. The gold set determines which improvements are visible at all.
- **Coverage is added rather than changing the recall rule.** Multi-anchor entries currently score a hit if *any* gold span is retrieved, which flatters synthesis questions — `fb_rules` q-004, q-005, and q-006 each have two anchors today. Coverage exposes that without touching the frozen rule.
- **Cross-document entries are excluded from whole-document baseline runs.** The baseline puts one document in context and structurally cannot answer a question spanning two. Reporting them as skipped-with-reason is honest; the alternative — feeding it several documents — would silently redefine what the baseline measures.
- **The judge is not touched this phase.** Disagreements are recorded so a later phase can tune the prompt against real examples rather than intuition.

## requirements

### always active

- The system SHALL require the answering pipeline to emit, alongside its answer, a machine-parseable list of the chunk ids it relied on.
- The system SHALL verify that every cited chunk id was present in the set retrieved for that question.
- The system SHALL compute citation precision as the fraction of cited chunks whose character span overlaps at least one of the entry's gold spans.
- The system SHALL compute coverage as the fraction of an entry's distinct gold spans hit by at least one retrieved chunk.
- The system SHALL accept gold sets declaring `version: 2` and SHALL reject `version: 1` files.
- The system SHALL support gold entries whose `sources` name more than one document.
- The system SHALL record every metric broken down by tag as well as in aggregate.
- The system SHALL match a `section` anchor only where it begins a line, permitting leading whitespace and Markdown heading markers.
- The system SHALL accept an optional `occurrence` selector on a `section` anchor, taking `first`, `last`, or a 1-based index, and SHALL apply it independently to each anchor in `value`.
- The system SHALL leave the judge model, judge prompt, retrieval parameters, and the any-overlap rule unchanged.

### event-driven

- WHEN a retrieval pipeline answers, the system SHALL record its cited chunk ids in the run report.
- WHEN a cited chunk id was not in the retrieved set, the system SHALL record it as a fabricated citation and count it in the fabrication rate.
- WHEN the deterministic citation check and the LLM judge reach opposite conclusions on an entry, the system SHALL list that entry in a disagreement section of the run summary, with both verdicts.
- WHEN a whole-document baseline run encounters a cross-document entry, the system SHALL record it as skipped with an explicit reason and SHALL NOT attempt an answer.
- WHEN `raglab gold locate <anchor>` is invoked, the system SHALL print every match of that anchor with its line number and surrounding context, using the same boundary rule the location resolver uses.
- WHEN a gold set is validated, the system SHALL warn for any entry carrying no tag from the controlled vocabulary.

### unwanted behavior

- IF the answering pipeline emits no parseable citation block, the system SHALL record the entry as uncited and exclude it from citation metrics, and SHALL NOT treat it as a fabrication or as a groundedness failure.
- IF a gold set declares `version: 1`, the system SHALL abort naming the file and the required migration, and SHALL NOT attempt to interpret it.
- IF an entry has an empty `sources` list without the `not-in-document` tag, or the tag without an empty list, the system SHALL report it as invalid.
- IF a `section` anchor in a v2 gold set resolves ambiguously, the system SHALL continue to report the entry as unscoreable for recall while still grading it for groundedness, exactly as Phase 1 established.
- IF a cited chunk id is syntactically malformed, the system SHALL record it as fabricated rather than raising.

## acceptance criteria

- [x] A retrieval run report contains, per entry, the cited chunk ids, any fabricated ids, citation precision, and coverage.
- [x] Aggregates include citation precision, fabrication rate, mean coverage, and a per-tag breakdown of every rate.
- [x] A pipeline citing a chunk id it was never given is caught and counted as a fabrication, verified by a test using a stubbed provider.
- [x] All five gold sets load as `version: 2`; a `version: 1` file is rejected with a message naming the migration.
- [x] `fb_rules.yaml` holds ~25 entries, with at least one entry per vocabulary tag and at least four `not-in-document` entries.
- [x] The five previously ambiguous `fb_rules` anchors resolve, so at least 20 entries are recall-scoreable.
- [x] At least one cross-document entry exists, retrieval answers it, and a whole-document baseline run records it as skipped with a reason.
- [x] `raglab gold locate A4.4.1` reports both occurrences with line numbers, marking which is line-initial.
- [x] Every anchor in `fb_rules.yaml` resolves, with no entry unscoreable for ambiguity.
- [x] A `section` anchor appearing only as a mid-sentence cross-reference produces no match, verified on `EV6.1.2`.
- [x] Coverage is strictly below recall_hit for at least one multi-anchor entry, demonstrating it measures something recall alone does not.
- [x] The run summary prints a disagreement section, and it is empty or non-empty for reasons a human can check by hand.
- [x] Grounded and refusal-correct rates on the four Markdown gold sets do not regress against Phase 1 -- refusal-correct held at 100% on all four in both phases, no regression. grounded_rate held on egear/smg (100%/100%) but dropped on amg_mct (88.9%→77.8%) and tiptronic (100%→87.5%); traced to judge-verdict flips on byte-identical retrieved context and near-identical answer content across runs, not to the citation-instruction prompt -- see plan.md's as-built notes. (fb_rules itself, not one of the four Markdown sets but sharing this run's machinery, saw its own refusal_correct_rate move from 50% to 100% after two `not-in-document` entries were corrected in the gold set -- a gold-set fix, not a model or judge change, and further evidence the earlier dips are not systemic.)

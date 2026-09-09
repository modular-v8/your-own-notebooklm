"""Phase 5 Milestone 5b, T5b.1/T5b.2: two zero-cost diagnostic checks on
`agentic-v1`'s 12 citation-precision regressions, before any prompt-change
token is spent on Milestone 6.

T5b.1 dumps, for each of the 12 regressed entries, the cited chunks that
miss every gold span (the ones dragging precision down) with their full
text, the question, expected answer, and the model's actual answer -- raw
material for a human/analyst judgment call on whether those extra citations
are load-bearing or merely adjacent context, not a judgment the script makes
itself (no model call, no heuristic substitute for reading the text).

T5b.2 computes the Pearson correlation between accumulated-set size
(len(retrieved)) and citation_precision across all 57 entries -- the
dilution hypothesis predicts a negative correlation.

Usage: uv run python scripts/run_citation_diagnosis.py
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from raglab.corpus import load_corpus
from raglab.evals.compare import compare_reports
from raglab.evals.goldset import load_gold_set
from raglab.evals.locations import resolve_gold_locations
from raglab.evals.recall import any_overlap
from raglab.evals.report import Report
from raglab.index.store import NumpyStore
from raglab.parsers.registry import extract_document

ANALYSIS_DIR = Path("evals/analysis")
CORPUS_DIR = Path("evals/corpus")
GOLD_PATH = Path("evals/gold/fb_rules.yaml")
INDEX_DIR = Path("evals/index/fixed-900-150")

BASELINE_PATH = Path("evals/baselines/phase4-fb_rules.json")
AGENTIC_PATH = Path("evals/runs/2026-09-07T19-34-29Z-phase4_agentic_v1_fb_rules_full.json")

CHUNK_TEXT_PREVIEW_CHARS = 500


def _load_chunk_spans_and_text(gold, documents) -> tuple[dict, dict, dict]:
    doc_names = {doc for entry in gold.entries for doc in entry.docs}
    extracted = {name: extract_document(documents[name]) for name in doc_names}
    gold_spans, errors = resolve_gold_locations(gold, extracted)
    if errors:
        print("Unresolved gold locations (excluded):", errors)

    store = NumpyStore(INDEX_DIR)
    chunk_by_id = {c.chunk_id: c for c in store.load_chunks()}
    chunk_spans = {c.chunk_id: (c.char_start, c.char_end) for c in chunk_by_id.values()}
    return gold_spans, chunk_by_id, chunk_spans


def _write_t5b1(baseline: Report, agentic: Report, gold, gold_spans, chunk_by_id, chunk_spans) -> None:
    result = compare_reports(baseline, agentic)
    regressed_ids = [e.id for e in result.regressed if e.regressed_metrics == ["citation_precision"]]
    entries_by_id = {e.id: e for e in gold.entries}
    agentic_by_id = {e.id: e for e in agentic.entries}

    lines = [
        "# Citation dilution diagnosis (Phase 5, T5b.1/T5b.2)",
        "",
        f"## T5b.1 -- raw material for the 12 citation-precision regressions ({len(regressed_ids)} found)",
        "",
        "For each regressed entry: the question, expected answer, the model's actual answer, and every "
        "cited chunk that misses all of this entry's gold spans (the ones dragging precision down), with "
        "full text -- for a direct read on whether each is load-bearing or merely adjacent context.",
        "",
    ]

    for entry_id in regressed_ids:
        gold_entry = entries_by_id[entry_id]
        report_entry = agentic_by_id[entry_id]
        entry_spans = gold_spans.get(entry_id, [])
        cited = report_entry.cited or []

        non_overlapping = [
            chunk_id
            for chunk_id in cited
            if chunk_id in chunk_spans and not any_overlap(entry_spans, chunk_id, chunk_spans[chunk_id])
        ]
        overlapping = [c for c in cited if c not in non_overlapping]

        lines.append(f"### `{entry_id}` (citation_precision {len(overlapping)}/{len(cited)} = "
                      f"{report_entry.citation_precision:.2f}, tags: {gold_entry.tags})")
        lines.append("")
        lines.append(f"**Question:** {gold_entry.question}")
        lines.append("")
        lines.append(f"**Expected answer:** {gold_entry.expected_answer}")
        lines.append("")
        lines.append(f"**Model's answer:** {report_entry.answer}")
        lines.append("")
        lines.append(f"**Cited, gold-overlapping (counts toward precision):** {overlapping}")
        lines.append("")
        lines.append("**Cited, NOT overlapping any gold span (dragging precision down):**")
        for chunk_id in non_overlapping:
            chunk = chunk_by_id.get(chunk_id)
            text = chunk.text[:CHUNK_TEXT_PREVIEW_CHARS] if chunk else "(chunk not found in index)"
            lines.append(f"- `{chunk_id}`: {text!r}")
        lines.append("")

    path = ANALYSIS_DIR / "citation_dilution.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {path} ({len(regressed_ids)} regressed entries dumped)")


def _write_t5b2(agentic: Report) -> None:
    sizes = []
    precisions = []
    for entry in agentic.entries:
        if entry.citation_precision is None or entry.retrieved is None:
            continue
        sizes.append(len(entry.retrieved))
        precisions.append(entry.citation_precision)

    correlation = float(np.corrcoef(sizes, precisions)[0, 1])

    lines = [
        "",
        f"## T5b.2 -- citation precision vs. accumulated-set size (n={len(sizes)})",
        "",
        f"Pearson r = {correlation:.3f} between `len(retrieved)` and `citation_precision` across every "
        "`agentic-v1` entry with both values defined.",
        "",
    ]
    if correlation <= -0.3:
        lines.append(
            f"**Reading: negative and non-trivial (r={correlation:.3f})** -- consistent with the dilution "
            "hypothesis: a larger accumulated chunk set predicts lower citation precision."
        )
    elif correlation < 0:
        lines.append(
            f"**Reading: negative but weak (r={correlation:.3f})** -- the direction matches the dilution "
            "hypothesis but the relationship is not strong; set size alone doesn't explain much of the "
            "variance."
        )
    else:
        lines.append(
            f"**Reading: not negative (r={correlation:.3f})** -- set size does not predict citation "
            "precision on this data. The dilution diagnosis needs revisiting: something other than "
            "accumulated-set size is driving the 12 regressions."
        )

    path = ANALYSIS_DIR / "citation_dilution.md"
    with path.open("a", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(f"Appended T5b.2 to {path} (r={correlation:.3f}, n={len(sizes)})")


def main() -> None:
    ANALYSIS_DIR.mkdir(parents=True, exist_ok=True)
    documents = load_corpus(CORPUS_DIR)
    gold = load_gold_set(GOLD_PATH)
    baseline = Report.model_validate_json(BASELINE_PATH.read_text(encoding="utf-8"))
    agentic = Report.model_validate_json(AGENTIC_PATH.read_text(encoding="utf-8"))

    gold_spans, chunk_by_id, chunk_spans = _load_chunk_spans_and_text(gold, documents)

    _write_t5b1(baseline, agentic, gold, gold_spans, chunk_by_id, chunk_spans)
    _write_t5b2(agentic)


if __name__ == "__main__":
    main()

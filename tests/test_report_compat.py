"""A Phase 1 report (no citation/coverage/by_tag fields) still loads under
the Phase 2 schema and deltas correctly against a Phase 2 report."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from raglab.evals.report import (
    Aggregates,
    EntryReport,
    GoldSetRef,
    Report,
    RoleReportConfig,
    RunConfig,
    TagAggregates,
    compute_delta,
)

PHASE_1_REPORT_PATH = Path("evals/runs/2026-09-05T17-13-35Z-fb_rules_retrieval.json")


def test_real_phase_1_report_loads_with_new_fields_defaulted():
    report = Report.model_validate_json(PHASE_1_REPORT_PATH.read_text(encoding="utf-8"))
    assert report.gold_set.version == 1
    assert report.aggregates.citation_precision is None
    assert report.aggregates.fabrication_rate is None
    assert report.aggregates.mean_coverage is None
    assert report.aggregates.uncited == 0
    assert report.aggregates.by_tag == {}
    for entry in report.entries:
        assert entry.cited is None
        assert entry.fabricated is None
        assert entry.citation_precision is None
        assert entry.coverage is None


def test_phase_1_report_deltas_against_phase_2_report():
    phase_1 = Report.model_validate_json(PHASE_1_REPORT_PATH.read_text(encoding="utf-8"))

    phase_2 = Report(
        run_id="2026-09-06T00-00-00Z-fb_rules_retrieval",
        started_at=datetime.now(timezone.utc).isoformat(),
        duration_s=40.0,
        config=phase_1.config,
        gold_set=GoldSetRef(path=str(PHASE_1_REPORT_PATH), version=2, entry_count=27),
        corpus_hashes=phase_1.corpus_hashes,
        aggregates=Aggregates(
            grounded_rate=0.9,
            refusal_correct_rate=1.0,
            graded=27,
            ungraded=0,
            skipped=0,
            errored=0,
            recall_at_k=0.95,
            mrr=0.8,
            input_tokens=60000,
            output_tokens=6000,
            p50_latency_s=10.0,
            citation_precision=0.85,
            fabrication_rate=0.02,
            mean_coverage=0.7,
            uncited=1,
            by_tag={"lexical-anchor": TagAggregates(count=7, grounded_rate=1.0)},
        ),
        entries=[EntryReport(id="q-001", status="graded", verdict="grounded")],
    )

    delta = compute_delta(phase_1, phase_2)
    assert delta["grounded_rate"] is not None
    # Phase 1 has no citation_precision to diff against -- must not crash, must be None.
    assert delta["citation_precision"] is None
    assert delta["fabrication_rate"] is None
    assert delta["mean_coverage"] is None

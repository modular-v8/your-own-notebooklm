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
    UsageReport,
    compute_delta,
)

PHASE_1_REPORT_PATH = Path("evals/runs/2026-09-05T17-13-35Z-fb_rules_retrieval.json")

# Predates Phase 5's usage split and retrieved_scores -- both must default cleanly.
PHASE_4_AGENTIC_REPORT_PATH = Path("evals/runs/2026-09-07T19-34-29Z-phase4_agentic_v1_fb_rules_full.json")


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


def test_real_phase_4_report_loads_with_usage_split_and_scores_defaulted():
    report = Report.model_validate_json(PHASE_4_AGENTIC_REPORT_PATH.read_text(encoding="utf-8"))
    for entry in report.entries:
        assert entry.retrieved_scores is None
        assert entry.pruned_discarded is None
        if entry.usage is not None:
            assert entry.usage.fresh_input_tokens == 0
            assert entry.usage.cache_creation_tokens == 0
            assert entry.usage.cache_read_tokens == 0
            # input_tokens keeps its pre-existing summed meaning unchanged.
            assert entry.usage.input_tokens > 0


def test_usage_report_split_round_trips_through_json():
    usage = UsageReport(
        input_tokens=180,
        output_tokens=20,
        fresh_input_tokens=100,
        cache_creation_tokens=30,
        cache_read_tokens=50,
    )
    entry = EntryReport(id="q-001", status="graded", usage=usage, retrieved_scores=[0.9, 0.7])

    restored = EntryReport.model_validate_json(entry.model_dump_json())

    assert restored.usage.fresh_input_tokens == 100
    assert restored.usage.cache_creation_tokens == 30
    assert restored.usage.cache_read_tokens == 50
    assert restored.usage.input_tokens == 180
    assert restored.retrieved_scores == [0.9, 0.7]

"""Paired per-entry comparison (specs/4-retrieval-optimization, Milestone 2).

T2.5's real acceptance gate lives in test_compare_baseline_against_itself_is_all_ties:
if that doesn't hold, nothing downstream in the phase can be trusted.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from raglab.evals.compare import CompareError, compare_reports
from raglab.evals.report import Aggregates, EntryReport, GoldSetRef, Report, RoleReportConfig, RunConfig
from raglab.experiments import ChunkingConfig, ExperimentConfig, RetrievalConfig

BASELINE_EXPERIMENT = ExperimentConfig(
    name="baseline",
    chunking=ChunkingConfig(strategy="fixed", size=900, overlap=150),
    retrieval=RetrievalConfig(mode="dense", k=5),
)

STRUCTURE_EXPERIMENT = ExperimentConfig(
    name="structure-v1",
    chunking=ChunkingConfig(strategy="structure", size=900, overlap=150),
    retrieval=RetrievalConfig(mode="dense", k=5),
)

BASE_RUN_CONFIG = RunConfig(
    pipeline="retrieval",
    answer=RoleReportConfig(provider="agent_sdk", model="claude-sonnet-5"),
    judge=RoleReportConfig(provider="agent_sdk", model="claude-opus-5"),
    concurrency=5,
    experiment=BASELINE_EXPERIMENT,
)

GOLD_SET_REF = GoldSetRef(path="evals/gold/x.yaml", version=3, entry_count=2, entry_ids_fingerprint="abc123")


def _empty_aggregates() -> Aggregates:
    return Aggregates(
        grounded_rate=None,
        refusal_correct_rate=None,
        graded=0,
        ungraded=0,
        skipped=0,
        errored=0,
        input_tokens=0,
        output_tokens=0,
        p50_latency_s=0.0,
    )


def _report(run_id: str, entries: list[EntryReport], *, config: RunConfig = BASE_RUN_CONFIG) -> Report:
    return Report(
        run_id=run_id,
        started_at=datetime.now(timezone.utc).isoformat(),
        duration_s=1.0,
        config=config,
        gold_set=GOLD_SET_REF,
        corpus_hashes={"doc.md": "sha256:abc"},
        aggregates=_empty_aggregates(),
        entries=entries,
    )


def _entry(
    id: str,
    *,
    status: str = "graded",
    verdict: str | None = "grounded",
    recall_hit: bool | None = True,
    coverage: float | None = 1.0,
    citation_precision: float | None = 1.0,
) -> EntryReport:
    return EntryReport(
        id=id,
        status=status,
        verdict=verdict,
        recall_hit=recall_hit,
        coverage=coverage,
        citation_precision=citation_precision,
    )


def test_recall_hit_flip_false_to_true_is_win():
    baseline = _report("b", [_entry("q-1", recall_hit=False, coverage=0.0, citation_precision=0.0)])
    experiment = _report("e", [_entry("q-1", recall_hit=True, coverage=0.0, citation_precision=0.0)])
    result = compare_reports(baseline, experiment)
    assert result.entries[0].metrics["recall_hit"].classification == "win"
    assert result.wins == 1 and result.losses == 0


def test_recall_hit_flip_true_to_false_is_loss():
    baseline = _report("b", [_entry("q-1", recall_hit=True)])
    experiment = _report("e", [_entry("q-1", recall_hit=False)])
    result = compare_reports(baseline, experiment)
    assert result.entries[0].metrics["recall_hit"].classification == "loss"
    assert result.losses == 1


def test_coverage_increase_is_win_decrease_is_loss():
    baseline = _report("b", [_entry("q-1", coverage=0.5), _entry("q-2", coverage=0.5)])
    experiment = _report("e", [_entry("q-1", coverage=1.0), _entry("q-2", coverage=0.0)])
    result = compare_reports(baseline, experiment)
    by_id = {e.id: e for e in result.entries}
    assert by_id["q-1"].metrics["coverage"].classification == "win"
    assert by_id["q-2"].metrics["coverage"].classification == "loss"


def test_citation_precision_increase_is_win_decrease_is_loss():
    baseline = _report("b", [_entry("q-1", citation_precision=0.5), _entry("q-2", citation_precision=0.5)])
    experiment = _report("e", [_entry("q-1", citation_precision=1.0), _entry("q-2", citation_precision=0.0)])
    result = compare_reports(baseline, experiment)
    by_id = {e.id: e for e in result.entries}
    assert by_id["q-1"].metrics["citation_precision"].classification == "win"
    assert by_id["q-2"].metrics["citation_precision"].classification == "loss"


def test_entry_improving_one_metric_and_regressing_another_is_a_loss():
    """T2.1: one win + one loss on the same entry must roll up as a loss,
    never averaged into a tie or a win."""
    baseline = _report("b", [_entry("q-1", recall_hit=False, citation_precision=1.0)])
    experiment = _report("e", [_entry("q-1", recall_hit=True, citation_precision=0.5)])
    result = compare_reports(baseline, experiment)
    entry = result.entries[0]
    assert entry.metrics["recall_hit"].classification == "win"
    assert entry.metrics["citation_precision"].classification == "loss"
    assert entry.classification == "loss"
    assert result.losses == 1 and result.wins == 0


def test_grounded_only_flip_is_a_tie():
    """T2.2: grounded_rate is reported but never classifies."""
    baseline = _report("b", [_entry("q-1", verdict="not_grounded")])
    experiment = _report("e", [_entry("q-1", verdict="grounded")])
    result = compare_reports(baseline, experiment)
    entry = result.entries[0]
    assert entry.baseline_verdict == "not_grounded"
    assert entry.experiment_verdict == "grounded"
    assert entry.classification == "tie"
    assert result.ties == 1


def test_missing_experiment_config_is_refused_and_names_the_report():
    no_experiment_config = RunConfig(
        pipeline="retrieval",
        answer=RoleReportConfig(provider="agent_sdk", model="claude-sonnet-5"),
        judge=RoleReportConfig(provider="agent_sdk", model="claude-opus-5"),
        concurrency=5,
    )
    baseline = _report("baseline-run", [_entry("q-1")], config=no_experiment_config)
    experiment = _report("experiment-run", [_entry("q-1")])
    with pytest.raises(CompareError, match="baseline-run"):
        compare_reports(baseline, experiment)


def test_gold_set_mismatch_is_refused_and_names_both_reports():
    baseline = _report("baseline-run", [_entry("q-1")])
    different_gold = GoldSetRef(path="evals/gold/y.yaml", version=3, entry_count=1, entry_ids_fingerprint="zzz")
    experiment = Report(
        run_id="experiment-run",
        started_at=datetime.now(timezone.utc).isoformat(),
        duration_s=1.0,
        config=BASE_RUN_CONFIG,
        gold_set=different_gold,
        corpus_hashes={"doc.md": "sha256:abc"},
        aggregates=_empty_aggregates(),
        entries=[_entry("q-1")],
    )
    with pytest.raises(CompareError, match="baseline-run") as exc_info:
        compare_reports(baseline, experiment)
    assert "experiment-run" in str(exc_info.value)


def test_chunking_mismatch_produces_note_and_still_classifies_span_metrics():
    structure_config = RunConfig(
        pipeline="retrieval",
        answer=RoleReportConfig(provider="agent_sdk", model="claude-sonnet-5"),
        judge=RoleReportConfig(provider="agent_sdk", model="claude-opus-5"),
        concurrency=5,
        experiment=STRUCTURE_EXPERIMENT,
    )
    baseline = _report("b", [_entry("q-1", recall_hit=False)])
    experiment = _report("e", [_entry("q-1", recall_hit=True)], config=structure_config)

    result = compare_reports(baseline, experiment)

    assert result.chunking_mismatch is True
    assert result.chunking_note is not None
    assert "not comparable" in result.chunking_note
    # Span-based classification still runs even though chunking differs.
    assert result.entries[0].metrics["recall_hit"].classification == "win"


def test_errored_entry_excluded_from_classification():
    baseline = _report("b", [_entry("q-1", status="errored", verdict=None, recall_hit=None, coverage=None, citation_precision=None)])
    experiment = _report("e", [_entry("q-1")])
    result = compare_reports(baseline, experiment)
    assert result.entries == []
    assert result.excluded == ["q-1"]
    assert result.wins == 0 and result.losses == 0 and result.ties == 0


def test_by_tag_breakdown():
    baseline = _report("b", [_entry("q-1", recall_hit=False), _entry("q-2", recall_hit=True)])
    experiment = _report("e", [_entry("q-1", recall_hit=True), _entry("q-2", recall_hit=True)])
    result = compare_reports(baseline, experiment, tags_by_id={"q-1": ["follow-up"], "q-2": ["follow-up"]})
    assert result.by_tag["follow-up"].count == 2
    assert result.by_tag["follow-up"].wins == 1
    assert result.by_tag["follow-up"].ties == 1


def test_compare_baseline_against_itself_is_all_ties():
    """T2.5's real gate: if a report doesn't tie against a byte-identical
    copy of itself, the comparison machinery is wrong and nothing
    downstream can be trusted."""
    entries = [
        _entry("q-1", recall_hit=True, coverage=1.0, citation_precision=1.0),
        _entry("q-2", recall_hit=False, coverage=0.0, citation_precision=0.0),
        _entry("q-3", verdict="refused_correctly", recall_hit=None, coverage=None, citation_precision=None),
    ]
    baseline = _report("b", entries)
    copy = _report("e", entries)

    result = compare_reports(baseline, copy)

    assert result.wins == 0
    assert result.losses == 0
    assert result.ties == len(entries)


def test_agentic_entry_fields_do_not_need_special_casing():
    """T7.2: retrieval_calls/capped are new fields on an agentic entry, but
    compare_reports must classify purely from recall_hit/coverage/
    citation_precision, same as every other pipeline -- no branch on
    "is this an agentic entry" anywhere in the comparison."""
    baseline = _report("b", [_entry("q-1", recall_hit=False, coverage=0.0, citation_precision=0.0)])
    agentic_entry = _entry("q-1", recall_hit=True, coverage=1.0, citation_precision=1.0)
    agentic_entry = agentic_entry.model_copy(update={"retrieval_calls": 3, "capped": True})
    experiment = _report("e", [agentic_entry])

    result = compare_reports(baseline, experiment)

    assert result.entries[0].classification == "win"

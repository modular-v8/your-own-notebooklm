"""Report schema stability (null retrieval fields) and delta computation."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from raglab.evals.report import (
    Aggregates,
    EntryReport,
    GoldSetRef,
    Report,
    ReportWriter,
    RoleReportConfig,
    RunConfig,
    compute_delta,
    find_matching_prior_report,
    make_run_id,
)
from raglab.experiments import ChunkingConfig, ExperimentConfig, RetrievalConfig

BASE_CONFIG = RunConfig(
    pipeline="whole_doc",
    answer=RoleReportConfig(provider="anthropic", model="claude-sonnet-5"),
    judge=RoleReportConfig(provider="anthropic", model="claude-opus-5"),
    concurrency=5,
)


def _report(run_id: str, *, graded: int, grounded_rate: float) -> Report:
    return Report(
        run_id=run_id,
        started_at=datetime.now(timezone.utc).isoformat(),
        duration_s=1.0,
        config=BASE_CONFIG,
        gold_set=GoldSetRef(path="evals/gold/x.yaml", version=1, entry_count=graded),
        corpus_hashes={"doc.md": "sha256:abc"},
        aggregates=Aggregates(
            grounded_rate=grounded_rate,
            refusal_correct_rate=None,
            graded=graded,
            ungraded=0,
            skipped=0,
            errored=0,
            input_tokens=100,
            output_tokens=50,
            p50_latency_s=1.5,
        ),
        entries=[EntryReport(id="q-001", status="graded", verdict="grounded")],
    )


def test_retrieval_fields_are_null_and_schema_accepts_them():
    report = _report("r1", graded=1, grounded_rate=1.0)
    assert report.aggregates.recall_at_k is None
    assert report.aggregates.mrr is None
    assert report.entries[0].retrieved is None
    assert report.entries[0].recall_hit is None

    # Round-trips through JSON without a schema change (Phase 1 populates these).
    dumped = report.model_dump_json()
    restored = Report.model_validate_json(dumped)
    assert restored.aggregates.recall_at_k is None


def test_writer_writes_readable_json(tmp_path):
    report = _report("2026-01-01T00-00-00Z-baseline", graded=1, grounded_rate=1.0)
    path = ReportWriter(tmp_path).write(report)
    assert path.exists()
    assert path.name == "2026-01-01T00-00-00Z-baseline.json"
    assert Report.model_validate_json(path.read_text(encoding="utf-8")).run_id == report.run_id


def test_make_run_id_format():
    started = datetime(2026, 3, 5, 12, 30, 45, tzinfo=timezone.utc)
    assert make_run_id("baseline", started) == "2026-03-05T12-30-45Z-baseline"


BASE_GOLD_SET = GoldSetRef(path="evals/gold/x.yaml", version=1, entry_count=1, entry_ids_fingerprint="")


def test_find_matching_prior_report_requires_matching_config(tmp_path):
    matching = _report("2026-01-01T00-00-00Z-a", graded=1, grounded_rate=0.5)
    ReportWriter(tmp_path).write(matching)

    different_config = RunConfig(
        pipeline="whole_doc",
        answer=RoleReportConfig(provider="openrouter", model="claude-sonnet-5"),
        judge=RoleReportConfig(provider="anthropic", model="claude-opus-5"),
        concurrency=5,
    )
    assert find_matching_prior_report(tmp_path, different_config, BASE_GOLD_SET) is None
    found = find_matching_prior_report(tmp_path, BASE_CONFIG, BASE_GOLD_SET)
    assert found is not None
    assert found.run_id == matching.run_id


def test_find_matching_prior_report_requires_matching_gold_set(tmp_path):
    """A Phase 0 defect: matching on provider config alone let a 29-entry
    rulebook run print a delta against a 10-entry transmission run."""
    matching = _report("2026-01-01T00-00-00Z-a", graded=1, grounded_rate=0.5)
    ReportWriter(tmp_path).write(matching)

    different_gold_set = GoldSetRef(path="evals/gold/y.yaml", version=1, entry_count=1, entry_ids_fingerprint="zzz")
    assert find_matching_prior_report(tmp_path, BASE_CONFIG, different_gold_set) is None


def test_run_config_without_experiment_defaults_to_none():
    """Backward compat: a pre-Phase-4 report has no `experiment` field at
    all, the same way old reports lacked `collection`."""
    assert BASE_CONFIG.experiment is None


def test_run_config_experiment_round_trips_through_json():
    experiment = ExperimentConfig(
        name="baseline",
        chunking=ChunkingConfig(strategy="fixed", size=900, overlap=150),
        retrieval=RetrievalConfig(mode="dense", k=5),
    )
    report = _report("2026-01-01T00-00-00Z-a", graded=1, grounded_rate=1.0)
    report = report.model_copy(update={"config": BASE_CONFIG.model_copy(update={"experiment": experiment})})

    restored = Report.model_validate_json(report.model_dump_json())

    assert restored.config.experiment.name == "baseline"
    assert restored.config.experiment.chunking.size == 900
    assert restored.config.experiment.chunking.overlap == 150
    assert restored.config.experiment.retrieval.mode == "dense"
    assert restored.config.experiment.retrieval.k == 5


def test_compute_delta_is_new_minus_old():
    previous = _report("2026-01-01T00-00-00Z-a", graded=10, grounded_rate=0.5)
    current = _report("2026-01-02T00-00-00Z-b", graded=10, grounded_rate=0.8)
    delta = compute_delta(previous, current)
    assert delta["grounded_rate"] == pytest.approx(0.3)
    assert delta["graded"] == 0
    assert delta["refusal_correct_rate"] is None  # both None -> None, not 0

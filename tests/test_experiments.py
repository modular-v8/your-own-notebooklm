"""ExperimentConfig loading from experiments.toml (specs/4-retrieval-optimization,
T1.4). `baseline` must reproduce today's fixed defaults exactly -- that's
what makes the Phase 4 baseline run comparable to Phases 0-3's numbers."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from raglab.experiments import (
    DEFAULT_EXPERIMENTS_PATH,
    ChunkingConfig,
    ExperimentsError,
    index_subdir_name,
    load_experiments,
)


def _write(tmp_path: Path, content: str) -> Path:
    path = tmp_path / "experiments.toml"
    path.write_text(textwrap.dedent(content), encoding="utf-8")
    return path


def test_repo_experiments_toml_baseline_matches_todays_defaults():
    """Pins the T1.4 acceptance shape against the real, checked-in file:
    900/150 chunking (index/chunker.py), k=5 dense retrieval (config.toml's
    [retrieval].top_k)."""
    experiments = load_experiments(DEFAULT_EXPERIMENTS_PATH)
    baseline = experiments["baseline"]

    assert baseline.name == "baseline"
    assert baseline.chunking.strategy == "fixed"
    assert baseline.chunking.size == 900
    assert baseline.chunking.overlap == 150
    assert baseline.retrieval.mode == "dense"
    assert baseline.retrieval.k == 5
    assert baseline.rewriting is None
    assert baseline.reranking is None
    assert baseline.agentic is None


def test_load_experiments_parses_named_entries(tmp_path):
    path = _write(
        tmp_path,
        """
        [baseline.chunking]
        strategy = "fixed"
        size = 900
        overlap = 150

        [baseline.retrieval]
        mode = "dense"
        k = 5

        [hybrid-v1.chunking]
        strategy = "fixed"
        size = 900
        overlap = 150

        [hybrid-v1.retrieval]
        mode = "hybrid"
        k = 5
        candidate_k = 20
        rrf_k = 60
        """,
    )
    experiments = load_experiments(path)

    assert set(experiments) == {"baseline", "hybrid-v1"}
    hybrid = experiments["hybrid-v1"]
    assert hybrid.retrieval.mode == "hybrid"
    assert hybrid.retrieval.candidate_k == 20
    assert hybrid.retrieval.rrf_k == 60


def test_missing_file_raises():
    with pytest.raises(ExperimentsError):
        load_experiments(Path("does-not-exist.toml"))


def test_missing_required_field_raises(tmp_path):
    path = _write(
        tmp_path,
        """
        [baseline.chunking]
        strategy = "fixed"
        size = 900
        overlap = 150
        """,
    )
    with pytest.raises(ExperimentsError):
        load_experiments(path)


def test_index_subdir_name_encodes_size_and_overlap_for_fixed():
    assert index_subdir_name(ChunkingConfig(strategy="fixed", size=900, overlap=150)) == "fixed-900-150"


def test_index_subdir_name_is_bare_for_structure():
    assert index_subdir_name(ChunkingConfig(strategy="structure", size=2000, overlap=150)) == "structure"

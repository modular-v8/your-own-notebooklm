"""AUC, bootstrap CI, and threshold sweep on synthetic labels/scores
(Phase 5, T2.3). 57 entries with 14 positives will overfit any multi-feature
model (plan.md), so these tests exercise the single-signal-threshold
machinery directly, not a fitted classifier.
"""

from __future__ import annotations

from raglab.analysis.signal_study import (
    CHANCE_AUC,
    auc,
    bootstrap_ci,
    candidate_thresholds,
    clears_chance_bar,
    threshold_sweep,
)


def test_auc_perfectly_separable_case():
    # Every positive scores strictly higher than every negative.
    labels = [False, False, False, True, True, True]
    scores = [0.1, 0.2, 0.3, 0.8, 0.9, 1.0]
    assert auc(labels, scores) == 1.0


def test_auc_inverted_signal_scores_below_chance():
    # Positives score strictly lower than negatives -- the opposite direction.
    labels = [False, False, False, True, True, True]
    scores = [0.8, 0.9, 1.0, 0.1, 0.2, 0.3]
    assert auc(labels, scores) == 0.0


def test_auc_identical_scores_is_exactly_chance():
    labels = [False, True, False, True]
    scores = [0.5, 0.5, 0.5, 0.5]
    assert auc(labels, scores) == 0.5


def test_bootstrap_ci_tight_around_one_for_separable_case():
    labels = [False] * 20 + [True] * 20
    scores = [i / 100 for i in range(20)] + [i / 100 + 1.0 for i in range(20)]
    lo, hi = bootstrap_ci(labels, scores, n_boot=500, seed=0)
    assert lo > 0.9
    assert hi <= 1.0


def test_bootstrap_ci_contains_chance_for_random_case():
    # Alternating labels against monotonically increasing scores in a small
    # sample -- no real separation, CI should straddle 0.50.
    labels = [i % 2 == 0 for i in range(20)]
    scores = list(range(20))
    lo, hi = bootstrap_ci(labels, scores, n_boot=500, seed=0)
    assert lo <= CHANCE_AUC <= hi


def test_clears_chance_bar_requires_both_auc_and_ci():
    assert clears_chance_bar(0.9, (0.7, 0.99)) is True
    assert clears_chance_bar(0.9, (0.4, 0.99)) is False  # CI still touches chance
    assert clears_chance_bar(0.6, (0.55, 0.65)) is False  # AUC below the bar


def test_candidate_thresholds_are_sorted_distinct_scores():
    assert candidate_thresholds([0.3, 0.1, 0.3, 0.9]) == [0.1, 0.3, 0.9]


def test_threshold_sweep_counts_escalations_correctly():
    labels = [False, False, True, True]  # 2 misses, 2 hits
    scores = [0.1, 0.2, 0.5, 0.9]

    points = threshold_sweep(labels, scores, thresholds=[0.15, 0.6])

    low, high = points
    # threshold=0.15: only the 0.1 score escalates -- catches one miss, no hits.
    assert low.escalation_rate == 1 / 4
    assert low.misses_caught == 1
    assert low.hits_wrongly_escalated == 0

    # threshold=0.6: everything below 0.6 escalates -- both misses, one hit.
    assert high.escalation_rate == 3 / 4
    assert high.misses_caught == 2
    assert high.hits_wrongly_escalated == 1


def test_threshold_sweep_escalates_a_score_exactly_at_the_threshold():
    # spread <= threshold escalates (plan.md: "spread > threshold? -> stop"),
    # so a score exactly on the boundary must escalate, not survive.
    labels = [False, True]
    scores = [0.5, 0.9]
    point = threshold_sweep(labels, scores, thresholds=[0.5])[0]
    assert point.misses_caught == 1
    assert point.escalation_rate == 1 / 2

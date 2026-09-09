# Signal separation study (Phase 5, T2.3/T2.5)

Baseline recall on `fb_rules`: 40 hits, 13 misses, 53 scored (not-in-document entries excluded -- no gold span to score recall against).

Chance bar: AUC >= 0.65 and the bootstrap 95% CI excludes 0.5.

| signal | AUC | 95% CI | clears bar? |
|---|---|---|---|
| `top1` | 0.740 | [0.591, 0.870] | YES |
| `margin` | 0.688 | [0.542, 0.819] | YES |
| `spread` | 0.821 | [0.700, 0.922] | YES |
| `count_above` | 0.500 | [0.500, 0.500] | no |
| `doc_agreement` | 0.296 | [0.142, 0.448] | no |

**Verdict: `spread` clears the chance bar** (AUC=0.821, 95% CI=[0.700, 0.922]) -- a proxy router is viable on this corpus.

## Threshold sweep

### `top1`

| threshold | escalation rate | misses caught | hits wrongly escalated |
|---|---|---|---|
| 0.558 | 1.9% | 1/13 | 0/40 |
| 0.638 | 13.2% | 3/13 | 4/40 |
| 0.662 | 24.5% | 6/13 | 7/40 |
| 0.678 | 34.0% | 7/13 | 11/40 |
| 0.712 | 45.3% | 10/13 | 14/40 |
| 0.755 | 56.6% | 11/13 | 19/40 |
| 0.781 | 67.9% | 12/13 | 24/40 |
| 0.797 | 77.4% | 12/13 | 29/40 |
| 0.814 | 88.7% | 13/13 | 34/40 |
| 0.875 | 100.0% | 13/13 | 40/40 |

### `margin`

| threshold | escalation rate | misses caught | hits wrongly escalated |
|---|---|---|---|
| 0.000 | 1.9% | 0/13 | 1/40 |
| 0.001 | 13.2% | 1/13 | 6/40 |
| 0.004 | 24.5% | 4/13 | 9/40 |
| 0.013 | 34.0% | 6/13 | 12/40 |
| 0.021 | 45.3% | 9/13 | 15/40 |
| 0.027 | 56.6% | 11/13 | 19/40 |
| 0.034 | 67.9% | 13/13 | 23/40 |
| 0.046 | 77.4% | 13/13 | 28/40 |
| 0.059 | 88.7% | 13/13 | 34/40 |
| 0.123 | 100.0% | 13/13 | 40/40 |

### `spread`

| threshold | escalation rate | misses caught | hits wrongly escalated |
|---|---|---|---|
| 0.010 | 1.9% | 0/13 | 1/40 |
| 0.021 | 13.2% | 2/13 | 5/40 |
| 0.028 | 24.5% | 6/13 | 7/40 |
| 0.037 | 34.0% | 9/13 | 9/40 |
| 0.051 | 45.3% | 13/13 | 11/40 |
| 0.069 | 56.6% | 13/13 | 17/40 |
| 0.082 | 67.9% | 13/13 | 23/40 |
| 0.098 | 77.4% | 13/13 | 28/40 |
| 0.111 | 88.7% | 13/13 | 34/40 |
| 0.169 | 100.0% | 13/13 | 40/40 |

### `count_above`

| threshold | escalation rate | misses caught | hits wrongly escalated |
|---|---|---|---|
| 5.000 | 100.0% | 13/13 | 40/40 |

### `doc_agreement`

| threshold | escalation rate | misses caught | hits wrongly escalated |
|---|---|---|---|
| 1.000 | 75.5% | 6/13 | 34/40 |
| 2.000 | 88.7% | 9/13 | 38/40 |
| 3.000 | 100.0% | 13/13 | 40/40 |


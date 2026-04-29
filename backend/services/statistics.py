"""
Statistical helpers for research reports.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from scipy import stats

from services.metrics import cumulative_return, sharpe_ratio, win_rate


@dataclass(frozen=True)
class ConfidenceInterval:
    metric: str
    lower: float
    upper: float
    samples: int


@dataclass(frozen=True)
class PairwiseTestResult:
    test_name: str
    statistic: float
    p_value: float
    corrected_p_value: float
    effect_size: float
    n: int


def bootstrap_confidence_intervals(
    equity_series: list[float],
    trade_pnls: list[float],
    *,
    resamples: int = 1000,
    seed: int = 42,
) -> list[ConfidenceInterval]:
    rng = np.random.default_rng(seed)
    equity = np.array(equity_series, dtype=float)
    pnls = np.array(trade_pnls or [0.0], dtype=float)
    rows: dict[str, list[float]] = {"sharpe": [], "return": [], "win_rate": []}
    if len(equity) < 2:
        return [ConfidenceInterval(metric=name, lower=0.0, upper=0.0, samples=0) for name in rows]
    for _ in range(resamples):
        indices = rng.integers(0, len(equity), size=len(equity))
        sampled_equity = equity[np.sort(indices)].tolist()
        sampled_pnls = pnls[rng.integers(0, len(pnls), size=len(pnls))].tolist()
        rows["sharpe"].append(sharpe_ratio(sampled_equity))
        rows["return"].append(cumulative_return(sampled_equity))
        rows["win_rate"].append(win_rate(sampled_pnls))
    return [
        ConfidenceInterval(
            metric=name,
            lower=_finite(float(np.percentile(values, 2.5))),
            upper=_finite(float(np.percentile(values, 97.5))),
            samples=resamples,
        )
        for name, values in rows.items()
    ]


def pairwise_pnl_test(
    left: list[float],
    right: list[float],
    *,
    comparisons: int = 1,
    prefer_wilcoxon: bool = True,
) -> PairwiseTestResult:
    n = min(len(left), len(right))
    if n == 0:
        return PairwiseTestResult("none", 0.0, 1.0, 1.0, 0.0, 0)
    left_arr = np.array(left[:n], dtype=float)
    right_arr = np.array(right[:n], dtype=float)
    diff = left_arr - right_arr
    if prefer_wilcoxon and n > 1 and np.any(diff):
        result = stats.wilcoxon(left_arr, right_arr, zero_method="zsplit")
        test_name = "wilcoxon_signed_rank"
    elif n > 1:
        result = stats.ttest_rel(left_arr, right_arr)
        test_name = "paired_t_test"
    else:
        return PairwiseTestResult("insufficient_samples", 0.0, 1.0, 1.0, 0.0, n)
    p_value = _finite(float(result.pvalue), default=1.0)
    return PairwiseTestResult(
        test_name=test_name,
        statistic=_finite(float(result.statistic)),
        p_value=p_value,
        corrected_p_value=min(1.0, p_value * max(comparisons, 1)),
        effect_size=cohens_d(diff.tolist()),
        n=n,
    )


def cohens_d(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    arr = np.array(values, dtype=float)
    std = float(np.std(arr, ddof=1))
    if std <= 0 or not math.isfinite(std):
        return 0.0
    return _finite(float(np.mean(arr)) / std)


def _finite(value: float, *, default: float = 0.0) -> float:
    return value if math.isfinite(value) else default

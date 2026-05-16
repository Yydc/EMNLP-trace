"""Bootstrap CI utilities.

Paper Table tab:gap says "Hard-split gaps include paired bootstrap 95% CIs."
This module provides two flavors:

  - ``problem_bootstrap_ci``  : resample problems (rows of E1 main matrix)
  - ``paired_bootstrap_ci``   : resample problems AND models pairwise (for
                                 per-problem differences across models)

Pure stdlib (no numpy/scipy dep) so it runs anywhere.
"""

from __future__ import annotations

import random
from statistics import mean
from typing import Any, Callable, List, Sequence, Tuple


def problem_bootstrap_ci(
    values: Sequence[float],
    statistic: Callable[[Sequence[float]], float] = mean,
    n_resamples: int = 1000,
    alpha: float = 0.05,
    seed: int = 12345,
) -> Tuple[float, float, float]:
    """Resample-with-replacement bootstrap CI for a single metric.

    Returns (point_estimate, lower, upper) where lower/upper are the
    (alpha/2, 1 - alpha/2) percentiles of the bootstrap distribution.
    """
    if not values:
        return float("nan"), float("nan"), float("nan")
    rng = random.Random(seed)
    n = len(values)
    samples = []
    for _ in range(n_resamples):
        resample = [values[rng.randrange(n)] for _ in range(n)]
        samples.append(statistic(resample))
    samples.sort()
    lo_idx = int(alpha / 2 * n_resamples)
    hi_idx = int((1 - alpha / 2) * n_resamples) - 1
    return statistic(values), samples[lo_idx], samples[hi_idx]


def paired_bootstrap_ci(
    paired_values: Sequence[Tuple[float, float]],
    diff_fn: Callable[[float, float], float] = lambda a, b: a - b,
    statistic: Callable[[Sequence[float]], float] = mean,
    n_resamples: int = 1000,
    alpha: float = 0.05,
    seed: int = 12345,
) -> Tuple[float, float, float]:
    """Paired bootstrap CI for per-problem (a, b) differences.

    Used to compute CI for Gap = Pass@1 - Blame@1, where each problem
    contributes one (pass, blame) pair.
    """
    if not paired_values:
        return float("nan"), float("nan"), float("nan")
    rng = random.Random(seed)
    n = len(paired_values)
    diffs = [diff_fn(a, b) for a, b in paired_values]
    samples = []
    for _ in range(n_resamples):
        resample = [diffs[rng.randrange(n)] for _ in range(n)]
        samples.append(statistic(resample))
    samples.sort()
    lo_idx = int(alpha / 2 * n_resamples)
    hi_idx = int((1 - alpha / 2) * n_resamples) - 1
    return statistic(diffs), samples[lo_idx], samples[hi_idx]


def correlation_with_ci(
    xs: Sequence[float],
    ys: Sequence[float],
    n_resamples: int = 1000,
    alpha: float = 0.05,
    seed: int = 12345,
) -> Tuple[float, float, float, int]:
    """Pearson r + bootstrap CI for paired (x, y).

    Returns (r, lower, upper, n). Filters out any pair with NaN/None.
    """
    if len(xs) != len(ys):
        raise ValueError("xs and ys must be same length")
    pairs = [(x, y) for x, y in zip(xs, ys) if x is not None and y is not None]
    if len(pairs) < 3:
        return float("nan"), float("nan"), float("nan"), len(pairs)

    def pearson(p: Sequence[Tuple[float, float]]) -> float:
        n = len(p)
        if n < 2:
            return 0.0
        mx = sum(x for x, _ in p) / n
        my = sum(y for _, y in p) / n
        num = sum((x - mx) * (y - my) for x, y in p)
        denx = sum((x - mx) ** 2 for x, _ in p)
        deny = sum((y - my) ** 2 for _, y in p)
        denom = (denx * deny) ** 0.5
        return num / denom if denom > 0 else 0.0

    r = pearson(pairs)
    rng = random.Random(seed)
    n = len(pairs)
    samples = []
    for _ in range(n_resamples):
        resample = [pairs[rng.randrange(n)] for _ in range(n)]
        samples.append(pearson(resample))
    samples.sort()
    lo_idx = int(alpha / 2 * n_resamples)
    hi_idx = int((1 - alpha / 2) * n_resamples) - 1
    return r, samples[lo_idx], samples[hi_idx], n

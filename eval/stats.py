"""Small statistics for reporting evaluation results honestly.

A rate from a few dozen rows is an estimate, so it is reported with the range
the true rate plausibly lies in.
"""

from __future__ import annotations

import math
from collections.abc import Sequence


def wilson_interval(passed: int, scored: int, z: float = 1.96) -> tuple[float, float]:
    """The Wilson score interval for a pass rate. The default ``z`` gives 95%.

    Unlike the textbook interval, it stays inside 0 to 1 and is not zero-width
    when every row passes: 22 of 22 gives about 0.85 to 1.00, which is what a
    perfect score on 22 rows supports.

    Raises:
        ValueError: If the counts are not possible.
    """
    if scored <= 0 or not 0 <= passed <= scored:
        msg = f"not a valid count: {passed} of {scored}"
        raise ValueError(msg)
    rate = passed / scored
    denominator = 1 + z * z / scored
    centre = (rate + z * z / (2 * scored)) / denominator
    margin = z * math.sqrt(rate * (1 - rate) / scored + z * z / (4 * scored * scored)) / denominator
    # An exact 0 or 1 at the ends, where rounding would otherwise leave 0.9999.
    low = 0.0 if passed == 0 else max(0.0, centre - margin)
    high = 1.0 if passed == scored else min(1.0, centre + margin)
    return low, high


def rate_with_interval(passed: int, scored: int) -> str:
    """``27/31 (71-95%)``: the count, then the 95% interval in whole percent."""
    low, high = wilson_interval(passed, scored)
    return f"{passed}/{scored} ({math.floor(low * 100)}-{math.ceil(high * 100)}%)"


def percentile(values: Sequence[float], fraction: float) -> float:
    """The value at ``fraction`` of the way through the sorted values (nearest rank).

    Raises:
        ValueError: If there are no values or the fraction is outside 0 to 1.
    """
    if not values or not 0 <= fraction <= 1:
        msg = "percentile needs at least one value and a fraction from 0 to 1"
        raise ValueError(msg)
    ordered = sorted(values)
    rank = max(1, math.ceil(fraction * len(ordered)))
    return ordered[rank - 1]

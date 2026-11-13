"""Formation geometry scorers for double top and RGR (head and shoulders)."""

from collections.abc import Sequence
from dataclasses import dataclass

from detection.pivots import Pivot

SYMMETRY_WEIGHT = 0.30
TREND_WEIGHT = 0.20
RETRACE_WEIGHT = 0.20
SEPARATION_WEIGHT = 0.15
SLOPE_WEIGHT = 0.15

TREND_ATR_SCALE = 3.0
RETRACE_ATR_SCALE = 3.0
NECKLINE_SLOPE_TOLERANCE = 0.01

# Only the trailing ``MAX_PIVOT_LOOKBACK`` pivots are eligible as the opening
# pivot of a candidate. A currently-forming pattern is anchored to the live leg,
# so this bound keeps every forming pattern while capping the nested enumeration
# on noisy series, which can otherwise score hundreds of thousands of
# geometrically-valid but irrelevant combinations.
MAX_PIVOT_LOOKBACK = 20


@dataclass(frozen=True)
class CandidateEvidence:
    pivots: tuple[Pivot, ...]
    neckline: float | None


@dataclass(frozen=True)
class Candidate:
    pattern: str
    stage: str
    sub_score: float
    evidence: CandidateEvidence


def score_double_top(
    pivots: Sequence[Pivot],
    *,
    atr_value: float,
    tolerance: float,
    min_separation: int,
) -> Candidate | None:
    """Score the best double top in ``pivots``, if any.

    ``forming`` is a confirmed peak, the confirmed trough after it, and the
    trailing unconfirmed high back within ``tolerance`` of the first peak.
    ``confirmed`` is the same geometry with a confirmed second peak followed by
    a pivot low below the trough (the neckline break).
    """
    if atr_value <= 0 or tolerance <= 0 or min_separation <= 0:
        return None

    best: Candidate | None = None
    start = max(0, len(pivots) - MAX_PIVOT_LOOKBACK)
    prior_lows = _prior_confirmed_lows(pivots)
    for first_position in range(start, len(pivots)):
        first = pivots[first_position]
        if first.kind != "high" or not first.confirmed:
            continue
        for trough_position in range(first_position + 1, len(pivots)):
            trough = pivots[trough_position]
            if trough.kind != "low" or not trough.confirmed:
                continue
            if trough.price >= first.price:
                continue
            for second_position in range(trough_position + 1, len(pivots)):
                second = pivots[second_position]
                if second.kind != "high":
                    continue
                if second.index - first.index < min_separation:
                    continue
                if _relative_distance(second.price, first.price) > tolerance:
                    continue
                if second.confirmed:
                    breakout = _first_low_below(
                        pivots[second_position + 1 :], trough.price
                    )
                    if breakout is None:
                        continue
                    stage = "confirmed"
                    used = (first, trough, second, breakout)
                elif second_position == len(pivots) - 1:
                    stage = "forming"
                    used = (first, trough, second)
                else:
                    continue

                sub_score = _double_top_score(
                    prior_lows,
                    first_position,
                    first,
                    trough,
                    second,
                    atr_value=atr_value,
                    tolerance=tolerance,
                    min_separation=min_separation,
                )
                candidate = Candidate(
                    pattern="double_top",
                    stage=stage,
                    sub_score=sub_score,
                    evidence=CandidateEvidence(pivots=used, neckline=trough.price),
                )
                if best is None or candidate.sub_score > best.sub_score:
                    best = candidate
    return best


def score_head_shoulders(
    pivots: Sequence[Pivot],
    *,
    atr_value: float,
    tolerance: float,
    min_separation: int,
) -> Candidate | None:
    """Score the best RGR (head and shoulders top) in ``pivots``, if any.

    ``forming`` is a confirmed left shoulder, a higher head, the two troughs
    and the trailing unconfirmed high within ``tolerance`` of the left
    shoulder. ``confirmed`` is the same geometry with a confirmed right
    shoulder followed by a pivot low below the trough line.
    """
    if atr_value <= 0 or tolerance <= 0 or min_separation <= 0:
        return None

    best: Candidate | None = None
    start = max(0, len(pivots) - MAX_PIVOT_LOOKBACK)
    prior_lows = _prior_confirmed_lows(pivots)
    for left_position in range(start, len(pivots)):
        left = pivots[left_position]
        if left.kind != "high" or not left.confirmed:
            continue
        for first_trough_position in range(left_position + 1, len(pivots)):
            first_trough = pivots[first_trough_position]
            if first_trough.kind != "low" or not first_trough.confirmed:
                continue
            if first_trough.price >= left.price:
                continue
            for head_position in range(first_trough_position + 1, len(pivots)):
                head = pivots[head_position]
                if head.kind != "high" or not head.confirmed:
                    continue
                if head.price <= left.price:
                    continue
                for second_trough_position in range(head_position + 1, len(pivots)):
                    second_trough = pivots[second_trough_position]
                    if second_trough.kind != "low" or not second_trough.confirmed:
                        continue
                    if second_trough.price >= head.price:
                        continue
                    if second_trough.index <= first_trough.index:
                        continue
                    slope = (second_trough.price - first_trough.price) / (
                        second_trough.index - first_trough.index
                    )
                    for shoulder_position in range(
                        second_trough_position + 1, len(pivots)
                    ):
                        shoulder = pivots[shoulder_position]
                        if shoulder.kind != "high":
                            continue
                        if shoulder.index - left.index < min_separation:
                            continue
                        if _relative_distance(shoulder.price, left.price) > tolerance:
                            continue
                        if shoulder.price >= head.price:
                            continue
                        if shoulder.confirmed:
                            breakout = _first_low_below_neckline(
                                pivots[shoulder_position + 1 :], second_trough, slope
                            )
                            if breakout is None:
                                continue
                            stage = "confirmed"
                            used = (
                                left,
                                first_trough,
                                head,
                                second_trough,
                                shoulder,
                                breakout,
                            )
                            neckline = _neckline_at(
                                second_trough, slope, breakout.index
                            )
                        elif shoulder_position == len(pivots) - 1:
                            stage = "forming"
                            used = (
                                left,
                                first_trough,
                                head,
                                second_trough,
                                shoulder,
                            )
                            neckline = _neckline_at(
                                second_trough, slope, shoulder.index
                            )
                        else:
                            continue

                        sub_score = _head_shoulders_score(
                            prior_lows,
                            left_position,
                            left,
                            first_trough,
                            head,
                            second_trough,
                            shoulder,
                            slope=slope,
                            atr_value=atr_value,
                            tolerance=tolerance,
                            min_separation=min_separation,
                        )
                        candidate = Candidate(
                            pattern="head_shoulders",
                            stage=stage,
                            sub_score=sub_score,
                            evidence=CandidateEvidence(
                                pivots=used, neckline=neckline
                            ),
                        )
                        if best is None or candidate.sub_score > best.sub_score:
                            best = candidate
    return best


def _double_top_score(
    prior_lows: Sequence[Pivot | None],
    first_position: int,
    first: Pivot,
    trough: Pivot,
    second: Pivot,
    *,
    atr_value: float,
    tolerance: float,
    min_separation: int,
) -> float:
    symmetry = _symmetry(first.price, second.price, tolerance)
    trend = _prior_trend(prior_lows, first_position, first.price, atr_value)
    retrace = _clamp(
        (first.price - trough.price) / (atr_value * RETRACE_ATR_SCALE)
    )
    separation = _clamp((second.index - first.index) / (2.0 * min_separation))
    return _clamp(
        SYMMETRY_WEIGHT * symmetry
        + TREND_WEIGHT * trend
        + RETRACE_WEIGHT * retrace
        + SEPARATION_WEIGHT * separation
        + SLOPE_WEIGHT
    )


def _head_shoulders_score(
    prior_lows: Sequence[Pivot | None],
    left_position: int,
    left: Pivot,
    first_trough: Pivot,
    head: Pivot,
    second_trough: Pivot,
    shoulder: Pivot,
    *,
    slope: float,
    atr_value: float,
    tolerance: float,
    min_separation: int,
) -> float:
    symmetry = _symmetry(left.price, shoulder.price, tolerance)
    trend = _prior_trend(prior_lows, left_position, head.price, atr_value)
    retrace = _clamp(
        (
            (head.price - first_trough.price)
            + (head.price - second_trough.price)
        )
        / (2.0 * atr_value * RETRACE_ATR_SCALE)
    )
    separation = _clamp((shoulder.index - left.index) / (2.0 * min_separation))
    slope_ratio = abs(slope) / head.price if head.price else 1.0
    slope_score = _clamp(1.0 - slope_ratio / NECKLINE_SLOPE_TOLERANCE)
    return _clamp(
        SYMMETRY_WEIGHT * symmetry
        + TREND_WEIGHT * trend
        + RETRACE_WEIGHT * retrace
        + SEPARATION_WEIGHT * separation
        + SLOPE_WEIGHT * slope_score
    )


def _symmetry(first: float, second: float, tolerance: float) -> float:
    return _clamp(1.0 - _relative_distance(second, first) / tolerance)


def _prior_trend(
    prior_lows: Sequence[Pivot | None],
    position: int,
    peak_price: float,
    atr_value: float,
) -> float:
    prior_low = prior_lows[position]
    if prior_low is None:
        return 0.0
    return _clamp(
        (peak_price - prior_low.price) / (atr_value * TREND_ATR_SCALE)
    )


def _prior_confirmed_lows(pivots: Sequence[Pivot]) -> list[Pivot | None]:
    prior: list[Pivot | None] = [None] * len(pivots)
    last: Pivot | None = None
    for position, pivot in enumerate(pivots):
        prior[position] = last
        if pivot.kind == "low" and pivot.confirmed:
            last = pivot
    return prior


def _first_low_below(pivots: Sequence[Pivot], level: float) -> Pivot | None:
    for pivot in pivots:
        if pivot.kind == "low" and pivot.price < level:
            return pivot
    return None


def _first_low_below_neckline(
    pivots: Sequence[Pivot], anchor: Pivot, slope: float
) -> Pivot | None:
    for pivot in pivots:
        if pivot.kind == "low" and pivot.price < _neckline_at(
            anchor, slope, pivot.index
        ):
            return pivot
    return None


def _neckline_at(anchor: Pivot, slope: float, index: int) -> float:
    return anchor.price + slope * (index - anchor.index)


def _relative_distance(value: float, reference: float) -> float:
    if reference == 0:
        return float("inf")
    return abs(value - reference) / abs(reference)


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date

import numpy as np

from marketdata.providers import Candle


@dataclass(frozen=True)
class Pivot:
    index: int
    date: date
    price: float
    kind: str
    confirmed: bool


def atr(candles: Sequence[Candle], period: int) -> float | None:
    """Average true range over the last ``period`` completed bars.

    Returns ``None`` when there are fewer than ``period + 1`` bars, because the
    first bar has no previous close to measure a true range against.
    """
    if period <= 0 or len(candles) < period + 1:
        return None
    high, low, close = float_arrays(candles)
    return atr_from_arrays(high, low, close, period)


def atr_from_arrays(
    high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int
) -> float | None:
    """Average true range from precomputed float arrays."""
    if period <= 0 or len(close) < period + 1:
        return None
    previous_close = close[:-1]
    true_range = np.maximum.reduce(
        [
            high[1:] - low[1:],
            np.abs(high[1:] - previous_close),
            np.abs(low[1:] - previous_close),
        ]
    )
    return float(np.mean(true_range[-period:]))


def find_pivots(
    candles: Sequence[Candle], *, atr_value: float, deviation: float
) -> list[Pivot]:
    """Track ATR-scaled swing pivots causally, exposing the live leg.

    A high is confirmed once price retraces ``deviation * atr_value`` below the
    running high, and a low symmetrically. The extreme since the last confirmed
    pivot is appended as an unconfirmed pivot so callers can score a formation
    that is still forming. A non-positive ``atr_value`` or ``deviation`` returns
    an empty list because no retrace can be measured.
    """
    if not candles or atr_value <= 0 or deviation <= 0:
        return []

    high, low, _ = float_arrays(candles)
    return find_pivots_from_arrays(
        candles, high, low, atr_value=atr_value, deviation=deviation
    )


def find_pivots_from_arrays(
    candles: Sequence[Candle],
    high: np.ndarray,
    low: np.ndarray,
    *,
    atr_value: float,
    deviation: float,
) -> list[Pivot]:
    """Causal ZigZag scan over precomputed high/low float arrays."""
    threshold = deviation * atr_value
    pivots: list[Pivot] = []
    direction = "up"
    extreme_index = 0
    extreme_price = float(high[0])

    for index in range(1, len(candles)):
        if direction == "up":
            if high[index] > extreme_price:
                extreme_index = index
                extreme_price = float(high[index])
            elif extreme_price - low[index] >= threshold:
                pivots.append(
                    Pivot(
                        index=extreme_index,
                        date=candles[extreme_index].date,
                        price=extreme_price,
                        kind="high",
                        confirmed=True,
                    )
                )
                direction = "down"
                extreme_index = index
                extreme_price = float(low[index])
        else:
            if low[index] < extreme_price:
                extreme_index = index
                extreme_price = float(low[index])
            elif high[index] - extreme_price >= threshold:
                pivots.append(
                    Pivot(
                        index=extreme_index,
                        date=candles[extreme_index].date,
                        price=extreme_price,
                        kind="low",
                        confirmed=True,
                    )
                )
                direction = "up"
                extreme_index = index
                extreme_price = float(high[index])

    kind = "high" if direction == "up" else "low"
    if not (
        pivots
        and pivots[-1].index == extreme_index
        and pivots[-1].kind == kind
    ):
        pivots.append(
            Pivot(
                index=extreme_index,
                date=candles[extreme_index].date,
                price=extreme_price,
                kind=kind,
                confirmed=False,
            )
        )
    return pivots


def float_arrays(
    candles: Sequence[Candle],
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    high = np.array([float(candle.high) for candle in candles], dtype=float)
    low = np.array([float(candle.low) for candle in candles], dtype=float)
    close = np.array([float(candle.close) for candle in candles], dtype=float)
    return high, low, close

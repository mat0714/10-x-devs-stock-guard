from datetime import date, timedelta
from decimal import Decimal

from django.test import TestCase

from detection.pivots import atr, find_pivots
from marketdata.providers import Candle


def _candles(rows, *, start=date(2024, 1, 1)):
    return [
        Candle(
            date=start + timedelta(days=offset),
            open=Decimal(str(close)),
            high=Decimal(str(high)),
            low=Decimal(str(low)),
            close=Decimal(str(close)),
            volume=None,
        )
        for offset, (high, low, close) in enumerate(rows)
    ]


class PivotTests(TestCase):
    def test_atrReturnsNoneWhenSeriesHasPeriodOrFewerBars(self):
        candles = _candles([(10, 8, 9)] * 5)

        self.assertIsNone(atr(candles, 5))
        self.assertIsNone(atr(candles, 6))

    def test_atrReturnsNoneWhenPeriodIsNotPositive(self):
        candles = _candles([(10, 8, 9)] * 5)

        self.assertIsNone(atr(candles, 0))
        self.assertIsNone(atr(candles, -1))

    def test_atrReturnsPositiveFloatWhenSeriesHasEnoughBars(self):
        candles = _candles([(10, 8, 9)] * 6)

        result = atr(candles, 4)

        self.assertIsInstance(result, float)
        self.assertGreater(result, 0.0)
        self.assertAlmostEqual(result, 2.0)

    def test_findPivotsReturnsConfirmedHighThenConfirmedLowWhenSeriesRisesFallsAndRises(self):
        candles = _candles(
            [
                (10, 9, 9.5),
                (11, 10, 10.5),
                (12, 11, 11.5),
                (12, 10, 10.5),
                (11, 9, 9.5),
                (11, 9, 9.5),
                (12, 10, 11.5),
            ]
        )

        pivots = find_pivots(candles, atr_value=1.0, deviation=1.0)

        confirmed = [pivot for pivot in pivots if pivot.confirmed]
        self.assertEqual([pivot.kind for pivot in confirmed], ["high", "low"])
        self.assertEqual([pivot.price for pivot in confirmed], [12.0, 9.0])
        self.assertEqual([pivot.index for pivot in confirmed], [2, 4])
        self.assertEqual(
            [pivot.date for pivot in confirmed],
            [candles[2].date, candles[4].date],
        )
        self.assertEqual(
            [pivot.index for pivot in pivots],
            sorted(pivot.index for pivot in pivots),
        )

    def test_findPivotsReturnsSingleUnconfirmedHighWhenSeriesOnlyRises(self):
        candles = _candles(
            [
                (10, 9, 9.5),
                (11, 10, 10.5),
                (12, 11, 11.5),
            ]
        )

        pivots = find_pivots(candles, atr_value=1.0, deviation=1.0)

        self.assertEqual(len(pivots), 1)
        pivot = pivots[0]
        self.assertEqual(pivot.kind, "high")
        self.assertEqual(pivot.price, 12.0)
        self.assertEqual(pivot.index, 2)
        self.assertFalse(pivot.confirmed)

    def test_findPivotsDoesNotConfirmPivotWhenRetraceIsSmallerThanThreshold(self):
        candles = _candles(
            [
                (10, 9, 9.5),
                (12, 11, 11.5),
                (12.5, 11.5, 12.0),
            ]
        )

        pivots = find_pivots(candles, atr_value=10.0, deviation=1.0)

        self.assertEqual([pivot for pivot in pivots if pivot.confirmed], [])
        self.assertEqual(len(pivots), 1)
        self.assertEqual(pivots[0].kind, "high")
        self.assertFalse(pivots[0].confirmed)

    def test_findPivotsReturnsEmptyListWhenInputIsEmpty(self):
        self.assertEqual(find_pivots([], atr_value=1.0, deviation=1.0), [])

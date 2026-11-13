from datetime import date, timedelta
from decimal import Decimal

from django.test import TestCase

from detection.pivots import atr, find_pivots
from detection.services import score_formation
from marketdata.providers import Candle
from marketdata.services import PriceSeries


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


def _series(
    legs,
    *,
    start=104.0,
    spread=0.5,
    start_date=date(2024, 1, 1),
):
    closes = []
    price = start
    for bars, step in legs:
        for _ in range(bars):
            price += step
            closes.append(price)
    candles = []
    previous = start
    for offset, close in enumerate(closes):
        candles.append(
            Candle(
                date=start_date + timedelta(days=offset),
                open=Decimal(str(round(previous, 4))),
                high=Decimal(str(round(close + spread, 4))),
                low=Decimal(str(round(close - spread, 4))),
                close=Decimal(str(round(close, 4))),
                volume=None,
            )
        )
        previous = close
    return tuple(candles)


def _price_series(candles, *, status="ok"):
    return PriceSeries(symbol="AAPL", candles=candles, status=status)


FORMING_DOUBLE_TOP_LEGS = (
    (10, -0.4),
    (20, 1.0),
    (20, -0.6),
    (20, 0.6),
    (5, 0.0),
)

CONFIRMED_DOUBLE_TOP_LEGS = (
    (10, -0.4),
    (20, 1.0),
    (20, -0.6),
    (20, 0.6),
    (12, -1.2),
)

HEAD_SHOULDERS_LEGS = (
    (20, 1.0),
    (15, -0.8),
    (20, 1.2),
    (16, -1.25),
    (9, 1.0),
    (4, -0.1),
)

REJECTED_SECOND_PEAK_LEGS = (
    (10, -0.4),
    (20, 1.0),
    (20, -0.6),
    (20, 1.05),
    (5, -0.2),
)


class ScoreFormationTests(TestCase):
    def test_scoreFormationReturnsFormingDoubleTopWhenSecondPeakStallsAtFirstPeak(self):
        result = score_formation(_price_series(_series(FORMING_DOUBLE_TOP_LEGS)))

        self.assertEqual(result.pattern, "double_top")
        self.assertEqual(result.stage, "forming")
        self.assertIn(result.grade, ("medium", "high"))
        self.assertGreaterEqual(result.score, 0.45)
        self.assertIsNotNone(result.evidence)

    def test_scoreFormationReturnsConfirmedDoubleTopWhenPriceBreaksTheTrough(self):
        result = score_formation(_price_series(_series(CONFIRMED_DOUBLE_TOP_LEGS)))

        self.assertEqual(result.pattern, "double_top")
        self.assertEqual(result.stage, "confirmed")
        self.assertEqual(result.grade, "high")
        self.assertIsNotNone(result.evidence)

    def test_scoreFormationReturnsFormingHeadShouldersWhenRightShoulderMatchesLeft(self):
        result = score_formation(_price_series(_series(HEAD_SHOULDERS_LEGS)))

        self.assertEqual(result.pattern, "head_shoulders")
        self.assertEqual(result.stage, "forming")
        self.assertIn(result.grade, ("medium", "high"))
        self.assertIsNotNone(result.evidence)

    def test_scoreFormationReturnsNoFormationWhenSeriesIsSteadyUptrend(self):
        result = score_formation(_price_series(_series(((70, 0.5),), start=100.0)))

        self.assertEqual(result.pattern, "none")
        self.assertEqual(result.stage, "none")
        self.assertEqual(result.grade, "none")
        self.assertEqual(result.score, 0.0)
        self.assertIsNone(result.evidence)

    def test_scoreFormationReturnsNoFormationWhenSecondPeakExceedsTolerance(self):
        result = score_formation(
            _price_series(_series(REJECTED_SECOND_PEAK_LEGS))
        )

        self.assertEqual(result.pattern, "none")
        self.assertEqual(result.grade, "none")
        self.assertIsNone(result.evidence)

    def test_scoreFormationReturnsNoFormationWhenSeriesIsShorterThanMinimumBars(self):
        result = score_formation(
            _price_series(_series(((40, 0.5),), start=100.0))
        )

        self.assertEqual(result.pattern, "none")
        self.assertEqual(result.stage, "none")
        self.assertEqual(result.grade, "none")
        self.assertEqual(result.score, 0.0)
        self.assertIsNone(result.evidence)

    def test_scoreFormationReturnsNoFormationWhenCandlesAreEmpty(self):
        result = score_formation(_price_series(()))

        self.assertEqual(result.grade, "none")
        self.assertIsNone(result.evidence)

    def test_scoreFormationReturnsFormingPatternWhenSeriesIsStale(self):
        candles = _series(FORMING_DOUBLE_TOP_LEGS)

        result = score_formation(_price_series(candles, status="stale"))

        self.assertEqual(result.pattern, "double_top")
        self.assertEqual(result.stage, "forming")
        self.assertNotEqual(result.grade, "none")

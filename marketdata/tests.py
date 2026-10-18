from datetime import date, datetime, time
from decimal import Decimal
from zoneinfo import ZoneInfo

import httpx
from django.test import TestCase

from marketdata.providers import ProviderError
from marketdata.providers import twelvedata

EASTERN = ZoneInfo("America/New_York")
API_KEY = "test-api-key"


def _value(day, *, volume="1000000"):
    value = {
        "datetime": day,
        "open": "100.5",
        "high": "110.25",
        "low": "90.75",
        "close": "105.0",
    }
    if volume is not None:
        value["volume"] = volume
    return value


def _payload(values):
    return {
        "meta": {"symbol": "AAPL", "interval": "1day"},
        "values": values,
        "status": "ok",
    }


def _fetch(payload, *, status_code=200, now_ny=None):
    captured = []

    def handler(request):
        captured.append(request)
        return httpx.Response(status_code, json=payload)

    candles = twelvedata.fetch_daily(
        "AAPL",
        bars=500,
        timeout=5.0,
        api_key=API_KEY,
        transport=httpx.MockTransport(handler),
        now_ny=now_ny or datetime(2024, 1, 5, 12, 0, tzinfo=EASTERN),
    )
    return candles, captured


class TwelveDataAdapterTests(TestCase):
    def test_fetchReturnsAscendingDecimalCandlesAndDocumentedRequestWhenResponseIsValid(self):
        payload = _payload([_value("2024-01-02"), _value("2024-01-03")])

        candles, captured = _fetch(payload)

        self.assertEqual(
            [candle.date for candle in candles],
            [date(2024, 1, 2), date(2024, 1, 3)],
        )
        self.assertEqual(
            (candles[0].open, candles[0].high, candles[0].low, candles[0].close),
            (Decimal("100.5"), Decimal("110.25"), Decimal("90.75"), Decimal("105.0")),
        )
        self.assertIsInstance(candles[0].close, Decimal)
        self.assertEqual(candles[0].volume, 1000000)

        request = captured[0]
        self.assertEqual(request.url.path, "/time_series")
        self.assertEqual(
            dict(request.url.params),
            {
                "symbol": "AAPL",
                "interval": "1day",
                "outputsize": "500",
                "order": "asc",
                "adjust": "all",
            },
        )
        self.assertEqual(request.headers["authorization"], f"apikey {API_KEY}")
        self.assertNotIn(API_KEY, str(request.url))

    def test_fetchReturnsAscendingCandlesWhenProviderSendsNewestFirst(self):
        payload = _payload(
            [_value("2024-01-05"), _value("2024-01-03"), _value("2024-01-04")]
        )

        candles, _ = _fetch(
            payload, now_ny=datetime(2024, 1, 8, 12, 0, tzinfo=EASTERN)
        )

        self.assertEqual(
            [candle.date for candle in candles],
            [date(2024, 1, 3), date(2024, 1, 4), date(2024, 1, 5)],
        )

    def test_fetchDropsTodaysNewYorkBarWhenBeforeSessionClose(self):
        payload = _payload([_value("2024-01-04"), _value("2024-01-05")])

        candles, _ = _fetch(
            payload, now_ny=datetime(2024, 1, 5, 15, 59, tzinfo=EASTERN)
        )

        self.assertEqual([candle.date for candle in candles], [date(2024, 1, 4)])

    def test_fetchKeepsTodaysNewYorkBarWhenAtOrAfterSessionClose(self):
        payload = _payload([_value("2024-01-04"), _value("2024-01-05")])

        for close_time in (time(16, 0), time(17, 30)):
            with self.subTest(close_time=close_time):
                candles, _ = _fetch(
                    payload,
                    now_ny=datetime.combine(
                        date(2024, 1, 5), close_time, tzinfo=EASTERN
                    ),
                )
                self.assertEqual(
                    [candle.date for candle in candles],
                    [date(2024, 1, 4), date(2024, 1, 5)],
                )

    def test_fetchReturnsNoneVolumeWhenVolumeIsAbsentOrBlank(self):
        payload = _payload(
            [_value("2024-01-02", volume=None), _value("2024-01-03", volume="   ")]
        )

        candles, _ = _fetch(payload)

        self.assertIsNone(candles[0].volume)
        self.assertIsNone(candles[1].volume)

    def test_fetchRaisesMappedProviderErrorWhenProviderReturnsErrorCode(self):
        cases = [
            (400, "provider_error"),
            (401, "auth_failed"),
            (403, "auth_failed"),
            (404, "symbol_not_found"),
            (429, "rate_limited"),
            (500, "provider_error"),
        ]
        for status_code, expected_reason in cases:
            with self.subTest(status_code=status_code):
                payload = {
                    "code": status_code,
                    "message": "Provider failure",
                    "status": "error",
                }
                with self.assertRaises(ProviderError) as context:
                    _fetch(payload, status_code=status_code)
                self.assertEqual(context.exception.reason, expected_reason)

    def test_fetchRaisesMappedProviderErrorWhenHttpStatusFailsWithoutCode(self):
        payload = {"status": "error", "message": "Too many requests"}

        with self.assertRaises(ProviderError) as context:
            _fetch(payload, status_code=429)

        self.assertEqual(context.exception.reason, "rate_limited")

    def test_fetchRaisesProviderErrorWhenNetworkFails(self):
        errors = [httpx.ConnectError("connection refused"), httpx.ReadTimeout("timed out")]
        for error in errors:
            with self.subTest(error=type(error).__name__):

                def handler(request, error=error):
                    raise error

                with self.assertRaises(ProviderError) as context:
                    twelvedata.fetch_daily(
                        "AAPL",
                        bars=500,
                        timeout=5.0,
                        api_key=API_KEY,
                        transport=httpx.MockTransport(handler),
                    )
                self.assertEqual(context.exception.reason, "provider_error")

    def test_fetchRaisesInvalidResponseWhenBodyIsNotJson(self):
        def handler(request):
            return httpx.Response(200, text="<html>rate limited</html>")

        with self.assertRaises(ProviderError) as context:
            twelvedata.fetch_daily(
                "AAPL",
                bars=500,
                timeout=5.0,
                api_key=API_KEY,
                transport=httpx.MockTransport(handler),
            )

        self.assertEqual(context.exception.reason, "invalid_response")

    def test_fetchRaisesInvalidResponseWhenValuesAreStructurallyInvalid(self):
        payload = _payload(
            [
                {
                    "datetime": "not-a-date",
                    "open": "1",
                    "high": "1",
                    "low": "1",
                    "close": "1",
                }
            ]
        )

        with self.assertRaises(ProviderError) as context:
            _fetch(payload)

        self.assertEqual(context.exception.reason, "invalid_response")

    def test_fetchRaisesNoDataWhenValuesArrayIsEmpty(self):
        payload = _payload([])

        with self.assertRaises(ProviderError) as context:
            _fetch(payload)

        self.assertEqual(context.exception.reason, "no_data")

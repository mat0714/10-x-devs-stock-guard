from datetime import date, datetime, time, timedelta
from decimal import Decimal
import io
from unittest.mock import patch
from zoneinfo import ZoneInfo

import httpx
from django.core.management import call_command
from django.test import TestCase

from marketdata.models import DailyCandle
from marketdata.providers import Candle, ProviderError
from marketdata.providers import twelvedata
from marketdata.services import PriceSeries, PriceUnavailable, fetch_daily_candles

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

    def test_fetchRaisesMappedReasonWhenHttpStatusFailsWithNonJsonBody(self):
        cases = [
            (404, "symbol_not_found"),
            (429, "rate_limited"),
            (500, "provider_error"),
        ]
        for status_code, expected_reason in cases:
            with self.subTest(status_code=status_code):

                def handler(request, status_code=status_code):
                    return httpx.Response(status_code, text="<html>rate limited</html>")

                with self.assertRaises(ProviderError) as context:
                    twelvedata.fetch_daily(
                        "AAPL",
                        bars=500,
                        timeout=5.0,
                        api_key=API_KEY,
                        transport=httpx.MockTransport(handler),
                    )
                self.assertEqual(context.exception.reason, expected_reason)

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

    def test_fetchSkipsMalformedRowsWhenOtherRowsAreValid(self):
        payload = _payload(
            [
                _value("2024-01-02"),
                {
                    "datetime": "not-a-date",
                    "open": "1",
                    "high": "1",
                    "low": "1",
                    "close": "1",
                },
                _value("2024-01-03"),
            ]
        )

        candles, _ = _fetch(payload)

        self.assertEqual(
            [candle.date for candle in candles],
            [date(2024, 1, 2), date(2024, 1, 3)],
        )

    def test_fetchRaisesNoDataWhenValuesArrayIsEmpty(self):
        payload = _payload([])

        with self.assertRaises(ProviderError) as context:
            _fetch(payload)

        self.assertEqual(context.exception.reason, "no_data")


def _service_candle(day, *, close="1.000000", volume=1000000):
    return Candle(
        date=day,
        open=Decimal("100.500000"),
        high=Decimal("110.250000"),
        low=Decimal("90.750000"),
        close=Decimal(close),
        volume=volume,
    )


def _service_candles(count, *, last_day=date(2024, 3, 1)):
    first_day = last_day - timedelta(days=count - 1)
    return [
        _service_candle(first_day + timedelta(days=offset)) for offset in range(count)
    ]


def _seed_rows(symbol, candles, *, fetched_at):
    DailyCandle.objects.bulk_create(
        [
            DailyCandle(
                symbol=symbol,
                date=candle.date,
                open=candle.open,
                high=candle.high,
                low=candle.low,
                close=candle.close,
                volume=candle.volume,
                fetched_at=fetched_at,
            )
            for candle in candles
        ]
    )


def _stored_dates(symbol):
    return list(
        DailyCandle.objects.filter(symbol=symbol)
        .order_by("date")
        .values_list("date", flat=True)
    )


class FetchServiceTests(TestCase):
    def test_fetchReturnsCachedSeriesWithoutProviderCallWhenNewestFetchIsAfterLastClose(self):
        now = datetime(2024, 1, 8, 18, 0, tzinfo=EASTERN)
        _seed_rows(
            "AAPL",
            _service_candles(2, last_day=date(2024, 1, 5)),
            fetched_at=datetime(2024, 1, 8, 17, 0, tzinfo=EASTERN),
        )

        with self.settings(TWELVE_DATA_API_KEY=API_KEY):
            with patch("django.utils.timezone.now", return_value=now):
                with patch("marketdata.services.twelvedata.fetch_daily") as fetch:
                    result = fetch_daily_candles(" aapl ")

        self.assertIsInstance(result, PriceSeries)
        self.assertEqual(result.symbol, "AAPL")
        self.assertEqual(result.status, "ok")
        self.assertEqual(result.reason, "cached")
        self.assertEqual(
            [candle.date for candle in result.candles],
            [date(2024, 1, 4), date(2024, 1, 5)],
        )
        fetch.assert_not_called()

    def test_fetchRefetchesOnceWhenNewestFetchIsBeforeLastCloseOnSameUtcDay(self):
        now = datetime(2024, 1, 8, 18, 0, tzinfo=EASTERN)
        _seed_rows(
            "AAPL",
            _service_candles(1, last_day=date(2024, 1, 5)),
            fetched_at=datetime(2024, 1, 8, 10, 0, tzinfo=EASTERN),
        )
        fetched = _service_candles(2, last_day=date(2024, 1, 8))

        with self.settings(TWELVE_DATA_API_KEY=API_KEY):
            with patch("django.utils.timezone.now", return_value=now):
                with patch(
                    "marketdata.services.twelvedata.fetch_daily",
                    return_value=fetched,
                ) as fetch:
                    result = fetch_daily_candles("AAPL")

        self.assertEqual(fetch.call_count, 1)
        self.assertEqual(result.status, "ok")
        self.assertIsNone(result.reason)
        self.assertEqual(
            _stored_dates("AAPL"),
            [date(2024, 1, 5), date(2024, 1, 7), date(2024, 1, 8)],
        )

    def test_fetchCallsProviderOnceAndStoresRowsWhenNothingIsStored(self):
        now = datetime(2024, 1, 8, 18, 0, tzinfo=EASTERN)
        fetched = _service_candles(3, last_day=date(2024, 1, 5))

        with self.settings(TWELVE_DATA_API_KEY=API_KEY):
            with patch("django.utils.timezone.now", return_value=now):
                with patch(
                    "marketdata.services.twelvedata.fetch_daily",
                    return_value=fetched,
                ) as fetch:
                    result = fetch_daily_candles("AAPL")

        self.assertEqual(fetch.call_count, 1)
        self.assertEqual(fetch.call_args.kwargs["bars"], 500)
        self.assertIsInstance(result, PriceSeries)
        self.assertEqual(result.status, "ok")
        self.assertIsNone(result.reason)
        self.assertEqual(
            _stored_dates("AAPL"),
            [date(2024, 1, 3), date(2024, 1, 4), date(2024, 1, 5)],
        )

    def test_fetchRefetchesWhenNewestFetchIsFromAPreviousSession(self):
        now = datetime(2024, 1, 8, 18, 0, tzinfo=EASTERN)
        _seed_rows(
            "AAPL",
            _service_candles(2, last_day=date(2024, 1, 5)),
            fetched_at=datetime(2024, 1, 5, 17, 0, tzinfo=EASTERN),
        )
        fetched = _service_candles(3, last_day=date(2024, 1, 8))

        with self.settings(TWELVE_DATA_API_KEY=API_KEY):
            with patch("django.utils.timezone.now", return_value=now):
                with patch(
                    "marketdata.services.twelvedata.fetch_daily",
                    return_value=fetched,
                ) as fetch:
                    result = fetch_daily_candles("AAPL")

        self.assertEqual(fetch.call_count, 1)
        self.assertEqual(result.status, "ok")
        self.assertEqual(
            _stored_dates("AAPL"),
            [
                date(2024, 1, 4),
                date(2024, 1, 5),
                date(2024, 1, 6),
                date(2024, 1, 7),
                date(2024, 1, 8),
            ],
        )

    def test_fetchUpdatesOverlappingDatesInPlaceAndKeepsRowCount(self):
        now = datetime(2024, 1, 8, 18, 0, tzinfo=EASTERN)
        _seed_rows(
            "AAPL",
            [
                _service_candle(date(2024, 1, 4), close="1.000000"),
                _service_candle(date(2024, 1, 5), close="1.000000"),
            ],
            fetched_at=datetime(2024, 1, 5, 17, 0, tzinfo=EASTERN),
        )
        fetched = [
            _service_candle(date(2024, 1, 5), close="2.000000"),
            _service_candle(date(2024, 1, 8), close="2.000000"),
        ]

        with self.settings(TWELVE_DATA_API_KEY=API_KEY):
            with patch("django.utils.timezone.now", return_value=now):
                with patch(
                    "marketdata.services.twelvedata.fetch_daily",
                    return_value=fetched,
                ):
                    fetch_daily_candles("AAPL")

        rows = list(
            DailyCandle.objects.filter(symbol="AAPL")
            .order_by("date")
            .values_list("date", "close")
        )
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[1], (date(2024, 1, 5), Decimal("2.000000")))

    def test_fetchPrunesToLookbackAndKeepsNewestWhenProviderReturnsMoreBars(self):
        now = datetime(2024, 1, 8, 18, 0, tzinfo=EASTERN)
        fetched = _service_candles(520, last_day=date(2024, 3, 1))

        with self.settings(TWELVE_DATA_API_KEY=API_KEY):
            with patch("django.utils.timezone.now", return_value=now):
                with patch(
                    "marketdata.services.twelvedata.fetch_daily",
                    return_value=fetched,
                ):
                    fetch_daily_candles("AAPL", bars=500)

        stored = _stored_dates("AAPL")
        self.assertEqual(len(stored), 500)
        self.assertEqual(stored[-1], date(2024, 3, 1))
        self.assertEqual(stored[0], date(2024, 3, 1) - timedelta(days=499))

    def test_fetchKeepsConfiguredCacheWindowWhenBarsOverrideIsSmaller(self):
        now = datetime(2024, 1, 8, 18, 0, tzinfo=EASTERN)
        fetched = _service_candles(520, last_day=date(2024, 3, 1))

        with self.settings(TWELVE_DATA_API_KEY=API_KEY):
            with patch("django.utils.timezone.now", return_value=now):
                with patch(
                    "marketdata.services.twelvedata.fetch_daily",
                    return_value=fetched,
                ) as fetch:
                    fetch_daily_candles("AAPL", bars=200)

        self.assertEqual(fetch.call_args.kwargs["bars"], 200)
        stored = _stored_dates("AAPL")
        self.assertEqual(len(stored), 500)
        self.assertEqual(stored[-1], date(2024, 3, 1))
        self.assertEqual(stored[0], date(2024, 3, 1) - timedelta(days=499))

    def test_fetchReturnsInvalidSymbolWithoutProviderCallWhenBarsIsNotPositive(self):
        for bars in (0, -1):
            with self.subTest(bars=bars):
                with self.settings(TWELVE_DATA_API_KEY=API_KEY):
                    with patch(
                        "marketdata.services.twelvedata.fetch_daily"
                    ) as fetch:
                        result = fetch_daily_candles("AAPL", bars=bars)

                self.assertIsInstance(result, PriceUnavailable)
                self.assertEqual(result.reason, "invalid_symbol")
                fetch.assert_not_called()

    def test_fetchReturnsStaleWithReasonWhenProviderFailsAndRowsAreStored(self):
        now = datetime(2024, 1, 8, 18, 0, tzinfo=EASTERN)
        _seed_rows(
            "AAPL",
            _service_candles(1, last_day=date(2024, 1, 5)),
            fetched_at=datetime(2024, 1, 5, 17, 0, tzinfo=EASTERN),
        )

        with self.settings(TWELVE_DATA_API_KEY=API_KEY):
            with patch("django.utils.timezone.now", return_value=now):
                with patch(
                    "marketdata.services.twelvedata.fetch_daily",
                    side_effect=ProviderError("rate_limited", "slow down"),
                ):
                    result = fetch_daily_candles("AAPL")

        self.assertIsInstance(result, PriceSeries)
        self.assertEqual(result.status, "stale")
        self.assertEqual(result.reason, "rate_limited")
        self.assertEqual(result.message, "slow down")
        self.assertEqual([candle.date for candle in result.candles], [date(2024, 1, 5)])
        self.assertEqual(_stored_dates("AAPL"), [date(2024, 1, 5)])

    def test_fetchReturnsUnavailableWhenProviderFailsAndNoRowsAreStored(self):
        now = datetime(2024, 1, 8, 18, 0, tzinfo=EASTERN)

        with self.settings(TWELVE_DATA_API_KEY=API_KEY):
            with patch("django.utils.timezone.now", return_value=now):
                with patch(
                    "marketdata.services.twelvedata.fetch_daily",
                    side_effect=ProviderError("symbol_not_found", "unknown symbol"),
                ):
                    result = fetch_daily_candles("NOPE")

        self.assertIsInstance(result, PriceUnavailable)
        self.assertEqual(result.symbol, "NOPE")
        self.assertEqual(result.reason, "symbol_not_found")
        self.assertEqual(result.message, "unknown symbol")

    def test_fetchReturnsNotConfiguredWhenApiKeyIsEmptyAndNoRowsAreStored(self):
        now = datetime(2024, 1, 8, 18, 0, tzinfo=EASTERN)

        with self.settings(TWELVE_DATA_API_KEY=""):
            with patch("django.utils.timezone.now", return_value=now):
                with patch("marketdata.services.twelvedata.fetch_daily") as fetch:
                    result = fetch_daily_candles("AAPL")

        self.assertIsInstance(result, PriceUnavailable)
        self.assertEqual(result.reason, "not_configured")
        fetch.assert_not_called()

    def test_fetchReturnsStaleNotConfiguredWhenApiKeyIsEmptyAndRowsAreStored(self):
        now = datetime(2024, 1, 8, 18, 0, tzinfo=EASTERN)
        _seed_rows(
            "AAPL",
            _service_candles(1, last_day=date(2024, 1, 5)),
            fetched_at=datetime(2024, 1, 5, 17, 0, tzinfo=EASTERN),
        )

        with self.settings(TWELVE_DATA_API_KEY=""):
            with patch("django.utils.timezone.now", return_value=now):
                result = fetch_daily_candles("AAPL")

        self.assertIsInstance(result, PriceSeries)
        self.assertEqual(result.status, "stale")
        self.assertEqual(result.reason, "not_configured")
        self.assertEqual([candle.date for candle in result.candles], [date(2024, 1, 5)])

    def test_fetchReturnsInvalidSymbolWithoutProviderCallWhenSymbolIsBlank(self):
        for symbol in ("", "   "):
            with self.subTest(symbol=symbol):
                with self.settings(TWELVE_DATA_API_KEY=API_KEY):
                    with patch(
                        "marketdata.services.twelvedata.fetch_daily"
                    ) as fetch:
                        result = fetch_daily_candles(symbol)

                self.assertIsInstance(result, PriceUnavailable)
                self.assertEqual(result.reason, "invalid_symbol")
                fetch.assert_not_called()

    def test_fetchReturnsResultForEveryMappedProviderReason(self):
        now = datetime(2024, 1, 8, 18, 0, tzinfo=EASTERN)
        reasons = [
            "auth_failed",
            "symbol_not_found",
            "rate_limited",
            "provider_error",
            "invalid_response",
            "no_data",
        ]

        for reason in reasons:
            with self.subTest(reason=reason):
                with self.settings(TWELVE_DATA_API_KEY=API_KEY):
                    with patch("django.utils.timezone.now", return_value=now):
                        with patch(
                            "marketdata.services.twelvedata.fetch_daily",
                            side_effect=ProviderError(reason, "boom"),
                        ):
                            result = fetch_daily_candles("AAPL")

                self.assertIsInstance(result, PriceUnavailable)
                self.assertEqual(result.reason, reason)
                self.assertEqual(result.message, "boom")

    def test_fetchReturnsTypedResultWhenProviderRaisesUnexpectedError(self):
        now = datetime(2024, 1, 8, 18, 0, tzinfo=EASTERN)

        with self.settings(TWELVE_DATA_API_KEY=API_KEY):
            with patch("django.utils.timezone.now", return_value=now):
                with patch(
                    "marketdata.services.twelvedata.fetch_daily",
                    side_effect=RuntimeError("boom"),
                ):
                    result = fetch_daily_candles("AAPL")

        self.assertIsInstance(result, PriceUnavailable)
        self.assertEqual(result.reason, "provider_error")

    def test_fetchReturnsTypedResultWhenPersistenceFails(self):
        now = datetime(2024, 1, 8, 18, 0, tzinfo=EASTERN)
        fetched = _service_candles(2, last_day=date(2024, 1, 5))

        with self.settings(TWELVE_DATA_API_KEY=API_KEY):
            with patch("django.utils.timezone.now", return_value=now):
                with patch(
                    "marketdata.services.twelvedata.fetch_daily",
                    return_value=fetched,
                ):
                    with patch(
                        "marketdata.services._store",
                        side_effect=RuntimeError("db down"),
                    ):
                        result = fetch_daily_candles("AAPL")

        self.assertIsInstance(result, PriceUnavailable)
        self.assertEqual(result.reason, "provider_error")


class FetchCandlesCommandTests(TestCase):
    def test_fetchCandlesCommandReturnsOkStatusAndCountWhenFetchSucceeds(self):
        _seed_rows(
            "AAPL",
            _service_candles(3, last_day=date(2024, 3, 1)),
            fetched_at=datetime(2024, 3, 1, 17, 0, tzinfo=EASTERN),
        )
        series = PriceSeries(
            symbol="AAPL",
            candles=tuple(_service_candles(3, last_day=date(2024, 3, 1))),
            status="ok",
        )
        stdout = io.StringIO()

        with patch(
            "marketdata.management.commands.fetch_candles.fetch_daily_candles",
            return_value=series,
        ):
            call_command("fetch_candles", "AAPL", stdout=stdout)

        output = stdout.getvalue()
        self.assertIn("status=ok", output)
        self.assertIn("candles=3", output)
        self.assertIn("stored=3", output)

    def test_fetchCandlesCommandReturnsUnavailableReasonWhenSymbolIsNotFound(self):
        result = PriceUnavailable(symbol="NOPE", reason="symbol_not_found")
        stdout = io.StringIO()

        with patch(
            "marketdata.management.commands.fetch_candles.fetch_daily_candles",
            return_value=result,
        ):
            call_command("fetch_candles", "NOPE", stdout=stdout)

        self.assertIn("status=unavailable reason=symbol_not_found", stdout.getvalue())

    def test_fetchCandlesCommandOmitsProviderMessageWhenUnavailable(self):
        result = PriceUnavailable(
            symbol="NOPE",
            reason="symbol_not_found",
            message="<b>untrusted provider text</b>",
        )
        stdout = io.StringIO()

        with patch(
            "marketdata.management.commands.fetch_candles.fetch_daily_candles",
            return_value=result,
        ):
            call_command("fetch_candles", "NOPE", stdout=stdout)

        self.assertNotIn("<b>untrusted provider text</b>", stdout.getvalue())

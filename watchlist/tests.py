import time
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth.models import User
from django.test import TestCase

from detection.services import FormationScore
from marketdata.services import PriceSeries, PriceUnavailable

from .models import WatchlistItem
from .services import MAX_SCAN_WORKERS, Row, scan_watchlist

PASSWORD = "S3cure-Passw0rd!x"


class AddWatchlistItemTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="marek@example.com",
            email="marek@example.com",
            password=PASSWORD,
        )
        self.client.login(username="marek@example.com", password=PASSWORD)
        self.fetch_patcher = patch("watchlist.services.fetch_daily_candles")
        self.fetch = self.fetch_patcher.start()
        self.addCleanup(self.fetch_patcher.stop)
        self.fetch.return_value = PriceUnavailable(
            symbol="AAPL", reason="not_configured"
        )

    def test_addReturnsNormalizedSymbolWhenSymbolHasMixedCaseAndSpaces(self):
        self.client.post("/", {"symbol": "  aapl  ", "name": ""})

        item = WatchlistItem.objects.get()
        self.assertEqual(item.symbol, "AAPL")
        self.assertEqual(item.user, self.user)

    def test_addReturnsFormErrorAndNoSecondRowWhenSymbolAlreadyExists(self):
        WatchlistItem.objects.create(user=self.user, symbol="AAPL")

        response = self.client.post("/", {"symbol": "aapl", "name": ""})

        self.assertEqual(response.status_code, 200)
        self.assertIn("symbol", response.context["form"].errors)
        self.assertEqual(WatchlistItem.objects.count(), 1)

    def test_addReturnsFormErrorWhenSymbolFormatIsInvalid(self):
        response = self.client.post("/", {"symbol": "1BAD!", "name": ""})

        self.assertEqual(response.status_code, 200)
        self.assertIn("symbol", response.context["form"].errors)
        self.assertEqual(WatchlistItem.objects.count(), 0)

    def test_addReturnsTickerOnlyWhenNameIsBlank(self):
        response = self.client.post("/", {"symbol": "AAPL", "name": ""})

        self.assertRedirects(response, "/")
        list_response = self.client.get("/")
        self.assertContains(list_response, "AAPL")
        self.assertNotContains(list_response, "AAPL (")

    def test_homeReturnsLoginRedirectWhenVisitorIsAnonymous(self):
        self.client.logout()

        response = self.client.get("/")

        self.assertRedirects(response, "/login/?next=/")


class WatchlistListTests(TestCase):
    def setUp(self):
        self.alice = User.objects.create_user(
            username="alice@example.com",
            email="alice@example.com",
            password=PASSWORD,
        )
        self.bob = User.objects.create_user(
            username="bob@example.com",
            email="bob@example.com",
            password=PASSWORD,
        )
        self.fetch_patcher = patch("watchlist.services.fetch_daily_candles")
        self.fetch = self.fetch_patcher.start()
        self.addCleanup(self.fetch_patcher.stop)
        self.fetch.return_value = PriceUnavailable(
            symbol="AAPL", reason="not_configured"
        )

    def test_listReturnsOnlyOwnRowsWhenAnotherUserHasItems(self):
        WatchlistItem.objects.create(user=self.alice, symbol="AAPL")
        WatchlistItem.objects.create(user=self.bob, symbol="MSFT")
        self.client.login(username="alice@example.com", password=PASSWORD)

        response = self.client.get("/")

        self.assertContains(response, "AAPL")
        self.assertNotContains(response, "MSFT")
        self.assertEqual(
            list(response.context["items"]),
            list(WatchlistItem.objects.filter(user=self.alice)),
        )

    def test_listReturnsItemsOrderedAlphabeticallyWhenMultipleExist(self):
        WatchlistItem.objects.create(user=self.alice, symbol="MSFT")
        WatchlistItem.objects.create(user=self.alice, symbol="AAPL")
        self.client.login(username="alice@example.com", password=PASSWORD)

        response = self.client.get("/")

        self.assertEqual(
            [item.symbol for item in response.context["items"]],
            ["AAPL", "MSFT"],
        )


class RemoveWatchlistItemTests(TestCase):
    def setUp(self):
        self.alice = User.objects.create_user(
            username="alice@example.com",
            email="alice@example.com",
            password=PASSWORD,
        )
        self.bob = User.objects.create_user(
            username="bob@example.com",
            email="bob@example.com",
            password=PASSWORD,
        )
        self.fetch_patcher = patch("watchlist.services.fetch_daily_candles")
        self.fetch = self.fetch_patcher.start()
        self.addCleanup(self.fetch_patcher.stop)
        self.fetch.return_value = PriceUnavailable(
            symbol="AAPL", reason="not_configured"
        )

    def test_removeReturnsRedirectToHomeAndDeletesRowWhenPostedAuthenticated(self):
        item = WatchlistItem.objects.create(user=self.alice, symbol="AAPL")
        self.client.login(username="alice@example.com", password=PASSWORD)

        response = self.client.post(f"/watchlist/{item.pk}/delete/")

        self.assertRedirects(response, "/")
        self.assertFalse(WatchlistItem.objects.filter(pk=item.pk).exists())

    def test_removeReturnsMethodNotAllowedWhenRequestedWithGet(self):
        item = WatchlistItem.objects.create(user=self.alice, symbol="AAPL")
        self.client.login(username="alice@example.com", password=PASSWORD)

        response = self.client.get(f"/watchlist/{item.pk}/delete/")

        self.assertEqual(response.status_code, 405)

    def test_removeReturnsNotFoundAndKeepsRowWhenRowBelongsToAnotherUser(self):
        item = WatchlistItem.objects.create(user=self.bob, symbol="AAPL")
        self.client.login(username="alice@example.com", password=PASSWORD)

        response = self.client.post(f"/watchlist/{item.pk}/delete/")

        self.assertEqual(response.status_code, 404)
        self.assertTrue(WatchlistItem.objects.filter(pk=item.pk).exists())


class RowRenderingTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="alice@example.com",
            email="alice@example.com",
            password=PASSWORD,
        )
        WatchlistItem.objects.create(user=self.user, symbol="AAPL")
        self.client.login(username="alice@example.com", password=PASSWORD)

    def test_listReturnsGradeBadgeWhenScoreGradeIsHigh(self):
        with patch("watchlist.services.fetch_daily_candles") as fetch, patch(
            "watchlist.services.score_formation"
        ) as score:
            fetch.return_value = PriceSeries(
                symbol="AAPL", candles=(), status="ok"
            )
            score.return_value = FormationScore(
                pattern="double_top",
                stage="forming",
                grade="high",
                score=0.82,
                evidence=None,
            )

            response = self.client.get("/")

        self.assertContains(response, "badge")
        self.assertContains(response, "grade-high")

    def test_listReturnsConfirmedLabelWhenScoreStageIsConfirmed(self):
        with patch("watchlist.services.fetch_daily_candles") as fetch, patch(
            "watchlist.services.score_formation"
        ) as score:
            fetch.return_value = PriceSeries(
                symbol="AAPL", candles=(), status="ok"
            )
            score.return_value = FormationScore(
                pattern="double_top",
                stage="confirmed",
                grade="high",
                score=0.85,
                evidence=None,
            )

            response = self.client.get("/")

        self.assertContains(response, "confirmed")

    def test_listReturnsStaleMarkerWhenSeriesIsStale(self):
        with patch("watchlist.services.fetch_daily_candles") as fetch, patch(
            "watchlist.services.score_formation"
        ) as score:
            fetch.return_value = PriceSeries(
                symbol="AAPL", candles=(), status="stale"
            )
            score.return_value = FormationScore(
                pattern="double_top",
                stage="forming",
                grade="medium",
                score=0.5,
                evidence=None,
            )

            response = self.client.get("/")

        self.assertContains(response, "(stale)")

    def test_listReturnsMessageAndNoBadgeWhenPriceUnavailable(self):
        with patch("watchlist.services.fetch_daily_candles") as fetch:
            fetch.return_value = PriceUnavailable(
                symbol="AAPL", reason="rate_limited"
            )

            response = self.client.get("/")

        self.assertContains(response, "rate limited")
        self.assertNotContains(response, 'class="badge')

    def test_listReturnsNoBadgeWhenNoFormationDetected(self):
        with patch("watchlist.services.fetch_daily_candles") as fetch, patch(
            "watchlist.services.score_formation"
        ) as score:
            fetch.return_value = PriceSeries(
                symbol="AAPL", candles=(), status="ok"
            )
            score.return_value = FormationScore(
                pattern="none",
                stage="none",
                grade="none",
                score=0.0,
                evidence=None,
            )

            response = self.client.get("/")

        self.assertNotContains(response, 'class="badge')


class ScanWatchlistTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="alice@example.com",
            email="alice@example.com",
            password=PASSWORD,
        )

    def _items(self, *symbols):
        return [
            WatchlistItem.objects.create(user=self.user, symbol=symbol)
            for symbol in symbols
        ]

    def test_scanReturnsStillScanningRowWhenFetchOutlastsBudget(self):
        items = self._items("AAPL")

        def slow_fetch(symbol, *, timeout=None):
            time.sleep(0.2)
            return PriceUnavailable(symbol=symbol, reason="not_configured")

        with patch(
            "watchlist.services.fetch_daily_candles", side_effect=slow_fetch
        ):
            rows = scan_watchlist(items, max_workers=1, budget_seconds=0.05)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].item.pk, items[0].pk)
        self.assertEqual(rows[0].message, "still scanning")
        self.assertIsNone(rows[0].score)

    def test_scanReturnsRowForEveryItemInInputOrderWhenOneTaskRaises(self):
        items = self._items("AAPL", "MSFT", "GOOG")

        def flaky_fetch(symbol, *, timeout=None):
            if symbol == "MSFT":
                raise RuntimeError("boom")
            return PriceUnavailable(symbol=symbol, reason="not_configured")

        with patch(
            "watchlist.services.fetch_daily_candles", side_effect=flaky_fetch
        ):
            rows = scan_watchlist(items, max_workers=2, budget_seconds=5)

        self.assertEqual(len(rows), 3)
        self.assertTrue(all(isinstance(row, Row) for row in rows))
        self.assertEqual(
            [row.item.pk for row in rows], [item.pk for item in items]
        )
        self.assertEqual(rows[1].message, "analysis failed")

    def test_scanReturnsRateLimitedMessageWhenFetchReportsRateLimited(self):
        items = self._items("AAPL")

        with patch("watchlist.services.fetch_daily_candles") as fetch:
            fetch.return_value = PriceUnavailable(
                symbol="AAPL", reason="rate_limited"
            )

            rows = scan_watchlist(items, max_workers=1, budget_seconds=5)

        self.assertEqual(rows[0].message, "rate limited")
        self.assertIsNone(rows[0].score)
        self.assertFalse(rows[0].stale)

    def test_scanReturnsStaleRowWhenSeriesStatusIsStale(self):
        items = self._items("AAPL")

        with patch("watchlist.services.fetch_daily_candles") as fetch, patch(
            "watchlist.services.score_formation"
        ) as score:
            fetch.return_value = PriceSeries(
                symbol="AAPL", candles=(), status="stale"
            )
            score.return_value = FormationScore(
                pattern="double_top",
                stage="forming",
                grade="medium",
                score=0.5,
                evidence=None,
            )

            rows = scan_watchlist(items, max_workers=1, budget_seconds=5)

        self.assertTrue(rows[0].stale)
        self.assertEqual(rows[0].score, score.return_value)

    def test_scanReturnsRowsInInputOrderWhenFetchesCompleteOutOfOrder(self):
        items = self._items("TSLA", "AAPL", "GOOG", "MSFT")
        delays = {"TSLA": 0.06, "AAPL": 0.0, "GOOG": 0.03, "MSFT": 0.01}

        def delayed_fetch(symbol, *, timeout=None):
            time.sleep(delays[symbol])
            return PriceUnavailable(symbol=symbol, reason="not_configured")

        with patch(
            "watchlist.services.fetch_daily_candles", side_effect=delayed_fetch
        ):
            rows = scan_watchlist(items, max_workers=4, budget_seconds=5)

        self.assertEqual(
            [row.item.symbol for row in rows],
            ["TSLA", "AAPL", "GOOG", "MSFT"],
        )
        self.assertEqual(
            [row.item.pk for row in rows], [item.pk for item in items]
        )

    def test_scanReturnsAllRowsWhenMaxWorkersIsUnsetOrOversized(self):
        self.assertGreaterEqual(settings.WATCHLIST_SCAN_MAX_WORKERS, 1)
        self.assertLessEqual(
            settings.WATCHLIST_SCAN_MAX_WORKERS, MAX_SCAN_WORKERS
        )
        items = self._items("AAPL", "MSFT")

        with patch("watchlist.services.fetch_daily_candles") as fetch:
            fetch.return_value = PriceUnavailable(
                symbol="AAPL", reason="not_configured"
            )

            default_rows = scan_watchlist(items)
            oversized_rows = scan_watchlist(
                items, max_workers=1000, budget_seconds=5
            )

        self.assertEqual(len(default_rows), 2)
        self.assertEqual(len(oversized_rows), 2)

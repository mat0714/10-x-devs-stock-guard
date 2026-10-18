from typing import Any

from django.core.management.base import BaseCommand

from marketdata.models import DailyCandle
from marketdata.services import PriceUnavailable, fetch_daily_candles


class Command(BaseCommand):
    help = "Fetch daily candles for one symbol and report the stored date range."

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument("symbol", type=str)
        parser.add_argument("--bars", type=int, default=None)

    def handle(self, *args: Any, **options: Any) -> None:
        symbol = options["symbol"]
        bars = options["bars"]

        if bars is None:
            result = fetch_daily_candles(symbol)
        else:
            result = fetch_daily_candles(symbol, bars=bars)

        stored = DailyCandle.objects.filter(symbol=result.symbol).count()

        if isinstance(result, PriceUnavailable):
            self.stdout.write(
                f"status=unavailable reason={result.reason} stored={stored}"
            )
            if result.message:
                self.stdout.write(result.message)
            return

        parts = [f"status={result.status}"]
        if result.reason:
            parts.append(f"reason={result.reason}")
        first = result.candles[0].date if result.candles else None
        last = result.candles[-1].date if result.candles else None
        parts.append(f"candles={len(result.candles)}")
        parts.append(f"first={first}")
        parts.append(f"last={last}")
        parts.append(f"stored={stored}")
        self.stdout.write(" ".join(parts))

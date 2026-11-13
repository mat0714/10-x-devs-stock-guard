from typing import Any

from django.core.management.base import BaseCommand

from detection.services import score_formation
from marketdata.services import PriceUnavailable, PriceSeries, fetch_daily_candles


class Command(BaseCommand):
    help = "Grade the bearish formation for one symbol and print the evidence."

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

        if isinstance(result, PriceUnavailable):
            self.stdout.write(
                f"status=unavailable reason={result.reason}"
            )
            return

        self._report(result)

    def _report(self, result: PriceSeries) -> None:
        self.stdout.write(f"status={result.status}")
        self.stdout.write(f"candles={len(result.candles)}")

        score = score_formation(result)
        self.stdout.write(f"pattern={score.pattern}")
        self.stdout.write(f"stage={score.stage}")
        self.stdout.write(f"grade={score.grade}")
        self.stdout.write(f"score={score.score:.3f}")

        if score.evidence is None:
            self.stdout.write("evidence=none")
            return

        for pivot in score.evidence.pivots:
            self.stdout.write(
                f"pivot={pivot.date} price={pivot.price:.2f} kind={pivot.kind}"
            )
        if score.evidence.neckline is not None:
            self.stdout.write(f"neckline={score.evidence.neckline:.2f}")

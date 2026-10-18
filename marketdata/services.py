import logging
from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.conf import settings
from django.db import transaction
from django.db.models import Max
from django.utils import timezone

from marketdata.models import DailyCandle
from marketdata.providers import Candle, ProviderError
from marketdata.providers import twelvedata

NEW_YORK = ZoneInfo("America/New_York")
SESSION_CLOSE = time(16, 0)

_logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PriceSeries:
    symbol: str
    candles: tuple[Candle, ...]
    status: str
    reason: str | None = None
    message: str = ""


@dataclass(frozen=True)
class PriceUnavailable:
    symbol: str
    reason: str
    message: str = ""


FetchResult = PriceSeries | PriceUnavailable


def fetch_daily_candles(symbol: str, *, bars: int | None = None) -> FetchResult:
    normalized = symbol.strip().upper()
    if not normalized:
        return PriceUnavailable(symbol=normalized, reason="invalid_symbol")

    lookback = bars if bars is not None else settings.MARKET_DATA_LOOKBACK_BARS
    now = timezone.now()

    newest = DailyCandle.objects.filter(symbol=normalized).aggregate(
        newest=Max("fetched_at"),
    )["newest"]
    if newest is not None and newest >= _last_completed_close(now):
        return PriceSeries(
            symbol=normalized,
            candles=_load(normalized),
            status="ok",
            reason="cached",
        )

    api_key = settings.TWELVE_DATA_API_KEY
    if not api_key:
        return _failure(normalized, "not_configured", "")

    try:
        candles = twelvedata.fetch_daily(
            normalized,
            bars=lookback,
            timeout=settings.MARKET_DATA_HTTP_TIMEOUT,
            api_key=api_key,
        )
    except ProviderError as exc:
        return _failure(normalized, exc.reason, exc.message)

    with transaction.atomic():
        _store(normalized, candles, now, lookback)
    return PriceSeries(symbol=normalized, candles=_load(normalized), status="ok")


def _failure(symbol: str, reason: str, message: str) -> FetchResult:
    _logger.warning("Market data fetch failed for %s: %s", symbol, reason)
    candles = _load(symbol)
    if candles:
        return PriceSeries(
            symbol=symbol,
            candles=candles,
            status="stale",
            reason=reason,
            message=message,
        )
    return PriceUnavailable(symbol=symbol, reason=reason, message=message)


def _store(
    symbol: str,
    candles: list[Candle],
    fetched_at: datetime,
    lookback: int,
) -> None:
    rows = [
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
    DailyCandle.objects.bulk_create(
        rows,
        update_conflicts=True,
        unique_fields=["symbol", "date"],
        update_fields=["open", "high", "low", "close", "volume", "fetched_at"],
    )

    if DailyCandle.objects.filter(symbol=symbol).count() <= lookback:
        return
    cutoff = (
        DailyCandle.objects.filter(symbol=symbol)
        .order_by("-date")
        .values_list("date", flat=True)[lookback - 1]
    )
    DailyCandle.objects.filter(symbol=symbol, date__lt=cutoff).delete()


def _load(symbol: str) -> tuple[Candle, ...]:
    rows = (
        DailyCandle.objects.filter(symbol=symbol)
        .order_by("date")
        .values_list("date", "open", "high", "low", "close", "volume")
    )
    return tuple(
        Candle(
            date=day,
            open=open_,
            high=high,
            low=low,
            close=close,
            volume=volume,
        )
        for day, open_, high, low, close, volume in rows
    )


def _last_completed_close(now: datetime) -> datetime:
    now_ny = now.astimezone(NEW_YORK)
    day = now_ny.date()
    if now_ny < datetime.combine(day, SESSION_CLOSE, tzinfo=NEW_YORK):
        day -= timedelta(days=1)
    while day.weekday() >= 5:
        day -= timedelta(days=1)
    return datetime.combine(day, SESSION_CLOSE, tzinfo=NEW_YORK).astimezone(UTC)

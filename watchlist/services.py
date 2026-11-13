import logging
import time
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from django.conf import settings
from django.db import connection

from detection.services import FormationScore, score_formation
from marketdata.services import PriceSeries, fetch_daily_candles

from .models import WatchlistItem

_logger = logging.getLogger(__name__)

# Hard ceiling on the scan pool so an over-eager env override cannot fan out an
# unbounded number of threads (and their DB connections) from a single request.
MAX_SCAN_WORKERS = 32


@dataclass(frozen=True)
class Row:
    item: WatchlistItem
    score: FormationScore | None
    stale: bool = False
    message: str = ''


def scan_watchlist(
    items: Iterable[WatchlistItem],
    *,
    max_workers: int | None = None,
    per_row_timeout: float | None = None,
    budget_seconds: float | None = None,
) -> list[Row]:
    """Scan a watchlist in bounded-parallel, one isolated row per item.

    Every item is fetched and scored in its own pool task; rows keep the input
    order, a task that raises degrades to a row message, and a task still
    running when the total budget is spent yields a "still scanning" row
    rather than blocking the request. Defaults come from settings.
    """
    items = list(items)
    if max_workers is None:
        max_workers = settings.WATCHLIST_SCAN_MAX_WORKERS
    if per_row_timeout is None:
        per_row_timeout = settings.WATCHLIST_SCAN_PER_SYMBOL_TIMEOUT
    if budget_seconds is None:
        budget_seconds = settings.WATCHLIST_SCAN_BUDGET_SECONDS

    pool = ThreadPoolExecutor(
        max_workers=min(max(1, max_workers), MAX_SCAN_WORKERS)
    )
    futures = [
        pool.submit(_build_row, item, per_row_timeout) for item in items
    ]
    deadline = time.monotonic() + budget_seconds
    rows = []
    try:
        for item, future in zip(items, futures):
            remaining = deadline - time.monotonic()
            try:
                rows.append(future.result(timeout=max(0.0, remaining)))
            except TimeoutError:
                rows.append(
                    Row(
                        item=item,
                        score=None,
                        stale=False,
                        message='still scanning',
                    )
                )
    finally:
        pool.shutdown(wait=False, cancel_futures=True)
    return rows


def _build_row(item: WatchlistItem, per_row_timeout: float | None) -> Row:
    try:
        result = fetch_daily_candles(item.symbol, timeout=per_row_timeout)
        if isinstance(result, PriceSeries):
            return Row(
                item=item,
                score=score_formation(result),
                stale=result.status == 'stale',
                message=result.message,
            )
        return Row(
            item=item,
            score=None,
            stale=False,
            message=result.message or result.reason.replace('_', ' '),
        )
    except Exception:
        _logger.warning(
            'Formation analysis failed for %s', item.symbol, exc_info=True
        )
        return Row(
            item=item, score=None, stale=False, message='analysis failed'
        )
    finally:
        connection.close()

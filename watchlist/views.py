from dataclasses import dataclass

from django.contrib.auth.decorators import login_required
from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from detection.services import FormationScore, score_formation
from marketdata.services import PriceSeries, fetch_daily_candles

from .forms import WatchlistItemForm
from .models import WatchlistItem


@dataclass(frozen=True)
class Row:
    item: WatchlistItem
    score: FormationScore | None
    stale: bool = False
    message: str = ''


def _build_row(item: WatchlistItem) -> Row:
    try:
        result = fetch_daily_candles(item.symbol)
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
        return Row(
            item=item, score=None, stale=False, message='analysis failed'
        )


@login_required
def index(request):
    if request.method == 'POST':
        form = WatchlistItemForm(request.POST, user=request.user)
        if form.is_valid():
            try:
                with transaction.atomic():
                    form.save()
            except IntegrityError:
                form.add_error(
                    'symbol', 'This stock is already on your watchlist.'
                )
            else:
                return redirect('watchlist')
    else:
        form = WatchlistItemForm(user=request.user)
    items = request.user.watchlist_items.all()
    rows = [_build_row(item) for item in items]
    return render(
        request,
        'watchlist/list.html',
        {'form': form, 'items': items, 'rows': rows},
    )


@login_required
@require_POST
def remove(request, pk):
    item = get_object_or_404(WatchlistItem, pk=pk, user=request.user)
    item.delete()
    return redirect('watchlist')

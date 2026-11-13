from django.contrib.auth.decorators import login_required
from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .forms import WatchlistItemForm
from .models import WatchlistItem
from .services import scan_watchlist


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
    rows = scan_watchlist(items)
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

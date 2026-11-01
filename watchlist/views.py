from django.contrib.auth.decorators import login_required
from django.db import IntegrityError, transaction
from django.shortcuts import redirect, render

from .forms import WatchlistItemForm


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
    return render(
        request,
        'watchlist/list.html',
        {'form': form, 'items': request.user.watchlist_items.all()},
    )
